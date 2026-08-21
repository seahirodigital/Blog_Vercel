import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from modules import apify_fetcher, gemini_formatter, notion_writer, onedrive_writer, state_store


load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
GEMINI_TOKEN_CANDIDATES = (
    ("GEMINI_TOKEN_invest", os.getenv("GEMINI_TOKEN_invest", "") or os.getenv("GEMINI_TOKEN_INVEST", "")),
    (
        "GEMINI_TOKEN_INVESTsub",
        os.getenv("GEMINI_TOKEN_INVESTsub", "") or os.getenv("GEMINI_TOKEN_INVESTSUB", ""),
    ),
    ("GEMINI_TOKEN_tech", os.getenv("GEMINI_TOKEN_tech", "") or os.getenv("GEMINI_TOKEN_TECH", "")),
)


def parse_args():
    parser = argparse.ArgumentParser(description="info_viewer 手動URL単発処理")
    parser.add_argument("--video-url", required=True)
    return parser.parse_args()


def _normalized_video_url(video_url: str) -> str:
    normalized = onedrive_writer.normalize_youtube_url(video_url)
    if not normalized.startswith("https://www.youtube.com/watch?v="):
        raise ValueError(f"YouTube 動画URLの形式が不正です: {video_url}")
    return normalized


def _fetch_oembed(video_url: str) -> dict[str, str]:
    response = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": video_url, "format": "json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "title": str(payload.get("title") or "").strip(),
        "channel_name": str(payload.get("author_name") or "手動URL").strip(),
        "channel_url": str(payload.get("author_url") or "").strip(),
        "thumbnail_url": str(payload.get("thumbnail_url") or "").strip(),
    }


def _find_existing_article(saved_articles: list[dict[str, Any]], video_url: str) -> dict[str, Any] | None:
    normalized = _normalized_video_url(video_url)
    for article in saved_articles:
        if article.get("youtubeUrlNormalized") == normalized:
            return article
    return None


def _gemini_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_tokens: set[str] = set()
    for token_name, token_value in GEMINI_TOKEN_CANDIDATES:
        token = str(token_value or "").strip()
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        candidates.append((token_name, token))
    return candidates


def _save_github_output(channel_name: str, title: str, notion_page_id: str):
    github_output = os.getenv("GITHUB_OUTPUT", "")
    if not github_output or not notion_page_id:
        return
    safe_channel = channel_name.replace(",", "，").replace("|", "｜")
    safe_title = title.replace(",", "，").replace("|", "｜")
    page_id = notion_page_id.replace("-", "")
    with open(github_output, "a", encoding="utf-8") as output_file:
        output_file.write(f"notion_urls={safe_channel}|{safe_title}|https://notion.so/{page_id}\n")


def _mark_failed(
    state: dict[str, Any],
    video_url: str,
    run_id: str,
    stage: str,
    message: str,
    *,
    quota: bool = False,
):
    state_store.mark_retry(
        state,
        video_url,
        stage,
        message,
        run_id,
        wait_seconds=state_store.resolve_retry_wait_seconds(quota=quota),
        status=state_store.DEFERRED_STATUS if quota else state_store.FAILED_STATUS,
    )
    state_store.save_state(state)


def main() -> int:
    args = parse_args()
    video_url = _normalized_video_url(args.video_url)
    run_id = datetime.now(timezone.utc).strftime("manual-%Y%m%dT%H%M%SZ")

    if not APIFY_API_KEY:
        raise RuntimeError("APIFY_API_KEY が設定されていません")
    if not _gemini_candidates():
        raise RuntimeError("info_viewer 用の Gemini API キーが設定されていません")

    print("=" * 72)
    print("info_viewer 手動URL単発処理開始")
    print(f"対象URL: {video_url}")
    print("=" * 72)

    saved_articles = onedrive_writer.list_saved_articles()
    existing_article = _find_existing_article(saved_articles, video_url)
    if existing_article:
        print(f"生成済み記事のため重複処理をスキップ: {existing_article.get('relativePath', '')}")
        return 0

    metadata = _fetch_oembed(video_url)
    video = {
        "row_number": None,
        "video_url": video_url,
        "video_title": metadata["title"],
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "video_updated_at": "",
        "duration": "",
        "thumbnail_url": metadata["thumbnail_url"],
        "status": "",
        "channel_name": metadata["channel_name"],
        "channel_url": metadata["channel_url"],
        "gemini_profile": "manual",
    }

    state = state_store.load_state()
    existing_article_map = {
        article.get("youtubeUrlNormalized"): article
        for article in saved_articles
        if article.get("youtubeUrlNormalized")
    }
    state_store.sync_target_videos(state, [video], existing_article_map, deactivate_missing=False)
    state_store.prioritize_video(state, video_url)
    state_store.mark_processing(state, video_url, run_id)
    state_store.save_state(state)

    apify_result = apify_fetcher.get_transcript(video_url, APIFY_API_KEY)
    if not apify_result.get("ok"):
        message = apify_result.get("error") or "Apify から文字起こしを取得できませんでした"
        _mark_failed(state, video_url, run_id, "Apify", message)
        raise RuntimeError(message)

    transcript = apify_result["transcript"]
    title = transcript.get("title") or metadata["title"] or "動画タイトル未設定"
    video["video_title"] = title

    gemini_result: dict[str, Any] | None = None
    gemini_errors: list[str] = []
    quota_failure = False
    for token_name, api_key in _gemini_candidates():
        print(f"Gemini 整形を実行: {token_name}")
        candidate_result = gemini_formatter.format_transcript(transcript, api_key, video)
        if candidate_result.get("ok"):
            gemini_result = candidate_result
            break
        quota_failure = quota_failure or bool(candidate_result.get("stopPipeline"))
        gemini_errors.append(f"{token_name}: {candidate_result.get('error') or 'Gemini 整形失敗'}")

    if not gemini_result:
        message = " / ".join(gemini_errors) or "Gemini 整形に失敗しました"
        _mark_failed(state, video_url, run_id, "Gemini", message, quota=quota_failure)
        raise RuntimeError(message)

    markdown = gemini_result["markdown"]
    try:
        upload_result = onedrive_writer.upload_markdown(
            channel_name=video["channel_name"],
            title=title,
            published_at=video["published_at"],
            markdown_body=markdown,
            metadata={
                "video_url": video_url,
                "channel_url": video["channel_url"],
                "duration": video["duration"],
                "sheet_status": "完了",
                "apify_transcript": transcript.get("captions", ""),
            },
        )
    except Exception as error:
        _mark_failed(state, video_url, run_id, "OneDrive", str(error))
        raise

    notion_page_id = ""
    if notion_writer.is_configured():
        try:
            notion_result = notion_writer.save_article(
                video=video,
                title=title,
                markdown=markdown,
                transcript_text=transcript.get("captions", ""),
                upload_result=upload_result,
            )
            notion_page_id = notion_result.get("pageId", "")
            upload_result["notionPageId"] = notion_page_id
            upload_result["notionDatabaseId"] = notion_result.get("databaseId", "")
            upload_result["notionAction"] = notion_result.get("action", "")
            print(f"Notion 保存完了: {notion_writer.schema_summary(notion_result)}")
        except Exception as error:
            print(f"Notion 保存は任意のためスキップ: {error}")

    state_store.mark_done(state, video_url, run_id, upload_result=upload_result)
    state_store.save_state(state)
    _save_github_output(video["channel_name"], title, notion_page_id)

    print("-" * 72)
    print("手動URL単発処理成功")
    print(f"OneDrive: {upload_result.get('relativePath', '')}")
    print(f"Notion page ID: {notion_page_id or '保存なし'}")
    print("-" * 72)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"手動URL単発処理に失敗: {error}", file=sys.stderr)
        raise
