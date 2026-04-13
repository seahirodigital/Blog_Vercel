/**
 * Vercel Serverless Function: note下書き投稿トリガー
 *
 * GET  /api/note-draft?fileId=xxx  → GitHub Variable からURLを返す
 * POST /api/note-draft             → GitHub Actions の note-draft ワークフローを起動
 *   Body: { fileId: "..." }  または { fileIds: ["...", "..."] }（複数一括）
 */

import { createHash } from 'crypto';

const GITHUB_API = 'https://api.github.com';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  // ── GET: 下書き保存済みURLを返す ──────────────────────
  if (req.method === 'GET') {
    const fileId = req.query?.fileId;
    if (!fileId) return res.status(400).json({ error: 'fileId は必須です' });

    const hash = createHash('md5').update(fileId).digest('hex').slice(0, 8).toUpperCase();
    const varName = `NOTE_DRAFT_URL_${hash}`;

    try {
      const response = await fetch(`${GITHUB_API}/repos/${repo}/actions/variables/${varName}`, {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
        },
      });
      if (response.status === 200) {
        const data = await response.json();
        return res.status(200).json({ url: data.value });
      }
      return res.status(200).json({ url: null });
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  // ── POST: GitHub Actions ワークフローを起動 ──────────
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { fileId, fileIds, noTopImage, no_top_image } = req.body || {};
  const ids = fileIds && Array.isArray(fileIds) ? fileIds : fileId ? [fileId] : [];
  if (ids.length === 0) {
    return res.status(400).json({ error: 'fileId または fileIds は必須です' });
  }
  const skipTopImage = Boolean(noTopImage || no_top_image);

  const url = `${GITHUB_API}/repos/${repo}/actions/workflows/note-draft.yml/dispatches`;
  const ghHeaders = {
    Authorization: `Bearer ${githubToken}`,
    Accept: 'application/vnd.github.v3+json',
    'Content-Type': 'application/json',
  };

  // 複数ファイルを順番にワークフロー起動（並列ではなく連続で起動してrate limitを避ける）
  const results = [];
  for (const id of ids) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: ghHeaders,
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            file_id: id,
            no_top_image: String(skipTopImage),
          },
        }),
      });
      if (response.status === 204) {
        results.push({ fileId: id, success: true });
      } else {
        const errText = await response.text();
        results.push({ fileId: id, success: false, error: errText });
      }
    } catch (error) {
      results.push({ fileId: id, success: false, error: error.message });
    }
    // 連続起動の間に短い待機（500ms）
    if (ids.length > 1) await new Promise(r => setTimeout(r, 500));
  }

  const allSuccess = results.every(r => r.success);
  return res.status(200).json({
    success: allSuccess,
    message: allSuccess
      ? `${results.length}件のnote下書き投稿を開始しました。`
      : `一部失敗: ${results.filter(r => !r.success).map(r => r.fileId).join(', ')}`,
    results,
  });
}
