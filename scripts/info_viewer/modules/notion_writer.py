from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from . import onedrive_writer


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = os.getenv("INFO_VIEWER_NOTION_VERSION", "2022-06-28")
DEFAULT_NOTION_DATABASE_ID = "368c4a3b7cc280989667da064731ee7a"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_DELAYS = (1.5, 3, 6)
APPEND_ON_EXISTING = str(os.getenv("INFO_VIEWER_NOTION_APPEND_ON_EXISTING", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}
LOCAL_NOTION_ENV_FILE = os.getenv(
    "INFO_VIEWER_NOTION_ENV_FILE",
    r"C:\Users\mahha\OneDrive\開発\Notion_skill\Youtube_archive_note\.env",
)
NOTION_ENV_KEYS = {
    "INFO_VIEWER_NOTION_API_KEY",
    "INFO_VIEWER_NOTION_DATABASE_ID",
    "INFO_VIEWER_NOTION_DATABASE_URL",
    "NOTION_API_KEY",
    "NOTION_TOKEN",
    "NOTION_DATABASE_ID",
    "NOTION_DATABASE_URL",
}

YOUTUBE_URL_ALIASES = [
    "Youtube",
    "YouTube",
    "Youtube URL",
    "YouTube URL",
    "youtube_url",
    "youtube",
    "動画URL",
    "動画 URL",
    "Video URL",
    "URL",
    "url",
]

# Notionの「人物」multi_selectへ入れる正式名と、動画タイトル側の表記ゆれ。
# Geminiには判定させず、ここだけでタグを確定する。
KNOWN_PERSONS: list[tuple[str, list[str]]] = [
    ("ちょる子", ["ちょる子", "ちょるこ", "チョル子", "チョルコ"]),
    ("大川智宏", ["大川智宏", r"大川\.?智宏"]),
    ("岡崎良介", ["岡崎良介", r"岡崎\.?良介", "ザキオカ", "ザ岡"]),
    ("木野内栄治", ["木野内栄治", r"木野内\.?栄治"]),
    ("テスタ", ["テスタ"]),
    ("田中泰輔", ["田中泰輔", r"田中\.?泰輔"]),
    ("森永康平", ["森永康平", r"森永\.?康平"]),
    ("大橋ひろこ", ["大橋ひろこ", r"大橋\.?ひろこ"]),
    ("池水雄一", ["池水雄一", r"池水\.?雄一"]),
    ("田端信太郎", ["田端信太郎", r"田端\.?信太郎"]),
    ("あばねちゃん", ["あばねちゃん"]),
]


def is_configured() -> bool:
    try:
        return bool(get_token() and get_database_id())
    except ValueError:
        return False


def _load_external_notion_env() -> None:
    env_path = Path(LOCAL_NOTION_ENV_FILE)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = name.strip()
        if name not in NOTION_ENV_KEYS or os.getenv(name):
            continue
        os.environ[name] = value.strip().strip('"').strip("'")


def get_token() -> str:
    _load_external_notion_env()
    return os.getenv("INFO_VIEWER_NOTION_API_KEY") or os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN") or ""


def get_database_id() -> str:
    _load_external_notion_env()
    raw = (
        os.getenv("INFO_VIEWER_NOTION_DATABASE_ID")
        or os.getenv("INFO_VIEWER_NOTION_DATABASE_URL")
        or os.getenv("NOTION_DATABASE_ID")
        or os.getenv("NOTION_DATABASE_URL")
        or DEFAULT_NOTION_DATABASE_ID
    )
    return notion_id_from_url(raw)


def notion_id_from_url(url_or_id: str) -> str:
    value = str(url_or_id or "").strip()
    compact = value.replace("-", "")
    if re.fullmatch(r"(?i)[0-9a-f]{32}", compact):
        return compact.lower()
    base = value.split("?", 1)[0]
    matches = re.findall(r"(?i)([0-9a-f]{32})", base) or re.findall(r"(?i)([0-9a-f]{32})", value)
    if not matches:
        raise ValueError(f"Notion DB IDを抽出できません: {url_or_id}")
    return matches[-1].lower()


def hyphenate_notion_id(raw_id: str) -> str:
    value = str(raw_id or "").replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError(f"Notion IDの形式が不正です: {raw_id}")
    return f"{value[0:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:32]}"


def normalize_key(value: str) -> str:
    return str(value or "").strip().replace(" ", "").replace("_", "").replace("-", "").lower()


def normalize_notion_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if "T" in text or re.search(r"\d{1,2}:\d{2}", text):
            return parsed.isoformat().replace("+00:00", "Z")
        return parsed.date().isoformat()
    except ValueError:
        pass

    normalized = re.sub(r"\s+", " ", text)
    japanese_match = re.match(
        r"^(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        normalized,
    )
    if japanese_match:
        year, month, day, hour, minute, second = japanese_match.groups()
        if hour is None:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"

    slash_match = re.match(
        r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T/](\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        normalized,
    )
    if slash_match:
        year, month, day, hour, minute, second = slash_match.groups()
        if hour is None:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T{int(hour):02d}:{int(minute):02d}:{int(second or 0):02d}"

    return ""


def notion_rich_text(text: str) -> list[dict[str, Any]]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    return [{"type": "text", "text": {"content": cleaned[:2000]}}]


def notion_title(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": str(text or "")[:2000]}}]


def extract_persons_from_title(title: str) -> list[str]:
    found: list[str] = []
    for canonical, patterns in KNOWN_PERSONS:
        for pattern in patterns:
            if re.search(pattern, str(title or "")):
                found.append(canonical)
                break
    return found


class NotionClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{NOTION_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        for attempt, wait_seconds in enumerate((0, *RETRY_DELAYS), start=1):
            if wait_seconds:
                time.sleep(wait_seconds)
            response = requests.request(method, url, headers=headers, json=body, timeout=60)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt <= len(RETRY_DELAYS):
                continue
            if not response.ok:
                raise RuntimeError(f"Notion APIエラー HTTP {response.status_code}: {response.text[:1000]}")
            if not response.text:
                return {}
            return response.json()
        raise RuntimeError("Notion APIリクエストに失敗しました。")

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self.request("GET", f"/databases/{hyphenate_notion_id(database_id)}")

    def query_database(self, database_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/databases/{hyphenate_notion_id(database_id)}/query", body)

    def create_page(self, database_id: str, properties: dict[str, Any], children: list[dict[str, Any]]) -> str:
        page = self.request(
            "POST",
            "/pages",
            {
                "parent": {"database_id": hyphenate_notion_id(database_id)},
                "properties": properties,
                "children": children[:80],
            },
        )
        page_id = page.get("id", "")
        append_children(self, page_id, children[80:])
        return page_id

    def update_page(self, page_id: str, properties: dict[str, Any]) -> None:
        self.request("PATCH", f"/pages/{page_id}", {"properties": properties})


def append_children(client: NotionClient, page_id: str, children: list[dict[str, Any]]) -> None:
    if not page_id:
        return
    for index in range(0, len(children), 100):
        chunk = children[index : index + 100]
        if chunk:
            client.request("PATCH", f"/blocks/{page_id}/children", {"children": chunk})


def find_property(
    properties: dict[str, Any],
    aliases: list[str],
    wanted_types: set[str],
    *,
    fuzzy_keywords: list[str] | None = None,
    fallback_by_type: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    alias_set = {normalize_key(alias) for alias in aliases}
    for name, prop in properties.items():
        if normalize_key(name) in alias_set and prop.get("type") in wanted_types:
            return name, prop

    keywords = [normalize_key(keyword) for keyword in (fuzzy_keywords or []) if keyword]
    if keywords:
        for name, prop in properties.items():
            normalized_name = normalize_key(name)
            if prop.get("type") in wanted_types and any(keyword in normalized_name for keyword in keywords):
                return name, prop

    if fallback_by_type:
        for name, prop in properties.items():
            if prop.get("type") in wanted_types:
                return name, prop
    return None


def find_youtube_url_property(properties: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    supported_types = {"url", "rich_text"}
    preferred_aliases = [alias for alias in YOUTUBE_URL_ALIASES if normalize_key(alias) not in {"url"}]
    exact = find_property(properties, preferred_aliases, supported_types)
    if exact:
        return exact

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for name, prop in properties.items():
        if prop.get("type") not in supported_types:
            continue
        normalized_name = normalize_key(name)
        score = 0
        if "youtube" in normalized_name or "youtu" in normalized_name:
            score = 100
        elif "動画url" in normalized_name or "動画リンク" in normalized_name:
            score = 90
        elif "video" in normalized_name and "url" in normalized_name:
            score = 80
        elif normalized_name == "url" or "url" in normalized_name:
            score = 40
        if score:
            scored.append((score, name, prop))

    if not scored:
        return find_property(properties, ["URL", "url"], supported_types)
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1], scored[0][2]


def build_url_property(prop: dict[str, Any], url: str) -> dict[str, Any]:
    if prop.get("type") == "url":
        return {"url": url}
    return {"rich_text": notion_rich_text(url)}


def build_select_or_text_property(prop: dict[str, Any], value: str) -> dict[str, Any]:
    if prop.get("type") == "select":
        return {"select": {"name": str(value or "")[:100]}}
    if prop.get("type") == "multi_select":
        return {"multi_select": [{"name": str(value or "")[:100]}] if value else []}
    return {"rich_text": notion_rich_text(value)}


def resolve_notion_date(video: dict[str, Any]) -> str:
    raw_date = str(video.get("video_updated_at") or video.get("published_at") or "").strip()
    normalized_date = normalize_notion_date(raw_date)
    if normalized_date:
        return normalized_date
    return datetime.now().date().isoformat()


def analyze_database_schema(database: dict[str, Any]) -> dict[str, Any]:
    database_properties = database.get("properties", {})
    title_prop = find_property(database_properties, ["タイトル", "動画タイトル", "Name", "名前"], {"title"}, fallback_by_type=True)
    youtube_prop = find_youtube_url_property(database_properties)
    person_prop = find_property(database_properties, ["人物", "人", "persons", "person"], {"multi_select"})

    return {
        "title": {"name": title_prop[0], "type": title_prop[1].get("type")} if title_prop else None,
        "youtube": {"name": youtube_prop[0], "type": youtube_prop[1].get("type")} if youtube_prop else None,
        "person": {"name": person_prop[0], "type": person_prop[1].get("type")} if person_prop else None,
        "properties": [
            {"name": name, "type": prop.get("type", "")}
            for name, prop in sorted(database_properties.items(), key=lambda item: item[0])
        ],
    }


def build_notion_properties(
    database: dict[str, Any],
    video: dict[str, Any],
    *,
    title: str,
    youtube_url: str,
    upload_result: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    database_properties = database.get("properties", {})
    title_prop = find_property(database_properties, ["タイトル", "動画タイトル", "Name", "名前"], {"title"}, fallback_by_type=True)
    if not title_prop:
        raise RuntimeError("Notion DBにtitle型プロパティが見つかりません。")

    youtube_prop = find_youtube_url_property(database_properties)
    if not youtube_prop:
        raise RuntimeError("Notion DBにYoutube/動画URL/URL系のurlまたはrich_text列が見つかりません。")

    properties: dict[str, Any] = {
        title_prop[0]: {"title": notion_title(title)},
        youtube_prop[0]: build_url_property(youtube_prop[1], youtube_url),
    }

    date_prop = find_property(database_properties, ["日付", "動画更新日時", "投稿日", "公開日", "Date"], {"date"})
    if date_prop:
        properties[date_prop[0]] = {"date": {"start": resolve_notion_date(video)}}

    channel_prop = find_property(
        database_properties,
        ["チャンネル名", "チャンネル", "Channel"],
        {"rich_text", "select", "multi_select"},
    )
    if channel_prop:
        properties[channel_prop[0]] = build_select_or_text_property(channel_prop[1], video.get("channel_name", ""))

    onedrive_prop = find_property(
        database_properties,
        ["OneDrive", "OneDrive URL", "Markdown URL", "記事URL", "保存先"],
        {"url", "rich_text"},
        fuzzy_keywords=["onedrive", "markdownurl", "記事url", "保存先"],
    )
    if onedrive_prop and upload_result:
        web_url = upload_result.get("webUrl", "")
        if web_url:
            properties[onedrive_prop[0]] = build_url_property(onedrive_prop[1], web_url)

    completed_prop = find_property(database_properties, ["完了", "Done"], {"checkbox"})
    if completed_prop:
        properties[completed_prop[0]] = {"checkbox": True}

    status_prop = find_property(database_properties, ["状況", "状態", "ステータス", "Status"], {"select"})
    if status_prop:
        properties[status_prop[0]] = {"select": {"name": "完了"}}

    person_prop = find_property(database_properties, ["人物", "人", "persons", "person"], {"multi_select"})
    persons = extract_persons_from_title(title)
    if person_prop and persons:
        properties[person_prop[0]] = {"multi_select": [{"name": person} for person in persons]}

    selected = {
        "titleProperty": title_prop[0],
        "youtubeProperty": youtube_prop[0],
        "youtubePropertyType": youtube_prop[1].get("type", ""),
        "personProperty": person_prop[0] if person_prop else "",
        "persons": persons,
    }
    return properties, selected


def text_chunks(text: str, size: int = 1800) -> list[str]:
    cleaned = str(text or "")
    if not cleaned:
        return []
    return [cleaned[index : index + size] for index in range(0, len(cleaned), size)]


def paragraph_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": notion_rich_text(text)}}


def heading_block(level: int, text: str) -> dict[str, Any]:
    safe_level = min(max(level, 1), 3)
    key = f"heading_{safe_level}"
    return {"object": "block", "type": key, key: {"rich_text": notion_rich_text(text)}}


def bulleted_block(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": notion_rich_text(text)}}


def divider_block() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _is_youtube_url_line(line: str) -> bool:
    text = str(line or "").strip().strip("<>")
    return bool(re.fullmatch(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+", text))


def strip_notion_leading_metadata(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    index = 0

    while index < len(lines) and not lines[index].strip():
        index += 1

    if index < len(lines) and lines[index].strip() == "## 動画情報":
        body_start = None
        scan_index = index + 1
        while scan_index < len(lines):
            if lines[scan_index].strip() == "## 整形記事":
                body_start = scan_index + 1
                break
            scan_index += 1
        if body_start is not None:
            lines = lines[body_start:]

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and lines[0].startswith("# "):
        lines.pop(0)

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and _is_youtube_url_line(lines[0]):
        lines.pop(0)

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and lines[0].strip() == "---":
        lines.pop(0)

    while lines and not lines[0].strip():
        lines.pop(0)

    return "\n".join(lines).strip()


def markdown_to_notion_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    in_code = False
    code_buffer: list[str] = []

    for raw_line in str(markdown or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code and code_buffer:
                for chunk in text_chunks("\n".join(code_buffer)):
                    blocks.append(paragraph_block(chunk))
                code_buffer = []
            in_code = not in_code
            continue
        if in_code:
            code_buffer.append(line)
            continue
        if not line.strip():
            continue
        if line.strip() == "---":
            blocks.append(divider_block())
        elif line.startswith("# "):
            blocks.append(heading_block(1, line[2:]))
        elif line.startswith("## "):
            blocks.append(heading_block(2, line[3:]))
        elif line.startswith("### "):
            blocks.append(heading_block(3, line[4:]))
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append(bulleted_block(line[2:]))
        else:
            for chunk in text_chunks(line):
                blocks.append(paragraph_block(chunk))

    if code_buffer:
        for chunk in text_chunks("\n".join(code_buffer)):
            blocks.append(paragraph_block(chunk))
    return blocks


def build_notion_children(markdown: str, transcript_text: str, video: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = markdown_to_notion_blocks(strip_notion_leading_metadata(markdown))
    blocks.append(divider_block())
    blocks.append(heading_block(2, "元の文字起こし"))
    for chunk in text_chunks(transcript_text):
        blocks.append(paragraph_block(chunk))
    return blocks


def find_existing_page(
    client: NotionClient,
    database_id: str,
    youtube_property: tuple[str, dict[str, Any]],
    youtube_url: str,
) -> str:
    property_name, prop = youtube_property
    prop_type = prop.get("type")
    if prop_type == "url":
        filter_body = {"property": property_name, "url": {"equals": youtube_url}}
    elif prop_type == "rich_text":
        filter_body = {"property": property_name, "rich_text": {"equals": youtube_url}}
    else:
        return ""

    result = client.query_database(database_id, {"filter": filter_body, "page_size": 1})
    rows = result.get("results", [])
    if rows:
        return rows[0].get("id", "")
    return ""


def save_article(
    *,
    video: dict[str, Any],
    title: str,
    markdown: str,
    transcript_text: str,
    upload_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = get_token()
    if not token:
        raise RuntimeError("Notion APIトークンが設定されていません。NOTION_API_KEY または NOTION_TOKEN を設定してください。")

    database_id = get_database_id()
    client = NotionClient(token)
    database = client.retrieve_database(database_id)
    schema = analyze_database_schema(database)
    raw_youtube_url = str(video.get("video_url") or "").strip()
    youtube_url = onedrive_writer.normalize_youtube_url(raw_youtube_url)
    properties, selected = build_notion_properties(
        database,
        video,
        title=title,
        youtube_url=youtube_url,
        upload_result=upload_result,
    )
    youtube_prop = find_youtube_url_property(database.get("properties", {}))
    if not youtube_prop:
        raise RuntimeError("Notion DBのYoutube URL列を特定できませんでした。")

    existing_page_id = find_existing_page(client, database_id, youtube_prop, youtube_url)
    if not existing_page_id and raw_youtube_url and raw_youtube_url != youtube_url:
        existing_page_id = find_existing_page(client, database_id, youtube_prop, raw_youtube_url)
    if existing_page_id:
        client.update_page(existing_page_id, properties)
        if APPEND_ON_EXISTING:
            append_children(client, existing_page_id, build_notion_children(markdown, transcript_text, video))
        action = "updated_existing"
        page_id = existing_page_id
    else:
        page_id = client.create_page(database_id, properties, build_notion_children(markdown, transcript_text, video))
        action = "created"

    return {
        "pageId": page_id,
        "databaseId": database_id,
        "action": action,
        "schema": schema,
        "selected": selected,
        "savedAt": datetime.now().isoformat(),
    }


def schema_summary(result: dict[str, Any]) -> str:
    selected = result.get("selected", {}) if isinstance(result, dict) else {}
    schema = result.get("schema", {}) if isinstance(result, dict) else {}
    return json.dumps(
        {
            "action": result.get("action", ""),
            "pageId": result.get("pageId", ""),
            "youtubeProperty": selected.get("youtubeProperty", ""),
            "youtubePropertyType": selected.get("youtubePropertyType", ""),
            "personProperty": selected.get("personProperty", ""),
            "persons": selected.get("persons", []),
            "propertyCount": len(schema.get("properties", [])),
        },
        ensure_ascii=False,
    )
