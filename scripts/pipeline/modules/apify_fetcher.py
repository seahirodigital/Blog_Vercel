"""
Apify クライアント (GitHub Actions 対応版)
YouTube動画の文字起こし（スクリプト）をApify経由で取得する
"""

import requests
from typing import Optional

# ApifyのYouTube Transcripts Actor ID
ACTOR_ID = "1s7eXiaukVuOr4Ueg"
APIFY_BASE_URL = "https://api.apify.com/v2"


def get_transcript(video_url: str, api_key: str, language: str = "ja") -> Optional[dict]:
    """
    YouTube動画の文字起こしをApify経由で取得する

    Returns:
        {
            "title": "動画タイトル",
            "captions": "文字起こしテキスト全文",
            "video_id": "動画ID",
            "url": "元のURL"
        }
        または None（字幕なし・エラー時）
    """
    print(f"   🎬 Apifyでスクリプト取得中: {video_url}")

    run_url = f"{APIFY_BASE_URL}/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    headers = {"Content-Type": "application/json"}
    params = {"token": api_key, "memory": 8192, "timeout": 300}

    payload = {
        "urls": [video_url.strip()],
        "captionsBoolean": True,
        "captionsLanguage": language
    }

    try:
        response = requests.post(run_url, json=payload, headers=headers, params=params, timeout=360)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            print(f"   ⚠️ データが取得できませんでした: {video_url}")
            return None

        item = data[0]

        # 字幕チェック
        captions = item.get("captions")
        if not captions or (isinstance(captions, list) and (len(captions) == 0 or captions[0] is None)):
            print(f"   ⚠️ 字幕なし（スキップ）: {video_url}")
            return None

        # 字幕をテキストに変換
        if isinstance(captions, list):
            caption_text = " ".join([
                c.get("text", "") if isinstance(c, dict) else str(c)
                for c in captions if c
            ])
        else:
            caption_text = str(captions)

        title = item.get("title", "無題")
        video_id = item.get("videoId", "")

        print(f"   ✅ スクリプト取得完了: 「{title}」({len(caption_text)}文字)")
        return {
            "title": title,
            "captions": caption_text,
            "video_id": video_id,
            "url": video_url
        }

    except requests.exceptions.Timeout:
        print(f"   ❌ タイムアウト: {video_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"   ❌ APIエラー: {e}")
        return None
