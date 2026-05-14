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

async function upsertGithubVariable(repo, token, name, value) {
  const check = await githubFetch(repo, token, `/actions/variables/${name}`);
  const body = JSON.stringify({ name, value });
  if (check.status === 200) {
    const response = await githubFetch(repo, token, `/actions/variables/${name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`GitHub Variable更新失敗: ${response.status} ${text.slice(0, 200)}`);
    }
    return;
  }
  if (check.status !== 404 && !check.ok) {
    const text = await check.text();
    throw new Error(`GitHub Variable確認失敗: ${check.status} ${text.slice(0, 200)}`);
  }

  const response = await githubFetch(repo, token, '/actions/variables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub Variable作成失敗: ${response.status} ${text.slice(0, 200)}`);
  }
}

async function loadSchedules(repo, token) {
  const raw = await readGithubVariable(repo, token, SCHEDULE_VAR_NAME);
  return parseSchedules(raw);
}

async function saveSchedules(repo, token, schedules) {
  const sorted = [...schedules].sort((a, b) => {
    const left = new Date(a.publishAt || 0).getTime();
    const right = new Date(b.publishAt || 0).getTime();
    return left - right;
  });
  await upsertGithubVariable(repo, token, SCHEDULE_VAR_NAME, JSON.stringify(sorted));
  return sorted;
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
        publish_mode: item.mode || 'now',
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
  const publishAt = toIsoString(body.publishAt || body.scheduledAt || body.scheduleAt);
  if (!publishAt) {
    throw new Error('publishAt は必須です');
  }
  if (new Date(publishAt).getTime() <= Date.now() - 60_000) {
    throw new Error('予約日時は現在時刻より後にしてください');
  }

  const now = new Date().toISOString();
  const articleMap = normalizeArticleMap(body.articles);
  return ids.map((fileId) => {
    const meta = articleMap.get(String(fileId)) || {};
    return {
      id: randomUUID(),
      status: 'scheduled',
      fileId: String(fileId),
      title: firstString(meta.title, firstString(body.articleTitle, '')),
      name: firstString(meta.name, firstString(body.articleName, '')),
      path: firstString(meta.path, ''),
      noteTarget,
      noTopImage: Boolean(body.noTopImage || body.no_top_image),
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
      const scheduleId = firstString(req.body?.scheduleId || req.query?.scheduleId, '');
      if (!scheduleId) return res.status(400).json({ error: 'scheduleId は必須です' });
      const schedules = await loadSchedules(repo, githubToken);
      const next = schedules.map((item) => item.id === scheduleId
        ? { ...item, status: 'cancelled', cancelledAt: new Date().toISOString() }
        : item);
      await saveSchedules(repo, githubToken, next);
      return res.status(200).json({ success: true, schedules: next });
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
      const schedules = await saveSchedules(repo, githubToken, [...existing, ...items]);
      return res.status(200).json({
        success: true,
        message: `${items.length}件のnote公開予約を登録しました。`,
        schedules,
        created: items,
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
