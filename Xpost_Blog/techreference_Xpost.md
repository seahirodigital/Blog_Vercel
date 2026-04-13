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

## 6. 2026-04-13 GitHub Actions 再検証メモ
### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\xpost-blog-queue.yml` の再実行 run `24330603939` では、`DISCORD_BOT_TOKEN` と `SOCIALDATA_API_KEY` の不足は解消した。
- 同 run で Discord 6 件の同期、SocialData からの元投稿取得、OneDrive への元投稿ソース保存、manifest 再構築までは成功した。
- `https://blog-vercel-git-xpost-blog-preview-seahirodigitals-projects.vercel.app/api/xpost-blog-index` でも `generatedAt: 2026-04-13T07:15:14.854875` の manifest を確認でき、少なくとも preview API から最新 manifest を読める状態になった。

### 失敗
- 記事本文の生成だけは `Gemini` で停止した。失敗メッセージは `GenerateContentConfig` に対する `thinking_level` の validation error だった。
- 失敗した投稿は `https://x.com/l_go_mrk/status/2041474685767159840` で、queue 上は `failed`、`lastFailureStage` は `Gemini` として manifest に残った。

### 試行錯誤
- まず quota や token 切り替え不良を疑ったが、run log では `GEMINI_TOKEN_tech` 自体は読めていたため、認証や secret ではなく SDK パラメータ形状の問題だと切り分けた。
- ローカルで `google.genai.types.GenerateContentConfig.model_fields` を確認すると、`thinking_level` は直下ではなく `thinking_config` 配下で受ける構造だった。
- そのため `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\gemini_runtime.py` を修正し、`thinking_level` を `thinking_config.thinking_level` に詰め直す方針へ切り替えた。

## 7. 2026-04-13 Gemini thinking_level 無効化メモ
### 失敗
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\gemini_runtime.py` で `thinking_config.thinking_level` へ正しくネストしても、`gemini-2.5-flash` の `models.generate_content` では `Thinking level is not supported for this model.` が返った。
- そのため Xpost_blog では、パラメータ形状ではなく `thinking_level` 指定そのものを外す必要があると判断した。

### 判断
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py` の本編多段生成は触らない。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\gemini_formatter.py` だけ `thinking_level` を外し、ブログ本編と同じく素直な Gemini generation config として `temperature=0.5` を使う。

### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\gemini_formatter.py` から `thinking_level` を外した後、GitHub Actions run `24331356968` は `処理成功件数: 1` で完了した。
- 同 run の manifest 更新時刻は `2026-04-13T07:37:29.427484` で、OneDrive への記事保存処理まで進んだ。

### 追加の注意
- `https://blog-vercel-git-xpost-blog-preview-seahirodigitals-projects.vercel.app/xpost_blog/` は Vercel Deployment Protection 配下の preview URL である。
- Vercel MCP では HTML と runtime log の取得ができたが、未ログインの Playwright では Vercel のログイン画面へリダイレクトされた。
- 画面確認用には Vercel が発行する一時共有 URL を使う。ただしブラウザ側の認証状態によっては Vercel ログインが必要になる。

## 8. 2026-04-13 Vercel Functions 上限と Xpost API 統合方針
### 背景
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api` 配下の JavaScript ファイルは、Vercel では基本的に 1 ファイル 1 Serverless Function として扱われる。
- Vercel Hobby plan では deployment あたりの Function 数に上限があるため、Xpost 用 API を `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog-articles.js`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog-index.js`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-xpost-blog.js` のように 3 本足すと上限に当たりやすい。

### 採用する方針
- Xpost 用 API は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` の 1 本に統合する。
- ここでいう「3つに分岐」とは、Vercel Function を 3 本作るという意味ではない。1 本の `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` の中で、URL query の `resource` 値を見て処理を切り替えるという意味である。
- 例: `https://blog-vercel-dun.vercel.app/api/xpost-blog?resource=articles` は記事一覧・記事本文・保存処理を担当する。
- 例: `https://blog-vercel-dun.vercel.app/api/xpost-blog?resource=index` は manifest と元投稿ソース取得を担当する。
- 例: `https://blog-vercel-dun.vercel.app/api/xpost-blog?resource=trigger` は GitHub Actions の Xpost pipeline 起動を担当する。

### 理由
- 外から見ると API の入口は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` 1 本だけなので、Vercel Functions 数の増加は 1 本に抑えられる。
- 中では `resource=articles`、`resource=index`、`resource=trigger` で処理責務を分けるため、既存の `xpost-blog-articles` / `xpost-blog-index` / `trigger-xpost-blog` の考え方は維持できる。

## 9. 2026-04-13 本番 URL 用 UI と統合 API 実装メモ
### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` を追加し、`resource=articles`、`resource=index`、`resource=trigger` の 3 ルートを 1 本の Vercel Function に統合した。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` を追加し、`https://blog-vercel-dun.vercel.app/xpost_blog.html` で読める静的ページとして配置する方針にした。
- UI は黒背景ではなく白背景基調へ変更した。
- 「元投稿」の表示切り替えは、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` の記事一覧行右端にある `元投稿` トグルから制御する。
- エディタは入力に合わせてプレビューを即時更新し、保存は `Ctrl+S` または `Command+S` でも実行できるようにした。

### 判断
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog-articles.js`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog-index.js`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-xpost-blog.js` は本番 `main` に個別追加しない。
- 理由は、Vercel Hobby の Function 数上限に近いためである。3 本を個別追加すると制限に当たりやすいが、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` 1 本なら API 増加を 1 Function に抑えられる。
- `OneDrive 元投稿` リンクは UI から削除し、`OneDrive 記事` リンクだけをエディタ側のアイコンとして残す。

### 画面確認後の修正
- `https://blog-vercel-dun.vercel.app/xpost_blog.html` のスクリーンショット確認で、記事一覧の上に OneDrive の相対フォルダ名 `20260413_...` が残っていることを確認した。
- これは「記事カードレイアウト上部にある説明文章は不要」という指定に反するため、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` から記事一覧のフォルダラベル表示を削除した。
- あわせて、初回ロード時に先頭記事を自動選択し、エディタとプレビューまで即時に見えるようにした。
