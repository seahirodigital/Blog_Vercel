import argparse
import os
import sys
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from modules import apify_fetcher, gemini_formatter, manifest_builder, onedrive_writer, sheet_reader

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
CHANNEL_SHEET_NAME = os.getenv("INFO_VIEWER_CHANNEL_SHEET_NAME", "チャンネル設定")
VIDEO_SHEET_NAME = os.getenv("INFO_VIEWER_VIDEO_SHEET_NAME", "動画リスト")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def parse_args():
    parser = argparse.ArgumentParser(description="info_viewer 自動取得パイプライン")
    parser.add_argument("--max-items", type=int, default=int(os.getenv("INFO_VIEWER_MAX_ITEMS", "0") or 0))
    parser.add_argument("--channel-name", type=str, default="")
    parser.add_argument("--video-url", type=str, default="")
    parser.add_argument("--rebuild-manifest-only", action="store_true")
    return parser.parse_args()


def _matches_filter(video: dict[str, Any], args) -> bool:
    if args.channel_name and video.get("channel_name") != args.channel_name:
        return False
    if args.video_url and video.get("video_url") != args.video_url:
        return False
    return True


def main():
    print("=" * 72)
    print("info_viewer パイプライン開始")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    args = parse_args()
    required = []
    if not SPREADSHEET_ID:
        required.append("SPREADSHEET_ID")
    if not args.rebuild_manifest_only and not APIFY_API_KEY:
        required.append("APIFY_API_KEY")
    if not args.rebuild_manifest_only and not GEMINI_API_KEY:
        required.append("GEMINI_API_KEY")
    if required:
        print(f"必須環境変数が不足しています: {', '.join(required)}")
        sys.exit(1)

    target_channels, all_target_videos = sheet_reader.get_target_videos(
        SPREADSHEET_ID,
        channel_sheet_name=CHANNEL_SHEET_NAME,
        video_sheet_name=VIDEO_SHEET_NAME,
        include_completed=True,
    )
    print(f"対象チャンネル数: {len(target_channels)}")
    print(f"対象動画数: {len(all_target_videos)}")

    saved_articles_before = onedrive_writer.list_saved_articles()
    existing_article_map = {
        article.get("youtubeUrlNormalized"): article
        for article in saved_articles_before
        if article.get("youtubeUrlNormalized")
    }

    synced_count = 0
    for video in all_target_videos:
        normalized_url = onedrive_writer.normalize_youtube_url(video.get("video_url", ""))
        if normalized_url in existing_article_map and video.get("status") != "完了":
            try:
                sheet_reader.update_video_status(
                    SPREADSHEET_ID,
                    video["row_number"],
                    "完了",
                    sheet_name=VIDEO_SHEET_NAME,
                )
                video["status"] = "完了"
                synced_count += 1
            except Exception as error:
                print(f"状態同期に失敗: {video.get('video_url')} / {error}")

    if synced_count:
        print(f"既存記事に合わせて状況を完了へ同期: {synced_count}件")

    pending_videos = [
        video
        for video in all_target_videos
        if video.get("status") != "完了"
        and onedrive_writer.normalize_youtube_url(video.get("video_url", "")) not in existing_article_map
        and _matches_filter(video, args)
    ]

    if args.max_items > 0:
        pending_videos = pending_videos[: args.max_items]

    failures: list[dict[str, Any]] = []
    success_count = 0

    if args.rebuild_manifest_only:
        print("manifest 再構築のみ実行します。")
    elif not pending_videos:
        print("新規処理対象はありません。manifest のみ更新します。")
    else:
        print(f"処理対象件数: {len(pending_videos)}")

        for index, video in enumerate(pending_videos, start=1):
            title_for_log = video.get("video_title") or video.get("video_url")
            print(f"[{index}/{len(pending_videos)}] {title_for_log}")

            transcript = apify_fetcher.get_transcript(video["video_url"], APIFY_API_KEY)
            if not transcript:
                failures.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": title_for_log,
                        "error": "Apify から文字起こしを取得できませんでした",
                        "occurredAt": datetime.now().isoformat(),
                    }
                )
                continue

            actual_title = video.get("video_title") or transcript.get("title") or "無題"
            video["video_title"] = actual_title
            markdown = gemini_formatter.format_transcript(transcript, GEMINI_API_KEY, video)
            if not markdown:
                failures.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": actual_title,
                        "error": "Gemini 整形に失敗しました",
                        "occurredAt": datetime.now().isoformat(),
                    }
                )
                continue

            try:
                onedrive_writer.upload_markdown(
                    channel_name=video["channel_name"],
                    title=actual_title,
                    published_at=video.get("published_at", ""),
                    markdown_body=markdown,
                    metadata={
                        "video_url": video["video_url"],
                        "channel_url": video.get("channel_url", ""),
                        "duration": video.get("duration", ""),
                        "sheet_status": "完了",
                    },
                )
                sheet_reader.update_video_status(
                    SPREADSHEET_ID,
                    video["row_number"],
                    "完了",
                    sheet_name=VIDEO_SHEET_NAME,
                )
                video["status"] = "完了"
                success_count += 1
            except Exception as error:
                failures.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": actual_title,
                        "error": str(error),
                        "occurredAt": datetime.now().isoformat(),
                    }
                )

    saved_articles_after = onedrive_writer.list_saved_articles()
    manifest = manifest_builder.build_manifest(
        target_channels=target_channels,
        target_videos=all_target_videos,
        saved_articles=saved_articles_after,
        failures=failures,
    )
    manifest_builder.write_manifest(manifest)

    print("-" * 72)
    print(f"成功: {success_count}件")
    print(f"失敗: {len(failures)}件")
    print(f"manifest 更新済み: {manifest.get('generatedAt')}")
    print("-" * 72)

    for failure in failures:
        print(f"失敗: {failure['title']} / {failure['error']}")


if __name__ == "__main__":
    main()
