/**
 * Vercel Serverless Function: アフィリエイトリンクメモ管理
 * GET  /api/affiliate-links → メモ1〜5を取得（OneDrive Graph API経由）
 * PUT  /api/affiliate-links → メモ1〜5を保存（OneDrive Graph API経由）
 *
 * 常にOneDriveの実ファイルを読み書きし、UIと同期する
 */

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
// OneDrive上の実パス（開発/Blog_Vercel/...）
const AFFILIATE_FILE_PATH = '開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt';

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
  if (!res.ok) throw new Error(`Token取得失敗: ${res.status}`);
  return (await res.json()).access_token;
}

function encodePath(p) {
  return p.split('/').map(encodeURIComponent).join('/');
}

function parseMemos(content) {
  const memos = { memo1: '', memo2: '', memo3: '', memo4: '', memo5: '' };
  const parts = content.split(/===MEMO(\d)===/);
  for (let i = 1; i < parts.length; i += 2) {
    const n = parts[i];
    if (n >= 1 && n <= 5) memos[`memo${n}`] = (parts[i + 1] || '').trim();
  }
  return memos;
}

function buildFileContent(memos) {
  let out = '';
  for (let i = 1; i <= 5; i++) {
    out += `===MEMO${i}===\n`;
    out += (memos[`memo${i}`] || '') + '\n\n';
  }
  return out;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  try {
    const token = await getAccessToken();
    const encoded = encodePath(AFFILIATE_FILE_PATH);

    if (req.method === 'GET') {
      const url = `${GRAPH_API}/me/drive/root:/${encoded}:/content`;
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) {
        if (r.status === 404) return res.status(200).json({ memos: { memo1:'',memo2:'',memo3:'',memo4:'',memo5:'' } });
        throw new Error(`読み込み失敗: ${r.status}`);
      }
      return res.status(200).json({ memos: parseMemos(await r.text()) });
    }

    if (req.method === 'PUT') {
      const { memos } = req.body;
      if (!memos) return res.status(400).json({ error: 'memos は必須です' });
      const url = `${GRAPH_API}/me/drive/root:/${encoded}:/content`;
      const r = await fetch(url, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'text/plain; charset=utf-8' },
        body: buildFileContent(memos),
      });
      if (!r.ok) throw new Error(`保存失敗: ${r.status}`);
      return res.status(200).json({ success: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    console.error('Affiliate API Error:', e.message);
    return res.status(500).json({ error: e.message });
  }
}
