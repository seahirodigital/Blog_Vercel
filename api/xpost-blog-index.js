const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const DEFAULT_FOLDER = process.env.XPOST_BLOG_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/X投稿';

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

function stripFrontmatter(markdownText = '') {
  const match = markdownText.match(/^---\s*\n[\s\S]*?\n---\s*\n?/);
  return match ? markdownText.slice(match[0].length).trim() : markdownText.trim();
}

async function fetchManifest(token) {
  const url = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(DEFAULT_FOLDER)}/manifest.json:/content`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (response.status === 404) {
    return {
      generatedAt: null,
      baseFolder: DEFAULT_FOLDER,
      source: 'manifest_missing',
      channels: [],
      items: [],
      recent: [],
      stats: { channelCount: 0, itemCount: 0, articleCount: 0, failureCount: 0 },
      failures: [],
      processingLogs: [],
    };
  }

  if (!response.ok) {
    throw new Error(`manifest 読み込み失敗: ${response.status}`);
  }

  return await response.json();
}

async function fetchItemContent(token, itemId) {
  const url = `${GRAPH_API}/me/drive/items/${itemId}/content`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`ファイル読み込み失敗: ${response.status}`);
  }
  const raw = await response.text();
  return stripFrontmatter(raw);
}

function findItemByArticleId(manifest, articleId) {
  const items = Array.isArray(manifest?.items) ? manifest.items : [];
  return items.find((item) => item.articleId === articleId) || null;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const token = await getAccessToken();
    const { id, sourceId, articleId } = req.query;

    if (id) {
      const content = await fetchItemContent(token, id);
      return res.status(200).json({ content });
    }

    if (sourceId) {
      const content = await fetchItemContent(token, sourceId);
      return res.status(200).json({ content });
    }

    const manifest = await fetchManifest(token);
    if (articleId) {
      const item = findItemByArticleId(manifest, articleId);
      if (!item) {
        return res.status(404).json({ error: 'articleId に対応する manifest 項目が見つかりません' });
      }
      const sourceContent = item.sourceId ? await fetchItemContent(token, item.sourceId) : '';
      return res.status(200).json({
        item,
        sourceContent,
      });
    }

    return res.status(200).json(manifest);
  } catch (error) {
    console.error('xpost-blog-index error:', error);
    return res.status(500).json({ error: error.message });
  }
}