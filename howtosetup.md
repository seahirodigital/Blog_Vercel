# Vibe Blog Engine 環境構築マニュアル (howtosetup.mdOut

このドキュメントは、Vercel Blog Engine（YouTube→自動ブログ作成→OneDrive保存）システムの構築から各種APIキーの取得・設定方法までをまとめた完全版マニュアルです。

---

## 1. 必要なツールの準備とアカウント一覧

本システムでは、以下のサービスのアカウント・API設定が必要です。

1. **GitHub**: ソースコード管理・Actionsでの定期実行のため
2. **Vercel**: Webエディタの公開・保存APIのホスティングのため
3. **Google Cloud (GCP)**: Google Sheets 連携用（サービスアカウント）
4. **Apify**: YouTubeからの全自動文字起こし用
5. **Google AI Studio (Gemini)**: ブログ記事のAI生成用
6. **Azure Portal (Entra ID)**: OneDriveへの自動保存（Graph API）用

---

## 2. 各種 API Key / 認証情報 の取得方法

### A. Apify API Key (`APIFY_API_KEY`)
1. [Apify Console](https://console.apify.com/) にログイン
2. 左メニュー「Settings」>「Integrations」を開く
3. 「API token」の項目にある文字列をコピー

### B. Gemini API Key (`GEMINI_API_KEY`)
1. [Google AI Studio](https://aistudio.google.com/apikey) にログイン
2. 「Get API key」または「Create API key」をクリック
3. `AIzaSy...` から始まるAPIキーをコピー

### C. Google Sheets 連携 (`SPREADSHEET_ID`, `SHEET_NAME`, `GOOGLE_SERVICE_ACCOUNT_JSON`)
1. **Google Cloud Console** でプロジェクトを作成し、`Google Sheets API` を有効化する
2. **IAMと管理 > サービスアカウント** から新しいサービスアカウントを作成する
3. 作成したサービスアカウントの「キー（JSON形式）」を新規作成してダウンロード（→ `service_account.json`）
4. スプレッドシート側の「共有」ボタンから、サービスアカウントのメールアドレス（例: `bot@xxx.iam.gserviceaccount.com`）を「編集者」として追加する
5. スプレッドシートのURLから ID（`d/` と `/edit` の間の文字列）を控える。(`SPREADSHEET_ID`)

### D. OneDrive連携 (`ONEDRIVE_CLIENT_ID`, `ONEDRIVE_CLIENT_SECRET`, `ONEDRIVE_REFRESH_TOKEN`)

> **[注意]** 無料の個人用Microsoftアカウントは、そのままではAzure Portalにログインできない（ディレクトリ・テナントが存在しない）ため、Azure無料アカウント機能（クレカ登録必須・課金なし）等でテナントを有効化するか、**別の捨てアカウント**を新しく作ってダミーのアプリを作成する必要があります。

1. **アプリの登録 (Azure Portal)**
   - [Azure Portal](https://portal.azure.com) で **「App registrations（アプリの登録）」** を開く。
   - 「＋新規登録」をクリックし、サポートされるアカウントの種類を**「任意の組織ディレクトリ内のアカウントと個人用の Microsoft アカウント」**に設定。
   - リダイレクトURIを `Web` ＋ `http://localhost:8080` と設定して登録。

2. **Client ID / Secret の取得**
   - 概要ページに表示される `Application (client) ID` をコピー。（→ `ONEDRIVE_CLIENT_ID`）
   - 左メニューの「証明書とシークレット」から新しいクライアントシークレットを作成し、その「値（Value）」をコピー。（→ `ONEDRIVE_CLIENT_SECRET`）

3. **API Access Permissions の設定**
   - 左メニューの「APIのアクセス許可」を開く。
   - 「Microsoft Graph」→ **「委任されたアクセス許可 (Delegated permissions)」** を選択。
   - `Files.ReadWrite.All` と `offline_access` を検索してチェックし、追加する。

4. **Refresh Token の取得**
   - ブラウザで以下のURLを開く（`[CLIENT_ID]` は取得したものに置き換える）。
     `https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=[CLIENT_ID]&scope=offline_access%20Files.ReadWrite.All&response_type=code&redirect_uri=http://localhost:8080`
   - **実際に保存先とするメインのOneDriveアカウント**でログインし、アクセスを許可（承諾）する。
   - `localhost` へのアクセスエラー画面になるが、そのブラウザのアドレスバーのURLにある `code=M.R3_xxxx...` の部分をコピーする。
   - 取得した `code` を用いて、Python等で POST (`https://login.microsoftonline.com/common/oauth2/v2.0/token`) を行い、戻り値のJSONから `refresh_token` を取得する。（→ `ONEDRIVE_REFRESH_TOKEN`）

5. **保存先フォルダ (`ONEDRIVE_FOLDER`)**
   - 上記で承認したメインのOneDrive内にフォルダを作成し、OneDriveルートからの相対パスを指定する。
   - 例: `Obsidian/Blog` 

---

## 3. GitHub と Vercel への登録手順

ここまでで用意した計 **8つ（+ GITHUB関連2つ）** の環境変数をシステムに設定します。

### 1. GitHub Secrets の登録（バックエンド用）
1. 対象の GitHub リポジトリ（例: `seahirodigital/Blog_Vercel`）を開く。
2. `Settings` > `Secrets and variables` > `Actions` に進む。
3. `New repository secret` をクリックし、以下の8つを登録する。

- `APIFY_API_KEY`
- `GEMINI_API_KEY`
- `SPREADSHEET_ID`
- `SHEET_NAME`
- `GOOGLE_SERVICE_ACCOUNT_JSON` （JSONの中身をすべてペースト）
- `ONEDRIVE_CLIENT_ID`
- `ONEDRIVE_CLIENT_SECRET`
- `ONEDRIVE_REFRESH_TOKEN`

### 2. Vercel の Environment Variables の登録（フロント・API用）
1. [Vercel](https://vercel.com/) にアクセスし、プロジェクトを開く。
2. `Settings` > `Environment Variables` に進む。
3. GitHub登録時と同じ8つの変数に加えて、以下の2つを追加登録する。

- **`GITHUB_REPO`**: リポジトリ名（例: `seahirodigital/Blog_Vercel`）
- **`GITHUB_TOKEN`**: WebUIからGitHubの機能を実行するために必要な鍵
  - *(※GitHubの `Settings` > `Developer settings` > `Personal access tokens (classic)` で、`repo` と `workflow` の権限にチェックを入れて新規発行した `ghp_...` から始まるパスワード)*

### 3. デプロイと稼働確認
1. すべての環境変数を設定後、Vercel 画面上で「Deploy」または「Redeploy」を実行する。
2. 表示されたURLにアクセスし、Vibe Blog Engine のエディタ画面が開くことを確認する。
3. エディタから何か文字を入力し、右上の「保存」ボタンで OneDrive に自動保存されるかテストする。
4. 左下の「パイプライン実行」ボタンを押し、裏で GitHub Actions が動いて AIによる生成スクリプト が実行されるかテストする。

以上で構築完了となります！

---

## 4. トラブルシューティング実績（構築時の試行錯誤）

構築過程で発生した問題と、その恒久対策を記録します。再構築やエラー発生時の参考にしてください。

### ① 保存先フォルダパスの「空白（スペース）」問題
- **事象**: `ONEDRIVE_FOLDER` に「Obsidian in Onedrive...」のように空白が含まれると、一覧取得や保存に失敗（400 Bad Request）する。
- **原因**: Graph APIのパス指定で空白がそのままURLとして送られていた。
- **対策**: `api/articles.js` 内でパスを `/` で分割し、各階層を `encodeURIComponent` で処理するように修正した。

### ② リフレッシュトークンの「使い捨て」問題（重要）
- **事象**: 一度保存に成功しても、数回使うと「トークンが無効（invalid_grant）」になり保存できなくなる。
- **原因**: Microsoftの仕様で、リフレッシュトークンを使用して新しいアクセストークンを取得すると、リフレッシュトークン自体も新しいものに更新（ローテーション）され、古いものは即座に無効化されるため。
- **対策**: 
  - `api/articles.js` に Vercel API を叩く機能を実装。
  - トークン取得のたびに、最新のリフレッシュトークンを Vercel の環境変数 (`ONEDRIVE_REFRESH_TOKEN`) に自動で上書き保存する仕組みを構築した。
  - **必須変数**: Vercel側の環境変数に `VERCEL_TOKEN` と `VERCEL_PROJECT_ID` を追加設定する必要がある。

#### Microsoft パスワード変更後の手動復旧手順

- **症状**: `https://blog-vercel-dun.vercel.app/` は表示されるが、記事一覧に「記事一覧の取得に失敗しました」と出る。`https://blog-vercel-dun.vercel.app/api/articles?mode=shallow&h1Limit=0` は `500` になり、本文が `{"error":"Token取得失敗: 400"}` になる。
- **原因**: Microsoft アカウントのパスワード変更やセキュリティ再認証により、Vercel 本番環境変数の `ONEDRIVE_REFRESH_TOKEN` が失効している。
- **直す場所**: コードではなく、Vercel 本番の `ONEDRIVE_REFRESH_TOKEN`。必要に応じて `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` と GitHub Actions Secret の `ONEDRIVE_REFRESH_TOKEN` も同じ値に更新する。

1. `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` を開き、`ONEDRIVE_CLIENT_ID` と `ONEDRIVE_CLIENT_SECRET` を確認する。
2. ブラウザで次の URL を開く。`<ONEDRIVE_CLIENT_ID>` は `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.env` の値に置き換える。

   ```text
   https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=<ONEDRIVE_CLIENT_ID>&scope=offline_access%20Files.ReadWrite.All&response_type=code&redirect_uri=http://localhost:8080
   ```

3. 実際に記事を保存している OneDrive アカウントでログインし、アクセス許可に同意する。
4. `http://localhost:8080` の接続エラー画面に戻っても正常。ブラウザのアドレスバーから `code=` 以降、`&` より前までの文字列をコピーする。
5. PowerShell で次を実行し、`refresh_token` を取得する。`<...>` は実値に置き換える。


   ```powershell
   $body = @{
     client_id = "<ONEDRIVE_CLIENT_ID>"
     client_secret = "<ONEDRIVE_CLIENT_SECRET>"
     code = "<手順4で取得したcode>"
     redirect_uri = "http://localhost:8080"
     grant_type = "authorization_code"
     scope = "Files.ReadWrite.All offline_access"
   }
   Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/common/oauth2/v2.0/token" -Body $body -ContentType "application/x-www-form-urlencoded"
   ```

6. 返ってきた JSON の `refresh_token` をコピーする。`access_token` ではなく `refresh_token` を使うこと。
7. Vercel Dashboard で `blog-vercel-dun` のプロジェクトを開き、`Settings` > `Environment Variables` へ進む。
8. Production の `ONEDRIVE_REFRESH_TOKEN` を手順6の値に更新する。
9. 必要なら Vercel Dashboard から Production を Redeploy する。環境変数更新だけで即時反映されない場合があるため、Redeploy した方が確実。
10. 復旧確認として、`https://blog-vercel-dun.vercel.app/api/articles?mode=shallow&h1Limit=0` が `200` になり、`articles` または `folders` を含む JSON を返すことを確認する。
11. `https://blog-vercel-dun.vercel.app/` を再読み込みし、記事一覧が表示されることを確認する。

### ③ 個人用 OneDrive での `$filter` 制限
- **事象**: 記事一覧取得時に HTTP 400 エラーが発生。
- **原因**: `me/drive/root/children` に対する `$filter=file ne null` は、ビジネス用（OneDrive for Business）では動くが、個人用 OneDrive アカウントではサポートされていない。
- **対策**: `$filter` を削除し、APIから返ってきた全アイテムを JavaScript 側の `.filter()` で `.md` ファイルのみに絞り込むように変更した。

### ④ Microsoft アカウントの「不一致」問題
- **事象**: Web上では「保存成功」と出るが、ローカルの PC フォルダ（Obsidian内）にファイルが一行に現れない。
- **原因**: 
  - ローカルPCの OneDrive アプリでログインしているアカウント（例: `mahha_punk@...`）と、
  - Azure Portal で認証（OAuth許可）したアカウント（例: `seahirodigital@...`）が別のものであった。
- **対策**: ローカルで同期中のアカウントで認証をやり直し、リフレッシュトークンを再取得して設定した。

### ⑤ OneDrive 同期の「時間差（ラグ）」
- **事象**: クラウド保存直後、PCのエクスプローラーを見てもファイルが見当たらない。
- **原因**: クラウド上には保存されているが、OneDrive クライアントがローカルへダウンロード（同期）するまでに数秒〜数十秒のタイムラグがあるため。
- **確認方法**: `onedrive.live.com`（Web版）を見てファイルがあれば保存自体は成功している。しばらく待つか、OneDriveアイコンの「同期」を手動で促せばローカルに現れる。

---

## 5. 運用上の注意

- **`.env` ファイル**: ローカルの `.env` には全パスワードが記載されています。絶対に GitHub に Push しないでください（`.gitignore` で保護済み）。
- **リフレッシュトークンの手動更新**: 万が一自動更新が止まった場合は、再度ブラウザから `code` を発行し、`ONEDRIVE_REFRESH_TOKEN` を手動で Vercel/GitHub に貼り直してください。

---

## 6. AppSheet と GitHub Actions のダイレクト連携（Webhookボタン）

AppSheetのボタンから直接 GitHub Actions（パイプラインなど）を起動する手順です。
（別のフローをボタン化したい場合も、全く同じ手順で [合言葉] や [カラム] を変えるだけで実装可能です）

### Step 1: GitHub 側の準備（受け入れ・認証）

1. **GitHub PAT（Personal Access Token）の取得**
   - GitHubの `Settings` > `Developer settings` > `Personal access tokens` > **`Fine-grained tokens`**> **`Token (clasaix)`** を開く。
   - `Generate new token(Classic)` で新しいトークンを作成。
   - **Repo**: `Repo` にチェック。
   - **Expiration**: `No Expiration` にすると良い。
   - 生成された `github_pat_...` の文字列を絶対にメモしておく（二度と表示されません）。
2. **GitHub Actions のトリガー設定**
   - リポジトリの `.github/workflows/XXX.yml` の `on:` の設定に以下を追加する。
     ```yaml
     on:
       repository_dispatch:
         types: [trigger-name] # 任意の合言葉
     ```

### Step 2: AppSheet 側の Automation (Bot) 作成

1. AppSheetの `Automation`（ロボットマーク）から `New Bot` を作成。
2. **Event (きっかけ)**: 
   - `Event Type`: `Data Change` -> `Updates` のみチェック。
   - `Table`: ボタンを設置したい対象のテーブルを選択。
   - `Condition`: `[ステータスカラム] = "実行"` （※ボタン押下で書き換わる値を指定）
3. **Process (Webhook)**: `Add a step` > `Call a webhook` を選択。
   - `Url`: `https://api.github.com/repos/【ユーザー名】/【リポジトリ名】/dispatches` (ダブルクォーテーションで囲む: `"https://..."`)
   - `HTTP Verb`: `Post`
   - `Body` (JSON形式): 
     ```json
     {
       "event_type": "trigger-name"  // Step1で決めた合言葉
     }
     ```
   - **`HTTP Headers`** (Addボタンで3つ追加。**UIが1枠しかない場合は、1枠にコロン区切りで記述する**):
     1. `Authorization: "Bearer github_pat_..."`
     2. `Accept: "application/vnd.github+json"`
     3. `X-GitHub-Api-Version` は **削除する**（※重要：トラブルシューティング参照）

### Step 3: AppSheet 側の Action (ボタン) 配置

1. AppSheetの `Actions` から `New Action` を作成。
2. `For a record of this table`: BotのEventと同じ対象テーブルを選択。
3. `Do this`: `Data: set the values of some columns in this row`
4. `Set these columns`: 
   - 左側：Step2で指定したカラム（例：`Caption` や `ステータス`）
   - 右側：`"実行"` （※ `=[Caption]="実行"` ではなく、必ず上書きする文字列そのものをダブルクォーテーションで囲んで入れる）
5. `Position`: 
   - 画面の右下に目立たせたい場合は **`Primary`**。
   - 特定の項目の横に置きたい場合は **`Inline`**。
6. (任意) UX向上のための `Behavior` 設定:
   - **確認ダイヤログ**: `Needs confirmation?` をONにし、`Confirmation Message` に `="実行しますか？"` と入力。
   - **ボタンのグレーアウト**: `Only if this condition is true` を `[ステータスカラム] <> "実行"` にする（押したら消えるようになる）。

---

### 【トラブルシューティング・初心者がハマる罠】

*   **罠①：HTTP Headersが1枠しかない**
    古い情報だと「Key」と「Value」で枠が分かれていますが、最近のAppSheet UIは1枠で `Header-Name: "Value"` と入力します。
*   **罠②：`Bearer` 付け忘れ問題 (401 Unauthorized)**
    `Authorization` の値は単なるトークン文字列ではなく、必ず手前に `Bearer ` (ベアラー＋半角スペース) が必要です。（例：`Authorization: "Bearer github_pat_..."`）
*   **罠③：日付が Date 型に勝手に変換される問題 (Invalid expression)**
    `X-GitHub-Api-Version: "2022-11-28"` を設定すると、AppSheetが気を利かせてカレンダーの `Date` (日付型) と勘違いし、文字と型が違うとエラー停止します。このバージョン指定ヘッダー自体が必須ではないため、**項目自体を丸ごと削除**するのが一番安全で早いです。
*   **罠④：アクションの設定で Yes/No 判定を書いてしまう**
    カラムの値を更新するActionで、枠に `=[Caption]="実行"` と書くと文字列の上書きではなく比較式（合っているかどうかのTrue/False）になってしまいます。純粋に `"実行"` とだけ入力します。
*   **罠⑤：ボタンが画面に出ない（テーブル不一致）**
    「ボタンが表示されない！」という場合の9割は、アクション設定の `For a record of this table` と、いま自分がアプリで見ているプレビュー画面の対象テーブルが異なっていることが原因です。

---

## 7. note予約投稿をGitHub Actionsで実行する仕組み

### なぜこの方式にしたか

以前の予約投稿は、GitHub Actionsの定期実行からVercelの`/api/note-post-cron`を呼び出し、Vercel側で予約ファイルを確認してからGitHub Actionsの投稿ジョブを起動する構成でした。

この構成では、Vercel Cron、VercelのServerless Function、Vercel側の環境変数、認証ヘッダーのどれかが崩れると予約投稿が止まります。そこで、予約監視と投稿ジョブ起動をGitHub Actions内で完結させる構成へ変更しました。

### 全体の流れ

1. `.github/workflows/note-post.yml` の `schedule` が定期的に起動する。
2. `.github/scripts/note_post_schedule_dispatch.py` が `data/note-post-schedules.json` をGitHub API経由で読む。
3. `status` が `scheduled` で、`publishAt` が現在時刻を過ぎた予約を探す。
4. 対象予約を `queued` に更新し、`queuedAt`、`queuedBy`、`dispatchAttempts` を記録する。
5. GitHub APIで `.github/workflows/note-post.yml` の `workflow_dispatch` を起動する。
6. `post-to-note` ジョブがOneDriveから記事本文を取得し、note.comへ投稿する。
7. 投稿成功後、同じ予約IDの状態を `published` に更新し、`publishedAt` と `publishedUrl` を保存する。

### 何分おきに予約を見に行くか

主監視は `.github/workflows/note-post.yml` の以下の設定で動きます。

```yaml
schedule:
  - cron: '*/5 * * * *'
```

これはUTC基準で5分おきに予約ファイルを確認する設定です。GitHub Actionsのscheduleは厳密な秒単位の実行保証ではないため、実際の起動は数分遅れることがあります。

バックアップ監視は `.github/workflows/note-post-schedule-backup.yml` の以下の設定で動きます。

```yaml
schedule:
  - cron: '2-59/5 * * * *'
```

これは毎時2分、7分、12分、17分のように、主監視から約2分ずらして5分おきに確認する設定です。主監視が混雑やGitHub側の都合で遅れた場合でも、バックアップ監視が近いタイミングで拾えるようにしています。

### 二重投稿を防ぐ仕組み

予約監視ジョブには以下の同時実行制御を入れています。

```yaml
concurrency:
  group: note-post-schedule-dispatch
  cancel-in-progress: false
```

主監視とバックアップ監視が同時に走っても、同じ `note-post-schedule-dispatch` グループとして直列化されます。これにより、同じ `data/note-post-schedules.json` を同時に更新して二重投稿するリスクを下げています。

また、期限到来した予約は投稿ジョブを起動する前に `queued` に更新されます。これにより、次の監視ジョブは同じ予約を通常の `scheduled` として扱わず、同じ記事を重複起動しにくくなります。

### 必要な権限とSecrets

予約監視ジョブには、以下の権限が必要です。

```yaml
permissions:
  actions: write
  contents: write
```

`contents: write` は `data/note-post-schedules.json` の状態を `scheduled`、`queued`、`published`、`error` に更新するために使います。

`actions: write` はGitHub APIから `workflow_dispatch` を呼び出し、投稿ジョブを起動するために使います。

Secretsは `GH_PAT` を優先して使います。`GH_PAT` が空の場合は `GITHUB_TOKEN` を使う設計です。ただし、リポジトリ設定や権限設定によっては `GITHUB_TOKEN` だけではworkflow dispatchが制限される可能性があるため、本番運用では `GH_PAT` をGitHub Actions Secretsに設定しておくことを推奨します。

### 関連ファイル

- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.github\workflows\note-post.yml`
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.github\workflows\note-post-schedule-backup.yml`
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\.github\scripts\note_post_schedule_dispatch.py`
- `C:\Users\mahha\OneDrive\開発\Blog_Vercel\data\note-post-schedules.json`
