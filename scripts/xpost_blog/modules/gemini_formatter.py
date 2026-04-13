import os
import re
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

from gemini_runtime import (  # noqa: E402
    build_generation_config,
    create_client,
    get_text_model_name,
    get_text_transport,
    run_text_generation,
)

MODEL_NAME = get_text_model_name("XPOST_BLOG_GEMINI_MODEL")
TRANSPORT_NAME = get_text_transport("XPOST_BLOG_GEMINI_TRANSPORT", default="models.generate_content")
GENERATION_CONFIG = build_generation_config(temperature=0.5)
PROMPT_PATH = Path(__file__).resolve().parents[3] / "Xpost_Blog" / "Discord_connect" / "Xpost_blog_prompt" / "prompt.md"
RETRYABLE_KEYWORDS = (
    "429",
    "500",
    "503",
    "timeout",
    "timed out",
    "rate limit",
    "unavailable",
    "resource exhausted",
)
QUOTA_KEYWORDS = (
    "quota exceeded",
    "resource_exhausted",
    "too_many_requests",
    "rate limit",
    "429",
)
INPUT_LIMIT_KEYWORDS = (
    "too many tokens",
    "request too large",
    "input too long",
    "context",
    "invalid argument",
)
FALLBACK_SOURCE_CHARS = int(os.getenv("XPOST_BLOG_GEMINI_FALLBACK_SOURCE_CHARS", "32000") or 32000)
MAX_RETRIES = int(os.getenv("XPOST_BLOG_GEMINI_MAX_RETRIES", "3") or 3)
RETRY_WAIT_SECONDS = int(os.getenv("XPOST_BLOG_GEMINI_RETRY_WAIT_SECONDS", "15") or 15)


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"プロンプトが見つかりません: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_input(bundle: dict[str, Any], queue_item: dict[str, Any], source_text: str) -> str:
    return (
        f"【X URL】\n{bundle.get('post_url') or queue_item.get('postUrl', '')}\n\n"
        f"【仮タイトル】\n{bundle.get('title') or queue_item.get('title', '')}\n\n"
        f"【投稿者名】\n{bundle.get('author_name') or queue_item.get('authorName', '')}\n\n"
        f"【投稿者アカウント】\n{bundle.get('author_screen_name') or queue_item.get('authorScreenName', '')}\n\n"
        f"【投稿日時】\n{bundle.get('published_at') or queue_item.get('publishedAt', '')}\n\n"
        f"【いいね数】\n{bundle.get('favorite_count', 0)}\n\n"
        f"【リポスト数】\n{bundle.get('repost_count', 0)}\n\n"
        f"【返信数】\n{bundle.get('reply_count', 0)}\n\n"
        f"【ブックマーク数】\n{bundle.get('bookmark_count', 0)}\n\n"
        f"【閲覧数】\n{bundle.get('view_count', 0)}\n\n"
        f"【Article 判定】\n{'あり' if bundle.get('is_article') else 'なし'}\n\n"
        f"【元投稿ソース】\n{source_text}"
    )


def _normalize_markdown(text: str, fallback_title: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    if not cleaned.startswith("# "):
        return f"# {fallback_title}\n\n{cleaned}"
    return cleaned


def _trim_source_text(text: str, max_chars: int) -> str:
    cleaned = str(text or "").strip()
    if not cleaned or max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    head_chars = int(max_chars * 0.72)
    tail_chars = max_chars - head_chars
    return (
        f"{cleaned[:head_chars].rstrip()}\n\n"
        "【中略: 元投稿ソースが長いため一部を省略】\n\n"
        f"{cleaned[-tail_chars:].lstrip()}"
    ).strip()


def _format_exception(error: Exception) -> str:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    body = ""
    if response is not None:
        try:
            body = (response.text or "").strip()[:400]
        except Exception:
            body = ""
    detail = str(error).strip() or error.__class__.__name__
    if status_code and f"{status_code}" not in detail:
        detail = f"HTTP {status_code}: {detail}"
    if body and body not in detail:
        detail = f"{detail} | {body}"
    return detail


def _is_retryable(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in RETRYABLE_KEYWORDS)


def _is_quota(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in QUOTA_KEYWORDS)


def _is_input_limit(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in INPUT_LIMIT_KEYWORDS)


def _extract_retry_after_seconds(message: str) -> int:
    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", str(message or ""), flags=re.I)
    if not match:
        return 0
    try:
        return max(0, int(float(match.group(1)) + 0.999))
    except ValueError:
        return 0


def format_post(bundle: dict[str, Any], api_key: str, queue_item: dict[str, Any]) -> dict[str, Any]:
    prompt = _load_prompt()
    client = create_client(api_key)
    source_text = str(bundle.get("source_markdown", "") or "")
    fallback_title = bundle.get("title") or queue_item.get("title") or "X投稿まとめ"
    attempts: list[dict[str, Any]] = []

    variants = [{"label": "full", "trimmed": False, "source": source_text}]
    trimmed = _trim_source_text(source_text, FALLBACK_SOURCE_CHARS)
    if trimmed and trimmed != source_text:
        variants.append({"label": "trimmed", "trimmed": True, "source": trimmed})

    last_error = "Gemini 整形に失敗しました"
    recommended_wait_seconds = 0
    stop_pipeline = False

    for variant in variants:
        input_text = _build_input(bundle, queue_item, variant["source"])
        if variant["trimmed"]:
            print(f"   Gemini フォールバック: 元投稿ソースを {len(variant['source'])} 文字に抑えて再試行")

        force_next_variant = False
        for attempt_index in range(1, MAX_RETRIES + 1):
            attempt_log = {
                "transport": TRANSPORT_NAME,
                "attempt": attempt_index,
                "variant": variant["label"],
                "trimmed": variant["trimmed"],
                "inputChars": len(input_text),
                "sourceChars": len(variant["source"]),
            }
            try:
                _, generated = run_text_generation(
                    client,
                    model=MODEL_NAME,
                    transport=TRANSPORT_NAME,
                    prompt=prompt,
                    input_text=input_text,
                    generation_config=GENERATION_CONFIG,
                )
                normalized = _normalize_markdown(generated, fallback_title)
                if normalized:
                    attempt_log["status"] = "success"
                    attempts.append(attempt_log)
                    return {
                        "ok": True,
                        "markdown": normalized,
                        "model": MODEL_NAME,
                        "transport": TRANSPORT_NAME,
                        "attemptCount": len(attempts),
                        "usedSourceChars": len(variant["source"]),
                        "trimmed": variant["trimmed"],
                        "attempts": attempts[-6:],
                    }
                last_error = "Gemini の応答が空でした"
                attempt_log["status"] = "empty"
                attempt_log["error"] = last_error
                attempts.append(attempt_log)
                break
            except Exception as error:
                last_error = _format_exception(error)
                attempt_log["status"] = "failed"
                attempt_log["error"] = last_error
                attempts.append(attempt_log)
                print(f"   Gemini 整形エラー: {last_error}")

                if not variant["trimmed"] and _is_input_limit(last_error) and len(variants) > 1:
                    force_next_variant = True
                    break
                if _is_quota(last_error):
                    stop_pipeline = True
                    recommended_wait_seconds = max(recommended_wait_seconds, _extract_retry_after_seconds(last_error))
                    break
                if attempt_index < MAX_RETRIES and _is_retryable(last_error):
                    wait_seconds = RETRY_WAIT_SECONDS * attempt_index
                    print(f"   Gemini 再試行待機: {wait_seconds}秒")
                    time.sleep(wait_seconds)
                    continue
                break

        if force_next_variant or stop_pipeline:
            break

    return {
        "ok": False,
        "error": last_error,
        "model": MODEL_NAME,
        "transport": TRANSPORT_NAME,
        "attemptCount": len(attempts),
        "trimmed": bool(attempts[-1]["trimmed"]) if attempts else False,
        "recommendedWaitSeconds": recommended_wait_seconds,
        "stopPipeline": stop_pipeline,
        "attempts": attempts[-6:],
    }
