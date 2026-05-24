from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from modules import notion_writer, onedrive_writer, state_store


load_dotenv()


def _timestamp(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        normalized = " ".join(text.split()).replace("/", "-")
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="info_viewer の既存OneDrive記事をNotionへ保存します")
    parser.add_argument("--limit", type=int, default=int(os.getenv("INFO_VIEWER_NOTION_BACKFILL_LIMIT", "5") or 5))
    parser.add_argument("--article-id", default="", help="特定のOneDrive item IDだけを保存する")
    parser.add_argument("--video-url", default="", help="特定のYouTube URLだけを保存する")
    parser.add_argument("--no-state-update", action="store_true", help="pipeline_state.json へNotion保存結果を書き戻さない")
    return parser.parse_args()


def _select_articles(articles: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = [article for article in articles if article.get("fileId") and article.get("relativePath")]

    if args.article_id:
        selected = [article for article in selected if article.get("fileId") == args.article_id]

    normalized_filter = onedrive_writer.normalize_youtube_url(args.video_url)
    if normalized_filter:
        selected = [
            article
            for article in selected
            if article.get("youtubeUrlNormalized") == normalized_filter
            or onedrive_writer.normalize_youtube_url(article.get("youtubeUrl", "")) == normalized_filter
        ]

    selected.sort(
        key=lambda article: (
            _timestamp(article.get("publishedAt", "")),
            _timestamp(article.get("lastModified", "")),
        ),
        reverse=True,
    )
    limit = max(1, min(int(args.limit or 5), 20))
    return selected[:limit]


def _load_markdown(article: dict[str, Any]) -> tuple[dict[str, str], str]:
    relative_path = article.get("relativePath", "")
    if not relative_path:
        raise RuntimeError("記事のrelativePathが空です")
    text = onedrive_writer.download_text(relative_path)
    if text is None:
        raise RuntimeError(f"記事Markdownを取得できません: {relative_path}")
    return onedrive_writer.parse_frontmatter(text)


def _article_to_video(article: dict[str, Any], metadata: dict[str, str]) -> dict[str, Any]:
    return {
        "video_url": article.get("youtubeUrl") or metadata.get("video_url", ""),
        "video_title": article.get("title") or metadata.get("title", ""),
        "channel_name": article.get("channelName") or metadata.get("channel_name", ""),
        "channel_url": article.get("channelUrl") or metadata.get("channel_url", ""),
        "published_at": article.get("publishedAt") or metadata.get("published_at", ""),
        "video_updated_at": article.get("publishedAt") or metadata.get("published_at", ""),
        "duration": article.get("duration") or metadata.get("duration", ""),
        "status": article.get("sheetStatus") or metadata.get("sheet_status", ""),
    }


def _upload_result(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": article.get("fileId", ""),
        "name": article.get("fileName", ""),
        "webUrl": article.get("webUrl", ""),
        "relativePath": article.get("relativePath", ""),
        "title": article.get("title", ""),
    }


def _update_state(article: dict[str, Any], notion_result: dict[str, Any]) -> None:
    youtube_url = article.get("youtubeUrl") or article.get("youtubeUrlNormalized") or ""
    if not youtube_url:
        return

    try:
        state = state_store.load_state()
        record = state_store.get_record(state, youtube_url)
        record["notionPageId"] = notion_result.get("pageId", "")
        record["notionDatabaseId"] = notion_result.get("databaseId", "")
        record["notionAction"] = notion_result.get("action", "")
        state_store.save_state(state)
    except Exception as error:
        print(f"   ⚠️ state更新をスキップしました: {error}")


def main() -> int:
    args = _parse_args()
    if not notion_writer.is_configured():
        print("Notion APIトークンまたはDB IDが未設定です。", file=sys.stderr)
        return 2

    articles = _select_articles(onedrive_writer.list_saved_articles(), args)
    if not articles:
        print("Notion保存対象の既存記事が見つかりません。", file=sys.stderr)
        return 1

    print(f"Notion保存対象: {len(articles)}件")
    success_count = 0
    failures: list[dict[str, str]] = []

    for index, article in enumerate(articles, start=1):
        title = article.get("title") or article.get("fileName") or article.get("fileId")
        print(f"[{index}/{len(articles)}] {title}")
        try:
            metadata, body = _load_markdown(article)
            video = _article_to_video(article, metadata)
            notion_result = notion_writer.save_article(
                video=video,
                title=article.get("title") or metadata.get("title") or title,
                markdown=body,
                transcript_text="",
                upload_result=_upload_result(article),
            )
            success_count += 1
            if not args.no_state_update:
                _update_state(article, notion_result)
            print(f"   Notion保存完了: {notion_writer.schema_summary(notion_result)}")
        except Exception as error:
            message = str(error)
            failures.append({"title": str(title), "error": message})
            print(f"   Notion保存失敗: {message}", file=sys.stderr)

    print("-" * 72)
    print(f"成功: {success_count}件")
    print(f"失敗: {len(failures)}件")
    for failure in failures:
        print(f"失敗: {failure['title']} / {failure['error']}")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
