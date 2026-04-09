import os
import re
from pathlib import Path
from typing import Any, Optional

from google import genai

MODEL_NAME = os.getenv("INFO_VIEWER_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
PROMPT_PATH = Path(__file__).resolve().parents[3] / "info_viewer" / "prompt" / "base_prompt.md"


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"プロンプトが見つかりません: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_input(transcript: dict[str, Any], video: dict[str, Any]) -> str:
    return (
        f"【動画タイトル】\n{video.get('video_title') or transcript.get('title') or '未設定'}\n\n"
        f"【チャンネル名】\n{video.get('channel_name', '')}\n\n"
        f"【投稿日】\n{video.get('published_at', '')}\n\n"
        f"【再生時間】\n{video.get('duration', '')}\n\n"
        f"【動画URL】\n{video.get('video_url') or transcript.get('url') or ''}\n\n"
        f"【YouTubeトランスクリプト】\n{transcript.get('captions', '')}"
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


def _generate_with_models(client: genai.Client, prompt: str, input_text: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{prompt}\n\n{input_text}",
    )
    return _extract_text_from_response(response)


def _generate_with_interactions(client: genai.Client, prompt: str, input_text: str) -> str:
    interaction = client.interactions.create(
        model=MODEL_NAME,
        input=f"{prompt}\n\n{input_text}",
    )
    return _extract_text_from_response(interaction)


def format_transcript(transcript: dict[str, Any], api_key: str, video: dict[str, Any]) -> Optional[str]:
    prompt = _load_prompt()
    client = genai.Client(api_key=api_key)
    input_text = _build_input(transcript, video)
    fallback_title = video.get("video_title") or transcript.get("title") or "無題"

    try:
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            generated = _generate_with_models(client, prompt, input_text)
        else:
            generated = _generate_with_interactions(client, prompt, input_text)
    except Exception as error:
        print(f"   Gemini 整形エラー: {error}")
        return None

    normalized = _normalize_markdown(generated, fallback_title)
    return normalized or None
