/**
 * Vercel Serverless Function: note予約投稿の取りこぼし防止Cron
 *
 * GET/POST /api/note-post-cron
 *
 * GitHub Actions の schedule が発火しない場合の保険として、期限到来した
 * note公開予約を GitHub Actions の note-post.yml へ投入する。
 */

const GITHUB_API = 'https://api.github.com';
const DEFAULT_REPO = 'seahirodigital/Blog_Vercel';
const DEFAULT_NOTE_TARGET = 'blog_main';
const SCHEDULE_FILE_PATH = 'data/note-post-schedules.json';
const WORKFLOW_FILE = 'note-post.yml';
const DEFAULT_QUEUE_STALE_MINUTES = 45;
const MAX_CLAIM_RETRIES = 3;

function encodeContent(value) {
  return Buffer.from(value, 'utf8').toString('base64');
}

function decodeContent(value) {
  return Buffer.from(String(value || '').replace(/\n/g, ''), 'base64').toString('utf8');
}

function encodeRepoPath(path) {
  return String(path || '').split('/').map(encodeURIComponent).join('/');
}

function parseSchedules(rawValue) {
  if (!rawValue) return [];
  try {
    const parsed = JSON.parse(rawValue);
    return Array.isArray(parsed) ? parsed.filter(item => item && typeof item === 'object') : [];
  } catch {
    return [];
  }
}

function getAuthHeader(req) {
  return String(req.headers?.authorization || req.headers?.Authorization || '');
}

function verifyCronAuth(req) {
  const allowedSecrets = [
    process.env.CRON_SECRET,
    process.env.NOTE_POST_CRON_SECRET,
    process.env.GITHUB_TOKEN,
  ].filter(Boolean);

  if (allowedSecrets.length === 0) {
    return {
      ok: false,
      status: 500,
      error: 'CRON_SECRET または GITHUB_TOKEN が未設定です。',
    };
  }
  const authHeader = getAuthHeader(req);
  return {
    ok: allowedSecrets.some(secret => authHeader === `Bearer ${secret}`),
    status: 401,
    error: 'Unauthorized',
  };
}

function githubHeaders(token, extra = {}) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    ...extra,
  };
}

async function githubFetch(repo, token, path, options = {}) {
  return await fetch(`${GITHUB_API}/repos/${repo}${path}`, {
    ...options,
    headers: githubHeaders(token, options.headers || {}),
  });
}

async function readSchedulesFile(repo, token) {
  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(SCHEDULE_FILE_PATH)}`);
  if (response.status === 404) return { sha: '', schedules: [] };
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`予約ファイル取得失敗: ${response.status} ${text.slice(0, 300)}`);
  }
  const data = await response.json();
  return {
    sha: data.sha || '',
    schedules: parseSchedules(decodeContent(data.content || '')),
  };
}

async function writeSchedulesFile(repo, token, schedules, sha, message) {
  const body = {
    message,
    content: encodeContent(`${JSON.stringify(schedules, null, 2)}\n`),
  };
  if (sha) body.sha = sha;

  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(SCHEDULE_FILE_PATH)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (response.status === 409) {
    const conflict = new Error('予約ファイル更新が競合しました。最新状態で再試行します。');
    conflict.code = 'SCHEDULE_CONFLICT';
    throw conflict;
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`予約ファイル更新失敗: ${response.status} ${text.slice(0, 300)}`);
  }
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value || ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isStaleQueued(item, nowMs, staleMs) {
  if (item.status !== 'queued' || item.publishedAt) return false;
  const queuedMs = Date.parse(item.queuedAt || '');
  return Number.isFinite(queuedMs) && nowMs - queuedMs >= staleMs;
}

function shouldClaim(item, nowMs, staleMs) {
  const publishMs = Date.parse(item.publishAt || '');
  if (!Number.isFinite(publishMs)) return item.status === 'scheduled';
  if (item.status === 'scheduled') return publishMs <= nowMs;
  return isStaleQueued(item, nowMs, staleMs);
}

function buildDispatchInputs(item) {
  return {
    file_id: String(item.fileId || ''),
    no_top_image: String(Boolean(item.noTopImage)),
    note_target: String(item.noteTarget || DEFAULT_NOTE_TARGET),
    publish_mode: 'scheduled_due',
    scheduled_at: String(item.publishAt || ''),
    schedule_id: String(item.id || ''),
    article_title: String(item.title || item.name || ''),
  };
}

async function claimDueSchedules(repo, token, now, source, staleMinutes) {
  const staleMs = staleMinutes * 60 * 1000;
  const nowMs = now.getTime();
  const nowIso = now.toISOString();

  for (let attempt = 1; attempt <= MAX_CLAIM_RETRIES; attempt += 1) {
    const { sha, schedules } = await readSchedulesFile(repo, token);
    const claimed = [];
    const nextSchedules = schedules.map((item) => {
      if (!shouldClaim(item, nowMs, staleMs)) return item;

      if (!item.fileId || !item.id) {
        return {
          ...item,
          status: 'error',
          error: 'fileId または予約IDが空のため起動できません。',
        };
      }

      const claimedItem = {
        ...item,
        status: 'queued',
        queuedAt: nowIso,
        queuedBy: source,
        error: '',
      };
      claimed.push(claimedItem);
      return claimedItem;
    });

    if (claimed.length === 0) {
      return { claimed, checked: schedules.length, attempts: attempt };
    }

    try {
      await writeSchedulesFile(repo, token, nextSchedules, sha, 'Claim due note post schedules');
      return { claimed, checked: schedules.length, attempts: attempt };
    } catch (error) {
      if (error.code === 'SCHEDULE_CONFLICT' && attempt < MAX_CLAIM_RETRIES) {
        continue;
      }
      throw error;
    }
  }

  return { claimed: [], checked: 0, attempts: MAX_CLAIM_RETRIES };
}

async function dispatchNotePostWorkflow(repo, token, item) {
  const response = await githubFetch(repo, token, `/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: 'main',
      inputs: buildDispatchInputs(item),
    }),
  });

  if (response.status === 204) return { success: true };
  const text = await response.text();
  return { success: false, error: text || `HTTP ${response.status}` };
}

async function markDispatchFailures(repo, token, failures) {
  if (failures.length === 0) return;

  for (let attempt = 1; attempt <= MAX_CLAIM_RETRIES; attempt += 1) {
    const { sha, schedules } = await readSchedulesFile(repo, token);
    const failureMap = new Map(failures.map(item => [item.id, item.error]));
    const nextSchedules = schedules.map((item) => {
      if (!failureMap.has(item.id)) return item;
      return {
        ...item,
        status: 'error',
        error: failureMap.get(item.id),
      };
    });

    try {
      await writeSchedulesFile(repo, token, nextSchedules, sha, 'Mark failed note post dispatches');
      return;
    } catch (error) {
      if (error.code === 'SCHEDULE_CONFLICT' && attempt < MAX_CLAIM_RETRIES) {
        continue;
      }
      throw error;
    }
  }
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (!['GET', 'POST'].includes(req.method)) {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const auth = verifyCronAuth(req);
  if (!auth.ok) {
    return res.status(auth.status).json({ error: auth.error });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || DEFAULT_REPO;
  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  const now = new Date();
  const source = String(req.query?.source || req.body?.source || 'vercel-cron').slice(0, 80);
  const staleMinutes = parsePositiveInteger(
    req.query?.staleMinutes || req.body?.staleMinutes || process.env.NOTE_POST_QUEUE_STALE_MINUTES,
    DEFAULT_QUEUE_STALE_MINUTES,
  );

  try {
    const claim = await claimDueSchedules(repo, githubToken, now, source, staleMinutes);
    const dispatched = [];
    const failures = [];

    for (const item of claim.claimed) {
      const result = await dispatchNotePostWorkflow(repo, githubToken, item);
      if (result.success) {
        dispatched.push({ id: item.id, fileId: item.fileId, title: item.title || item.name || '' });
      } else {
        failures.push({
          id: item.id,
          fileId: item.fileId,
          title: item.title || item.name || '',
          error: result.error,
        });
      }
    }

    await markDispatchFailures(repo, githubToken, failures);

    return res.status(200).json({
      success: failures.length === 0,
      checkedAt: now.toISOString(),
      source,
      checked: claim.checked,
      claimed: claim.claimed.length,
      dispatched,
      failures,
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      error: error.message,
    });
  }
}
