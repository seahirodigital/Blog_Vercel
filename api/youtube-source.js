/**
 * Vercel Serverless Function: YouTube元動画URL取得
 * GET /api/youtube-source?name=filename.md
 * → GitHub Variables (YT_SOURCE_<hash>) からURLを返す
 */

import { createHash } from 'crypto';

const GITHUB_API = 'https://api.github.com';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const name = req.query?.name;
  if (!name) return res.status(400).json({ error: 'name は必須です' });

  const githubToken = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || 'seahirodigital/Blog_Vercel';

  if (!githubToken) {
    return res.status(500).json({ error: 'GITHUB_TOKEN が設定されていません' });
  }

  const hash = createHash('md5').update(name).digest('hex').slice(0, 8).toUpperCase();
  const varName = `YT_SOURCE_${hash}`;

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
