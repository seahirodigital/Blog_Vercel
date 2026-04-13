/**
 * Vercel Serverless Function: Amazon ASIN 自動取得
 * GET /api/amazon-asin?product_name=Edifier+M90
 *
 * Google Custom Search API で "{商品名} site:amazon.co.jp/dp" を検索し、
 * 結果URLから ASIN を正規表現で抽出する。
 * Amazon を直接スクレイピングしないためクラウドIPのブロックを受けない。
 *
 * 必要な環境変数（Vercel Dashboard で設定）:
 *   GOOGLE_CSE_API_KEY  : Google Custom Search API キー
 *   GOOGLE_CSE_CX       : カスタム検索エンジンID (cx)
 */

const ASSOCIATE_TAG = 'hiroshit-22';
const GOOGLE_CSE_BASE = 'https://www.googleapis.com/customsearch/v1';

/**
 * Google Custom Search API で Amazon 商品を検索し ASIN を返す
 */
async function searchAsinViaGoogle(productName, apiKey, cx) {
  const query = `${productName} site:amazon.co.jp`;
  const url = new URL(GOOGLE_CSE_BASE);
  url.searchParams.set('key', apiKey);
  url.searchParams.set('cx', cx);
  url.searchParams.set('q', query);
  url.searchParams.set('num', '10');
  url.searchParams.set('gl', 'jp');
  url.searchParams.set('hl', 'ja');

  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google CSE HTTPエラー: ${res.status} ${body.slice(0, 200)}`);
  }

  const data = await res.json();
  const items = data.items || [];

  // URLから ASIN を抽出
  const asinRe = /(?:dp|gp\/product)\/([A-Z0-9]{10})/;
  const keywords = productName.replace(/&/g, ' ').split(/\s+/).filter((w) => w.length >= 2);

  for (const item of items) {
    const link = item.link || '';
    const title = (item.title || '').toLowerCase();
    const snippet = (item.snippet || '').toLowerCase();

    const asinMatch = link.match(asinRe);
    if (!asinMatch) continue;

    const asin = asinMatch[1];
    const combined = title + ' ' + snippet;

    // AND条件: すべてのキーワードがタイトルまたはスニペットに含まれるか
    const matched = keywords.every((kw) => combined.includes(kw.toLowerCase()));
    if (matched) {
      return { asin, title: item.title || '' };
    }
  }

  return null;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const productName = req.query?.product_name;
  if (!productName) return res.status(400).json({ error: 'product_name は必須です' });

  const apiKey = process.env.GOOGLE_CSE_API_KEY;
  const cx = process.env.GOOGLE_CSE_CX;
  if (!apiKey || !cx) {
    return res.status(500).json({
      error: 'GOOGLE_CSE_API_KEY または GOOGLE_CSE_CX が未設定です',
      asin: null,
    });
  }

  try {
    const result = await searchAsinViaGoogle(productName, apiKey, cx);
    if (result) {
      const { asin, title } = result;
      const link = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${ASSOCIATE_TAG}`;
      return res.status(200).json({ asin, link, title: title.slice(0, 80) });
    }
    return res.status(200).json({ asin: null, message: 'キーワードに一致する商品が見つかりません' });
  } catch (error) {
    return res.status(500).json({ error: error.message, asin: null });
  }
}
