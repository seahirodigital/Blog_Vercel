# techreference_Xpost

## 1. 文書の目的
本書は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\Xpost_Blog` の実装中に得た技術メモ、成功、失敗、試行中の判断を蓄積するための記録である。

仕様の正本は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\Xpost_Blog\仕様書.md` とし、本書は裏側の判断理由を残す。

## 2. 2026-04-13 実装着手メモ
### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\runner.py` の queue 設計は Xpost にも転用しやすく、`state -> processable -> deferred` の流れをそのまま使える見込みが高い。
- OneDrive CRUD は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\articles.js` を保存先差し替えで流用できる。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer\仕様書.md` の Gemini tech 運用ルールを参照することで、Xpost でも `GEMINI_TOKEN_tech` 専用運用に揃えやすい。

### 修正した認識
- 将来差し替え先として最初に口頭で `Antigravity` と書いてしまったが、これは誤り。
- 正しくは `Apify` を差し替え先候補として扱う。
- 今後の文書と実装では `SocialData -> Apify` の順で表記を統一する。

### 試行中
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog\index.html` は本編の完全コピーをそのまま保守するより、主要操作だけ残した専用 UI を組む方が安全かを比較中。
- phase 1 では「一覧 / 元投稿 / エディタ / プレビュー / pipeline 起動」の最短導線を優先する。

## 3. 実装方針メモ
### queue
- Discord 取得は `C:\Users\HCY\OneDrive\Vercel_Blog\X投稿\state\xpost_pipeline_state.json` に cursor と post 状態を保存する。
- 30分巡回時に新規 URL を `pending` 化する。
- quota 時は `deferred` と `nextRetryAt` を付けて次回 run に回す。

### 取得層
- phase 1 は `SocialData API` を使う。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\socialdata_fetcher.py` は X URL -> tweet/article JSON -> Markdown ソースへの変換だけに責務を絞る。
- 将来 `Apify` へ切り替えるときは、この取得層の差し替えで済むようにする。

### Gemini
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer\仕様書.md` の `12.2 Gemini キー分離と quota 時の挙動` を参照。
- 基本は `GEMINI_TOKEN_tech` を使う。
- ただし検証を止めないため、`GEMINI_TOKEN_tech` の quota 到達時だけ `GEMINI_TOKEN_INVESTSUB` へ fallback する。
- 本編の `GEMINI_API_KEY` や `GEMINI_TOKEN_SUB3` には逃がさない。

## 4. 注意点
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\Xpost_Blog\Discord_connect\reference\xpost_api_reference.md` には機密情報が混ざる可能性があるため、記事やログへ転記しない。
- OneDrive 配下では `.pyc` の扱いが不安定なことがあるため、構文確認は AST parse を使う。

## 5. 2026-04-13 仕上げメモ
### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog-articles.js` の記事一覧は `*_ブログ_*.md` だけを返すようにした。これで `C:\Users\HCY\OneDrive\Vercel_Blog\X投稿` 配下の元投稿ソース Markdown が一覧に混ざらない。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog\index.html` は frontmatter を保持しつつ本文だけ編集する方式にした。保存時に YAML を壊しにくい。

### 判断
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\Xpost_Blog\仕様書.md` の `GEMINI_TOKEN_INVESTSUB` 記述は、当初いったん採用しない方針に寄せていた。
- その後、検証中に pipeline 全体が止まる不都合を避けるため、最終的に `GEMINI_TOKEN_tech -> GEMINI_TOKEN_INVESTSUB` の順で fallback する実装へ修正した。
- それでも fallback は 1 段だけに限定し、本編の Gemini キー群には広げない。

### 気づき
- PowerShell の表示だけで文字化けして見える箇所があったが、`python -X utf8` で実ファイルを確認すると UTF-8 本体は正常だった。Windows では表示と実体を分けて確認する方が安全。
- GitHub Actions で fallback を有効にするには、コード変更だけでなく `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\xpost-blog-queue.yml` に `GEMINI_TOKEN_INVESTSUB` の受け渡しも必要だった。
- `xpost-blog-preview` branch の Vercel preview では Hobby 上限の「Serverless Functions 12 本」に引っかかった。
- 検証のため branch 上だけで `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\amazon-asin.js` と `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger.js` を `C:\Users\HCY\OneDrive\開発\Blog_Vercel\vercel_preview_disabled_api\` へ退避し、Xpost 関連 API を優先して preview を通す方針に切り替えた。
