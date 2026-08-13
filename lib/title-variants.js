import { randomUUID } from 'node:crypto';

import { sha256 } from './accessories-core.js';


export function normalizeTitleVariantKeywords(input) {
  const source = String(input ?? '').normalize('NFKC').replace(/\r\n?/g, '\n');
  const values = [];
  const seen = new Set();
  for (const row of source.split('\n')) {
    const markdownLabels = row.replace(/\[([^\]\n]+)\]\(https?:\/\/[^)\s]+\)/gi, '$1');
    for (const rawCell of markdownLabels.split('\t')) {
      let value = rawCell
        .replace(/https?:\/\/[^\s)\]]+/gi, ' ')
        .replace(/[\u200B-\u200D\uFEFF]/g, '')
        .replace(/^\s*(?:[-*•・●○■□▪▶▼+]+\s*)+/, '')
        .replace(/(?:\s*[+]+\s*)+$/g, '')
        .replace(/^['"`「『【\[]+|['"`」』】\]]+$/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      if (!value || /^[+\-–—]+$/.test(value) || /^www\./i.test(value)) continue;
      value = value.replace(/[\s:：|│。．]+$/g, '').trim();
      if (!value || value.length > 120) continue;
      const key = value.toLocaleLowerCase('ja-JP');
      if (seen.has(key)) continue;
      seen.add(key);
      values.push(value);
    }
  }
  return values;
}


export function titleVariantArticleTitle(keyword) {
  const value = String(keyword || '').trim();
  return value.endsWith('まとめ') ? value : `${value}まとめ`;
}


export function titleVariantFilename(keyword) {
  const title = titleVariantArticleTitle(keyword)
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[ .]+$/g, '');
  if (!title) throw new Error('記事ファイル名を作成できません');
  return `${[...title].slice(0, 150).join('').replace(/[ .]+$/g, '')}.md`;
}


export function createTitleVariantJob({ batchId, parent, keyword, promptSnapshot, maxGenerationAttempts, createdAt = '' }) {
  const articleTitle = titleVariantArticleTitle(keyword);
  const attempts = Number.parseInt(maxGenerationAttempts, 10);
  if (![1, 2, 3].includes(attempts)) throw new Error('MLXの記事作成・修正回数は1回から3回で指定してください');
  const values = { job_type: 'title_variant', target_keyword: keyword, target_title: articleTitle };
  return {
    schema_version: 1,
    job_type: 'title_variant',
    job_id: randomUUID(),
    batch_id: batchId,
    created_at: createdAt || new Date().toISOString(),
    completed_at: '',
    state: 'registration_pending',
    attempt_count: 0,
    engine: 'MLX',
    article_title: articleTitle,
    parent,
    category: {
      id: 'title_variant',
      name: 'タイトル変更',
      affiliate_section: 'none',
      template_file: 'tpl_title_variant.md',
      title_format: '',
    },
    target: {
      keyword,
      title: articleTitle,
      filename: titleVariantFilename(keyword),
    },
    generation_options: { max_attempts: attempts },
    master_snapshot: {
      spreadsheet_id: '1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94',
      sheet_name: '周辺機器DB_LLM',
      row_number: 0,
      values,
      sha256: sha256(JSON.stringify(values)),
    },
    prompt_snapshot: promptSnapshot,
    registry: {
      spreadsheet_id: '1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94',
      sheet_name: '周辺機器DB_LLM',
      status: '記事化',
      sync: 'pending',
    },
    lease: { owner: '', expires_at: '', etag: '' },
    result: { article_id: '', article_url: '', error_summary: '' },
  };
}
