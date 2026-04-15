from datetime import datetime
from typing import Any

from .onedrive_writer import PRIMARY_BASE_FOLDER, normalize_youtube_url, upload_json


def _video_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    video_updated_at = item.get("videoUpdatedAt") or item.get("publishedAt", "")
    return (
        _sort_timestamp(video_updated_at),
        _sort_timestamp(item.get("publishedAt", "")),
        _sort_timestamp(item.get("articleUpdatedAt", "")),
    )


def _sort_timestamp(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass

    normalized = " ".join(text.split())
    for date_format in (
        "%Y/%m/%d/%H:%M:%S",
        "%Y/%m/%d/%H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, date_format).timestamp()
        except ValueError:
            continue

    return 0.0


def build_manifest(
    target_channels: list[dict[str, Any]],
    target_videos: list[dict[str, Any]],
    saved_articles: list[dict[str, Any]],
    failures: list[dict[str, Any]] | None = None,
    processing_logs: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    queue_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures = failures or []
    processing_logs = processing_logs or []
    queue_videos = queue_state.get("videos", {}) if isinstance(queue_state, dict) else {}
    article_map = {
        article["youtubeUrlNormalized"]: article
        for article in saved_articles
        if article.get("youtubeUrlNormalized")
    }
    failure_map: dict[str, dict[str, Any]] = {}
    for failure in failures:
        normalized_url = normalize_youtube_url(failure.get("videoUrl", ""))
        if not normalized_url:
            continue
        current = failure_map.get(normalized_url)
        if current is None or str(current.get("occurredAt", "")) <= str(failure.get("occurredAt", "")):
            failure_map[normalized_url] = failure

    channels: list[dict[str, Any]] = []
    all_videos: list[dict[str, Any]] = []

    for channel in target_channels:
        channel_videos = [
            video for video in target_videos if video.get("channel_id") == channel.get("id")
        ]
        videos: list[dict[str, Any]] = []
        ready_count = 0

        for video in channel_videos:
            normalized_video_url = normalize_youtube_url(video.get("video_url", ""))
            article = article_map.get(normalized_video_url)
            failure = failure_map.get(normalized_video_url)
            queue_record = queue_videos.get(normalized_video_url, {}) if isinstance(queue_videos, dict) else {}
            has_article = bool(article)
            if has_article:
                ready_count += 1

            pending_status = video.get("status") or "未生成"
            queue_stage = queue_record.get("lastStage") or (failure.get("stage", "") if failure else "")
            queue_error = queue_record.get("lastError") or (failure.get("error", "") if failure else "")
            queue_failure_at = queue_record.get("lastFailureAt") or (failure.get("occurredAt", "") if failure else "")
            queue_status = queue_record.get("status", video.get("_queue_status", ""))
            if not has_article and queue_stage:
                if queue_status == "deferred":
                    pending_status = f"{queue_stage}保留"
                elif queue_status == "failed":
                    pending_status = f"{queue_stage}失敗"
                else:
                    pending_status = f"{queue_stage}失敗"

            item = {
                "id": article.get("fileId") if article else normalized_video_url,
                "articleId": article.get("fileId") if article else "",
                "title": video.get("video_title") or (article.get("title") if article else "無題"),
                "publishedAt": video.get("published_at", ""),
                "videoUpdatedAt": video.get("video_updated_at", "") or video.get("published_at", ""),
                "duration": video.get("duration", ""),
                "thumbnailUrl": video.get("thumbnail_url", ""),
                "youtubeUrl": video.get("video_url", ""),
                "articleStatus": "記事あり" if has_article else pending_status,
                "hasArticle": has_article,
                "articleUpdatedAt": article.get("lastModified", "") if article else "",
                "articleWebUrl": article.get("webUrl", "") if article else "",
                "channelName": channel.get("channel_name", ""),
                "channelUrl": channel.get("channel_url", ""),
                "sheetStatus": video.get("status", ""),
                "queueStatus": queue_status,
                "queueNextRetryAt": queue_record.get("nextRetryAt", video.get("_queue_next_retry_at", "")),
                "queueAttemptCount": int(queue_record.get("attemptCount") or video.get("_queue_attempt_count") or 0),
                "manualPriorityAt": queue_record.get("manualPriorityAt", video.get("_queue_manual_priority_at", "")),
                "lastFailureStage": queue_stage,
                "lastFailureMessage": queue_error,
                "lastFailureAt": queue_failure_at,
                "markdown": "",
            }
            videos.append(item)
            all_videos.append(item)

        videos.sort(key=_video_sort_key, reverse=True)

        channels.append(
            {
                "id": channel.get("id"),
                "name": channel.get("channel_name"),
                "channelUrl": channel.get("channel_url", ""),
                "summary": "Google Sheets 連携対象",
                "videos": videos,
            }
        )

    recent = sorted(
        [video for video in all_videos if video.get("hasArticle")],
        key=_video_sort_key,
        reverse=True,
    )

    return {
        "runId": run_id or datetime.now().strftime("%Y%m%dT%H%M%S"),
        "generatedAt": datetime.now().isoformat(),
        "baseFolder": PRIMARY_BASE_FOLDER,
        "source": "info_viewer_manifest",
        "channels": channels,
        "recent": recent,
        "stats": {
            "channelCount": len(channels),
            "videoCount": len(all_videos),
            "articleCount": len(recent),
            "failureCount": len(failures),
            "processingLogCount": len(processing_logs),
        },
        "failures": failures,
        "processingLogs": processing_logs,
    }


def write_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return upload_json("manifest.json", manifest)
