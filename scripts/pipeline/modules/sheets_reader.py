"""
Google Sheets クライアント (GitHub Actions 対応版)
環境変数 GOOGLE_SERVICE_ACCOUNT_JSON からサービスアカウント鍵を読み込む
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials

# Google APIに必要なスコープ
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def _get_gs_client():
    """環境変数またはファイルからサービスアカウント認証を取得"""
    # 方法1: 環境変数からJSON文字列を読み込む (GitHub Actions用)
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    # 方法2: ローカルファイルから読み込む (ローカル開発用)
    sa_file = os.path.join(os.path.dirname(__file__), "..", "service_account.json")
    if os.path.exists(sa_file):
        creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        return gspread.authorize(creds)

    raise FileNotFoundError(
        "❌ サービスアカウント認証情報が見つかりません。\n"
        "   環境変数 GOOGLE_SERVICE_ACCOUNT_JSON を設定するか、\n"
        "   service_account.json を配置してください。"
    )


def get_pending_rows(spreadsheet_id: str, sheet_name: str, status_list: list[str] = None) -> list[dict]:
    """
    スプレッドシートからフィルター条件に合う行を取得する
    """
    if status_list is None:
        status_list = ["単品", "複数", "情報", "量産元"]

    print(f"📊 Google Sheetsに接続中...")
    try:
        client = _get_gs_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        # 全データを取得
        all_records = worksheet.get_all_records()
        print(f"   シート名: {sheet_name} | 全行数: {len(all_records)}")

        # 「状況」列でフィルタリング
        pending = [
            row for row in all_records
            if str(row.get("状況", "")).strip() in status_list and row.get("動画URL", "").strip()
        ]
        print(f"   処理対象 (状況={status_list}): {len(pending)}件")

        return pending
    except Exception as e:
        print(f"   ❌ スプレッドシート取得エラー: {e}")
        if "spreadsheetNotFound" in str(e):
            print("   💡 ヒント: スプレッドシートをサービスアカウントのメールアドレスに共有しましたか？")
        raise


def update_status(spreadsheet_id: str, sheet_name: str, video_url: str, new_status: str = "完了"):
    """
    指定URLの行の「状況」列を上書き更新する
    """
    try:
        client = _get_gs_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        cell = worksheet.find(video_url)

        if cell:
            headers = worksheet.row_values(1)
            try:
                status_col = headers.index("状況") + 1
                worksheet.update_cell(cell.row, status_col, new_status)
                print(f"   ✅ ステータス更新: 行{cell.row} → 「{new_status}」")
            except ValueError:
                print(f"   ⚠️ 「状況」列が見つかりません。")
        else:
            print(f"   ⚠️ URLが見つかりません: {video_url}")

    except Exception as e:
        print(f"   ❌ スプレッドシート更新エラー: {e}")
