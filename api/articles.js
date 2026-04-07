/**
 * Vercel Serverless Function: 記事CRUD (OneDrive Graph API)
 * GET    /api/articles         → 記事一覧取得（サブフォルダ再帰対応）
 * GET    /api/articles?id=xxx  → 記事内容取得
 * PUT    /api/articles         → 記事保存（新規 or 上書き）
 * PATCH  /api/articles         → 記事リネーム
 *
 * ★ トークン自動ローテーション実装済み
 */

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';

// リフレッシュトークンをVercel環境変数に自動更新する
async function updateVercelEnvToken(newRefreshToken) {
  const vercelToken = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!vercelToken || !projectId) {
    console.warn('VERCEL_TOKEN or VERCEL_PROJECT_ID が未設定のためトークン更新をスキップ');
    return;
  }
  try {
    const listRes = await fetch(
      `${VERCEL_API}/v9/projects/${projectId}/env?limit=100`,
      { headers: { Authorization: `Bearer ${vercelToken}` } }
    );
    if (!listRes.ok) { console.warn('Vercel env list 取得失敗:', listRes.status); return; }
    const listData = await listRes.json();
    const targetEnv = (listData.envs || []).find(e => e.key === 'ONEDRIVE_REFRESH_TOKEN');
    if (!targetEnv) { console.warn('ONEDRIVE_REFRESH_TOKEN の環境変数IDが見つかりません'); return; }
    const patchRes = await fetch(
      `${VERCEL_API}/v9/projects/${projectId}/env/${targetEnv.id}`,
      {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${vercelToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: newRefreshToken }),
      }
    );
    if (patchRes.ok) console.log('✅ リフレッシュトークンをVercel環境変数に自動更新しました');
    else console.warn('Vercel env 更新失敗:', patchRes.status, await patchRes.text());
  } catch (e) {
    console.warn('トークン更新エラー (保存処理には影響なし):', e.message);
  }
}

// アクセストークン取得（+ リフレッシュトークン自動ローテーション）
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
    console.error('Token エラー:', err);
    throw new Error(`Token取得失敗: ${res.status}`);
  }
  const data = await res.json();
  if (data.refresh_token && data.refresh_token !== process.env.ONEDRIVE_REFRESH_TOKEN) {
    updateVercelEnvToken(data.refresh_token).catch(console.warn);
  }
  return data.access_token;
}

// フォルダパスのURLエンコード
function encodeFolderPath(folder) {
  return folder.split('/').map(encodeURIComponent).join('/');
}

/**
 * MarkdownテキストからH1タイトルを抽出する
 * `# タイトル` 形式の最初の行を返す。見つからなければ空文字列。
 */
function extractH1FromMarkdown(text) {
  for (const line of text.split('\n')) {
    const s = line.trim();
    if (s.startsWith('# ') && !s.startsWith('## ')) {
      return s.slice(2).trim();
    }
  }
  return '';
}

/**
 * 記事ファイルの先頭1KBをRange取得してH1タイトルを返す
 * 失敗時は空文字列を返す（一覧取得全体はエラーにしない）
 */
async function fetchH1Title(token, fileId) {
  try {
    const url = `${GRAPH_API}/me/drive/items/${fileId}/content`;
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Range: 'bytes=0-1023',
      },
    });
    // 206 Partial Content or 200 OK どちらも受け入れる
    if (!res.ok && res.status !== 206) return '';
    const text = await res.text();
    return extractH1FromMarkdown(text);
  } catch {
    return '';
  }
}

/**
 * 記事一覧を再帰的に取得する（OneDriveのフォルダ階層をそのまま反映）
 * @param {string} token - アクセストークン
 * @param {string} folderPath - OneDriveのフォルダパス（例: "Blog_Articles"）
 * @param {string} relativePath - UIに表示するフォルダ相対パス（例: "2026年記事"）
 * @param {number} depth - 再帰深さ（無限ループ防止、最大5階層）
 */
async function listArticlesRecursive(token, folderPath, relativePath = '', depth = 0) {
  if (depth > 5) return []; // 安全のため最大5階層まで

  const encoded = encodeFolderPath(folderPath);
  const url = `${GRAPH_API}/me/drive/root:/${encoded}:/children?$select=id,name,lastModifiedDateTime,webUrl,size,folder&$top=200`;

  console.log(`LIST (depth=${depth}):`, folderPath);
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

  if (!res.ok) {
    if (res.status === 404) {
      console.log('フォルダが存在しないため空リストを返します:', folderPath);
      return [];
    }
    const errBody = await res.text();
    console.error('List error:', res.status, errBody);
    throw new Error(`一覧取得失敗: ${res.status}`);
  }

  const data = await res.json();
  const items = data.value || [];
  let articles = [];
  const subFolderPromises = [];

  for (const item of items) {
    if (item.folder) {
      // サブフォルダ → 再帰取得（並列化）
      const subRelative = relativePath ? `${relativePath}/${item.name}` : item.name;
      subFolderPromises.push(
        listArticlesRecursive(token, `${folderPath}/${item.name}`, subRelative, depth + 1)
      );
    } else if (item.name && item.name.endsWith('.md')) {
      // Markdownファイル → 記事として追加（H1はあとで並列取得）
      articles.push({
        id: item.id,
        name: item.name,
        path: relativePath,
        lastModified: item.lastModifiedDateTime,
        webUrl: item.webUrl || '',
        size: item.size || 0,
        h1Title: '', // 後で並列取得して埋める
      });
    }
  }

  // サブフォルダを並列取得してマージ
  const subResults = await Promise.all(subFolderPromises);
  for (const sub of subResults) articles = articles.concat(sub);

  // 各記事のH1タイトルを並列取得（先頭1KBのみ）
  await Promise.all(
    articles
      .filter(a => !a.h1Title) // サブフォルダからの記事は既に取得済みの場合スキップ
      .map(async (article) => {
        article.h1Title = await fetchH1Title(token, article.id);
      })
  );

  // 新しい順にソート
  articles.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
  return articles;
}

// 追加: URLからフォルダ情報を取得する
async function resolveFolderFromUrl(token, urlStr) {
  let folderId = null;
  try {
    const u = new URL(urlStr);
    if (u.searchParams.has('id')) {
      folderId = u.searchParams.get('id');
    }
  } catch (e) {}

  if (!folderId) {
    try {
      const base64Value = Buffer.from(urlStr).toString('base64');
      const encodedUrl = 'u!' + base64Value.replace(/\+/g, '-', 'g').replace(/\//g, '_', 'g').replace(/=+$/, '');
      const res = await fetch(`${GRAPH_API}/shares/${encodedUrl}/driveItem`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        folderId = data.id;
        return { id: data.id, name: data.name };
      }
    } catch(e) {}
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

    const res = await fetch(apiUrl, { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const data = await res.json();
      return { id: data.id, name: data.name };
    } else {
      console.warn('resolveFolderFromUrl error:', await res.text());
    }
  }
  return null;
}

// 追加: フォルダID起点での再帰取得
async function listArticlesRecursiveById(token, folderId, relativePath, depth = 0) {
  if (depth > 5) return [];

  const url = `${GRAPH_API}/me/drive/items/${folderId}/children?$select=id,name,lastModifiedDateTime,webUrl,size,folder&$top=200`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

  if (!res.ok) {
    console.warn('listArticlesRecursiveById error', await res.text());
    return [];
  }

  const data = await res.json();
  const items = data.value || [];
  let articles = [];
  const subFolderPromises = [];

  for (const item of items) {
    if (item.folder) {
      const subRelative = relativePath ? `${relativePath}/${item.name}` : item.name;
      subFolderPromises.push(listArticlesRecursiveById(token, item.id, subRelative, depth + 1));
    } else if (item.name && item.name.endsWith('.md')) {
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
  for (const sub of subResults) articles = articles.concat(sub);

  await Promise.all(
    articles
      .filter(a => !a.h1Title)
      .map(async (article) => {
        article.h1Title = await fetchH1Title(token, article.id);
      })
  );

  return articles;
}

// 記事内容取得（ファイルID使用）
async function getArticle(token, fileId) {
  const url = `${GRAPH_API}/me/drive/items/${fileId}/content`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const errBody = await res.text();
    console.error('Get error:', res.status, errBody);
    throw new Error(`読み込み失敗: ${res.status}`);
  }
  return await res.text();
}

// 記事保存（新規: パス指定 / 既存: ファイルID指定）
async function saveArticle(token, filename, content, fileId = null) {
  let url;
  if (fileId) {
    // 既存ファイル: IDで直接上書き（フォルダ位置を維持）
    url = `${GRAPH_API}/me/drive/items/${fileId}/content`;
  } else {
    // 新規ファイル: ルートフォルダに作成
    const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
    const encoded = encodeFolderPath(folder);
    const encodedFile = encodeURIComponent(filename);
    url = `${GRAPH_API}/me/drive/root:/${encoded}/${encodedFile}:/content`;
  }

  console.log('SAVE:', url);
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

// 記事移動（ファイルID + 移動先フォルダの相対パス）
async function moveArticle(token, fileId, destRelativePath) {
  const baseFolder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const destPath = destRelativePath ? `${baseFolder}/${destRelativePath}` : baseFolder;
  // 移動先フォルダのIDを取得
  const folderUrl = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(destPath)}`;
  const folderRes = await fetch(folderUrl, { headers: { Authorization: `Bearer ${token}` } });
  if (!folderRes.ok) {
    const err = await folderRes.text();
    throw new Error(`移動先フォルダ取得失敗: ${folderRes.status}: ${err}`);
  }
  const folderData = await folderRes.json();
  // ファイルを移動（parentReference.idを書き換えるだけ）
  const moveUrl = `${GRAPH_API}/me/drive/items/${fileId}`;
  const res = await fetch(moveUrl, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ parentReference: { id: folderData.id } }),
  });
  if (!res.ok) {
    const err = await res.text();
    console.error('Move error:', res.status, err);
    throw new Error(`移動失敗: ${res.status}`);
  }
  return await res.json();
}

// 記事リネーム（ファイルID + 新ファイル名）
async function renameArticle(token, fileId, newName) {
  const url = `${GRAPH_API}/me/drive/items/${fileId}`;
  console.log('RENAME:', fileId, '->', newName);
  const res = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name: newName }),
  });
  if (!res.ok) {
    const err = await res.text();
    console.error('Rename error:', res.status, err);
    throw new Error(`リネーム失敗: ${res.status}`);
  }
  return await res.json();
}

// 記事削除（ファイルID指定）
async function deleteArticle(token, fileId) {
  const url = `${GRAPH_API}/me/drive/items/${fileId}`;
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok && res.status !== 204) {
    const err = await res.text();
    console.error('Delete error:', res.status, err);
    throw new Error(`削除失敗: ${res.status}`);
  }
}

// 記事複製（コンテンツ読み込み → 同フォルダに新規保存）
async function duplicateArticle(token, fileId, newName, folderPath) {
  const content = await getArticle(token, fileId);
  const baseFolder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
  const targetFolder = folderPath ? `${baseFolder}/${folderPath}` : baseFolder;
  const encoded = encodeFolderPath(targetFolder);
  const encodedFile = encodeURIComponent(newName);
  const url = `${GRAPH_API}/me/drive/root:/${encoded}/${encodedFile}:/content`;
  console.log('DUPLICATE:', url);
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
    console.error('Duplicate error:', res.status, err);
    throw new Error(`複製失敗: ${res.status}`);
  }
  return await res.json();
}

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, PATCH, DELETE, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  try {
    const token = await getAccessToken();

    // GET: 記事一覧 or 記事内容
    if (req.method === 'GET') {
      const { id, externalUrls } = req.query;
      if (id) {
        const content = await getArticle(token, id);
        return res.status(200).json({ content });
      }
      const folder = process.env.ONEDRIVE_FOLDER || 'Blog_Articles';
      let articles = await listArticlesRecursive(token, folder, '');

      if (externalUrls) {
        try {
          const urlsList = JSON.parse(externalUrls);
          if (Array.isArray(urlsList) && urlsList.length > 0) {
            const extPromises = urlsList.map(async (urlStr) => {
              const folderInfo = await resolveFolderFromUrl(token, urlStr);
              if (folderInfo && folderInfo.id) {
                return await listArticlesRecursiveById(token, folderInfo.id, folderInfo.name);
              }
              return [];
            });
            const extResults = await Promise.all(extPromises);
            for (const extList of extResults) {
              articles = articles.concat(extList);
            }
          }
        } catch (e) {
          console.warn('externalUrls の処理に失敗:', e);
        }
      }

      // 新しい順に再ソート
      articles.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
      return res.status(200).json({ articles });
    }

    // PUT: 記事保存
    if (req.method === 'PUT') {
      const { filename, content, fileId } = req.body;
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

    // PATCH: 記事リネーム or 記事移動
    if (req.method === 'PATCH') {
      const { fileId, newName, action, destFolderPath } = req.body;
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

    // DELETE: 記事削除
    if (req.method === 'DELETE') {
      const { fileId } = req.body;
      if (!fileId) return res.status(400).json({ error: 'fileId は必須です' });
      await deleteArticle(token, fileId);
      return res.status(200).json({ success: true });
    }

    // POST: 記事複製
    if (req.method === 'POST') {
      const { fileId, newName, folderPath } = req.body;
      if (!fileId || !newName) return res.status(400).json({ error: 'fileId と newName は必須です' });
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
  } catch (error) {
    console.error('API Error:', error.message);
    return res.status(500).json({ error: error.message });
  }
}
