"""周辺機器ジョブ、管理JSON、本文専用MarkdownをOneDriveへ保存する。"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests


GRAPH_API = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
RETRYABLE = {429, 500, 502, 503, 504}
CONTROL_FOLDER = os.getenv("ACCESSORIES_CONTROL_FOLDER", "Blog_Vercel_Accessories_Control").strip("/")
AFFILIATE_FILE_PATH = os.getenv(
    "ACCESSORIES_AFFILIATE_FILE_PATH",
    "開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt",
).strip("/")
_TOKEN_CACHE: dict[str, Any] = {"access_token": "", "expires_at": 0.0}
JST = timezone(timedelta(hours=9))


def _encode_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in str(path).strip("/").split("/") if part)


def _access_token() -> str:
    if _TOKEN_CACHE["access_token"] and time.time() < float(_TOKEN_CACHE["expires_at"]) - 60:
        return str(_TOKEN_CACHE["access_token"])
    required = {
        "client_id": os.getenv("ONEDRIVE_CLIENT_ID", ""),
        "client_secret": os.getenv("ONEDRIVE_CLIENT_SECRET", ""),
        "refresh_token": os.getenv("ONEDRIVE_REFRESH_TOKEN", ""),
    }
    if not all(required.values()):
        raise ValueError("OneDrive認証情報が不足しています")
    response = requests.post(
        TOKEN_URL,
        data={
            **required,
            "grant_type": "refresh_token",
            "scope": "Files.ReadWrite.All offline_access",
        },
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"OneDrive token取得失敗: HTTP {response.status_code}")
    data = response.json()
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError("OneDrive token取得結果が空です")
    if data.get("refresh_token"):
        os.environ["ONEDRIVE_REFRESH_TOKEN"] = str(data["refresh_token"])
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    return token


def _request(method: str, url: str, *, token: str, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = f"Bearer {token}"
    for attempt in range(4):
        response = requests.request(method, url, headers=headers, timeout=120, **kwargs)
        if response.status_code not in RETRYABLE or attempt == 3:
            return response
        retry_after = response.headers.get("Retry-After", "")
        wait = int(retry_after) if retry_after.isdigit() else min(2**attempt, 8)
        time.sleep(wait)
    return response


def _ensure_folder(path: str, token: str) -> str:
    current = ""
    parent_id = ""
    for segment in [part for part in path.strip("/").split("/") if part]:
        current = f"{current}/{segment}" if current else segment
        lookup = _request(
            "GET",
            f"{GRAPH_API}/me/drive/root:/{_encode_path(current)}?$select=id",
            token=token,
        )
        if lookup.ok:
            parent_id = lookup.json()["id"]
            continue
        if lookup.status_code != 404:
            raise RuntimeError(f"OneDriveフォルダ確認失敗: HTTP {lookup.status_code}")
        url = (
            f"{GRAPH_API}/me/drive/items/{parent_id}/children"
            if parent_id
            else f"{GRAPH_API}/me/drive/root/children"
        )
        created = _request(
            "POST",
            url,
            token=token,
            headers={"Content-Type": "application/json"},
            json={"name": segment, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        )
        if created.status_code == 409:
            # 自動ワーカーと手動復旧が同時に初期化しても、先に作成されたフォルダを再利用する。
            raced_lookup = _request(
                "GET",
                f"{GRAPH_API}/me/drive/root:/{_encode_path(current)}?$select=id",
                token=token,
            )
            if raced_lookup.ok:
                parent_id = raced_lookup.json()["id"]
                continue
        if not created.ok:
            raise RuntimeError(f"OneDriveフォルダ作成失敗: HTTP {created.status_code}")
        parent_id = created.json()["id"]
    return parent_id


def upload_text(path: str, text: str, *, content_type: str, if_match: str = "") -> dict[str, Any]:
    token = _access_token()
    clean = path.strip("/")
    parent = clean.rsplit("/", 1)[0] if "/" in clean else ""
    if parent:
        _ensure_folder(parent, token)
    headers = {"Content-Type": content_type}
    if if_match:
        headers["If-Match"] = if_match
    response = _request(
        "PUT",
        f"{GRAPH_API}/me/drive/root:/{_encode_path(clean)}:/content",
        token=token,
        headers=headers,
        data=text.encode("utf-8"),
    )
    if response.status_code == 412:
        raise RuntimeError("OneDriveジョブは他のワーカーが更新しました")
    if not response.ok:
        raise RuntimeError(f"OneDrive保存失敗: HTTP {response.status_code}")
    return response.json()


def upload_json(path: str, value: dict[str, Any], *, if_match: str = "") -> dict[str, Any]:
    return upload_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
        if_match=if_match,
    )


def download_json(path: str) -> tuple[dict[str, Any], str]:
    token = _access_token()
    metadata = _request(
        "GET",
        f"{GRAPH_API}/me/drive/root:/{_encode_path(path)}?$select=id,eTag",
        token=token,
    )
    if not metadata.ok:
        raise FileNotFoundError(f"OneDrive JSONが見つかりません: {path}")
    meta = metadata.json()
    content = _request("GET", f"{GRAPH_API}/me/drive/items/{meta['id']}/content", token=token)
    if not content.ok:
        raise RuntimeError(f"OneDrive JSON取得失敗: HTTP {content.status_code}")
    etag = str(meta.get("eTag", "")) or metadata.headers.get("ETag", "")
    return content.json(), etag


def download_article(file_id: str) -> str:
    token = _access_token()
    response = _request("GET", f"{GRAPH_API}/me/drive/items/{quote(file_id, safe='')}/content", token=token)
    if not response.ok:
        raise RuntimeError(f"親記事取得失敗: HTTP {response.status_code}")
    return _decode_utf8_text(response.content)


def _decode_utf8_text(content: bytes) -> str:
    """OneDriveがcharsetを返さなくてもMarkdownをUTF-8として正しく復元する。"""
    try:
        return bytes(content).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RuntimeError("OneDriveテキストがUTF-8ではありません") from error


def download_text_path(path: str) -> str:
    token = _access_token()
    response = _request(
        "GET",
        f"{GRAPH_API}/me/drive/root:/{_encode_path(path)}:/content",
        token=token,
    )
    if not response.ok:
        raise RuntimeError(f"OneDriveテキスト取得失敗: HTTP {response.status_code}")
    return _decode_utf8_text(response.content)


def job_path(job_id: str) -> str:
    return f"{CONTROL_FOLDER}/jobs/{job_id}.json"


def read_job(job_id: str) -> tuple[dict[str, Any], str]:
    return download_json(job_path(job_id))


def save_job(job: dict[str, Any], *, if_match: str = "") -> dict[str, Any]:
    return upload_json(job_path(job["job_id"]), job, if_match=if_match)


def acquire_job(job_id: str, owner: str, lease_minutes: int = 30) -> tuple[dict[str, Any], str]:
    job, etag = read_job(job_id)
    now = datetime.now(timezone.utc)
    expires_text = str(job.get("lease", {}).get("expires_at", ""))
    try:
        expires = datetime.fromisoformat(expires_text.replace("Z", "+00:00")) if expires_text else None
    except ValueError:
        expires = None
    if job.get("state") == "completed":
        raise RuntimeError("完了済みジョブは再処理しません")
    if job.get("state") == "processing" and expires and expires > now:
        raise RuntimeError("ジョブは他のワーカーが処理中です")
    if job.get("state") not in {"pending", "failed", "processing"}:
        raise RuntimeError(f"実行できないジョブ状態です: {job.get('state')}")
    job["state"] = "processing"
    job["attempt_count"] = int(job.get("attempt_count", 0)) + 1
    job["lease"] = {
        "owner": owner,
        "expires_at": (now + timedelta(minutes=lease_minutes)).isoformat().replace("+00:00", "Z"),
        "etag": etag,
    }
    saved = save_job(job, if_match=etag)
    return job, saved.get("eTag", "") or saved.get("@odata.etag", "")


def child_folder_name(job: dict[str, Any]) -> str:
    created_at = str(job.get("created_at", "")).strip()
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"ジョブ作成日時が不正です: {created_at}") from error
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    timestamp = created.astimezone(JST).strftime("%Y%m%d_%H%M")
    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", str(job.get("parent", {}).get("title", "")))
    title = re.sub(r"\s+", " ", title).strip(" .")[:10].rstrip(" .")
    if not title:
        raise ValueError("親記事タイトルから保存フォルダ名を作成できません")
    return f"{timestamp}_{title}"


def save_child_article(job: dict[str, Any], filename: str, markdown: str) -> dict[str, Any]:
    article_root = os.getenv("ONEDRIVE_FOLDER", "Blog_Articles").strip("/")
    return upload_text(
        f"{article_root}/周辺機器/{child_folder_name(job)}/{filename}",
        markdown,
        content_type="text/markdown; charset=utf-8",
    )
