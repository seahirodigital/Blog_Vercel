# Amazon Product Details Blog Pipeline Plan

## 目的

Amazon の個別商品ページから商品説明、特徴、スペック、価格、評価、レビュー/評判などのテキスト情報を取得し、既存の YouTube 文字起こし入力の代わりとしてブログ生成パイプラインへ流す。

## 採用する Apify Actor

- Actor: `scraper-engine/amazon-product-details-scraper`
- 入力: Amazon 商品 URL または ASIN
- 取得対象: 商品タイトル、価格、評価、レビュー件数、商品説明、特徴、スペック、A+ Content、レビュー本文など、Actor が返す商品詳細データ
- 既存 YouTube パイプラインとの接続: 取得結果を `title` と `captions` を持つ疑似 transcript に整形して、既存の Gemini 作家、編集、編集長プロセスへ渡す

## 実装方針

1. `scripts/pipeline/modules/amazon_product_fetcher.py` を追加し、Apify から商品詳細を取得する。
2. `scripts/pipeline/main.py` に `source_type=amazon` と URL 直指定の処理を追加する。
3. `api/trigger.js` と `.github/workflows/blog-pipeline.yml` に Amazon URL 配列を渡せる入力を追加する。
4. Chrome 拡張 `reference` に「ページ詳細取得」プルダウンと記事作成ボタンを追加する。
5. Viewer サイドパネルにスマホ向け `AMZN` URL 入力ボタンを追加する。
6. 生成記事には `source_type` メタ情報を付与し、Viewer の記事一覧で `AMZN` / `YT` タグを表示する。

## UX

### PC

Amazon 商品ページを開いた状態で Chrome 拡張を開き、ページ詳細取得から「今表示しているページ」または「その他タブで表示中すべて」を選び、記事作成ボタンで GitHub Actions を起動する。

### スマホ

Amazon アプリなどから商品 URL をコピーし、Blog Vercel のサイドパネル上の `AMZN` ボタンから URL を入力して GitHub Actions を起動する。

## 注意点

- `amzn.asia` などの短縮 URL は Apify 側で失敗する可能性があるため、可能な限り正規 URL または ASIN に解決してから渡す。
- Apify トークンは GitHub Secrets / Vercel 環境変数側で有効なものを使う。ローカル `.env` の既存キーは認証エラーになった。
- 既存の Sheets 経由 YouTube パイプラインは残し、Amazon 直URL指定時のみ別分岐で実行する。

## 実装・実行メモ

- `scraper-engine/amazon-product-details-scraper` の入力は `asins` を主入力にし、短縮 URL などで ASIN が取れない場合は `startUrls` も併記する。
- 言語指定は Actor schema に合わせて `ja-JP` を既定値にする。
- `https://amzn.asia/d/00VBIXc2` で Amazon 直URLモードを実行し、Apify 呼び出しまでは到達した。ローカルの Apify token が無効なため、実データ取得は 401 `user-or-token-not-found` で停止した。
