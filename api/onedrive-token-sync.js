import { timingSafeEqual } from 'node:crypto';
import { syncGitHubActionsRefreshToken } from './_onedrive-token-sync.js';

const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  if (!leftBuffer.length || leftBuffer.length !== rightBuffer.length) return false;
  return timingSafeEqual(leftBuffer, rightBuffer);
}

function isAuthorized(req) {
  const expected = process.env.ONEDRIVE_SYNC_SECRET || process.env.ONEDRIVE_CLIENT_SECRET || '';
  const supplied = req.headers['x-onedrive-sync-secret'] || '';
  return safeEqual(supplied, expected);
}

async function updateVercelEnvToken(newRefreshToken) {
  const vercelToken = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!vercelToken || !projectId) return false;

  try {
    const listRes = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env?limit=100`, {
      headers: { Authorization: `Bearer ${vercelToken}` },
    });
    if (!listRes.ok) return false;

    const listData = await listRes.json();
    const targetEnv = (listData.envs || []).find((env) => env.key === 'ONEDRIVE_REFRESH_TOKEN');
    if (!targetEnv) return false;

    const updateRes = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env/${targetEnv.id}`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${vercelToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ value: newRefreshToken }),
    });
    return updateRes.ok;
  } catch (error) {
    console.warn('Vercel OneDrive refresh token 同期エラー:', error.message);
    return false;
  }
}

async function refreshOneDriveToken() {
  const currentRefreshToken = process.env.ONEDRIVE_REFRESH_TOKEN;
  const params = new URLSearchParams({
    client_id: process.env.ONEDRIVE_CLIENT_ID,
    client_secret: process.env.ONEDRIVE_CLIENT_SECRET,
    refresh_token: currentRefreshToken,
    grant_type: 'refresh_token',
    scope: 'Files.ReadWrite.All offline_access',
  });

  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  });
  if (!response.ok) {
    throw new Error(`OneDrive token 更新に失敗しました: ${response.status} ${await response.text()}`);
  }

  const data = await response.json();
  if (!data.access_token) {
    throw new Error('OneDrive token 更新結果に access_token がありません');
  }

  const refreshToken = data.refresh_token || currentRefreshToken;
  let vercelEnvUpdated = false;
  if (data.refresh_token && data.refresh_token !== currentRefreshToken) {
    process.env.ONEDRIVE_REFRESH_TOKEN = data.refresh_token;
    vercelEnvUpdated = await updateVercelEnvToken(data.refresh_token);
  }

  const githubSecretSynced = await syncGitHubActionsRefreshToken(refreshToken, { force: true });
  return { refreshToken, vercelEnvUpdated, githubSecretSynced };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-onedrive-sync-secret');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ success: false, error: 'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ success: false, error: 'Unauthorized' });

  try {
    const result = await refreshOneDriveToken();
    return res.status(200).json({
      success: true,
      refreshToken: result.refreshToken,
      vercelEnvUpdated: result.vercelEnvUpdated,
      githubSecretSynced: result.githubSecretSynced,
    });
  } catch (error) {
    console.error('OneDrive token sync error:', error.message);
    return res.status(500).json({ success: false, error: error.message });
  }
}
