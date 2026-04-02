/**
 * OGPメタデータ取得API
 * URLを受け取り、OGP情報（title, description, image, domain）を返す
 * CORSを回避するためサーバーサイドで取得する
 */
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'url required' });

  try {
    const response = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; OGPBot/1.0)' },
      redirect: 'follow',
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return res.status(502).json({ error: `upstream ${response.status}` });
    const html = await response.text();

    // OGPプロパティを取得するヘルパー
    const getMeta = (prop) => {
      const patterns = [
        new RegExp(`<meta[^>]+property=["']og:${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
        new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:${prop}["']`, 'i'),
        new RegExp(`<meta[^>]+name=["']${prop}["'][^>]+content=["']([^"']+)["']`, 'i'),
        new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${prop}["']`, 'i'),
      ];
      for (const re of patterns) {
        const m = html.match(re);
        if (m) return m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
      }
      return '';
    };

    const title = getMeta('title') || html.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1]?.trim() || '';
    const description = getMeta('description');
    const image = getMeta('image');
    const domain = new URL(url).hostname;

    res.status(200).json({ title, description, image, domain });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
