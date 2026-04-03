/**
 * ローカル開発専用: OS のファイルマネージャーで対象ファイルを開く
 * Windows → explorer /select,"path"
 * macOS   → open -R "path"
 * Linux   → xdg-open "folder"
 *
 * 必須環境変数 (`.env.local` に設定):
 *   LOCAL_ARTICLES_BASE=C:\Users\HCY\OneDrive\開発\Blog_Vercel\Blog_Articles
 */
import { spawn } from 'child_process';
import path from 'path';

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const localBase = process.env.LOCAL_ARTICLES_BASE;
  if (!localBase) {
    return res.status(501).json({ error: 'LOCAL_ARTICLES_BASE 未設定（.env.local に追加してください）' });
  }

  const { path: relPath = '', name = '' } = req.query;
  const fullPath = path.join(localBase, relPath, name);

  try {
    const platform = process.platform;
    if (platform === 'win32') {
      // /select でファイルをハイライト表示
      spawn('explorer', [`/select,${fullPath}`], { detached: true, stdio: 'ignore' }).unref();
    } else if (platform === 'darwin') {
      // Finder でファイルを選択状態で開く
      spawn('open', ['-R', fullPath], { detached: true, stdio: 'ignore' }).unref();
    } else {
      // Linux: 親フォルダを開く
      spawn('xdg-open', [path.dirname(fullPath)], { detached: true, stdio: 'ignore' }).unref();
    }
    return res.status(200).json({ success: true, path: fullPath });
  } catch (e) {
    return res.status(500).json({ error: e.message });
  }
}
