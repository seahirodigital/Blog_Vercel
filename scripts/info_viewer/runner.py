import argparse
import os
import sys
import time
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from modules import apify_fetcher, gemini_formatter, manifest_builder, onedrive_writer, sheet_reader, state_store

load_dotenv()

COMPLETED_STATUS = "完了"
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
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--process-queue", action="store_true")
    parser.add_argument("--rebuild-manifest-only", action="store_true")
    return parser.parse_args()


def _resolve_run_mode(args) -> str:
    if args.rebuild_manifest_only:
        return "rebuild_manifest_only"
    if args.sync_only and args.process_queue:
        return "full"
    if args.sync_only:
        return "sync_only"
    if args.process_queue:
        return "process_queue"
    return "full"


def _matches_filter(video: dict[str, Any], args) -> bool:
    if args.channel_name and video.get("channel_name") != args.channel_name:
        return False
    if args.video_url and video.get("video_url") != args.video_url:
        return False
    return True


def _has_filters(args) -> bool:
    return bool(args.channel_name or args.video_url)


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


def _load_previous_manifest_state() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        previous_manifest = onedrive_writer.download_json("manifest.json") or {}
        if not isinstance(previous_manifest, dict):
            return [], []
        previous_failures = previous_manifest.get("failures", [])
        previous_processing_logs = previous_manifest.get("processingLogs", [])
        return (
            previous_failures if isinstance(previous_failures, list) else [],
            previous_processing_logs if isinstance(previous_processing_logs, list) else [],
        )
    except Exception as error:
        print(f"既存 manifest の読み込みをスキップします: {error}")
        return [], []


def _build_existing_article_map(saved_articles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        article.get("youtubeUrlNormalized"): article
        for article in saved_articles
        if article.get("youtubeUrlNormalized")
    }


def _sync_sheet_status_for_saved_articles(
    target_videos: list[dict[str, Any]],
    existing_article_map: dict[str, dict[str, Any]],
    processing_logs: list[dict[str, Any]],
    run_id: str,
) -> int:
    synced_count = 0
    for video in target_videos:
        normalized_url = _video_key(video.get("video_url", ""))
        if normalized_url not in existing_article_map or video.get("status") == COMPLETED_STATUS:
            continue
        try:
            sheet_reader.update_video_status(
                SPREADSHEET_ID,
                video["row_number"],
                COMPLETED_STATUS,
                sheet_name=VIDEO_SHEET_NAME,
            )
            video["status"] = COMPLETED_STATUS
            synced_count += 1
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "状況同期",
                "success",
                "既存記事に合わせて Google Sheets を完了へ更新しました",
            )
        except Exception as error:
            print(f"状況同期に失敗: {video.get('video_url')} / {error}")
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "状況同期",
                "failed",
                str(error),
            )
    return synced_count


def _require_environment(run_mode: str):
    required = []
    if not SPREADSHEET_ID:
        required.append("SPREADSHEET_ID")
    if run_mode in {"process_queue", "full"} and not APIFY_API_KEY:
        required.append("APIFY_API_KEY")
    if run_mode in {"process_queue", "full"} and not GEMINI_API_KEY:
        required.append("GEMINI_API_KEY")
    if required:
        print(f"必要な環境変数が不足しています: {', '.join(required)}")
        sys.exit(1)


def _append_failure(
    failures: list[dict[str, Any]],
    video: dict[str, Any],
    stage_key: str,
    stage_name: str,
    error: str,
    **extra: Any,
):
    entry = {
        "videoUrl": video.get("video_url", ""),
        "title": video.get("video_title") or video.get("video_url", ""),
        "stageKey": stage_key,
        "stage": stage_name,
        "error": error,
        "occurredAt": _now_iso(),
    }
    entry.update({key: value for key, value in extra.items() if value not in (None, "")})
    failures.append(entry)


def _sync_queue_state(
    state: dict[str, Any],
    target_videos: list[dict[str, Any]],
    existing_article_map: dict[str, dict[str, Any]],
    args,
    processing_logs: list[dict[str, Any]],
    run_id: str,
) -> dict[str, int]:
    sync_targets = [video for video in target_videos if _matches_filter(video, args)]
    sync_stats = state_store.sync_target_videos(
        state,
        sync_targets,
        existing_article_map,
        deactivate_missing=not _has_filters(args),
    )
    state_store.save_state(state)
    _append_processing_log(
        processing_logs,
        run_id,
        None,
        "キュー同期",
        "success",
        "Sheets 差分を処理キューへ同期しました",
        scanned=sync_stats.get("scanned"),
        added=sync_stats.get("added"),
        pending=sync_stats.get("pending"),
        markedDone=sync_stats.get("markedDone"),
        deactivated=sync_stats.get("deactivated"),
    )
    return sync_stats


def _print_queue_summary(state: dict[str, Any], label: str):
    summary = state_store.get_summary(state)
    print(
        f"{label}: total={summary['total']} active={summary['active']} "
        f"queueable={summary['queueable']} pending={summary['pending']} "
        f"deferred={summary['deferred']} failed={summary['failed']} done={summary['done']}"
    )


def _process_pending_videos(
    pending_videos: list[dict[str, Any]],
    state: dict[str, Any],
    run_id: str,
    processing_logs: list[dict[str, Any]],
    failures_this_run: list[dict[str, Any]],
) -> int:
    success_count = 0

    for index, video in enumerate(pending_videos, start=1):
        title_for_log = video.get("video_title") or video.get("video_url")
        print(f"[{index}/{len(pending_videos)}] {title_for_log}")
        state_store.mark_processing(state, video["video_url"], run_id)
        state_store.save_state(state)
        _append_processing_log(
            processing_logs,
            run_id,
            video,
            "処理開始",
            "queued",
            "対象動画の自動記事化を開始しました",
            queueStatus=video.get("_queue_status", ""),
            queueAttemptCount=video.get("_queue_attempt_count"),
        )

        apify_result = apify_fetcher.get_transcript(video["video_url"], APIFY_API_KEY)
        if not apify_result.get("ok"):
            error_message = apify_result.get("error") or "Apify から文字起こしを取得できませんでした"
            retry_record = state_store.mark_retry(
                state,
                video["video_url"],
                "Apify",
                error_message,
                run_id,
                wait_seconds=state_store.resolve_retry_wait_seconds(),
                status=state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures_this_run,
                video,
                "apify",
                "Apify",
                error_message,
                httpStatus=apify_result.get("httpStatus"),
                nextRetryAt=retry_record.get("nextRetryAt"),
            )
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "Apify",
                "failed",
                error_message,
                httpStatus=apify_result.get("httpStatus"),
                nextRetryAt=retry_record.get("nextRetryAt"),
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
            error_message = gemini_result.get("error") or "Gemini 整形に失敗しました"
            quota_stop = bool(gemini_result.get("stopPipeline"))
            retry_wait_seconds = state_store.resolve_retry_wait_seconds(
                gemini_result.get("recommendedWaitSeconds") or 0,
                quota=quota_stop,
            )
            retry_record = state_store.mark_retry(
                state,
                video["video_url"],
                "Gemini",
                error_message,
                run_id,
                wait_seconds=retry_wait_seconds,
                status=state_store.DEFERRED_STATUS if quota_stop else state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures_this_run,
                video,
                "gemini",
                "Gemini",
                error_message,
                model=gemini_result.get("model"),
                transport=gemini_result.get("transport"),
                attemptCount=gemini_result.get("attemptCount"),
                transcriptChars=gemini_result.get("transcriptChars"),
                inputChars=gemini_result.get("inputChars"),
                trimmed=gemini_result.get("trimmed"),
                attempts=gemini_result.get("attempts", []),
                nextRetryAt=retry_record.get("nextRetryAt"),
            )
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "Gemini",
                "failed",
                error_message,
                model=gemini_result.get("model"),
                transport=gemini_result.get("transport"),
                attemptCount=gemini_result.get("attemptCount"),
                transcriptChars=gemini_result.get("transcriptChars"),
                inputChars=gemini_result.get("inputChars"),
                trimmed=gemini_result.get("trimmed"),
                recommendedWaitSeconds=gemini_result.get("recommendedWaitSeconds"),
                nextRetryAt=retry_record.get("nextRetryAt"),
            )

            if quota_stop:
                remaining_videos = pending_videos[index:]
                carry_message = "Gemini の quota 到達のため次回 run に繰り越します"
                if retry_wait_seconds:
                    carry_message = f"{carry_message}。目安待機 {retry_wait_seconds}秒"
                for remaining_video in remaining_videos:
                    carry_record = state_store.mark_retry(
                        state,
                        remaining_video["video_url"],
                        "Gemini",
                        carry_message,
                        run_id,
                        wait_seconds=retry_wait_seconds,
                        status=state_store.DEFERRED_STATUS,
                    )
                    _append_processing_log(
                        processing_logs,
                        run_id,
                        remaining_video,
                        "Gemini",
                        "deferred",
                        carry_message,
                        nextRetryAt=carry_record.get("nextRetryAt"),
                    )
                state_store.save_state(state)
                if remaining_videos:
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
                    "sheet_status": COMPLETED_STATUS,
                },
            )
        except Exception as error:
            error_message = str(error)
            retry_record = state_store.mark_retry(
                state,
                video["video_url"],
                "OneDrive保存",
                error_message,
                run_id,
                wait_seconds=state_store.resolve_retry_wait_seconds(),
                status=state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures_this_run,
                video,
                "onedrive",
                "OneDrive保存",
                error_message,
                nextRetryAt=retry_record.get("nextRetryAt"),
            )
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "OneDrive保存",
                "failed",
                error_message,
                nextRetryAt=retry_record.get("nextRetryAt"),
            )
            continue

        success_count += 1
        state_store.mark_done(state, video["video_url"], run_id, upload_result=upload_result)
        state_store.save_state(state)
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
                COMPLETED_STATUS,
                sheet_name=VIDEO_SHEET_NAME,
            )
            video["status"] = COMPLETED_STATUS
            _append_processing_log(
                processing_logs,
                run_id,
                video,
                "状況更新",
                "success",
                "Google Sheets の状況を完了へ更新しました",
            )
        except Exception as error:
            _append_failure(
                failures_this_run,
                video,
                "sheet_update",
                "状況更新",
                str(error),
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

    return success_count


def main():
    print("=" * 72)
    print("info_viewer パイプライン開始")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    args = parse_args()
    run_mode = _resolve_run_mode(args)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    _require_environment(run_mode)

    target_channels, all_target_videos = sheet_reader.get_target_videos(
        SPREADSHEET_ID,
        channel_sheet_name=CHANNEL_SHEET_NAME,
        video_sheet_name=VIDEO_SHEET_NAME,
        include_completed=True,
    )
    print(f"実行モード: {run_mode}")
    print(f"対象チャンネル数: {len(target_channels)}")
    print(f"対象動画数: {len(all_target_videos)}")

    previous_failures, previous_processing_logs = _load_previous_manifest_state()
    processing_logs: list[dict[str, Any]] = []
    failures_this_run: list[dict[str, Any]] = []
    success_count = 0

    saved_articles_before = onedrive_writer.list_saved_articles()
    existing_article_map = _build_existing_article_map(saved_articles_before)
    state = state_store.load_state()

    if run_mode != "rebuild_manifest_only":
        synced_count = _sync_sheet_status_for_saved_articles(
            all_target_videos,
            existing_article_map,
            processing_logs,
            run_id,
        )
        if synced_count:
            print(f"既存記事に合わせて Sheets 状況を完了へ同期: {synced_count}件")

        sync_stats = _sync_queue_state(
            state,
            all_target_videos,
            existing_article_map,
            args,
            processing_logs,
            run_id,
        )
        print(
            "キュー同期: "
            f"scanned={sync_stats['scanned']} added={sync_stats['added']} "
            f"pending={sync_stats['pending']} done={sync_stats['markedDone']} "
            f"deactivated={sync_stats['deactivated']}"
        )
        state_store.attach_queue_metadata(all_target_videos, state)
        _print_queue_summary(state, "キュー状況")
    else:
        print("manifest 再構築のみ実行します。")

    if run_mode == "rebuild_manifest_only":
        pass
    elif run_mode == "sync_only":
        print("Sheets 差分取得とキュー同期のみ実行しました。")
    else:
        pending_videos = state_store.list_processable_videos(
            state,
            max_items=args.max_items,
            channel_name=args.channel_name,
            video_url=args.video_url,
        )
        if not pending_videos:
            print("今回処理できるキュー対象はありません。")
        else:
            print(f"処理対象件数: {len(pending_videos)}")
            success_count = _process_pending_videos(
                pending_videos,
                state,
                run_id,
                processing_logs,
                failures_this_run,
            )
            state_store.attach_queue_metadata(all_target_videos, state)
            _print_queue_summary(state, "処理後キュー状況")

    saved_articles_after = onedrive_writer.list_saved_articles()
    resolved_keys = {
        article.get("youtubeUrlNormalized")
        for article in saved_articles_after
        if article.get("youtubeUrlNormalized")
    }
    merged_failures = _merge_failures(previous_failures, failures_this_run, resolved_keys)
    merged_processing_logs = _merge_processing_logs(previous_processing_logs, processing_logs)
    state_store.attach_queue_metadata(all_target_videos, state)
    manifest = manifest_builder.build_manifest(
        target_channels=target_channels,
        target_videos=all_target_videos,
        saved_articles=saved_articles_after,
        failures=merged_failures,
        processing_logs=merged_processing_logs,
        run_id=run_id,
        queue_state=state,
    )
    manifest_builder.write_manifest(manifest)

    print("-" * 72)
    print(f"成功: {success_count}件")
    print(f"失敗: {len(failures_this_run)}件")
    print(f"manifest 更新完了: {manifest.get('generatedAt')}")
    print("-" * 72)

    for failure in failures_this_run:
        print(f"失敗: {failure['title']} / {failure['stage']} / {failure['error']}")


if __name__ == "__main__":
    main()
