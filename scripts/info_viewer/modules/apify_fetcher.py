from typing import Any

import requests

ACTOR_ID = "1s7eXiaukVuOr4Ueg"
APIFY_BASE_URL = "https://api.apify.com/v2"


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def _channel_metadata(item: dict[str, Any]) -> tuple[str, str]:
    channel = item.get("channel")
    nested_channel = channel if isinstance(channel, dict) else {}
    channel_name = _first_value(item, "channelName", "channelTitle", "authorName")
    channel_url = _first_value(item, "channelUrl", "authorUrl")
    if not channel_name:
        channel_name = _first_value(nested_channel, "name", "title")
    if not channel_url:
        channel_url = _first_value(nested_channel, "url", "channelUrl")
    return str(channel_name or "").strip(), str(channel_url or "").strip()


def _read_response_text(response: requests.Response) -> str:
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def get_transcript(video_url: str, api_key: str, language: str = "ja") -> dict[str, Any]:
    print(f"   Apify で文字起こし取得: {video_url}")
    run_url = f"{APIFY_BASE_URL}/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload = {
        "urls": [video_url.strip()],
        "captionsBoolean": True,
        "captionsLanguage": language,
    }
    params = {"token": api_key, "memory": 8192, "timeout": 300}

    try:
        response = requests.post(run_url, json=payload, params=params, timeout=360)
        status_code = response.status_code
        response.raise_for_status()
        data = response.json()
        if not data:
            return {
                "ok": False,
                "stage": "Apify",
                "error": "Apify のデータセット結果が空でした",
                "httpStatus": status_code,
                "videoUrl": video_url,
            }

        item = data[0]
        captions = item.get("captions")
        if not captions:
            return {
                "ok": False,
                "stage": "Apify",
                "error": "Apify の captions が空でした",
                "httpStatus": status_code,
                "videoUrl": video_url,
                "itemCount": len(data) if isinstance(data, list) else 0,
                "title": item.get("title", ""),
            }

        if isinstance(captions, list):
            caption_text = " ".join(
                str(part.get("text", "") if isinstance(part, dict) else part).strip()
                for part in captions
                if part
            ).strip()
        else:
            caption_text = str(captions).strip()

        if not caption_text:
            return {
                "ok": False,
                "stage": "Apify",
                "error": "Apify の文字起こし本文が空でした",
                "httpStatus": status_code,
                "videoUrl": video_url,
                "itemCount": len(data) if isinstance(data, list) else 0,
                "title": item.get("title", ""),
            }

        channel_name, channel_url = _channel_metadata(item)
        duration = _first_value(item, "duration", "durationSeconds")
        thumbnail_url = _first_value(item, "thumbnailUrl", "thumbnail", "thumbnail_url")
        published_at = _first_value(item, "publishedAt", "uploadDate", "date")
        title = _first_value(item, "title", "videoTitle")

        return {
            "ok": True,
            "stage": "Apify",
            "httpStatus": status_code,
            "videoUrl": video_url,
            "itemCount": len(data) if isinstance(data, list) else 0,
            "captionChars": len(caption_text),
            "transcript": {
                "title": str(title or "").strip(),
                "captions": caption_text,
                "video_id": item.get("videoId", ""),
                "url": video_url,
                "channel_name": channel_name,
                "channel_url": channel_url,
                "published_at": str(published_at or "").strip(),
                "duration": str(duration or "").strip(),
                "thumbnail_url": str(thumbnail_url or "").strip(),
            },
        }
    except requests.RequestException as error:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        body = _read_response_text(response)[:400] if response is not None else ""
        detail = str(error).strip()
        if status_code:
            detail = f"HTTP {status_code}: {detail}"
        if body:
            detail = f"{detail} | {body}"
        print(f"   Apify エラー: {detail}")
        return {
            "ok": False,
            "stage": "Apify",
            "error": detail or "Apify リクエストに失敗しました",
            "httpStatus": status_code,
            "videoUrl": video_url,
        }
