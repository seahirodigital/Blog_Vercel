# Vibe Blog Engine - 現在仕様書

YouTube 動画からブログ記事を生成し、OneDrive で管理し、Vercel UI から編集し、note.com へ下書き保存する自動化システムです。ここには 2026-04-09 時点で実際に動いている仕様だけを書きます。試行錯誤、失敗ノウハウ、Adobe Express を使った時期の経緯は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\techrefere.md` に分離しています。

## Use Cases & Search Tags
- 「YouTube動画からブログ記事を自動生成するパイプライン」
- 「Gemini AIでYouTube文字起こしからnote記事を作る」
- 「GitHub Actionsで記事生成を自動化するシステム」
- 「Vercelで記事をプレビュー・編集するWebアプリ」
- 「Amazonアフィリエイトリンクを記事に自動挿入する」
- 「AppSheetからブログ生成パイプラインを実行する」
- 「Google Sheetsで記事生成の進捗管理をする」
- 「noteの下書きにMarkdown記事を自動投稿する」

---

## 1. システム全体像

このリポジトリは、次の 3 本の本番フローで動いています。

### 1.1 記事生成フロー

```text
Google Sheets
  ↓ 「状況」列が 単品 / 複数 / 情報 / 量産元 の行だけを取得
C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\blog-pipeline.yml
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\apify_fetcher.py
  ↓ YouTube 文字起こし取得
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py
  ↓ Gemini 2.5 Flash で記事生成
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_affiliate_links.py
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_amazon_affiliate.py
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\onedrive_sync.py
  ↓ OneDrive へ Markdown 保存
Google Sheets の「状況」を 完了 へ更新
  ↓
GitHub Variable YT_SOURCE_<hash> を保存
```

### 1.2 note 下書き保存フロー

```text
C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\index.html
  ↓ 下書きボタン
C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\note-draft.js
  ↓ workflow_dispatch
C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml
  ↓ OneDrive から file_id の Markdown を取得
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py
  ↓ note API で下書き作成
  ↓ Playwright で OGP 展開
  ↓ Amazon トップ画像を判定してアップロード
GitHub Variable NOTE_DRAFT_URL_<hash> を保存
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\index.html が URL を再取得して表示
```

### 1.3 info_viewer 構築フロー

```text
C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-info-viewer.js
  ↓ workflow_dispatch
C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\main.py
  ↓
OneDrive の info_viewer 配下に manifest と出力を更新
  ↓
C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\info_viewer\index.html で表示
```

## 2. GitHub Actions の現在仕様

| ワークフロー | ファイル | トリガー | 現在の役割 |
| --- | --- | --- | --- |
| Blog Pipeline - YouTube → AI → OneDrive | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\blog-pipeline.yml` | 毎日実行 / 手動実行 | Google Sheets を読んで記事を量産する |
| Note 下書き保存 - OneDrive → note.com | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` | `workflow_dispatch` | OneDrive の 1 記事を note 下書きへ保存する |
| Note セッション維持 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-keepalive.yml` | 3 日ごと / 手動実行 | note セッションを延命する |
| Info Viewer Pipeline | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml` | 毎日実行 / 手動実行 | info_viewer の出力を構築する |

現在の本番 Actions には、debug 専用の `Apify Amazon hiRes Probe` は含みません。

## 3. 記事生成パイプラインの現実仕様

### 3.1 処理対象の決め方

- 実行入口は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger.js` です。
- ただし、実際にどの行を処理するかは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py` が Google Sheets の「状況」列で決めます。
- 現在処理対象になる値は `単品`、`複数`、`情報`、`量産元` の 4 種です。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\blog-pipeline.yml` には `mode` 入力がありますが、2026-04-09 時点の `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py` はシートの pending 行を読む方式で動いており、単発 URL を受け取る専用分岐にはなっていません。

### 3.2 1 行ごとの処理フロー

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\apify_fetcher.py` が YouTube の文字起こしを取得します。
2. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py` が Gemini 2.5 Flash で記事本文を生成します。
3. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_affiliate_links.py` が通常アフィリエイトリンクを挿入します。
4. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_amazon_affiliate.py` が Amazon アフィリエイト導線を挿入します。
5. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\onedrive_sync.py` が Markdown を OneDrive へ保存します。
6. Google Sheets の「状況」を `完了` へ更新します。
7. GitHub Variable `YT_SOURCE_<hash>` に元 YouTube URL を保存します。

### 3.3 状況列による分岐

| 状況 | 使うプロンプト |
| --- | --- |
| `単品` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\01-writer-prompt.txt` → `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\02-editor-prompt.txt` → `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\03-director-prompt.txt` |
| `複数` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\01-writer-prompt.txt` 内の該当セクション → `02-editor-prompt.txt` → `03-director-prompt.txt` |
| `情報` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\01-writer-prompt.txt` 内の該当セクション → `02-editor-prompt.txt` → `03-director-prompt.txt` |
| `量産元` | 上記に加えて `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\031-best-outline-prompt.txt` と `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt` を使います |

### 3.4 アフィリエイト挿入の現在仕様

- 通常アフィリエイト挿入は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_affiliate_links.py` が担当します。
- Amazon アフィリエイト導線は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_amazon_affiliate.py` が担当します。
- `insert_affiliate_links.py` は `affiliate_links.txt` の `===MEMO1===` と `▼` ブロックを読んで挿入します。
- スクリプト未検出またはエラー時は記事生成自体は止めず、その行だけ挿入をスキップします。
- UI 側の 🔗 ボタンは偶数 H2 の手動挿入、Python スクリプトは奇数 H2 の自動挿入、という役割分担です。

### 3.5 保存と失敗時の現在挙動

- 保存先は OneDrive の `ONEDRIVE_FOLDER` です。
- 保存ファイル名は `YYYYMMDD_HHMM_動画タイトル.md` です。
- 文字起こし取得に失敗した場合: その行は失敗扱いで終了し、Google Sheets の「状況」は更新しません。
- AI 生成に失敗した場合: その行は失敗扱いで終了し、後続の保存へ進みません。
- 保存成功時は GitHub Variable `YT_SOURCE_<hash>` に元 YouTube URL を保存します。

## 4. 管理画面（Vibe Blog UI）

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\index.html` で記事一覧、Markdown 編集、note 下書き保存を行います。

### 4.1 サイドバー

- OneDrive のフォルダ階層を最大 5 階層まで再帰表示します。
- 右クリックメニューで選択、複製、削除、OneDrive で開く、エクスプローラー表示ができます。
- 複数選択してドラッグすると、フォルダ間一括移動ができます。
- 下部のフォルダ管理から表示対象を絞れます。

### 4.2 エディタ

- 左ペインは Markdown エディタ、右ペインはプレビューです。
- エディタとプレビューは相互スクロール同期します。
- URL 単独行は OGP カードへ変換できます。
- エディタバーには note 保存先 URL、保存状態、文字数、🔗 ボタン、コピーボタンがあります。

### 4.3 操作系

- タイトル編集は H1 優先で行い、確定時に OneDrive 側ファイル名も更新します。
- ツールバーから Amazon 検索、note、新規下書き、アフィリンク管理、Google Sheets、パイプライン実行、保存、リロードができます。
- モバイルでは長押しドラッグ移動と左スワイプ操作に対応しています。

## 5. note 下書き自動投稿システム

### 5.1 仕組み

```text
[下書きボタン]
    ↓ POST /api/note-draft
    ↓ C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml を dispatch
    ↓ C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py 実行
    ↓ API ログイン → text_notes → draft_save
    ↓ Playwright で OGP 展開
    ↓ Amazon トップ画像を判定してアップロード
    ↓ GitHub Variable NOTE_DRAFT_URL_<hash> に URL を保存
    ↓ UI が polling して URL を表示
```

### 5.2 note API の現在仕様

| 操作 | エンドポイント | メソッド |
|------|--------------|---------|
| ログイン | `https://note.com/api/v1/sessions/sign_in` | POST |
| スケルトン作成 | `https://note.com/api/v1/text_notes` | POST |
| 本文保存 | `https://note.com/api/v1/text_notes/draft_save?id={id}&is_temp_saved=true` | POST |

本文保存では `X-XSRF-TOKEN`、`Origin: https://editor.note.com`、`Referer: https://editor.note.com/` が必須です。低レベル仕様は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\techrefere2.md` にあります。

### 5.3 セッション管理

- 初回だけ `python prompts/05-draft-manager/note_draft_poster.py --save-cookies` で Cookie を保存します。
- 以降は API ログインで Cookie を自動更新します。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-keepalive.yml` が 3 日ごとにセッションを延命します。

### 5.4 Playwright フェーズの現在分岐

- エディタ本文が読み込めた場合: OGP 展開とトップ画像処理まで進みます。
- エディタ本文が読み込めない場合: Playwright フェーズを打ち切ります。この場合でも、API で保存した本文下書き自体は残ります。
- 複数記事を選んだ場合でも、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\note-draft.js` は file_id ごとに順番に `workflow_dispatch` を投げます。1 file_id = 1 note 記事です。

### 5.5 Amazon トップ画像の対象解決

1. 記事本文の先頭から最初の `▼` より前にある最初の URL を拾います。
2. その URL から ASIN を抽出できれば、それを最優先ターゲットにします。
3. URL から ASIN が取れない場合は、note タイトル → H1 → H2 の順で商品名を再抽出します。
4. それでも商品名が決まらなければ、トップ画像挿入をスキップします。

### 5.6 Amazon トップ画像の取得方法

トップ画像の取得と保存は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py` が担当します。

現在の処理順は次です。

1. Amazon Creators API の `getItems` または `searchItems` で通常画像を必ず取得します。
2. 画像 URL と ASIN が決まったら、Apify actor `kawsar/amazon-product-details-scrapper` へ `https://www.amazon.co.jp/dp/{ASIN}` を渡して hiRes 画像を取りに行きます。
3. Apify で hiRes が返らない場合だけ、Amazon 商品詳細 HTML を取得して `data-old-hires` と `colorImages.initial[].hiRes` を正規表現で探します。
4. HTML が captcha の場合や hiRes が見つからない場合は、通常画像だけを使って継続します。

つまり、現在の hiRes 主経路は Amazon 直接 scraping ではなく Apify です。Amazon 直接 HTML は fallback です。

### 5.7 画像の保存ルール

| 種別 | ローカル既定保存先 | GitHub Actions 上の一時保存先 | OneDrive 側の保存先 | 内容 |
| --- | --- | --- | --- | --- |
| raw | `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images\raw` | `/home/runner/work/_temp/amazon_top_images/raw` | `Vercel_Blog/Amazon_images/raw` | Creators API の通常画像と、取得できた場合の hiRes 元画像 |
| prepared | `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images\prepared` | `/home/runner/work/_temp/amazon_top_images/prepared` | `Vercel_Blog/Amazon_images/prepared` | note ヘッダー用に整形した画像 |

命名規則は次です。

- 通常画像: `YYYYMMDD_ASIN.jpg`
- hiRes 元画像: `YYYYMMDD_ASIN_hires.jpg`
- note ヘッダー整形画像: `YYYYMMDD_ASIN_note_hero.jpg`

### 5.8 `prepared` 画像の現在仕様

- 生成サイズは `1600x836` です。
- 比率は note ヘッダーの `800:418` と同じです。
- リサイズは `contain` です。
- 余白色は白固定 `RGB(255, 255, 255)` です。
- 向き補正は `ImageOps.exif_transpose()` です。
- 保存形式は JPEG、品質は `quality=92` です。

### 5.9 note へアップロードする画像の選び方

現在の優先順位は固定です。

1. `prepared`
2. `hires`
3. `api`

したがって、正常系では `direct_prepared` が本番経路です。

### 5.10 アップロード方法の現在仕様

- 本番経路は note の通常 `画像をアップロード` 導線です。
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py` は、選ばれた画像を file chooser で直接アップロードします。
- Adobe Express は本番経路では使いません。
- `NOTE_TOP_IMAGE_USE_ADOBE=1` を明示したときだけ debug 経路として残しています。
- `NOTE_TOP_IMAGE_FORCE_DIRECT=1` を付けると、Adobe debug を有効にしていても通常アップロードを維持します。
- `NOTE_TOP_IMAGE_DEBUG=1` を付けたときだけ、HTML、PNG、JSON の debug 成果物を保存します。

## 6. Vercel API の現在仕様

| API | ファイル | 役割 |
| --- | --- | --- |
| `/api/articles` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\articles.js` | OneDrive 記事の一覧取得、本文取得、保存、複製、移動、削除、リネーム |
| `/api/trigger` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger.js` | `blog-pipeline.yml` を dispatch |
| `/api/note-draft` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\note-draft.js` | `note-draft.yml` を dispatch、または note 下書き URL を返す |
| `/api/affiliate-links` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\affiliate-links.js` | `affiliate_links.txt` の MEMO を OneDrive 経由で読み書き |
| `/api/ogp` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\ogp.js` | OGP タイトル、説明、画像を取得。Amazon URL の特殊処理あり |
| `/api/open-file` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\open-file.js` | ローカルの Explorer / Finder で記事ファイルを選択表示 |
| `/api/amazon-asin` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\amazon-asin.js` | Google Custom Search で商品名から ASIN を探す |
| `/api/youtube-source` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\youtube-source.js` | GitHub Variable `YT_SOURCE_<hash>` から元動画 URL を返す |
| `/api/trigger-info-viewer` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-info-viewer.js` | `info-viewer-pipeline.yml` を dispatch |
| `/api/info-viewer-index` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\info-viewer-index.js` | info_viewer の manifest や index 情報を返す |

## 7. GitHub Actions ワークフロー一覧

| ワークフロー | トリガー | 役割 |
|------------|---------|------|
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\blog-pipeline.yml` | 毎日実行 / 手動実行 | 記事自動生成 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` | `workflow_dispatch` | note 下書き投稿 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-keepalive.yml` | 3 日ごと / 手動実行 | note セッション延命 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml` | 毎日実行 / 手動実行 | info_viewer 構築 |

## 8. 環境変数の現在仕様

### 8.1 GitHub Secrets

| 変数名 | 現在の用途 |
| --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Sheets 読み書き |
| `SPREADSHEET_ID` | 記事生成対象シートのあるスプレッドシート ID |
| `SHEET_NAME` | 記事生成対象シート名 |
| `APIFY_API_KEY` | YouTube 文字起こし取得と Amazon hiRes 取得 |
| `GEMINI_API_KEY` | Gemini 2.5 Flash 記事生成 |
| `ONEDRIVE_CLIENT_ID` | OneDrive / Microsoft Graph |
| `ONEDRIVE_CLIENT_SECRET` | OneDrive / Microsoft Graph |
| `ONEDRIVE_REFRESH_TOKEN` | OneDrive / Microsoft Graph |
| `ONEDRIVE_FOLDER` | 記事 Markdown の保存先ルート |
| `NOTE_EMAIL` | note API ログイン |
| `NOTE_PASSWORD` | note API ログイン |
| `NOTE_STORAGE_STATE` | Playwright 用の note Cookie |
| `GH_PAT` | GitHub Variables / Secrets 更新、workflow dispatch |
| `GOOGLE_CSE_API_KEY` | `/api/amazon-asin` 用 |
| `GOOGLE_CSE_CX` | `/api/amazon-asin` 用 |
| `AMAZON_CLIENT_ID` | Amazon Creators API |
| `AMAZON_CLIENT_SECRET` | Amazon Creators API |

### 8.2 Vercel 環境変数

| 変数名 | 現在の用途 |
| --- | --- |
| `ONEDRIVE_CLIENT_ID` | OneDrive / Microsoft Graph |
| `ONEDRIVE_CLIENT_SECRET` | OneDrive / Microsoft Graph |
| `ONEDRIVE_REFRESH_TOKEN` | OneDrive トークン更新 |
| `ONEDRIVE_FOLDER` | 記事 Markdown の保存先ルート |
| `VERCEL_TOKEN` | OneDrive refresh token を Vercel へ反映 |
| `VERCEL_PROJECT_ID` | OneDrive refresh token を Vercel へ反映 |
| `GITHUB_TOKEN` | GitHub Actions dispatch と Variables 読み書き |
| `GITHUB_REPO` | 対象リポジトリ名 |
| `LOCAL_ARTICLES_BASE` | `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog` |
| `INFO_VIEWER_ONEDRIVE_FOLDER` | info_viewer の OneDrive ルート |

### 8.3 実行フラグ

| 変数名 | 現在の意味 |
| --- | --- |
| `NOTE_TOP_IMAGE_DEBUG` | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts` に debug 成果物を出す |
| `NOTE_TOP_IMAGE_USE_ADOBE` | Adobe Express 経路を debug 用に有効化する |
| `NOTE_TOP_IMAGE_FORCE_DIRECT` | Adobe debug を有効にしていても direct upload を維持する |

## 9. ファイル構成

| パス | 役割 |
| --- | --- |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\index.html` | 記事一覧、Markdown 編集、note 下書き実行のメイン UI |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\links.html` | 補助ページ |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\info_viewer\index.html` | info_viewer の表示 UI |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api` | Vercel Serverless Functions |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py` | 記事生成パイプラインの入口 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules` | Google Sheets、Apify、OneDrive、Gemini 連携 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts` | 記事生成・アフィリエイト挿入・note 下書き投稿の prompt / 実処理 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager` | アフィリエイトリンク挿入、Amazon 画像取得 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager` | note 下書き保存、OGP 展開、トップ画像挿入 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test` | note トップ画像の debug 専用置き場 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows` | GitHub Actions 定義 |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\techrefere2.md` | note API の低レベル技術リファレンス |
| `C:\Users\HCY\OneDrive\開発\Blog_Vercel\techrefere.md` | 経緯、試行錯誤、失敗ノウハウの蓄積場所 |

## 10. 現在の note トップ画像の正常系

```text
記事本文の先頭 URL から ASIN 解決
  ↓
Amazon Creators API で通常画像取得
  ↓
Apify で hiRes を試行
  ↓ 取れれば hiRes、取れなければ通常画像
raw 保存
  ↓
Pillow で white background の prepared 画像を作成
  ↓
note の通常アップロード導線へ prepared を投入
  ↓
下書き保存
```

この正常系が通ったときの `image_flow` は `direct_prepared` です。

## 11. 2026-04-10 Gemini 制限時の切り替え仕様

本番記事フローの Gemini 呼び出しは、2026年4月10日現在では
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\blog-pipeline.yml`
から
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py`
を起動し、1記事ずつ直列で処理する。

1記事あたりの AI 整形は次の 3 段階で進む。

1. writer
2. editor
3. director

Gemini のキー候補は次の 4 段構えである。

1. `GEMINI_API_KEY`
2. `GEMINI_TOKEN_sub`
3. `GEMINI_TOKEN_SUB2`
4. `GEMINI_TOKEN_SUB3`

切り替えルールは次の通り。

- `429`
- `quota exceeded`
- `rate limit`

上記のいずれかを検知したら、同じキーでは待機せず、その場で次の候補キーへ切り替える。
30秒 / 60秒 / 90秒待機して同一キーを再試行する旧仕様は廃止した。

さらに、あるキーが 1 回でも quota / rate limit に到達した場合は、その GitHub Actions run 中では以後そのキーを再試行しない。
これにより、2本目以降の記事で同じ exhausted key を無駄打ちしない。

writer / editor / director の途中で quota に到達した場合でも、成功済みステップの出力は保持する。
たとえば writer 完了後に editor で quota へ達した場合、次のキーでは writer をやり直さず、
editor から再開する。director で止まった場合も同様に、次キーでは director から再開する。

ログにはキー本体を出さず、SHA-256 の先頭 8 文字だけを指紋として表示する。
これにより、秘密値を漏らさずに「本当に別キーか」を確認できる。

現在の本番記事フロー用 Gemini secrets は次の通り。

- `GEMINI_API_KEY`
- `GEMINI_TOKEN_sub`
- `GEMINI_TOKEN_SUB2`
- `GEMINI_TOKEN_SUB3`

モデル名と transport の共通設定は
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\gemini_runtime.py`
へ集約している。
本編と `info_viewer` の両方がこの共通モジュールを参照するため、
将来 Gemini のモデル名を変更する場合は、この共通設定を起点に見直せばよい。

## 12. 2026-04-10 info_viewer 現行運用メモ

`info_viewer` の現行 workflow は
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-queue.yml`
であり、旧 `Info Viewer Pipeline Legacy` は廃止した。

`info_viewer` は本番記事フローと Gemini キーを分離している。
2026年4月10日現在では `GEMINI_API_KEY` を使わず、次の専用キーのみを利用する。

- `GEMINI_TOKEN_invest`
- `GEMINI_TOKEN_INVESTSUB`
- `GEMINI_TOKEN_tech`

プロフィールごとの切り替えは次の通り。

- `invest`: `GEMINI_TOKEN_invest -> GEMINI_TOKEN_INVESTSUB`
- `tech`: `GEMINI_TOKEN_tech`

一覧 UI の現行仕様は次の通り。

- スプレッドシートの `サムネイル` 列から YouTube サムネイル URL を取り出し、カード左側へ表示する
- スプレッドシートの `動画更新日時` を読み込み、一覧の日時表示と `新着順` の並び替えに使う
- 日時表示は `YYYY/MM/DD/HH:MM` 形式で出す
- YouTube タイトルは一覧では 30 文字以内に省略してカード高さを抑える
- `記事あり` や `完了` などの一覧ラベルは表示しない
