const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const DEFAULT_FOLDER = process.env.INFO_VIEWER_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/投資info_viewer';
const STATE_RELATIVE_PATH = 'state/pipeline_state.json';

function encodeFolderPath(folderPath = '') {
  return String(folderPath)
    .split('/')
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join('/');
}

async function updateVercelEnvToken(newRefreshToken) {
  const vercelToken = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!vercelToken || !projectId) return;

  try {
    const listRes = await fetch(
      `${VERCEL_API}/v9/projects/${projectId}/env?limit=100`,
      { headers: { Authorization: `Bearer ${vercelToken}` } }
    );
    if (!listRes.ok) return;
    const listData = await listRes.json();
    const targetEnv = (listData.envs || []).find((env) => env.key === 'ONEDRIVE_REFRESH_TOKEN');
    if (!targetEnv) return;

    await fetch(`${VERCEL_API}/v9/projects/${projectId}/env/${targetEnv.id}`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${vercelToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ value: newRefreshToken }),
    });
  } catch (error) {
    console.warn('refresh token update skipped:', error.message);
  }
}

async function getAccessToken() {
  const params = new URLSearchParams({
    client_id: process.env.ONEDRIVE_CLIENT_ID,
    client_secret: process.env.ONEDRIVE_CLIENT_SECRET,
    refresh_token: process.env.ONEDRIVE_REFRESH_TOKEN,
    grant_type: 'refresh_token',
    scope: 'Files.ReadWrite.All offline_access',
  });

  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!response.ok) {
    throw new Error(`OneDrive token 取得失敗: ${response.status}`);
  }

  const data = await response.json();
  if (data.refresh_token && data.refresh_token !== process.env.ONEDRIVE_REFRESH_TOKEN) {
    updateVercelEnvToken(data.refresh_token).catch(console.warn);
  }
  return data.access_token;
}

function normalizeYoutubeUrl(url = '') {
  const raw = String(url || '').trim();
  if (!raw) return '';

  try {
    const parsed = new URL(raw);
    const host = parsed.hostname.toLowerCase();
    let videoId = '';

    if (host.includes('youtu.be')) {
      videoId = parsed.pathname.replace(/^\/+/, '').split('/')[0] || '';
    } else if (host.includes('youtube.com')) {
      if (parsed.pathname === '/watch') {
        videoId = parsed.searchParams.get('v') || '';
      } else if (parsed.pathname.startsWith('/shorts/') || parsed.pathname.startsWith('/live/')) {
        videoId = parsed.pathname.replace(/^\/+/, '').split('/')[1] || '';
      }
    }

    if (!videoId) return raw;
    return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
  } catch {
    return raw;
  }
}

function blankState() {
  return {
    version: 1,
    updatedAt: '',
    videos: {},
  };
}

function stateUrl() {
  return `${GRAPH_API}/me/drive/root:/${encodeFolderPath(`${DEFAULT_FOLDER}/${STATE_RELATIVE_PATH}`)}:/content`;
}

async function loadState(token) {
  const response = await fetch(stateUrl(), {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (response.status === 404) {
    return blankState();
  }
  if (!response.ok) {
    throw new Error(`state 読み込み失敗: ${response.status}`);
  }

  const payload = await response.json();
  if (!payload || typeof payload !== 'object') {
    return blankState();
  }

  if (!payload.videos || typeof payload.videos !== 'object') {
    payload.videos = {};
  }
  return payload;
}

async function saveState(token, state) {
  const response = await fetch(stateUrl(), {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify(state, null, 2),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`state 保存失敗: ${response.status} ${text}`);
  }

  return response.json();
}

function ensurePriorityRecord(state, body) {
  const normalizedVideoUrl = normalizeYoutubeUrl(body.video_url || body.youtubeUrl || '');
  if (!normalizedVideoUrl) {
    throw new Error('video_url が不足しています');
  }

  if (!state.videos || typeof state.videos !== 'object') {
    state.videos = {};
  }

  const now = new Date().toISOString();
  const existing = state.videos[normalizedVideoUrl] || {};
  const record = {
    normalizedVideoUrl,
    firstSeenAt: existing.firstSeenAt || now,
    lastSeenAt: now,
    lastAttemptAt: existing.lastAttemptAt || '',
    attemptCount: Number(existing.attemptCount || body.queueAttemptCount || 0),
    lastError: existing.lastError || body.lastFailureMessage || '',
    lastStage: existing.lastStage || body.lastFailureStage || 'Gemini',
    lastFailureAt: existing.lastFailureAt || body.lastFailureAt || '',
    active: true,
    removedAt: '',
    videoUrl: body.video_url || body.youtubeUrl || normalizedVideoUrl,
    videoTitle: body.title || existing.videoTitle || '',
    channelName: body.channelName || existing.channelName || '',
    channelUrl: body.channelUrl || existing.channelUrl || '',
    publishedAt: body.publishedAt || existing.publishedAt || '',
    duration: body.duration || existing.duration || '',
    thumbnailUrl: body.thumbnailUrl || existing.thumbnailUrl || '',
    rowNumber: body.rowNumber || existing.rowNumber || null,
    sheetStatus: body.sheetStatus || existing.sheetStatus || '',
    status: 'pending',
    nextRetryAt: now,
    processingStartedAt: '',
    manualPriorityAt: now,
  };

  state.videos[normalizedVideoUrl] = record;
  state.updatedAt = now;
  return record;
}

async function dispatchPriorityWorkflow(videoUrl) {
  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return {
      workflowTriggered: false,
      warning: 'GITHUB_TOKEN が設定されていないため、次回スケジュール実行で処理されます。',
    };
  }

  const response = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/info-viewer-queue.yml/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          mode: 'process_queue',
          max_items: '1',
          channel_name: '',
          video_url: videoUrl,
          rebuild_manifest_only: 'false',
        },
      }),
    }
  );

  if (response.status === 204) {
    return {
      workflowTriggered: true,
      warning: '',
    };
  }

  return {
    workflowTriggered: false,
    warning: `GitHub Actions 起動失敗: ${response.status} ${await response.text()}`,
  };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const token = await getAccessToken();
    const state = await loadState(token);
    const record = ensurePriorityRecord(state, req.body || {});
    await saveState(token, state);
    const dispatchResult = await dispatchPriorityWorkflow(record.normalizedVideoUrl);

    return res.status(200).json({
      success: true,
      message: dispatchResult.workflowTriggered
        ? '最優先キューへ移動し、GitHub Actions を起動しました。'
        : '最優先キューへ移動しました。',
      workflowTriggered: dispatchResult.workflowTriggered,
      warning: dispatchResult.warning || '',
      videoUrl: record.normalizedVideoUrl,
      manualPriorityAt: record.manualPriorityAt,
    });
  } catch (error) {
    console.error('info-viewer-priority error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}
