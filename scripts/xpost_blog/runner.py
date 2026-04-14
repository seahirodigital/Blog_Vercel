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

from modules import discord_fetcher, gemini_formatter, manifest_builder, onedrive_writer, source_fetcher, state_store


def _parse_nonnegative_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(0, parsed)


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.getenv("XPOST_DISCORD_GUILD_ID", "1485160018767642705").strip()
DISCORD_CHANNEL_ID = os.getenv("XPOST_DISCORD_CHANNEL_ID", "1485179091463307344").strip()
DISCORD_CHANNEL_NAME = os.getenv("XPOST_DISCORD_CHANNEL_NAME", "01_tech").strip() or "01_tech"
SOCIALDATA_API_KEY = os.getenv("SOCIALDATA_API_KEY", "").strip()
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "").strip()
XPOST_BLOG_SOURCE_PROVIDER = os.getenv("XPOST_BLOG_SOURCE_PROVIDER", "socialdata").strip() or "socialdata"
XPOST_BLOG_APIFY_ACTOR = os.getenv("XPOST_BLOG_APIFY_ACTOR", "").strip()
GEMINI_TOKEN_INVEST_SUB = (os.getenv("GEMINI_TOKEN_INVESTsub", "") or os.getenv("GEMINI_TOKEN_INVESTSUB", "")).strip()
GEMINI_TOKEN_TECH = (os.getenv("GEMINI_TOKEN_tech", "") or os.getenv("GEMINI_TOKEN_TECH", "")).strip()
DEFAULT_MAX_ITEMS = _parse_nonnegative_int(os.getenv("XPOST_BLOG_MAX_ITEMS", "0"), 0)
MAX_ITEMS_PER_RUN = _parse_nonnegative_int(os.getenv("XPOST_BLOG_MAX_ITEMS_PER_RUN", "0"), 0)
GEMINI_SERIAL_DELAY_SECONDS = int(os.getenv("XPOST_BLOG_GEMINI_SERIAL_DELAY_SECONDS", "20") or 20)

GEMINI_TOKEN_POOLS = {
    "tech": ("GEMINI_TOKEN_tech", GEMINI_TOKEN_TECH),
    "invest_sub": ("GEMINI_TOKEN_INVESTSUB", GEMINI_TOKEN_INVEST_SUB),
}


def _is_scheduled_run() -> bool:
    return os.getenv("GITHUB_EVENT_NAME", "") == "schedule" or os.getenv("EVENT_NAME", "") == "schedule"


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


def _resolve_max_items(requested: int) -> int:
    normalized = _parse_nonnegative_int(requested, DEFAULT_MAX_ITEMS)
    if normalized <= 0:
        return 0 if MAX_ITEMS_PER_RUN <= 0 else MAX_ITEMS_PER_RUN
    return normalized if MAX_ITEMS_PER_RUN <= 0 else min(normalized, MAX_ITEMS_PER_RUN)


def _max_items_label(max_items: int) -> str:
    return "無制限" if int(max_items or 0) <= 0 else str(max_items)


def _require_environment(run_mode: str):
    if run_mode in {"sync_only", "full"} and not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN が設定されていません")
    source_fetcher.validate_environment(
        run_mode=run_mode,
        preferred_provider=XPOST_BLOG_SOURCE_PROVIDER,
        socialdata_api_key=SOCIALDATA_API_KEY,
        apify_api_key=APIFY_API_KEY,
    )
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


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_bundle_from_saved_source(post: dict[str, Any]) -> dict[str, Any] | None:
    source_relative_path = str(post.get("sourceRelativePath") or "").strip()
    if not source_relative_path:
        return None
    try:
        source_document = onedrive_writer.download_text(source_relative_path)
    except Exception as error:
        print(f"   OneDrive 保存済みソースの再読込に失敗: {error}")
        return None
    if not source_document:
        return None

    metadata, source_body = onedrive_writer.parse_frontmatter(source_document)
    source_title = metadata.get("title") or post.get("sourceTitle") or post.get("title") or "元投稿ソース"
    post_url = metadata.get("post_url") or post.get("postUrl", "")
    normalized_post_url = metadata.get("normalized_post_url") or post.get("normalizedPostUrl") or onedrive_writer.normalize_x_url(post_url)
    return {
        "ok": True,
        "post_url": post_url,
        "normalized_post_url": normalized_post_url,
        "tweet_id": metadata.get("tweet_id") or post.get("tweetId", ""),
        "article_id": metadata.get("article_id") or post.get("articleId", ""),
        "title": source_title,
        "source_title": source_title,
        "author_name": metadata.get("author_name") or post.get("authorName", ""),
        "author_screen_name": metadata.get("author_screen_name") or post.get("authorScreenName", ""),
        "published_at": metadata.get("published_at") or post.get("publishedAt", ""),
        "favorite_count": _as_int(metadata.get("favorite_count") or post.get("favoriteCount")),
        "repost_count": _as_int(metadata.get("repost_count") or post.get("repostCount")),
        "reply_count": _as_int(metadata.get("reply_count") or post.get("replyCount")),
        "quote_count": _as_int(metadata.get("quote_count") or post.get("quoteCount")),
        "bookmark_count": _as_int(metadata.get("bookmark_count") or post.get("bookmarkCount")),
        "view_count": _as_int(metadata.get("view_count") or post.get("viewCount")),
        "is_article": bool(metadata.get("article_id") or post.get("articleId") or "/i/article/" in normalized_post_url),
        "source_markdown": source_body.strip(),
        "source_provider": metadata.get("source_provider") or post.get("sourceProvider") or "onedrive",
        "source_provider_label": "OneDrive保存済みソース",
        "source_provider_detail": source_relative_path,
        "attempted_providers": ["OneDrive保存済みソース"],
        "fallback_used": False,
        "fallback_reason": "saved_source_reuse",
        "reused_saved_source": True,
    }


def _is_token_cooldown_failure(failure_kind: str, message: str) -> bool:
    if failure_kind in {"quota", "transient", "retryable", "empty"}:
        return True
    lowered = str(message or "").lower()
    return any(
        keyword in lowered
        for keyword in (
            "429",
            "500",
            "503",
            "too many requests",
            "resource exhausted",
            "rate limit",
            "service unavailable",
            "internal server error",
            "unavailable",
        )
    )


def _failure_wait_seconds(gemini_result: dict[str, Any], failure_kind: str, token_cooldown: bool) -> int:
    recommended = gemini_result.get("recommendedWaitSeconds", 0)
    if token_cooldown:
        return state_store.resolve_token_cooldown_wait_seconds(recommended)
    return state_store.resolve_retry_wait_seconds(recommended, quota=(failure_kind == "quota"))


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


def _sync_from_discord(state: dict[str, Any], processing_logs: list[dict[str, Any]]) -> dict[str, int]:
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
    return stats


def _process_pending_posts(
    pending_posts: list[dict[str, Any]],
    state: dict[str, Any],
    failures: list[dict[str, Any]],
    processing_logs: list[dict[str, Any]],
    run_id: str,
) -> int:
    success_count = 0

    for index, post in enumerate(pending_posts, start=1):
        title_for_log = post.get("title") or post.get("postUrl") or "X投稿"
        print(f"[{index}/{len(pending_posts)}] {title_for_log}")
        state_store.mark_processing(state, post["postUrl"], run_id)
        state_store.save_state(state)
        _append_processing_log(processing_logs, post, "queue", "queued", "X投稿を処理キューへ投入しました")

        bundle = _build_bundle_from_saved_source(post)
        if bundle:
            state_store.update_post_metadata(state, post["postUrl"], bundle)
            state_store.save_state(state)
            _append_processing_log(
                processing_logs,
                post,
                "OneDrive",
                "source_reused",
                "保存済みの元投稿ソースを再利用し、取得APIを呼ばずにGemini処理へ進みます",
                sourceProvider=bundle.get("source_provider"),
                sourceProviderDetail=bundle.get("source_provider_detail"),
                fallbackReason=bundle.get("fallback_reason"),
            )
        else:
            bundle = source_fetcher.fetch_post_bundle(
                post["postUrl"],
                socialdata_api_key=SOCIALDATA_API_KEY,
                apify_api_key=APIFY_API_KEY,
                preferred_provider=XPOST_BLOG_SOURCE_PROVIDER,
                apify_actor_name=XPOST_BLOG_APIFY_ACTOR,
            )
        source_provider_label = bundle.get("source_provider_label") or "取得"
        source_provider = bundle.get("source_provider") or ""
        source_provider_detail = bundle.get("source_provider_detail") or ""
        attempted_providers = bundle.get("attempted_providers") or []
        fallback_used = bool(bundle.get("fallback_used"))
        fallback_reason = bundle.get("fallback_reason") or ""
        if not bundle.get("ok"):
            error_message = bundle.get("error") or "取得に失敗しました"
            wait_seconds = state_store.resolve_retry_wait_seconds()
            state_store.mark_retry(
                state,
                post["postUrl"],
                source_provider_label,
                error_message,
                run_id,
                wait_seconds=wait_seconds,
                status=state_store.FAILED_STATUS,
            )
            state_store.save_state(state)
            _append_failure(
                failures,
                post,
                source_provider_label,
                error_message,
                httpStatus=bundle.get("httpStatus"),
                sourceProvider=source_provider,
                sourceProviderDetail=source_provider_detail,
                attemptedProviders=attempted_providers,
                fallbackUsed=fallback_used,
                fallbackReason=fallback_reason,
            )
            _append_processing_log(
                processing_logs,
                post,
                source_provider_label,
                "failed",
                error_message,
                httpStatus=bundle.get("httpStatus"),
                sourceProvider=source_provider,
                sourceProviderDetail=source_provider_detail,
                attemptedProviders=attempted_providers,
                fallbackUsed=fallback_used,
                fallbackReason=fallback_reason,
            )
            continue

        source_upload = {
            "id": post.get("sourceFileId", ""),
            "relativePath": post.get("sourceRelativePath", ""),
            "webUrl": post.get("sourceWebUrl", ""),
            "folderName": post.get("folderName", ""),
            "title": bundle.get("source_title") or bundle.get("title") or "元投稿ソース",
        }

        if not bundle.get("reused_saved_source"):
            state_store.update_post_metadata(state, post["postUrl"], bundle)
            state_store.save_state(state)
            _append_processing_log(
                processing_logs,
                post,
                source_provider_label,
                "success",
                f"{source_provider_label} から元投稿ソースを取得しました",
                isArticle=bundle.get("is_article"),
                favoriteCount=bundle.get("favorite_count", 0),
                sourceProvider=source_provider,
                sourceProviderDetail=source_provider_detail,
                attemptedProviders=attempted_providers,
                fallbackUsed=fallback_used,
                fallbackReason=fallback_reason,
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
                    "source_provider": source_provider,
                    "source_provider_detail": source_provider_detail,
                    "attempted_providers": ", ".join(str(item) for item in attempted_providers if item),
                    "fallback_used": str(fallback_used).lower(),
                    "fallback_reason": fallback_reason,
                },
            )
            state_store.update_source_upload(state, post["postUrl"], source_upload)
            state_store.save_state(state)
            _append_processing_log(processing_logs, post, "OneDrive", "source_saved", "元投稿ソースを OneDrive に保存しました")

        gemini_candidates = _build_gemini_candidates()
        selected_candidate: dict[str, str] | None = None
        successful_gemini_result: dict[str, Any] | None = None
        terminal_failure = False
        token_failures: list[dict[str, Any]] = []

        for candidate_index, candidate in enumerate(gemini_candidates, start=1):
            gemini_token_name = candidate["token_name"]
            gemini_api_key = candidate["api_key"]
            resolved_profile = candidate["resolved_profile"]

            token_cooldown = state_store.get_gemini_token_cooldown(state, gemini_token_name)
            if token_cooldown:
                remaining_seconds = int(token_cooldown.get("remainingSeconds") or 0)
                cooldown_message = f"{gemini_token_name} は Gemini 失敗後のクールダウン中です ({remaining_seconds}秒後に再開)"
                token_failures.append(
                    {
                        "message": cooldown_message,
                        "wait_seconds": remaining_seconds,
                        "resolved_profile": resolved_profile,
                        "token_name": gemini_token_name,
                        "failure_kind": token_cooldown.get("failureKind") or "cooldown",
                        "attempt_count": 0,
                    }
                )
                _append_processing_log(
                    processing_logs,
                    post,
                    "Gemini",
                    "skipped",
                    cooldown_message,
                    geminiResolvedProfile=resolved_profile,
                    geminiTokenEnv=gemini_token_name,
                    recommendedWaitSeconds=remaining_seconds,
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
            failure_kind = gemini_result.get("failureKind") or ("quota" if is_quota else "error")
            should_cooldown_token = _is_token_cooldown_failure(failure_kind, error_message)
            wait_seconds = _failure_wait_seconds(gemini_result, failure_kind, should_cooldown_token)

            if should_cooldown_token:
                cooldown_entry = state_store.mark_gemini_token_cooldown(
                    state,
                    gemini_token_name,
                    error_message,
                    wait_seconds=wait_seconds,
                    failure_kind=failure_kind,
                )
                state_store.save_state(state)
                cooldown_wait_seconds = int(cooldown_entry.get("waitSeconds") or wait_seconds)
                carry_message = f"{gemini_token_name} の Gemini 失敗により、この TOKEN は {cooldown_wait_seconds}秒休止し、次の TOKEN を試します"
                token_failures.append(
                    {
                        "message": carry_message,
                        "wait_seconds": cooldown_wait_seconds,
                        "resolved_profile": resolved_profile,
                        "token_name": gemini_token_name,
                        "failure_kind": failure_kind,
                        "attempt_count": gemini_result.get("attemptCount", 0),
                        "raw_error": error_message,
                    }
                )
                _append_processing_log(
                    processing_logs,
                    post,
                    "Gemini",
                    "cooldown",
                    carry_message,
                    model=gemini_result.get("model"),
                    transport=gemini_result.get("transport"),
                    attemptCount=gemini_result.get("attemptCount"),
                    trimmed=gemini_result.get("trimmed"),
                    failureKind=failure_kind,
                    recommendedWaitSeconds=cooldown_wait_seconds,
                    tokenCooldownUntil=cooldown_entry.get("until"),
                    geminiResolvedProfile=resolved_profile,
                    geminiTokenEnv=gemini_token_name,
                    candidateIndex=candidate_index,
                )
                print(f"   {gemini_token_name} を {cooldown_wait_seconds}秒休止し、次の TOKEN を試します。")
                continue

            retry_status = state_store.DEFERRED_STATUS if failure_kind == "transient" else state_store.FAILED_STATUS
            retry_record = state_store.mark_gemini_retry(
                state,
                post["postUrl"],
                error_message,
                run_id,
                wait_seconds=wait_seconds,
                status=retry_status,
                failure_kind=failure_kind,
                gemini_attempt_count=gemini_result.get("attemptCount", 0),
                gemini_token_env=gemini_token_name,
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
                failureKind=failure_kind,
                recommendedWaitSeconds=wait_seconds,
                nextRetryAt=retry_record.get("nextRetryAt"),
                needsReviewReason=retry_record.get("needsReviewReason", ""),
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
                failureKind=failure_kind,
                recommendedWaitSeconds=wait_seconds,
                nextRetryAt=retry_record.get("nextRetryAt"),
                needsReviewReason=retry_record.get("needsReviewReason", ""),
                geminiResolvedProfile=resolved_profile,
                geminiTokenEnv=gemini_token_name,
                candidateIndex=candidate_index,
            )
            terminal_failure = True
            break

        if terminal_failure:
            continue

        if not selected_candidate or not successful_gemini_result:
            waits = [int(item.get("wait_seconds") or 0) for item in token_failures if int(item.get("wait_seconds") or 0) > 0]
            deferred_wait_seconds = min(waits) if waits else state_store.resolve_token_cooldown_wait_seconds()
            last_failure = token_failures[-1] if token_failures else {}
            deferred_message = (
                "利用可能な Gemini TOKEN がありません。TOKEN切れまたは一時障害のため、"
                "この投稿は次回の queue 処理の先頭へ回します"
            )
            retry_record = state_store.mark_gemini_retry(
                state,
                post["postUrl"],
                deferred_message,
                run_id,
                wait_seconds=deferred_wait_seconds,
                status=state_store.DEFERRED_STATUS,
                failure_kind=last_failure.get("failure_kind") or "unavailable",
                gemini_attempt_count=sum(int(item.get("attempt_count") or 0) for item in token_failures),
                gemini_token_env=last_failure.get("token_name", ""),
                retry_priority=True,
            )
            state_store.save_state(state)
            _append_failure(
                failures,
                post,
                "GeminiQuota",
                deferred_message,
                geminiResolvedProfile=last_failure.get("resolved_profile", ""),
                geminiTokenEnv=last_failure.get("token_name", ""),
                recommendedWaitSeconds=deferred_wait_seconds,
                nextRetryAt=retry_record.get("nextRetryAt"),
                needsReviewReason=retry_record.get("needsReviewReason", ""),
                tokenFailures=token_failures,
            )
            _append_processing_log(
                processing_logs,
                post,
                "Gemini",
                "deferred",
                deferred_message,
                geminiResolvedProfile=last_failure.get("resolved_profile", ""),
                geminiTokenEnv=last_failure.get("token_name", ""),
                recommendedWaitSeconds=deferred_wait_seconds,
                nextRetryAt=retry_record.get("nextRetryAt"),
                needsReviewReason=retry_record.get("needsReviewReason", ""),
                tokenFailures=token_failures,
            )
            print("Gemini の利用可能キーが一時不足のため、この投稿は次回 queue 処理に回します")
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
                "source_provider": source_provider,
                "source_provider_detail": source_provider_detail,
                "attempted_providers": ", ".join(str(item) for item in attempted_providers if item),
                "fallback_used": str(fallback_used).lower(),
                "fallback_reason": fallback_reason,
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
    print(f"取得プロバイダ: {source_fetcher.normalize_provider_name(XPOST_BLOG_SOURCE_PROVIDER)}")
    if source_fetcher.normalize_provider_name(XPOST_BLOG_SOURCE_PROVIDER) == "apify" and XPOST_BLOG_APIFY_ACTOR.strip():
        print(f"Apify Actor: {XPOST_BLOG_APIFY_ACTOR.strip()}")

    if args.post_url:
        state_store.upsert_manual_post(state, args.post_url, channel_name=DISCORD_CHANNEL_NAME)
        state_store.prioritize_post(state, args.post_url)
        state_store.save_state(state)
        print(f"手動優先 URL をキューへ登録しました: {args.post_url}")

    discord_stats = {"scanned": 0, "added": 0, "pending": 0}
    if run_mode in {"sync_only", "full"}:
        discord_stats = _sync_from_discord(state, processing_logs)

    success_count = 0
    if run_mode in {"process_queue", "full"}:
        effective_max_items = _resolve_max_items(args.max_items)
        skip_scheduled_queue = (
            run_mode == "full"
            and _is_scheduled_run()
            and not args.post_url
            and int(discord_stats.get("added") or 0) == 0
        )
        if skip_scheduled_queue:
            print("Discord 新規追加 0 件の scheduled run のため、queue 処理自体をスキップします")
            pending_posts = []
        else:
            pending_posts = state_store.list_processable_posts(
                state,
                max_items=effective_max_items,
                post_url=args.post_url,
            )
        if not pending_posts:
            print("処理対象件数: 0")
        else:
            print(f"処理対象件数: {len(pending_posts)} (上限 {_max_items_label(effective_max_items)})")
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
