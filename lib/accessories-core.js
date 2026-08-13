import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

// VercelはNode.js FunctionをCommonJSへ変換するため import.meta を使わず、
// ローカルと /var/task の両方でプロジェクトルートになる実行ディレクトリを使う。
export const REPO_ROOT = process.cwd();

export const MASTER_HEADERS = [
  '親製品検出キーワード',
  '周辺機器カテゴリID',
  '周辺機器カテゴリ名',
  'タイトル形式',
  'アフィリエイトセクション',
  'デフォルト有効',
  '使用テンプレートファイル',
];

export const REGISTRY_HEADERS = [
  '作成日時',
  '完了日時',
  '記事タイトル',
  '進捗',
  '記事URLリンク',
  '大元記事タイトル',
  '大元記事リンク',
  '対象周辺機器',
  '生成エンジン',
  'エラー概要',
  'ジョブID',
  'バッチID',
];

export function sha256(value) {
  return createHash('sha256').update(String(value ?? ''), 'utf8').digest('hex');
}

export function normalizeText(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase('ja-JP');
}

function parseBoolean(value, rowNumber) {
  const normalized = normalizeText(value).trim();
  if (['true', '1', 'yes', 'y', 'はい', '有効'].includes(normalized)) return true;
  if (['false', '0', 'no', 'n', 'いいえ', '無効'].includes(normalized)) return false;
  throw new Error(`周辺機器DB ${rowNumber}行目のデフォルト有効が不正です`);
}

export function parseMasterValues(values) {
  if (!Array.isArray(values) || values.length === 0) throw new Error('周辺機器DBが空です');
  const headers = values[0].map((value) => String(value ?? '').trim());
  const missing = MASTER_HEADERS.filter((header) => !headers.includes(header));
  if (missing.length) throw new Error(`周辺機器DBの必須列が不足しています: ${missing.join(', ')}`);
  const seen = new Set();
  const categories = [];

  for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
    const rowNumber = rowIndex + 1;
    const raw = Object.fromEntries(headers.map((header, index) => [header, String(values[rowIndex]?.[index] ?? '').trim()]));
    if (!Object.values(raw).some(Boolean)) continue;
    const categoryId = raw['周辺機器カテゴリID'];
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(categoryId)) throw new Error(`周辺機器DB ${rowNumber}行目のカテゴリIDが不正です`);
    if (seen.has(categoryId)) throw new Error(`周辺機器DBのカテゴリIDが重複しています: ${categoryId}`);
    seen.add(categoryId);
    const keywords = raw['親製品検出キーワード'].split(/[,\n、。|]/).map((item) => item.trim()).filter(Boolean);
    if (!keywords.length) throw new Error(`周辺機器DB ${rowNumber}行目の検出キーワードが空です`);
    for (const header of MASTER_HEADERS.slice(2, 5).concat(MASTER_HEADERS[6])) {
      if (!raw[header]) throw new Error(`周辺機器DB ${rowNumber}行目の${header}が空です`);
    }
    const priorityValue = raw['表示優先度'] || '999';
    const priority = Number.parseInt(priorityValue, 10);
    if (!Number.isFinite(priority)) throw new Error(`周辺機器DB ${rowNumber}行目の表示優先度が不正です`);
    const canonical = JSON.stringify(Object.fromEntries(Object.entries(raw).sort(([a], [b]) => (
      a < b ? -1 : a > b ? 1 : 0
    ))));
    // 既存シートの旧表記を安全に読み替える移行互換。
    // rawとSHA-256はシート原文のまま保持し、ユーザーが別名称へ編集した場合は上書きしない。
    const legacyAdapter = categoryId === 'adapter'
      && raw['周辺機器カテゴリ名'] === 'アダプター'
      && raw['タイトル形式'] === '製品名 アダプターおすすめ：';
    categories.push({
      rowNumber,
      keywords,
      categoryId,
      categoryName: legacyAdapter ? '充電器' : raw['周辺機器カテゴリ名'],
      titleFormat: legacyAdapter ? '製品名 充電器おすすめ：' : raw['タイトル形式'],
      affiliateSection: raw['アフィリエイトセクション'],
      defaultEnabled: parseBoolean(raw['デフォルト有効'], rowNumber),
      templateFile: raw['使用テンプレートファイル'],
      displayPriority: priority,
      raw,
      sha256: sha256(canonical),
    });
  }
  return categories.sort((a, b) => a.displayPriority - b.displayPriority || a.rowNumber - b.rowNumber);
}

export function matchingCategories(articleText, categories) {
  const normalized = normalizeText(articleText);
  return categories.filter((category) => category.keywords.some((keyword) => normalized.includes(normalizeText(keyword))));
}

export function extractH1(markdown) {
  const matches = [...String(markdown ?? '').matchAll(/^# (.+)$/gm)];
  if (matches.length !== 1) throw new Error(`H1は1件だけ必要です: ${matches.length}件`);
  if (String(markdown).slice(0, matches[0].index).trim()) throw new Error('記事の最初の空白でない行がH1ではありません');
  return matches[0][1].trim();
}

export function deriveProductName(title) {
  const left = String(title ?? '').split(/[:：│|]/, 1)[0].trim();
  const product = left.split(/\s*(?:レビュー|比較|違い|まとめ)/, 1)[0]
    .replace(/[\s。．.!！?？:：│|]+$/, '')
    .trim();
  return product || String(title ?? '').trim();
}

export function buildChildTitle(parentTitle, categoryName, titleFormat = '') {
  const product = deriveProductName(parentTitle);
  const configured = String(titleFormat || '')
    .replaceAll('{製品名}', product)
    .replace(/^製品名/, product)
    .replace(/[:：│|\s]+$/, '')
    .trim();
  const prefix = configured || `${product} ${categoryName}おすすめ`;
  return `${prefix}まとめ`;
}

export function parseAffiliateText(text, sectionName) {
  const normalized = String(text ?? '').replace(/\r\n?/g, '\n');
  const marker = /^===([A-Za-z0-9_-]+)===$/gm;
  const matches = [...normalized.matchAll(marker)];
  const index = matches.findIndex((match) => match[1] === sectionName);
  if (index < 0) throw new Error(`アフィリエイトセクションがありません: ${sectionName}`);
  const start = matches[index].index + matches[index][0].length;
  const end = matches[index + 1]?.index ?? normalized.length;
  const rawText = normalized.slice(start, end).replace(/^\n+|\n+$/g, '');
  const starts = [...rawText.matchAll(/^▼/gm)].map((match) => match.index);
  if (!starts.length) throw new Error(`商品ブロックがありません: ${sectionName}`);
  const sectionIntro = rawText.slice(0, starts[0]).trim();
  const products = starts.map((blockStart, productIndex) => {
    const blockEnd = starts[productIndex + 1] ?? rawText.length;
    const productText = rawText.slice(blockStart, blockEnd).trim();
    const title = productText.split('\n')[0].replace(/^▼/, '').trim();
    const urls = productText.match(/https?:\/\/[^\s)\]]+/g) ?? [];
    if (!title) throw new Error(`「▼」直後の見出しがありません: ${sectionName} #${productIndex + 1}`);
    return { index: productIndex + 1, title, text: productText, urls };
  });
  return { name: sectionName, rawText, sectionIntro, products };
}

export async function loadPromptTemplate(templateFile) {
  const filename = String(templateFile || '').trim();
  if (!/^[A-Za-z0-9_-]+\.md$/.test(filename) || path.basename(filename) !== filename) {
    throw new Error(`使用テンプレートファイルが不正です: ${filename}`);
  }
  try {
    return await readFile(path.join(REPO_ROOT, 'accessories/templates', filename), 'utf8');
  } catch {
    throw new Error(`使用テンプレートファイルが存在しません: ${filename}`);
  }
}

const AFFILIATE_SECTION_LABELS = {
  battery: 'バッテリー',
  adapter: '充電器',
  cable: 'ケーブル',
  case: 'ケース',
  film: '保護フィルム',
  keyboard: 'キーボード',
  mouse: 'マウス',
  stand: 'スタンド',
  hub: 'ハブ',
  earphone: 'イヤホン',
  headphone: 'ヘッドホン',
  speaker: 'スピーカー',
  storage: 'ストレージ',
  monitor: 'モニター',
};

export function affiliateSectionLabel(sectionId) {
  const id = String(sectionId || '').trim();
  const memo = id.match(/^MEMO(\d+)$/i);
  if (memo) return `メモ${memo[1]}`;
  return AFFILIATE_SECTION_LABELS[id.toLowerCase()] || id;
}

export function parseAffiliateSections(content) {
  const normalized = String(content || '').replace(/\r\n?/g, '\n');
  const matches = [...normalized.matchAll(/^===([A-Za-z0-9_-]+)===$/gm)];
  if (!matches.length) return [{ id: 'MEMO1', label: 'メモ1', content: '' }];
  if (normalized.slice(0, matches[0].index).trim()) {
    throw new Error('最初のセクションより前に文章があります');
  }
  const seen = new Set();
  return matches.map((match, index) => {
    const id = match[1];
    if (seen.has(id)) throw new Error(`アフィリエイトセクションが重複しています: ${id}`);
    seen.add(id);
    const start = match.index + match[0].length;
    const end = matches[index + 1]?.index ?? normalized.length;
    return {
      id,
      label: affiliateSectionLabel(id),
      content: normalized.slice(start, end).replace(/^\n+|\n+$/g, ''),
    };
  });
}

export function serializeAffiliateSections(sections) {
  if (!Array.isArray(sections) || !sections.length) throw new Error('アフィリエイトセクションが必要です');
  const seen = new Set();
  const chunks = sections.map((section) => {
    const id = String(section?.id || '').trim();
    if (!/^[A-Za-z0-9_-]+$/.test(id)) throw new Error(`セクション名が不正です: ${id}`);
    if (seen.has(id)) throw new Error(`セクション名が重複しています: ${id}`);
    seen.add(id);
    const body = String(section?.content || '').replace(/\r\n?/g, '\n').trim();
    if (/^===[A-Za-z0-9_-]+===$/m.test(body)) {
      throw new Error(`本文内にセクション見出しは記載できません: ${id}`);
    }
    return `===${id}===\n${body}`;
  });
  return `${chunks.join('\n\n')}\n`;
}

export function createJob({ batchId, engine, parent, category, promptSnapshot, articleTitle, maxGenerationAttempts, createdAt = '' }) {
  const jobCreatedAt = createdAt || new Date().toISOString();
  const requestedAttempts = Number.parseInt(maxGenerationAttempts, 10);
  const normalizedAttempts = [1, 2, 3].includes(requestedAttempts)
    ? requestedAttempts
    : engine === 'MLX' ? 1 : 2;
  return {
    schema_version: 2,
    job_id: randomUUID(),
    batch_id: batchId,
    created_at: jobCreatedAt,
    completed_at: '',
    state: 'registration_pending',
    attempt_count: 0,
    engine,
    article_title: articleTitle,
    parent,
    category: {
      id: category.categoryId,
      name: category.categoryName,
      affiliate_section: category.affiliateSection,
      template_file: category.templateFile,
      title_format: category.titleFormat,
    },
    generation_options: { max_attempts: normalizedAttempts },
    master_snapshot: {
      spreadsheet_id: '1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94',
      sheet_name: '周辺機器DB',
      row_number: category.rowNumber,
      sha256: category.sha256,
      values: category.raw,
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

export function safePublicError(error) {
  const message = error instanceof Error ? error.message : String(error ?? '不明なエラー');
  return message
    .replace(/(?:AIza|ya29\.)[A-Za-z0-9._-]+/g, '[秘密情報]')
    .replace(/-----BEGIN[\s\S]*?-----END[^-]+-----/g, '[秘密情報]')
    .slice(0, 500);
}
