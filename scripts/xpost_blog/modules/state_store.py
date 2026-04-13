from datetime import datetime, timedelta, timezone
from typing import Any

from . import onedrive_writer

STATE_FILE_PATH = "state/xpost_pipeline_state.json"
DEFAULT_RETRY_SECONDS = 1800
QUOTA_RETRY_SECONDS = 3600
PROCESSING_STALE_SECONDS = 14400

PENDING_STATUS = "pending"
PROCESSING_STATUS = "processing"
DEFERRED_STATUS = "deferred"
FAILED_STATUS = "failed"
DONE_STATUS = "done"
INACTIVE_STATUS = "inactive"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp(value: str | None) -> float:
    parsed = _parse_iso(value)
    return parsed.timestamp() if parsed else 0.0


def _iso_after(wait_seconds: int) -> str:
    return (_now() + timedelta(seconds=max(0, int(wait_seconds or 0)))).isoformat().replace("+00:00", "Z")


def _blank_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": "",
        "meta": {
            "discordChannels": {},
        },
        "posts": {},
    }


def _normalize_post_key(post_url: str) -> str:
    return onedrive_writer.normalize_x_url(post_url or "")


def _ensure_record(state: dict[str, Any], post_url: str) -> dict[str, Any]:
    posts = state.setdefault("posts", {})
    key = _normalize_post_key(post_url)
    if not key:
        raise KeyError(f"post_url が不正です: {post_url}")
    if key not in posts:
        posts[key] = {
            "normalizedPostUrl": key,
            "firstSeenAt": _now_iso(),
            "attemptCount": 0,
            "nextRetryAt": _now_iso(),
            "lastError": "",
            "lastStage": "",
            "active": True,
        }
    return posts[key]


def _copy_post_fields(record: dict[str, Any], post: dict[str, Any]):
    record["postUrl"] = post.get("post_url", "")
    record["normalizedPostUrl"] = _normalize_post_key(post.get("post_url", ""))
    record["title"] = post.get("title", "")
    record["authorName"] = post.get("author_name", "")
    record["authorScreenName"] = post.get("author_screen_name", "")
    record["publishedAt"] = post.get("published_at", "")
    record["discordMessageId"] = post.get("discord_message_id", "")
    record["discordJumpUrl"] = post.get("discord_jump_url", "")
    record["discordChannelId"] = post.get("discord_channel_id", "")
    record["discordChannelName"] = post.get("discord_channel_name", "")
    record["discordAuthorName"] = post.get("discord_author_name", "")
    record["discordAuthorId"] = post.get("discord_author_id", "")
    record["observedAt"] = post.get("observed_at", "")


def load_state() -> dict[str, Any]:
    state = onedrive_writer.download_json(STATE_FILE_PATH) or {}
    if not isinstance(state, dict):
        return _blank_state()
    state.setdefault("version", 1)
    state.setdefault("updatedAt", "")
    state.setdefault("meta", {"discordChannels": {}})
    state.setdefault("posts", {})
    if not isinstance(state["meta"], dict):
        state["meta"] = {"discordChannels": {}}
    state["meta"].setdefault("discordChannels", {})
    if not isinstance(state["posts"], dict):
        state["posts"] = {}
    return state


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    state.setdefault("meta", {"discordChannels": {}})
    state.setdefault("posts", {})
    state["updatedAt"] = _now_iso()
    onedrive_writer.upload_json(STATE_FILE_PATH, state)
    return state


def get_channel_cursor(state: dict[str, Any], channel_id: str) -> str:
    channels = state.get("meta", {}).get("discordChannels", {})
    if not isinstance(channels, dict):
        return ""
    entry = channels.get(str(channel_id), {})
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("lastMessageId", "") or "")


def set_channel_cursor(state: dict[str, Any], channel_id: str, message_id: str):
    if not message_id:
        return
    channels = state.setdefault("meta", {}).setdefault("discordChannels", {})
    channels[str(channel_id)] = {
        "lastMessageId": str(message_id),
        "updatedAt": _now_iso(),
    }


def sync_discovered_posts(state: dict[str, Any], posts: list[dict[str, Any]]) -> dict[str, int]:
    stats = {
        "scanned": 0,
        "added": 0,
        "pending": 0,
    }
    now_iso = _now_iso()

    for post in posts:
        key = _normalize_post_key(post.get("post_url", ""))
        if not key:
            continue
        stats["scanned"] += 1
        record = state.get("posts", {}).get(key)
        if record is None:
            record = _ensure_record(state, post.get("post_url", ""))
            stats["added"] += 1
        previous_status = str(record.get("status") or "")
        _copy_post_fields(record, post)
        record["active"] = True
        record["lastSeenAt"] = now_iso
        if not record.get("firstSeenAt"):
            record["firstSeenAt"] = now_iso
        if previous_status in {"", INACTIVE_STATUS}:
            record["status"] = PENDING_STATUS
            record["nextRetryAt"] = now_iso
            stats["pending"] += 1

    state["updatedAt"] = now_iso
    return stats


def upsert_manual_post(state: dict[str, Any], post_url: str, channel_name: str = "manual") -> dict[str, Any]:
    normalized = _normalize_post_key(post_url)
    record = _ensure_record(state, normalized)
    now_iso = _now_iso()
    record["postUrl"] = normalized
    record["normalizedPostUrl"] = normalized
    record["discordChannelName"] = channel_name
    record["active"] = True
    record["lastSeenAt"] = now_iso
    record["status"] = PENDING_STATUS
    record["nextRetryAt"] = now_iso
    state["updatedAt"] = now_iso
    return record


def resolve_retry_wait_seconds(recommended_wait_seconds: int = 0, quota: bool = False) -> int:
    base = QUOTA_RETRY_SECONDS if quota else DEFAULT_RETRY_SECONDS
    return max(base, int(recommended_wait_seconds or 0))


def list_processable_posts(state: dict[str, Any], max_items: int = 0, post_url: str = "") -> list[dict[str, Any]]:
    normalized_filter = _normalize_post_key(post_url)
    now = _now()
    records: list[dict[str, Any]] = []

    for record in state.get("posts", {}).values():
        if not record.get("active", True):
            continue
        status = str(record.get("status") or PENDING_STATUS)
        if status in {DONE_STATUS, INACTIVE_STATUS}:
            continue
        if normalized_filter and record.get("normalizedPostUrl") != normalized_filter:
            continue
        if status == PROCESSING_STATUS:
            started_at = _parse_iso(record.get("processingStartedAt") or record.get("lastAttemptAt"))
            if started_at and (now - started_at).total_seconds() < PROCESSING_STALE_SECONDS:
                continue
        if not normalized_filter:
            next_retry_at = _parse_iso(record.get("nextRetryAt"))
            if next_retry_at and next_retry_at > now:
                continue
        records.append(dict(record))

    records.sort(
        key=lambda item: (
            0 if item.get("manualPriorityAt") else 1,
            -_timestamp(item.get("manualPriorityAt")),
            str(item.get("nextRetryAt", "")),
            -_timestamp(item.get("publishedAt") or item.get("observedAt")),
            str(item.get("postUrl", "")),
        )
    )
    if max_items > 0:
        return records[:max_items]
    return records


def list_manifest_posts(state: dict[str, Any]) -> list[dict[str, Any]]:
    records = [dict(record) for record in state.get("posts", {}).values() if record.get("active", True) or record.get("articleFileId")]
    records.sort(key=lambda item: -_timestamp(item.get("publishedAt") or item.get("observedAt")))
    return records


def mark_processing(state: dict[str, Any], post_url: str, run_id: str) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    now_iso = _now_iso()
    record["status"] = PROCESSING_STATUS
    record["lastRunId"] = run_id
    record["lastAttemptAt"] = now_iso
    record["processingStartedAt"] = now_iso
    record["attemptCount"] = int(record.get("attemptCount") or 0) + 1
    record["nextRetryAt"] = ""
    state["updatedAt"] = now_iso
    return record


def update_post_metadata(state: dict[str, Any], post_url: str, metadata: dict[str, Any]) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    field_map = {
        "title": "title",
        "author_name": "authorName",
        "author_screen_name": "authorScreenName",
        "published_at": "publishedAt",
        "tweet_id": "tweetId",
        "article_id": "articleId",
        "favorite_count": "favoriteCount",
        "repost_count": "repostCount",
        "reply_count": "replyCount",
        "quote_count": "quoteCount",
        "bookmark_count": "bookmarkCount",
        "view_count": "viewCount",
        "is_article": "isArticle",
        "source_title": "sourceTitle",
    }
    for source_key, target_key in field_map.items():
        if metadata.get(source_key) not in (None, ""):
            record[target_key] = metadata[source_key]
    state["updatedAt"] = _now_iso()
    return record


def update_source_upload(state: dict[str, Any], post_url: str, upload_result: dict[str, Any]) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    record["sourceFileId"] = upload_result.get("id", "")
    record["sourceRelativePath"] = upload_result.get("relativePath", "")
    record["sourceWebUrl"] = upload_result.get("webUrl", "")
    record["sourceTitle"] = upload_result.get("title", record.get("sourceTitle", ""))
    record["folderName"] = upload_result.get("folderName", record.get("folderName", ""))
    record["sourceSavedAt"] = _now_iso()
    state["updatedAt"] = _now_iso()
    return record


def mark_retry(
    state: dict[str, Any],
    post_url: str,
    stage: str,
    error: str,
    run_id: str,
    wait_seconds: int,
    status: str = DEFERRED_STATUS,
) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    now_iso = _now_iso()
    record["status"] = status
    record["lastRunId"] = run_id
    record["lastStage"] = stage
    record["lastError"] = str(error or "").strip()
    record["lastFailureAt"] = now_iso
    record["processingStartedAt"] = ""
    record["nextRetryAt"] = _iso_after(wait_seconds)
    state["updatedAt"] = now_iso
    return record


def mark_done(
    state: dict[str, Any],
    post_url: str,
    run_id: str,
    blog_result: dict[str, Any],
) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    now_iso = _now_iso()
    record["status"] = DONE_STATUS
    record["lastRunId"] = run_id
    record["lastStage"] = ""
    record["lastError"] = ""
    record["nextRetryAt"] = ""
    record["processingStartedAt"] = ""
    record["lastCompletedAt"] = now_iso
    record["articleFileId"] = blog_result.get("id", "")
    record["articleRelativePath"] = blog_result.get("relativePath", "")
    record["articleWebUrl"] = blog_result.get("webUrl", "")
    record["articleTitle"] = blog_result.get("title", record.get("articleTitle", ""))
    record["folderName"] = blog_result.get("folderName", record.get("folderName", ""))
    record["manualPriorityAt"] = ""
    state["updatedAt"] = now_iso
    return record


def prioritize_post(state: dict[str, Any], post_url: str) -> dict[str, Any]:
    record = _ensure_record(state, post_url)
    now_iso = _now_iso()
    record["status"] = PENDING_STATUS
    record["manualPriorityAt"] = now_iso
    record["nextRetryAt"] = now_iso
    record["processingStartedAt"] = ""
    state["updatedAt"] = now_iso
    return record