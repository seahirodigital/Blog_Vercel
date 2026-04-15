const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const PRIMARY_FOLDER =
  process.env.INFO_VIEWER_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/info_viewer';
const LEGACY_FOLDER = 'Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer';
const STATE_RELATIVE_PATH = 'state/pipeline_state.json';

function folderCandidates() {
  const configuredFallbacks = String(process.env.INFO_VIEWER_ONEDRIVE_FALLBACK_FOLDERS || '')
    .split(/[\r\n;]+/)
    .map((part) => part.trim().replace(/^\/+|\/+$/g, ''))
    .filter(Boolean);

  const seen = new Set();
  return [PRIMARY_FOLDER, ...configuredFallbacks, LEGACY_FOLDER]
    .map((folder) => String(folder || '').trim().replace(/^\/+|\/+$/g, ''))
    .filter((folder) => folder && !seen.has(folder) && seen.add(folder));
}

function encodeFolderPath(folderPath = '') {
  return String(folderPath)
    .split('/')
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join('/');
}

function fullPath(baseFolder = '', relativePath = '') {
  const cleanBase = String(baseFolder || '').trim().replace(/^\/+|\/+$/g, '');
  const cleanRelative = String(relativePath || '').trim().replace(/^\/+|\/+$/g, '');
  return cleanRelative ? `${cleanBase}/${cleanRelative}` : cleanBase;
}

function stateUrl(baseFolder = PRIMARY_FOLDER) {
  return `${GRAPH_API}/me/drive/root:/${encodeFolderPath(fullPath(baseFolder, STATE_RELATIVE_PATH))}:/content`;
}

async function graphRequest(method, url, accessToken, options = {}) {
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    ...(options.headers || {}),
  };

  return fetch(url, {
    ...options,
    method,
    headers,
  });
}

async function ensureFolderPath(accessToken, folderPath) {
  const cleanPath = String(folderPath || '').trim().replace(/^\/+|\/+$/g, '');
  if (!cleanPath) return null;

  let currentPath = '';
  let parentId = null;

  for (const segment of cleanPath.split('/').filter(Boolean)) {
    currentPath = currentPath ? `${currentPath}/${segment}` : segment;
    const lookupUrl = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(currentPath)}`;
    const lookupRes = await graphRequest('GET', lookupUrl, accessToken);

    if (lookupRes.ok) {
      const payload = await lookupRes.json();
      parentId = payload.id;
      continue;
    }
    if (lookupRes.status !== 404) {
      throw new Error(`OneDrive フォルダ確認失敗: ${lookupRes.status}`);
    }

    const createUrl = parentId
      ? `${GRAPH_API}/me/drive/items/${parentId}/children`
      : `${GRAPH_API}/me/drive/root/children`;
    const createRes = await graphRequest('POST', createUrl, accessToken, {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: segment,
        folder: {},
        '@microsoft.graph.conflictBehavior': 'replace',
      }),
    });
    if (!createRes.ok) {
      throw new Error(`OneDrive フォルダ作成失敗: ${createRes.status} ${await createRes.text()}`);
    }

    const payload = await createRes.json();
    parentId = payload.id;
  }

  return parentId;
}

async function updateVercelEnvToken(newRefreshToken) {
  const vercelToken = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!vercelToken || !projectId) return;

  try {
    const listRes = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env?limit=100`, {
      headers: { Authorization: `Bearer ${vercelToken}` },
    });
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

async function loadState(token) {
  for (const folder of folderCandidates()) {
    const response = await graphRequest('GET', stateUrl(folder), token);

    if (response.status === 404) {
      continue;
    }
    if (!response.ok) {
      throw new Error(`state 読み込み失敗: ${response.status}`);
    }

    const payload = await response.json();
    const state = payload && typeof payload === 'object' ? payload : blankState();
    if (!state.videos || typeof state.videos !== 'object') {
      state.videos = {};
    }
    state.baseFolder = folder;
    return state;
  }

  return {
    ...blankState(),
    baseFolder: PRIMARY_FOLDER,
  };
}

async function saveState(token, state) {
  await ensureFolderPath(token, fullPath(PRIMARY_FOLDER, 'state'));

  const response = await graphRequest('PUT', stateUrl(PRIMARY_FOLDER), token, {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify(state, null, 2),
  });

  if (!response.ok) {
    throw new Error(`state 保存失敗: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

function ensurePriorityRecord(state, body) {
  const normalizedVideoUrl = normalizeYoutubeUrl(body.video_url || body.youtubeUrl || '');
  if (!normalizedVideoUrl) {
    throw new Error('video_url が不足しています。');
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
    videoUpdatedAt: body.videoUpdatedAt || existing.videoUpdatedAt || body.publishedAt || existing.publishedAt || '',
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
      warning: 'GITHUB_TOKEN が未設定のため、次回キュー更新で処理されます。',
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
        ? '最優先キューへ追加し、GitHub Actions を起動しました。'
        : '最優先キューへ追加しました。',
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
