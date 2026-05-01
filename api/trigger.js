/**
 * Vercel Serverless Function: GitHub Actions パイプライントリガー
 * POST /api/trigger → GitHub Actions の blog-pipeline ワークフローを手動起動
 */

export default async function handler(req, res) {
  // CORS対応
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  try {
    const url = `https://api.github.com/repos/${repo}/actions/workflows/blog-pipeline.yml/dispatches`;
    const sourceType = String(req.body?.source_type || req.body?.sourceType || '').trim();
    const rawUrls = req.body?.source_urls || req.body?.sourceUrls || req.body?.urls || req.body?.url || '';
    const sourceUrls = Array.isArray(rawUrls)
      ? rawUrls.map((item) => String(item || '').trim()).filter(Boolean)
      : String(rawUrls || '').split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
    const status = String(req.body?.status || '単品').trim() || '単品';

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          mode: req.body?.mode || 'batch',
          source_type: sourceType,
          source_urls: sourceUrls.length > 0 ? JSON.stringify(sourceUrls) : '',
          status,
        },
      }),
    });

    if (response.status === 204) {
      return res.status(200).json({
        success: true,
        message: 'パイプラインを起動しました。GitHub Actionsでの進捗を確認してください。',
      });
    }

    const errText = await response.text();
    return res.status(response.status).json({
      success: false,
      error: `GitHub API エラー: ${errText}`,
    });
  } catch (error) {
    console.error('Trigger Error:', error);
    return res.status(500).json({ error: error.message });
  }
}
