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
