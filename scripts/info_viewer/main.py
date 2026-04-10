from runner import main as runner_main


if __name__ == "__main__":
    runner_main()
    raise SystemExit

import argparse
import os
import sys
import time
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
GEMINI_SERIAL_DELAY_SECONDS = int(os.getenv("INFO_VIEWER_GEMINI_SERIAL_DELAY_SECONDS", "20") or 20)


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


def _now_iso() -> str:
    return datetime.now().isoformat()


def _video_key(video_url: str) -> str:
    return onedrive_writer.normalize_youtube_url(video_url or "")


def _append_processing_log(
    logs: list[dict[str, Any]],
    run_id: str,
    video: dict[str, Any] | None,
    stage: str,
    status: str,
    message: str,
    **extra: Any,
):
    entry = {
        "runId": run_id,
        "occurredAt": _now_iso(),
        "stage": stage,
        "status": status,
        "message": message,
    }
    if video:
        entry.update(
            {
                "videoUrl": video.get("video_url", ""),
                "title": video.get("video_title") or video.get("video_url", ""),
                "channelName": video.get("channel_name", ""),
                "rowNumber": video.get("row_number"),
            }
        )
    entry.update({key: value for key, value in extra.items() if value not in (None, "")})
    logs.append(entry)


def _merge_failures(
    previous_failures: list[dict[str, Any]],
    new_failures: list[dict[str, Any]],
    resolved_keys: set[str],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for failure in previous_failures + new_failures:
        key = _video_key(failure.get("videoUrl", ""))
        if not key or key in resolved_keys:
            continue
        current = merged.get(key)
        if current is None or str(current.get("occurredAt", "")) <= str(failure.get("occurredAt", "")):
            merged[key] = failure
    return sorted(merged.values(), key=lambda item: str(item.get("occurredAt", "")), reverse=True)


def _merge_processing_logs(previous_logs: list[dict[str, Any]], new_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = []
    if isinstance(previous_logs, list):
        merged.extend(previous_logs[-250:])
    merged.extend(new_logs)
    return merged[-500:]


def _sleep_before_next_gemini_request(current_index: int, total_count: int, reason: str):
    if GEMINI_SERIAL_DELAY_SECONDS <= 0 or current_index >= total_count:
        return
    print(f"次の Gemini 処理まで {GEMINI_SERIAL_DELAY_SECONDS}秒待機します: {reason}")
    time.sleep(GEMINI_SERIAL_DELAY_SECONDS)


def main():
    print("=" * 72)
    print("info_viewer パイプライン開始")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
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

    previous_manifest: dict[str, Any] = {}
    previous_failures: list[dict[str, Any]] = []
    previous_processing_logs: list[dict[str, Any]] = []
    try:
        previous_manifest = onedrive_writer.download_json("manifest.json") or {}
        if isinstance(previous_manifest, dict):
            previous_failures = previous_manifest.get("failures", []) if isinstance(previous_manifest.get("failures"), list) else []
            previous_processing_logs = (
                previous_manifest.get("processingLogs", [])
                if isinstance(previous_manifest.get("processingLogs"), list)
                else []
            )
    except Exception as error:
        print(f"既存 manifest の読み込みをスキップ: {error}")

    saved_articles_before = onedrive_writer.list_saved_articles()
    existing_article_map = {
        article.get("youtubeUrlNormalized"): article
        for article in saved_articles_before
        if article.get("youtubeUrlNormalized")
    }

    synced_count = 0
    processing_logs: list[dict[str, Any]] = []
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
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "状況同期",
                    "success",
                    "既存記事に合わせて状況を完了へ同期しました",
                )
            except Exception as error:
                print(f"状態同期に失敗: {video.get('video_url')} / {error}")
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "状況同期",
                    "failed",
                    str(error),
                )

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

    failures_this_run: list[dict[str, Any]] = []
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
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "開始",
                "queued",
                "対象動画の処理を開始しました",
            )

            apify_result = apify_fetcher.get_transcript(video["video_url"], APIFY_API_KEY)
            if not apify_result.get("ok"):
                failures_this_run.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": title_for_log,
                        "stageKey": "apify",
                        "stage": "Apify",
                        "error": apify_result.get("error") or "Apify から文字起こしを取得できませんでした",
                        "occurredAt": _now_iso(),
                        "httpStatus": apify_result.get("httpStatus"),
                    }
                )
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "Apify",
                    "failed",
                    apify_result.get("error") or "Apify から文字起こしを取得できませんでした",
                    httpStatus=apify_result.get("httpStatus"),
                )
                continue

            transcript = apify_result["transcript"]
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "Apify",
                "success",
                "文字起こしを取得しました",
                captionChars=apify_result.get("captionChars"),
                itemCount=apify_result.get("itemCount"),
            )
            actual_title = video.get("video_title") or transcript.get("title") or "無題"
            video["video_title"] = actual_title
            gemini_result = gemini_formatter.format_transcript(transcript, GEMINI_API_KEY, video)
            if not gemini_result.get("ok"):
                failures_this_run.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": actual_title,
                        "stageKey": "gemini",
                        "stage": "Gemini",
                        "error": gemini_result.get("error") or "Gemini 整形に失敗しました",
                        "occurredAt": _now_iso(),
                        "model": gemini_result.get("model"),
                        "transport": gemini_result.get("transport"),
                        "attemptCount": gemini_result.get("attemptCount"),
                        "transcriptChars": gemini_result.get("transcriptChars"),
                        "inputChars": gemini_result.get("inputChars"),
                        "trimmed": gemini_result.get("trimmed"),
                        "attempts": gemini_result.get("attempts", []),
                    }
                )
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "Gemini",
                    "failed",
                    gemini_result.get("error") or "Gemini 整形に失敗しました",
                    model=gemini_result.get("model"),
                    transport=gemini_result.get("transport"),
                    attemptCount=gemini_result.get("attemptCount"),
                    transcriptChars=gemini_result.get("transcriptChars"),
                    inputChars=gemini_result.get("inputChars"),
                    trimmed=gemini_result.get("trimmed"),
                    recommendedWaitSeconds=gemini_result.get("recommendedWaitSeconds"),
                )
                if gemini_result.get("stopPipeline"):
                    remaining_videos = pending_videos[index:]
                    if remaining_videos:
                        wait_seconds = gemini_result.get("recommendedWaitSeconds") or 0
                        carry_message = "Gemini の quota 到達のため次回 run に繰り越します"
                        if wait_seconds:
                            carry_message = f"{carry_message}（推奨待機 {wait_seconds}秒）"
                        for remaining_video in remaining_videos:
                            _append_processing_log(
                                processing_logs,
                                run_id,
                                remaining_video,
                                "Gemini",
                                "deferred",
                                carry_message,
                            )
                        print(f"Gemini quota 到達のため残り {len(remaining_videos)} 件は次回へ繰り越します。")
                    break
                _sleep_before_next_gemini_request(index, len(pending_videos), "Gemini 失敗後の直列待機")
                continue

            markdown = gemini_result["markdown"]
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "Gemini",
                "success",
                "Markdown 整形に成功しました",
                model=gemini_result.get("model"),
                transport=gemini_result.get("transport"),
                attemptCount=gemini_result.get("attemptCount"),
                transcriptChars=gemini_result.get("transcriptChars"),
                inputChars=gemini_result.get("inputChars"),
                trimmed=gemini_result.get("trimmed"),
            )

            try:
                upload_result = onedrive_writer.upload_markdown(
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
            except Exception as error:
                failures_this_run.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": actual_title,
                        "stageKey": "onedrive",
                        "stage": "OneDrive保存",
                        "error": str(error),
                        "occurredAt": _now_iso(),
                    }
                )
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "OneDrive保存",
                    "failed",
                    str(error),
                )
                continue

            success_count += 1
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "OneDrive保存",
                "success",
                "Markdown を OneDrive に保存しました",
                fileId=upload_result.get("id"),
                relativePath=upload_result.get("relativePath"),
            )

            try:
                sheet_reader.update_video_status(
                    SPREADSHEET_ID,
                    video["row_number"],
                    "完了",
                    sheet_name=VIDEO_SHEET_NAME,
                )
                video["status"] = "完了"
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "状況更新",
                    "success",
                    "Google Sheets の状況を完了へ更新しました",
                )
            except Exception as error:
                failures_this_run.append(
                    {
                        "videoUrl": video["video_url"],
                        "title": actual_title,
                        "stageKey": "sheet_update",
                        "stage": "状況更新",
                        "error": str(error),
                        "occurredAt": _now_iso(),
                    }
                )
                _append_processing_log(
                    processing_logs,
                    run_id,
                    video,
                    "状況更新",
                    "failed",
                    str(error),
                )

            _sleep_before_next_gemini_request(index, len(pending_videos), "動画ごとの Gemini 直列化")

    saved_articles_after = onedrive_writer.list_saved_articles()
    resolved_keys = {
        article.get("youtubeUrlNormalized")
        for article in saved_articles_after
        if article.get("youtubeUrlNormalized")
    }
    merged_failures = _merge_failures(previous_failures, failures_this_run, resolved_keys)
    merged_processing_logs = _merge_processing_logs(previous_processing_logs, processing_logs)
    manifest = manifest_builder.build_manifest(
        target_channels=target_channels,
        target_videos=all_target_videos,
        saved_articles=saved_articles_after,
        failures=merged_failures,
        processing_logs=merged_processing_logs,
        run_id=run_id,
    )
    manifest_builder.write_manifest(manifest)

    print("-" * 72)
    print(f"成功: {success_count}件")
    print(f"失敗: {len(failures_this_run)}件")
    print(f"manifest 更新済み: {manifest.get('generatedAt')}")
    print("-" * 72)

    for failure in failures_this_run:
        print(f"失敗: {failure['title']} / {failure['stage']} / {failure['error']}")


if __name__ == "__main__":
    from runner import main as runner_main

    runner_main()
