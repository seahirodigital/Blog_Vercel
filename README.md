# Vibe Blog Engine — 仕様書

YouTube動画からAIでブログ記事を自動生成し、OneDriveで管理・編集・note.comへ自動下書き投稿するフルスタック・オートメーション・システム。

---

## 1. システム全体像

```
YouTube動画URL
    ↓ Apify（文字起こし）
    ↓ Gemini 2.5 Flash（3段階AI生成）
    ↓ OneDrive（Markdownファイル保存）
    ↓ Vibe Blog UI（閲覧・編集・管理）
    ↓ GitHub Actions（note下書き自動投稿）
    ↓ note.com（下書き記事）
```

**コンポーネント構成:**

| レイヤー | 場所 | 役割 |
|---------|------|------|
| パイプライン | `scripts/pipeline/` + GitHub Actions | 記事自動生成・OneDrive保存 |
| API | `api/` | Vercel Serverless Functions（OneDrive/GitHub/note連携） |
| フロントエンド | `public/index.html` | 記事管理・編集・note投稿管理画面 |

---

## 2. 記事生成パイプライン

### 2.1 実行トリガー

- **自動**: 毎日 JST 9:00（UTC 0:00）スケジュール実行
- **手動**: Vibe Blog UI の「パイプライン実行」ボタン、または GitHub Actions UI

### 2.2 Googleスプレッドシート読み込み

- **認証**: `GOOGLE_SERVICE_ACCOUNT_JSON` サービスアカウント
- **対象シート**: `SHEET_NAME`（デフォルト: "動画リスト"）
- **処理対象の条件**: 「状況」列が `単品` / `複数` / `情報` のいずれか、かつ「動画URL」列に値がある行
- **完了時**: 処理成功行の「状況」を `完了` に自動更新

### 2.3 1本あたりの処理フロー（5ステップ）

```
Step 1: 文字起こし取得（Apify）
Step 2: AI 3段階生成（Gemini 2.5 Flash）
Step 3: アフィリエイトリンク自動挿入
Step 4: OneDrive保存
Step 5: スプレッドシートのステータス更新
```

#### Step 1 — 文字起こし取得

- `modules/apify_fetcher.py` が Apify API 経由で YouTube の文字起こしと動画タイトルを取得

#### Step 2 — AI 3段階生成（Gemini 2.5 Flash）

プロンプトは `scripts/pipeline/prompts/` から読み込み。

| フェーズ | プロンプトファイル | 役割 |
|---------|-----------------|------|
| Drafter | `01-writer-prompt.txt` | 状況（単品/情報/複数）でプロンプトを切り替えて初稿を生成 |
| Editor | `02-editor-prompt.txt` | 文章リズム・SEOキーワード・モバイル最適化 |
| Director | `03-director-prompt.txt` | 最終トーン調整・YAMLメタ・画像挿入指示 |

Gemini Interaction Hub（`previous_interaction_id`）でコンテキストを連鎖させて生成。レート制限時は最大3回リトライ（30秒/60秒/90秒待機）。

#### Step 3 — アフィリエイトリンク自動挿入

`scripts/pipeline/prompts/04-affiliate-link-manager/insert_affiliate_links.py` を動的ロードして実行。

- **リンクソース**: OneDrive上の `affiliate_links.txt`（`===MEMO1===` セクション内の `▼` ブロック形式）を毎回直接取得

**挿入ルール（スクリプト自動）:**

| 挿入位置 | 挿入内容 | 備考 |
|---------|---------|------|
| H2「結論」の直前 | MEMO1全文 ＋ Amazonアソシエイト免責事項 | 固定位置 |
| 奇数番目H2（3,5,7...）の直前 | ▼ブロックを1つランダム選択（重複なし） | 1番目はスキップ |
| 記事末尾 | MEMO1全文 | 常に付与 |

> **免責事項**（最初の挿入位置のみ1回付与）:  
> `(Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。)`

**挿入ルール（UIボタン手動）:**

| 挿入位置 | 挿入内容 | 担当 |
|---------|---------|------|
| 偶数番目H2（2,4,6...）の直前 | クリップボードの内容 | 🔗 リンク挿入ボタン（3.2節参照） |

> スクリプトが奇数H2を担当し、UIボタンが偶数H2を担当することで、**全ての章間に必ずアフィリエイトリンクが配置**される。

- スクリプト未検出 or エラー時は**スキップして処理続行**（記事生成は止まらない）
- OneDrive取得失敗時はスクリプトと同階層のローカルファイルにフォールバック

#### Step 4 — OneDrive保存

- `modules/onedrive_sync.py` が Microsoft Graph API 経由でアップロード
- **フォルダ**: `ONEDRIVE_FOLDER`（デフォルト: "Blog_Articles"）
- **ファイル名**: `YYYYMMDD_HHMM_動画タイトル.md`

#### Step 5 — スプレッドシート更新

- 保存成功後、対象行の「状況」を `完了` に更新（`modules/sheets_reader.py`）

### 2.4 note下書き自動投稿（別ワークフロー）

記事生成パイプラインとは独立した別ワークフロー（`note-draft.yml`）。詳細は [セクション4](#4-note下書き自動投稿システム) を参照。

`scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py` が以下を実行:
1. Cookie復元 → セッション検証 → 必要に応じてAPIログイン
2. `POST /api/v1/text_notes` でスケルトン作成
3. `POST /api/v1/text_notes/draft_save` で本文保存
4. GitHub Repository Variable に下書きURLを記録

---

## 3. 管理画面（Vibe Blog UI）

`public/index.html` — React + Tailwind CSS（CDN）でシングルファイル実装。

---

### 3.1 サイドバー（記事一覧）

OneDriveのフォルダ階層を**多段階ツリー**で表示。横幅ドラッグリサイズ・開閉トグル対応。モバイルではドロワー形式で表示。

#### フォルダツリー

- OneDriveの実際のフォルダ構造を最大5階層まで再帰表示
- 各フォルダはクリックで開閉（初期状態は全トップレベルフォルダを展開）
- フォルダ横の数字バッジはサブフォルダ含む全記事数

#### 記事の右クリックメニュー

| 項目 | 動作 |
|------|------|
| 選択 | チェックボックス選択モードを開始し、この記事を最初の選択状態にする |
| 複製 | 記事をコピー（ファイル名先頭に「コピー_」付与） |
| 削除 | 確認ダイアログ後にOneDriveから削除 |
| OneDriveで開く | OneDrive Webブラウザ画面で直接開く |
| エクスプローラーで表示 | ローカルのExplorer/Finderでファイルを選択表示（要 `LOCAL_ARTICLES_BASE` 環境変数） |

#### フォルダの右クリックメニュー

| 項目 | 動作 |
|------|------|
| サイドバーから非表示 | そのフォルダをサイドバー表示から除外する（ファイル削除ではない） |

#### ドラッグ&ドロップでの記事移動

- 記事をドラッグしてフォルダヘッダーへドロップ → OneDrive上でファイルを移動
- ドロップ可能フォルダは紫の破線アウトラインで強調表示
- **複数選択してから一括ドラッグ**も可能（後述）

#### Ctrl/Shift クリックによる複数選択（フォルダ移動専用）

| 操作 | 動作 |
|------|------|
| `Ctrl` / `Cmd` + クリック | 個別にトグル選択（紫アウトラインでハイライト） |
| `Shift` + クリック | 最後にクリックした記事から現在の記事まで範囲選択 |
| 修飾キーなしクリック | 複数選択を解除して通常選択に戻る |
| `Esc` | 複数選択を解除 |
| 複数選択中にドラッグ | 選択中の全記事を一括でフォルダ移動 |

> **note下書き投稿の複数選択とは別機能。**  
> フォルダ移動用の複数選択は `Ctrl/Cmd/Shift` クリック。  
> note下書き一括投稿用の選択は右クリック→「選択」でチェックボックスモードを使う。

#### フォルダ管理（下部の「フォルダ管理」ボタン）

サイドバー下部に常駐するボタン。クリックするとフォルダピッカーパネルが上方に展開。

- 全フォルダを階層インデント付きで一覧表示
- チェックボックスをクリックで表示/非表示を切り替え
- 「すべて表示」ボタンで非表示を一括解除
- 非表示フォルダ数がバッジ（オレンジ）で常時表示
- 設定は `localStorage` に永続保存（`sb_hiddenFolders` キー）

#### note下書き投稿の複数選択モード

1. 記事を右クリック → 「選択」でチェックボックスモード開始
2. 記事タイトル左のチェックボックスをクリックして複数選択（薄紫ハイライト）
3. ツールバーの「下書き」ボタンが「下書き(N)」と件数表示に変化
4. 「解除」ボタンで選択モードをキャンセル

---

### 3.2 エディタ

- **左ペイン**: Markdownエディタ（JetBrains Monoフォント）
- **右ペイン**: リアルタイムMarkdownプレビュー（OGPカード展開対応）
- 両ペインの境界をドラッグでサイズ調整可能

#### エディタ ↔ プレビュー スクロール同期

- エディタをスクロール → プレビューが対応位置に自動追従
- プレビューをスクロール → エディタが対応位置に自動追従
- `marked.lexer()` によるトークン行番号マップ方式で、見出し以外の段落も精密に同期
- プレビューをダブルクリック → クリックした要素と**同じ高さ**にエディタの対応行を表示

#### OGPカード自動展開

プレビュー内のURL行（URLのみの段落）を自動でOGPカードに変換。

- Amazon商品URL（`amzn.to` 短縮URL含む）に対応
- エディタでURL行末に Enter を押すと即時フェッチ開始
- 「OGP更新」ボタンで失敗したリンクを再試行
- エディタ編集中もOGPカードは維持される（キャッシュ機構）

#### エディタバー（MARKDOWNラベルの行）

左から順に:

| 要素 | 説明 |
|------|------|
| 保存先URLリンク | note下書き保存完了後に `editor.note.com` のURLが自動表示 |
| ●（灰） / ✓（緑） | 自動保存ステータス（待機中 / 完了） |
| 文字数 | 現在の文字数をリアルタイム表示 |
| 🔗 リンク挿入ボタン | クリップボードの内容を偶数番目H2（2,4,6...）の直前に一括挿入 |
| コピーボタン | Markdown全文をクリップボードにコピー |

#### リンク挿入ボタン（🔗）の詳細

**目的**: アフィリエイトリンクのPythonスクリプト（`insert_affiliate_links.py`）が奇数番目H2（3,5,7...）に自動挿入するのと**対になるように**、偶数番目H2（2,4,6...）の直前にも手動でリンクを挿入する。これにより全ての章間にリンクが配置される。

**操作手順**:
1. アフィリエイトリンクモーダルから挿入したいリンクをコピー
2. エディタバーの 🔗 ボタンをクリック
3. 偶数番目H2（2番目・4番目・6番目...）の直前に一括挿入される

**挿入位置の対応関係**（H2見出し番号ベース）:

| H2番号 | 挿入担当 |
|--------|---------|
| 1番目 | なし（記事冒頭のリード文） |
| 2番目 | 🔗 リンク挿入ボタン（手動） |
| 3番目 | Pythonスクリプト（自動） |
| 4番目 | 🔗 リンク挿入ボタン（手動） |
| 5番目 | Pythonスクリプト（自動） |
| 6番目 | 🔗 リンク挿入ボタン（手動） |
| H2「結論」 | Pythonスクリプト（MEMO1全文） |
| 記事末尾 | Pythonスクリプト（MEMO1全文） |

#### Amazon検索フォーム（ヘッダー右）

- テキスト入力後 Enter または「Amazon」ボタンで `https://www.amazon.co.jp/s?k=キーワード` を新タブで開く

#### エディタバーのリンク（MARKDOWN ラベルの右隣）

**YouTube リンク（元動画）**
- 記事内容から最初の YouTube URL を自動抽出して表示（youtube.com/watch?v=... または youtu.be/... に対応）
- 見つからない場合は非表示
- クリックで元の YouTube 動画を新タブで開く

**note 下書き保存先 URL**
- note への下書き投稿完了後、GitHub Variables から取得したリンクを表示
- **永続化**: localStorage に保存され、ページリロード後も消えない
- 記事を選択するたびにバックグラウンドで最新 URL を再取得（移動後も維持）
- クリックで note.com の下書き記事を新タブで開く

#### 記事タイトル表示（H1 ベース）

- **記事を開くと**: 本文先頭の `# H1タイトル` を自動抽出
- **サイドバー**: H1 がキャッシュされ、ファイル名由来のタイトル（YouTube タイトル）の代わりに表示
- **エディタヘッダー**: H1 がサイドバーと同じタイトルを表示
- **✏️ 編集ボタン**: H1 がある場合はそれを初期値として提供
- **フォールバック**: H1 が存在しない場合はファイル名から従来通り抽出
- **キャッシュ**: localStorage（`sb_articleH1Cache` キー）に保存、一度開いた記事は次回から即表示

**メリット**: YouTube 動画タイトル（ファイル名に埋め込まれた記事生成時のタイトル）ではなく、実際の記事内容を反映した**真の記事タイトル**をサイドバーで一目で確認できる

**キーボードショートカット:**

| ショートカット | 動作 |
|--------------|------|
| `Ctrl+S` | 保存 |
| `Ctrl+B` | 太字（選択テキストを `**` で囲む） |
| `Ctrl+Z` | Undo（500ms debounce、最大100段階） |
| `Ctrl+F` | 検索・置換パネルの開閉 |
| `Escape` | タイトル編集 / 検索パネル / 複数選択を閉じる・解除 |

---

### 3.3 タイトル編集

- ✏️ アイコンクリックでインライン編集
- 確定時に **OneDrive上のファイル名もリネーム**（`PATCH /api/articles`）
- ファイル名のプレフィックス（`YYYYMMDD_HHMM_`）は保持される

---

### 3.4 ツールバーボタン一覧

| ボタン | 説明 |
|--------|------|
| Amazon検索フォーム | キーワードでAmazon商品検索（新タブ） |
| note | note.comを新しいタブで開く |
| 下書き | 現在の記事（または選択した複数記事）をnoteに下書き投稿 |
| アフィリンク | アフィリエイトリンク管理モーダルを開く |
| シート | Google Sheetsを新しいタブで開く |
| パイプライン | 記事生成パイプラインを手動起動 |
| 保存 | 現在の内容をOneDriveに保存（`Ctrl+S`と同等） |
| リロード | 記事一覧を再取得 |

---

### 3.5 モバイルレスポンシブ対応

スマートフォンでの記事管理を専用タッチジェスチャーで対応。

#### 長押しドラッグ＆ドロップ（フォルダ移動）

**トリガー**: 記事を 500ms 長押し

| 動作 | 説明 |
|------|------|
| ゴースト表示 | 指の下に記事名カードが浮かぶ（バイブレーション付き） |
| フォルダ検出 | 指が重なるフォルダが紫の破線でハイライト |
| 指を離す | ハイライト中のフォルダへ記事を移動（複数選択も一括対応） |
| スクロール干渉 | 長押し中の上下スクロール防止（スムーズなドラッグ実現） |

> **複数選択中の場合**: Ctrl/Cmd+クリックで選択した全記事が同時に移動

#### 左スワイプ（削除・複製）

**トリガー**: 記事を左に 55px 以上スワイプ

| 動作 | ボタン | 説明 |
|------|--------|------|
| スワイプ左 | 複製（🟣） | 記事をコピー（ファイル名に「コピー_」付与） |
|  | 削除（🔴） | 確認ダイアログ後に削除 |
| スワイプ右 or 別タップ | — | スワイプ状態を閉じる |

> **レイアウト**: 記事が左にスライドして右端に2ボタンが露出（iOS風スワイプメニュー）

#### 操作の判別

| 条件 | 判定 | 動作 |
|------|------|------|
| 縦方向 > 横方向 +12px 移動 | 縦スクロール | スクロール優先（スワイプ/ドラッグキャンセル） |
| 左方向 12px以上かつ横 > 縦 | スワイプ確定 | 55px でアクション表示 |
| 500ms無移動 | 長押し確定 | ドラッグ開始 |

> デバイス振動・遅延なしの流暢な UX を実現

---

## 4. note下書き自動投稿システム

### 4.1 仕組み

```
[下書きボタン]
    ↓ POST /api/note-draft  (Vercel)
    ↓ GitHub Actions note-draft.yml を dispatch
    ↓ prompts/05-draft-manager/note_draft_poster.py 実行
    ↓ APIログイン → スケルトン作成 → draft_save
    ↓ GitHub Variable NOTE_DRAFT_URL_<hash> にURLを保存
    ↓ UI が5秒間隔でpolling → URLが取得できたらリンク表示
```

### 4.2 使用するnote API（確定版）

| 操作 | エンドポイント | メソッド |
|------|--------------|---------|
| ログイン | `https://note.com/api/v1/sessions/sign_in` | POST |
| スケルトン作成 | `https://note.com/api/v1/text_notes` | POST |
| **本文保存（下書き）** | `https://note.com/api/v1/text_notes/draft_save?id={id}&is_temp_saved=true` | POST |

**本文保存に必須のヘッダー:**
- `X-XSRF-TOKEN`: CookieのXSRF-TOKENをURLデコードした値
- `Origin: https://editor.note.com`
- `Referer: https://editor.note.com/`

詳細は `reference/techrefere2.md` を参照。

### 4.3 セッション管理

- **初回のみ手動**: `python prompts/05-draft-manager/note_draft_poster.py --save-cookies`（ブラウザ手動ログイン → Cookie取得）
- **以降は完全自動**: APIログイン（`POST /api/v1/sessions/sign_in`）でCookieを自動取得・更新
- **keepalive**: `.github/workflows/note-keepalive.yml` が3日おきにセッションを延命

### 4.4 複数記事の一括投稿

サイドバーで複数記事を選択した状態で「下書き」ボタンを押すと、選択した記事が**それぞれ独立したnote記事**として下書き保存される（1記事 = 1note記事）。

---

## 5. Vercel API エンドポイント一覧

| エンドポイント | メソッド | 説明 |
|--------------|---------|------|
| `/api/articles` | GET | 記事一覧取得（OneDrive） |
| `/api/articles?id=xxx` | GET | 記事本文取得 |
| `/api/articles` | PUT | 記事保存（上書き） |
| `/api/articles` | PATCH | ファイルリネーム（`action`省略時） |
| `/api/articles` | PATCH (`action=move`) | 記事をフォルダ間移動（OneDrive Graph API） |
| `/api/articles` | DELETE | ファイル削除 |
| `/api/articles` | POST | ファイル複製 |
| `/api/trigger` | POST | パイプライン起動（GitHub Actions） |
| `/api/note-draft` | POST | note下書き投稿トリガー（単体 or 複数） |
| `/api/note-draft?fileId=xxx` | GET | 下書き済みURLを取得（GitHub Variable） |
| `/api/affiliate-links` | GET | アフィリエイトリンク取得 |
| `/api/affiliate-links` | PUT | アフィリエイトリンク保存 |
| `/api/open-file?path=&name=` | GET | ローカルExplorer/Finderでファイルを開く（`vercel dev`環境専用） |
| `/api/ogp?url=` | GET | OGPメタデータ取得（Amazonは自動クリーン+遅延処理） |

---

## 6. GitHub Actionsワークフロー一覧

| ワークフロー | トリガー | 役割 |
|------------|---------|------|
| `pipeline.yml` | 毎日JST 9:00 / 手動 | 記事自動生成 |
| `note-draft.yml` | `workflow_dispatch`（fileId必須） | note下書き投稿 |
| `note-keepalive.yml` | 3日おき cron / 手動 | noteセッション延命 |

---

## 7. 環境変数一覧

### GitHub Secrets（Actions用）

| 変数名 | 用途 |
|--------|------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | スプレッドシート用サービスアカウント鍵 |
| `SPREADSHEET_ID` | 管理用スプレッドシートID |
| `SHEET_NAME` | 読み込み対象シート名 |
| `APIFY_API_KEY` | Amazon hiRes 画像取得の Apify fallback |
| `GEMINI_API_KEY` | Google AI APIキー |
| `ONEDRIVE_CLIENT_ID` | Microsoft Graph API クライアントID |
| `ONEDRIVE_CLIENT_SECRET` | Microsoft Graph API クライアントシークレット |
| `ONEDRIVE_REFRESH_TOKEN` | OneDriveアクセス維持 |
| `ONEDRIVE_FOLDER` | OneDrive内のルートフォルダ名 |
| `NOTE_EMAIL` | noteログインメールアドレス |
| `NOTE_PASSWORD` | noteログインパスワード |
| `NOTE_STORAGE_STATE` | Playwright StorageState JSON（Cookie情報） |
| `GH_PAT` | GitHub PAT（`secrets:write` + `variables:write` スコープ必須） |

### Vercel 環境変数

| 変数名 | 用途 |
|--------|------|
| `ONEDRIVE_CLIENT_ID` | Microsoft Graph API |
| `ONEDRIVE_CLIENT_SECRET` | Microsoft Graph API |
| `ONEDRIVE_REFRESH_TOKEN` | OneDriveトークン（自動更新） |
| `ONEDRIVE_FOLDER` | OneDriveフォルダ名 |
| `VERCEL_TOKEN` | 環境変数自動更新用（Vercel PAT） |
| `VERCEL_PROJECT_ID` | VercelプロジェクトID |
| `GITHUB_TOKEN` | note-draft API用（GH_PATの値を設定） |
| `GITHUB_REPO` | リポジトリ名（例: `seahirodigital/Blog_Vercel`） |
| `LOCAL_ARTICLES_BASE` | ローカル開発時のExplorer/Finder表示用ベースパス（省略時: `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog`） |

### GitHub Variables（自動生成）

| 変数名 | 内容 |
|--------|------|
| `NOTE_DRAFT_URL_<8桁ハッシュ>` | 記事ごとの下書きURL（note_draft_poster.pyが自動生成） |

---

## 8. 初回セットアップ手順

1. GitHub Secrets を上記の通りすべて設定
2. Vercel 環境変数を設定
3. noteのStorageState初回取得:
   ```bash
   cd scripts/pipeline
   pip install requests pynacl playwright
   python prompts/05-draft-manager/note_draft_poster.py --save-cookies
   # ブラウザが開くのでnote.comにログイン → Enterを押す
   # GH_PATが設定されていればNOTE_STORAGE_STATEに自動登録される
   ```
4. Vercelにデプロイ（`vercel --prod` またはGitHub連携）
5. スプレッドシートに動画URLを追加してパイプラインを実行

---

## 9. ファイル構成

```
Blog_Vercel/
├── public/
│   └── index.html              # 管理画面（React + Tailwind, シングルファイル）
├── api/
│   ├── articles.js             # OneDrive記事CRUD（移動含む）
│   ├── ogp.js                  # OGPメタデータ取得（Amazon対応）
│   ├── open-file.js            # ローカルExplorer/Finder起動（開発環境専用）
│   ├── trigger.js              # パイプライン起動
│   ├── note-draft.js           # note下書きトリガー + URL取得
│   └── affiliate-links.js      # アフィリエイトリンク管理
├── scripts/
│   └── pipeline/
│       ├── prompts/05-draft-manager/ # note下書き投稿スクリプト群（v4.1）
│       ├── prompts/                # AI生成プロンプト集
│       └── ...
├── .github/
│   └── workflows/
│       ├── pipeline.yml            # 記事自動生成
│       ├── note-draft.yml          # note下書き投稿
│       └── note-keepalive.yml      # セッション維持cron
├── reference/
│   └── techrefere2.md             # note API技術リファレンス
├── vercel.json
└── README.md
```

---

## 10. note 下書き保存の現在仕様

### 本番で使うスクリプト
- 本番導線は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py`
- このスクリプトが、本文下書き作成、OGP 展開、Amazon 商品特定、トップ画像挿入、最後の `下書き保存` まで担当する

### Amazonトップ画像のルール
- 記事本文の先頭から最初の `▼` より前に URL があれば、その先頭 URL から ASIN を抽出する
- `▼` より前に URL がなければ、note タイトル / H1 / H2 から商品名を再抽出する
- それでも特定できない場合は画像挿入をスキップする

### 画像の分岐ルール
- `hires` が取得できた場合:
- 元画像を `raw` に保存し、note HERO 向けの整形済み画像を `prepared` に生成して、note の通常アップロードで挿入する
- `hires` が取得できない場合:
- Amazon Creators API の通常画像を `raw` に保存し、それを元に `prepared` を生成して、note の通常アップロードで挿入する

### Adobe Express 関連
- Adobe Express のログイン state は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\adobe_express_storage_state.json`
- state 保存補助スクリプトは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\save_adobe_express_storage_state.py`
- 現在の本番経路では Adobe Express は使わない
- Adobe Express は `NOTE_TOP_IMAGE_USE_ADOBE=1` を入れたときだけ debug 用に残す

### debug / 切り分け用
- 画像単体の切り分け検証は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\note_image_draft_test.py`
- 詳細メモは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\gazoup_reference.md`
- スクリーンショットや HTML などの成果物は `NOTE_TOP_IMAGE_DEBUG=1` を入れたときだけ `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts\` に保存する

### 2026-04-09 時点の成功実績
- GitHub Actions 成功 run は `https://github.com/seahirodigital/Blog_Vercel/actions/runs/24174122466`
- note 下書き URL は `https://editor.note.com/notes/n941b2432f659/edit/`
- artifact `top_image_result.json` の実測結果は `image_flow=direct_prepared`
- `selected_image_kind=prepared` で、`C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images\prepared\YYYYMMDD_ASIN_note_hero.jpg` 系の整形済み画像が note ヘッダーへ通常アップロードされている
- 同じ artifact では `hires_image_url=https://m.media-amazon.com/images/I/51QPhONLrhL._AC_SL1280_.jpg` も確認できており、hiRes 自体の取得と note 添付の両方が通った

---

## 11. トップ画像の現状と今後の主方針

### 現状

- GitHub Actions から Amazon 商品詳細ページへ直接アクセスすると captcha に捕まりやすいため、Amazon hiRes 画像の取得は **Apify fallback** に切り替えている
- 2026-04-09 の時点で、本番経路は **Adobe Express を外し、整形済み画像を note の通常アップロードへ入れる方式** に切り替わった
- 成功 run `24174122466` では `direct_prepared` で note ヘッダー保存まで完了している

### 白画像問題の要点

- artifact 検証では、note に保存された後で壊れているのではなく、**Adobe 側のキャンバスが白いまま保存・挿入されている** 可能性が高い
- `blob:` 画像検出だけでアップロード完了扱いしていること
- `プロジェクトを保存中...` が消える前に確定挿入へ進んでいる可能性があること
- Adobe 内で用途違いの file input を掴んでいる可能性があること

### 今後の主方針

Adobe Express 経由は複雑で、GitHub Actions 上での安定化コストが高い。  
そのため、現在の主方針は **note の `画像をアップロード` 導線を本番経路にする**。

ただし、元画像をそのままトップ画像へ入れると、ヘッダー枠で **見切れやすい**。  
そのため、以下の流れへ舵を切る。

1. Apify から hiRes 画像を取得する
2. 元画像を必ず OneDrive に保存する
3. note ヘッダー向けに、見切れないよう事前整形した画像を生成する
4. 整形済み画像を note の通常アップロードで貼る

### OneDrive 保存先

トップ画像用の Amazon 画像は、元画像と整形済み画像の両方を必ず次へ保存する。

`C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images`

推奨構成:

- 元画像:
  `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images\raw\YYYYMMDD_ASIN_hires.jpg`
- 整形済み画像:
  `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images\prepared\YYYYMMDD_ASIN_note_hero.jpg`

理由:

- GitHub Actions で添付に失敗しても、手動添付へすぐ切り替えられる
- 元画像と整形済み画像を残しておけば、見た目の再調整がしやすい
- 成功 run の artifact にも `raw` と `prepared` の両方のパスが残るため、後追い検証がしやすい

### 整形ルール

最優先は **見切れ禁止**。  
画像が少し小さくなるほうが、見切れるよりましとする。  
そのうえで、トップの HERO なので、**枠内に収まる最大サイズ**で中央配置する。

実装方針:

- note のトップ画像比率 `800:418` を基準に固定キャンバスを作る
- 実生成サイズは `1600x836` など、同一比率で高解像度にする
- 元画像は `contain` で縮小し、**cover や crop は使わない**
- 足りない余白は**必ず白背景**で埋める

### 推奨ツール

GitHub Actions で扱いやすいのは Python の `Pillow`。

推奨処理:

- `ImageOps.exif_transpose()` で向きを正規化
- `Image.convert('RGB')`
- `ImageOps.contain(image, (1600, 836), method=Image.Resampling.LANCZOS)` で最大サイズ化
- `Image.new('RGB', (1600, 836), background_color)` で固定キャンバス生成
- `paste()` で中央配置
- `save(..., quality=92, optimize=True)` で JPEG 保存

この方針により、Amazon captcha は Apify で回避しつつ、Adobe 依存を外し、GitHub Actions 上で再現性の高いトップ画像処理へ寄せる。

### 今回の失敗ノウハウ要約

- Amazon 商品詳細ページの直接 scraping は、GitHub Actions ランナーからだと captcha に落ちやすく、hiRes 抽出の主経路にしてはいけない
- Adobe Express 経由は一見 hiRes を使えても、白画像・UI 文言差分・保存待機不足の不安定さが大きく、本番経路に向かない
- note の通常アップロード導線は、file chooser の遅延発火や文言差分があるので、複数セレクタと再試行は必要
- ただし一度整形済み画像まで用意できれば、**note 通常アップロードの方が Adobe より再現性が高い**
