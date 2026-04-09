# Note下書き自動投稿の技術リファレンス (v6 — OGP展開統合版)

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
| **OGP展開（Amazonカード）** | ✅ 完全自動化 | Playwright headless + JS注入 + Ctrl+S保存 |

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
python prompts/05-draft-manager/note_draft_poster.py --save-cookies
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

## 7. OGP展開（Amazonカード）— 失敗→成功の全記録

### 旧実装（失敗）の原因

draft_save 成功後に Playwright でエディタを開き、`editor.innerHTML` を取得して再度 `draft_save` を呼ぶ実装を行ったが失敗した。

| 原因 | 詳細 |
|------|------|
| エディタの内容未ロード | Playwright でページを開いた時点では、note エディタは空の状態で起動する。draft_save で保存した内容はサーバー側にあるが、エディタDOMには即座に反映されない |
| innerHTML が空を取得 | エディタが空のままの状態で `innerHTML` を抽出 → `draft_save` に空のHTMLを送信 → 本文が上書きで消えた |

---

### 確定した正解の実装（v6）

#### 全体フロー

```
Phase 1: APIログイン（POST /api/v1/sessions/sign_in）
Phase 2: 下書き作成（POST /api/v1/text_notes + draft_save）→ editor_url 取得
Phase 3: セッション更新（GitHub Secret自動書き換え）
Phase 4: OGP展開（Playwright headless Chromium）
  ├─ Cookie注入 → editor_url を開く
  ├─ ProseMirrorコンテンツ出現をポーリング待機
  ├─ JS注入（OGP展開ループ・最大3スイープ）
  ├─ 5秒待機（非同期反映待ち）
  ├─ エディタクリック + Ctrl+S で明示的に保存
  └─ 8秒待機（保存完了待ち）
```

#### エディタ内容ロード待機（解決した旧来の問題）

note SPA の特性: `domcontentloaded` 後もエディタ DOM は空。  
ProseMirror コンテンツ（`p` / `h2` / `h3` タグ）の出現を最大60秒ポーリングして検知する。

```python
EDITOR_CONTENT_SELECTOR = ".ProseMirror p, .ProseMirror h2, .ProseMirror h3"

while time.time() < deadline:
    count = page.locator(EDITOR_CONTENT_SELECTOR).count()
    if count > 0:
        text = page.locator(EDITOR_CONTENT_SELECTOR).first.text_content()
        if text and text.strip():
            return True  # 本文ロード確認
    time.sleep(1)
```

#### OGP展開JS（ProseMirrorへのURL→Enter操作）

note エディタのOGPカード化は「URLの行末にカーソルを置いてEnterを押す」操作で発動する。  
JS で `setCaretAtUrlEnd()` を呼び Playwright の `page.keyboard.press("Enter")` で実行する。

```python
# 最大3スイープで展開漏れを拾う
for sweep in range(3):
    all_urls = page.evaluate("window.noteFormatter.extractUrls()")
    target_urls = [u for u in set(all_urls) if any(d in u for d in OGP_TARGET_DOMAINS)]
    if not target_urls:
        break
    for url in target_urls:
        # URL出現回数分だけ繰り返す（同一URLが複数箇所にある場合）
        for occ in range(1, all_urls.count(url) + 1):
            found = page.evaluate("(args) => window.noteFormatter.setCaretAtUrlEnd(args.url, args.occ)",
                                  {"url": url, "occ": occ})
            if found:
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
    page.wait_for_timeout(3000)  # カードDOM反映待ち

# 全スイープ後に不要な空行を一括削除
page.evaluate("window.noteFormatter.normalizeLineBreaks()")
```

対象ドメイン: `amzn.to`, `amazon.co.jp`, `apple.com`, `youtube.com`

#### 保存トリガー（headless 特有の問題と解決）

**問題**: headless モードでは note SPA の自動保存イベントが発火しないケースがある。  
**解決**: OGP展開後に明示的に Ctrl+S を送信する。

```python
page.wait_for_timeout(5000)   # 非同期反映待ち
editor = page.locator(".ProseMirror, .note-editable, [contenteditable='true']").first
editor.click()                # エディタにフォーカス
page.keyboard.press("Control+s")
page.wait_for_timeout(8000)   # 保存完了待ち
```

#### Cookie受け渡しの正解（ハマりポイント）

**問題**: `_load_cookies()` は環境変数 `NOTE_STORAGE_STATE`（実行開始時点の古いCookie）を返す。  
Phase 1 でAPIログインして得た新しい `_note_session_v5` は `session` オブジェクト内にのみ存在する。  
Playwright に古いCookieを渡すとエディタ認証が失敗し、OGP展開の変更が保存されない。

```python
# NG: 環境変数の古いCookieを読む
latest_cookies = _load_cookies()

# 正解: requests.Session オブジェクトから直接取得
session_cookies = {c.name: c.value for c in session.cookies}
_run_ogp_expansion_on_draft(result["url"], session_cookies, headless=True)
```

#### GitHub Actions ワークフローの設定

OGP展開には Playwright Chromium のバイナリが必要。`pip install playwright` だけでは不足。

```yaml
- name: Python 依存パッケージをインストール
  run: pip install -r scripts/pipeline/requirements.txt

- name: Playwright ブラウザをインストール（Chromium）
  run: playwright install --with-deps chromium  # --with-deps でOS依存ライブラリも取得
```

`timeout-minutes` は OGP展開時間を含めて `20` に設定。

#### 実績ログ（成功時の出力）

```
── Phase 4: OGP展開（Playwright） ──
   ⏳ エディタコンテンツのロード待機（最大60秒）...
   ✅ エディタコンテンツ検出: 227要素（1.2秒後）
   [Python] 🔄 1回目のスイープ...
   [Python] 残存対象URL: 11種 / 計30箇所
   [Python] 🔄 2回目のスイープ...
   [Python] 残存対象URL: 11種 / 計12箇所
   [Python] 🔄 3回目のスイープ...
   [Python] 残存対象URL: 1種 / 計1箇所
   [Python] 🧹 不要な空行を最終一括削除...
   ✅ OGP展開処理完了: 31件
   💾 Ctrl+S で明示的に保存をトリガー...
   ✅ OGP展開 + 保存が完了しました。
```

---

## 8. 関連ファイル一覧

| ファイル | 役割 |
|---------|------|
| `scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py` | メインスクリプト（v6 — OGP展開統合版） |
| `testcode/note_ogp_opener.py` | OGP展開の試作・検証スクリプト（スタンドアロン版） |
| `.github/workflows/note-draft.yml` | 下書き投稿ワークフロー（timeout: 20分、playwright install 含む） |
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

---

## 10. Amazon ASIN 自動取得のアーキテクチャ改修 (2026-04-05)

### 過去の課題と変遷
*   **v1 (スクレイピング等)**: Vercel ServerlessやGitHub Actions上のIP（Playwright等）がAmazonの強力なボット対策によって「503」や「403」で一斉にブロックされ、ASINの取得に失敗。
*   **v2 (Google CSE)**: Amazonサイト内検索をGoogle Custom Search経由で行う戦略を取るも、リンクの正確さや抽出ロジックの面で不確実性が残る。

### 解決策（v3: Amazon Creators APIへの移行）
Amazonが公式に提供する新しい **Creators API** を利用し、100%確実かつブロック回避のできるASIN取得経路を確立しました。従来のPA-API（Product Advertising API）とは認証・エンドポイント・データ形式が異なります。

#### Creators API (v3.x / FE Region) の仕様
- **認証方式**: OAuth2 (Login with Amazon) - Client Credentials Flow
  - トークンエンドポイント: `https://api.amazon.co.jp/auth/o2/token`
  - スコープ: `creatorsapi::default`
- **データエンドポイント**: `https://creatorsapi.amazon/catalog/v1/searchItems` (POST)
- **必須ヘッダー**:
    - `Authorization: Bearer <access_token>`
    - `x-marketplace: www.amazon.co.jp` (※日本向けには必須)
    - `Content-Type: application/json`
- **リクエスト仕様**: JSONボディで `keywords`, `partnerTag`, `marketplace`, `resources` を指定。
- **レスポンス構造**: 全て **camelCase**（例: `searchResult`, `items`, `asin`, `itemInfo`）。

#### 最新の取得フロー優先順位
```
1. Amazon Creators API (公式・IPブロック完全回避)
※ Vercel、Google CSE、スクレイピング等を利用した過去のフォールバック処理は不要と判断し削除済。
```

#### 必要な環境変数
GitHub Actions (および必要ならローカルの `.env`) に以下の Secret の設定が必須です。
※ 過去に使用していた `GOOGLE_CSE_API_KEY` および `GOOGLE_CSE_CX` は不要となりました。

| キー | 用途・値 |
|------|----------|
| `AMAZON_CLIENT_ID` | Creators APIのアプリケーションClient ID (`amzn1.application-...`) |
| `AMAZON_CLIENT_SECRET` | Creators APIのClient Secret (`amzn1.oa2-cs.v1...`) |

#### 変更ファイル
| ファイル | 変更内容 |
|----------|---------|
| `insert_amazon_affiliate.py` | `_fetch_asin_via_creators_api()` を実装・最優先化。OAuth2フローとPOST検索 |
| `blog-pipeline.yml` | `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET` 等の env エクスポートを追加 |

---

## noteトップ画像・Adobe Express 技術メモ

### 現在の本番導線
- 本番スクリプトは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py`
- Amazon画像取得は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py`
- Adobe Express のログイン state 保存補助は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\save_adobe_express_storage_state.py`
- debug 切り分け用スクリプトと成果物は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\`

### Amazon画像取得で確定した知見
- Creators API の `Images.Primary.Large` は、実測では 500px 級で止まるケースがある
- 高画質画像は商品ページ側の `hiRes` / `data-old-hires` / `landingImage` 系から取れる場合がある
- 現在は `amazon_gazo_get.py` で、通常版を必ず保存し、取れた場合のみ `_hires` 付き画像を追加保存する
- 保存先は `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog`

### note 側の商品特定ルール
- 記事本文の先頭から最初の `▼` より前に URL がある場合は、その一番上の URL を正しい Amazon リンクとして扱い ASIN を抽出する
- `▼` より前に URL が無い場合のみ、現在の note タイトル / H1 / H2 から商品名を再抽出する
- それでも商品特定できなければ、トップ画像挿入はスキップする

### Adobe Express で白画像になった原因と対策
- 初期実装では、`input[type='file']` の候補が広すぎて、Adobe ではなく note 側や別の隠し input に当たる可能性があった
- その結果、Adobe 側のキャンバスが白紙のまま `挿入` が進み、note に白い eyecatch が保存されるケースがあった
- 対策として `アップロード` サイドバーを明示で開き、Adobe 側 shadow root 内の `x-upload-button-editor` 配下 `input[type='file']` を優先するよう修正した
- ファイル投入後は `blob:` 画像の出現を待ってから、`sp-button#save-btn` → `sp-button#dialog-download-btn` でコードベースのまま挿入する

### 現在の Adobe セレクタ方針
- 上部 `挿入`: `sp-button#save-btn`
- 確定 `挿入`: `sp-button#dialog-download-btn`
- 画像アップロード: `アップロード` サイドバーを開いた上で Adobe 側 `input[type='file']`
- 右パネルの `ファイル形式` / `サイズ` は調整せず、そのまま note へ返す

### debug 出力先
- note トップ画像まわりの成果物は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts\`
- 代表ファイル:
- `top_image_result.json`
- `after_top_image_draft_save.html`
- `after_top_image_draft_save.png`
- `adobe_after_upload.html`
- `adobe_after_upload.png`

---

## 2026-04-09 トップ画像障害の実録

### 失敗の時系列

今回の Pixel 10a 記事で、note 下書き投稿のトップ画像処理は複数の独立した問題が連続して表面化した。

1. 最初の失敗は Amazon Secret 未注入だった。  
   `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` に `AMAZON_CLIENT_ID` と `AMAZON_CLIENT_SECRET` が無く、`amazon_gazo_get.py` が `環境変数 AMAZON_CLIENT_ID が未設定` で停止した。  
   修正 commit: `770e4bb`

2. その次は note の通常アップロード導線が古い文言依存だった。  
   `text=画像をアップロード` 前提では current UI に追従できず、ローカルでは成功しても Actions では `画像アップロード導線を特定できませんでした` で止まった。  
   修正 commit: `7e6153e`

3. さらに Actions とローカルで browser state が揃っていなかった。  
   ローカルは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\adobe_express_storage_state.json` を読み込んでいたが、Actions は未読込だった。  
   これを `ADOBE_EXPRESS_STORAGE_STATE` Secret と artifact 保存付きで揃えた。  
   修正 commit: `652d6a5`

4. `ADOBE_EXPRESS_STORAGE_STATE` を JSON 文字列で渡した後、`Path(...).exists()` を先に呼んで `File name too long` で落ちた。  
   JSON 判定を先にし、パス判定は後段へ回した。  
   修正 commit: `7ec0d99`

5. その後の Actions では、アップロード導線クリック後にメニューが閉じるケースに弱かった。  
   `input[type='file']` のポーリング待機、メニュー再オープン、再試行 artifact を追加した。  
   修正 commit: `ada05c2`

6. 最後に残っていた本丸は、Amazon 画像ファイルを Actions 上で早すぎるタイミングで消していたことだった。  
   `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py` が OneDrive アップロード直後に JPEG を削除しており、その後段の Playwright が存在しない画像を note に渡そうとしていた。  
   修正 commit: `7564857`

### 今回成功したノウハウ

- `note-draft.yml` には Amazon / note / Adobe の Secret をすべて明示的に `env` で渡す必要がある。Repository Secret に登録しただけでは Python から見えない。
- `ADOBE_EXPRESS_STORAGE_STATE` はファイルパスではなく JSON 本文として Secret に入れ、実行時に一時 `storage_state` ファイルへ変換するのが安全。
- GitHub Actions とローカルの差分追跡には artifact 保存が必須。  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\note-draft.yml` で `if: always()` の `actions/upload-artifact@v4` を入れておくと、失敗時の DOM と screenshot を後追いできる。
- note の通常アップロードは file chooser が遅延発火することがある。  
  1回目クリック直後の `input[type='file']` ポーリング、導線消失時のトップ画像メニュー再オープン、追加 artifact 保存が有効だった。
- Amazon 画像を note へ直接アップロードする経路では、OneDrive 連携後でもローカル画像は削除してはいけない。  
  note 挿入が終わるまで JPEG を残す必要がある。

### Actions 成功 run

- 成功 run:
  `https://github.com/seahirodigital/Blog_Vercel/actions/runs/24167942186`
- 成功時の note URL:
  `https://editor.note.com/notes/n8a945789c39b/edit/`
- ローカルへダウンロードした artifact:
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\tmp\run_24167942186\note-top-image-artifacts-24167942186\top_image_result.json`

この成功 run では、トップ画像の保存自体は完了している。

```json
{
  "image_flow": "direct_api",
  "image_target_asin": "B0F535RF9Z",
  "hires_image_url": "",
  "upload_entry_strategy": "button_role_label_regex_upload#0:filechooser",
  "after_ready_image_count": 1
}
```

### hiRes / Adobe 差分の実測結果

#### 1. 同一 ASIN `B0F535RF9Z` の hiRes 抽出差分

同じ `B0F535RF9Z` をローカルで `amazon_gazo_get.py` に直接渡すと、hiRes は取得できた。

- ローカル検証出力先:
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\tmp\local_hires_probe`
- ローカル実測結果:
  - `api_image_url`:
    `https://m.media-amazon.com/images/I/31gI-U4GtcL._SL500_.jpg`
  - `hires_image_url`:
    `https://m.media-amazon.com/images/I/51QPhONLrhL._AC_SL1280_.jpg`

一方、Actions 成功 run の `top_image_result.json` では `hires_image_url` は空だった。  
つまり、**同一 ASIN でも GitHub Actions ランナー経由では Amazon 商品ページから hiRes を引けていない**。

#### 2. 同一 Pixel 10a 記事をローカルで実行した結果

記事:
`C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\20260408_0200_【待望】Google Pixel 10a国内発表キタァーー！Pixel 9aから何が変わった？わかりやすくスペック仕様を.md`

ローカル実行後の artifact:
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts\top_image_result.json`

ローカル実測結果:

```json
{
  "image_flow": "direct_api_after_adobe_failure",
  "image_target_asin": "B0F535RF9Z",
  "hires_image_url": "https://m.media-amazon.com/images/I/51QPhONLrhL._AC_SL1280_.jpg",
  "selected_image_path": "C:\\Users\\HCY\\OneDrive\\Obsidian in Onedrive 202602\\Vercel_Blog\\...\\20260409_B0F535RF9Z.jpg",
  "after_ready_image_count": 1,
  "adobe_error": "Adobe Express アップロードサイドバー を特定できませんでした"
}
```

ここから分かることは次の2点。

- ローカルでは `hiRes` 自体の取得は成功している
- ただし現状の本番コードでは、Adobe Express のアップロードサイドバー検出に失敗して通常アップロードへフォールバックしている

### 現時点の結論

- Actions 側:
  hiRes が取れていないため、Adobe 経由には入らず `direct_api` で通常版画像を保存している
- ローカル側:
  hiRes は取れて Adobe 導線までは入るが、Adobe UI 操作が未完成で `direct_api_after_adobe_failure` にフォールバックしている
- したがって、**現在確認できている「最終的に note に保存されたトップ画像」は、ローカル・Actions とも通常版である**

### 次にやるべき差分調査

1. Actions 上の Amazon 商品詳細 HTML を artifact 化し、ローカル HTML と比較して `data-old-hires` / `colorImages.initial[0].hiRes` の有無を確認する  
2. ローカルの Adobe Express 画面で、`adobe_workspace_open.html` と `adobe_upload_sidebar_open.html` が取れていない理由を詰め、アップロードサイドバー検出セレクタを更新する  
3. `image_flow=adobe_hires` が実際に成立した証跡が取れるまで、ローカル成功と Actions 成功を分けて記録する

### 2026-04-09 追加検証: Adobe 経路の修正後

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\05-draft-manager\note_draft_poster.py`
に以下を追加した。

- Adobe Express へ入った直後に、サイドバーを開く前から shadow DOM 内の `input[type='file']` を探索する
- `cc-everywhere-container-*`、`sp-button#save-btn`、`dialog_download_btn` を Adobe ワークスペース判定に追加する
- Amazon hiRes が空のとき、note の Playwright context から Amazon 詳細ページを開いて再抽出する browser fallback を追加する
- 差分確認用 artifact として
  `amazon_detail_requests.html`
  `amazon_detail_browser.html`
  `amazon_hires_probe.json`
  `adobe_file_input_candidates_pre_sidebar.json`
  を出す

#### ローカル再実行結果

記事:
`C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\20260408_0200_【待望】Google Pixel 10a国内発表キタァーー！Pixel 9aから何が変わった？わかりやすくスペック仕様を.md`

実行後の artifact:
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts\top_image_result.json`

結果:

```json
{
  "image_flow": "adobe_hires",
  "hires_image_url": "https://m.media-amazon.com/images/I/51QPhONLrhL._AC_SL1280_.jpg",
  "selected_image_path": "C:\\Users\\HCY\\OneDrive\\Obsidian in Onedrive 202602\\Vercel_Blog\\...\\20260409_B0F535RF9Z_hires.jpg",
  "upload_sidebar_strategy": "direct_input_pre_sidebar",
  "upload_entry_strategy": "frame#1:input[type='file']#2:score=90:root=[object ShadowRoot]:host=x-upload-button-editor",
  "insert_strategy": "frame#1:sp_button_save_btn#0",
  "confirm_insert_strategy": "frame#1:dialog_download_btn_scoped#0"
}
```

ここで初めて、**ローカルでは hiRes JPEG を Adobe 経由で note に保存できた**。

#### ローカル hiRes probe の結果

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\debug\note_gazo_test\artifacts\amazon_hires_probe.json`

```json
{
  "detail_page_url": "https://www.amazon.co.jp/dp/B0F535RF9Z",
  "asin": "B0F535RF9Z",
  "requests_hires_url": "https://m.media-amazon.com/images/I/51QPhONLrhL._AC_SL1280_.jpg",
  "browser_probe_used": false
}
```

この時点での更新された結論は次の通り。

- ローカル側の Adobe 経路は修正完了し、`adobe_hires` まで到達した
- Actions 側の未解決は、**Amazon hiRes が requests で抜けない差分がまだ残っているか** に集約された
- そのため次の確認対象は、Actions run の `amazon_hires_probe.json` が
  `requests_hires_url`
  `browser_hires_url`
  のどちらで hiRes を拾えるか、である

