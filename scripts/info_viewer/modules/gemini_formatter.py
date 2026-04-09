import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from google import genai

MODEL_NAME = os.getenv("INFO_VIEWER_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
PROMPT_PATH = Path(__file__).resolve().parents[3] / "info_viewer" / "prompt" / "base_prompt.md"
RETRYABLE_KEYWORDS = ("429", "503", "500", "timeout", "timed out", "rate limit", "unavailable", "resource exhausted")
INPUT_LIMIT_KEYWORDS = ("too large", "too many tokens", "context", "token", "request too large", "input too long", "invalid argument")
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


def _extract_text_from_response(response: Any) -> str:
    text = getattr(response, "text", "") or ""
    if text:
        return text

    outputs = getattr(response, "outputs", None) or []
    for output in outputs:
        output_text = getattr(output, "text", "") or ""
        if output_text:
            return output_text

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", "") or ""
            if part_text:
                return part_text

    return ""


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


def _generate_with_models(client: genai.Client, prompt: str, input_text: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{prompt}\n\n{input_text}",
        config={"temperature": 0.2},
    )
    return _extract_text_from_response(response)


def _generate_with_interactions(client: genai.Client, prompt: str, input_text: str) -> str:
    interaction = client.interactions.create(
        model=MODEL_NAME,
        system_instruction=prompt,
        input=input_text,
        generation_config={"temperature": 0.2},
    )
    return _extract_text_from_response(interaction)


def _run_transport(
    client: genai.Client,
    transport_name: str,
    prompt: str,
    input_text: str,
) -> str:
    if transport_name == "models.generate_content":
        return _generate_with_models(client, prompt, input_text)
    if transport_name == "interactions.create":
        return _generate_with_interactions(client, prompt, input_text)
    raise ValueError(f"未知の Gemini transport です: {transport_name}")


def format_transcript(transcript: dict[str, Any], api_key: str, video: dict[str, Any]) -> dict[str, Any]:
    prompt = _load_prompt()
    client = genai.Client(api_key=api_key)
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

    transports = ["models.generate_content", "interactions.create"]
    last_error = "Gemini 整形に失敗しました"
    last_transport = ""

    for variant in variants:
        input_text = _build_input_from_text(variant["transcriptText"], transcript, video)
        input_chars = len(input_text)
        transcript_chars = len(variant["transcriptText"])
        if variant["trimmed"]:
            print(f"   Gemini フォールバック: 文字起こしを {transcript_chars} 文字に抑えて再試行")

        force_next_variant = False
        for transport_name in transports:
            last_transport = transport_name
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
                    generated = _run_transport(client, transport_name, prompt, input_text)
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

                    if attempt_index < MAX_RETRIES and _is_retryable_error(last_error):
                        wait_seconds = RETRY_WAIT_SECONDS * attempt_index
                        print(f"   Gemini 再試行待機: {wait_seconds}秒 ({transport_name} {attempt_index}/{MAX_RETRIES})")
                        time.sleep(wait_seconds)
                        continue
                    break

            if force_next_variant:
                break

    return {
        "ok": False,
        "stage": "Gemini",
        "error": last_error,
        "model": MODEL_NAME,
        "transport": last_transport,
        "attemptCount": len(attempts),
        "promptChars": len(prompt),
        "inputChars": attempts[-1]["inputChars"] if attempts else 0,
        "transcriptChars": len(raw_transcript),
        "usedTranscriptChars": attempts[-1]["transcriptChars"] if attempts else 0,
        "trimmed": bool(attempts[-1]["trimmed"]) if attempts else False,
        "attempts": attempts[-6:],
    }
