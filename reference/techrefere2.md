# Note下書き自動投稿の技術リファレンス (v3)

## 1. 目的と実装できた機能
* MarkdownのH1部分抽出、タイトルと本文の分離
* プラットフォーム非対応タグ（動画キャプション等）のフィルタリング
* noteエディタへの自動入力・下書き保存
* URL自動展開（OGP化）JS注入によるリッチな編集体験の自動化

---

## 2. 試行錯誤（v3.0まで：Playwright編）

### (1) ヘッドレスブラウザによるID/パスワード直接ログインの失敗
* **手法**: `page.fill` してログインボタンを自動押下。
* **問題**: note側のreCAPTCHAにクラウドIP（GitHub Actions）からのアクセスが完全にブロックされた。

### (2) Cookieのみの設定による不安定さ
* **手法**: 重要そうなCookieのみを環境変数からセット。
* **問題**: セッション情報の不足・有効期限切れで不安定。手動運用となった。

### (3) クリップボードペーストの制限
* **手法**: `keyboard.press("Control+v")` で一発入力。
* **問題**: Actionsのヘッドレス環境ではクリップボードアクセス権限の問題でペースト失敗。

### (4) v3.0 StorageState方式（Playwright）
* **手法**: 初回のみ手動ログインし、PlaywrightのStorageState（Cookie＋LocalStorage全体）をGitHub Secretに保存。毎回復元してreCAPTCHAを回避。3日おきのcronでセッション延命。
* **問題（設定漏れ）**: GitHub Actions ワークフローに `NOTE_STORAGE_STATE` と `GITHUB_TOKEN` が渡されておらず、StorageState復元が機能しなかった。

---

## 3. 試行錯誤（v4.0：HTTP API直接投稿編）

Playwright廃止・noteの内部APIに直接HTTPリクエストを送る方式へ移行。

### 判明した事実

**成功した操作：**

| 操作 | エンドポイント | 結果 |
|------|--------------|------|
| APIログイン | `POST /api/v1/sessions/sign_in` | 200 成功 |
| 記事作成（タイトルのみ） | `POST /api/v1/text_notes` | 201 成功（`body`は常に`null`） |
| GitHub SecretのCookie自動更新 | GitHub API | 成功 |

**失敗した操作（本文保存）：**

`PUT /api/v1/text_notes/{id}` は常に **422** を返す。

```
{"error": {"code": "invalid", "message": "不正なパラメータが渡されました。はじめから操作をやり直してください。"}}
```

試したパターンと全ての結果：

| パターン | 結果 |
|----------|------|
| JSON + `status: "draft"` | 422 |
| JSON（statusなし） | 422 |
| フォームデータ（`data=`送信） | 400（Content-Type衝突） |
| `PATCH` メソッド | 405 |
| `GET` メソッド | 405 |
| `body` を最小HTML `<p>テスト</p>` | 422 |
| `body` をプレーンテキスト | 422 |
| URL を数値IDでなく `key` で指定 | 404 |
| `/api/v2/text_notes/{id}` | 404 |
| `Origin: https://editor.note.com` | 422（変化なし） |
| `Referer: https://editor.note.com/notes/{id}/edit/` | 422（変化なし） |
| POST後にGETでsession初期化→PUT | GET: 405、PUT: 422のまま |

### 根本的な制約（結論）

1. **`POST /api/v1/text_notes` は `body` を受け付けない**  
   どのパラメータを渡してもPOSTレスポンスの `body` は常に `null`。タイトルのみ保存される。

2. **`PUT /api/v1/text_notes/{id}` は外部HTTPクライアントから呼べない**  
   パラメータ・ヘッダー・Content-Type・メソッド・APIバージョン・Origin/Refererを変えても全て422。  
   noteのエディタ（`editor.note.com`）が内部セッションで使うAPIであり、  
   通常のHTTPクライアントからは意図的にブロックされていると断定。

---

## 4. 結論と今後の方針

### 現状のまとめ

| 機能 | 状態 |
|------|------|
| 認証（APIログイン） | 完全自動化 ✅ |
| タイトル保存 | 完全自動化 ✅ |
| 本文保存 | 不可 ❌（PUT APIがブロック） |
| Cookie自動更新 | 完全自動化 ✅ |
| セッション維持cron | 完全自動化 ✅ |

### 次のアプローチ候補

| 方針 | 難易度 | 備考 |
|------|-------|------|
| **A: Playwrightへの回帰（v5.0）** | 中 | StorageStateで認証は解決済み。v4.0の成果（Cookie管理・ワークフロー設定）を活かして再実装 |
| **B: note公式API（将来）** | - | 現時点で公式APIは存在しない |
| **C: ブラウザ実通信のプロキシ解析** | 高 | 実際のブラウザリクエストをキャプチャして必要なパラメータを特定 |

### 推奨：Playwrightへの回帰（v5.0）
v3.0のPlaywright方式に戻り、v4.0の成果を組み込んで安定化する：
1. ワークフローの設定漏れ（`NOTE_STORAGE_STATE`・`GITHUB_TOKEN`）は修正済み
2. Cookie重複問題の解決策はv4.0で確立済み
3. APIログインによるCookie自動再取得をフォールバックとして維持
4. 本文入力はProseMirrorへの`page.evaluate()`直接注入で安定化
