from typing import Optional

import requests

ACTOR_ID = "1s7eXiaukVuOr4Ueg"
APIFY_BASE_URL = "https://api.apify.com/v2"


def get_transcript(video_url: str, api_key: str, language: str = "ja") -> Optional[dict]:
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
        response.raise_for_status()
        data = response.json()
        if not data:
            return None

        item = data[0]
        captions = item.get("captions")
        if not captions:
            return None

        if isinstance(captions, list):
            caption_text = " ".join(
                str(part.get("text", "") if isinstance(part, dict) else part).strip()
                for part in captions
                if part
            ).strip()
        else:
            caption_text = str(captions).strip()

        if not caption_text:
            return None

        return {
            "title": item.get("title", ""),
            "captions": caption_text,
            "video_id": item.get("videoId", ""),
            "url": video_url,
        }
    except requests.RequestException as error:
        print(f"   Apify エラー: {error}")
        return None
