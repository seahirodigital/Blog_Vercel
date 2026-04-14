import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

import requests

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
UPLOAD_RETRY_DELAYS = (2, 5, 10)
DEFAULT_BASE_FOLDER = os.getenv(
    "XPOST_BLOG_ONEDRIVE_FOLDER",
    "Obsidian in Onedrive 202602/Vercel_Blog/X投稿",
)


def normalize_x_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""

    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
    except Exception:
        return raw

    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.strip("/")
    parts = [part for part in path.split("/") if part]

    if host not in {"x.com", "twitter.com"}:
        return raw

    if len(parts) >= 3 and parts[1] == "status":
        post_id = parts[2]
        return f"https://x.com/i/status/{post_id}"

    if len(parts) >= 3 and parts[0] == "i" and parts[1] in {"status", "article"}:
        post_id = parts[2]
        return f"https://x.com/i/{parts[1]}/{post_id}"

    return raw


def extract_post_id(url: str) -> str:
    normalized = normalize_x_url(url)
    if not normalized:
        return ""

    try:
        parsed = urlparse(normalized)
    except Exception:
        return ""

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) >= 3 and parts[0] == "i":
        return parts[2]
    return ""


def _yaml_escape(value: str) -> str:
    escaped = str(value or "")
    escaped = escaped.replace("\\", "\\\\").replace('"', '\\"')
    return escaped


def _safe_name(value: str, max_length: int = 48) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "", str(value or ""))
    safe = re.sub(r"\s+", " ", safe).strip()
    safe = safe[:max_length].rstrip()
    return safe or "untitled"


def _date_prefix(date_text: str) -> str:
    text = str(date_text or "").strip()
    if text:
        for candidate in (text, text[:10], text.replace("/", "-")):
            try:
                return datetime.fromisoformat(candidate.replace("Z", "+00:00")).strftime("%Y%m%d")
            except ValueError:
                continue
    return datetime.now().strftime("%Y%m%d")


def build_record_folder_name(post_url: str, published_at: str, title: str) -> str:
    date_prefix = _date_prefix(published_at)
    post_id = extract_post_id(post_url) or hashlib.md5(str(post_url or title).encode("utf-8")).hexdigest()[:8]
    return f"{date_prefix}_{post_id}_{_safe_name(title, max_length=32)}"


def _build_markdown_document(markdown_body: str, metadata: dict[str, Any]) -> str:
    preferred_order = [
        "doc_type",
        "title",
        "post_url",
        "normalized_post_url",
        "tweet_id",
        "article_id",
        "source_provider",
        "source_provider_detail",
        "author_name",
        "author_screen_name",
        "published_at",
        "favorite_count",
        "repost_count",
        "reply_count",
        "quote_count",
        "bookmark_count",
        "view_count",
        "discord_message_id",
        "discord_jump_url",
        "source_file_id",
        "source_relative_path",
        "generated_at",
    ]
    frontmatter = ["---"]
    written = set()
    for key in preferred_order:
        if key in metadata and metadata.get(key) not in (None, ""):
            frontmatter.append(f'{key}: "{_yaml_escape(metadata.get(key, ""))}"')
            written.add(key)

    for key in sorted(metadata.keys()):
        if key in written or metadata.get(key) in (None, ""):
            continue
        frontmatter.append(f'{key}: "{_yaml_escape(metadata.get(key, ""))}"')

    frontmatter.extend(["---", ""])
    return "\n".join(frontmatter) + str(markdown_body or "").strip() + "\n"


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
        normalized = normalized.replace('\\"', '"').replace('\\\\', '\\')
        metadata[key.strip()] = normalized
    return metadata, body


def strip_frontmatter(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body.strip()


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
    full_path = f"{DEFAULT_BASE_FOLDER}/{relative_path}" if relative_path else DEFAULT_BASE_FOLDER
    upload_url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(full_path)}:/content"

    for attempt, wait_seconds in enumerate((0, *UPLOAD_RETRY_DELAYS), start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            if parent:
                _ensure_folder_path(f"{DEFAULT_BASE_FOLDER}/{parent}", token)
            else:
                _ensure_folder_path(DEFAULT_BASE_FOLDER, token)

            response = _request(
                "PUT",
                upload_url,
                token,
                headers={"Content-Type": content_type},
                data=content.encode("utf-8"),
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else 0
            if status_code not in RETRYABLE_STATUS_CODES or attempt > len(UPLOAD_RETRY_DELAYS):
                raise
        except requests.RequestException:
            if attempt > len(UPLOAD_RETRY_DELAYS):
                raise

    raise RuntimeError(f"upload failed without response: {relative_path}")


def upload_json(relative_path: str, data: dict[str, Any]) -> dict[str, Any]:
    return upload_text(
        relative_path,
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )


def download_text(relative_path: str) -> str | None:
    token = _get_access_token()
    relative_path = str(relative_path).strip("/ ")
    full_path = f"{DEFAULT_BASE_FOLDER}/{relative_path}" if relative_path else DEFAULT_BASE_FOLDER
    url = f"{GRAPH_API_BASE}/me/drive/root:/{_encode_path(full_path)}:/content"
    response = _request("GET", url, token)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def download_json(relative_path: str) -> dict[str, Any] | None:
    text = download_text(relative_path)
    if text is None or not text.strip():
        return None
    return json.loads(text)


def upload_source_markdown(source_title: str, published_at: str, markdown_body: str, metadata: dict[str, Any]) -> dict[str, Any]:
    folder_name = build_record_folder_name(metadata.get("post_url", ""), published_at, source_title)
    filename = f"{_date_prefix(published_at)}_元投稿_{_safe_name(source_title, 42)}.md"
    document = _build_markdown_document(
        markdown_body,
        {
            **metadata,
            "doc_type": "source",
            "title": source_title,
            "generated_at": datetime.now().isoformat(),
        },
    )
    upload = upload_text(f"{folder_name}/{filename}", document)
    return {
        "id": upload.get("id", ""),
        "name": upload.get("name", filename),
        "webUrl": upload.get("webUrl", ""),
        "relativePath": f"{folder_name}/{filename}",
        "folderName": folder_name,
        "title": source_title,
    }


def upload_blog_markdown(title: str, published_at: str, markdown_body: str, metadata: dict[str, Any]) -> dict[str, Any]:
    folder_name = metadata.get("folder_name") or build_record_folder_name(metadata.get("post_url", ""), published_at, title)
    filename = f"{_date_prefix(published_at)}_ブログ_{_safe_name(title, 42)}.md"
    document = _build_markdown_document(
        markdown_body,
        {
            **metadata,
            "doc_type": "blog",
            "title": title,
            "generated_at": datetime.now().isoformat(),
        },
    )
    upload = upload_text(f"{folder_name}/{filename}", document)
    return {
        "id": upload.get("id", ""),
        "name": upload.get("name", filename),
        "webUrl": upload.get("webUrl", ""),
        "relativePath": f"{folder_name}/{filename}",
        "folderName": folder_name,
        "title": title,
    }
