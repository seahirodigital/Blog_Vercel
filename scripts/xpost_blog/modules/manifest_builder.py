from datetime import datetime
from typing import Any

from .onedrive_writer import DEFAULT_BASE_FOLDER, normalize_x_url, upload_json


def _sort_timestamp(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _article_status(record: dict[str, Any]) -> str:
    if record.get("articleFileId"):
        return "記事あり"
    status = str(record.get("status") or "pending")
    stage = str(record.get("lastStage") or "")
    if status == "deferred":
        return f"{stage or 'Gemini'}保留"
    if status == "failed":
        return f"{stage or '取得'}失敗"
    if record.get("sourceFileId"):
        return "整形待ち"
    return "未生成"


def build_manifest(
    state: dict[str, Any],
    failures: list[dict[str, Any]] | None = None,
    processing_logs: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    failures = failures or []
    processing_logs = processing_logs or []
    records = state.get("posts", {}) if isinstance(state, dict) else {}
    items: list[dict[str, Any]] = []
    channels_map: dict[str, list[dict[str, Any]]] = {}

    for record in records.values():
        if not isinstance(record, dict):
            continue
        if not record.get("active", True) and not record.get("articleFileId"):
            continue

        normalized_post_url = normalize_x_url(record.get("postUrl", ""))
        item = {
            "id": record.get("articleFileId") or normalized_post_url,
            "articleId": record.get("articleFileId", ""),
            "sourceId": record.get("sourceFileId", ""),
            "title": record.get("articleTitle") or record.get("title") or record.get("sourceTitle") or normalized_post_url,
            "sourceTitle": record.get("sourceTitle") or record.get("title") or "元投稿ソース",
            "postUrl": record.get("postUrl", ""),
            "normalizedPostUrl": normalized_post_url,
            "publishedAt": record.get("publishedAt", ""),
            "observedAt": record.get("observedAt", ""),
            "authorName": record.get("authorName", ""),
            "authorScreenName": record.get("authorScreenName", ""),
            "favoriteCount": int(record.get("favoriteCount") or 0),
            "repostCount": int(record.get("repostCount") or 0),
            "replyCount": int(record.get("replyCount") or 0),
            "quoteCount": int(record.get("quoteCount") or 0),
            "bookmarkCount": int(record.get("bookmarkCount") or 0),
            "viewCount": int(record.get("viewCount") or 0),
            "isArticle": bool(record.get("isArticle")),
            "hasArticle": bool(record.get("articleFileId")),
            "articleStatus": _article_status(record),
            "queueStatus": record.get("status", "pending"),
            "queueNextRetryAt": record.get("nextRetryAt", ""),
            "queueAttemptCount": int(record.get("attemptCount") or 0),
            "sourceStatus": "元投稿あり" if record.get("sourceFileId") else "未取得",
            "articleUpdatedAt": record.get("lastCompletedAt", ""),
            "sourceUpdatedAt": record.get("sourceSavedAt", ""),
            "articleWebUrl": record.get("articleWebUrl", ""),
            "sourceWebUrl": record.get("sourceWebUrl", ""),
            "discordMessageId": record.get("discordMessageId", ""),
            "discordJumpUrl": record.get("discordJumpUrl", ""),
            "discordChannelId": record.get("discordChannelId", ""),
            "channelName": record.get("discordChannelName") or "01_tech",
            "lastFailureStage": record.get("lastStage", ""),
            "lastFailureMessage": record.get("lastError", ""),
            "lastFailureAt": record.get("lastFailureAt", ""),
            "folderName": record.get("folderName", ""),
        }
        items.append(item)
        channels_map.setdefault(item["channelName"], []).append(item)

    items.sort(
        key=lambda item: (
            -_sort_timestamp(item.get("articleUpdatedAt") or item.get("publishedAt") or item.get("observedAt")),
            str(item.get("title", "")),
        )
    )

    channels = []
    for channel_name, channel_items in sorted(channels_map.items(), key=lambda entry: entry[0]):
        channel_items.sort(
            key=lambda item: (
                -_sort_timestamp(item.get("publishedAt") or item.get("observedAt")),
                str(item.get("title", "")),
            )
        )
        channels.append(
            {
                "id": channel_name,
                "name": channel_name,
                "summary": "Discord 取得キューをベースにした Xpost_blog 出力",
                "items": channel_items,
            }
        )

    recent = [item for item in items if item.get("hasArticle")]
    return {
        "runId": run_id or datetime.now().strftime("%Y%m%dT%H%M%S"),
        "generatedAt": datetime.now().isoformat(),
        "baseFolder": DEFAULT_BASE_FOLDER,
        "source": "xpost_blog_manifest",
        "channels": channels,
        "items": items,
        "recent": recent,
        "stats": {
            "channelCount": len(channels),
            "itemCount": len(items),
            "articleCount": len(recent),
            "failureCount": len(failures),
            "processingLogCount": len(processing_logs),
        },
        "failures": failures,
        "processingLogs": processing_logs,
    }


def write_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return upload_json("manifest.json", manifest)