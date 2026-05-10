"""
Gemini 呼び出しの共通設定と transport ラッパー。

モデル名や transport の解決をここへ集約し、
本編パイプラインと info_viewer の両方から再利用する。

デフォルト transport は安定した models.generate_content を使用。
interactions.create は環境変数 GEMINI_TRANSPORT で明示指定した場合のみ利用可能。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
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
    default: str = DEFAULT_GENERATE_CONTENT_TRANSPORT,
) -> str:
    normalized = str(value or "").strip()
    if normalized in SUPPORTED_TRANSPORTS:
        return normalized
    return default


def get_text_transport(
    *override_env_names: str,
    default: str = DEFAULT_GENERATE_CONTENT_TRANSPORT,
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
    if temperature is not None:
        config["temperature"] = temperature
    if max_output_tokens is not None:
        config["max_output_tokens"] = max_output_tokens
    return config


def create_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _read_attr_or_key(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _as_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value

    for method_name in ("model_dump", "to_dict", "dict"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            mapped = method()
        except Exception:
            continue
        if isinstance(mapped, Mapping):
            return mapped

    return value


def _iter_items(value: Any):
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (list, tuple)):
        return value
    return []


def _extract_text_from_node(node: Any, depth: int = 0) -> str:
    if node is None or depth > 8:
        return ""

    node = _as_mapping(node)

    if isinstance(node, str):
        return node

    for field_name in ("text", "output_text"):
        value = _read_attr_or_key(node, field_name)
        if isinstance(value, str) and value:
            return value

    for field_name in (
        "outputs",
        "output",
        "candidates",
        "content",
        "contents",
        "parts",
        "message",
        "messages",
        "response",
        "responses",
        "interaction",
        "data",
        "items",
    ):
        value = _read_attr_or_key(node, field_name)
        if value is None:
            continue
        if isinstance(value, str) and value:
            return value
        for item in _iter_items(value) or [value]:
            text = _extract_text_from_node(item, depth + 1)
            if text:
                return text

    return ""


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

    return _extract_text_from_node(response)


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
        text = extract_text_from_response(response)
        if not text:
            print("   [DIAGNOSTICS] interactions.create returned empty text.")
            print(f"   [DIAGNOSTICS] type(response) = {type(response)}")
            try:
                import json
                dump_val = _as_mapping(response)
                print("   [DIAGNOSTICS] response structure:")
                print(json.dumps(dump_val, default=str, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"   [DIAGNOSTICS] could not dump response: {e}")
                print(f"   [DIAGNOSTICS] repr(response) = {repr(response)}")
        return response, text

    contents = input_text
    if prompt:
        contents = f"{prompt}\n\n{input_text}".strip()

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return response, extract_text_from_response(response)
