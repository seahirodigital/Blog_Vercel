/**
 * Vercel Serverless Function: Amazon ASIN 自動取得
 * GET /api/amazon-asin?product_name=Edifier+M90
 * → Amazon.co.jp を検索し、広告除外・商品名ANDマッチで最初のASINを返す
 *
 * GitHub Actions の IP は Amazon にブロックされるため、
 * Vercel のサーバーサイドから呼び出すことでブロックを回避する。
 */

const AMAZON_SEARCH_BASE = 'https://www.amazon.co.jp/s?k=';
const ASSOCIATE_TAG = 'hiroshit-22';

const FETCH_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/122.0.0.0 Safari/537.36',
  'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
  Accept:
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Encoding': 'gzip, deflate, br',
  Connection: 'keep-alive',
};

/**
 * 検索結果HTMLから広告を除いたASINリストを抽出（最大10件）
 */
function parseOrganicAsins(html) {
  const sponsored = new Set();

  // AdHolder クラスを持つ div 内の ASIN を広告として収集
  for (const m of html.matchAll(/class="[^"]*AdHolder[^"]*"[^>]*data-asin="([A-Z0-9]{10})"/g)) {
    sponsored.add(m[1]);
  }
  // puis-sponsored-label-text を含むブロックの前の ASIN も広告
  for (const m of html.matchAll(/data-asin="([A-Z0-9]{10})"[^>]*>[\s\S]{0,2000}?puis-sponsored-label-text/g)) {
    sponsored.add(m[1]);
  }

  const seen = new Set();
  const organics = [];
  for (const m of html.matchAll(/data-asin="([A-Z0-9]{10})"/g)) {
    const asin = m[1];
    if (seen.has(asin) || sponsored.has(asin)) continue;
    seen.add(asin);
    organics.push(asin);
    if (organics.length >= 10) break;
  }
  return organics;
}

/**
 * 商品ページのタイトルを抽出
 */
function extractProductTitle(html) {
  // id="productTitle" の直後のテキストを取得（1行・300文字以内）
  const m = html.match(/id="productTitle"[^>]*>([^<]{3,300})</);
  if (m) return m[1].replace(/\s+/g, ' ').trim();

  // フォールバック: <title> タグ
  const m2 = html.match(/<title>([^<]{3,200})<\/title>/);
  if (m2) {
    const t = m2[1].split('Amazon.co.jp')[0].replace(/\s+/g, ' ').trim().replace(/[:\-:：]+$/, '');
    return t || m2[1].trim();
  }
  return '';
}

/**
 * キーワード AND マッチ（すべてのキーワードがタイトルに含まれるか）
 */
function keywordMatchesTitle(keywords, title) {
  const lower = title.toLowerCase();
  return keywords.every((kw) => lower.includes(kw.toLowerCase()));
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const productName = req.query?.product_name;
  if (!productName) return res.status(400).json({ error: 'product_name は必須です' });

  // 検索キーワードを生成（& を除いた2文字以上のトークン）
  const keywords = productName.replace(/&/g, ' ').split(/\s+/).filter((w) => w.length >= 2);

  const searchUrl = AMAZON_SEARCH_BASE + encodeURIComponent(productName);

  try {
    // Amazon 検索ページを取得
    const searchRes = await fetch(searchUrl, { headers: FETCH_HEADERS });
    if (!searchRes.ok) {
      return res.status(502).json({
        error: `Amazon検索HTTPエラー: ${searchRes.status}`,
        asin: null,
      });
    }

    const searchHtml = await searchRes.text();
    const organics = parseOrganicAsins(searchHtml);

    if (organics.length === 0) {
      return res.status(200).json({ asin: null, message: 'Organic候補なし' });
    }

    // 各商品ページのタイトルで AND マッチ確認
    for (const asin of organics) {
      const productRes = await fetch(`https://www.amazon.co.jp/dp/${asin}`, {
        headers: FETCH_HEADERS,
      });
      if (!productRes.ok) continue;

      const productHtml = await productRes.text();
      const title = extractProductTitle(productHtml);
      const matched = keywordMatchesTitle(keywords, title);

      if (matched) {
        const link = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${ASSOCIATE_TAG}`;
        return res.status(200).json({ asin, link, title: title.slice(0, 80) });
      }
    }

    return res.status(200).json({ asin: null, message: 'キーワードに一致する商品なし' });
  } catch (error) {
    return res.status(500).json({ error: error.message, asin: null });
  }
}
