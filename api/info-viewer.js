import notionHandler from '../lib/info-viewer-notion.js';
import { syncGitHubActionsRefreshToken } from '../lib/onedrive-token-sync.js';

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const GRAPH_RETRY_STATUS_CODES = new Set([429, 500, 502, 503, 504]);
const GRAPH_MAX_RETRIES = 3;
const GRAPH_BASE_DELAY_MS = 750;
const GRAPH_MAX_DELAY_MS = 5000;
const INFO_VIEWER_LOOKBACK_DAYS = Number.parseInt(process.env.INFO_VIEWER_LOOKBACK_DAYS || '21', 10);
const PRIMARY_FOLDER =
  process.env.INFO_VIEWER_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/info_viewer';
const LEGACY_FOLDER = 'Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer';
const STATE_RELATIVE_PATH = 'state/pipeline_state.json';
const ASSET_RELATIVE_FOLDER = 'assets';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function graphRetryDelayMs(response, attempt) {
  const retryAfter = response.headers.get('retry-after');
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds >= 0) {
      return Math.min(seconds * 1000, GRAPH_MAX_DELAY_MS);
    }

    const retryAt = Date.parse(retryAfter);
    if (!Number.isNaN(retryAt)) {
      return Math.min(Math.max(retryAt - Date.now(), 0), GRAPH_MAX_DELAY_MS);
    }
  }

  return Math.min(GRAPH_BASE_DELAY_MS * 2 ** attempt, GRAPH_MAX_DELAY_MS);
}

async function graphFetch(url, options = {}, label = 'graph') {
  for (let attempt = 0; attempt <= GRAPH_MAX_RETRIES; attempt += 1) {
    const response = await fetch(url, options);
    if (!GRAPH_RETRY_STATUS_CODES.has(response.status) || attempt === GRAPH_MAX_RETRIES) {
      return response;
    }

    const waitMs = graphRetryDelayMs(response, attempt);
    console.warn(`${label} returned ${response.status}; retrying in ${waitMs}ms`);
    await sleep(waitMs);
  }

  return fetch(url, options);
}

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

  return graphFetch(url, {
    ...options,
    method,
    headers,
  }, `graph ${method}`);
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
      throw new Error(`OneDrive フォルダ確認に失敗しました: ${lookupRes.status}`);
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
      throw new Error(`OneDrive フォルダ作成に失敗しました: ${createRes.status} ${await createRes.text()}`);
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
    throw new Error(`OneDrive token 更新に失敗しました: ${response.status}`);
  }

  const data = await response.json();
  const issuedRefreshToken = data.refresh_token || '';
  if (data.refresh_token && data.refresh_token !== process.env.ONEDRIVE_REFRESH_TOKEN) {
    process.env.ONEDRIVE_REFRESH_TOKEN = data.refresh_token;
    await Promise.allSettled([
      updateVercelEnvToken(data.refresh_token),
      syncGitHubActionsRefreshToken(data.refresh_token),
    ]);
  } else {
    await syncGitHubActionsRefreshToken(issuedRefreshToken || process.env.ONEDRIVE_REFRESH_TOKEN);
  }
  return data.access_token;
}

function stripFrontmatter(markdownText = '') {
  return splitFrontmatter(markdownText).body;
}

function splitFrontmatter(markdownText = '') {
  const text = String(markdownText || '');
  const match = text.match(/^---\s*\n[\s\S]*?\n---\s*\n?/);
  return {
    frontmatter: match ? match[0] : '',
    body: match ? text.slice(match[0].length) : text,
  };
}

function toTimestamp(value = '') {
  const text = String(value || '').trim();
  if (!text) return 0;

  const direct = Date.parse(text);
  if (!Number.isNaN(direct)) {
    return direct;
  }

  const normalized = text.replace(/\//g, '-').replace(/\s+/g, ' ').trim();
  const compactMatch = normalized.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/);
  if (compactMatch) {
    const [, year, month, day, hour, minute, second] = compactMatch;
    return Date.parse(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`) || 0;
  }

  const dateTimeMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T-])(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (dateTimeMatch) {
    const [, year, month, day, hour, minute, second = '00'] = dateTimeMatch;
    return Date.parse(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`) || 0;
  }

  const dateOnlyMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnlyMatch) {
    const [, year, month, day] = dateOnlyMatch;
    return Date.parse(`${year}-${month}-${day}T00:00:00Z`) || 0;
  }

  return 0;
}

function lookbackCutoffTime() {
  return Date.now() - INFO_VIEWER_LOOKBACK_DAYS * 24 * 60 * 60 * 1000;
}

function manifestItemTime(item = {}) {
  const candidates = [
    item.articleUpdatedAt,
    item.videoUpdatedAt,
    item.publishedAt,
    item.lastFailureAt,
    item.queueNextRetryAt,
    item.manualPriorityAt,
  ];
  return candidates.reduce((latest, value) => Math.max(latest, toTimestamp(value)), 0);
}

function shouldTrackManifestItem(item = {}) {
  const time = manifestItemTime(item);
  return !time || time >= lookbackCutoffTime();
}

function filterManifestLookback(manifest) {
  const channels = Array.isArray(manifest.channels) ? manifest.channels : [];
  const filteredChannels = channels
    .map((channel) => ({
      ...channel,
      videos: Array.isArray(channel.videos)
        ? channel.videos.filter(shouldTrackManifestItem)
        : [],
    }))
    .filter((channel) => channel.videos.length > 0);

  const recent = Array.isArray(manifest.recent)
    ? manifest.recent.filter(shouldTrackManifestItem)
    : [];
  const failures = Array.isArray(manifest.failures)
    ? manifest.failures.filter(shouldTrackManifestItem)
    : [];
  const videoCount = filteredChannels.reduce((count, channel) => count + channel.videos.length, 0);
  const articleCount = filteredChannels.reduce(
    (count, channel) => count + channel.videos.filter((video) => video.hasArticle || video.articleId).length,
    0
  );

  return {
    ...manifest,
    channels: filteredChannels,
    recent,
    failures,
    stats: {
      ...(manifest.stats || {}),
      channelCount: filteredChannels.length,
      videoCount,
      articleCount,
      failureCount: failures.length,
    },
    filter: {
      ...(manifest.filter || {}),
      lookbackDays: INFO_VIEWER_LOOKBACK_DAYS,
      cutoffAt: new Date(lookbackCutoffTime()).toISOString(),
    },
  };
}

function compareFreshness(left, right, selector) {
  const leftTime = toTimestamp(selector(left));
  const rightTime = toTimestamp(selector(right));
  if (leftTime !== rightTime) {
    return rightTime - leftTime;
  }

  const leftPrimary = left.baseFolder === PRIMARY_FOLDER ? 1 : 0;
  const rightPrimary = right.baseFolder === PRIMARY_FOLDER ? 1 : 0;
  return rightPrimary - leftPrimary;
}

async function fetchManifest(token) {
  const manifests = [];
  for (const folder of folderCandidates()) {
    const url = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(folder)}/manifest.json:/content`;
    const response = await graphFetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    }, 'info-viewer manifest');

    if (response.status === 404) {
      continue;
    }
    if (!response.ok) {
      throw new Error(`manifest の取得に失敗しました: ${response.status}`);
    }

    const manifest = await response.json();
    if (!manifest.baseFolder) {
      manifest.baseFolder = folder;
    }
    manifests.push(manifest);
  }

  if (manifests.length) {
    manifests.sort((left, right) =>
      compareFreshness(left, right, (item) => item.generatedAt || item.updatedAt || item.runId)
    );
    return filterManifestLookback(manifests[0]);
  }

  return filterManifestLookback({
    generatedAt: null,
    baseFolder: PRIMARY_FOLDER,
    source: 'manifest_missing',
    channels: [],
    recent: [],
    stats: { channelCount: 0, videoCount: 0, articleCount: 0, failureCount: 0 },
    failures: [],
  });
}

async function fetchArticleRawContent(token, itemId) {
  const url = `${GRAPH_API}/me/drive/items/${encodeURIComponent(itemId)}/content`;
  const response = await graphFetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  }, 'info-viewer article content');
  if (!response.ok) {
    throw new Error(`記事本文の取得に失敗しました: ${response.status}`);
  }

  return response.text();
}

async function fetchArticleContent(token, itemId) {
  const raw = await fetchArticleRawContent(token, itemId);
  return {
    content: stripFrontmatter(raw),
  };
}

async function saveArticleContent(token, itemId, content) {
  const raw = await fetchArticleRawContent(token, itemId);
  const { frontmatter } = splitFrontmatter(raw);
  const nextBody = String(content ?? '').replace(/^\uFEFF/, '');
  const nextContent = `${frontmatter}${nextBody}`;
  const response = await graphFetch(`${GRAPH_API}/me/drive/items/${encodeURIComponent(itemId)}/content`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/plain; charset=utf-8',
    },
    body: nextContent,
  }, 'info-viewer article save');

  if (!response.ok) {
    throw new Error(`記事本文の保存に失敗しました: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

function sanitizeAssetName(name = '', mimeType = '') {
  const fallbackExt = String(mimeType || '').split('/')[1] || 'png';
  const rawName = String(name || `image.${fallbackExt}`).replace(/[\\/:*?"<>|]+/g, '_').trim();
  const normalized = rawName || `image.${fallbackExt}`;
  const hasExt = /\.[A-Za-z0-9]{2,8}$/.test(normalized);
  return hasExt ? normalized : `${normalized}.${fallbackExt}`;
}

function uniqueAssetName(name = '', mimeType = '') {
  const safeName = sanitizeAssetName(name, mimeType);
  const dotIndex = safeName.lastIndexOf('.');
  const base = dotIndex > 0 ? safeName.slice(0, dotIndex) : safeName;
  const ext = dotIndex > 0 ? safeName.slice(dotIndex) : '';
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const random = Math.random().toString(36).slice(2, 8);
  return `${timestamp}_${random}_${base}${ext}`;
}

async function uploadImageAsset(token, body = {}) {
  const mimeType = String(body.mimeType || '').trim();
  if (!mimeType.startsWith('image/')) {
    throw new Error('画像ファイルだけをアップロードできます。');
  }

  const rawData = String(body.data || '').replace(/^data:[^,]+,/, '');
  if (!rawData) {
    throw new Error('画像データが不足しています。');
  }

  const buffer = Buffer.from(rawData, 'base64');
  if (!buffer.length) {
    throw new Error('画像データを読み取れませんでした。');
  }

  const filename = uniqueAssetName(body.name || 'image', mimeType);
  await ensureFolderPath(token, fullPath(PRIMARY_FOLDER, ASSET_RELATIVE_FOLDER));

  const assetPath = fullPath(PRIMARY_FOLDER, `${ASSET_RELATIVE_FOLDER}/${filename}`);
  const response = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodeFolderPath(assetPath)}:/content`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': mimeType,
    },
    body: buffer,
  }, 'info-viewer image upload');

  if (!response.ok) {
    throw new Error(`画像アップロードに失敗しました: ${response.status} ${await response.text()}`);
  }

  const result = await response.json();
  const id = result.id || '';
  return {
    id,
    name: result.name || filename,
    mimeType,
    src: `/api/info-viewer?resource=image&id=${encodeURIComponent(id)}&mime=${encodeURIComponent(mimeType)}`,
  };
}

async function fetchImageAsset(token, itemId, mimeType = '') {
  const safeMime = String(mimeType || '').startsWith('image/') ? String(mimeType) : 'image/png';
  const response = await graphFetch(`${GRAPH_API}/me/drive/items/${encodeURIComponent(itemId)}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  }, 'info-viewer image read');
  if (!response.ok) {
    throw new Error(`画像の取得に失敗しました: ${response.status}`);
  }

  return {
    contentType: response.headers.get('content-type') || safeMime,
    buffer: Buffer.from(await response.arrayBuffer()),
  };
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
  const states = [];
  for (const folder of folderCandidates()) {
    const response = await graphRequest('GET', stateUrl(folder), token);

    if (response.status === 404) {
      continue;
    }
    if (!response.ok) {
      throw new Error(`state の取得に失敗しました: ${response.status}`);
    }

    const payload = await response.json();
    const state = payload && typeof payload === 'object' ? payload : blankState();
    if (!state.videos || typeof state.videos !== 'object') {
      state.videos = {};
    }
    state.baseFolder = folder;
    states.push(state);
  }

  if (states.length) {
    states.sort((left, right) =>
      compareFreshness(left, right, (item) => item.updatedAt || item.generatedAt)
    );
    return states[0];
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
    throw new Error(`state の保存に失敗しました: ${response.status} ${await response.text()}`);
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
      warning: 'GITHUB_TOKEN が未設定のため、キュー更新だけを実施しました。',
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
    warning: `GitHub Actions の起動に失敗しました: ${response.status} ${await response.text()}`,
  };
}

async function deleteArticle(token, articleId) {
  const response = await graphFetch(`${GRAPH_API}/me/drive/items/${encodeURIComponent(articleId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }, 'info-viewer article delete');

  if (response.status === 404) {
    return;
  }
  if (!response.ok) {
    throw new Error(`OneDrive 記事削除に失敗しました: ${response.status} ${await response.text()}`);
  }
}

function resolveResource(req) {
  return String(
    req.query?.resource || req.body?.resource || (req.method === 'DELETE' ? 'article' : 'index')
  ).toLowerCase();
}

async function handleIndexRequest(req, res, token) {
  const articleId = req.query?.id || '';
  if (articleId) {
    const article = await fetchArticleContent(token, articleId);
    return res.status(200).json(article);
  }

  const manifest = await fetchManifest(token);
  return res.status(200).json(manifest);
}

async function handlePriorityRequest(req, res, token) {
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
}

async function handleArticleDeleteRequest(req, res, token) {
  const articleId = req.body?.articleId || '';
  if (!articleId) {
    return res.status(400).json({ success: false, error: 'articleId が不足しています。' });
  }

  await deleteArticle(token, articleId);
  return res.status(200).json({ success: true });
}

async function handleArticleSaveRequest(req, res, token) {
  const articleId = req.body?.articleId || '';
  if (!articleId) {
    return res.status(400).json({ success: false, error: 'articleId が不足しています。' });
  }
  if (req.body?.content === undefined || req.body?.content === null) {
    return res.status(400).json({ success: false, error: 'content が不足しています。' });
  }

  const result = await saveArticleContent(token, articleId, req.body.content);
  return res.status(200).json({
    success: true,
    id: result.id || articleId,
    name: result.name || '',
    webUrl: result.webUrl || '',
    lastModified: result.lastModifiedDateTime || new Date().toISOString(),
    size: result.size || 0,
  });
}

async function handleImageUploadRequest(req, res, token) {
  const image = await uploadImageAsset(token, req.body || {});
  return res.status(200).json({
    success: true,
    ...image,
  });
}

async function handleImageReadRequest(req, res, token) {
  const imageId = req.query?.id || '';
  if (!imageId) {
    return res.status(400).json({ success: false, error: 'id が不足しています。' });
  }

  const image = await fetchImageAsset(token, imageId, req.query?.mime || '');
  res.setHeader('Content-Type', image.contentType);
  res.setHeader('Cache-Control', 'public, max-age=86400');
  return res.status(200).send(image.buffer);
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-info-viewer-admin-secret');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    const resource = resolveResource(req);
    if (resource === 'notion') {
      return await notionHandler(req, res);
    }

    const token = await getAccessToken();

    if (req.method === 'GET' && resource === 'image') {
      return await handleImageReadRequest(req, res, token);
    }
    if (req.method === 'GET') {
      return await handleIndexRequest(req, res, token);
    }
    if (req.method === 'POST' && resource === 'image') {
      return await handleImageUploadRequest(req, res, token);
    }
    if (req.method === 'POST' && resource === 'priority') {
      return await handlePriorityRequest(req, res, token);
    }
    if (req.method === 'PUT' && (resource === 'article' || resource === 'save')) {
      return await handleArticleSaveRequest(req, res, token);
    }
    if (req.method === 'DELETE' && (resource === 'article' || resource === 'delete')) {
      return await handleArticleDeleteRequest(req, res, token);
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('info-viewer error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}
