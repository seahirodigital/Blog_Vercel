/**
 * Vercel Serverless Function: 記事CRUD (OneDrive Graph API)
 * GET    /api/articles         → 記事一覧取得
 * GET    /api/articles?id=xxx  → 記事内容取得
 * PUT    /api/articles         → 記事保存（上書き）
 */

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';

async function getAccessToken() {
  const params = new URLSearchParams({
    client_id: process.env.ONEDRIVE_CLIENT_ID,
    client_secret: process.env.ONEDRIVE_CLIENT_SECRET,
    refresh_token: process.env.ONEDRIVE_REFRESH_TOKEN,
    grant_type: 'refresh_token',
    scope: 'Files.ReadWrite.All offline_access',
  });

  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error('Token error response:', err);
    throw new Error(`Token取得失敗: ${res.status}`);
  }

  const data = await res.json();
  return data.access_token;
}

// フォルダパスをエンコード（空白等を含むパス対応）
function encodeFolderPath(folder) {
  return folder.split('/').map(encodeURIComponent).join('/');
}

// 記事一覧取得
async function listArticles(token) {
  const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const encoded = encodeFolderPath(folder);

  // 個人用OneDriveでは $filter が使えないため、シンプルなクエリに変更
  const url = `${GRAPH_API}/me/drive/root:/${encoded}:/children?$select=id,name,lastModifiedDateTime,webUrl,size&$top=100`;

  console.log('List URL:', url);

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    // フォルダが存在しない場合は空を返す（初回起動時等）
    if (res.status === 404) {
      console.log('Folder not found, returning empty list');
      return [];
    }
    const errBody = await res.text();
    console.error('List error:', res.status, errBody);
    throw new Error(`一覧取得失敗: ${res.status}`);
  }

  const data = await res.json();
  return (data.value || [])
    .filter((item) => item.name && item.name.endsWith('.md'))
    .sort((a, b) => new Date(b.lastModifiedDateTime) - new Date(a.lastModifiedDateTime))
    .map((item) => ({
      id: item.id,
      name: item.name,
      lastModified: item.lastModifiedDateTime,
      webUrl: item.webUrl || '',
      size: item.size || 0,
    }));
}

// 記事内容取得
async function getArticle(token, fileId) {
  const url = `${GRAPH_API}/me/drive/items/${fileId}/content`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const errBody = await res.text();
    console.error('Get article error:', res.status, errBody);
    throw new Error(`読み込み失敗: ${res.status}`);
  }
  return await res.text();
}

// 記事保存
async function saveArticle(token, filename, content) {
  const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const encoded = encodeFolderPath(folder);
  const encodedFilename = encodeURIComponent(filename);
  const url = `${GRAPH_API}/me/drive/root:/${encoded}/${encodedFilename}:/content`;

  console.log('Save URL:', url);

  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/plain; charset=utf-8',
    },
    body: content,
  });

  if (!res.ok) {
    const err = await res.text();
    console.error('Save error:', res.status, err);
    throw new Error(`保存失敗: ${res.status}`);
  }

  return await res.json();
}

export default async function handler(req, res) {
  // CORS対応
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    const token = await getAccessToken();

    // GET: 記事一覧 or 記事内容
    if (req.method === 'GET') {
      const { id } = req.query;

      if (id) {
        const content = await getArticle(token, id);
        return res.status(200).json({ content });
      }

      const articles = await listArticles(token);
      return res.status(200).json({ articles });
    }

    // PUT: 記事保存
    if (req.method === 'PUT') {
      const { filename, content } = req.body;

      if (!filename || content === undefined || content === null) {
        return res.status(400).json({ error: 'filename と content は必須です' });
      }

      const result = await saveArticle(token, filename, content);
      return res.status(200).json({
        success: true,
        id: result.id || '',
        name: result.name || filename,
        webUrl: result.webUrl || '',
        lastModified: result.lastModifiedDateTime || new Date().toISOString(),
        size: result.size || 0,
      });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('API Error:', error.message);
    return res.status(500).json({ error: error.message });
  }
}
