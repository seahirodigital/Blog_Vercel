/**
 * OGPメタデータ取得API
 * URLを受け取り、OGP情報（title, description, image, domain）を返す
 * CORSを回避するためサーバーサイドで取得する
 * amzn.to短縮URLやアフィリエイトURLのリダイレクトにも対応
 */
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'url required' });

  try {
    // ブラウザに近いヘッダーでリクエスト（Bot検出を回避）
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
      },
      redirect: 'follow',
      signal: AbortSignal.timeout(10000),
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
        // ダブルクォートの代わりにシングルクォートやなし
        new RegExp(`<meta[^>]+property=og:${prop}[^>]+content=["']([^"']+)["']`, 'i'),
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

    const title = getMeta('title') || html.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1]?.trim() || '';
    const description = getMeta('description');
    const image = getMeta('image');
    let domain;
    try { domain = new URL(finalUrl).hostname; } catch { domain = new URL(url).hostname; }

    res.status(200).json({ title, description, image, domain, finalUrl });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
