import os
import re
import sys
import time
from datetime import datetime
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

MODEL_NAME = get_text_model_name("INFO_VIEWER_GEMINI_MODEL")
TRANSPORT_NAME = get_text_transport("INFO_VIEWER_GEMINI_TRANSPORT", default="models.generate_content")
GENERATION_CONFIG = build_generation_config(temperature=0.2)
PROMPT_PATH = Path(__file__).resolve().parents[3] / "info_viewer" / "prompt" / "base_prompt.md"
RETRYABLE_KEYWORDS = ("429", "503", "500", "timeout", "timed out", "rate limit", "unavailable", "resource exhausted")
INPUT_LIMIT_KEYWORDS = ("too large", "too many tokens", "context", "token", "request too large", "input too long", "invalid argument")
QUOTA_EXHAUSTED_KEYWORDS = (
    "quota exceeded",
    "exceeded your current quota",
    "do not have enough quota",
    "resource_exhausted",
    "generate_content_free_tier_requests",
    "too_many_requests",
)
FALLBACK_TRANSCRIPT_CHARS = int(os.getenv("INFO_VIEWER_GEMINI_FALLBACK_TRANSCRIPT_CHARS", "45000") or 45000)
MAX_RETRIES = int(os.getenv("INFO_VIEWER_GEMINI_MAX_RETRIES", "3") or 3)
RETRY_WAIT_SECONDS = int(os.getenv("INFO_VIEWER_GEMINI_RETRY_WAIT_SECONDS", "15") or 15)


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"プロンプトが見つかりません: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_input(transcript: dict[str, Any], video: dict[str, Any]) -> str:
    return _build_input_from_text(transcript.get("captions", ""), transcript, video)


def _build_input_from_text(transcript_text: str, transcript: dict[str, Any], video: dict[str, Any]) -> str:
    return (
        f"【動画タイトル】\n{video.get('video_title') or transcript.get('title') or '未設定'}\n\n"
        f"【チャンネル名】\n{video.get('channel_name', '')}\n\n"
        f"【投稿日】\n{video.get('published_at', '')}\n\n"
        f"【再生時間】\n{video.get('duration', '')}\n\n"
        f"【動画URL】\n{video.get('video_url') or transcript.get('url') or ''}\n\n"
        f"【YouTubeトランスクリプト】\n{transcript_text}"
    )


def _normalize_markdown(text: str, fallback_title: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return ""

    if not cleaned.startswith("# "):
        return f"# {fallback_title}\n\n{cleaned}"
    return cleaned


def _trim_transcript(text: str, max_chars: int) -> str:
    cleaned = str(text or "").strip()
    if not cleaned or max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    head_chars = int(max_chars * 0.7)
    tail_chars = max_chars - head_chars
    head = cleaned[:head_chars].rstrip()
    tail = cleaned[-tail_chars:].lstrip()
    return (
        f"{head}\n\n"
        "【中略: 長い文字起こしのため一部を省略】\n\n"
        f"{tail}"
    ).strip()


def _is_retryable_error(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in RETRYABLE_KEYWORDS)


def _looks_like_input_limit(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in INPUT_LIMIT_KEYWORDS)


def _looks_like_quota_exhausted(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword in lowered for keyword in QUOTA_EXHAUSTED_KEYWORDS)


def _extract_retry_after_seconds(message: str) -> int:
    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", str(message or ""), flags=re.I)
    if not match:
        return 0
    try:
        return max(0, int(float(match.group(1)) + 0.999))
    except ValueError:
        return 0


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


def format_transcript(transcript: dict[str, Any], api_key: str, video: dict[str, Any]) -> dict[str, Any]:
    prompt = _load_prompt()
    client = create_client(api_key)
    raw_transcript = str(transcript.get("captions", "") or "")
    fallback_title = video.get("video_title") or transcript.get("title") or "無題"
    attempts: list[dict[str, Any]] = []

    variants = [
        {
            "label": "full",
            "trimmed": False,
            "transcriptText": raw_transcript,
        }
    ]
    trimmed_transcript = _trim_transcript(raw_transcript, FALLBACK_TRANSCRIPT_CHARS)
    if trimmed_transcript and trimmed_transcript != raw_transcript:
        variants.append(
            {
                "label": "trimmed",
                "trimmed": True,
                "transcriptText": trimmed_transcript,
            }
        )

    transport_name = TRANSPORT_NAME
    last_error = "Gemini 整形に失敗しました"
    recommended_wait_seconds = 0
    stop_pipeline = False

    for variant in variants:
        input_text = _build_input_from_text(variant["transcriptText"], transcript, video)
        input_chars = len(input_text)
        transcript_chars = len(variant["transcriptText"])
        if variant["trimmed"]:
            print(f"   Gemini フォールバック: 文字起こしを {transcript_chars} 文字に抑えて再試行")

        force_next_variant = False
        for attempt_index in range(1, MAX_RETRIES + 1):
            attempt_log = {
                "transport": transport_name,
                "attempt": attempt_index,
                "variant": variant["label"],
                "trimmed": variant["trimmed"],
                "inputChars": input_chars,
                "transcriptChars": transcript_chars,
                "occurredAt": datetime.now().isoformat(),
            }
            try:
                _, generated = run_text_generation(
                    client,
                    model=MODEL_NAME,
                    transport=transport_name,
                    prompt=prompt,
                    input_text=input_text,
                    generation_config=GENERATION_CONFIG,
                )
                normalized = _normalize_markdown(generated, fallback_title)
                if normalized:
                    attempt_log["status"] = "success"
                    attempt_log["responseChars"] = len(generated or "")
                    attempts.append(attempt_log)
                    return {
                        "ok": True,
                        "stage": "Gemini",
                        "markdown": normalized,
                        "model": MODEL_NAME,
                        "transport": transport_name,
                        "attemptCount": len(attempts),
                        "promptChars": len(prompt),
                        "inputChars": input_chars,
                        "transcriptChars": len(raw_transcript),
                        "usedTranscriptChars": transcript_chars,
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

                if not variant["trimmed"] and _looks_like_input_limit(last_error) and len(variants) > 1:
                    force_next_variant = True
                    break

                if _looks_like_quota_exhausted(last_error):
                    stop_pipeline = True
                    recommended_wait_seconds = max(recommended_wait_seconds, _extract_retry_after_seconds(last_error))
                    break

                if attempt_index < MAX_RETRIES and _is_retryable_error(last_error):
                    wait_seconds = RETRY_WAIT_SECONDS * attempt_index
                    print(f"   Gemini 再試行待機: {wait_seconds}秒 ({transport_name} {attempt_index}/{MAX_RETRIES})")
                    time.sleep(wait_seconds)
                    continue
                break

        if force_next_variant or stop_pipeline:
            break

    return {
        "ok": False,
        "stage": "Gemini",
        "error": last_error,
        "model": MODEL_NAME,
        "transport": transport_name,
        "attemptCount": len(attempts),
        "promptChars": len(prompt),
        "inputChars": attempts[-1]["inputChars"] if attempts else 0,
        "transcriptChars": len(raw_transcript),
        "usedTranscriptChars": attempts[-1]["transcriptChars"] if attempts else 0,
        "trimmed": bool(attempts[-1]["trimmed"]) if attempts else False,
        "stopPipeline": stop_pipeline,
        "quotaExhausted": stop_pipeline,
        "retryableError": _is_retryable_error(last_error),
        "recommendedWaitSeconds": recommended_wait_seconds,
        "attempts": attempts[-6:],
    }
