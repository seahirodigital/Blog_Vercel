# techreference_Xpost

## 0. 2026-04-13 Xpost note Secret 名切り替えメモ
### 変更内容
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` の note 認証系 Secret は Xpost 専用名へ切り替えた。
- 使用する Secret 名は `NOTE_EMAIL_XPOST_TECH`、`NOTE_PASSWORD_XPOST_TECH`、`NOTE_STORAGE_STATE_XPOST_TECH` とする。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py` は `NOTE_STORAGE_SECRET_NAME` 環境変数で、どの GitHub Secret に Cookie JSON を自動更新するか切り替えられるようにした。

### 運用ルール
- Xpost 側の note 下書きでは、既存の `NOTE_EMAIL` / `NOTE_PASSWORD` / `NOTE_STORAGE_STATE` を使わず、Xpost 専用 Secret だけを見る。
- `NOTE_STORAGE_STATE_XPOST_TECH` が空でも、`NOTE_EMAIL_XPOST_TECH` と `NOTE_PASSWORD_XPOST_TECH` があれば初回ログインで下書きを作成し、その後に Cookie JSON を同名 Secret へ自動保存する。
- 以後の note 下書きは保存済み Cookie を優先し、期限切れ時だけ再ログインして同じ Secret を上書き更新する。

## 0. 2026-04-13 Xpost UI / note 認証メモ
### 実装
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` のヘッダーは `note下書き` を青塗り白文字、`パイプライン` と `保存` を青枠白地青文字へそろえ、`保存` を最右端へ移した。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` のサイド下部には `アフィリンク` の下へ `ブログエディター` と `Info-Viewer` の戻りリンクを追加した。戻り先は `/index.html` と `/info_viewer/index.html`。
- Xpost の note 下書きは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\note-draft.js` を本編ブログと同じ経路で使い、`NOTE_DRAFT_URL_<hash>` を `localStorage` キー `xpostBlog.noteDraftUrls` にキャッシュするようにした。

### 運用ルール
- note のログイン情報はリポジトリ内ファイルへ書かない。登録先は GitHub Secrets の `NOTE_EMAIL`、`NOTE_PASSWORD`、`NOTE_STORAGE_STATE`。
- `NOTE_STORAGE_STATE` は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py` の `--save-cookies` で取得する note Cookie JSON を使う。
- Xpost 側の note 下書きでも Amazon トップ画像は使わず、`noTopImage: true` を維持する。本編と同じ workflow を通すが、技術記事では OGP 展開だけを残す。

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
- 2026-04-14 時点の本番運用では 15分巡回で新規 URL を `pending` 化する。
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

## 10. 2026-04-13 info_viewer型4ペインUIとtech affiliate / note下書きメモ
### 成功
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` は、角丸カード型ではなく `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\info_viewer\index.html` のサイドパネル思想に合わせ、記事一覧 / 元投稿 / エディター / プレビューの4ペイン型へ戻す方針にした。
- 「元投稿」トグルは各記事行ではなく、記事一覧ヘッダー右側に固定する。これにより、記事選択と元投稿ペイン表示切り替えの責務を分離できる。
- Xリンクは削除ボタンに見えないよう、斜め線2本ではなく「X」文字入りの正方形アイコンへ変更する。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js` に `resource=affiliate` を追加し、Vercel Functionを増やさず tech affiliate の読み書きを統合APIに載せる。
- tech affiliate の保存先は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\Xpost_Blog\tech_affiliate\affiliate_links.txt` とし、本編の `===MEMO1===` 形式を流用する。
- note下書きは既存の `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\note-draft.js` と `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` を流用し、Xpost_blog からは `noTopImage: true` を渡す。

### 判断
- note下書きでは OGP 展開は維持する。技術記事では URL カードの見え方が重要なため、`--no-top-image` は Amazonトップ画像の添付だけを止め、OGP処理は止めない。
- Vercel Hobby の Function 数対策として、affiliate 専用APIファイルは新規作成しない。既存の `resource=articles` / `resource=index` / `resource=trigger` と同じ統合API内に `resource=affiliate` を追加する。
- tech affiliate は Gemini 整形後の記事末尾へ入れる運用でよい。UI上では「アフィ挿入」ボタンで、選択中の MEMO を記事末尾へ追記する。

### 注意
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py` の既定動作は本編用に残す。`--no-top-image` が明示された場合だけ、Amazonトップ画像をスキップする。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\affiliate_links.txt` は本編用のため、Xpost_blog側からは直接編集しない。

## 11. 2026-04-14 フェーズ4 Apify 置き換え検証メモ
### 位置づけ
- 本節は `Apify` 検証時点の履歴メモであり、2026-04-14 の本番採用方針は次節 `12. SocialData 安定運用へ戻す判断メモ` を正とする。

### 比較した候補
- `apidojo/tweet-scraper`
  - Apify 表記価格は `from $0.40 / 1,000 tweets`。
  - 価格見出しは最安だが、今回の用途は Discord から拾った単一 X URL をその場で引く運用なので、検索主体 actor より単一 URL 指定が明示された actor を優先した。
- `apidojo/twitter-scraper-lite`
  - Actor ページの価格説明では `Single Tweet Query: $0.05 per query` と書かれている。
  - 単一 URL を 1 件ずつ処理する Xpost_blog では、見出し価格より実運用コストが高くなりやすいので採用しなかった。
- `fastdata/twitter-scraper`
  - Apify 表記価格は `from $0.50 / 1,000 results`。
  - `tweetUrls` による `Single Tweet Lookup` が明示され、空振り run は課金しない旨も書かれていた。
  - 今回は「単一 URL を安く、最短で取る」要件に最も合うため、第一採用にした。
- `SocialDataAPI`
  - 記事取得1件あたり0.0002ドル。
  - https://docs.socialdata.tools/getting-started/pricing/

### 採用判断
- 検証時点では `Apify -> fastdata/twitter-scraper` を主経路候補として見ていた。
- ただし `https://x.com/i/article/...` 本文まで Apify 単独で安定取得できる根拠は、この時点では確認できなかった。
- そのため `SocialData API` は残し、以下の条件だけ fallback する。
  - Discord 入力 URL 自体が `https://x.com/i/article/...` のとき
  - 通常ポストでも展開 URL に `https://x.com/i/article/...` が含まれ、記事本文の欠落が起きると判断したとき
  - Apify actor 実行自体が失敗したとき

### 実装メモ
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\apify_fetcher.py`
  - `fastdata/twitter-scraper` の `tweetUrls` 入力を使い、1 URL 単位で tweet 本文・件数・author 情報を共通 bundle へ正規化する。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\source_fetcher.py`
  - `Apify` / `SocialData` の切替と fallback 判定を集約した。
  - `preferred_provider=apify` でも fallback 自体は残し、極力 `Apify` を先に試す構成にした。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\runner.py`
  - 取得元を直結から抽象化へ切り替えた。
  - processing log と OneDrive frontmatter に `source_provider`、`source_provider_detail`、fallback の有無を残すようにした。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\xpost-blog-queue.yml`
  - `APIFY_API_KEY`、`XPOST_BLOG_SOURCE_PROVIDER=apify`、`XPOST_BLOG_APIFY_ACTOR=fastdata/twitter-scraper` を渡すようにした。

### 試行錯誤
- 最初は `apidojo/tweet-scraper` を最有力候補に見たが、headline 価格が安くても「単一 tweet lookup が明示されているか」と「1件ずつ回す運用での実コスト」は別問題だと判断した。
- `fastdata/twitter-scraper` は利用実績がまだ少ないため、不調時に即 `SocialData` へ戻せる抽象化を先に入れた。actor 差し替えだけで検証を続けられる状態にしてある。
- X記事本文取得は、今すぐ無理に Apify へ一本化すると品質事故になりやすいため、今回は「通常ポストは Apify 主経路、X記事だけ SocialData fallback」の折衷を採用した。

## 12. 2026-04-14 SocialData 安定運用へ戻す判断メモ
### 方針更新
- Xpost_blog の取得主経路は `SocialData API` に戻す。
- `Apify` は Xpost 取得案としては採用しない。検証コードは残すが、本番 workflow では使わない。
- queue 同期は `15分ごと`、取得は `1 run 最大1件` に固定する。
- thread 展開は行わない。記事化に必要な `Get Tweet` と必要時のみ `Get Article` だけを見る。
- Gemini は日次上限制御を入れず、既存の `GEMINI_TOKEN_tech -> GEMINI_TOKEN_INVESTSUB` failover を維持する。

### 運用整理表
| 項目 | 採用値 | 理由 |
| --- | --- | --- |
| queue 同期間隔 | 15分ごと | GitHub Actions の起動と依存インストールの重さを踏まえ、5分や10分より安定しやすい |
| 1 run の取得件数 | 最大1件 | SocialData の無料帯に十分余裕を残し、記事化の進行も追いやすい |
| 取得主経路 | SocialData API | X article 取得まで含めると一番安定するため |
| Apify | 不採用 | X article 本文取得まで単独で安定させにくかったため |
| thread 展開 | しない | 記事目的では過剰取得になりやすく、無料帯設計とも相性が悪いため |
| Gemini 制御 | 既存 failover 維持 | 日次上限より token failover の方が実運用に合っているため |

### コスト整理表
| ケース | 想定 API 呼び出し | 1記事あたりコスト | 1ドルあたり理論件数 | 備考 |
| --- | --- | --- | --- | --- |
| 通常ポスト | `Get Tweet` = 1回 | `$0.0002` | `5,000件` | 本文と基本メタだけで足りる場合 |
| X article 付き | `Get Tweet` + `Get Article` = 2回 | `$0.0004` | `2,500件` | article 本文を引く場合 |
| thread 展開 | 不採用 | `0` | 対象外 | 今回の運用では行わない |

### 取得間隔と無料帯の見積もり
| 指標 | 計算式 | 値 | メモ |
| --- | --- | --- | --- |
| 1日あたりの run 回数 | `24時間 × 4回/時` | `96 run/日` | 15分ごと実行 |
| 1日あたりの通常ポスト取得上限 | `96 run × 1件` | `96件/日` | `Get Tweet` のみ |
| 1日あたりの X article 取得上限 | `96 run × 1件` | `96件/日` | 件数上限は同じ、API 呼び出しは増える |
| 1日あたりの通常ポスト API 使用量 | `96 × 1 req` | `96 req/日` | SocialData 無料帯理論値より大幅に低い |
| 1日あたりの X article API 使用量 | `96 × 2 req` | `192 req/日` | article 付き投稿だけが続いても低水準 |
| SocialData 無料帯理論値 | `3 req/分 × 60 × 24` | `4,320 req/日` | docs 記載の fair-use ベース |

### 注意
- SocialData docs には「`3 requests per minute` までは free」と「`positive balance` が必要」が同居しているため、完全残高ゼロ運用を断定はしない。少額残高を置きつつ、課金発生を避ける設計として解釈する方が安全。
- 本番 workflow は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\xpost-blog-queue.yml` で `15分ごと` と `1 run 最大1件` に寄せる。
- 今回の設計は「最大取得」ではなく「安定して候補を拾い、記事制作を止めない」ことを優先する。

### 参考URL
- SocialData Pricing: https://docs.socialdata.tools/getting-started/pricing/
- GitHub Actions billing: https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions
- GitHub Actions scheduled workflows: https://docs.github.com/en/actions/reference/events-that-trigger-workflows

## 13. 2026-04-14 元投稿ビューアー空表示の調査メモ
### 症状
- `https://blog-vercel-dun.vercel.app/xpost_blog.html` で記事を開くと、元投稿ペインに `元投稿がありません` と出るケースがあった。
- 代表例は `📝 DESIGN.mdの日本版をつくりました ...` で、記事本文は存在するのに元投稿だけが空だった。

### 切り分け結果
- Discord 取得失敗ではなかった。`processingLogs` では `SocialData success` と `source_saved` が先に記録され、元投稿 Markdown 自体は OneDrive に保存されていた。
- 問題は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` が `article.id` から `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js?resource=index&articleId=...` を呼び、API 側が manifest の `articleId` 一致だけで元投稿を探していた点だった。
- 孤立記事では、記事 frontmatter に `source_file_id` が入っていても、manifest 側の同一投稿レコードに `articleId` が戻っておらず、viewer からは 404 になっていた。

### 根本原因
- `2026-04-14T03:46:49Z` の GitHub Actions run `24379895620` で、OneDrive Graph API が `503 Service Unavailable` を返し、`state/xpost_pipeline_state.json` 保存中に pipeline が停止していた。
- このとき記事ファイル実体だけが先に保存され、`state` と `manifest` の更新が追いつかず、`articleId` が欠けたまま残る条件が実際に発生していた。
- 加えて `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\xpost_blog.html` の手動保存は記事ファイル更新だけで、manifest/state の再同期は行っていなかった。

### 対応
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\xpost-blog.js`
  - manifest に `articleId` が無い場合でも、記事 frontmatter の `source_file_id` / `post_url` / `normalized_post_url` を使って元投稿を引ける fallback を追加した。
  - これにより、孤立記事でも viewer が元投稿を返せるようにした。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\xpost_blog\modules\onedrive_writer.py`
  - OneDrive 保存時に `429/500/502/503/504` の短い retry を追加した。
  - transient な Graph API エラーで `state` と `manifest` だけ取り残される事故を減らす狙い。
