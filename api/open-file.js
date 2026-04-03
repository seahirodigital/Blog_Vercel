/**
 * ローカル開発専用: OS のファイルマネージャーで対象ファイルを開く
 * Windows → explorer /select,"path"
 * macOS   → open -R "path"
 * Linux   → xdg-open "folder"
 *
 * 環境変数 LOCAL_ARTICLES_BASE が未設定の場合はデフォルトパスを使用:
 *   C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog
 */
import { spawn } from 'child_process';
import path from 'path';

const DEFAULT_BASE = 'C:\\Users\\HCY\\OneDrive\\Obsidian in Onedrive 202602\\Vercel_Blog';

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const localBase = process.env.LOCAL_ARTICLES_BASE || DEFAULT_BASE;

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
