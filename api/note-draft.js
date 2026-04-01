/**
 * Vercel Serverless Function: note下書き投稿トリガー
 * POST /api/note-draft → GitHub Actions の note-draft ワークフローを起動
 *
 * Body: { fileId: "OneDriveの記事ファイルID" }
 */

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  const { fileId } = req.body || {};
  if (!fileId) {
    return res.status(400).json({ error: 'fileId は必須です' });
  }

  try {
    const url = `https://api.github.com/repos/${repo}/actions/workflows/note-draft.yml/dispatches`;

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
          file_id: fileId,
        },
      }),
    });

    if (response.status === 204) {
      return res.status(200).json({
        success: true,
        message: 'note下書き投稿を開始しました。GitHub Actionsで進捗を確認してください。',
      });
    }

    const errText = await response.text();
    return res.status(response.status).json({
      success: false,
      error: `GitHub API エラー: ${errText}`,
    });
  } catch (error) {
    console.error('Note Draft Trigger Error:', error);
    return res.status(500).json({ error: error.message });
  }
}
