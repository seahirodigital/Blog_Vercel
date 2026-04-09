from datetime import datetime
from typing import Any

from .onedrive_writer import DEFAULT_BASE_FOLDER, normalize_youtube_url, upload_json


def build_manifest(
    target_channels: list[dict[str, Any]],
    target_videos: list[dict[str, Any]],
    saved_articles: list[dict[str, Any]],
    failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    failures = failures or []
    article_map = {
        article["youtubeUrlNormalized"]: article
        for article in saved_articles
        if article.get("youtubeUrlNormalized")
    }

    channels: list[dict[str, Any]] = []
    all_videos: list[dict[str, Any]] = []

    for channel in target_channels:
        channel_videos = [
            video for video in target_videos if video.get("channel_id") == channel.get("id")
        ]
        videos: list[dict[str, Any]] = []
        ready_count = 0

        for video in channel_videos:
            article = article_map.get(normalize_youtube_url(video.get("video_url", "")))
            has_article = bool(article)
            if has_article:
                ready_count += 1

            item = {
                "id": article.get("fileId") if article else normalize_youtube_url(video.get("video_url", "")),
                "articleId": article.get("fileId") if article else "",
                "title": video.get("video_title") or (article.get("title") if article else "無題"),
                "publishedAt": video.get("published_at", ""),
                "duration": video.get("duration", ""),
                "youtubeUrl": video.get("video_url", ""),
                "articleStatus": "記事あり" if has_article else (video.get("status") or "未生成"),
                "hasArticle": has_article,
                "articleUpdatedAt": article.get("lastModified", "") if article else "",
                "articleWebUrl": article.get("webUrl", "") if article else "",
                "channelName": channel.get("channel_name", ""),
                "channelUrl": channel.get("channel_url", ""),
                "markdown": "",
            }
            videos.append(item)
            all_videos.append(item)

        videos.sort(
            key=lambda item: (item.get("publishedAt", ""), item.get("articleUpdatedAt", "")),
            reverse=True,
        )

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
        key=lambda item: (item.get("publishedAt", ""), item.get("articleUpdatedAt", "")),
        reverse=True,
    )

    return {
        "generatedAt": datetime.now().isoformat(),
        "baseFolder": DEFAULT_BASE_FOLDER,
        "source": "info_viewer_manifest",
        "channels": channels,
        "recent": recent,
        "stats": {
            "channelCount": len(channels),
            "videoCount": len(all_videos),
            "articleCount": len(recent),
            "failureCount": len(failures),
        },
        "failures": failures,
    }


def write_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return upload_json("manifest.json", manifest)
