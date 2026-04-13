from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.append(str(MODULES_DIR))

from modules import discord_fetcher, gemini_formatter, manifest_builder, onedrive_writer, socialdata_fetcher, state_store

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.getenv("XPOST_DISCORD_GUILD_ID", "1485160018767642705").strip()
DISCORD_CHANNEL_ID = os.getenv("XPOST_DISCORD_CHANNEL_ID", "1485179091463307344").strip()
DISCORD_CHANNEL_NAME = os.getenv("XPOST_DISCORD_CHANNEL_NAME", "01_tech").strip() or "01_tech"
SOCIALDATA_API_KEY = os.getenv("SOCIALDATA_API_KEY", "").strip()
GEMINI_TOKEN_INVEST_SUB = (os.getenv("GEMINI_TOKEN_INVESTsub", "") or os.getenv("GEMINI_TOKEN_INVESTSUB", "")).strip()
GEMINI_TOKEN_TECH = (os.getenv("GEMINI_TOKEN_tech", "") or os.getenv("GEMINI_TOKEN_TECH", "")).strip()
DEFAULT_MAX_ITEMS = int(os.getenv("XPOST_BLOG_MAX_ITEMS", "3") or 3)
GEMINI_SERIAL_DELAY_SECONDS = int(os.getenv("XPOST_BLOG_GEMINI_SERIAL_DELAY_SECONDS", "20") or 20)

GEMINI_TOKEN_POOLS = {
    "tech": ("GEMINI_TOKEN_tech", GEMINI_TOKEN_TECH),
    "invest_sub": ("GEMINI_TOKEN_INVESTSUB", GEMINI_TOKEN_INVEST_SUB),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Xpost_blog runner")
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--process-queue", action="store_true")
    parser.add_argument("--rebuild-manifest-only", action="store_true")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--post-url", type=str, default="")
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


def _require_environment(run_mode: str):
    if run_mode in {"sync_only", "full"} and not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN が設定されていません")
    if run_mode in {"process_queue", "full"} and not SOCIALDATA_API_KEY:
        raise ValueError("SOCIALDATA_API_KEY が設定されていません")
    if run_mode in {"process_queue", "full"} and not any(token for _, token in GEMINI_TOKEN_POOLS.values()):
        raise ValueError("GEMINI_TOKEN_tech または GEMINI_TOKEN_INVESTSUB が設定されていません")


def _build_gemini_candidates() -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for pool_name in ("tech", "invest_sub"):
        token_name, token_value = GEMINI_TOKEN_POOLS[pool_name]
        if not token_value:
            continue
        candidates.append(
            {
                "resolved_profile": pool_name,
                "token_name": token_name,
                "api_key": token_value,
            }
        )
    return candidates


def _append_processing_log(logs: list[dict[str, Any]], record: dict[str, Any] | None, stage: str, status: str, message: str, **extra):
    entry = {
        "occurredAt": datetime.now().isoformat(),
        "stage": stage,
        "status": status,
        "message": message,
    }
    if record:
        entry.update(
            {
                "postUrl": record.get("postUrl") or record.get("post_url", ""),
                "title": record.get("title") or record.get("sourceTitle") or "",
                "channelName": record.get("discordChannelName") or record.get("discord_channel_name") or DISCORD_CHANNEL_NAME,
                "discordMessageId": record.get("discordMessageId") or record.get("discord_message_id", ""),
            }
        )
    entry.update({key: value for key, value in extra.items() if value not in (None, "")})
    logs.append(entry)


def _append_failure(failures: list[dict[str, Any]], record: dict[str, Any] | None, stage: str, error: str, **extra):
    entry = {
        "occurredAt": datetime.now().isoformat(),
        "stage": stage,
        "error": error,
    }
    if record:
        entry.update(
            {
                "postUrl": record.get("postUrl") or record.get("post_url", ""),
                "title": record.get("title") or record.get("sourceTitle") or "",
                "channelName": record.get("discordChannelName") or record.get("discord_channel_name") or DISCORD_CHANNEL_NAME,
            }
        )
    entry.update({key: value for key, value in extra.items() if value not in (None, "")})
    failures.append(entry)


def _merge_failures(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for failure in previous + current:
        normalized = onedrive_writer.normalize_x_url(failure.get("postUrl", "")) or failure.get("postUrl", "")
        if not normalized:
            continue
        existing = merged.get(normalized)
        if existing is None or str(existing.get("occurredAt", "")) <= str(failure.get("occurredAt", "")):
            merged[normalized] = failure
    return sorted(merged.values(), key=lambda item: str(item.get("occurredAt", "")), reverse=True)[:200]


def _merge_processing_logs(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = [*previous, *current]
    merged.sort(key=lambda item: str(item.get("occurredAt", "")), reverse=True)
    return merged[:400]


def _load_previous_manifest_state() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = onedrive_writer.download_json("manifest.json") or {}
    if not isinstance(manifest, dict):
        return [], []
    failures = manifest.get("failures", []) if isinstance(manifest.get("failures"), list) else []
    logs = manifest.get("processingLogs", []) if isinstance(manifest.get("processingLogs"), list) else []
    return failures, logs


def _sleep_between_posts(current_index: int, total_count: int):
    if current_index >= total_count or GEMINI_SERIAL_DELAY_SECONDS <= 0:
        return
    print(f"次の整形まで {GEMINI_SERIAL_DELAY_SECONDS}秒待機します")
    time.sleep(GEMINI_SERIAL_DELAY_SECONDS)


def _sync_from_discord(state: dict[str, Any], processing_logs: list[dict[str, Any]]):
    cursor = state_store.get_channel_cursor(state, DISCORD_CHANNEL_ID)
    result = discord_fetcher.fetch_channel_posts(
        bot_token=DISCORD_BOT_TOKEN,
        guild_id=DISCORD_GUILD_ID,
        channel_id=DISCORD_CHANNEL_ID,
        channel_name=DISCORD_CHANNEL_NAME,
        after_message_id=cursor,
    )
    stats = state_store.sync_discovered_posts(state, result.get("posts", []))
    if result.get("lastMessageId"):
        state_store.set_channel_cursor(state, DISCORD_CHANNEL_ID, result["lastMessageId"])
    state_store.save_state(state)
    _append_processing_log(
        processing_logs,
        None,
        "Discord",
        "synced",
        f"Discord から {stats['scanned']} 件走査し、新規 {stats['added']} 件をキューへ追加しました",
        scannedMessages=result.get("scannedMessages", 0),
        newPosts=stats.get("added", 0),
    )
    print(
        f"Discord 同期: scanned={stats['scanned']} added={stats['added']} pending={stats['pending']} cursor={result.get('lastMessageId', '')}"
    )


def _process_pending_posts(
    pending_posts: list[dict[str, Any]],
    state: dict[str, Any],
    failures: list[dict[str, Any]],
    processing_logs: list[dict[str, Any]],
    run_id: str,
) -> int:
    success_count = 0
    exhausted_pools: dict[str, dict[str, Any]] = {}

    for index, post in enumerate(pending_posts, start=1):
        title_for_log = post.get("title") or post.get("postUrl") or "X投稿"
        print(f"[{index}/{len(pending_posts)}] {title_for_log}")
        state_store.mark_processing(state, post["postUrl"], run_id)
        state_store.save_state(state)
        _append_processing_log(processing_logs, post, "queue", "queued", "X投稿を処理キューへ投入しました")

        bundle = socialdata_fetcher.fetch_post_bundle(post["postUrl"], SOCIALDATA_API_KEY)
        if not bundle.get("ok"):
            error_message = bundle.get("error") or "SocialData 取得に失敗しました"
            wait_seconds = state_store.resolve_retry_wait_seconds()
            state_store.mark_retry(
                state,
                post["postUrl"],
                "SocialData",
                error_message,
                run_id,
                wait_seconds=wait_seconds,
                status=state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(failures, post, "SocialData", error_message, httpStatus=bundle.get("httpStatus"))
            _append_processing_log(processing_logs, post, "SocialData", "failed", error_message, httpStatus=bundle.get("httpStatus"))
            continue

        state_store.update_post_metadata(state, post["postUrl"], bundle)
        state_store.save_state(state)
        _append_processing_log(
            processing_logs,
            post,
            "SocialData",
            "success",
            "SocialData から元投稿ソースを取得しました",
            isArticle=bundle.get("is_article"),
            favoriteCount=bundle.get("favorite_count", 0),
        )

        source_upload = onedrive_writer.upload_source_markdown(
            bundle.get("source_title") or bundle.get("title") or "元投稿ソース",
            bundle.get("published_at") or post.get("publishedAt", ""),
            bundle.get("source_markdown", ""),
            {
                "post_url": bundle.get("post_url") or post["postUrl"],
                "normalized_post_url": bundle.get("normalized_post_url") or post["postUrl"],
                "tweet_id": bundle.get("tweet_id", ""),
                "article_id": bundle.get("article_id", ""),
                "author_name": bundle.get("author_name", ""),
                "author_screen_name": bundle.get("author_screen_name", ""),
                "published_at": bundle.get("published_at", ""),
                "favorite_count": bundle.get("favorite_count", 0),
                "repost_count": bundle.get("repost_count", 0),
                "reply_count": bundle.get("reply_count", 0),
                "quote_count": bundle.get("quote_count", 0),
                "bookmark_count": bundle.get("bookmark_count", 0),
                "view_count": bundle.get("view_count", 0),
                "discord_message_id": post.get("discordMessageId", ""),
                "discord_jump_url": post.get("discordJumpUrl", ""),
            },
        )
        state_store.update_source_upload(state, post["postUrl"], source_upload)
        state_store.save_state(state)
        _append_processing_log(processing_logs, post, "OneDrive", "source_saved", "元投稿ソースを OneDrive に保存しました")

        gemini_candidates = _build_gemini_candidates()
        selected_candidate: dict[str, str] | None = None
        successful_gemini_result: dict[str, Any] | None = None
        terminal_failure = False
        quota_failure: dict[str, Any] | None = None

        for candidate_index, candidate in enumerate(gemini_candidates, start=1):
            gemini_token_name = candidate["token_name"]
            gemini_api_key = candidate["api_key"]
            resolved_profile = candidate["resolved_profile"]

            exhausted_pool = exhausted_pools.get(gemini_token_name)
            if exhausted_pool:
                quota_failure = {
                    "message": exhausted_pool["message"],
                    "wait_seconds": exhausted_pool["wait_seconds"],
                    "resolved_profile": resolved_profile,
                    "token_name": gemini_token_name,
                }
                _append_processing_log(
                    processing_logs,
                    post,
                    "Gemini",
                    "skipped",
                    exhausted_pool["message"],
                    geminiResolvedProfile=resolved_profile,
                    geminiTokenEnv=gemini_token_name,
                    candidateIndex=candidate_index,
                )
                continue

            print(f"   Gemini candidate {candidate_index}/{len(gemini_candidates)}: {gemini_token_name}")
            gemini_result = gemini_formatter.format_post(bundle, gemini_api_key, post)
            if gemini_result.get("ok"):
                selected_candidate = candidate
                successful_gemini_result = gemini_result
                break

            error_message = gemini_result.get("error") or "Gemini 整形に失敗しました"
            is_quota = bool(gemini_result.get("stopPipeline"))
            wait_seconds = state_store.resolve_retry_wait_seconds(
                gemini_result.get("recommendedWaitSeconds", 0),
                quota=is_quota,
            )

            if is_quota:
                carry_message = f"{gemini_token_name} の quota 制限に到達したため、次の Gemini キーへ切り替えます"
                if wait_seconds:
                    carry_message = f"{carry_message} ({wait_seconds}秒待機)"
                exhausted_pools[gemini_token_name] = {
                    "message": carry_message,
                    "wait_seconds": wait_seconds,
                }
                quota_failure = {
                    "message": carry_message,
                    "wait_seconds": wait_seconds,
                    "resolved_profile": resolved_profile,
                    "token_name": gemini_token_name,
                    "raw_error": error_message,
                }
                _append_processing_log(
                    processing_logs,
                    post,
                    "Gemini",
                    "quota",
                    error_message,
                    model=gemini_result.get("model"),
                    transport=gemini_result.get("transport"),
                    attemptCount=gemini_result.get("attemptCount"),
                    trimmed=gemini_result.get("trimmed"),
                    recommendedWaitSeconds=gemini_result.get("recommendedWaitSeconds"),
                    geminiResolvedProfile=resolved_profile,
                    geminiTokenEnv=gemini_token_name,
                    candidateIndex=candidate_index,
                )
                print(f"   {gemini_token_name} quota 到達。fallback を続行します。")
                continue

            state_store.mark_retry(
                state,
                post["postUrl"],
                "Gemini",
                error_message,
                run_id,
                wait_seconds=wait_seconds,
                status=state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures,
                post,
                "Gemini",
                error_message,
                model=gemini_result.get("model"),
                transport=gemini_result.get("transport"),
                attemptCount=gemini_result.get("attemptCount"),
                trimmed=gemini_result.get("trimmed"),
                recommendedWaitSeconds=wait_seconds,
                geminiResolvedProfile=resolved_profile,
                geminiTokenEnv=gemini_token_name,
            )
            _append_processing_log(
                processing_logs,
                post,
                "Gemini",
                "failed",
                error_message,
                model=gemini_result.get("model"),
                transport=gemini_result.get("transport"),
                attemptCount=gemini_result.get("attemptCount"),
                trimmed=gemini_result.get("trimmed"),
                recommendedWaitSeconds=wait_seconds,
                geminiResolvedProfile=resolved_profile,
                geminiTokenEnv=gemini_token_name,
                candidateIndex=candidate_index,
            )
            terminal_failure = True
            break

        if terminal_failure:
            continue

        if not selected_candidate or not successful_gemini_result:
            deferred_message = (quota_failure or {}).get("message") or "Gemini の利用可能なキーが一時的に不足しています"
            deferred_wait_seconds = (quota_failure or {}).get("wait_seconds") or state_store.resolve_retry_wait_seconds(quota=True)
            state_store.mark_retry(
                state,
                post["postUrl"],
                "Gemini",
                deferred_message,
                run_id,
                wait_seconds=deferred_wait_seconds,
                status=state_store.DEFERRED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures,
                post,
                "GeminiQuota",
                deferred_message,
                geminiResolvedProfile=(quota_failure or {}).get("resolved_profile", ""),
                geminiTokenEnv=(quota_failure or {}).get("token_name", ""),
                recommendedWaitSeconds=deferred_wait_seconds,
            )
            _append_processing_log(
                processing_logs,
                post,
                "Gemini",
                "deferred",
                deferred_message,
                geminiResolvedProfile=(quota_failure or {}).get("resolved_profile", ""),
                geminiTokenEnv=(quota_failure or {}).get("token_name", ""),
            )
            print("Gemini の利用可能キーが一時不足のため、この投稿は次回 run に回します")
            continue

        gemini_result = successful_gemini_result
        selected_token_name = selected_candidate["token_name"]
        selected_profile = selected_candidate["resolved_profile"]
        _append_processing_log(
            processing_logs,
            post,
            "Gemini",
            "success",
            "Markdown 整形が完了しました",
            model=gemini_result.get("model"),
            transport=gemini_result.get("transport"),
            attemptCount=gemini_result.get("attemptCount"),
            trimmed=gemini_result.get("trimmed"),
            geminiResolvedProfile=selected_profile,
            geminiTokenEnv=selected_token_name,
        )

        article_title = bundle.get("source_title") or bundle.get("title") or post.get("title") or "X投稿まとめ"
        article_upload = onedrive_writer.upload_blog_markdown(
            article_title,
            bundle.get("published_at") or post.get("publishedAt", ""),
            gemini_result.get("markdown", ""),
            {
                "post_url": bundle.get("post_url") or post["postUrl"],
                "normalized_post_url": bundle.get("normalized_post_url") or post["postUrl"],
                "tweet_id": bundle.get("tweet_id", ""),
                "article_id": bundle.get("article_id", ""),
                "author_name": bundle.get("author_name", ""),
                "author_screen_name": bundle.get("author_screen_name", ""),
                "published_at": bundle.get("published_at", ""),
                "favorite_count": bundle.get("favorite_count", 0),
                "repost_count": bundle.get("repost_count", 0),
                "reply_count": bundle.get("reply_count", 0),
                "quote_count": bundle.get("quote_count", 0),
                "bookmark_count": bundle.get("bookmark_count", 0),
                "view_count": bundle.get("view_count", 0),
                "discord_message_id": post.get("discordMessageId", ""),
                "discord_jump_url": post.get("discordJumpUrl", ""),
                "source_file_id": source_upload.get("id", ""),
                "source_relative_path": source_upload.get("relativePath", ""),
                "folder_name": source_upload.get("folderName", ""),
            },
        )
        state_store.mark_done(state, post["postUrl"], run_id, article_upload)
        state_store.save_state(state)
        success_count += 1
        _append_processing_log(processing_logs, post, "OneDrive", "article_saved", "ブログ記事を OneDrive に保存しました")
        _sleep_between_posts(index, len(pending_posts))

    return success_count


def main():
    args = parse_args()
    run_mode = _resolve_run_mode(args)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")

    _require_environment(run_mode)
    previous_failures, previous_logs = _load_previous_manifest_state()
    failures: list[dict[str, Any]] = []
    processing_logs: list[dict[str, Any]] = []
    state = state_store.load_state()

    print(f"実行モード: {run_mode}")
    print(f"対象 Discord チャンネル: {DISCORD_CHANNEL_NAME} ({DISCORD_CHANNEL_ID})")

    if args.post_url:
        state_store.upsert_manual_post(state, args.post_url, channel_name=DISCORD_CHANNEL_NAME)
        state_store.prioritize_post(state, args.post_url)
        state_store.save_state(state)
        print(f"手動優先 URL をキューへ登録しました: {args.post_url}")

    if run_mode in {"sync_only", "full"}:
        _sync_from_discord(state, processing_logs)

    success_count = 0
    if run_mode in {"process_queue", "full"}:
        pending_posts = state_store.list_processable_posts(state, max_items=args.max_items, post_url=args.post_url)
        if not pending_posts:
            print("処理対象件数: 0")
        else:
            print(f"処理対象件数: {len(pending_posts)}")
            success_count = _process_pending_posts(pending_posts, state, failures, processing_logs, run_id)
            print(f"処理成功件数: {success_count}")

    manifest = manifest_builder.build_manifest(
        state,
        failures=_merge_failures(previous_failures, failures),
        processing_logs=_merge_processing_logs(previous_logs, processing_logs),
        run_id=run_id,
    )
    manifest_builder.write_manifest(manifest)
    print(f"manifest 更新完了: {manifest.get('generatedAt')}")


if __name__ == "__main__":
    main()
