# Vibe Blog Engine - 仕様書 (System Blueprint)

YouTube動画からAIでブログ記事を自動生成し、OneDriveで管理・編集・公開するためのフルスタック・オートメーション・システム。

---

## 1. システム概要 (Architecture)

本プロジェクトは以下の3つのコンポーネントで構成されています。

1.  **Pipeline (scripts/pipeline)**: GitHub Actions で動作する自動記事生成エンジン。
2.  **API (api/)**: Vercel Serverless Functions。OneDriveとの通信およびパイプライン起動。
3.  **Frontend (public/index.html)**: 記事の閲覧・編集・リネーム・保存、および手動トリガーを行う管理画面。

---

## 2. ブログ生成パイプライン仕様

### 2.1 実行トリガー
-   **スケジュール実行**: 毎日 JST 9:00 (UTC 0:00)。
-   **手動実行**: GitHub UI または Vibe Blog 画面上の「パイプライン実行」ボタン。

### 2.2 スプレッドシート読み込み仕様 (Google Sheets)
-   **認証**: `GOOGLE_SERVICE_ACCOUNT_JSON` を使用。
-   **対象シート**: `SHEET_NAME` (デフォルト: "動画リスト")。
-   **抽出ルール**:
    -   「状況」列の値が `単品`, `複数`, `情報` のいずれかであること。
    -   「動画URL」列に値が入っていること。
-   **処理フロー**:
    1. 待機中の行を取得。
    2. 動画ごとに文字起こし取得、AI生成、OneDrive保存を実行。
    3. 成功した場合、該当行の「状況」を `完了` に更新。

### 2.3 AI 3段階生成ロジック (Gemini 2.5 Flash)
プロンプトは `scripts/pipeline/prompts/` フォルダ内の外部ファイルから読み込まれます。

1.  **Step 1: Drafter (ライター)**
    -   `01-writer-prompt.txt` を使用。
    -   スプレッドシートの「状況」に応じて `[単品]`, `[情報]`, `[複数]` のプロンプトを切り替え。
2.  **Step 2: Editor (編集者)**
    -   `02-editor-prompt.txt` を使用。
    -   文章のリズム、SEOキーワードの配置、モバイル最適化を実施。
3.  **Step 3: Director (編集長)**
    -   `03-director-prompt.txt` を使用。
    -   最終トーン調整、メタディスクリプション（YAML）、画像挿入ポイントの指示。

### 2.4 保存仕様 (OneDrive)
-   **フォルダ**: `ONEDRIVE_FOLDER` (デフォルト: "Blog_Articles")。
-   **ファイル名規則**: `YYYYMMDD_HHMM_動画タイトル.md`
-   **文字コード**: UTF-8。

---

## 3. 管理画面 (Vibe Blog UI) 仕様

### 3.1 記事管理 (Sidebar)
-   **フォルダ階層表示**: OneDrive上の実際のディレクトリ構造（エクスプローラー形式）を再帰的に取得して表示。
-   **UI操作**: 横幅変更（ドラッグリサイズ）および開閉（トグル）が可能。
-   **新規作成**: ルート直下に新しいMarkdownファイルを作成。

### 3.2 エディタ & タイトル編集
-   **タイトル編集**: ✏️ アイコンでリネーム。編集確定時に **OneDrive上の実ファイル名もリネーム（PATCH API）** され、永続化される。
-   **自動保存**: なし（明示的な「保存」ボタン押下、または Ctrl+S）。
-   **リサイズ**: エディタとプレビューの境界をドラッグで調整可能。

### 3.3 認証 & トークン
-   **OAuth ローテーション**: API呼び出しごとにアクセストークンを再取得し、リフレッシュトークンが更新された場合は **Vercel環境変数を自動書き換え** して維持する（API側の `updateVercelEnvToken`）。

---

## 4. 開発・運用ルール

### 4.1 安全管理
-   ファイルの書き込み・変更・削除、および破壊的なコマンド実行前には必ず作業計画を報告し、ユーザーの確認 (`y/n`) を取ること。
-   ただし、`winmacsync`（同期スクリプト）および `/yt-note-edited-article` 関連の半自動ワークフローは自律実行可能。

### 4.2 コミュニケーション
-   全ての応答、コード内コメント、タスク表示は **日本語** で行うこと。

### 4.3 同期管理
-   グローバルスキルや設定（`GEMINI.md` 等）を変更した際は、OneDriveへの反映のため即座に `winmacsync` を実行すること。

---

## 5. 環境変数 (Required Environment Variables)

-   `GOOGLE_SERVICE_ACCOUNT_JSON`: スプレッドシート用サービスアカウント鍵。
-   `SPREADSHEET_ID`: 管理用スプレッドシートのID。
-   `SHEET_NAME`: 読み込み対象のシート名。
-   `APIFY_API_KEY`: YouTube文字起こし取得用。
-   `GEMINI_API_KEY`: Google AI APIキー。
-   `ONEDRIVE_CLIENT_ID / SECRET`: Microsoft Graph API 認証情報。
-   `ONEDRIVE_REFRESH_TOKEN`: OneDriveアクセス維持用。
-   `ONEDRIVE_FOLDER`: OneDrive内のルートフォルダ名。
-   `VERCEL_TOKEN`: 環境変数自動更新用（Vercel Personal Access Token）。
-   `VERCEL_PROJECT_ID`: VercelプロジェクトID。
