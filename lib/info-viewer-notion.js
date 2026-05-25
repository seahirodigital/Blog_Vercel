import { timingSafeEqual } from 'node:crypto';

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const NOTION_API_BASE = 'https://api.notion.com/v1';
const NOTION_VERSION = process.env.INFO_VIEWER_NOTION_VERSION || '2022-06-28';
const DEFAULT_NOTION_DATABASE_ID = '368c4a3b7cc280989667da064731ee7a';
const PRIMARY_FOLDER =
  process.env.INFO_VIEWER_ONEDRIVE_FOLDER || 'Obsidian in Onedrive 202602/Vercel_Blog/info_viewer';
const LEGACY_FOLDER = 'Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer';

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  if (!leftBuffer.length || leftBuffer.length !== rightBuffer.length) return false;
  return timingSafeEqual(leftBuffer, rightBuffer);
}

function isAuthorized(req) {
  const expected =
    process.env.INFO_VIEWER_ADMIN_SECRET ||
    process.env.ONEDRIVE_SYNC_SECRET ||
    process.env.ONEDRIVE_CLIENT_SECRET ||
    '';
  const supplied = req.headers['x-info-viewer-admin-secret'] || req.headers.authorization?.replace(/^Bearer\s+/i, '') || '';
  return Boolean(expected) && safeEqual(supplied, expected);
}

function encodeFolderPath(folderPath = '') {
  return String(folderPath)
    .split('/')
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join('/');
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

function toTimestamp(value = '') {
  const parsed = Date.parse(String(value || '').replace(/\//g, '-'));
  return Number.isNaN(parsed) ? 0 : parsed;
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
    return videoId ? `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}` : raw;
  } catch {
    return raw;
  }
}

function notionIdFromUrl(urlOrId = '') {
  const value = String(urlOrId || '').trim();
  const compact = value.replace(/-/g, '');
  if (/^[0-9a-f]{32}$/i.test(compact)) return compact.toLowerCase();
  const matches = value.split('?', 1)[0].match(/[0-9a-f]{32}/gi) || value.match(/[0-9a-f]{32}/gi);
  if (!matches?.length) throw new Error(`Notion DB IDを抽出できません: ${urlOrId}`);
  return matches[matches.length - 1].toLowerCase();
}

function hyphenateNotionId(rawId = '') {
  const value = String(rawId || '').replace(/-/g, '').toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(value)) throw new Error(`Notion IDの形式が不正です: ${rawId}`);
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}

function normalizeKey(value = '') {
  return String(value || '').trim().replace(/[ _-]/g, '').toLowerCase();
}

function richText(text = '') {
  const cleaned = String(text || '').trim();
  return cleaned ? [{ type: 'text', text: { content: cleaned.slice(0, 2000) } }] : [];
}

function titleText(text = '') {
  return [{ type: 'text', text: { content: String(text || '').slice(0, 2000) } }];
}

function findProperty(properties = {}, aliases = [], wantedTypes = new Set(), fallbackByType = false) {
  const aliasSet = new Set(aliases.map(normalizeKey));
  for (const [name, prop] of Object.entries(properties)) {
    if (aliasSet.has(normalizeKey(name)) && wantedTypes.has(prop?.type)) return [name, prop];
  }
  if (fallbackByType) {
    for (const [name, prop] of Object.entries(properties)) {
      if (wantedTypes.has(prop?.type)) return [name, prop];
    }
  }
  return null;
}

function findUrlProperty(properties = {}) {
  const exact = findProperty(
    properties,
    ['URL', 'url', 'Youtube', 'YouTube', 'Youtube URL', 'YouTube URL', '動画URL', 'Video URL'],
    new Set(['url', 'rich_text'])
  );
  if (exact) return exact;

  const scored = Object.entries(properties)
    .filter(([, prop]) => ['url', 'rich_text'].includes(prop?.type))
    .map(([name, prop]) => {
      const normalizedName = normalizeKey(name);
      let score = 0;
      if (normalizedName.includes('youtube') || normalizedName.includes('youtu')) score = 100;
      else if (normalizedName.includes('動画url') || normalizedName.includes('動画リンク')) score = 90;
      else if (normalizedName.includes('url')) score = 40;
      return [score, name, prop];
    })
    .filter(([score]) => score > 0)
    .sort((left, right) => right[0] - left[0]);
  return scored.length ? [scored[0][1], scored[0][2]] : null;
}

function buildUrlProperty(prop, url) {
  return prop?.type === 'url' ? { url } : { rich_text: richText(url) };
}

function buildSelectOrTextProperty(prop, value) {
  if (prop?.type === 'select') return value ? { select: { name: String(value).slice(0, 100) } } : { select: null };
  if (prop?.type === 'multi_select') return { multi_select: value ? [{ name: String(value).slice(0, 100) }] : [] };
  return { rich_text: richText(value) };
}

function normalizeNotionDate(value = '') {
  const text = String(value || '').trim();
  if (!text) return '';
  const direct = Date.parse(text);
  if (!Number.isNaN(direct)) {
    return /\d{1,2}:\d{2}|T/.test(text) ? new Date(direct).toISOString() : new Date(direct).toISOString().slice(0, 10);
  }
  const japanese = text.match(/^(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
  if (japanese) {
    const [, year, month, day, hour, minute, second = '00'] = japanese;
    if (!hour) return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${minute}:${second.padStart(2, '0')}`;
  }
  const slash = text.match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T/](\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
  if (slash) {
    const [, year, month, day, hour, minute, second = '00'] = slash;
    if (!hour) return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${minute}:${second.padStart(2, '0')}`;
  }
  return '';
}

function splitFrontmatter(markdown = '') {
  const text = String(markdown || '');
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (!match) return { metadata: {}, body: text };
  const metadata = {};
  for (const line of match[1].split(/\r?\n/)) {
    const index = line.indexOf(':');
    if (index < 0) continue;
    const key = line.slice(0, index).trim();
    let value = line.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    metadata[key] = value.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  }
  return { metadata, body: text.slice(match[0].length) };
}

function textChunks(text = '', size = 1800) {
  const cleaned = String(text || '');
  const chunks = [];
  for (let index = 0; index < cleaned.length; index += size) chunks.push(cleaned.slice(index, index + size));
  return chunks;
}

function block(type, text = '') {
  if (type === 'divider') return { object: 'block', type: 'divider', divider: {} };
  if (type.startsWith('heading_')) return { object: 'block', type, [type]: { rich_text: richText(text) } };
  if (type === 'bulleted_list_item') return { object: 'block', type, [type]: { rich_text: richText(text) } };
  return { object: 'block', type: 'paragraph', paragraph: { rich_text: richText(text) } };
}

function markdownToBlocks(markdown = '') {
  const blocks = [];
  let inCode = false;
  let codeBuffer = [];
  for (const rawLine of String(markdown || '').split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (line.startsWith('```')) {
      if (inCode && codeBuffer.length) {
        for (const chunk of textChunks(codeBuffer.join('\n'))) blocks.push(block('paragraph', chunk));
        codeBuffer = [];
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }
    if (!line.trim()) continue;
    if (line.trim() === '---') blocks.push(block('divider'));
    else if (line.startsWith('# ')) blocks.push(block('heading_1', line.slice(2)));
    else if (line.startsWith('## ')) blocks.push(block('heading_2', line.slice(3)));
    else if (line.startsWith('### ')) blocks.push(block('heading_3', line.slice(4)));
    else if (line.startsWith('- ') || line.startsWith('* ')) blocks.push(block('bulleted_list_item', line.slice(2)));
    else for (const chunk of textChunks(line)) blocks.push(block('paragraph', chunk));
  }
  if (codeBuffer.length) {
    for (const chunk of textChunks(codeBuffer.join('\n'))) blocks.push(block('paragraph', chunk));
  }
  return blocks;
}

async function getOneDriveAccessToken() {
  const params = new URLSearchParams({
    client_id: process.env.ONEDRIVE_CLIENT_ID || '',
    client_secret: process.env.ONEDRIVE_CLIENT_SECRET || '',
    refresh_token: process.env.ONEDRIVE_REFRESH_TOKEN || '',
    grant_type: 'refresh_token',
    scope: 'Files.ReadWrite.All offline_access',
  });
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!response.ok) throw new Error(`OneDrive token取得失敗: HTTP ${response.status}`);
  const data = await response.json();
  if (!data.access_token) throw new Error('OneDrive token取得結果に access_token がありません');
  return data.access_token;
}

async function fetchManifest(accessToken) {
  const manifests = [];
  for (const folder of folderCandidates()) {
    const url = `${GRAPH_API}/me/drive/root:/${encodeFolderPath(folder)}/manifest.json:/content`;
    const response = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.status === 404) continue;
    if (!response.ok) throw new Error(`manifest取得失敗: HTTP ${response.status}`);
    const manifest = await response.json();
    manifests.push({ ...manifest, baseFolder: manifest.baseFolder || folder });
  }
  manifests.sort((left, right) => toTimestamp(right.generatedAt || right.updatedAt) - toTimestamp(left.generatedAt || left.updatedAt));
  if (!manifests.length) throw new Error('manifest.json が見つかりません');
  return manifests[0];
}

async function fetchArticleContent(accessToken, itemId) {
  const response = await fetch(`${GRAPH_API}/me/drive/items/${encodeURIComponent(itemId)}/content`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new Error(`記事本文取得失敗: HTTP ${response.status}`);
  return response.text();
}

function getNotionToken() {
  return process.env.NOTION_API_KEY || '';
}

function getNotionDatabaseId() {
  return notionIdFromUrl(
    process.env.NOTION_DATABASE_ID || DEFAULT_NOTION_DATABASE_ID
  );
}

async function notionRequest(method, path, body) {
  const response = await fetch(`${NOTION_API_BASE}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${getNotionToken()}`,
      'Notion-Version': NOTION_VERSION,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Notion APIエラー HTTP ${response.status}: ${(await response.text()).slice(0, 1000)}`);
  return response.status === 204 ? {} : response.json();
}

async function appendChildren(pageId, children) {
  for (let index = 0; index < children.length; index += 100) {
    const chunk = children.slice(index, index + 100);
    if (chunk.length) await notionRequest('PATCH', `/blocks/${pageId}/children`, { children: chunk });
  }
}

async function findExistingPage(databaseId, urlProperty, youtubeUrl) {
  if (!urlProperty || !youtubeUrl) return '';
  const [name, prop] = urlProperty;
  const filter =
    prop.type === 'url'
      ? { property: name, url: { equals: youtubeUrl } }
      : { property: name, rich_text: { equals: youtubeUrl } };
  const result = await notionRequest('POST', `/databases/${hyphenateNotionId(databaseId)}/query`, { filter, page_size: 1 });
  return result.results?.[0]?.id || '';
}

function buildProperties(database, item, metadata) {
  const databaseProperties = database.properties || {};
  const titleProperty = findProperty(databaseProperties, ['タイトル', '動画タイトル', 'Name', '名前'], new Set(['title']), true);
  if (!titleProperty) throw new Error('Notion DBにtitle型プロパティが見つかりません');
  const urlProperty = findUrlProperty(databaseProperties);
  const channelProperty = findProperty(databaseProperties, ['チャンネル名', 'チャンネル', 'Channel'], new Set(['rich_text', 'select', 'multi_select']));
  const dateProperty = findProperty(databaseProperties, ['日付', '動画更新日時', '投稿日', '公開日', 'Date'], new Set(['date']));

  const youtubeUrl = normalizeYoutubeUrl(item.youtubeUrl || metadata.video_url || '');
  const properties = {
    [titleProperty[0]]: { title: titleText(item.title || metadata.title || '無題') },
  };
  if (urlProperty && youtubeUrl) properties[urlProperty[0]] = buildUrlProperty(urlProperty[1], youtubeUrl);
  if (channelProperty) properties[channelProperty[0]] = buildSelectOrTextProperty(channelProperty[1], item.channelName || metadata.channel_name || '');

  const dateValue = normalizeNotionDate(item.videoUpdatedAt || item.publishedAt || metadata.published_at || item.articleUpdatedAt || '');
  if (dateProperty && dateValue) properties[dateProperty[0]] = { date: { start: dateValue } };

  return {
    properties,
    selected: {
      titleProperty: titleProperty[0],
      youtubeProperty: urlProperty?.[0] || '',
      youtubePropertyType: urlProperty?.[1]?.type || '',
      channelProperty: channelProperty?.[0] || '',
      dateProperty: dateProperty?.[0] || '',
      youtubeUrl,
    },
  };
}

async function saveNotionArticle(databaseId, database, item, markdown) {
  const { metadata, body } = splitFrontmatter(markdown);
  const { properties, selected } = buildProperties(database, item, metadata);
  const urlProperty = findUrlProperty(database.properties || {});
  const existingPageId = await findExistingPage(databaseId, urlProperty, selected.youtubeUrl);

  if (existingPageId) {
    await notionRequest('PATCH', `/pages/${existingPageId}`, { properties });
    return { pageId: existingPageId, action: 'updated_existing', selected };
  }

  const children = markdownToBlocks(body);
  const page = await notionRequest('POST', '/pages', {
    parent: { database_id: hyphenateNotionId(databaseId) },
    properties,
    children: children.slice(0, 80),
  });
  await appendChildren(page.id, children.slice(80));
  return { pageId: page.id, action: 'created', selected };
}

function selectTargets(manifest, body = {}) {
  const requestedId = String(body.articleId || '').trim();
  const requestedUrl = normalizeYoutubeUrl(body.videoUrl || '');
  const limit = Math.min(Math.max(Number(body.limit || 5), 1), 20);
  const recent = Array.isArray(manifest.recent) ? manifest.recent : [];
  let targets = recent.filter((item) => item?.hasArticle && item?.articleId);
  if (requestedId) targets = targets.filter((item) => item.articleId === requestedId);
  if (requestedUrl) targets = targets.filter((item) => normalizeYoutubeUrl(item.youtubeUrl || '') === requestedUrl);
  return targets.slice(0, limit);
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-info-viewer-admin-secret');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ success: false, error: 'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ success: false, error: 'Unauthorized' });
  if (!getNotionToken()) return res.status(500).json({ success: false, error: 'NOTION_API_KEY が未設定です' });

  try {
    const accessToken = await getOneDriveAccessToken();
    const manifest = await fetchManifest(accessToken);
    const targets = selectTargets(manifest, req.body || {});
    if (!targets.length) return res.status(404).json({ success: false, error: 'Notion保存対象の記事が見つかりません' });

    const databaseId = getNotionDatabaseId();
    const database = await notionRequest('GET', `/databases/${hyphenateNotionId(databaseId)}`);
    const results = [];
    for (const item of targets) {
      try {
        const markdown = await fetchArticleContent(accessToken, item.articleId);
        const notionResult = await saveNotionArticle(databaseId, database, item, markdown);
        results.push({
          success: true,
          title: item.title,
          articleId: item.articleId,
          youtubeUrl: notionResult.selected.youtubeUrl,
          pageId: notionResult.pageId,
          action: notionResult.action,
          selected: notionResult.selected,
        });
      } catch (error) {
        results.push({
          success: false,
          title: item.title,
          articleId: item.articleId,
          error: error.message,
        });
      }
    }

    return res.status(200).json({
      success: results.every((item) => item.success),
      testedAt: new Date().toISOString(),
      databaseId,
      requested: targets.length,
      saved: results.filter((item) => item.success).length,
      failed: results.filter((item) => !item.success).length,
      results,
    });
  } catch (error) {
    console.error('info-viewer-notion error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}
