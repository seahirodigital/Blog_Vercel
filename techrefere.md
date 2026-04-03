# Note下書き自動投稿の技術リファレンス (v5 — 確定版)

## 1. 完成した機能一覧

| 機能 | 状態 | 実装方法 |
|------|------|---------|
| 認証（APIログイン） | ✅ 完全自動化 | `POST /api/v1/sessions/sign_in` |
| スケルトン作成 | ✅ 完全自動化 | `POST /api/v1/text_notes` |
| **本文保存** | ✅ 完全自動化 | `POST /api/v1/text_notes/draft_save` |
| Cookie自動更新 | ✅ 完全自動化 | GitHub Secret自動書き換え（PyNaCl）|
| セッション維持cron | ✅ 完全自動化 | `note-keepalive.yml`（3日おき）|
| 下書きURL記録 | ✅ 完全自動化 | GitHub Repository Variable |
| UI上のURL表示 | ✅ 実装済み | polling + MARKDOWNバーにリンク表示 |
| **OGP展開（Amazonカード）** | ❌ 失敗 | Playwright + JS注入 → 本文が空白になる問題 |

---

## 2. 確定した正解のAPI仕様

### 認証

```
POST https://note.com/api/v1/sessions/sign_in
Content-Type: application/json

{ "login": "<email>", "password": "<password>" }
→ 200 OK + Set-Cookie: _note_session_v5, XSRF-TOKEN 等
```

### 記事スケルトン作成（タイトル・本文なし）

```
POST https://note.com/api/v1/text_notes
Content-Type: application/json
Origin: https://editor.note.com
X-Requested-With: XMLHttpRequest

{ "template_key": null }
→ 201 Created + { "data": { "id": 12345, "key": "nXXXXXXXXXXXX" } }
```

**重要**: `name`（タイトル）も `body` も含めない。`template_key: null` のみ。

### 本文保存（下書き）← ここが核心

```
POST https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=true
Content-Type: application/json
Origin: https://editor.note.com
Referer: https://editor.note.com/
X-XSRF-TOKEN: <CookieのXSRF-TOKENをURLデコードした値>
X-Requested-With: XMLHttpRequest

{
  "body": "<p>本文HTML</p>",
  "body_length": 123,
  "name": "タイトル",
  "index": false,
  "is_lead_form": false,
  "image_keys": []
}
→ 200 OK
```

**重要ポイント:**
- エンドポイントは `PUT /text_notes/{id}` **ではなく** `POST /text_notes/draft_save?id={id}`
- `X-XSRF-TOKEN` は `XSRF-TOKEN` Cookieの値を `urllib.parse.unquote()` してセット
- `Origin` と `Referer` は必ず `https://editor.note.com` / `https://editor.note.com/` を指定
- `body_length` はHTMLタグを除去したプレーンテキストの文字数

### 下書き完成後のURL

```
https://editor.note.com/notes/{key}/edit/
```

---

## 3. 試行錯誤の全記録

### v3.0 — Playwright方式（2025年）

| 手法 | 問題 |
|------|------|
| ID/パスワード直接ログイン | GitHub ActionsのクラウドIPをreCAPTCHAが完全ブロック |
| Cookieのみ設定 | セッション情報不足・有効期限切れで不安定 |
| クリップボードペースト | ヘッドレス環境でクリップボード権限エラー |
| StorageState方式 | `NOTE_STORAGE_STATE` と `GITHUB_TOKEN` のワークフロー設定漏れで機能せず |

### v4.0 — HTTP API直接投稿（失敗した全パターン）

**`POST /api/v1/text_notes` の調査:**
- `body` をどのパラメータで渡しても、レスポンスの `body` は常に `null`
- `name` のみ保存される
- → **POSTにbodyを含めることはできない**（仕様）

**`PUT /api/v1/text_notes/{id}` の全失敗パターン:**

| パターン | 結果 |
|----------|------|
| JSON + `status: "draft"` | 422 |
| JSON（statusなし） | 422 |
| フォームデータ（`data=`送信） | 400 |
| `PATCH` メソッド | 405 |
| `body` を最小HTML `<p>テスト</p>` | 422 |
| `body` をプレーンテキスト | 422 |
| URL を `key` で指定 | 404 |
| `/api/v2/text_notes/{id}` | 404 |
| `Origin: https://editor.note.com` | 422（変化なし） |
| POST後にGETでsession初期化→PUT | GET: 405、PUT: 422のまま |

**結論**: `PUT` は公開用エンドポイントであり、下書き保存には使えない。

### v4.1 — NoteClient2ソース逆解析（成功）

PyPIパッケージ `NoteClient2` の `client.py` を `pip install` して読解。
`site-packages/NoteClient2/client.py` の `_draft_save()` メソッドから正解を特定:

```python
url = f"https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=true"
headers = {
    "X-XSRF-TOKEN": urllib.parse.unquote(cookies.get("XSRF-TOKEN", "")),
    "Referer": "https://editor.note.com/",
    ...
}
```

これをHTTP APIクライアント（requests）で再現して完全動作を確認。

---

## 4. Cookie・セッション管理の仕様

### 初回セットアップ

```bash
python note_draft_poster.py --save-cookies
# ブラウザを開いて手動ログイン → StorageState取得
# GITHUB_TOKENがあれば NOTE_STORAGE_STATE Secretに自動登録
```

### 以降（完全自動）

1. `NOTE_STORAGE_STATE` Secret からCookieを復元
2. セッション有効性チェック（`GET /api/v3/users/user_features`）
3. 無効時 → `POST /api/v1/sessions/sign_in` でAPIログイン
4. `_note_session_v5` Cookieの重複が発生する場合は古いものをクリアしてから再セット
5. 操作後、最新CookieをGitHub Secret `NOTE_STORAGE_STATE` に自動上書き

### keepalive（3日おき cron）

`.github/workflows/note-keepalive.yml` が `0 3 */3 * *` で実行。
セッションが有効なら更新保存、無効ならAPIログインで復旧。

---

## 5. 下書きURLの記録・表示

### 記録（note_draft_poster.py）

下書き成功後、GitHub Repository Variable に保存:
```
NOTE_DRAFT_URL_<MD5(file_id)[:8].upper()>  =  "https://editor.note.com/notes/{key}/edit/"
```
`PATCH /repos/{owner}/{repo}/actions/variables/{name}` で更新（なければ `POST` で作成）。

### 取得（api/note-draft.js）

```
GET /api/note-draft?fileId=<OneDrive_fileId>
→ { "url": "https://editor.note.com/notes/.../edit/" }   // またはnull
```

### 表示（public/index.html）

下書きボタン押下後、5秒間隔・最大24回（2分）のpollingでURLを取得。
取得できた時点でエディタバーの `MARKDOWN` 右隣に「保存先URL」リンクを表示。

---

## 6. Cookie重複エラーの解決策

`requests.Session` で同一名Cookieが複数ドメインに存在すると `dict(session.cookies)` が失敗する。

```python
# NG: CookieConflictError
cookies = dict(session.cookies)

# OK: iteratorで重複を除去
seen = set()
cookie_list = []
for cookie in session.cookies:
    key = (cookie.name, cookie.domain)
    if key not in seen:
        seen.add(key)
        cookie_list.append(cookie)
```

---

## 7. OGP展開（Amazonカード）試行 — 失敗記録

### 試みた手法

draft_save 成功後に Playwright（headless Chromium）で `editor.note.com/notes/{key}/edit/` を開き、
`05-note_ogp_formatter.js` を3回実行（7秒→5秒→3秒待機）してから、
`editor.innerHTML` を取得してもう一度 `draft_save` を呼ぶ実装を行った。

### 失敗の結果

- note エディタ上で本文が**空白（先頭に改行のみ）**になった
- アフィリエイトリンクのAmazonカードは表示されなかった

### 推定原因

| 原因 | 詳細 |
|------|------|
| エディタの内容未ロード | Playwright でページを開いた時点では、note エディタは空の状態で起動する。draft_save で保存した内容はサーバー側にあるが、エディタDOMには即座に反映されない |
| innerHTML が空を取得 | エディタが空のままの状態で `innerHTML` を抽出 → `draft_save` に空のHTMLを送信 → 本文が上書きで消えた |
| OGP展開のタイミング | JS が URL にカーソルを当てて Enter を押す操作は、実際にコンテンツが表示されていないと意味をなさない |

### 根本的な制約

note のエディタ（`editor.note.com`）は **SPA（Single Page Application）** であり、
URL を開いただけでは下書き内容をDOMに復元しない。
エディタの内部状態（ProseMirror / 独自実装）のロードを待つ仕組みが別途必要。
headless ブラウザからの制御は、エディタのレンダリング完了を正確に検知することが困難。

### 今後の対策候補

| 方針 | 内容 |
|------|------|
| A | `draft_save` API のリクエストボディに直接 OGP カードの HTML 要素を手動で組み込む（ブラウザ不要） |
| B | エディタロード完了を確認する selector を特定して待機時間を大幅延長（15〜30秒）してから JS実行 |
| C | OGP展開はnote の手動編集に委ね、本文保存のみ自動化（現行維持） |

**現在の方針: C（OGPステップなし）でv4.1を維持。**

---

## 8. 関連ファイル一覧

| ファイル | 役割 |
|---------|------|
| `scripts/pipeline/note_draft_poster.py` | メインスクリプト（v4.1） |
| `.github/workflows/note-draft.yml` | 下書き投稿ワークフロー |
| `.github/workflows/note-keepalive.yml` | セッション維持cron |
| `api/note-draft.js` | VercelサーバーレスAPI（トリガー + URL取得） |

---

## 8. GitHub Secrets / Variables 一覧

| 名前 | 種別 | 内容 |
|------|------|------|
| `NOTE_STORAGE_STATE` | Secret | Playwright StorageState JSON（Cookie情報）|
| `NOTE_EMAIL` | Secret | noteログインメールアドレス |
| `NOTE_PASSWORD` | Secret | noteログインパスワード |
| `GH_PAT` | Secret | GitHub PAT（secrets:write + variables:write スコープ必須）|
| `NOTE_DRAFT_URL_<hash>` | Variable | 記事ごとの下書きURL（自動生成） |

---

## 9. ブログエディタ改善記録（public/index.html）

### 9-1. OGPカード展開機能（✅ 正常動作中）

#### 概要

Markdownプレビュー内のURL行を自動でOGPカード（サムネイル付きリンク）に変換する。  
Amazon商品リンク・短縮リンク（amzn.to）・通常URLすべてに対応。

#### アーキテクチャ

| 処理 | 場所 | 役割 |
|------|------|------|
| OGPメタデータ取得 | `api/ogp.js`（Vercel Serverless） | CORSを回避してサーバーサイドでHTMLをフェッチ、メタタグを抽出 |
| カード変換 | `public/index.html`（クライアント） | `<a>` タグをOGPカード要素に差し替え |
| キャッシュ | `ogpCacheRef`（useRef） | エディタ編集でDOMがリセットされても即時復元 |
| DOM再適用 | `useLayoutEffect` | `renderedHTML` 変化直後、ブラウザ描画前にキャッシュからカードを復元 |

#### OGPカード変換フロー

```
Markdownレンダリング
  → <a href="URL">URL</a> 検出（isOgpUrl関数）
  → 未キャッシュ: /api/ogp?url=... にフェッチ
  → キャッシュ済み: useLayoutEffect で即時挿入
  → buildOgpCard() でDOM要素を生成
  → insertOgpCard() で <p> または <a> をカードに置換
```

#### Amazon対応の詳細（api/ogp.js）

Amazonはサーバーサイドからのフェッチをbot検出でブロックするため、以下の対策を実装:

| 対策 | 内容 |
|------|------|
| ブラウザ偽装ヘッダー | User-Agent・Accept・Referer（google.com）・Sec-Fetch-* を全て設定 |
| 商品タイトル抽出 | `<span id="productTitle">` からタイトルを直接抽出（OGPメタタグが汎用名の場合） |
| 商品画像抽出 | `"hiRes"`・`"large"` JSONパターン、`id="landingImage"` imgタグから優先順に抽出 |
| クリーンURL再試行 | bot検出時にASINを抽出し `amazon.co.jp/dp/{ASIN}?language=ja_JP` で再フェッチ |

#### クライアント側のワーカー設計

```
Amazon URL   → シングルワーカー + 2200ms間隔（レート制限を確実に回避）
その他のURL  → 2並列ワーカー（300ms stagger）+ 500ms間隔
```

**Amazon URLを並列処理すると即座にレート制限（HTTP 503/429）が発生する。**  
シングルワーカーで逐次処理することで全ASINのカード取得が可能になった。

#### 最終フォールバック

4回リトライ後も失敗した場合、URLから最低限の情報でカードを構築:
- ASINが取れる場合: タイトル `Amazon商品 (B0XXXXXXXX)` + `amazon.co.jp` ドメイン
- ASINなし: ドメインのみ表示

これにより、素URLのままプレビューに残ることがなくなった。

#### Enter押下で即時OGP展開

エディタのURL行末でEnterを押すと、そのURLをバックグラウンドでフェッチし、プレビューのリンクを即時カード化する（renderedHTML再レンダリングとは独立した処理）。

```javascript
// textarea の onKeyDown
if (e.key === 'Enter') {
  const line = 現在行のテキスト;
  if (line.startsWith('http') && !ogpCacheRef.current[line]) {
    fetch(`/api/ogp?url=${encodeURIComponent(line)}`)
      .then(...) // キャッシュ保存 + DOM直接挿入
  }
}
```

#### OGPカードCSS

```css
.ogp-card { border: 1px solid #e2e8f0; border-radius: 0.75rem; display: flex;
            max-height: 160px; box-shadow: 0 1px 6px rgba(0,0,0,0.08); }
.ogp-card-image { width: 140px; object-fit: contain; padding: 0.5rem; background: #f8fafc; }
```

---

### 9-2. エディタ ↔ プレビュー スクロール同期（✅ 実装済み）

#### 設計思想

以前の実装は`h1〜h6`見出し要素のみを同期アンカーとしていたため、  
ユーザーコンテンツ（`▼`で始まる段落、Amazon商品リスト等）では機能しなかった。  
**`marked.lexer()` によるトークン行番号マップ**に切り替え、全ブロック要素に `data-line` を付与して精密同期を実現。

#### 実装フロー

```
1. renderedHTML useMemo
   └── marked.lexer(markdown) でトークン取得
   └── 各トークンのソース行番号を tokenLineMapRef に格納

2. useLayoutEffect（data-line付与）
   └── プレビュー直下のブロック要素に data-line={ソース行番号} を順番にセット
   └── insertOgpCard() が data-line を引き継ぐように修正済み

3. handleEditorScroll（エディタ→プレビュー）
   └── エディタのscrollTopから「先頭に見えている行番号」を算出
   └── [data-line] 要素から前後を二分探索して補間スクロール

4. handlePreviewScroll（プレビュー→エディタ）
   └── プレビューscrollTop付近の [data-line] 要素を特定
   └── 対応ソース行番号を算出してエディタをスクロール
```

#### ダブルクリック位置同期

プレビューでダブルクリックすると、エディタの対応行を**同じビューポート高さ**に合わせる。

```javascript
const elViewportTop = el.getBoundingClientRect().top - pv.getBoundingClientRect().top;
ta.scrollTop = Math.max(0, elLine * lineH - elViewportTop);
// プレビューはスクロールしない。エディタだけが追いつく。
```

例: プレビューで「## FAQ」が上端から150px → エディタで `## FAQ` 行が上端から150pxに表示される。

#### 無限ループ防止

```javascript
const editorScrolling  = useRef(false);  // エディタがスクロール中
const previewScrolling = useRef(false);  // プレビューがスクロール中

// 相手がスクロール中なら自分のハンドラはスキップ
// 60ms後にフラグをリセット
```

---

### 9-3. その他の実装済み機能

| 機能 | 実装概要 |
|------|---------|
| 自動保存 | `content` 変更を debounce 500ms → OneDrive API に保存。初回ロード時は `affUserEdited` ref で誤発火を防止 |
| Ctrl+Z アンドゥ | undoStack（最大100件）＋ 500ms debounce でネイティブundoの代替を実装 |
| アフィリエイトリンクモーダル | OneDrive上の `.txt` ファイルを読み書き。リサイズ可能。モーダル表示中も自動保存が誤発火しないよう `affUserEdited` ref で制御 |
| OGP更新ボタン | 失敗リンクのみ再試行（成功済み `.ogp-card` には触れない） |
| Markdown → HTML変換 | `marked.js`（CDN）＋ リンクは別タブ開き（カスタムrenderer） |
| 3行以上の連続改行保持 | `\n{3,}` → 余分な行を `<br>` に変換してから `marked.parse()` |
