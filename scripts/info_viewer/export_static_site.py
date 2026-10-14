from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = PROJECT_ROOT / "info_viewer_site"
CONTENT_DIR = SITE_ROOT / "content" / "articles"
DATA_PATH = SITE_ROOT / "data" / "article_index.json"
SEARCH_PATH = SITE_ROOT / "static" / "search.json"

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


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.S)
    if not match:
        return {}, text
    metadata: dict[str, str] = {}
    meta_block, body = match.groups()
    for line in meta_block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = value.strip()
        if (normalized.startswith('"') and normalized.endswith('"')) or (
            normalized.startswith("'") and normalized.endswith("'")
        ):
            normalized = normalized[1:-1]
        metadata[key.strip()] = normalized.replace('\\"', '"').replace("\\\\", "\\")
    return metadata, body


def _extract_persons_from_title(title: str) -> list[str]:
    found: list[str] = []
    for canonical, patterns in KNOWN_PERSONS:
        if any(re.search(pattern, str(title or "")) for pattern in patterns):
            found.append(canonical)
    return found


def _remote_modules():
    from modules import onedrive_writer

    return onedrive_writer


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


def _format_duration(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    iso_match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text, flags=re.I)
    if iso_match:
        hours, minutes, seconds = (int(part or 0) for part in iso_match.groups())
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    if re.fullmatch(r"\d+", text):
        total_seconds = int(text)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    return text


def _format_recorded_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return _format_date(text)


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


def _entry_from_markdown(
    article_id: str,
    raw_markdown: bytes,
    fallback: dict[str, Any],
    last_modified: str,
    source_file_id: str,
) -> tuple[dict[str, Any], str]:
    markdown = raw_markdown.decode("utf-8-sig")
    metadata, _ = _parse_frontmatter(markdown)
    title = str(metadata.get("title") or fallback.get("title") or "無題").strip()
    youtube_url = str(metadata.get("video_url") or fallback.get("youtubeUrl") or "").strip()
    channel_name = str(metadata.get("channel_name") or fallback.get("channelName") or "手動URL").strip()
    published_at = str(metadata.get("published_at") or fallback.get("publishedAt") or "").strip()
    recorded_at = str(
        metadata.get("generated_at")
        or fallback.get("recordedAt")
        or fallback.get("generatedAt")
        or last_modified
        or ""
    ).strip()
    duration = _format_duration(str(metadata.get("duration") or fallback.get("duration") or ""))
    people = _extract_persons_from_title(title)
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
        "duration": duration,
        "recordedAt": recorded_at,
        "recordedLabel": _format_recorded_time(recorded_at),
        "timeLabel": duration or _format_recorded_time(recorded_at),
        "persons": people,
        "lastModified": last_modified,
        "sourceFileId": source_file_id,
    }
    return entry, _plain_text(markdown)


def _load_article(article: dict[str, Any], previous: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    onedrive_writer = _remote_modules()
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

    entry, plain_text = _entry_from_markdown(
        article_id,
        raw_markdown,
        article,
        last_modified,
        str(article.get("fileId") or ""),
    )
    return entry, plain_text, should_download


def _load_local_article(
    source: Path,
    source_root: Path,
    used_article_ids: set[str],
) -> tuple[dict[str, Any], str, bool]:
    raw_markdown = source.read_bytes()
    markdown = raw_markdown.decode("utf-8-sig")
    metadata, _ = _parse_frontmatter(markdown)
    youtube_url = str(metadata.get("video_url") or "").strip()
    relative_path = source.relative_to(source_root).as_posix()
    article_id = _article_id({"youtubeUrlNormalized": youtube_url, "relativePath": relative_path})
    if article_id in used_article_ids:
        article_id = hashlib.sha256(f"{youtube_url}\n{relative_path}".encode("utf-8")).hexdigest()[:18]
    used_article_ids.add(article_id)
    destination = CONTENT_DIR / f"{article_id}.md"
    should_write = not destination.exists() or destination.read_bytes() != raw_markdown
    if should_write:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw_markdown)

    last_modified = datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat()
    entry, plain_text = _entry_from_markdown(article_id, raw_markdown, {}, last_modified, "")
    return entry, plain_text, should_write


def _timestamp_sort_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return 0.0


def _newest_sort_key(entry: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        _timestamp_sort_value(entry.get("recordedAt")),
        _timestamp_sort_value(entry.get("lastModified")),
        _timestamp_sort_value(entry.get("publishedAt")),
        str(entry.get("title") or ""),
    )


def _search_item(entry: dict[str, Any], plain_text: str) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "url": entry["url"],
        "title": entry["title"],
        "channelName": entry["channelName"],
        "channelTab": entry["channelTab"],
        "duration": entry["duration"],
        "timeLabel": entry["timeLabel"],
        "publishedAt": entry["publishedAt"],
        "recordedAt": entry["recordedAt"],
        "lastModified": entry["lastModified"],
        "persons": entry["persons"],
        "text": plain_text,
    }


def _write_site_index(entries: list[dict[str, Any]], search_items: list[dict[str, Any]]) -> None:

    entries.sort(key=_newest_sort_key, reverse=True)
    entries_by_id = {entry["id"]: entry for entry in entries}
    search_items.sort(key=lambda item: _newest_sort_key(entries_by_id[item["id"]]), reverse=True)
    latest_entry_by_channel: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key = entry["channelKey"]
        current = latest_entry_by_channel.get(key)
        if current is None or _newest_sort_key(entry) > _newest_sort_key(current):
            latest_entry_by_channel[key] = entry

    channels = [
        {"name": entry["channelName"], "tab": entry["channelTab"], "latestAt": entry["recordedAt"]}
        for entry in sorted(latest_entry_by_channel.values(), key=_newest_sort_key, reverse=True)
    ]

    index = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "articleList": entries,
        "articles": {entry["id"]: entry for entry in entries},
        "channels": channels,
        "people": sorted({person for entry in entries for person in entry["persons"]}),
    }
    _write_json(DATA_PATH, index)
    _write_json(SEARCH_PATH, search_items)


def _write_remote_articles() -> int:
    onedrive_writer = _remote_modules()
    previous_articles = _existing_metadata()
    entries: list[dict[str, Any]] = []
    search_items: list[dict[str, Any]] = []
    changed_count = 0

    for article in onedrive_writer.list_saved_articles():
        if not article.get("fileId"):
            continue
        article_id = _article_id(article)
        entry, plain_text, changed = _load_article(article, previous_articles.get(article_id, {}))
        entries.append(entry)
        search_items.append(_search_item(entry, plain_text))
        changed_count += int(changed)

    _write_site_index(entries, search_items)
    print(f"静的Viewerを書き出しました: 記事 {len(entries)}件、Markdown更新 {changed_count}件")
    return 0


def _write_local_seed_articles(seed_dir: Path, limit: int) -> int:
    source_root = seed_dir.expanduser().resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Markdownの保存先が見つかりません: {source_root}")

    candidates = sorted(source_root.rglob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if limit > 0:
        candidates = candidates[:limit]
    if not candidates:
        raise FileNotFoundError(f"Markdownが見つかりません: {source_root}")

    entries: list[dict[str, Any]] = []
    search_items: list[dict[str, Any]] = []
    changed_count = 0
    used_article_ids: set[str] = set()
    for source in candidates:
        entry, plain_text, changed = _load_local_article(source, source_root, used_article_ids)
        entries.append(entry)
        search_items.append(_search_item(entry, plain_text))
        changed_count += int(changed)

    _write_site_index(entries, search_items)
    print(f"ローカルMarkdownを初期表示へ反映しました: 記事 {len(entries)}件、Markdown更新 {changed_count}件")
    return 0


def _reindex_existing_articles() -> int:
    current = _read_json(DATA_PATH, {})
    previous_entries = current.get("articleList", []) if isinstance(current, dict) else []
    if not isinstance(previous_entries, list) or not previous_entries:
        raise FileNotFoundError(f"既存の記事索引が見つかりません: {DATA_PATH}")

    entries: list[dict[str, Any]] = []
    search_items: list[dict[str, Any]] = []
    for previous in previous_entries:
        article_id = str(previous.get("id") or "").strip()
        source = CONTENT_DIR / f"{article_id}.md"
        if not article_id or not source.is_file():
            raise FileNotFoundError(f"索引に対応するMarkdownが見つかりません: {source}")
        raw_markdown = source.read_bytes()
        entry, plain_text = _entry_from_markdown(
            article_id,
            raw_markdown,
            previous,
            str(previous.get("lastModified") or ""),
            str(previous.get("sourceFileId") or ""),
        )
        entries.append(entry)
        search_items.append(_search_item(entry, plain_text))

    _write_site_index(entries, search_items)
    print(f"既存Markdownから索引を再生成しました: 記事 {len(entries)}件")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Info Viewerの静的サイトを書き出す")
    parser.add_argument("--seed-dir", type=Path, help="初期表示に使う既存Markdownのフォルダ")
    parser.add_argument("--limit", type=int, default=4, help="初期表示に載せる記事数。0なら全件")
    parser.add_argument("--reindex-existing", action="store_true", help="既存の記事IDを維持したまま索引を再生成する")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.reindex_existing:
        return _reindex_existing_articles()
    if args.seed_dir:
        return _write_local_seed_articles(args.seed_dir, args.limit)
    return _write_remote_articles()


if __name__ == "__main__":
    raise SystemExit(main())
