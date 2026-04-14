/**
 * Xpost_blog 統合 API。
 * Vercel Hobby の Function 数を抑えるため、resource query で処理を分岐する。
 */

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const DEFAULT_FOLDER = process.env.XPOST_BLOG_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/X投稿';
const TECH_AFFILIATE_FILE_PATH = process.env.XPOST_BLOG_TECH_AFFILIATE_FILE_PATH
  || '開発/Blog_Vercel/Xpost_Blog/tech_affiliate/affiliate_links.txt';

function encodeFolderPath(folderPath = '') {
  return String(folderPath)
    .split('/')
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join('/');
}

function parseAffiliateMemos(content = '') {
  const memos = {};
  const parts = String(content || '').split(/===MEMO(\d+)===/);
  for (let i = 1; i < parts.length; i += 2) {
    const memoNumber = parseInt(parts[i], 10);
    if (Number.isFinite(memoNumber)) {
      memos[`memo${memoNumber}`] = (parts[i + 1] || '').trim();
    }
  }
  if (Object.keys(memos).length === 0) memos.memo1 = '';
  return memos;
}

function buildAffiliateFileContent(memos = {}) {
  const memoNumbers = Object.keys(memos)
    .map((key) => parseInt(String(key).replace('memo', ''), 10))
    .filter(Number.isFinite)
    .sort((a, b) => a - b);

  const numbers = memoNumbers.length ? memoNumbers : [1];
  return numbers
    .map((number) => `===MEMO${number}===\n${memos[`memo${number}`] || ''}\n`)
    .join('\n');
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

function parseFrontmatterFields(frontmatter = '') {
  const text = String(frontmatter || '').trim();
  if (!text.startsWith('---')) return {};

  const normalized = text
    .replace(/^---\s*\n?/, '')
    .replace(/\n?---\s*$/, '');
  const fields = {};

  for (const line of normalized.split('\n')) {
    const separator = line.indexOf(':');
    if (separator < 0) continue;

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    if (!key) continue;

    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    fields[key] = value.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  }

  return fields;
}

function normalizeXUrl(url = '') {
  const raw = String(url || '').trim();
  if (!raw) return '';

  const candidate = raw.startsWith('http://') || raw.startsWith('https://') ? raw : `https://${raw}`;
  try {
    const parsed = new URL(candidate);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
    const parts = parsed.pathname.split('/').filter(Boolean);
    if (!['x.com', 'twitter.com'].includes(host)) return candidate;

    if (parts.length >= 3 && parts[1] === 'status') {
      return `https://x.com/i/status/${parts[2]}`;
    }
    if (parts.length >= 3 && parts[0] === 'i' && ['status', 'article'].includes(parts[1])) {
      return `https://x.com/i/${parts[1]}/${parts[2]}`;
    }
  } catch {
    return candidate;
  }

  return candidate;
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (value === undefined || value === null) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return '';
}

function toInteger(value) {
  const parsed = Number.parseInt(String(value ?? '').replace(/,/g, ''), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function timestampMs(value) {
  const date = new Date(value || '');
  const time = date.getTime();
  return Number.isNaN(time) ? 0 : time;
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

function findItemBySourceId(manifest, sourceId) {
  const items = Array.isArray(manifest?.items) ? manifest.items : [];
  const target = String(sourceId || '').trim();
  if (!target) return null;
  return items.find((item) => String(item.sourceId || '').trim() === target) || null;
}

function findItemByPostUrl(manifest, postUrl) {
  const items = Array.isArray(manifest?.items) ? manifest.items : [];
  const target = normalizeXUrl(postUrl);
  if (!target) return null;

  return items.find((item) => {
    const candidates = [item.normalizedPostUrl, item.postUrl].map((value) => normalizeXUrl(value));
    return candidates.includes(target);
  }) || null;
}

function enrichArticlesWithManifest(articles, manifest) {
  const items = Array.isArray(manifest?.items) ? manifest.items : [];
  const byArticleId = new Map();

  for (const item of items) {
    const articleId = firstNonEmpty(item.articleId, item.hasArticle ? item.id : '');
    if (articleId) byArticleId.set(articleId, item);
  }

  return articles.map((article) => {
    const item = byArticleId.get(article.id);
    if (!item) {
      return {
        ...article,
        discordPostedAt: '',
        sourcePublishedAt: '',
        sortPublishedAt: article.lastModified || '',
      };
    }

    const discordPostedAt = firstNonEmpty(item.discordPostedAt, item.discordPublishedAt, item.observedAt);
    const sourcePublishedAt = firstNonEmpty(item.sourcePublishedAt, item.publishedAt);
    const articleUpdatedAt = firstNonEmpty(item.articleUpdatedAt, article.lastModified);

    return {
      ...article,
      h1Title: firstNonEmpty(article.h1Title, item.title),
      sourceTitle: item.sourceTitle || '',
      postUrl: item.postUrl || '',
      normalizedPostUrl: item.normalizedPostUrl || '',
      sourcePublishedAt,
      discordPostedAt,
      sortPublishedAt: firstNonEmpty(discordPostedAt, sourcePublishedAt, articleUpdatedAt, article.lastModified),
      articleUpdatedAt,
      sourceUpdatedAt: item.sourceUpdatedAt || '',
      discordMessageId: item.discordMessageId || '',
      discordJumpUrl: item.discordJumpUrl || '',
      discordChannelId: item.discordChannelId || '',
      channelName: item.channelName || '',
    };
  });
}

function buildFallbackItemFromArticle(articleId, metadata = {}, manifestItem = null) {
  const sourceId = firstNonEmpty(manifestItem?.sourceId, metadata.source_file_id);
  const postUrl = firstNonEmpty(manifestItem?.postUrl, metadata.post_url, metadata.normalized_post_url);
  const normalizedPostUrl = firstNonEmpty(
    manifestItem?.normalizedPostUrl,
    normalizeXUrl(metadata.normalized_post_url || metadata.post_url),
    postUrl,
  );
  const sourceTitle = firstNonEmpty(
    manifestItem?.sourceTitle,
    metadata.title,
    manifestItem?.title,
    normalizedPostUrl,
  );

  return {
    ...(manifestItem || {}),
    id: articleId,
    articleId,
    hasArticle: true,
    articleStatus: manifestItem?.articleStatus || '記事あり',
    sourceId,
    sourceStatus: sourceId ? '元投稿あり' : '未取得',
    title: firstNonEmpty(manifestItem?.title, metadata.title, normalizedPostUrl, articleId),
    sourceTitle,
    postUrl,
    normalizedPostUrl,
    publishedAt: firstNonEmpty(manifestItem?.publishedAt, metadata.published_at),
    observedAt: firstNonEmpty(manifestItem?.observedAt, metadata.observed_at),
    authorName: firstNonEmpty(metadata.author_name, manifestItem?.authorName),
    authorScreenName: firstNonEmpty(metadata.author_screen_name, manifestItem?.authorScreenName),
    favoriteCount: manifestItem?.favoriteCount ?? toInteger(metadata.favorite_count),
    repostCount: manifestItem?.repostCount ?? toInteger(metadata.repost_count),
    replyCount: manifestItem?.replyCount ?? toInteger(metadata.reply_count),
    quoteCount: manifestItem?.quoteCount ?? toInteger(metadata.quote_count),
    bookmarkCount: manifestItem?.bookmarkCount ?? toInteger(metadata.bookmark_count),
    viewCount: manifestItem?.viewCount ?? toInteger(metadata.view_count),
    discordMessageId: firstNonEmpty(metadata.discord_message_id, manifestItem?.discordMessageId),
    discordJumpUrl: firstNonEmpty(metadata.discord_jump_url, manifestItem?.discordJumpUrl),
    channelName: firstNonEmpty(manifestItem?.channelName, metadata.discord_channel_name),
  };
}

async function resolveSourceBundleForArticle(token, manifest, articleId) {
  const directItem = findItemByArticleId(manifest, articleId);
  if (directItem?.sourceId) {
    return {
      item: directItem,
      sourceContent: directItem.sourceId ? await fetchItemContent(token, directItem.sourceId) : '',
    };
  }

  const articleDocument = parseMarkdownDocument(await getArticle(token, articleId));
  const metadata = parseFrontmatterFields(articleDocument.frontmatter);
  if (directItem) {
    const hydratedItem = buildFallbackItemFromArticle(articleId, metadata, directItem);
    return {
      item: hydratedItem,
      sourceContent: hydratedItem.sourceId ? await fetchItemContent(token, hydratedItem.sourceId) : '',
      sourceFallback: true,
    };
  }

  const fallbackItem = buildFallbackItemFromArticle(
    articleId,
    metadata,
    findItemBySourceId(manifest, metadata.source_file_id)
      || findItemByPostUrl(manifest, metadata.post_url || metadata.normalized_post_url),
  );

  if (!fallbackItem) return null;
  return {
    item: fallbackItem,
    sourceContent: fallbackItem.sourceId ? await fetchItemContent(token, fallbackItem.sourceId) : '',
    sourceFallback: true,
  };
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

    let manifest = null;
    try {
      manifest = await fetchManifest(token);
    } catch (error) {
      console.warn('manifest による記事一覧補強をスキップ:', error.message);
    }

    articles = enrichArticlesWithManifest(articles, manifest);
    articles.sort((a, b) => timestampMs(b.sortPublishedAt || b.lastModified) - timestampMs(a.sortPublishedAt || a.lastModified));
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
    const bundle = await resolveSourceBundleForArticle(token, manifest, articleId);
    if (!bundle?.item) {
      return res.status(404).json({ error: 'articleId に対応する manifest 項目が見つかりません' });
    }
    return res.status(200).json(bundle);
  }

  return res.status(200).json(manifest);
}

async function handleAffiliateRequest(req, res, token) {
  const encodedPath = encodeFolderPath(TECH_AFFILIATE_FILE_PATH);
  const url = `${GRAPH_API}/me/drive/root:/${encodedPath}:/content`;

  if (req.method === 'GET') {
    const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (response.status === 404) {
      return res.status(200).json({ memos: { memo1: '' } });
    }
    if (!response.ok) {
      throw new Error(`tech affiliate 読み込み失敗: ${response.status}`);
    }
    return res.status(200).json({ memos: parseAffiliateMemos(await response.text()) });
  }

  if (req.method === 'PUT') {
    const { memos } = req.body || {};
    if (!memos || typeof memos !== 'object') {
      return res.status(400).json({ error: 'memos は必須です' });
    }
    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'text/plain; charset=utf-8',
      },
      body: buildAffiliateFileContent(memos),
    });
    if (!response.ok) {
      throw new Error(`tech affiliate 保存失敗: ${response.status}`);
    }
    return res.status(200).json({ success: true });
  }

  return res.status(405).json({ error: 'Method not allowed' });
}

async function handleTriggerRequest(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const mode = req.body?.mode || 'full_pipeline';
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
          mode,
          max_items: String(req.body?.max_items ?? '0'),
          post_url: req.body?.post_url || '',
          rebuild_manifest_only: String(Boolean(req.body?.rebuild_manifest_only)),
        },
      }),
    }
  );

  if (response.status === 204) {
    return res.status(200).json({
      success: true,
      message:
        mode === 'process_queue'
          ? 'Xpost_blog QUE処理を起動しました。GitHub Actions で進捗を確認してください。'
          : 'Xpost_blog を最初から実行しました。GitHub Actions で進捗を確認してください。',
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
    if (resource === 'affiliate') {
      return await handleAffiliateRequest(req, res, token);
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
