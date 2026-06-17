# Blog Vercel 白画面調査レポート

保存日時: 2026-06-17
保存先: `C:\Users\mahha\OneDrive\開発\Blog_Vercel\docs\blog-vercel-white-screen-investigation-2026-06-17.md`

## 退避点
- 現在の退避ブランチ: `codex/pre-fix-20260617`
- 現在のHEAD: `e354e78b727ed2a116a7d25bbff2c3c00f1695d1`
- GitHub main 参照時点: `8806eda89bb11cbd15916db881d319845c9f52b4`
- 本番相当の退避ブランチ: `codex/pre-fix-origin-main-20260617`

## 症状
- Vercel 上で画面が真っ白になる。
- ログに `GitHub Actions Secret 同期エラー: Cannot find module '/var/task/node_modules/libsodium-wrappers/dist/modules-esm/libsodium.mjs' imported from /var/task/node_modules/libsodium-wrappers/dist/modules-esm/libsodium-wrappers.mjs` が出る。

## 調査結果
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\lib\onedrive-token-sync.js` の `loadSodium()` は `import('libsodium-wrappers')` を使っている。
- この共通関数は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\api\articles.js`、`C:\Users\mahha\OneDrive\開発\Blog_Vercel\api\info-viewer.js`、`C:\Users\mahha\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` などから呼ばれる。
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\package-lock.json` は存在しないため、Vercel 側の再インストールで依存解決が揺れる。
- `libsodium-wrappers@0.8.4` の ESM は `libsodium` へ依存するが、Vercel 実行環境ではその解決が崩れている。

## 結論
- 昨日の UI 差分そのものより、`libsodium-wrappers` の ESM 読み込みが Vercel 実行時に壊れている可能性が高い。
- 白画面は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\public\index.html` の初期 `fetch('/api/articles')` が失敗した時に起きうる。

## すぐ戻す方法
1. `git switch codex/pre-fix-20260617`
2. もしくは `git reset --hard e354e78b727ed2a116a7d25bbff2c3c00f1695d1`
3. 本番相当へ戻す場合は `git switch codex/pre-fix-origin-main-20260617`

## 次の対策方針
- 最小修正で `C:\Users\mahha\OneDrive\開発\Blog_Vercel\lib\onedrive-token-sync.js` の sodium 読み込みを ESM import から CJS 読み込みに切り替える。
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\package.json` の `libsodium` と `libsodium-wrappers` を exact version に固定し、Vercel 再デプロイ時の依存解決の揺れを止める。
- 既存の機能は増やさない。
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\state_store.py` の manual priority 判定は別件の軽微なロジック不備として後で確認する。

## 実装した対策
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\lib\onedrive-token-sync.js`
  - `import('libsodium-wrappers')` をやめ、静的 import で `libsodium-wrappers` を読む形へ変更。
  - Vercel が ESM 側の `dist/modules-esm` を解決して失敗する経路を避けつつ、Vercel のファイルトレーサーに依存を確実に拾わせる。
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\package.json`
  - `libsodium-wrappers` を `0.7.15` に固定。
  - `libsodium` を `0.7.15` として明示追加。

## 追加確認
- コミット `e070956dedc85045cc56b4baa0ff698dd65a020c` を push 後、GitHub main 反映は確認できた。
- その直後の Vercel 本番 `/api/articles` と `/api/info-viewer` は HTTP 500 `FUNCTION_INVOCATION_FAILED` になった。
- `createRequire(import.meta.url)` 経由の `require('libsodium-wrappers')` が Vercel の関数ファイルトレースに拾われない可能性があるため、静的 import へ切り替えた。
