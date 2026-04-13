/**
 * Xpost_blog 統合 API。
 * Vercel Hobby の Function 数を抑えるため、resource query で処理を分岐する。
 */

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

function isBlogArticleFile(name = '') {
  return String(name).endsWith('.md') && String(name).includes('_ブログ_');
}

function parseMarkdownDocument(text = '') {
  const raw = String(text || '');
  const match = raw.match(/^---\s*\n[\s\S]*?\n---\s*\n?/);
  if (!match) {
    return {
      raw,
      frontmatter: '',
      body: raw.trim(),
    };
  }
  return {
    raw,
    frontmatter: match[0].trimEnd(),
    body: raw.slice(match[0].length).trim(),
  };
}

function stripFrontmatter(markdownText = '') {
  const parsed = parseMarkdownDocument(markdownText);
  return parsed.body;
}

function extractH1FromMarkdown(text = '') {
  for (const line of String(text || '').split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith('# ') && !trimmed.startsWith('## ')) {
      return trimmed.slice(2).trim();
    }
  }
  return '';
}

async function updateVercelEnvToken(newRefreshToken) {
  const vercelToken = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!vercelToken || !projectId) {
    console.warn('VERCEL_TOKEN or VERCEL_PROJECT_ID が未設定のためトークン更新をスキップ');
    return;
  }

  try {
    const listRes = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env?limit=100`, {
      headers: { Authorization: `Bearer ${vercelToken}` },
    });
    if (!listRes.ok) {
      console.warn('Vercel env list 取得失敗:', listRes.status);
      return;
    }

    const listData = await listRes.json();
    const targetEnv = (listData.envs || []).find((env) => env.key === 'ONEDRIVE_REFRESH_TOKEN');
    if (!targetEnv) {
      console.warn('ONEDRIVE_REFRESH_TOKEN の環境変数IDが見つかりません');
      return;
    }

    const patchRes = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env/${targetEnv.id}`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${vercelToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ value: newRefreshToken }),
    });

    if (!patchRes.ok) {
      console.warn('Vercel env 更新失敗:', patchRes.status, await patchRes.text());
    }
  } catch (error) {
    console.warn('トークン更新エラー (保存処理には影響なし):', error.message);
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
    const errorText = await response.text();
    console.error('OneDrive token error:', errorText);
    throw new Error(`OneDrive token 取得失敗: ${response.status}`);
  }

  const data = await response.json();
  if (data.refresh_token && data.refresh_token !== process.env.ONEDRIVE_REFRESH_TOKEN) {
    updateVercelEnvToken(data.refresh_token).catch(console.warn);
  }
  return data.access_token;
}

async function fetchH1Title(token, fileId) {
  try {
    const response = await fetch(`${GRAPH_API}/me/drive/items/${fileId}/content`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Range: 'bytes=0-1023',
      },
    });
    if (!response.ok && response.status !== 206) return '';
    return extractH1FromMarkdown(await response.text());
  } catch {
    return '';
  }
}

async function listArticlesRecursive(token, folderPath, relativePath = '', depth = 0) {
  if (depth > 5) return [];

  const encoded = encodeFolderPath(folderPath);
  const url = `${GRAPH_API}/me/drive/root:/${encoded}:/children?$select=id,name,lastModifiedDateTime,webUrl,size,folder&$top=200`;
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

  if (!response.ok) {
    if (response.status === 404) return [];
    const errorText = await response.text();
    console.error('OneDrive list error:', response.status, errorText);
    throw new Error(`記事一覧取得失敗: ${response.status}`);
  }

  const data = await response.json();
  const items = data.value || [];
  let articles = [];
  const subFolderPromises = [];

  for (const item of items) {
    if (item.folder) {
      const subRelative = relativePath ? `${relativePath}/${item.name}` : item.name;
      subFolderPromises.push(listArticlesRecursive(token, `${folderPath}/${item.name}`, subRelative, depth + 1));
    } else if (isBlogArticleFile(item.name)) {
      articles.push({
        id: item.id,
        name: item.name,
        path: relativePath,
        lastModified: item.lastModifiedDateTime,
        webUrl: item.webUrl || '',
        size: item.size || 0,
        h1Title: '',
      });
    }
  }

  const subResults = await Promise.all(subFolderPromises);
  for (const subList of subResults) articles = articles.concat(subList);

  await Promise.all(
    articles
      .filter((article) => !article.h1Title)
      .map(async (article) => {
        article.h1Title = await fetchH1Title(token, article.id);
      })
  );

  articles.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
  return articles;
}

async function resolveFolderFromUrl(token, urlStr) {
  let folderId = null;

  try {
    const parsedUrl = new URL(urlStr);
    if (parsedUrl.searchParams.has('id')) {
      folderId = parsedUrl.searchParams.get('id');
    }
  } catch {}

  if (!folderId) {
    try {
      const base64Value = Buffer.from(urlStr).toString('base64');
      const encodedUrl = `u!${base64Value.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`;
      const response = await fetch(`${GRAPH_API}/shares/${encodedUrl}/driveItem`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        return { id: data.id, name: data.name };
      }
    } catch {}
  }

  if (folderId) {
    let apiUrl = `${GRAPH_API}/me/drive/items/${folderId}?$select=id,name`;

    if (folderId.startsWith('/')) {
      const match = folderId.match(/\/Documents\/(.+)$/i);
      if (match) {
        const path = match[1].split('/').map(encodeURIComponent).join('/');
        apiUrl = `${GRAPH_API}/me/drive/root:/${path}?$select=id,name`;
      }
    }

    const response = await fetch(apiUrl, { headers: { Authorization: `Bearer ${token}` } });
    if (response.ok) {
      const data = await response.json();
      return { id: data.id, name: data.name };
    }
    console.warn('resolveFolderFromUrl error:', await response.text());
  }

  return null;
}

async function listArticlesRecursiveById(token, folderId, relativePath, depth = 0) {
  if (depth > 5) return [];

  const url = `${GRAPH_API}/me/drive/items/${folderId}/children?$select=id,name,lastModifiedDateTime,webUrl,size,folder&$top=200`;
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

  if (!response.ok) {
    console.warn('listArticlesRecursiveById error:', await response.text());
    return [];
  }

  const data = await response.json();
  const items = data.value || [];
  let articles = [];
  const subFolderPromises = [];

  for (const item of items) {
    if (item.folder) {
      const subRelative = relativePath ? `${relativePath}/${item.name}` : item.name;
      subFolderPromises.push(listArticlesRecursiveById(token, item.id, subRelative, depth + 1));
    } else if (isBlogArticleFile(item.name)) {
      articles.push({
        id: item.id,
        name: item.name,
        path: relativePath,
        lastModified: item.lastModifiedDateTime,
        webUrl: item.webUrl || '',
        size: item.size || 0,
        h1Title: '',
      });
    }
  }

  const subResults = await Promise.all(subFolderPromises);
  for (const subList of subResults) articles = articles.concat(subList);

  await Promise.all(
    articles
      .filter((article) => !article.h1Title)
      .map(async (article) => {
        article.h1Title = await fetchH1Title(token, article.id);
      })
  );

  return articles;
}

async function getArticle(token, fileId) {
  const response = await fetch(`${GRAPH_API}/me/drive/items/${fileId}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const errorText = await response.text();
    console.error('OneDrive get error:', response.status, errorText);
    throw new Error(`記事読み込み失敗: ${response.status}`);
  }
  return await response.text();
}

async function saveArticle(token, filename, content, fileId = null) {
  const url = fileId
    ? `${GRAPH_API}/me/drive/items/${fileId}/content`
    : `${GRAPH_API}/me/drive/root:/${encodeFolderPath(DEFAULT_FOLDER)}/${encodeURIComponent(filename)}:/content`;

  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/plain; charset=utf-8',
    },
    body: content,
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('OneDrive save error:', response.status, errorText);
    throw new Error(`記事保存失敗: ${response.status}`);
  }
  return await response.json();
}

async function moveArticle(token, fileId, destRelativePath) {
  const destPath = destRelativePath ? `${DEFAULT_FOLDER}/${destRelativePath}` : DEFAULT_FOLDER;
  const folderResponse = await fetch(`${GRAPH_API}/me/drive/root:/${encodeFolderPath(destPath)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!folderResponse.ok) {
    const errorText = await folderResponse.text();
    throw new Error(`移動先フォルダ取得失敗: ${folderResponse.status}: ${errorText}`);
  }

  const folderData = await folderResponse.json();
  const response = await fetch(`${GRAPH_API}/me/drive/items/${fileId}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ parentReference: { id: folderData.id } }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('OneDrive move error:', response.status, errorText);
    throw new Error(`記事移動失敗: ${response.status}`);
  }
  return await response.json();
}

async function renameArticle(token, fileId, newName) {
  const response = await fetch(`${GRAPH_API}/me/drive/items/${fileId}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name: newName }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('OneDrive rename error:', response.status, errorText);
    throw new Error(`記事リネーム失敗: ${response.status}`);
  }
  return await response.json();
}

async function deleteArticle(token, fileId) {
  const response = await fetch(`${GRAPH_API}/me/drive/items/${fileId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok && response.status !== 204) {
    const errorText = await response.text();
    console.error('OneDrive delete error:', response.status, errorText);
    throw new Error(`記事削除失敗: ${response.status}`);
  }
}

async function duplicateArticle(token, fileId, newName, folderPath) {
  const content = await getArticle(token, fileId);
  const targetFolder = folderPath ? `${DEFAULT_FOLDER}/${folderPath}` : DEFAULT_FOLDER;
  const url = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(targetFolder)}/${encodeURIComponent(newName)}:/content`;
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/plain; charset=utf-8',
    },
    body: content,
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('OneDrive duplicate error:', response.status, errorText);
    throw new Error(`記事複製失敗: ${response.status}`);
  }
  return await response.json();
}

async function fetchManifest(token) {
  const url = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(DEFAULT_FOLDER)}/manifest.json:/content`;
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

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
  const response = await fetch(`${GRAPH_API}/me/drive/items/${itemId}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`ファイル読み込み失敗: ${response.status}`);
  }
  return stripFrontmatter(await response.text());
}

function findItemByArticleId(manifest, articleId) {
  const items = Array.isArray(manifest?.items) ? manifest.items : [];
  return items.find((item) => item.articleId === articleId) || null;
}

async function handleArticlesRequest(req, res, token) {
  if (req.method === 'GET') {
    const { id, externalUrls } = req.query;
    if (id) {
      const parsed = parseMarkdownDocument(await getArticle(token, id));
      return res.status(200).json({
        content: parsed.raw,
        body: parsed.body,
        frontmatter: parsed.frontmatter,
      });
    }

    let articles = await listArticlesRecursive(token, DEFAULT_FOLDER, '');
    if (externalUrls) {
      try {
        const urlsList = JSON.parse(externalUrls);
        if (Array.isArray(urlsList) && urlsList.length > 0) {
          const externalResults = await Promise.all(
            urlsList.map(async (urlStr) => {
              const folderInfo = await resolveFolderFromUrl(token, urlStr);
              return folderInfo?.id ? listArticlesRecursiveById(token, folderInfo.id, folderInfo.name) : [];
            })
          );
          for (const externalList of externalResults) articles = articles.concat(externalList);
        }
      } catch (error) {
        console.warn('externalUrls の処理に失敗:', error.message);
      }
    }

    articles.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
    return res.status(200).json({ articles });
  }

  if (req.method === 'PUT') {
    const { filename, content, fileId } = req.body || {};
    if (!filename || content === undefined || content === null) {
      return res.status(400).json({ error: 'filename と content は必須です' });
    }
    const result = await saveArticle(token, filename, content, fileId || null);
    return res.status(200).json({
      success: true,
      id: result.id || '',
      name: result.name || filename,
      webUrl: result.webUrl || '',
      lastModified: result.lastModifiedDateTime || new Date().toISOString(),
      size: result.size || 0,
    });
  }

  if (req.method === 'PATCH') {
    const { fileId, newName, action, destFolderPath } = req.body || {};
    if (action === 'move') {
      if (!fileId || destFolderPath === undefined) {
        return res.status(400).json({ error: 'fileId と destFolderPath は必須です' });
      }
      const result = await moveArticle(token, fileId, destFolderPath);
      return res.status(200).json({
        success: true,
        id: result.id || fileId,
        name: result.name || '',
        path: destFolderPath,
        webUrl: result.webUrl || '',
        lastModified: result.lastModifiedDateTime || new Date().toISOString(),
      });
    }

    if (!fileId || !newName) {
      return res.status(400).json({ error: 'fileId と newName は必須です' });
    }
    const result = await renameArticle(token, fileId, newName);
    return res.status(200).json({
      success: true,
      id: result.id || fileId,
      name: result.name || newName,
      webUrl: result.webUrl || '',
      lastModified: result.lastModifiedDateTime || new Date().toISOString(),
      size: result.size || 0,
    });
  }

  if (req.method === 'DELETE') {
    const { fileId } = req.body || {};
    if (!fileId) return res.status(400).json({ error: 'fileId は必須です' });
    await deleteArticle(token, fileId);
    return res.status(200).json({ success: true });
  }

  if (req.method === 'POST') {
    const { fileId, newName, folderPath } = req.body || {};
    if (!fileId || !newName) {
      return res.status(400).json({ error: 'fileId と newName は必須です' });
    }
    const result = await duplicateArticle(token, fileId, newName, folderPath || '');
    return res.status(200).json({
      success: true,
      id: result.id || '',
      name: result.name || newName,
      webUrl: result.webUrl || '',
      lastModified: result.lastModifiedDateTime || new Date().toISOString(),
      size: result.size || 0,
    });
  }

  return res.status(405).json({ error: 'Method not allowed' });
}

async function handleIndexRequest(req, res, token) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { id, sourceId, articleId } = req.query;
  if (id || sourceId) {
    const content = await fetchItemContent(token, id || sourceId);
    return res.status(200).json({ content });
  }

  const manifest = await fetchManifest(token);
  if (articleId) {
    const item = findItemByArticleId(manifest, articleId);
    if (!item) {
      return res.status(404).json({ error: 'articleId に対応する manifest 項目が見つかりません' });
    }
    const sourceContent = item.sourceId ? await fetchItemContent(token, item.sourceId) : '';
    return res.status(200).json({ item, sourceContent });
  }

  return res.status(200).json(manifest);
}

async function handleTriggerRequest(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';
  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  const response = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/xpost-blog-queue.yml/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: req.body?.ref || 'main',
        inputs: {
          mode: req.body?.mode || 'full_pipeline',
          max_items: String(req.body?.max_items ?? '3'),
          post_url: req.body?.post_url || '',
          rebuild_manifest_only: String(Boolean(req.body?.rebuild_manifest_only)),
        },
      }),
    }
  );

  if (response.status === 204) {
    return res.status(200).json({
      success: true,
      message: 'Xpost_blog パイプラインを起動しました。GitHub Actions で進捗を確認してください。',
    });
  }

  return res.status(response.status).json({
    success: false,
    error: `GitHub API エラー: ${await response.text()}`,
  });
}

function resolveResource(req) {
  return String(req.query?.resource || req.body?.resource || 'articles').toLowerCase();
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, PATCH, DELETE, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    const resource = resolveResource(req);
    if (resource === 'trigger') {
      return await handleTriggerRequest(req, res);
    }

    const token = await getAccessToken();
    if (resource === 'index') {
      return await handleIndexRequest(req, res, token);
    }
    if (resource === 'articles') {
      return await handleArticlesRequest(req, res, token);
    }

    return res.status(400).json({ error: `不明な resource です: ${resource}` });
  } catch (error) {
    console.error('xpost-blog error:', error);
    return res.status(500).json({ error: error.message });
  }
}
