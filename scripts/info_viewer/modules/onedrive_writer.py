import json
import os
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
DEFAULT_BASE_FOLDER = os.getenv(
    "INFO_VIEWER_ONEDRIVE_FOLDER",
    "Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer",
)


def normalize_youtube_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    try:
        parsed = urlparse(raw)
    except Exception:
        return raw

    host = parsed.netloc.lower()
    video_id = ""

    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/")[0]
    elif "youtube.com" in host:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/live/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) > 1:
                video_id = parts[1]

    if not video_id:
        return raw

    return f"https://www.youtube.com/watch?{urlencode({'v': video_id})}"


def _yaml_escape(value: str) -> str:
    escaped = str(value or "")
    escaped = escaped.replace("\\", "\\\\").replace('"', '\\"')
    return escaped


def _safe_name(value: str, max_length: Optional[int] = None) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "", str(value or ""))
    safe = re.sub(r"\s+", " ", safe).strip()
    if max_length:
        safe = safe[:max_length].rstrip()
    return safe or "untitled"


def _date_prefix(date_text: str) -> str:
    text = str(date_text or "").strip()
    if text:
        for candidate in [text, text[:10], text.replace("/", "-")]:
            try:
                return datetime.fromisoformat(candidate.replace("Z", "+00:00")).strftime("%Y%m%d")
            except ValueError:
                try:
                    return datetime.strptime(candidate, "%Y-%m-%d").strftime("%Y%m%d")
                except ValueError:
                    continue
    return datetime.now().strftime("%Y%m%d")


def _prepend_video_url(markdown_body: str, video_url: str) -> str:
    body = str(markdown_body or "").strip()
    normalized_url = normalize_youtube_url(video_url or "")
    if not normalized_url:
        return body

    if body.startswith(normalized_url):
        return body

    if not body:
        return f"{normalized_url}\n"

    return f"{normalized_url}\n\n{body}"


def _build_markdown_document(markdown_body: str, metadata: dict[str, Any]) -> str:
    prepared_markdown = _prepend_video_url(markdown_body, metadata.get("video_url", ""))
    frontmatter = [
        "---",
        f'title: "{_yaml_escape(metadata.get("title", ""))}"',
        f'video_url: "{_yaml_escape(metadata.get("video_url", ""))}"',
        f'channel_name: "{_yaml_escape(metadata.get("channel_name", ""))}"',
        f'channel_url: "{_yaml_escape(metadata.get("channel_url", ""))}"',
        f'published_at: "{_yaml_escape(metadata.get("published_at", ""))}"',
        f'duration: "{_yaml_escape(metadata.get("duration", ""))}"',
        f'sheet_status: "{_yaml_escape(metadata.get("sheet_status", ""))}"',
        f'generated_at: "{_yaml_escape(metadata.get("generated_at", ""))}"',
        "---",
        "",
    ]
    return "\n".join(frontmatter) + prepared_markdown + "\n"


def _encode_path(path: str) -> str:
    return "/".join(quote(part) for part in str(path or "").split("/") if part)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.S)
    if not match:
        return {}, text

    meta_block, body = match.groups()
    metadata: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = value.strip()
        if (normalized.startswith('"') and normalized.endswith('"')) or (
            normalized.startswith("'") and normalized.endswith("'")
        ):
            normalized = normalized[1:-1]
        normalized = normalized.replace('\\"', '"').replace("\\\\", "\\")
        metadata[key.strip()] = normalized
    return metadata, body


def _get_access_token() -> str:
    client_id = os.getenv("ONEDRIVE_CLIENT_ID")
    client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET")
    refresh_token = os.getenv("ONEDRIVE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("OneDrive 認証情報が不足しています。")

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "Files.ReadWrite.All offline_access",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _request(method: str, url: str, token: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=120, **kwargs)


def _ensure_folder_path(path: str, token: str):
    clean_path = str(path or "").strip("/ ")
    if not clean_path:
        return None

    current_path = ""
    parent_id = None

    for segment in [part for part in clean_path.split("/") if part]:
        current_path = f"{current_path}/{segment}" if current_path else segment
        lookup_url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(current_path)}"
        lookup_res = _request("GET", lookup_url, token)
        if lookup_res.ok:
            parent_id = lookup_res.json()["id"]
            continue
        if lookup_res.status_code != 404:
            lookup_res.raise_for_status()

        create_url = (
            f"{GRAPH_API_BASE}/me/drive/root/children"
            if parent_id is None
            else f"{GRAPH_API_BASE}/me/drive/items/{parent_id}/children"
        )
        create_res = _request(
            "POST",
            create_url,
            token,
            headers={"Content-Type": "application/json"},
            json={
                "name": segment,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "replace",
            },
        )
        create_res.raise_for_status()
        parent_id = create_res.json()["id"]

    return parent_id


def upload_text(relative_path: str, content: str, content_type: str = "text/plain; charset=utf-8") -> dict[str, Any]:
    token = _get_access_token()
    relative_path = str(relative_path).strip("/ ")
    parent = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
    if parent:
        _ensure_folder_path(f"{DEFAULT_BASE_FOLDER}/{parent}", token)
    else:
        _ensure_folder_path(DEFAULT_BASE_FOLDER, token)

    full_path = f"{DEFAULT_BASE_FOLDER}/{relative_path}" if relative_path else DEFAULT_BASE_FOLDER
    upload_url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(full_path)}:/content"
    response = _request(
        "PUT",
        upload_url,
        token,
        headers={"Content-Type": content_type},
        data=content.encode("utf-8"),
    )
    response.raise_for_status()
    return response.json()


def upload_json(relative_path: str, data: dict[str, Any]) -> dict[str, Any]:
    return upload_text(
        relative_path,
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )


def download_text(relative_path: str) -> Optional[str]:
    token = _get_access_token()
    relative_path = str(relative_path).strip("/ ")
    full_path = f"{DEFAULT_BASE_FOLDER}/{relative_path}" if relative_path else DEFAULT_BASE_FOLDER
    url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(full_path)}:/content"
    response = _request("GET", url, token)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def download_json(relative_path: str) -> Optional[dict[str, Any]]:
    text = download_text(relative_path)
    if text is None or not text.strip():
        return None
    return json.loads(text)


def upload_markdown(
    channel_name: str,
    title: str,
    published_at: str,
    markdown_body: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    channel_folder = _safe_name(channel_name)
    safe_title = _safe_name(title, max_length=30)
    filename = f"{_date_prefix(published_at)}_{safe_title}.md"
    document = _build_markdown_document(
        markdown_body,
        {
            **metadata,
            "title": title,
            "channel_name": channel_name,
            "published_at": published_at,
            "generated_at": datetime.now().isoformat(),
        },
    )
    upload = upload_text(f"{channel_folder}/{filename}", document)
    return {
        "id": upload.get("id", ""),
        "name": upload.get("name", filename),
        "webUrl": upload.get("webUrl", ""),
        "channelFolder": channel_folder,
        "relativePath": f"{channel_folder}/{filename}",
        "title": title,
        "videoUrl": metadata.get("video_url", ""),
        "publishedAt": published_at,
    }


def _list_children(path: str, token: str) -> list[dict[str, Any]]:
    url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(path)}:/children?$top=200"
    response = _request("GET", url, token)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("value", [])


def _download_item_text(item_id: str, token: str, byte_range: Optional[str] = None) -> str:
    headers: dict[str, str] = {}
    if byte_range:
        headers["Range"] = byte_range
    url = f"{GRAPH_API_BASE}/me/drive/items/{item_id}/content"
    response = _request("GET", url, token, headers=headers)
    if not response.ok and response.status_code != 206:
        response.raise_for_status()
    return response.text


def list_saved_articles() -> list[dict[str, Any]]:
    token = _get_access_token()
    _ensure_folder_path(DEFAULT_BASE_FOLDER, token)
    channels = _list_children(DEFAULT_BASE_FOLDER, token)
    saved_articles: list[dict[str, Any]] = []

    for folder in channels:
        if not folder.get("folder"):
            continue
        folder_name = folder.get("name", "")
        files = _list_children(f"{DEFAULT_BASE_FOLDER}/{folder_name}", token)
        for file_item in files:
            file_name = file_item.get("name", "")
            if not file_name.endswith(".md"):
                continue
            preview_text = _download_item_text(file_item["id"], token, byte_range="bytes=0-8191")
            metadata, _ = parse_frontmatter(preview_text)
            saved_articles.append(
                {
                    "fileId": file_item.get("id", ""),
                    "fileName": file_name,
                    "webUrl": file_item.get("webUrl", ""),
                    "lastModified": file_item.get("lastModifiedDateTime", ""),
                    "title": metadata.get("title") or file_name[:-3],
                    "youtubeUrl": metadata.get("video_url", ""),
                    "youtubeUrlNormalized": normalize_youtube_url(metadata.get("video_url", "")),
                    "channelName": metadata.get("channel_name") or folder_name,
                    "channelUrl": metadata.get("channel_url", ""),
                    "publishedAt": metadata.get("published_at", ""),
                    "duration": metadata.get("duration", ""),
                    "sheetStatus": metadata.get("sheet_status", ""),
                    "channelFolder": folder_name,
                    "relativePath": f"{folder_name}/{file_name}",
                }
            )

    return saved_articles
