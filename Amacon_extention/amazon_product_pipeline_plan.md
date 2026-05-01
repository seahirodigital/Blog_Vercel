# Amazon Product Details Blog Pipeline Plan

## 目的

Amazon の個別商品ページから商品説明、特徴、スペック、価格、評価、レビュー/評判などのテキスト情報を取得し、既存の YouTube 文字起こし入力の代わりとしてブログ生成パイプラインへ流す。

## 採用方針

- PC Chrome 拡張ルートでは、Amazon ページを開いているブラウザ側で DOM / alt / carousel / 可能なら OCR テキストを抽出し、`source_payloads` として GitHub Actions に渡す。
- GitHub Actions は `source_payloads` がある場合、Apify もサーバーHTML再取得も使わず、Chrome 抽出済みデータだけを疑似 transcript に整形して既存の Gemini 作家、編集、編集長プロセスへ渡す。
- スマホ URL 入力など `source_payloads` がない場合だけ、サーバー側の HTML fallback を試す。
- Apify は無料で十分な商品詳細・A+・画像内相当テキストを安定取得できる Actor が見つからなかったため、デフォルト無効にする。将来使う場合のみ `AMAZON_USE_APIFY=true` で明示的に有効化する。

## 実装方針

1. `scripts/pipeline/modules/amazon_product_fetcher.py` で Chrome 抽出 payload とサーバー HTML fallback を transcript 化する。
2. `scripts/pipeline/main.py` に `source_type=amazon`、`source_urls`、`source_payloads` の処理を追加する。
3. `api/trigger.js` と `.github/workflows/blog-pipeline.yml` に Amazon URL 配列と Chrome 抽出 payload を渡せる入力を追加する。
4. Chrome 拡張 `reference` に「ページ詳細取得」プルダウン、記事作成ボタン、ページ内商品詳細抽出を追加する。
5. Viewer サイドパネルにスマホ向け `AMZN` URL 入力ボタンを追加する。
6. 生成記事には `source_type` メタ情報を付与し、Viewer の記事一覧で `AMZN` / `YT` タグを表示する。

## UX

### PC

Amazon 商品ページを開いた状態で Chrome 拡張を開き、ページ詳細取得から「今表示しているページ」または「その他タブで表示中すべて」を選び、記事作成ボタンで GitHub Actions を起動する。

### スマホ

Amazon アプリなどから商品 URL をコピーし、Blog Vercel のサイドパネル上の `AMZN` ボタンから URL を入力して GitHub Actions を起動する。

## 注意点

- `amzn.asia` などの短縮 URL はサーバーHTML fallback 側で失敗する可能性があるため、PC ではChrome拡張抽出を優先する。
- Apify はデフォルト無効。Apify トークン未設定でも Amazon Chrome payload / HTML fallback ルートは動く。
- 既存の Sheets 経由 YouTube パイプラインは残し、Amazon 直URL指定時のみ別分岐で実行する。

## 実装・実行メモ

- `scraper-engine/amazon-product-details-scraper` は Actions で `actor-is-not-rented` になったため主経路から外した。
- Junglee 系の無料候補もローカル token 制約下では実データ検証できず、要件の「特徴・商品説明・スペック・画像内相当テキスト」まで安定取得できる確証がない。
- `https://www.amazon.co.jp/dp/B0G39C97WQ` はサーバーHTML fallback で特徴、商品説明、価格、評価、在庫、A+ DOM テキストを取得できた。ただし画像内に焼き込まれた文は OCR がないと抜けない。
