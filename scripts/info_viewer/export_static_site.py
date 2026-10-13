import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from modules import notion_writer, onedrive_writer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = PROJECT_ROOT / "info_viewer_site"
CONTENT_DIR = SITE_ROOT / "content" / "articles"
DATA_PATH = SITE_ROOT / "data" / "article_index.json"
SEARCH_PATH = SITE_ROOT / "static" / "search.json"


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(serialized)


def _youtube_id(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return ""
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0]
    if "youtube.com" not in host:
        return ""
    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [""])[0]
    if parsed.path.startswith("/shorts/") or parsed.path.startswith("/live/"):
        parts = parsed.path.strip("/").split("/")
        return parts[1] if len(parts) > 1 else ""
    return ""


def _thumbnail_url(video_url: str) -> str:
    video_id = _youtube_id(video_url)
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""


def _article_id(article: dict[str, Any]) -> str:
    stable_key = article.get("youtubeUrlNormalized") or article.get("fileId") or article.get("relativePath") or ""
    return hashlib.sha256(str(stable_key).encode("utf-8")).hexdigest()[:18]


def _format_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y.%m.%d")
    except ValueError:
        return text[:10].replace("-", ".").replace("/", ".")


def _channel_tab(channel_name: str) -> str:
    normalized = "".join(str(channel_name or "").split())
    return normalized[:4] or "手動URL"


def _plain_text(markdown: str) -> str:
    cleaned = re.sub(r"^---\s*\n[\s\S]*?\n---\s*\n?", "", markdown)
    cleaned = re.sub(r"```[\s\S]*?```", lambda match: match.group(0).replace("```", ""), cleaned)
    cleaned = re.sub(r"!?(\[[^\]]*\])\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"[#>*_`~|-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _existing_metadata() -> dict[str, dict[str, Any]]:
    current = _read_json(DATA_PATH, {})
    articles = current.get("articles", {}) if isinstance(current, dict) else {}
    return articles if isinstance(articles, dict) else {}


def _load_article(article: dict[str, Any], previous: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    article_id = _article_id(article)
    last_modified = str(article.get("lastModified") or "")
    destination = CONTENT_DIR / f"{article_id}.md"
    should_download = not destination.exists() or previous.get("lastModified") != last_modified
    if should_download:
        raw_markdown = onedrive_writer.download_item_bytes(str(article.get("fileId") or ""))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw_markdown)
    else:
        raw_markdown = destination.read_bytes()

    markdown = raw_markdown.decode("utf-8-sig")
    metadata, _ = onedrive_writer.parse_frontmatter(markdown)
    title = str(metadata.get("title") or article.get("title") or "無題").strip()
    youtube_url = str(metadata.get("video_url") or article.get("youtubeUrl") or "").strip()
    channel_name = str(metadata.get("channel_name") or article.get("channelName") or "手動URL").strip()
    published_at = str(metadata.get("published_at") or article.get("publishedAt") or "").strip()
    people = notion_writer.extract_persons_from_title(title)
    entry = {
        "id": article_id,
        "url": f"/articles/{article_id}/",
        "title": title,
        "channelName": channel_name,
        "channelKey": channel_name,
        "channelTab": _channel_tab(channel_name),
        "youtubeUrl": youtube_url,
        "thumbnail": _thumbnail_url(youtube_url),
        "publishedAt": published_at,
        "publishedLabel": _format_date(published_at),
        "persons": people,
        "lastModified": last_modified,
        "sourceFileId": str(article.get("fileId") or ""),
    }
    return entry, _plain_text(markdown), should_download


def _sort_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("publishedAt") or ""),
        str(entry.get("lastModified") or ""),
        str(entry.get("title") or ""),
    )


def main() -> int:
    previous_articles = _existing_metadata()
    saved_articles = onedrive_writer.list_saved_articles()
    entries: list[dict[str, Any]] = []
    search_items: list[dict[str, Any]] = []
    changed_count = 0

    for article in saved_articles:
        if not article.get("fileId"):
            continue
        article_id = _article_id(article)
        entry, plain_text, changed = _load_article(article, previous_articles.get(article_id, {}))
        entries.append(entry)
        search_items.append(
            {
                "id": entry["id"],
                "url": entry["url"],
                "title": entry["title"],
                "channelName": entry["channelName"],
                "channelTab": entry["channelTab"],
                "persons": entry["persons"],
                "text": plain_text,
            }
        )
        changed_count += int(changed)

    entries.sort(key=_sort_key, reverse=True)
    search_items.sort(key=lambda item: _sort_key(next(entry for entry in entries if entry["id"] == item["id"])), reverse=True)
    channels_by_key: dict[str, dict[str, str]] = {}
    for entry in entries:
        key = entry["channelKey"]
        channels_by_key.setdefault(key, {"name": entry["channelName"], "tab": entry["channelTab"]})

    index = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "articleList": entries,
        "articles": {entry["id"]: entry for entry in entries},
        "channels": sorted(channels_by_key.values(), key=lambda item: (item["tab"], item["name"])),
        "people": sorted({person for entry in entries for person in entry["persons"]}),
    }
    _write_json(DATA_PATH, index)
    _write_json(SEARCH_PATH, search_items)
    print(f"静的Viewerを書き出しました: 記事 {len(entries)}件、Markdown更新 {changed_count}件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
