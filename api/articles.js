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
    throw new Error(`Token取得失敗: ${err}`);
  }

  const data = await res.json();
  return data.access_token;
}

// 記事一覧取得
async function listArticles(token) {
  const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const encodedFolder = folder.split('/').map(encodeURIComponent).join('/');
  const url = `${GRAPH_API}/me/drive/root:/${encodedFolder}:/children?$filter=file ne null&$orderby=lastModifiedDateTime desc&$select=id,name,lastModifiedDateTime,webUrl,size`;

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    // フォルダが存在しない場合は空を返す
    if (res.status === 404) return [];
    throw new Error(`一覧取得失敗: ${res.status}`);
  }

  const data = await res.json();
  return (data.value || [])
    .filter((item) => item.name.endsWith('.md'))
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

  if (!res.ok) throw new Error(`読み込み失敗: ${res.status}`);
  return await res.text();
}

// 記事保存
async function saveArticle(token, filename, content) {
  const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const encodedFolder = folder.split('/').map(encodeURIComponent).join('/');
  const encodedFilename = encodeURIComponent(filename);
  const url = `${GRAPH_API}/me/drive/root:/${encodedFolder}/${encodedFilename}:/content`;

  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/plain',
    },
    body: content,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`保存失敗: ${err}`);
  }

  return await res.json();
}

export default async function handler(req, res) {
  // CORS対応
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

      if (!filename || !content) {
        return res.status(400).json({ error: 'filename と content は必須です' });
      }

      const result = await saveArticle(token, filename, content);
      return res.status(200).json({
        success: true,
        webUrl: result.webUrl || '',
        lastModified: result.lastModifiedDateTime,
      });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('API Error:', error);
    return res.status(500).json({ error: error.message });
  }
}
