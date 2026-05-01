# Amazon Product Scraper Chrome 拡張 仕様書

## 使い方とページ別の動作

この拡張は、Chromeで開いているAmazonページから商品情報を取得し、クリップボードコピーまたはGoogle Sheetsへの直接書き込みを行う。2026-05-01時点の初期モードは `個別商品ページ` である。Amazonの商品詳細ページを開いて、Sheets書き込みをONにして `実行(Sheets書き込み)` を押すのが基本操作である。

### 基本手順

1. Chromeで対象のAmazonページを開く。
2. 拡張ポップアップを開く。
3. `アフィリエイトタグ` を確認する。
4. Sheetsへ直接書き込む場合は、設定パネルで `スプレッドシートURL` またはスプレッドシートID、`シート名` を設定し、`Google認証` を済ませる。
5. `Sheets書き込み` をONにする。
6. 対象ページに合う `モード` を選ぶ。
7. `ページ詳細取得` で、現在のタブだけなら `今表示しているページ`、同一ウィンドウ内の複数タブをまとめるなら `その他タブで表示中すべて` を選ぶ。
8. `実行` または `実行(Sheets書き込み)` を押す。

Sheets書き込みがOFFのときは、取得結果は従来どおりクリップボードへコピーされる。Sheets書き込みがONのときは、コピーではなく指定したGoogleスプレッドシートへ行追加する。指定先はネイティブのGoogleスプレッドシートである必要があり、Excel/OfficeファイルのままではSheets APIで書き込めない。

### モード別の対象ページと動作

| モード | 主な対象ページ | 実行時の動作 | Sheets書き込み時の行 |
|---|---|---|---|
| `個別商品ページ` | Amazonの商品詳細ページ。例: `/dp/{ASIN}`、`/gp/product/{ASIN}` | 商品タイトル、アフィリエイトURL、ブランド、価格、参考価格、レビュー平均、レビュー数を取得する。初期選択モード。 | 1商品につき1行。複数タブ選択時は商品詳細タブごとに1行ずつ追加する。 |
| `現在ページ取得` | 検索結果、ランキング、カテゴリ、商品グリッドなど、複数商品が並ぶページ | 現在表示されている一覧内の商品カードから、商品名、URL、価格、参考価格、レビュー平均、レビュー数を取得する。 | 商品カード1件につき1行。複数タブ選択時は各タブの一覧結果をまとめて追加する。 |
| `標準スクレイプ` | 検索結果、ランキング、カテゴリなどページ送りできる一覧ページ | 目標件数に達するまでスクロールと次ページ遷移を行い、レビュー件数条件を満たす商品を集める。 | 取得完了後、まとめて行追加する。Sheets OFF時は自動コピーする。 |
| `現在ページをAI用取得` | Amazonの商品詳細ページ | 商品詳細ページから記事作成やAI整形に使う長い説明テキスト、特徴、メーカー説明、商品説明を取得する。 | 1商品につき1行。A-I列に基本情報、J列に種別、T-V列に商品情報1-3を入れる。複数タブ対応。 |
| `全タブページをAI用取得` | 同一Chromeウィンドウ内で開いている複数の商品詳細ページ | 各商品詳細タブからタイトルとアフィリエイトURLを取得する。現在はAI詳細本文ではなく、全タブのリンク取得用途として動作する。 | 商品詳細タブ1件につき1行。 |
| `クーポン取得(グリッド)` | Amazonのクーポン/セール系グリッドページ | 商品名、価格、クーポン情報、アフィリエイトURLを取得する。 | 商品1件につき1行。クーポン情報は製品名列に入れる。複数タブ対応。 |
| `ブランド個別ページ` | ブランドストアやブランドのセール/商品グリッドページ | 表示中の商品カードから、商品名、価格、参考価格、割引/クーポン、URLを取得する。 | 商品1件につき1行。割引/クーポンは製品名列に入れる。複数タブ対応。 |
| `ふるさと納税取得用` | Amazonふるさと納税系の特殊グリッドページ | 自治体名と価格らしきテキスト、商品URLを取得し、アフィリエイトタグを付与する。 | 商品1件につき1行。複数タブ対応。 |

### Sheetsに書き込まれる基本列

基本列は次の順序で使う。

```text
カテゴリ	タイトル	Amazon URL	ブランド	製品名	価格	参考価格	レビュー平均	レビュー数	種別
```

AI用取得では、さらに後方列に `商品情報1`、`商品情報2`、`商品情報3` を追加して書き込む。拡張側はヘッダーがない場合に自動でヘッダーを作り、不足列がある場合はヘッダーを補完する。

### 使うページの選び方

- 商品詳細ページを1つずつスプレッドシートへ入れたい場合は、`個別商品ページ` を使う。
- 複数の商品詳細タブを開いてまとめて入れたい場合は、`個別商品ページ` と `その他タブで表示中すべて` を使う。
- 検索結果やランキングの表示中の商品だけを入れたい場合は、`現在ページ取得` を使う。
- ページ送りしながら条件に合う商品を集めたい場合は、`標準スクレイプ` を使う。
- 記事生成やAI整形に使う素材を商品詳細から取りたい場合は、`現在ページをAI用取得` を使う。
- クーポン/セール情報を記事素材にしたい場合は、`クーポン取得(グリッド)` または `ブランド個別ページ` を使う。

作成日: 2026-05-01

対象ディレクトリ:

- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\Amacon_extention`

主な対象ファイル:

- `manifest.json`
- `popup.html`
- `popup.js`
- `sheets-api.js`
- `background.js`

## 1. 拡張機能の目的

この Chrome 拡張は、Amazon.co.jp の商品一覧ページ、商品詳細ページ、ブランドページ、クーポンページなどを開いた状態で、ページ内 DOM から商品情報を抽出し、クリップボードコピー、Google Sheets 書き込み、または Blog Vercel の GitHub Actions 起動へつなげるためのツールである。

重要な前提:

- Amazon のページをサーバー側や GitHub Actions 側で再取得するのではなく、ユーザーが Chrome で実際に開いているページから情報を抜く。
- Actions ランナーから Amazon 商品詳細 HTML を直接取ると captcha / robot check になりやすい。
- したがって、商品詳細を記事生成に使う場合は、Chrome 拡張で取得した `source_payloads` を渡す経路が重要。

## 2. 権限と対応サイト

`manifest.json` の現在仕様:

- Manifest V3
- 拡張名: `Amazon Product Scraper`
- version: `11.1`
- permissions:
  - `storage`
  - `activeTab`
  - `tabs`
  - `scripting`
  - `clipboardWrite`
  - `identity`
- host_permissions:
  - `https://www.amazon.co.jp/*`
  - `https://www.amazon.com/*`
  - `https://amzn.asia/*`
  - `https://amzn.to/*`
  - `https://blog-vercel-dun.vercel.app/*`
  - `https://sheets.googleapis.com/*`
  - `https://www.googleapis.com/*`

実際の抽出ロジックはほぼ Amazon.co.jp 前提で、生成する affiliate URL も基本的に `https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}` 形式である。

## 3. UI 構成

ポップアップの主要 UI:

- モード選択
- 整列順序
- ページ詳細取得
- 記事作成
- 取得商品数
- レビュー件数
- レビュー平均点
- Sheets 書き込み toggle
- 実行
- コピー
- 停止
- プロンプト管理
- アフィリエイトリンク作成
- 全タブのアフィリエイトリンク一括取得
- 設定パネル

設定として保存される主な値:

- `affiliateTag`
- `itemCount`
- `minRating`
- `minReviews`
- `sortOrder`
- `mode`
- Google Sheets 関連設定
- 保存済みプロンプト

## 4. モード一覧

UI 上のモード:

| モード値 | 表示名 | 主用途 |
|---|---|---|
| `standard` | 標準スクレイプ | 検索結果・ランキング・商品グリッドから複数商品を取得 |
| `currentPage` | 現在ページ取得 | UI 上は存在するが、現状は専用分岐なし |
| `currentPageAI` | 現在ページをAI用取得 | Amazon 商品詳細ページから AI 整形用の詳細テキストを取得 |
| `allTabsAI` | 全タブページをAI用取得 | 実装上は全タブの商品タイトルと affiliate URL の一括取得 |
| `coupon` | クーポン取得(グリッド) | Amazon クーポン/セール系グリッドから商品とクーポン情報を取得 |
| `brand` | ブランド個別ページ | ブランドページや特殊グリッドから商品を手動追記しながら取得 |
| `furusato` | ふるさと納税取得用 | ふるさと納税系の特殊グリッドから商品名とURLを取得 |

## 5. 標準スクレイプ

対象ページ:

- Amazon 検索結果ページ
- カテゴリ一覧ページ
- ランキング系ページ
- 一部のグリッドページ
- `div[data-component-type="s-search-result"]` を含むページ
- `.ProductGridItem__itemOuter__KUtvv`
- `.GridItem-module__container_PW2gdkwTj1GQzdwJjejN`
- `.ProductUIRender__grid-item-v2__Ipp8M`
- `.a-carousel-card`

実行方法:

1. Amazon の検索結果や商品一覧ページを開く。
2. モードを `標準スクレイプ` にする。
3. 取得商品数、レビュー件数、整列順序を設定する。
4. `実行` を押す。

取得する項目:

- カテゴリ
- 商品名
- Amazon affiliate URL
- 価格
- 参考価格
- レビュー平均
- レビュー数

除外/条件:

- スポンサー商品らしき要素は除外する。
- ASIN が取れない商品は除外する。
- 価格が取れない商品は除外する。
- レビュー件数が `minReviews` 未満の商品は除外する。
- `minRating` は UI にあるが、現状の標準スクレイプの主要フィルタではレビュー件数のほうが使われている。

動作:

- ページ下部へスクロールする。
- 表示中の商品を抽出する。
- 目標件数に達するまで次ページボタンを押して進む。
- 完了時に TSV をクリップボードへ自動コピーする。
- `コピー` ボタンから再コピーまたは Sheets 書き込みができる。

出力形式:

```text
カテゴリ	タイトル	Amazon URL	ブランド	製品名	価格	参考価格	レビュー平均	レビュー数
```

## 6. 現在ページ取得

表示名:

- `現在ページ取得`

現状:

- UI には存在する。
- `popup.js` の実行分岐では `currentPage` 専用処理が見当たらない。
- そのため、実行時は標準スクレイプ側の処理へ流れる。

注意:

- 「今開いている商品詳細ページを詳細取得する」用途では `現在ページをAI用取得` を使う。
- `現在ページ取得` は今後の拡張用ラベル、または旧仕様の名残として扱うのが安全。

## 7. 現在ページをAI用取得

対象ページ:

- Amazon 商品詳細ページ
- URL に `/dp/{ASIN}` を含むページ
- `#productTitle` や `input[name="ASIN"]` が存在する商品ページ

用途:

- 1つの商品詳細ページを、AI に渡しやすい形で取得する。
- 商品説明や A+ Content を含めて、記事生成や比較レビュー用の素材にする。
- プロンプト管理で保存したプロンプトと組み合わせ、コピーした TSV/テキストを AI に貼って整形する運用を想定。

取得する基本項目:

- 商品タイトル
- affiliate URL
- 価格
- 参考価格
- レビュー平均
- レビュー数

取得する AI 用テキスト:

- `text1`: 「この商品について」相当
  - `#feature-bullets`
  - `#feature-bullets-btf`
  - 箇条書きの商品特徴
- `text2`: メーカー説明 + 商品情報
  - A+ Content
  - brand story
  - `#productDetails_feature_div`
  - 商品詳細テーブル
  - 重複テキスト除去あり
- `text3`: 商品説明
  - `#productDescription`
  - 取れない場合は A+ Content から代替

出力:

- Sheets 書き込みが OFF の場合は、1行 TSV としてクリップボードへコピーする。
- Sheets 書き込みが ON の場合は、Google Sheets へ1行追加する。

実装上の行構造:

```text
カテゴリ	タイトル	Amazon URL	ブランド	製品名	価格	参考価格	レビュー平均	レビュー数	単品	...	商品情報1	商品情報2	商品情報3
```

適しているページ:

- 通常の Amazon 商品詳細ページ
- A+ Content が本文 DOM に展開されているページ
- 商品説明や商品詳細テーブルが表示されているページ

不得意なページ:

- captcha / robot check ページ
- Amazon アプリ誘導やログイン要求ページ
- 商品情報が動的に未展開のページ
- A+ Content が画像だけで、テキスト DOM が少ないページ
- 画像内テキスト中心の商品ページ

## 8. 全タブページをAI用取得

表示名:

- `全タブページをAI用取得`

現状の実装:

- 名前は AI 用取得だが、実際には全タブの Amazon 商品詳細ページから「商品タイトル」と「affiliate URL」を取得してコピーする。
- 詳細テキストや A+ Content は取得しない。

対象ページ:

- 同じ Chrome ウィンドウ内で開いている Amazon.co.jp 商品詳細タブ
- URL に `amazon.co.jp/` と `/dp/` を含むページ

スキップされるページ:

- `chrome://`
- `chrome-extension://`
- `about:`
- Amazon 商品詳細ではないページ
- `/dp/` を含まないページ

出力:

```text
商品タイトル

https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}

商品タイトル

https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}
```

用途:

- 複数の商品詳細タブを開いておき、まとめて affiliate link リストを作る。
- 記事末尾の商品リストや比較候補リストを作る。

## 9. クーポン取得(グリッド)

対象ページ:

- Amazon のクーポン/セール系グリッドページ
- `.GridItem-module__container_PW2gdkwTj1GQzdwJjejN` を含むページ
- `.ProductCard-module__card_uyr_Jh7WpSkPx4iEpn4w` を含むページ

取得する項目:

- 商品名
- クーポン情報
- 価格
- affiliate URL

出力形式:

```text
商品名
価格:{価格}⇛{クーポン情報}
https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}
```

特徴:

- Apple, Anker, DJI, Bose, Shure, Sony などの優先ブランド順で並び替える。
- ページ上に独自のコピー UI を出す。
- `実行` 後、ページ右下の「クリップボードにコピー」からコピーする。

注意:

- Amazon 側のクーポンページ DOM class に強く依存する。
- class 名が変わると取得できない。

## 10. ブランド個別ページ

対象ページ:

- Amazon ブランドページ
- ブランドストア内の商品グリッド
- 検索結果とは違う特殊な商品カードページ
- `.ProductGridItem__itemOuter__KUtvv`
- `.GridItem-module__container_PW2gdkwTj1GQzdwJjejN`
- `.ProductUIRender__grid-item-v2__Ipp8M`
- `div[data-component-type="s-search-result"]`
- `.a-carousel-card`

使い方:

1. ブランドページを開く。
2. モードを `ブランド個別ページ` にする。
3. `実行` を押す。
4. ページ右下に専用 UI が出る。
5. ページをスクロールする。
6. `取得&追記` を押す。
7. 必要なだけ繰り返す。
8. `全件コピー` を押す。

取得する項目:

- 商品名
- 割引/クーポン情報
- 価格
- 参考価格
- affiliate URL

出力形式:

```text
商品名
価格:【割引/クーポン情報】{価格} ←{参考価格}(参考価格)
https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}
```

特徴:

- 自動ページ送りではなく、ユーザーがスクロールしてから `取得&追記` する。
- 取得済み ASIN は重複除外される。
- `リセット` で取得済みリストを消せる。

適しているページ:

- 商品カードが無限スクロール的に増えるブランドページ
- 検索結果ページより DOM が特殊なページ
- セール/ブランドストアの横断取得

## 11. ふるさと納税取得用

対象ページ:

- Amazon ふるさと納税系の特殊グリッド
- `div[data-cel-widget^="acsux-widgets_content-grid_row"]` を含むページ

取得する項目:

- 自治体名らしきテキスト
- 価格らしきテキスト
- 商品 URL
- affiliate tag 付き URL

出力形式:

```text
自治体名 価格
https://...
```

注意:

- Amazon の通常検索結果ではなく、特定の content grid 構造に依存する。
- 画像が `1x1_blank.png` のカードは除外される。
- `取得商品数` が最大件数として使われる。

## 12. 記事作成ボタン

`記事作成` は、Amazon 商品詳細ページの内容を Chrome 側で抽出し、Blog Vercel の `/api/trigger` を通じて GitHub Actions を起動する。

対象ページ:

- 現在表示中の Amazon 商品詳細ページ
- または同じウィンドウ内の Amazon 商品詳細タブ全部

ページ詳細取得:

- `今表示しているページ`
  - アクティブタブのみ対象
- `その他タブで表示中すべて`
  - 現在の Chrome ウィンドウ内の Amazon 商品詳細タブを対象

商品詳細ページ判定:

- `amzn.asia/`
- `amzn.to/`
- `amazon.` かつ `/dp/`
- `amazon.` かつ `/gp/product/`
- `amazon.` かつ `/gp/aw/d/{ASIN}`
- URL query に `asin={ASIN}`

抽出 payload:

- source
- capturedAt
- url
- canonicalUrl
- asin
- title
- pageTitle
- brand
- price
- listPrice
- rating
- reviewCount
- availability
- seller
- categories
- featureBullets
- description
- aplusLines
- carouselTexts
- imageAlts
- ocrTexts
- ocrStatus
- productOverview
- detailBullets
- importantInformation
- highResolutionImages
- extractionError

送信先:

- `https://blog-vercel-dun.vercel.app/api/trigger`

送信内容:

- `mode: single`
- `source_type: amazon`
- `source_urls`
- `source_payloads`
- `status: 単品`
- `request_id: amazon-{timestamp}-{random}`

重要:

- `source_payloads` が入っていれば、Actions 側は Chrome 抽出済み情報から記事生成素材を組み立てられる。
- `source_payloads` が空で URL だけの場合、Actions 側で Amazon HTML を取りに行き captcha で失敗しやすい。
- URL 入力だけで Blog Vercel サイトから起動する経路は、詳細取得の成功経路としては扱わない。

## 13. プロンプト管理

プロンプト管理は、AI に貼るプロンプトを拡張機能内に保存・選択・コピーする機能である。

できること:

- プロンプトタイトルを付けて保存
- 保存済みプロンプトの一覧表示
- 選択したプロンプトを自動でクリップボードへコピー
- 手動コピー
- 削除

保存場所:

- `chrome.storage.sync`
- key: `prompts`

保存形式:

```json
{
  "タイトル": {
    "content": "プロンプト本文",
    "updatedAt": "ISO日時"
  }
}
```

想定する使い方:

1. `現在ページをAI用取得` で商品詳細の TSV をコピーする。
2. プロンプト管理で用途別プロンプトをコピーする。
3. AI チャットへプロンプトと商品情報を貼り付ける。
4. レビュー記事、比較表、商品紹介文などに整形する。

プロンプトで整形しやすいページ:

- Amazon 商品詳細ページ
- 商品特徴、A+ Content、商品説明、商品詳細テーブルが DOM テキストとして存在するページ
- 商品名、価格、レビュー数が見えているページ

プロンプトで整形しにくいページ:

- 検索結果ページ
  - 標準スクレイプで表形式の商品リストは作れるが、個別商品の深い説明は取れない。
- クーポンページ
  - 商品名、価格、クーポン情報中心で、詳細レビュー素材には向かない。
- ブランドページ
  - 複数商品リスト向きで、個別商品の A+ Content までは取らない。
- 画像内説明が中心の商品ページ
  - DOM テキストが少ないため、AI 用の本文素材が薄くなる。

## 14. アフィリエイトリンク作成

単一リンク作成:

- ヘッダーのアフィリエイトリンク作成ボタンから実行する。
- 現在の Amazon 商品詳細ページからタイトルと ASIN を取得する。
- `タイトル\naffiliate URL` をクリップボードへコピーする。

全タブ一括リンク作成:

- ヘッダーの全タブリンクボタンから実行する。
- 現在の Chrome ウィンドウ内で開いている Amazon.co.jp `/dp/` ページを対象にする。
- 各タブからタイトルと ASIN を取得する。
- タイトルと affiliate URL のリストをコピーする。

出力:

```text
商品タイトル

https://www.amazon.co.jp/dp/{ASIN}/ref=nosim?tag={affiliateTag}
```

## 15. Google Sheets 連携

Google Sheets 連携は `sheets-api.js` が担当する。

設定項目:

- Google Client ID
- Google Client Secret
- スプレッドシート URL
- シート名
- Sheets 書き込み toggle

認証:

- Chrome Identity API の `chrome.identity.getAuthToken({ interactive: true })` を使う。
- token と期限を `chrome.storage.sync` に保存する。

書き込み:

- `appendData(data)` で Google Sheets API の values append を呼ぶ。
- 初回はヘッダー行を確認し、なければ追加する。
- range は `'シート名'!A:J`。

既定ヘッダー:

```text
カテゴリ	タイトル	Amazon URL	ブランド	製品名	価格	参考価格	レビュー平均	レビュー数	HTML
```

注意:

- `現在ページをAI用取得` は実装上、J列以降にも AI 用テキストを含む長い row を渡している。
- `sheets-api.js` 側の range は `A:J` のため、Google Sheets API 側の挙動確認が必要。
- 長文テキストは最大 50000 文字で切り詰められる。

## 16. Google Spreadsheet 連携マニュアル

この章は、Amazon Product Scraper で取得した商品情報を Google Spreadsheet に直接追記するための手順である。

### 16.1 連携でできること

Sheets 書き込みを ON にすると、`コピー` ボタンや `現在ページをAI用取得` の実行結果をクリップボードではなく Google Spreadsheet に追記できる。

主な書き込み対象:

- `標準スクレイプ` で取得した商品一覧
- `現在ページをAI用取得` で取得した単品商品情報
- `コピー` ボタン経由で `chrome.storage.local.scrapedProducts` に残っている商品一覧

### 16.2 事前に必要なもの

必要なもの:

- Google アカウント
- 書き込み先の Google Spreadsheet
- Chrome 拡張に設定する Google OAuth Client ID
- Google Sheets API が有効な Google Cloud プロジェクト

拡張機能側の `manifest.json` には、現在次の OAuth scope が入っている。

```json
"oauth2": {
  "client_id": "1065795462491-9qso4mganv3rfjv08k8g2bqcuk56i98h.apps.googleusercontent.com",
  "scopes": [
    "https://www.googleapis.com/auth/spreadsheets"
  ]
}
```

ただし、ポップアップ UI にも `Google Client ID` / `Google Client Secret` 入力欄がある。現在の認証処理は `chrome.identity.getAuthToken()` を使うため、実際の OAuth client は Chrome 拡張の manifest 側設定と Chrome Identity API の設定に依存する。

### 16.3 Spreadsheet を用意する

1. Google Spreadsheet を新規作成する。
2. 任意のシート名を決める。
3. 既定では `ブランド製品名仕訳` が使われる。
4. 共有設定は、自分の Google アカウントで編集できる状態にする。
5. Spreadsheet の URL をコピーする。

URL 例:

```text
https://docs.google.com/spreadsheets/d/XXXXXXXXXXXXXXXXXXXXXXXXXXXX/edit
```

拡張機能はこの URL から `/spreadsheets/d/{spreadsheetId}` の `{spreadsheetId}` を抽出する。

### 16.4 Google Cloud 側の準備

初回セットアップで必要な作業:

1. Google Cloud Console を開く。
2. 対象プロジェクトを作成または選択する。
3. Google Sheets API を有効化する。
4. OAuth 同意画面を設定する。
5. Chrome 拡張用の OAuth Client ID を作成する。
6. 作成した Client ID を拡張機能の manifest または UI 設定に反映する。

注意:

- Chrome 拡張で `chrome.identity.getAuthToken()` を使う場合、通常の Web アプリ OAuth とは設定が異なる。
- Chrome Web Store に公開していないローカル拡張では、拡張機能 ID が変わると OAuth 設定も合わなくなることがある。
- OAuth 設定が合っていない場合、`Google認証` ボタンで認証に失敗する。

### 16.5 拡張機能側の設定手順

1. Chrome で Amazon Product Scraper のポップアップを開く。
2. 歯車ボタンを押して設定パネルを開く。
3. `Google Client ID` に OAuth Client ID を入力する。
4. `Google Client Secret` に Client Secret を入力する。
5. `スプレッドシートURL` に書き込み先 Spreadsheet の URL を入力する。
6. `シート名` に書き込み先シート名を入力する。
7. `Google認証` を押す。
8. Google の認証画面が出たら、Spreadsheet に書き込む Google アカウントで許可する。
9. 認証状態が `認証済み` になれば準備完了。
10. メイン画面で `Sheets書き込み` toggle を ON にする。

設定値は `chrome.storage.sync` に保存される。

保存される主な key:

- `sheetsToggle`
- `sheetsClientId`
- `sheetsClientSecret`
- `spreadsheetUrl`
- `sheetName`
- `sheetsAccessToken`
- `sheetsTokenExpiry`

### 16.6 書き込みの使い方

標準スクレイプで書き込む手順:

1. Amazon 検索結果やランキングページを開く。
2. モードを `標準スクレイプ` にする。
3. `取得商品数` と `レビュー件数` を設定する。
4. `実行` を押して商品を取得する。
5. `Sheets書き込み` を ON にする。
6. `コピー` ボタンを押す。
7. クリップボードではなく Spreadsheet に追記される。

現在ページをAI用取得で書き込む手順:

1. Amazon 商品詳細ページを開く。
2. モードを `現在ページをAI用取得` にする。
3. `Sheets書き込み` を ON にする。
4. `実行` を押す。
5. 商品タイトル、価格、レビュー、AI 用テキストが Spreadsheet に追記される。

### 16.7 書き込まれる列

通常の商品一覧では、次の列を使う。

```text
A: カテゴリ
B: タイトル
C: Amazon URL
D: ブランド
E: 製品名
F: 価格
G: 参考価格
H: レビュー平均
I: レビュー数
J: HTML
```

`sheets-api.js` はヘッダーがない場合、次のヘッダーを自動追加する。

```text
カテゴリ	タイトル	Amazon URL	ブランド	製品名	価格	参考価格	レビュー平均	レビュー数	HTML
```

`現在ページをAI用取得` では、実装上 J 列以降に `単品` や AI 用テキストを含む長い行を渡している。運用上は、Spreadsheet 側で K 列以降を次のように使う想定にすると管理しやすい。

```text
J: 種別
T: 商品情報1
U: 商品情報2
V: 商品情報3
```

ただし、現在のヘッダーは A:J までなので、AI 用列を本格運用する場合はヘッダーを増やすか、`sheets-api.js` のヘッダー定義を更新するのが望ましい。

### 16.8 認証の更新

アクセストークンは `sheetsTokenExpiry` として、おおむね 1 時間後の期限で保存される。

期限切れ時:

- `getAccessToken()` が保存済み token の期限を確認する。
- 期限切れなら `authenticate()` を再実行する。
- 再認証が必要な場合、Google 認証画面が出ることがある。

認証がおかしい場合:

1. 設定パネルで `Google認証` を押し直す。
2. Spreadsheet URL とシート名を確認する。
3. Google Cloud 側で Sheets API が有効か確認する。
4. OAuth Client ID と拡張機能 ID の対応を確認する。

### 16.9 よくある失敗

`アクセスをブロック: AMZN_chrome_extention は Google の審査プロセスを完了していません`

- エラー例:

```text
Google でログイン
アクセスをブロック: AMZN_chrome_extention は Google の審査プロセスを完了していません

AMZN_chrome_extention は Google の審査プロセスを完了していません。
このアプリは現在テスト中で、デベロッパーに承認されたテスターのみがアクセスできます。
エラー 403: access_denied
```

- 原因:
  - Google Cloud の OAuth consent screen が `Testing` のまま。
  - ログインしようとしている Google アカウントが Test users に追加されていない。
  - 今回の例では `seahirodigital1@gmail.com` がテスターに入っていない可能性が高い。

- 最短の解決:
  1. Google Cloud Console を開く。
  2. 対象プロジェクトを選択する。
  3. `APIs & Services` を開く。
  4. `OAuth consent screen` を開く。
  5. `Audience` または `Test users` の設定を開く。
  6. Test users に `seahirodigital1@gmail.com` を追加する。
  7. 保存する。
  8. Chrome 拡張の `Google認証` をもう一度押す。

- 代替の解決:
  - OAuth app を Production に公開する。
  - ただし、Google Sheets の scope は sensitive scope 扱いになるため、外部ユーザー向けに広く使う場合は Google の verification が必要になる可能性がある。
  - 個人利用や開発中なら、Production 公開より Test users に自分の Google アカウントを追加する方が早い。

- それでも直らない場合:
  - ログインしている Google アカウントが本当に `seahirodigital1@gmail.com` か確認する。
  - Chrome の複数プロファイルで別アカウントになっていないか確認する。
  - OAuth consent screen の User type が External の場合、Test users に明示追加されているか確認する。
  - 拡張機能 ID が変わっている場合、Google Cloud 側の Chrome extension OAuth client と一致しているか確認する。
  - 一度 Chrome の拡張認証 token を消すか、拡張を再読み込みして認証し直す。

`Client IDが設定されていません`

- 設定パネルの `Google Client ID` が空。
- Client ID を入力して再度 `Google認証` を押す。

`スプレッドシートURLが無効です`

- URL に `/spreadsheets/d/{id}` が含まれていない。
- Google Spreadsheet の通常 URL を貼る。

`API Error (403)`

- Google Sheets API が有効ではない。
- OAuth scope が不足している。
- 認証した Google アカウントに Spreadsheet の編集権限がない。

`API Error (404)`

- Spreadsheet ID が間違っている。
- Spreadsheet が削除されている。
- 認証したアカウントから見えない。

`ヘッダー追加に失敗しました`

- シート名が間違っている。
- シートが存在しない。
- シート名に余分な空白がある。

`Sheets書き込み失敗`

- token 期限切れ、権限不足、Spreadsheet URL 不正、シート名不一致のいずれかを疑う。
- DevTools console に `Sheets API URL` と API error response が出る。

### 16.10 運用上の注意

- `Sheets書き込み` が OFF のときは、取得結果はクリップボードにコピーされる。
- `Sheets書き込み` が ON のときは、`コピー` ボタンが Spreadsheet 追記として動く。
- 標準スクレイプ完了時の自動コピーは、Sheets 書き込みとは別経路でクリップボードへコピーする。
- Sheets に書き込みたい場合は、取得後に `コピー` ボタンを押す運用が確実。
- `現在ページをAI用取得` は実行時に Sheets toggle を見て、ON なら直接 Sheets に書く。
- 長文の AI 用テキストは 50000 文字で切り詰める。
- Google Sheets 側の 1 セル文字数制限にも注意する。

## 17. コピーとストレージ

コピー方式:

- `navigator.clipboard.writeText`
- 失敗時は `textarea` + `document.execCommand('copy')` fallback

一時保存:

- 抽出結果は主に `chrome.storage.local` に保存される。
- UI 設定やプロンプトは `chrome.storage.sync` に保存される。

主な local storage:

- `scrapedProducts`
- `currentCategory`
- `isScraping`
- `status`
- `sortOrder`
- `mode`
- `shouldStop`

## 18. 停止

`停止` ボタンは `chrome.storage.local.shouldStop = true` を立てる。

標準スクレイプの自動ループは各ページ処理の合間に `shouldStop` を確認し、停止する。

注意:

- すでにページ内へ注入されたスクリプトを即時 kill するものではない。
- 標準スクレイプ以外の一部モードでは、停止ボタンの効き方は限定的。

## 19. 現在の制約

- Amazon 側 DOM class に依存するため、Amazon の UI 変更で壊れる可能性が高い。
- 商品詳細の深い取得は、Chrome で実際に表示できているページが前提。
- URL だけを Actions に渡しても、Actions 側で Amazon 詳細 HTML を安定取得することは期待できない。
- captcha / robot check / ログイン要求 / 年齢確認 / 配送先モーダルなどが出ている場合、抽出が失敗または薄くなる。
- A+ Content が画像だけの場合、プロンプト整形用の本文素材は不足する。
- `currentPage` はUIにあるが専用実装がない。
- `allTabsAI` は名前に反して、現在は詳細AI素材ではなく affiliate link 一括取得である。

## 20. 推奨運用

商品詳細から記事を作る場合:

1. Amazon 商品詳細ページを Chrome で開く。
2. ページが captcha ではなく、商品情報が表示されていることを確認する。
3. 1商品だけなら `現在ページをAI用取得` で素材をコピーする。
4. Actions でブログ生成まで進めたい場合は、`記事作成` を使って Chrome payload を送る。
5. Blog Vercel サイト内の URL 入力だけで起動する経路は避ける。

複数商品の比較リストを作る場合:

1. Amazon 検索結果やカテゴリページを開く。
2. `標準スクレイプ` で取得する。
3. 必要ならレビュー件数や取得件数を調整する。
4. コピーまたは Sheets 書き込みを使う。

セール/クーポン記事を作る場合:

1. クーポンページやブランドセールページを開く。
2. ページ構造に応じて `クーポン取得(グリッド)` または `ブランド個別ページ` を使う。
3. 出力された商品名、価格、クーポン、URLを記事素材にする。

AI で整形する場合:

1. プロンプト管理に用途別プロンプトを保存する。
2. 商品詳細ページで `現在ページをAI用取得` を実行する。
3. 保存済みプロンプトをコピーする。
4. AI にプロンプトと取得 TSV を渡して、レビュー文、比較表、メリット/デメリット、購入導線へ整形する。

## 21. 今後直すとよい点

- `currentPage` の専用実装を追加するか、UI から削除する。
- `allTabsAI` の名称を実態に合わせて「全タブリンク取得」に変える。
- `現在ページをAI用取得` の Sheets 書き込み列数と `sheets-api.js` の range/header を整合させる。
- `記事作成` で `source_payloads` が空になるケースを UI 側で明示エラーにする。
- Blog Vercel サイト側の URL-only 起動には「Amazon 詳細取得不可」の注意を出す。
- 抽出 payload の preview / debug 表示を追加し、Actions に何が渡ったかを確認しやすくする。
