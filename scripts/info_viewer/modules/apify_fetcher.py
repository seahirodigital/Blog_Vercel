import os
import time
from typing import Any, Optional

import requests

DEFAULT_ACTOR_ID = "1s7eXiaukVuOr4Ueg"
ACTOR_ID = os.getenv("INFO_VIEWER_APIFY_ACTOR_ID", DEFAULT_ACTOR_ID).strip() or DEFAULT_ACTOR_ID
APIFY_BASE_URL = "https://api.apify.com/v2"
FALLBACK_ACTOR_ID = "actose~youtube-transcripts"
MAX_RETRIES = max(1, int(os.getenv("INFO_VIEWER_APIFY_MAX_RETRIES", "3") or 3))
RETRY_WAIT_SECONDS = max(1, int(os.getenv("INFO_VIEWER_APIFY_RETRY_SECONDS", "15") or 15))


def _read_response_text(response: requests.Response) -> str:
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def _is_retryable_status(status_code: Optional[int]) -> bool:
    return status_code is None or status_code == 429 or (status_code is not None and status_code >= 500)


def _fallback_transcript(video_url: str, api_key: str, language: str, reason: str) -> dict[str, Any]:
    print(f"   字幕が空のため代替 Actor で取得します: {reason}")
    try:
        response = requests.post(
            f"{APIFY_BASE_URL}/acts/{FALLBACK_ACTOR_ID}/run-sync-get-dataset-items",
            json={"urls": [video_url.strip()], "language": language, "fallbackToAnyLanguage": True,
                  "includeTimestamps": False, "includeMarkdown": False, "saveSrtFile": False},
            params={"timeout": 300, "maxItems": 1},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=360,
        )
        response.raise_for_status()
        data = response.json()
        item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        captions = item.get("text")
        if item.get("status") == "success" and isinstance(captions, str) and captions.strip():
            captions = captions.strip()
            print(f"   代替 Actor から字幕を取得: {len(captions)}文字")
            return {"ok": True, "stage": "Apify", "httpStatus": response.status_code,
                    "videoUrl": video_url, "itemCount": len(data), "captionChars": len(captions),
                    "transcript": {"title": item.get("title", ""), "captions": captions,
                                   "video_id": item.get("videoId", ""), "url": video_url}}
        detail = str(item.get("error") or item.get("status") or "結果が空でした")[:300]
        return {"ok": False, "stage": "Apify", "error": f"{reason} / 代替 Actor: {detail}",
                "httpStatus": response.status_code, "videoUrl": video_url}
    except (requests.RequestException, ValueError) as error:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        return {"ok": False, "stage": "Apify", "error": f"{reason} / 代替 Actor の取得失敗: {error}",
                "httpStatus": status_code, "videoUrl": video_url}


def get_transcript(video_url: str, api_key: str, language: str = "ja") -> dict[str, Any]:
    print(f"   Apify で文字起こし取得: {video_url}")
    run_url = f"{APIFY_BASE_URL}/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload = {
        "urls": [video_url.strip()],
        "captionsBoolean": True,
        "captionsLanguage": language,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"timeout": 300, "maxItems": 1}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                run_url,
                json=payload,
                params=params,
                headers=headers,
                timeout=360,
            )
            status_code = response.status_code
            if _is_retryable_status(status_code) and attempt < MAX_RETRIES:
                wait_seconds = RETRY_WAIT_SECONDS * attempt
                print(
                    f"   Apify 一時エラー HTTP {status_code}。"
                    f"{wait_seconds}秒後に再試行します ({attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait_seconds)
                continue

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
                detail = " / ".join(str(item.get(key))[:200] for key in ("status", "reason", "error") if item.get(key))
                reason = "Apify の captions が空でした" + (f" ({detail})" if detail else "")
                return _fallback_transcript(video_url, api_key, language, reason)

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

            return {
                "ok": True,
                "stage": "Apify",
                "httpStatus": status_code,
                "videoUrl": video_url,
                "itemCount": len(data) if isinstance(data, list) else 0,
                "captionChars": len(caption_text),
                "transcript": {
                    "title": item.get("title", ""),
                    "captions": caption_text,
                    "video_id": item.get("videoId", ""),
                    "url": video_url,
                },
            }
        except requests.RequestException as error:
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
            if _is_retryable_status(status_code) and attempt < MAX_RETRIES:
                wait_seconds = RETRY_WAIT_SECONDS * attempt
                print(
                    f"   Apify 通信エラー。{wait_seconds}秒後に再試行します "
                    f"({attempt}/{MAX_RETRIES}): {error}"
                )
                time.sleep(wait_seconds)
                continue

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

    return {
        "ok": False,
        "stage": "Apify",
        "error": "Apify リクエストの再試行回数を超えました",
        "videoUrl": video_url,
    }
