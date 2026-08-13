import { randomUUID } from 'node:crypto';

import {
  buildChildTitle,
  createJob,
  extractH1,
  loadPromptTemplate,
  matchingCategories,
  parseAffiliateText,
  safePublicError,
  sha256,
} from '../lib/accessories-core.js';
import {
  getJob,
  getOneDriveToken,
  getWorkerHeartbeat,
  putJob,
  putJson,
  getJson,
  controlFolder,
  downloadArticle,
  downloadTextPath,
} from '../lib/accessories-onedrive.js';
import { appendRegistryJob, listRegistryJobs, loadAccessoryMaster, updateRegistryJob } from '../lib/accessories-sheets.js';

const GITHUB_API = 'https://api.github.com';
const AFFILIATE_FILE_PATH = process.env.ACCESSORIES_AFFILIATE_FILE_PATH
  || '開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt';
const PROMPT_CONTRACT_VERSION = 6;

function queryValue(value, fallback = '') {
  return Array.isArray(value) ? value[0] ?? fallback : value ?? fallback;
}

function jsonBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  try { return JSON.parse(req.body || '{}'); } catch { return {}; }
}

function browserPlatform(req, body) {
  return String(body.platform || req.headers['sec-ch-ua-platform'] || req.headers['user-agent'] || '').toLowerCase();
}

function isMac(req, body) {
  return /mac|darwin/.test(browserPlatform(req, body));
}

function heartbeatActive(record) {
  const timestamp = Date.parse(record?.value?.updated_at || record?.value?.timestamp || '');
  return Number.isFinite(timestamp) && Date.now() - timestamp < 90_000;
}

function workerSnapshot(record) {
  const value = record?.value || {};
  return {
    active: heartbeatActive(record),
    state: String(value.state || ''),
    currentJobId: String(value.current_job_id || ''),
    stage: String(value.stage || ''),
    message: String(value.message || ''),
    updatedAt: String(value.updated_at || value.timestamp || ''),
    error: String(value.error || ''),
  };
}

function normalizeFolderPath(value) {
  return String(value || '').normalize('NFC').trim().replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

function accessoryFolderPathFromRegistry(row) {
  const createdAt = new Date(String(row?.['作成日時'] || ''));
  const parentTitle = String(row?.['大元記事タイトル'] || '')
    .normalize('NFC')
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[ .]+$/g, '');
  if (Number.isNaN(createdAt.getTime()) || !parentTitle) return '';
  const jst = new Date(createdAt.getTime() + (9 * 60 * 60 * 1000));
  const pad = (value) => String(value).padStart(2, '0');
  const timestamp = `${jst.getUTCFullYear()}${pad(jst.getUTCMonth() + 1)}${pad(jst.getUTCDate())}_${pad(jst.getUTCHours())}${pad(jst.getUTCMinutes())}`;
  const titlePrefix = [...parentTitle].slice(0, 20).join('').replace(/[ .]+$/g, '');
  return titlePrefix ? `周辺機器/${timestamp}_${titlePrefix}` : '';
}

function matchingFolderBatch(rows, folderPath) {
  const normalizedPath = normalizeFolderPath(folderPath);
  if (!normalizedPath || normalizedPath === '周辺機器') return null;
  const matches = rows.filter((row) => {
    const expectedPath = accessoryFolderPathFromRegistry(row);
    return expectedPath && (
      normalizedPath === expectedPath
      || normalizedPath.startsWith(`${expectedPath}/`)
      || expectedPath.startsWith(`${normalizedPath}/`)
    );
  });
  if (!matches.length) return null;
  matches.sort((left, right) => Date.parse(right['作成日時'] || '') - Date.parse(left['作成日時'] || ''));
  const batchId = String(matches[0]['バッチID'] || '').trim();
  if (!batchId) return null;
  return {
    batchId,
    folderPath: accessoryFolderPathFromRegistry(matches[0]),
    ids: [...new Set(matches
      .filter((row) => row['バッチID'] === batchId)
      .map((row) => row['ジョブID'])
      .filter(Boolean))],
  };
}

async function statusJobIds(req) {
  const folderPath = normalizeFolderPath(queryValue(req.query.folderPath));
  if (folderPath) {
    const matched = matchingFolderBatch(await listRegistryJobs(), folderPath);
    if (!matched?.ids.length) throw new Error(`フォルダの生成結果が見つかりません: ${folderPath}`);
    return { ids: matched.ids, batch: true, batchId: matched.batchId, folderPath: matched.folderPath };
  }
  const batchId = String(queryValue(req.query.batchId) || '').trim();
  if (batchId) {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(batchId)) {
      throw new Error('batchIdの形式が不正です');
    }
    const rows = await listRegistryJobs();
    const ids = [...new Set(rows
      .filter((row) => row['バッチID'] === batchId)
      .map((row) => row['ジョブID'])
      .filter(Boolean))];
    if (!ids.length) throw new Error(`バッチのジョブが見つかりません: ${batchId}`);
    return { ids, batch: true, batchId };
  }
  const single = String(queryValue(req.query.jobId) || '').trim();
  const multiple = String(queryValue(req.query.jobIds) || '').trim();
  const values = multiple ? multiple.split(',') : single ? [single] : [];
  const ids = [...new Set(values.map((value) => value.trim()).filter(Boolean))];
  if (ids.length < 1) {
    throw new Error('batchId、jobId、jobIdsのいずれかは必須です');
  }
  if (ids.some((id) => !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id))) {
    throw new Error('jobIdの形式が不正です');
  }
  return { ids, batch: Boolean(multiple) };
}

function promptPath(engine, templateFile = 'tpl_default.md') {
  const templateId = String(templateFile).replace(/\.md$/, '');
  return `${controlFolder()}/prompts/${engine.toLowerCase()}/${templateId}.json`;
}

async function promptSnapshot(engine, token = null, templateFile = 'tpl_default.md') {
  const defaultContent = await loadPromptTemplate(templateFile);
  const oneDriveToken = token || await getOneDriveToken();
  const stored = await getJson(oneDriveToken, promptPath(engine, templateFile));
  if (
    stored?.value?.content
    && stored.value.sha256 === sha256(stored.value.content)
    && stored.value.contract_version === PROMPT_CONTRACT_VERSION
  ) {
    return stored.value;
  }
  const content = defaultContent;
  const initial = {
    id: stored?.value?.id || `${engine.toLowerCase()}-${templateFile.replace(/\.md$/, '')}`,
    revision: Number(stored?.value?.revision || 0) + 1,
    contract_version: PROMPT_CONTRACT_VERSION,
    sha256: sha256(content),
    content,
  };
  await putJson(oneDriveToken, promptPath(engine, templateFile), initial);
  return initial;
}

async function promptAction(req, res, body) {
  const engine = queryValue(req.query.engine, body.engine) === 'MLX' ? 'MLX' : 'Gemini';
  const templateFile = String(queryValue(req.query.templateFile, body.templateFile) || 'tpl_default.md');
  const token = await getOneDriveToken();
  if (req.method === 'GET') {
    const prompt = await promptSnapshot(engine, token, templateFile);
    return res.status(200).json({ engine, prompt });
  }
  if (req.method === 'PUT') {
    const current = await promptSnapshot(engine, token, templateFile);
    const content = String(body.content || '').trim();
    if (!content) return res.status(400).json({ error: 'プロンプト本文は必須です' });
    const next = {
      ...current,
      revision: Number(current.revision || 0) + 1,
      contract_version: PROMPT_CONTRACT_VERSION,
      sha256: sha256(content),
      content,
      updated_at: new Date().toISOString(),
    };
    await putJson(token, promptPath(engine, templateFile), next);
    return res.status(200).json({ success: true, engine, prompt: next });
  }
  if (req.method === 'DELETE') {
    return res.status(409).json({ error: '使用中の既定プロンプトは削除できません。代替プロンプト機能の追加後に削除できます。' });
  }
  return res.status(405).json({ error: '未対応のプロンプト操作です' });
}

async function preview(req, res, body) {
  const parentId = String(queryValue(req.query.parentId, body.parentId) || '').trim();
  if (!parentId) return res.status(400).json({ error: 'parentIdは必須です' });
  const token = await getOneDriveToken();
  const markdown = await downloadArticle(token, parentId);
  const affiliateText = await downloadTextPath(token, AFFILIATE_FILE_PATH);
  const parentTitle = extractH1(markdown);
  const categories = matchingCategories(markdown, await loadAccessoryMaster());
  const previews = [];
  for (const category of categories) {
    let group;
    let validationError = '';
    try {
      group = parseAffiliateText(affiliateText, category.affiliateSection);
      await loadPromptTemplate(category.templateFile);
    } catch (error) {
      validationError = safePublicError(error);
    }
    previews.push({
      id: category.categoryId,
      name: category.categoryName,
      defaultEnabled: category.defaultEnabled,
      title: buildChildTitle(parentTitle, category.categoryName, category.titleFormat),
      affiliateSection: category.affiliateSection,
      templateFile: category.templateFile,
      productCount: group?.products.length || 0,
      products: group?.products.map((product) => ({ title: product.title, urls: product.urls })) || [],
      available: !validationError,
      validationError,
    });
  }
  const prompts = await Promise.all(['MLX', 'Gemini'].map(async (engine) => {
    const prompt = await promptSnapshot(engine, token);
    return { engine, id: prompt.id, revision: prompt.revision };
  }));
  return res.status(200).json({
    parent: { id: parentId, title: parentTitle, webUrl: body.parentWebUrl || '' },
    categories: previews,
    prompts,
  });
}

async function dispatchGemini(jobId) {
  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';
  if (!githubToken) throw new Error('GITHUB_TOKENが設定されていません');
  const response = await fetch(`${GITHUB_API}/repos/${repo}/actions/workflows/accessories-gemini.yml/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${githubToken}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: 'main', inputs: { job_id: jobId } }),
  });
  if (response.status !== 204) throw new Error(`Gemini処理の起動失敗: HTTP ${response.status}`);
}

async function createJobs(req, res, body) {
  const engine = body.engine === 'Gemini' ? 'Gemini' : body.engine === 'MLX' ? 'MLX' : '';
  if (!engine) return res.status(400).json({ error: 'engineはMLXまたはGeminiで指定してください' });
  if (engine === 'MLX' && !isMac(req, body)) {
    return res.status(400).json({ error: 'MLXはMacからだけ依頼できます' });
  }
  const requestedParents = Array.isArray(body.parents) && body.parents.length
    ? body.parents
    : [{
        parentId: body.parentId,
        parentWebUrl: body.parentWebUrl,
        parentPath: body.parentPath,
        categoryIds: body.categoryIds,
      }];
  if (!requestedParents.length) return res.status(400).json({ error: '親記事の選択が必要です' });

  const token = await getOneDriveToken();
  const affiliateText = await downloadTextPath(token, AFFILIATE_FILE_PATH);
  const categories = await loadAccessoryMaster();
  const prepared = [];
  const seenPairs = new Set();
  const validatedTemplates = new Set();
  for (const requested of requestedParents) {
    const parentId = String(requested?.parentId || '').trim();
    const categoryIds = [...new Set(Array.isArray(requested?.categoryIds) ? requested.categoryIds.map(String) : [])];
    if (!parentId || !categoryIds.length) {
      return res.status(400).json({ error: '各親記事のparentIdとcategoryIdsは必須です' });
    }
    const markdown = await downloadArticle(token, parentId);
    const parentTitle = extractH1(markdown);
    const available = new Map(matchingCategories(markdown, categories).map((category) => [category.categoryId, category]));
    for (const categoryId of categoryIds) {
      const pairKey = `${parentId}:${categoryId}`;
      if (seenPairs.has(pairKey)) continue;
      seenPairs.add(pairKey);
      const category = available.get(categoryId);
      if (!category) throw new Error(`${parentTitle}に対応しない周辺機器カテゴリです: ${categoryId}`);
      parseAffiliateText(affiliateText, category.affiliateSection);
      if (!validatedTemplates.has(category.templateFile)) {
        await loadPromptTemplate(category.templateFile);
        validatedTemplates.add(category.templateFile);
      }
      prepared.push({
        parentId,
        parentTitle,
        parentWebUrl: String(requested.parentWebUrl || ''),
        parentPath: String(requested.parentPath || ''),
        category,
      });
    }
  }
  if (!prepared.length) return res.status(400).json({ error: '周辺機器カテゴリが選択されていません' });

  const batchId = randomUUID();
  const batchCreatedAt = new Date().toISOString();
  const created = [];
  const promptCache = new Map();
  for (const item of prepared) {
    const { category } = item;
    if (!promptCache.has(category.templateFile)) {
      promptCache.set(category.templateFile, await promptSnapshot(engine, token, category.templateFile));
    }
    const prompt = promptCache.get(category.templateFile);
    const job = createJob({
      batchId,
      engine,
      parent: {
        id: item.parentId,
        title: item.parentTitle,
        web_url: item.parentWebUrl,
        original_path: item.parentPath,
      },
      category,
      promptSnapshot: prompt,
      articleTitle: buildChildTitle(item.parentTitle, category.categoryName, category.titleFormat),
      createdAt: batchCreatedAt,
    });
    await putJob(token, job);
    try {
      await appendRegistryJob(job);
      job.state = 'pending';
      await putJob(token, job);
    } catch (error) {
      job.state = 'registration_failed';
      job.result.error_summary = safePublicError(error);
      await putJob(token, job);
      created.push({
        jobId: job.job_id,
        parentId: job.parent.id,
        parentTitle: job.parent.title,
        title: job.article_title,
        category: job.category.name,
        state: job.state,
        createdAt: job.created_at,
        error: job.result.error_summary,
      });
      continue;
    }
    if (engine === 'Gemini') {
      try {
        await dispatchGemini(job.job_id);
      } catch (error) {
        job.state = 'failed';
        job.registry.status = '失敗';
        job.result.error_summary = safePublicError(error);
        await putJob(token, job);
        try {
          await updateRegistryJob({
            jobId: job.job_id,
            status: '失敗',
            errorSummary: job.result.error_summary,
          });
        } catch (sheetError) {
          job.registry.sync = 'pending';
          job.registry.last_error = safePublicError(sheetError);
          await putJob(token, job);
        }
      }
    }
    created.push({
      jobId: job.job_id,
      parentId: job.parent.id,
      parentTitle: job.parent.title,
      title: job.article_title,
      category: job.category.name,
      state: job.state,
      createdAt: job.created_at,
      error: job.result.error_summary,
    });
  }
  const heartbeat = engine === 'MLX' ? await getWorkerHeartbeat(token) : null;
  const worker = engine === 'MLX' ? workerSnapshot(heartbeat) : null;
  return res.status(201).json({
    success: true,
    hasFailures: created.some((job) => ['failed', 'registration_failed'].includes(job.state)),
    batchId,
    jobs: created,
    automatic: engine === 'Gemini' || heartbeatActive(heartbeat),
    worker,
    message: created.some((job) => ['failed', 'registration_failed'].includes(job.state))
      ? '一部のジョブ登録または起動に失敗しました。生成進捗を確認してください。'
      : engine === 'MLX' && !heartbeatActive(heartbeat)
      ? '自動処理は待機中です。Macで手動復旧できます。'
      : '記事化ジョブを登録しました。',
  });
}

async function status(req, res) {
  let request;
  try {
    request = await statusJobIds(req);
  } catch (error) {
    return res.status(400).json({ error: safePublicError(error) });
  }
  const token = await getOneDriveToken();
  const records = await Promise.all(request.ids.map((jobId) => getJob(token, jobId)));
  const missingIndex = records.findIndex((record) => !record);
  if (missingIndex >= 0) {
    return res.status(404).json({ error: `ジョブが見つかりません: ${request.ids[missingIndex]}` });
  }
  const jobs = records.map((record) => {
    const job = record.value;
    return {
      jobId: job.job_id,
      batchId: job.batch_id,
      title: job.article_title,
      state: job.state,
      engine: job.engine,
      category: job.category?.name || '',
      parentId: job.parent?.id || '',
      parentTitle: job.parent?.title || '',
      createdAt: job.created_at,
      completedAt: job.completed_at,
      articleId: job.result?.article_id || '',
      articleUrl: job.result?.article_url || '',
      error: job.result?.error_summary || '',
      warning: job.result?.warning_summary || '',
      generationErrors: Array.isArray(job.result?.generation_errors) ? job.result.generation_errors : [],
      outputMode: job.result?.output_mode || 'generated',
      registrySync: job.registry?.sync || '',
    };
  });
  const heartbeat = jobs.some((job) => job.engine === 'MLX') ? await getWorkerHeartbeat(token) : null;
  const response = {
    batchId: request.batchId || jobs[0]?.batchId || '',
    folderPath: request.folderPath || '',
    jobs,
    worker: heartbeat ? workerSnapshot(heartbeat) : null,
    checkedAt: new Date().toISOString(),
  };
  return res.status(200).json(request.batch ? response : { ...jobs[0], ...response });
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(200).end();
  const body = jsonBody(req);
  const action = String(queryValue(req.query.action, body.action) || 'preview');
  try {
    if (req.method === 'GET' && action === 'preview') return await preview(req, res, body);
    if (req.method === 'GET' && action === 'status') return await status(req, res);
    if (action === 'prompt') return await promptAction(req, res, body);
    if (req.method === 'POST' && action === 'create') return await createJobs(req, res, body);
    return res.status(405).json({ error: '未対応の操作です' });
  } catch (error) {
    console.error('accessories error:', error);
    return res.status(500).json({ error: safePublicError(error) });
  }
}
