export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';
  const requestedMaxItems = req.body?.max_items ?? '5';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  try {
    const response = await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/info-viewer-queue.yml/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            mode: req.body?.mode || 'process_queue',
            max_items: String(requestedMaxItems),
            channel_name: req.body?.channel_name || '',
            video_url: req.body?.video_url || '',
            rebuild_manifest_only: String(Boolean(req.body?.rebuild_manifest_only)),
          },
        }),
      }
    );

    if (response.status === 204) {
      return res.status(200).json({
        success: true,
        message: 'info_viewer パイプラインを起動しました。',
      });
    }

    const errorText = await response.text();
    return res.status(response.status).json({
      success: false,
      error: `GitHub API エラー: ${errorText}`,
    });
  } catch (error) {
    console.error('trigger-info-viewer error:', error);
    return res.status(500).json({ error: error.message });
  }
}
