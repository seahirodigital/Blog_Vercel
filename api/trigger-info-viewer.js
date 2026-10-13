import { timingSafeEqual } from 'node:crypto';

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left || ''));
  const rightBuffer = Buffer.from(String(right || ''));
  return Boolean(leftBuffer.length && leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer));
}

function validYoutubeUrl(value) {
  try {
    const parsed = new URL(String(value || '').trim());
    const host = parsed.hostname.toLowerCase();
    return parsed.protocol === 'https:' && (host === 'youtu.be' || host.endsWith('.youtu.be') || host === 'youtube.com' || host.endsWith('.youtube.com'));
  } catch {
    return false;
  }
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-info-viewer-admin-secret');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ success: false, error: 'Method not allowed' });

  const expectedSecret = process.env.INFO_VIEWER_ADMIN_SECRET || '';
  const suppliedSecret = req.headers['x-info-viewer-admin-secret'] || '';
  if (!expectedSecret) return res.status(500).json({ success: false, error: 'INFO_VIEWER_ADMIN_SECRET が設定されていません' });
  if (!safeEqual(suppliedSecret, expectedSecret)) return res.status(401).json({ success: false, error: 'Unauthorized' });

  const videoUrl = String(req.body?.video_url || '').trim();
  if (!validYoutubeUrl(videoUrl)) {
    return res.status(400).json({ success: false, error: 'https の YouTube動画URLを指定してください' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';
  if (!githubToken) return res.status(500).json({ success: false, error: 'GITHUB_TOKEN が設定されていません' });

  try {
    const response = await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/info-viewer-queue.yml/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ref: 'main', inputs: { video_url: videoUrl } }),
      }
    );

    if (response.status === 204) {
      return res.status(202).json({
        success: true,
        message: 'info_viewer の手動URL処理を起動しました。',
      });
    }

    return res.status(response.status).json({
      success: false,
      error: `GitHub Actions の起動に失敗しました: ${(await response.text()).slice(0, 1000)}`,
    });
  } catch (error) {
    console.error('trigger-info-viewer error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}
