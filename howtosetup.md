# Vibe Blog Engine セットアップ・復旧メモ

このメモは、`C:\Users\mahha\OneDrive\開発\Blog_Vercel` の Vercel Blog Engine を復旧・運用するときの手順をまとめたものです。

## 必須環境変数

ローカルでは `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` に設定します。Vercel 本番では Vercel Dashboard の `blog-vercel` プロジェクト > `Settings` > `Environment Variables` に設定します。

- `ONEDRIVE_CLIENT_ID`: Microsoft Graph / OneDrive 用アプリの Client ID
- `ONEDRIVE_CLIENT_SECRET`: Microsoft Graph / OneDrive 用アプリの Client Secret
- `ONEDRIVE_REFRESH_TOKEN`: OneDrive の refresh token
- `ONEDRIVE_FOLDER`: OneDrive 内の記事保存先フォルダ
- `VERCEL_TOKEN`: Vercel REST API で環境変数更新や再デプロイを行うためのトークン
- `VERCEL_PROJECT_ID`: Vercel の `blog-vercel` プロジェクトID
- `GITHUB_REPO`: GitHub リポジトリ名
- `GITHUB_TOKEN`: GitHub Actions dispatch 等で使うトークン

## OneDrive Refresh Token 失効時の症状

Microsoft アカウントのパスワード変更やセキュリティ再認証の後、`ONEDRIVE_REFRESH_TOKEN` が失効することがあります。

典型的な症状:

- `https://blog-vercel-dun.vercel.app/` は表示される
- 記事一覧に「記事一覧の取得に失敗しました」と出る
- `https://blog-vercel-dun.vercel.app/api/articles?mode=shallow&h1Limit=0` が `500` を返す
- レスポンス本文が `{"error":"Token取得失敗: 400"}` になる
- `https://blog-vercel-dun.vercel.app/api/affiliate-links` も同じ `Token取得失敗: 400` になる

この場合、壊れているのはフロントエンドではなく OneDrive 認証です。直す場所はコードではなく、Vercel Production の `ONEDRIVE_REFRESH_TOKEN` です。

## 手動復旧手順

### 1. Microsoft 認可URLを開く

`<ONEDRIVE_CLIENT_ID>` は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` の値に置き換えます。

```text
https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=<ONEDRIVE_CLIENT_ID>&scope=offline_access%20Files.ReadWrite.All&response_type=code&redirect_uri=http://localhost:8080
```

実際に記事を保存している OneDrive アカウントでログインし、アクセス許可に同意します。

### 2. code を取得する

認可後に `http://localhost:8080` が「このサイトにアクセスできません」になるのは正常です。ローカルでWebサーバーを立てていないためです。

見るべき場所は画面本文ではなく、ブラウザのアドレスバーです。

成功時のURL例:

```text
http://localhost:8080/?code=M.C540_BAY...&session_state=...
```

使う値は `code=` の後ろから次の `&` の直前までです。

注意:

- `client_id=` や `redirect_uri=` は使いません
- `code` は一回使い切りです
- 失敗したら Microsoft 認可URLを開き直して新しい `code` を取得します
- 末尾が `%24` の場合は URL エンコードされた `$` なので、PowerShell に入れるときは `$` に戻します
- `!` や `*` が含まれるため、PowerShell では `code` をシングルクォートで囲むのが安全です

### 3. token API で refresh_token を取得する

通常の `Invoke-RestMethod` が `接続が切断されました: 受信時に予期しないエラーが発生しました。` で失敗することがあります。その場合は `curl.exe --ssl-no-revoke` を使います。

```powershell
$vars = @{}
Get-Content -LiteralPath "C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env" | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    $vars[$matches[1].Trim()] = $matches[2].Trim().Trim('"')
  }
}

$code = '<ブラウザのアドレスバーから取得したcode。末尾%24は$に戻す>'

$response = & curl.exe --ssl-no-revoke -sS --max-time 30 -X POST 'https://login.microsoftonline.com/common/oauth2/v2.0/token' `
  -H 'Content-Type: application/x-www-form-urlencoded' `
  --data-urlencode "client_id=$($vars['ONEDRIVE_CLIENT_ID'])" `
  --data-urlencode "client_secret=$($vars['ONEDRIVE_CLIENT_SECRET'])" `
  --data-urlencode "code=$code" `
  --data-urlencode 'redirect_uri=http://localhost:8080' `
  --data-urlencode 'grant_type=authorization_code' `
  --data-urlencode 'scope=Files.ReadWrite.All offline_access'

$json = $response | ConvertFrom-Json
$json.refresh_token
```

返ってきた JSON の `refresh_token` を使います。`access_token` ではありません。

### 4. refresh_token を反映する

取得した `refresh_token` を次の両方へ反映します。

1. `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` の `ONEDRIVE_REFRESH_TOKEN`
2. Vercel Dashboard の `blog-vercel` プロジェクト > `Settings` > `Environment Variables` > Production の `ONEDRIVE_REFRESH_TOKEN`

Vercel 環境変数更新後も、既存の本番関数が古い環境変数を掴んでいる場合があります。その場合は Production を再デプロイします。

## 今回つまずいたこと

2026-05-12 の復旧で実際につまずいた点です。

- `http://localhost:8080` の接続エラーを異常だと思いやすいが、これは正常です。アドレスバーの `code=` だけを使います。
- 貼り付け時にURLが崩れ、`code=` が `co...de=` のように見えました。この場合も `M.C540_BAY...` から始まる部分だけを使います。
- `%24` は `$` に戻します。
- 一度 token API 交換に成功した `code` は再利用できません。
- 通常の PowerShell HTTPS では接続が切断されたため、`curl.exe --ssl-no-revoke` で token API 交換を実行しました。
- Vercel 環境変数を更新しただけでは本番APIがまだ `Token取得失敗: 400` のままでした。Production 再デプロイ後に復旧しました。
- ローカルの `C:\Users\mahha\OneDrive\開発\Blog_Vercel\node_modules\.bin\vercel.cmd` は `39.4.2` で、Vercel API から `47.2.2 or later` を要求されました。
- Vercel CLI は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.codex_tmp` を走査して `EPERM` になりました。`C:\Users\mahha\OneDrive\開発\Blog_Vercel\.vercelignore` に `.codex_tmp`、`.env`、`.git`、`node_modules` を入れて除外します。

## Vercel 再デプロイの実測成功手順

Vercel CLI が使えない場合は、Vercel REST API で既存 Production デプロイを再デプロイします。

`VERCEL_TOKEN` と `VERCEL_PROJECT_ID` は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` から読みます。実値はログやチャットに出さないでください。

```powershell
$vars = @{}
Get-Content -LiteralPath "C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env" | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    $vars[$matches[1].Trim()] = $matches[2].Trim().Trim('"')
  }
}

$headers = @{
  Authorization = "Bearer $($vars['VERCEL_TOKEN'])"
  'Content-Type' = 'application/json'
}

$body = @{
  deploymentId = '<現在のProductionデプロイID>'
  name = 'blog-vercel'
  project = 'blog-vercel'
  target = 'production'
  withLatestCommit = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri 'https://api.vercel.com/v13/deployments?teamId=<VercelチームID>' `
  -Headers $headers `
  -Body $body
```

2026-05-12 の実測では、新しい Production デプロイが `READY / PROMOTED` になった後、記事一覧APIが復旧しました。

## 復旧確認

```powershell
curl.exe --ssl-no-revoke -sS -i --max-time 30 "https://blog-vercel-dun.vercel.app/api/articles?mode=shallow&h1Limit=0"
curl.exe --ssl-no-revoke -sS -I --max-time 20 "https://blog-vercel-dun.vercel.app/"
```

成功時:

- `/api/articles` が `HTTP/1.1 200 OK`
- 本文に `articles` と `folders` を含む JSON が返る
- トップページが `HTTP/1.1 200 OK`

## セキュリティ注意

- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` は秘密情報を含むため、GitHub に push しません。
- `refresh_token`、`access_token`、`ONEDRIVE_CLIENT_SECRET`、`VERCEL_TOKEN`、`GITHUB_TOKEN` はチャットやドキュメントに貼りません。
- ドキュメントにはプレースホルダだけを書きます。
