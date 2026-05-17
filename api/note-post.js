/**
 * Vercel Serverless Function: note公開投稿トリガー
 *
 * GET    /api/note-post        → 予約投稿一覧を返す
 * POST   /api/note-post        → 即時公開 or 予約投稿を登録
 * DELETE /api/note-post        → 予約投稿をキャンセル
 */

import { randomUUID } from 'crypto';

const GITHUB_API = 'https://api.github.com';
const DEFAULT_NOTE_TARGET = 'blog_main';
const ALLOWED_NOTE_TARGETS = new Set(['blog_main', 'xpost_tech']);
const SCHEDULE_VAR_NAME = 'NOTE_POST_SCHEDULES';
const SCHEDULE_FILE_PATH = 'data/note-post-schedules.json';
const RESERVATION_WORKFLOW_PATH = '.github/workflows/note-post-reservations.yml';
const RESERVATION_MONITOR_LEAD_MINUTES = 35;
const RESERVATION_MONITOR_SESSION_MINUTES = 330;
const RESERVATION_MONITOR_POLL_SECONDS = 60;
const RESERVATION_TRIGGER_WINDOW_MINUTES = RESERVATION_MONITOR_LEAD_MINUTES;
const RESERVATION_DIRECT_DISPATCH_MAX_WAIT_SECONDS = 2400;
const RESERVATION_LATE_GRACE_MINUTES = 720;
const RESERVATION_DIRECT_SOURCE = 'github-reservation-direct';

function firstString(value, fallback = '') {
  if (Array.isArray(value)) return value[0] || fallback;
  return typeof value === 'string' ? value : fallback;
}

function normalizeNoteTarget(value) {
  const resolved = typeof value === 'string' && value.trim()
    ? value.trim()
    : DEFAULT_NOTE_TARGET;
  if (!ALLOWED_NOTE_TARGETS.has(resolved)) {
    throw new Error(`noteTarget が不正です: ${resolved}`);
  }
  return resolved;
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

function normalizeArticleMap(articles) {
  const map = new Map();
  if (!Array.isArray(articles)) return map;
  for (const article of articles) {
    if (!article || typeof article !== 'object' || !article.id) continue;
    map.set(String(article.id), {
      title: firstString(article.title, firstString(article.h1Title, firstString(article.name, ''))),
      name: firstString(article.name, ''),
      path: firstString(article.path, ''),
    });
  }
  return map;
}

function toIsoString(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString();
}

function encodeContent(value) {
  return Buffer.from(value, 'utf8').toString('base64');
}

function decodeContent(value) {
  return Buffer.from(String(value || '').replace(/\n/g, ''), 'base64').toString('utf8');
}

function encodeRepoPath(path) {
  return String(path || '').split('/').map(encodeURIComponent).join('/');
}

function cronFromDate(date) {
  return `${date.getUTCMinutes()} ${date.getUTCHours()} ${date.getUTCDate()} ${date.getUTCMonth() + 1} *`;
}

function generateReservationCrons(schedules, now = new Date()) {
  const nowMs = now.getTime();
  const leadMs = RESERVATION_MONITOR_LEAD_MINUTES * 60 * 1000;
  const sessionMs = RESERVATION_MONITOR_SESSION_MINUTES * 60 * 1000;
  const entries = (schedules || [])
    .filter(item => item && item.status === 'scheduled')
    .map((item) => {
      const publishMs = Date.parse(item.publishAt || '');
      return Number.isFinite(publishMs) ? { item, publishMs } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.publishMs - b.publishMs);

  const sessions = [];
  for (const entry of entries) {
    const monitorStartMs = entry.publishMs - leadMs;
    if (monitorStartMs <= nowMs) continue;

    const current = sessions[sessions.length - 1];
    if (current && entry.publishMs <= current.monitorEndMs) {
      continue;
    }

    sessions.push({
      monitorStartMs,
      monitorEndMs: monitorStartMs + sessionMs,
      cron: cronFromDate(new Date(monitorStartMs)),
    });
  }

  return sessions.map(session => session.cron);
}

function buildReservationWorkflow(schedules) {
  const crons = generateReservationCrons(schedules);
  const lines = [
    'name: Note 公開投稿 予約監視セッション',
    '',
    '# このファイルは予約一覧から自動生成します。',
    '# 1回起動した監視ジョブが、セッション中に定期確認して対象予約を起動します。',
    '',
    'on:',
    '  workflow_dispatch:',
  ];

  if (crons.length > 0) {
    lines.push('  schedule:');
    for (const cron of crons) {
      lines.push(`    - cron: '${cron}'`);
    }
  }

  lines.push(
    '',
    'jobs:',
    '  dispatch-reserved-posts:',
    '    runs-on: ubuntu-latest',
    `    timeout-minutes: ${RESERVATION_MONITOR_SESSION_MINUTES + 10}`,
    '    concurrency:',
    '      group: note-post-reservation-dispatch',
    '      cancel-in-progress: false',
    '    permissions:',
    '      actions: write',
    '      contents: write',
    '    steps:',
    '      - name: リポジトリをチェックアウト',
    '        uses: actions/checkout@v4',
    '',
    '      - name: 予約時刻が近い投稿ジョブを監視して起動',
    '        env:',
    '          GH_PAT: ${{ secrets.GH_PAT }}',
    '          GITHUB_TOKEN: ${{ github.token }}',
    '          NOTE_POST_SCHEDULE_SOURCE: github-reservation-monitor',
    `          NOTE_POST_QUEUE_STALE_MINUTES: "90"`,
    `          NOTE_POST_PRESTART_WINDOW_MINUTES: "${RESERVATION_TRIGGER_WINDOW_MINUTES}"`,
    `          NOTE_POST_LATE_GRACE_MINUTES: "${RESERVATION_LATE_GRACE_MINUTES}"`,
    `          NOTE_POST_MONITOR_MODE: "true"`,
    `          NOTE_POST_MONITOR_DURATION_MINUTES: "${RESERVATION_MONITOR_SESSION_MINUTES}"`,
    `          NOTE_POST_MONITOR_POLL_SECONDS: "${RESERVATION_MONITOR_POLL_SECONDS}"`,
    '        run: python .github/scripts/note_post_schedule_dispatch.py',
  );

  return `${lines.join('\n')}\n`;
}

function selectDirectDispatchItems(items, now = new Date()) {
  const nowMs = now.getTime();
  return (items || []).filter((item) => {
    const publishMs = Date.parse(item.publishAt || '');
    if (!Number.isFinite(publishMs)) return false;
    const waitMs = publishMs - nowMs;
    return waitMs <= RESERVATION_DIRECT_DISPATCH_MAX_WAIT_SECONDS * 1000 && waitMs >= -60_000;
  });
}

function markSchedulesQueued(schedules, ids, source, now = new Date()) {
  const targetIds = new Set(ids);
  const queuedAt = now.toISOString();
  return schedules.map((item) => {
    if (!item || !targetIds.has(item.id)) return item;
    return {
      ...item,
      status: 'queued',
      queuedAt,
      queuedBy: source,
      dispatchAttempts: Number(item.dispatchAttempts || 0) + 1,
      error: '',
    };
  });
}

function isCancellableSchedule(item) {
  return item && (item.status === 'scheduled' || item.status === 'queued');
}

async function githubFetch(repo, token, path, options = {}) {
  return await fetch(`${GITHUB_API}/repos/${repo}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(options.headers || {}),
    },
  });
}

async function readRepoFile(repo, token, path) {
  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(path)}`);
  if (response.status === 404) return { exists: false, sha: '', content: '' };
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${path} 取得失敗: ${response.status} ${text.slice(0, 200)}`);
  }
  const data = await response.json();
  return {
    exists: true,
    sha: data.sha || '',
    content: decodeContent(data.content || ''),
  };
}

async function syncReservationWorkflow(repo, token, schedules) {
  const content = buildReservationWorkflow(schedules);
  const current = await readRepoFile(repo, token, RESERVATION_WORKFLOW_PATH);
  if (current.exists && current.content === content) {
    return { updated: false, cronCount: generateReservationCrons(schedules).length };
  }

  const body = {
    message: 'Update note post reservation workflow',
    content: encodeContent(content),
  };
  if (current.sha) body.sha = current.sha;

  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(RESERVATION_WORKFLOW_PATH)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`予約専用Workflow更新失敗: ${response.status} ${text.slice(0, 300)}`);
  }
  return { updated: true, cronCount: generateReservationCrons(schedules).length };
}

async function readGithubVariable(repo, token, name) {
  const response = await githubFetch(repo, token, `/actions/variables/${name}`);
  if (response.status === 404) return '';
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub Variable取得失敗: ${response.status} ${text.slice(0, 200)}`);
  }
  const data = await response.json();
  return data.value || '';
}

async function loadSchedules(repo, token) {
  const file = await readSchedulesFile(repo, token);
  if (file.exists && file.schedules.length > 0) return file.schedules;

  const raw = await readGithubVariable(repo, token, SCHEDULE_VAR_NAME);
  const variableSchedules = parseSchedules(raw);
  if (file.exists) {
    if (variableSchedules.length > 0) {
      await saveSchedules(repo, token, variableSchedules);
      return variableSchedules;
    }
    return file.schedules;
  }

  if (variableSchedules.length > 0) {
    await saveSchedules(repo, token, variableSchedules);
  }
  return variableSchedules;
}

async function saveSchedules(repo, token, schedules) {
  const sorted = [...schedules].sort((a, b) => {
    const left = new Date(a.publishAt || 0).getTime();
    const right = new Date(b.publishAt || 0).getTime();
    return left - right;
  });
  const file = await readSchedulesFile(repo, token);
  const body = {
    message: 'Update note post schedules',
    content: encodeContent(`${JSON.stringify(sorted, null, 2)}\n`),
  };
  if (file.sha) body.sha = file.sha;
  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(SCHEDULE_FILE_PATH)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`予約ファイル更新失敗: ${response.status} ${text.slice(0, 200)}`);
  }
  return sorted;
}

async function readSchedulesFile(repo, token) {
  const response = await githubFetch(repo, token, `/contents/${encodeRepoPath(SCHEDULE_FILE_PATH)}`);
  if (response.status === 404) return { exists: false, sha: '', schedules: [] };
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`予約ファイル取得失敗: ${response.status} ${text.slice(0, 200)}`);
  }
  const data = await response.json();
  return {
    exists: true,
    sha: data.sha || '',
    schedules: parseSchedules(decodeContent(data.content || '')),
  };
}

async function dispatchNotePostWorkflow(repo, token, item) {
  const response = await githubFetch(repo, token, '/actions/workflows/note-post.yml/dispatches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: 'main',
      inputs: {
        file_id: item.fileId,
        no_top_image: String(Boolean(item.noTopImage)),
        note_target: item.noteTarget || DEFAULT_NOTE_TARGET,
        publish_mode: item.mode || (item.id ? 'scheduled_due' : 'now'),
        scheduled_at: item.publishAt || '',
        schedule_id: item.id || '',
        article_title: item.title || item.name || '',
      },
    }),
  });

  if (response.status === 204) return { success: true };
  const text = await response.text();
  return { success: false, error: text || `HTTP ${response.status}` };
}

function buildScheduleItems(ids, body, noteTarget) {
  const now = new Date().toISOString();
  const articleMap = normalizeArticleMap(body.articles);
  const scheduleMap = new Map();
  if (Array.isArray(body.scheduleItems)) {
    for (const item of body.scheduleItems) {
      if (!item || typeof item !== 'object') continue;
      const fileId = firstString(item.fileId || item.id, '');
      if (!fileId) continue;
      scheduleMap.set(String(fileId), item);
    }
  }
  return ids.map((fileId) => {
    const meta = articleMap.get(String(fileId)) || {};
    const scheduleMeta = scheduleMap.get(String(fileId)) || {};
    const publishAt = toIsoString(scheduleMeta.publishAt || scheduleMeta.scheduledAt || body.publishAt || body.scheduledAt || body.scheduleAt);
    if (!publishAt) {
      throw new Error(`publishAt は必須です: ${fileId}`);
    }
    if (new Date(publishAt).getTime() <= Date.now() - 60_000) {
      throw new Error(`予約日時は現在時刻より後にしてください: ${firstString(meta.title, firstString(meta.name, fileId))}`);
    }
    return {
      id: randomUUID(),
      status: 'scheduled',
      fileId: String(fileId),
      title: firstString(scheduleMeta.title, firstString(meta.title, firstString(body.articleTitle, ''))),
      name: firstString(scheduleMeta.name, firstString(meta.name, firstString(body.articleName, ''))),
      path: firstString(scheduleMeta.path, firstString(meta.path, '')),
      noteTarget,
      noTopImage: Boolean(scheduleMeta.noTopImage || scheduleMeta.no_top_image || body.noTopImage || body.no_top_image),
      publishAt,
      createdAt: now,
      queuedAt: '',
      publishedAt: '',
      publishedUrl: '',
      error: '',
    };
  });
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  try {
    if (req.method === 'GET') {
      const schedules = await loadSchedules(repo, githubToken);
      return res.status(200).json({ schedules });
    }

    if (req.method === 'DELETE') {
      const bodyIds = Array.isArray(req.body?.scheduleIds) ? req.body.scheduleIds : [];
      const queryIds = Array.isArray(req.query?.scheduleIds)
        ? req.query.scheduleIds
        : firstString(req.query?.scheduleIds, '').split(',');
      const scheduleIds = [
        firstString(req.body?.scheduleId || req.query?.scheduleId, ''),
        ...bodyIds,
        ...queryIds,
      ].map(id => String(id || '').trim()).filter(Boolean);
      const cancelAll = Boolean(req.body?.cancelAll || req.query?.cancelAll === 'true');
      const schedules = await loadSchedules(repo, githubToken);
      const targetIds = new Set(cancelAll
        ? schedules.filter(isCancellableSchedule).map(item => item.id)
        : scheduleIds);

      if (targetIds.size === 0) {
        return res.status(400).json({ error: 'scheduleId は必須です' });
      }

      const cancelledAt = new Date().toISOString();
      const cancelledIds = [];
      const next = schedules.map((item) => {
        if (!item || !targetIds.has(item.id) || !isCancellableSchedule(item)) return item;
        cancelledIds.push(item.id);
        return { ...item, status: 'cancelled', cancelledAt };
      });
      const saved = await saveSchedules(repo, githubToken, next);
      const reservationWorkflow = await syncReservationWorkflow(repo, githubToken, saved);
      return res.status(200).json({
        success: true,
        schedules: saved,
        cancelledIds,
        cancelledCount: cancelledIds.length,
        reservationWorkflow,
      });
    }

    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }

    const body = req.body || {};
    const ids = Array.isArray(body.fileIds)
      ? body.fileIds.filter(Boolean).map(String)
      : body.fileId
        ? [String(body.fileId)]
        : [];
    if (ids.length === 0) {
      return res.status(400).json({ error: 'fileId または fileIds は必須です' });
    }

    const noteTarget = normalizeNoteTarget(body.noteTarget);
    const mode = firstString(body.mode || body.action, 'now');

    if (mode === 'schedule') {
      const existing = await loadSchedules(repo, githubToken);
      const items = buildScheduleItems(ids, body, noteTarget);
      const directDispatchItems = selectDirectDispatchItems(items);
      const directIds = directDispatchItems.map(item => item.id);
      const prepared = directIds.length > 0
        ? markSchedulesQueued([...existing, ...items], directIds, RESERVATION_DIRECT_SOURCE)
        : [...existing, ...items];
      let schedules = await saveSchedules(repo, githubToken, prepared);
      let reservationWorkflow = await syncReservationWorkflow(repo, githubToken, schedules);
      const directDispatched = [];
      const directFailures = [];

      for (const item of directDispatchItems) {
        const queuedItem = schedules.find(schedule => schedule.id === item.id) || item;
        const result = await dispatchNotePostWorkflow(repo, githubToken, queuedItem);
        if (result.success) {
          directDispatched.push({ id: item.id, fileId: item.fileId, title: item.title || item.name || '' });
        } else {
          directFailures.push({
            id: item.id,
            fileId: item.fileId,
            title: item.title || item.name || '',
            error: result.error,
          });
        }
      }

      if (directFailures.length > 0) {
        const failureMap = new Map(directFailures.map(item => [item.id, item.error]));
        schedules = await saveSchedules(
          repo,
          githubToken,
          schedules.map((item) => failureMap.has(item.id)
            ? { ...item, status: 'error', error: failureMap.get(item.id) }
            : item),
        );
        reservationWorkflow = await syncReservationWorkflow(repo, githubToken, schedules);
      }

      return res.status(200).json({
        success: directFailures.length === 0,
        message: directFailures.length === 0
          ? `${items.length}件のnote公開予約を登録しました。`
          : `予約登録後の事前起動に一部失敗しました: ${directFailures.map(item => item.fileId).join(', ')}`,
        schedules,
        created: items,
        directDispatched,
        directFailures,
        reservationWorkflow,
      });
    }

    const articleMap = normalizeArticleMap(body.articles);
    const results = [];
    for (const fileId of ids) {
      const meta = articleMap.get(fileId) || {};
      const item = {
        id: '',
        fileId,
        title: firstString(meta.title, firstString(body.articleTitle, '')),
        name: firstString(meta.name, firstString(body.articleName, '')),
        noteTarget,
        noTopImage: Boolean(body.noTopImage || body.no_top_image),
        mode: 'now',
      };
      const result = await dispatchNotePostWorkflow(repo, githubToken, item);
      results.push({ fileId, ...result });
      if (ids.length > 1) await new Promise(resolve => setTimeout(resolve, 500));
    }

    const allSuccess = results.every(result => result.success);
    return res.status(200).json({
      success: allSuccess,
      message: allSuccess
        ? `${results.length}件のnote公開投稿を開始しました。`
        : `一部失敗: ${results.filter(result => !result.success).map(result => result.fileId).join(', ')}`,
      results,
    });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}
