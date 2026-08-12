import { syncGitHubActionsRefreshToken } from './onedrive-token-sync.js';

const GRAPH_API = 'https://graph.microsoft.com/v1.0';
const TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const VERCEL_API = 'https://api.vercel.com';
const RETRYABLE = new Set([429, 500, 502, 503, 504]);
const CONTROL_FOLDER = process.env.ACCESSORIES_CONTROL_FOLDER || 'Blog_Vercel_Accessories_Control';

function encodePath(value) {
  return String(value || '').split('/').filter(Boolean).map(encodeURIComponent).join('/');
}

async function updateVercelRefreshToken(newRefreshToken) {
  const token = process.env.VERCEL_TOKEN;
  const projectId = process.env.VERCEL_PROJECT_ID;
  if (!token || !projectId) return;
  const list = await fetch(`${VERCEL_API}/v9/projects/${projectId}/env?limit=100`, { headers: { Authorization: `Bearer ${token}` } });
  if (!list.ok) return;
  const data = await list.json();
  const target = (data.envs || []).find((item) => item.key === 'ONEDRIVE_REFRESH_TOKEN');
  if (!target) return;
  await fetch(`${VERCEL_API}/v9/projects/${projectId}/env/${target.id}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: newRefreshToken }),
  });
}

export async function getOneDriveToken() {
  const required = [process.env.ONEDRIVE_CLIENT_ID, process.env.ONEDRIVE_CLIENT_SECRET, process.env.ONEDRIVE_REFRESH_TOKEN];
  if (!required.every(Boolean)) throw new Error('OneDrive認証情報が不足しています');
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: process.env.ONEDRIVE_CLIENT_ID,
      client_secret: process.env.ONEDRIVE_CLIENT_SECRET,
      refresh_token: process.env.ONEDRIVE_REFRESH_TOKEN,
      grant_type: 'refresh_token',
      scope: 'Files.ReadWrite.All offline_access',
    }).toString(),
  });
  if (!response.ok) throw new Error(`OneDrive token取得失敗: HTTP ${response.status}`);
  const data = await response.json();
  if (data.refresh_token && data.refresh_token !== process.env.ONEDRIVE_REFRESH_TOKEN) {
    process.env.ONEDRIVE_REFRESH_TOKEN = data.refresh_token;
    await Promise.allSettled([
      updateVercelRefreshToken(data.refresh_token),
      syncGitHubActionsRefreshToken(data.refresh_token),
    ]);
  }
  return data.access_token;
}

async function graphFetch(url, options = {}) {
  let response;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    response = await fetch(url, options);
    if (!RETRYABLE.has(response.status) || attempt === 3) return response;
    const retryAfter = Number(response.headers.get('retry-after'));
    const wait = Number.isFinite(retryAfter) ? retryAfter * 1000 : Math.min(750 * 2 ** attempt, 5000);
    await new Promise((resolve) => setTimeout(resolve, wait));
  }
  return response;
}

async function ensureFolder(token, folderPath) {
  let parentId = '';
  let current = '';
  for (const segment of String(folderPath || '').split('/').filter(Boolean)) {
    current = current ? `${current}/${segment}` : segment;
    const lookup = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodePath(current)}?$select=id`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (lookup.ok) {
      parentId = (await lookup.json()).id;
      continue;
    }
    if (lookup.status !== 404) throw new Error(`OneDriveフォルダ確認失敗: HTTP ${lookup.status}`);
    const createUrl = parentId ? `${GRAPH_API}/me/drive/items/${parentId}/children` : `${GRAPH_API}/me/drive/root/children`;
    const created = await graphFetch(createUrl, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: segment, folder: {}, '@microsoft.graph.conflictBehavior': 'fail' }),
    });
    if (created.status === 409) {
      // MLX/Geminiのプロンプ初期化が並行し、另リクエストが先に同名フォルダを作った場合は成功として再取得する。
      const racedLookup = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodePath(current)}?$select=id`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (racedLookup.ok) {
        parentId = (await racedLookup.json()).id;
        continue;
      }
    }
    if (!created.ok) throw new Error(`OneDriveフォルダ作成失敗: HTTP ${created.status}`);
    parentId = (await created.json()).id;
  }
  return parentId;
}

export async function downloadArticle(token, fileId) {
  const response = await graphFetch(`${GRAPH_API}/me/drive/items/${encodeURIComponent(fileId)}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`親記事読み込み失敗: HTTP ${response.status}`);
  return (await response.text()).replace(/^\ufeff/, '');
}

export async function downloadTextPath(token, targetPath) {
  const response = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodePath(targetPath)}:/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`OneDriveテキスト読み込み失敗: HTTP ${response.status}`);
  return (await response.text()).replace(/^\ufeff/, '');
}

export function jobPath(jobId) {
  return `${CONTROL_FOLDER}/jobs/${jobId}.json`;
}

export async function putJson(token, targetPath, value, { ifMatch = '' } = {}) {
  const parent = targetPath.includes('/') ? targetPath.slice(0, targetPath.lastIndexOf('/')) : '';
  if (parent) await ensureFolder(token, parent);
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json; charset=utf-8',
  };
  if (ifMatch) headers['If-Match'] = ifMatch;
  const response = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodePath(targetPath)}:/content`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(value, null, 2),
  });
  if (response.status === 412) throw new Error('OneDriveジョブを他の処理が更新しました');
  if (!response.ok) throw new Error(`OneDrive JSON保存失敗: HTTP ${response.status}`);
  return response.json();
}

export async function getJson(token, targetPath) {
  const meta = await graphFetch(`${GRAPH_API}/me/drive/root:/${encodePath(targetPath)}?$select=id,eTag`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (meta.status === 404) return null;
  if (!meta.ok) throw new Error(`OneDrive JSON確認失敗: HTTP ${meta.status}`);
  const item = await meta.json();
  const content = await graphFetch(`${GRAPH_API}/me/drive/items/${item.id}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!content.ok) throw new Error(`OneDrive JSON読み込み失敗: HTTP ${content.status}`);
  return { value: await content.json(), eTag: item.eTag || '' };
}

export async function putJob(token, job, options = {}) {
  return putJson(token, jobPath(job.job_id), job, options);
}

export async function getJob(token, jobId) {
  return getJson(token, jobPath(jobId));
}

export async function getWorkerHeartbeat(token) {
  return getJson(token, `${CONTROL_FOLDER}/worker/heartbeat.json`);
}

export function controlFolder() {
  return CONTROL_FOLDER;
}
