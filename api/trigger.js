/**
 * Vercel Serverless Function: GitHub Actions パイプライントリガー
 * POST /api/trigger → GitHub Actions の blog-pipeline ワークフローを手動起動
 */

const WORKFLOW_FILE = 'blog-pipeline.yml';
const DEFAULT_REF = 'main';

function githubHeaders(githubToken) {
  return {
    Authorization: `Bearer ${githubToken}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
  };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function findRecentWorkflowRun({ githubToken, repo, startedAt }) {
  const runsUrl = new URL(`https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/runs`);
  runsUrl.searchParams.set('branch', DEFAULT_REF);
  runsUrl.searchParams.set('event', 'workflow_dispatch');
  runsUrl.searchParams.set('per_page', '5');

  const startedMs = startedAt.getTime() - 30000;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    if (attempt > 0) await sleep(1500);
    const response = await fetch(runsUrl, {
      headers: githubHeaders(githubToken),
    });
    if (!response.ok) continue;

    const data = await response.json();
    const run = (data.workflow_runs || []).find((item) => {
      const createdMs = Date.parse(item.created_at || '');
      return Number.isFinite(createdMs) && createdMs >= startedMs;
    });
    if (run) {
      return {
        id: run.id,
        run_number: run.run_number,
        status: run.status,
        conclusion: run.conclusion,
        html_url: run.html_url,
        created_at: run.created_at,
      };
    }
  }
  return null;
}

function normalizeStringList(rawValue) {
  if (Array.isArray(rawValue)) {
    return rawValue.map((item) => String(item || '').trim()).filter(Boolean);
  }
  return String(rawValue || '')
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizePayloads(rawPayloads) {
  if (Array.isArray(rawPayloads)) {
    return rawPayloads.filter((item) => item && typeof item === 'object');
  }
  if (rawPayloads && typeof rawPayloads === 'object') {
    return [rawPayloads];
  }
  return [];
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  try {
    const url = `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
    const startedAt = new Date();
    const requestId = String(req.body?.request_id || req.body?.requestId || `trigger-${startedAt.getTime()}`).trim();
    const sourceType = String(req.body?.source_type || req.body?.sourceType || '').trim();
    const rawUrls = req.body?.source_urls || req.body?.sourceUrls || req.body?.urls || req.body?.url || '';
    const sourceUrls = normalizeStringList(rawUrls);
    const rawPayloads = req.body?.source_payloads || req.body?.sourcePayloads || req.body?.payloads || '';
    const sourcePayloads = normalizePayloads(rawPayloads);
    const sourcePayloadsInput = sourcePayloads.length > 0
      ? JSON.stringify(sourcePayloads)
      : String(rawPayloads || '').trim();
    const status = String(req.body?.status || '単品').trim() || '単品';
    const dispatchInputs = {
      mode: String(req.body?.mode || 'batch'),
      source_type: sourceType,
      source_urls: sourceUrls.length > 0 ? JSON.stringify(sourceUrls) : '',
      source_payloads: sourcePayloadsInput,
      status,
      request_id: requestId,
    };
    const dispatchBody = {
      ref: DEFAULT_REF,
      inputs: dispatchInputs,
    };

    const dispatchSize = JSON.stringify(dispatchBody).length;
    if (dispatchSize > 62000) {
      return res.status(413).json({
        success: false,
        request_id: requestId,
        error: `GitHub Actionsに渡す入力が大きすぎます (${dispatchSize} chars)。Chrome拡張側のpayload圧縮を確認してください。`,
      });
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: githubHeaders(githubToken),
      body: JSON.stringify(dispatchBody),
    });

    if (response.status === 204) {
      const run = await findRecentWorkflowRun({ githubToken, repo, startedAt });
      return res.status(200).json({
        success: true,
        request_id: requestId,
        workflow: WORKFLOW_FILE,
        actions_url: `https://github.com/${repo}/actions/workflows/${WORKFLOW_FILE}`,
        run,
        message: 'パイプラインを起動しました。GitHub Actionsでの進捗を確認してください。',
      });
    }

    const errText = await response.text();
    return res.status(response.status).json({
      success: false,
      request_id: requestId,
      workflow: WORKFLOW_FILE,
      error: `GitHub Actions起動失敗 (${response.status})`,
      details: errText,
    });
  } catch (error) {
    console.error('Trigger Error:', error);
    return res.status(500).json({ error: error.message });
  }
}
