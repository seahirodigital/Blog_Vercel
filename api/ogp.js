/**
 * OGPメタデータ取得API
 * URLを受け取り、OGP情報（title, description, image, domain）を返す
 * CORSを回避するためサーバーサイドで取得する
 * amzn.to短縮URLやアフィリエイトURLのリダイレクト・Amazon商品ページに対応
 */
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'url required' });

  try {
    // ブラウザに近いヘッダーでリクエスト（Amazon等のBot検出を回避）
    const browserHeaders = {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
      'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
      'Accept-Encoding': 'gzip, deflate, br',
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Referer': 'https://www.google.com/',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'cross-site',
      'Upgrade-Insecure-Requests': '1',
    };
    const response = await fetch(url, {
      headers: browserHeaders,
      redirect: 'follow',
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok) return res.status(502).json({ error: `upstream ${response.status}` });
    const html = await response.text();

    // リダイレクト後の最終URLを使ってdomainを取得
    const finalUrl = response.url || url;

    // OGPプロパティを取得するヘルパー（属性順序不問）
    const getMeta = (prop) => {
      const patterns = [
        new RegExp(`<meta[^>]+property=["']og:${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
        new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:${prop}["']`, 'i'),
        new RegExp(`<meta[^>]+name=["']${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
        new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${prop}["']`, 'i'),
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m) return m[1]
          .replace(/&amp;/g, '&')
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'")
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .trim();
      }
      return '';
    };

    let title = getMeta('title') || html.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1]?.trim() || '';
    let description = getMeta('description');
    let image = getMeta('image');
    let domain;
    try { domain = new URL(finalUrl).hostname; } catch { domain = new URL(url).hostname; }

    // ── Amazon特化抽出 ──────────────────────────────────────
    const isAmazon = /amazon\.(co\.jp|com|co\.uk|de|fr)/.test(domain) || url.includes('amzn.to') || url.includes('amzn.asia');
    if (isAmazon) {
      // 商品タイトル（汎用ページ「Amazon.co.jp」が返ってきた場合は上書き）
      if (!title || title === 'Amazon.co.jp' || title === 'Amazon' || title.startsWith('Amazon.')) {
        const titlePatterns = [
          /<span id="productTitle"[^>]*>\s*([\s\S]+?)\s*<\/span>/i,
          /<h1[^>]*id="title"[^>]*>[\s\S]*?<span[^>]*>([\s\S]+?)<\/span>/i,
          /<title[^>]*>([^|<]+?)\s*[:|]\s*Amazon/i,
        ];
        for (const re of titlePatterns) {
          const m = html.match(re);
          if (m) { title = m[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim(); break; }
        }
      }

      // 商品画像（複数パターン試行）
      if (!image || image.includes('amazon-logo') || image.includes('site-stripe')) {
        const imgPatterns = [
          // JSONデータに埋め込まれた高解像度画像
          /"hiRes"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/,
          /"large"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/,
          /"mainImage"\s*:\s*\{[^}]*"url"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/,
          // imgタグから直接取得
          /id="landingImage"[^>]+src="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
          /id="imgBlkFront"[^>]+src="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
          /id="main-image"[^>]+src="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
          // data-src（遅延読み込み）
          /id="landingImage"[^>]+data-old-hires="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
        ];
        for (const re of imgPatterns) {
          const m = html.match(re);
          if (m) { image = m[1]; break; }
        }
      }

      // 説明文（価格情報など）
      if (!description) {
        const priceMatch = html.match(/id="priceblock_ourprice"[^>]*>([\s\S]+?)<\/span>/i)
                        || html.match(/class="[^"]*price-large[^"]*"[^>]*>([^<]+)</i);
        if (priceMatch) description = priceMatch[1].replace(/<[^>]+>/g, '').trim();
      }

      // Bot検出された場合（タイトル・画像取得失敗）→ クリーンASIN URLで再試行
      const titleIsGeneric = !title || /^Amazon[\.\s]/.test(title) || title === 'Amazon.co.jp' || /robot check/i.test(title);
      if (titleIsGeneric && !image) {
        const asinM = (finalUrl + ' ' + url).match(/\/dp\/([A-Z0-9]{10})/);
        if (asinM) {
          const cleanUrl = `https://www.amazon.co.jp/dp/${asinM[1]}?language=ja_JP&th=1&psc=1`;
          if (cleanUrl !== finalUrl) {
            try {
              const r2 = await fetch(cleanUrl, {
                headers: { ...browserHeaders, 'Referer': 'https://www.amazon.co.jp/' },
                redirect: 'follow',
                signal: AbortSignal.timeout(10000),
              });
              if (r2.ok) {
                const html2 = await r2.text();
                // タイトル再抽出
                const tPats = [
                  /<span id="productTitle"[^>]*>\s*([\s\S]+?)\s*<\/span>/i,
                  /<h1[^>]*id="title"[^>]*>[\s\S]*?<span[^>]*>([\s\S]+?)<\/span>/i,
                  /<title[^>]*>([^|<]+?)\s*[:|]\s*Amazon/i,
                ];
                for (const re of tPats) {
                  const m = html2.match(re);
                  if (m) { title = m[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim(); break; }
                }
                // 画像再抽出
                const iPats = [
                  /"hiRes"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/,
                  /"large"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/,
                  /id="landingImage"[^>]+src="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
                  /id="imgBlkFront"[^>]+src="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
                  /id="landingImage"[^>]+data-old-hires="(https:\/\/m\.media-amazon\.com\/images\/[^"]+)"/i,
                ];
                for (const re of iPats) {
                  const m = html2.match(re);
                  if (m) { image = m[1]; break; }
                }
              }
            } catch {}
          }
        }
      }
    }

    res.status(200).json({ title, description, image, domain, finalUrl });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
