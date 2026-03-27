"""
OneDrive 同期モジュール (Microsoft Graph API)
生成されたMarkdownファイルをOneDriveへアップロードする
"""

import os
import requests
from typing import Optional

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# OneDrive内の保存先フォルダパス
ONEDRIVE_FOLDER = os.getenv("ONEDRIVE_FOLDER", "Blog_Articles")


def _get_access_token() -> str:
    """リフレッシュトークンからアクセストークンを取得"""
    client_id = os.getenv("ONEDRIVE_CLIENT_ID")
    client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET")
    refresh_token = os.getenv("ONEDRIVE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "❌ OneDrive認証情報が不足しています。\n"
            "   ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET, ONEDRIVE_REFRESH_TOKEN を設定してください。"
        )

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "Files.ReadWrite.All offline_access"
    }

    response = requests.post(TOKEN_URL, data=data)
    response.raise_for_status()
    token_data = response.json()

    # リフレッシュトークンが更新された場合は環境変数に反映（ログ出力のみ）
    new_refresh = token_data.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        print("   ℹ️  リフレッシュトークンが更新されました（手動で環境変数の更新が必要です）")

    return token_data["access_token"]


def upload_markdown(filename: str, content: str) -> Optional[str]:
    """
    MarkdownファイルをOneDriveにアップロードする

    Args:
        filename: ファイル名 (例: "20260327_1725_記事タイトル.md")
        content: Markdown文字列

    Returns:
        OneDrive上のファイルURL または None
    """
    try:
        access_token = _get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/plain"
        }

        # OneDriveにアップロード（上書きモード: conflict=replace）
        upload_url = (
            f"{GRAPH_API_BASE}/me/drive/root:/{ONEDRIVE_FOLDER}/{filename}:/content"
        )

        response = requests.put(
            upload_url,
            headers=headers,
            data=content.encode("utf-8")
        )
        response.raise_for_status()
        result = response.json()

        web_url = result.get("webUrl", "")
        print(f"   ☁️  OneDriveアップロード完了: {filename}")
        print(f"      URL: {web_url}")
        return web_url

    except Exception as e:
        print(f"   ❌ OneDriveアップロードエラー: {e}")
        return None


def list_articles() -> list[dict]:
    """
    OneDriveフォルダ内の記事一覧を取得する

    Returns:
        [{"name": "ファイル名.md", "id": "ファイルID", "lastModified": "...", "webUrl": "..."}]
    """
    try:
        access_token = _get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        url = f"{GRAPH_API_BASE}/me/drive/root:/{ONEDRIVE_FOLDER}:/children"
        params = {
            "$filter": "file ne null",
            "$orderby": "lastModifiedDateTime desc",
            "$select": "id,name,lastModifiedDateTime,webUrl,size"
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        articles = []
        for item in data.get("value", []):
            if item["name"].endswith(".md"):
                articles.append({
                    "id": item["id"],
                    "name": item["name"],
                    "lastModified": item["lastModifiedDateTime"],
                    "webUrl": item.get("webUrl", ""),
                    "size": item.get("size", 0)
                })

        return articles

    except Exception as e:
        print(f"   ❌ 記事一覧取得エラー: {e}")
        return []


def get_article_content(file_id: str) -> Optional[str]:
    """OneDriveからファイル内容を取得"""
    try:
        access_token = _get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        url = f"{GRAPH_API_BASE}/me/drive/items/{file_id}/content"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.text

    except Exception as e:
        print(f"   ❌ ファイル読み込みエラー: {e}")
        return None
