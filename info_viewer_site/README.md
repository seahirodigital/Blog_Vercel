# Info Viewer 静的サイト

このサイトは、`C:\Users\mahha\OneDrive\開発\Blog_Vercel\scripts\info_viewer\export_static_site.py` がOneDrive上の正本Markdownをそのまま `C:\Users\mahha\OneDrive\開発\Blog_Vercel\info_viewer_site\content\articles\` へ出力し、Hugoで静的HTMLへ変換する構成です。

閲覧時にVercel API、OneDrive、React、Tailwind、Babel、外部フォントCDNを呼びません。本文検索用の `C:\Users\mahha\OneDrive\開発\Blog_Vercel\info_viewer_site\static\search.json` だけは、検索を開いた時点でCloudflare Pagesから読み込みます。

## Cloudflare Pages設定

Cloudflare DashboardでGitHubリポジトリ `seahirodigital/Blog_Vercel` を接続し、次を設定します。

| 項目 | 値 |
| --- | --- |
| Production branch | `main` |
| Root directory | `info_viewer_site` |
| Build command | `hugo --gc --minify` |
| Build output directory | `public` |
| 環境変数 `HUGO_VERSION` | `0.165.0` |

Cloudflare PagesのURLは、プロジェクト作成時に払い出される `https://<Cloudflare Pagesプロジェクト名>.pages.dev/` です。独自ドメインを使う場合も、Hugoのリンクは相対URLのため追加変更は不要です。

## 更新フロー

1. `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-queue.yml` がYouTube処理、同一MarkdownのOneDrive保存、Notion保存を完了する。
2. 同じworkflowが `C:\Users\mahha\OneDrive\開発\Blog_Vercel\scripts\info_viewer\export_static_site.py` を実行する。
3. 静的Markdown、記事インデックス、検索インデックスだけをGitHubへコミットする。
4. Cloudflare PagesのGit連携が静的HTMLを再生成して公開する。

「即時URL」の送信は `https://blog-vercel-dun.vercel.app/api/trigger-info-viewer` を使用します。Vercel環境変数 `INFO_VIEWER_ADMIN_SECRET` の値を送信時だけ入力してください。閲覧時にVercelへ接続することはありません。

## ローカル確認

PowerShellで次を実行します。

```powershell
Set-Location -LiteralPath 'C:\Users\mahha\OneDrive\開発\Blog_Vercel\info_viewer_site'
hugo --gc --minify
hugo server --bind 127.0.0.1 --port 1313
```

生成先は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\info_viewer_site\public\` です。この生成物はGit管理しません。
