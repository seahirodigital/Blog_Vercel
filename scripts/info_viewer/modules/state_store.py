import os
from datetime import datetime, timedelta
from typing import Any

from . import onedrive_writer

STATE_FILE_PATH = os.getenv("INFO_VIEWER_STATE_FILE", "state/pipeline_state.json")
DEFAULT_RETRY_SECONDS = int(os.getenv("INFO_VIEWER_RETRY_SECONDS", "3600") or 3600)
QUOTA_RETRY_SECONDS = int(os.getenv("INFO_VIEWER_QUOTA_RETRY_SECONDS", "7200") or 7200)
PROCESSING_STALE_SECONDS = int(os.getenv("INFO_VIEWER_PROCESSING_STALE_SECONDS", "14400") or 14400)

PENDING_STATUS = "pending"
PROCESSING_STATUS = "processing"
DEFERRED_STATUS = "deferred"
FAILED_STATUS = "failed"
DONE_STATUS = "done"
INACTIVE_STATUS = "inactive"


def _now() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_after(wait_seconds: int) -> str:
    delay = max(0, int(wait_seconds or 0))
    return (_now() + timedelta(seconds=delay)).isoformat()


def _blank_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": "",
        "videos": {},
    }


def _normalize_video_key(video_url: str) -> str:
    return onedrive_writer.normalize_youtube_url(video_url or "")


def _ensure_record(state: dict[str, Any], video_url: str) -> dict[str, Any]:
    videos = state.setdefault("videos", {})
    key = _normalize_video_key(video_url)
    if not key or key not in videos:
        raise KeyError(f"キュー状態が見つかりません: {video_url}")
    return videos[key]


def _copy_video_fields(record: dict[str, Any], video: dict[str, Any]):
    record["videoUrl"] = video.get("video_url", "")
    record["normalizedVideoUrl"] = _normalize_video_key(video.get("video_url", ""))
    record["videoTitle"] = video.get("video_title", "")
    record["channelName"] = video.get("channel_name", "")
    record["channelUrl"] = video.get("channel_url", "")
    record["publishedAt"] = video.get("published_at", "")
    record["duration"] = video.get("duration", "")
    record["rowNumber"] = video.get("row_number")
    record["sheetStatus"] = video.get("status", "")


def _copy_article_fields(record: dict[str, Any], article: dict[str, Any]):
    record["articleRelativePath"] = article.get("relativePath", "")
    record["articleFileId"] = article.get("fileId", "")
    record["articleTitle"] = article.get("title", "")
    record["lastCompletedAt"] = article.get("lastModified") or record.get("lastCompletedAt", "")


def _record_to_video(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_number": record.get("rowNumber"),
        "video_url": record.get("videoUrl", ""),
        "video_title": record.get("videoTitle", ""),
        "published_at": record.get("publishedAt", ""),
        "duration": record.get("duration", ""),
        "status": record.get("sheetStatus", ""),
        "channel_name": record.get("channelName", ""),
        "channel_url": record.get("channelUrl", ""),
        "_queue_status": record.get("status", PENDING_STATUS),
        "_queue_next_retry_at": record.get("nextRetryAt", ""),
        "_queue_attempt_count": int(record.get("attemptCount") or 0),
    }


def load_state() -> dict[str, Any]:
    state = onedrive_writer.download_json(STATE_FILE_PATH) or {}
    if not isinstance(state, dict):
        return _blank_state()

    videos = state.get("videos")
    if not isinstance(videos, dict):
        state["videos"] = {}
    state.setdefault("version", 1)
    state.setdefault("updatedAt", "")
    return state


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    state = state if isinstance(state, dict) else _blank_state()
    state.setdefault("videos", {})
    state["updatedAt"] = _now_iso()
    onedrive_writer.upload_json(STATE_FILE_PATH, state)
    return state


def resolve_retry_wait_seconds(recommended_wait_seconds: int = 0, quota: bool = False) -> int:
    base = QUOTA_RETRY_SECONDS if quota else DEFAULT_RETRY_SECONDS
    return max(base, int(recommended_wait_seconds or 0))


def sync_target_videos(
    state: dict[str, Any],
    target_videos: list[dict[str, Any]],
    existing_article_map: dict[str, dict[str, Any]],
    deactivate_missing: bool = False,
) -> dict[str, int]:
    videos = state.setdefault("videos", {})
    now_iso = _now_iso()
    active_keys: set[str] = set()
    stats = {
        "scanned": 0,
        "added": 0,
        "pending": 0,
        "markedDone": 0,
        "deactivated": 0,
    }

    for video in target_videos:
        key = _normalize_video_key(video.get("video_url", ""))
        if not key:
            continue

        stats["scanned"] += 1
        active_keys.add(key)
        record = videos.get(key)
        if record is None:
            record = {
                "normalizedVideoUrl": key,
                "firstSeenAt": now_iso,
                "attemptCount": 0,
                "lastError": "",
                "lastStage": "",
                "nextRetryAt": now_iso,
            }
            videos[key] = record
            stats["added"] += 1

        _copy_video_fields(record, video)
        record["active"] = True
        record["removedAt"] = ""
        record["lastSeenAt"] = now_iso
        if not record.get("firstSeenAt"):
            record["firstSeenAt"] = now_iso

        article = existing_article_map.get(key)
        if video.get("status") == "完了" or article:
            if record.get("status") != DONE_STATUS:
                stats["markedDone"] += 1
            record["status"] = DONE_STATUS
            record["nextRetryAt"] = ""
            record["lastError"] = ""
            record["lastStage"] = ""
            record["sheetStatus"] = "完了"
            record["processingStartedAt"] = ""
            record["lastCompletedAt"] = now_iso
            if article:
                _copy_article_fields(record, article)
            continue

        if record.get("status") in ("", INACTIVE_STATUS, DONE_STATUS):
            record["status"] = PENDING_STATUS
            stats["pending"] += 1
        if not record.get("nextRetryAt"):
            record["nextRetryAt"] = now_iso

    if deactivate_missing:
        for key, record in videos.items():
            if key in active_keys:
                continue
            if not record.get("active"):
                continue
            record["active"] = False
            record["removedAt"] = now_iso
            if record.get("status") != DONE_STATUS:
                record["status"] = INACTIVE_STATUS
            stats["deactivated"] += 1

    state["updatedAt"] = now_iso
    return stats


def get_summary(state: dict[str, Any]) -> dict[str, int]:
    summary = {
        "total": 0,
        "active": 0,
        "pending": 0,
        "processing": 0,
        "deferred": 0,
        "failed": 0,
        "done": 0,
        "inactive": 0,
        "queueable": 0,
    }
    videos = state.get("videos", {})
    if not isinstance(videos, dict):
        return summary

    for record in videos.values():
        summary["total"] += 1
        if record.get("active"):
            summary["active"] += 1

        status = str(record.get("status") or PENDING_STATUS)
        if status in summary:
            summary[status] += 1

        if record.get("active") and status in {PENDING_STATUS, PROCESSING_STATUS, DEFERRED_STATUS, FAILED_STATUS}:
            summary["queueable"] += 1

    return summary


def _is_due(record: dict[str, Any], now: datetime) -> bool:
    next_retry_at = _parse_iso(record.get("nextRetryAt", ""))
    if next_retry_at is None:
        return True
    return next_retry_at <= now


def _is_stale_processing(record: dict[str, Any], now: datetime) -> bool:
    processing_started_at = _parse_iso(record.get("processingStartedAt", "")) or _parse_iso(record.get("lastAttemptAt", ""))
    if processing_started_at is None:
        return True
    return (now - processing_started_at).total_seconds() >= PROCESSING_STALE_SECONDS


def list_processable_videos(
    state: dict[str, Any],
    max_items: int = 0,
    channel_name: str = "",
    video_url: str = "",
) -> list[dict[str, Any]]:
    normalized_filter = _normalize_video_key(video_url)
    now = _now()
    candidates: list[dict[str, Any]] = []

    for record in state.get("videos", {}).values():
        if not record.get("active"):
            continue

        status = str(record.get("status") or PENDING_STATUS)
        if status in {DONE_STATUS, INACTIVE_STATUS}:
            continue
        if channel_name and record.get("channelName") != channel_name:
            continue
        if normalized_filter and record.get("normalizedVideoUrl") != normalized_filter:
            continue
        if status == PROCESSING_STATUS and not _is_stale_processing(record, now):
            continue
        if not _is_due(record, now):
            continue

        candidates.append(_record_to_video(record))

    candidates.sort(
        key=lambda item: (
            str(item.get("_queue_next_retry_at", "")),
            str(item.get("published_at", "")),
            str(item.get("video_url", "")),
        )
    )
    if max_items > 0:
        return candidates[:max_items]
    return candidates


def get_record(state: dict[str, Any], video_url: str) -> dict[str, Any]:
    return _ensure_record(state, video_url)


def mark_processing(state: dict[str, Any], video_url: str, run_id: str) -> dict[str, Any]:
    record = _ensure_record(state, video_url)
    now_iso = _now_iso()
    record["status"] = PROCESSING_STATUS
    record["lastRunId"] = run_id
    record["lastAttemptAt"] = now_iso
    record["processingStartedAt"] = now_iso
    record["attemptCount"] = int(record.get("attemptCount") or 0) + 1
    record["nextRetryAt"] = ""
    state["updatedAt"] = now_iso
    return record


def mark_retry(
    state: dict[str, Any],
    video_url: str,
    stage: str,
    error: str,
    run_id: str,
    wait_seconds: int,
    status: str = DEFERRED_STATUS,
) -> dict[str, Any]:
    record = _ensure_record(state, video_url)
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
    video_url: str,
    run_id: str,
    upload_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _ensure_record(state, video_url)
    now_iso = _now_iso()
    record["status"] = DONE_STATUS
    record["sheetStatus"] = "完了"
    record["lastRunId"] = run_id
    record["lastStage"] = ""
    record["lastError"] = ""
    record["nextRetryAt"] = ""
    record["processingStartedAt"] = ""
    record["lastCompletedAt"] = now_iso
    if isinstance(upload_result, dict):
        record["articleRelativePath"] = upload_result.get("relativePath", "")
        record["articleFileId"] = upload_result.get("id", "")
        record["articleTitle"] = upload_result.get("title", "")
    state["updatedAt"] = now_iso
    return record
