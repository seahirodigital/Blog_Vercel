"""
Gemini 呼び出しの共通設定と transport ラッパー。

モデル名や transport の解決をここへ集約し、
本編パイプラインと info_viewer の両方から再利用する。
"""

from __future__ import annotations

import os
from typing import Any

from google import genai

DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
DEFAULT_INTERACTIONS_TRANSPORT = "interactions.create"
DEFAULT_GENERATE_CONTENT_TRANSPORT = "models.generate_content"
SUPPORTED_TRANSPORTS = (
    DEFAULT_INTERACTIONS_TRANSPORT,
    DEFAULT_GENERATE_CONTENT_TRANSPORT,
)


def get_text_model_name(*override_env_names: str, default: str = DEFAULT_TEXT_MODEL) -> str:
    for env_name in override_env_names:
        value = os.getenv(env_name, "").strip()
        if value:
            return value

    shared_value = os.getenv("GEMINI_MODEL", "").strip()
    return shared_value or default


def normalize_transport_name(
    value: str | None,
    *,
    default: str = DEFAULT_INTERACTIONS_TRANSPORT,
) -> str:
    normalized = str(value or "").strip()
    if normalized in SUPPORTED_TRANSPORTS:
        return normalized
    return default


def get_text_transport(
    *override_env_names: str,
    default: str = DEFAULT_INTERACTIONS_TRANSPORT,
) -> str:
    for env_name in override_env_names:
        value = os.getenv(env_name, "").strip()
        if value:
            return normalize_transport_name(value, default=default)

    shared_value = os.getenv("GEMINI_TRANSPORT", "").strip()
    if shared_value:
        return normalize_transport_name(shared_value, default=default)

    return default


def build_generation_config(
    *,
    temperature: float | None = None,
    thinking_level: str | None = None,
    thinking_summaries: str | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    thinking_config: dict[str, Any] = {}
    if temperature is not None:
        config["temperature"] = temperature
    if thinking_level:
        thinking_config["thinking_level"] = thinking_level
    if thinking_summaries:
        normalized = str(thinking_summaries).strip().lower()
        if normalized in {"true", "1", "yes", "on", "enabled"}:
            thinking_config["include_thoughts"] = True
        elif normalized in {"false", "0", "no", "off", "disabled"}:
            thinking_config["include_thoughts"] = False
    if thinking_config:
        config["thinking_config"] = thinking_config
    if max_output_tokens is not None:
        config["max_output_tokens"] = max_output_tokens
    return config


def create_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def extract_text_from_response(response: Any) -> str:
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


def run_text_generation(
    client: genai.Client,
    *,
    model: str,
    transport: str,
    prompt: str,
    input_text: str,
    generation_config: dict[str, Any] | None = None,
    previous_interaction_id: str | None = None,
) -> tuple[Any, str]:
    transport_name = normalize_transport_name(transport)
    config = generation_config or {}

    if transport_name == DEFAULT_INTERACTIONS_TRANSPORT:
        request: dict[str, Any] = {
            "model": model,
            "input": input_text,
            "generation_config": config,
        }
        if prompt:
            request["system_instruction"] = prompt
        if previous_interaction_id:
            request["previous_interaction_id"] = previous_interaction_id
        response = client.interactions.create(**request)
        return response, extract_text_from_response(response)

    contents = input_text
    if prompt:
        contents = f"{prompt}\n\n{input_text}".strip()

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return response, extract_text_from_response(response)
