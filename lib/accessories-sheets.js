import { createSign } from 'node:crypto';

import { MASTER_HEADERS, REGISTRY_HEADERS, parseMasterValues, safePublicError } from './accessories-core.js';

export const ACCESSORIES_SPREADSHEET_ID = '1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94';
export const MASTER_SHEET_NAME = '周辺機器DB';
export const REGISTRY_SHEET_NAME = '周辺機器DB_LLM';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const SHEETS_API = 'https://sheets.googleapis.com/v4/spreadsheets';
let tokenCache = { token: '', expiresAt: 0 };

function base64Url(value) {
  return Buffer.from(value).toString('base64url');
}

function serviceAccount() {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON || '';
  if (!raw) throw new Error('GOOGLE_SERVICE_ACCOUNT_JSONが設定されていません');
  try {
    const info = JSON.parse(raw);
    if (!info.client_email || !info.private_key) throw new Error('必須値不足');
    return info;
  } catch {
    throw new Error('GOOGLE_SERVICE_ACCOUNT_JSONの形式が不正です');
  }
}

async function accessToken() {
  if (tokenCache.token && Date.now() < tokenCache.expiresAt - 60_000) return tokenCache.token;
  const info = serviceAccount();
  const now = Math.floor(Date.now() / 1000);
  const header = base64Url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const payload = base64Url(JSON.stringify({
    iss: info.client_email,
    scope: 'https://www.googleapis.com/auth/spreadsheets',
    aud: TOKEN_URL,
    iat: now,
    exp: now + 3600,
  }));
  const unsigned = `${header}.${payload}`;
  const signer = createSign('RSA-SHA256');
  signer.update(unsigned);
  signer.end();
  const assertion = `${unsigned}.${signer.sign(info.private_key, 'base64url')}`;
  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion,
    }).toString(),
  });
  if (!response.ok) throw new Error(`Google Sheets認証失敗: HTTP ${response.status}`);
  const data = await response.json();
  tokenCache = { token: data.access_token, expiresAt: Date.now() + Number(data.expires_in || 3600) * 1000 };
  return tokenCache.token;
}

async function sheetsFetch(url, options = {}) {
  const token = await accessToken();
  let lastResponse;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    lastResponse = await fetch(url, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) },
    });
    if (![429, 500, 502, 503, 504].includes(lastResponse.status) || attempt === 3) return lastResponse;
    await new Promise((resolve) => setTimeout(resolve, Math.min(750 * 2 ** attempt, 5000)));
  }
  return lastResponse;
}

function rangeUrl(sheetName, range = '') {
  const a1 = range ? `${sheetName}!${range}` : sheetName;
  return `${SHEETS_API}/${ACCESSORIES_SPREADSHEET_ID}/values/${encodeURIComponent(a1)}`;
}

async function readValues(sheetName, range = '') {
  const response = await sheetsFetch(rangeUrl(sheetName, range));
  if (!response.ok) throw new Error(`Google Sheets読み込み失敗: ${sheetName} HTTP ${response.status}`);
  const data = await response.json();
  return data.values || [];
}

export async function loadAccessoryMaster() {
  const values = await readValues(MASTER_SHEET_NAME, 'A:Z');
  return parseMasterValues(values);
}

async function validateRegistryHeaders() {
  const values = await readValues(REGISTRY_SHEET_NAME, 'A1:L1');
  const actual = values[0] || [];
  if (REGISTRY_HEADERS.some((header, index) => actual[index] !== header)) {
    throw new Error('周辺機器DB_LLMの先頭12列が仕様と一致しません');
  }
}

export function safeSheetText(value) {
  const text = String(value ?? '');
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

export async function appendRegistryJob(job) {
  await validateRegistryHeaders();
  const row = [
    job.created_at,
    '',
    job.article_title,
    '記事化',
    '',
    job.parent.title,
    job.parent.web_url,
    job.category.name,
    job.engine,
    '',
    job.job_id,
    job.batch_id,
  ].map(safeSheetText);
  const url = `${rangeUrl(REGISTRY_SHEET_NAME, 'A:L')}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  const response = await sheetsFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ majorDimension: 'ROWS', values: [row] }),
  });
  if (!response.ok) throw new Error(`周辺機器DB_LLM登録失敗: HTTP ${response.status}`);
}

async function findRegistryRow(jobId) {
  const values = await readValues(REGISTRY_SHEET_NAME, 'A:L');
  if (!values.length) throw new Error('周辺機器DB_LLMが空です');
  const headers = values[0];
  const jobIdIndex = headers.indexOf('ジョブID');
  if (jobIdIndex < 0) throw new Error('周辺機器DB_LLMにジョブID列がありません');
  const matches = values
    .map((row, index) => ({ row, rowNumber: index + 1 }))
    .filter((item) => item.row[jobIdIndex] === jobId);
  if (matches.length !== 1) throw new Error(`周辺機器DB_LLMのジョブIDは1行だけ必要です: ${jobId} (${matches.length}行)`);
  return { headers, ...matches[0] };
}

export async function updateRegistryJob({ jobId, status, completedAt = '', articleUrl = '', errorSummary = '' }) {
  if (!['記事化', '失敗', '完了'].includes(status)) throw new Error(`進捗が不正です: ${status}`);
  const found = await findRegistryRow(jobId);
  const updated = REGISTRY_HEADERS.map((header, index) => found.row[index] || '');
  updated[REGISTRY_HEADERS.indexOf('完了日時')] = status === '完了' ? completedAt : '';
  updated[REGISTRY_HEADERS.indexOf('進捗')] = status;
  updated[REGISTRY_HEADERS.indexOf('記事URLリンク')] = status === '完了' ? articleUrl : '';
  updated[REGISTRY_HEADERS.indexOf('エラー概要')] = status === '失敗' ? safePublicError(errorSummary) : '';
  const response = await sheetsFetch(rangeUrl(REGISTRY_SHEET_NAME, `A${found.rowNumber}:L${found.rowNumber}`) + '?valueInputOption=RAW', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ majorDimension: 'ROWS', values: [updated.map(safeSheetText)] }),
  });
  if (!response.ok) throw new Error(`周辺機器DB_LLM更新失敗: HTTP ${response.status}`);
}

export async function listRegistryJobs({ engine = '', status = '' } = {}) {
  const values = await readValues(REGISTRY_SHEET_NAME, 'A:L');
  if (!values.length) return [];
  const [headers, ...rows] = values;
  return rows
    .map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ''])))
    .filter((row) => (!engine || row['生成エンジン'] === engine) && (!status || row['進捗'] === status));
}

export function requiredHeaderContracts() {
  return { master: MASTER_HEADERS, registry: REGISTRY_HEADERS };
}
