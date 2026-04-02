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

- **リンクソース**: OneDrive上の `affiliate_links.txt`（MEMO1〜の▼ブロック形式）を毎回直接取得
- **挿入ルール**:
  1. H2「結論」直前 → MEMO1全文 ＋ Amazonアソシエイト免責事項
  2. 偶数番目のH2（2,4,6...）直前 → ▼ブロックをランダム1つ選択（重複なし）
  3. 記事末尾 → MEMO1全文 ＋ 免責事項
- スクリプト未検出 or エラー時は**スキップして処理続行**（記事生成は止まらない）

#### Step 4 — OneDrive保存

- `modules/onedrive_sync.py` が Microsoft Graph API 経由でアップロード
- **フォルダ**: `ONEDRIVE_FOLDER`（デフォルト: "Blog_Articles"）
- **ファイル名**: `YYYYMMDD_HHMM_動画タイトル.md`

#### Step 5 — スプレッドシート更新

- 保存成功後、対象行の「状況」を `完了` に更新（`modules/sheets_reader.py`）

### 2.4 note下書き自動投稿（別ワークフロー）

記事生成パイプラインとは独立した別ワークフロー（`note-draft.yml`）。詳細は [セクション4](#4-note下書き自動投稿システム) を参照。

`scripts/pipeline/note_draft_poster.py` が以下を実行:
1. Cookie復元 → セッション検証 → 必要に応じてAPIログイン
2. `POST /api/v1/text_notes` でスケルトン作成
3. `POST /api/v1/text_notes/draft_save` で本文保存
4. GitHub Repository Variable に下書きURLを記録

---

## 3. 管理画面（Vibe Blog UI）

`public/index.html` — React + Tailwind CSS（CDN）でシングルファイル実装。

### 3.1 サイドバー（記事一覧）

- OneDriveのフォルダ階層をツリー形式で表示（月別フォルダ等）
- 横幅ドラッグリサイズ・開閉トグル対応
- モバイルではドロワー形式で表示

**右クリックメニュー:**

| 項目 | 動作 |
|------|------|
| 選択 | チェックボックス選択モードを開始し、この記事を最初の選択状態にする |
| 複製 | 記事をコピー（ファイル名先頭に「コピー_」付与） |
| 削除 | 確認ダイアログ後にOneDriveから削除 |
| エクスプローラーで表示 | OneDrive Webで直接開く |

**複数選択モード:**

1. 右クリック → 「選択」でチェックボックスモード開始
2. 記事タイトル左のチェックボックスをクリックして複数選択（薄紫ハイライト）
3. ツールバーの「下書き」ボタンが「下書き(N)」と件数表示に変化
4. 「解除」ボタンで選択モードをキャンセル

### 3.2 エディタ

- **左ペイン**: Markdownエディタ（JetBrains Monoフォント）
- **右ペイン**: リアルタイムプレビュー
- 両ペインの境界をドラッグでサイズ調整可能

**エディタバー（MARKDOWNラベルの行）:**

- 文字数表示
- 全文コピーボタン
- **「保存先URL」リンク**: note下書き保存が完了したときにeditor.note.comのURLが自動表示される

**キーボードショートカット:**

| ショートカット | 動作 |
|--------------|------|
| `Ctrl+S` | 保存 |
| `Ctrl+B` | 太字（選択テキストを `**` で囲む） |
| `Ctrl+Z` | Undo（500ms debounce、最大100段階） |
| `Ctrl+F` | 検索・置換パネルの開閉 |
| `Escape` | タイトル編集/検索パネルを閉じる |

### 3.3 タイトル編集

- ✏️ アイコンクリックでインライン編集
- 確定時に **OneDrive上のファイル名もリネーム**（`PATCH /api/articles`）
- ファイル名のプレフィックス（`YYYYMMDD_HHMM_`）は保持される

### 3.4 ツールバーボタン一覧

| ボタン | 説明 |
|--------|------|
| note | note.comを新しいタブで開く |
| 下書き | 現在の記事（または選択した複数記事）をnoteに下書き投稿 |
| アフィリンク | アフィリエイトリンク管理モーダルを開く |
| シート | Google Sheetsを新しいタブで開く |
| パイプライン | 記事生成パイプラインを手動起動 |
| 保存 | 現在の内容をOneDriveに保存（`Ctrl+S`と同等） |
| リロード | 記事一覧を再取得 |

---

## 4. note下書き自動投稿システム

### 4.1 仕組み

```
[下書きボタン]
    ↓ POST /api/note-draft  (Vercel)
    ↓ GitHub Actions note-draft.yml を dispatch
    ↓ note_draft_poster.py 実行
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

- **初回のみ手動**: `python note_draft_poster.py --save-cookies`（ブラウザ手動ログイン → Cookie取得）
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
| `/api/articles` | PATCH | ファイルリネーム |
| `/api/articles` | DELETE | ファイル削除 |
| `/api/articles` | POST | ファイル複製 |
| `/api/trigger` | POST | パイプライン起動（GitHub Actions） |
| `/api/note-draft` | POST | note下書き投稿トリガー（単体 or 複数） |
| `/api/note-draft?fileId=xxx` | GET | 下書き済みURLを取得（GitHub Variable） |
| `/api/affiliate-links` | GET | アフィリエイトリンク取得 |
| `/api/affiliate-links` | PUT | アフィリエイトリンク保存 |

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
| `APIFY_API_KEY` | YouTube文字起こし取得 |
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
   python note_draft_poster.py --save-cookies
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
│   ├── articles.js             # OneDrive記事CRUD
│   ├── trigger.js              # パイプライン起動
│   ├── note-draft.js           # note下書きトリガー + URL取得
│   └── affiliate-links.js      # アフィリエイトリンク管理
├── scripts/
│   └── pipeline/
│       ├── note_draft_poster.py    # note下書き投稿スクリプト（v4.1）
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
