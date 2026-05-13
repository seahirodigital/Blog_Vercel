/**
 * Vercel Serverless Function: アフィリエイトリンクメモ管理
 * GET  /api/affiliate-links → MEMOを動的に取得（OneDrive Graph API経由）
 * PUT  /api/affiliate-links → MEMOを動的に保存（OneDrive Graph API経由）
 */

import { syncGitHubActionsRefreshToken } from './_onedrive-token-sync.js';

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const AFFILIATE_FILE_PATH = '開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt';

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
    if (patchRes.ok) {
      console.log('✅ リフレッシュトークンをVercel環境変数に自動更新しました');
    } else {
      console.warn('Vercel env 更新失敗:', patchRes.status, await patchRes.text());
    }
  } catch (error) {
    console.warn('トークン更新エラー (リンク処理には影響なし):', error.message);
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
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!res.ok) {
    const errorText = await res.text();
    console.error('Token エラー:', errorText);
    throw new Error(`Token取得失敗: ${res.status}`);
  }

  const data = await res.json();
  if (!data.access_token) {
    throw new Error('Token取得結果に access_token がありません');
  }
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

function encodePath(p) {
  return p.split('/').map(encodeURIComponent).join('/');
}

// ===MEMOx=== を動的に検出してオブジェクト化
function parseMemos(content) {
  const memos = {};
  const parts = content.split(/===MEMO(\d+)===/);
  for (let i = 1; i < parts.length; i += 2) {
    const n = parseInt(parts[i], 10);
    memos[`memo${n}`] = (parts[i + 1] || '').trim();
  }
  if (Object.keys(memos).length === 0) memos['memo1'] = '';
  return memos;
}

// 動的なmemosオブジェクトからファイル内容を生成
function buildFileContent(memos) {
  const nums = Object.keys(memos)
    .map(k => parseInt(k.replace('memo', ''), 10))
    .sort((a, b) => a - b);
  let out = '';
  for (const n of nums) {
    out += `===MEMO${n}===\n`;
    out += (memos[`memo${n}`] || '') + '\n\n';
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
      const itemUrl = `${GRAPH_API}/me/drive/root:/${encoded}:`;
      const url = `${GRAPH_API}/me/drive/root:/${encoded}:/content`;
      const headers = { Authorization: `Bearer ${token}` };
      const itemResponse = await fetch(itemUrl, { headers });
      const storageUrl = itemResponse.ok ? (await itemResponse.json()).webUrl || '' : '';
      const r = await fetch(url, { headers });
      if (!r.ok) {
        if (r.status === 404) return res.status(200).json({ memos: { memo1: '' }, storageUrl });
        throw new Error(`読み込み失敗: ${r.status}`);
      }
      return res.status(200).json({ memos: parseMemos(await r.text()), storageUrl });
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
