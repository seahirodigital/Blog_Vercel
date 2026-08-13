"""MLXへ本文全体を渡さないタイトル派生プロンプト。"""

from __future__ import annotations

import json


def build_prompt_input(
    *,
    template_content: str,
    source_title: str,
    target_title: str,
    keyword: str,
    intro_text: str,
    conclusion_text: str,
) -> tuple[str, str]:
    system_prompt = str(template_content or "").strip()
    payload = {
        "source_title": source_title,
        "target_title": target_title,
        "target_keyword": keyword,
        "source_intro_text": intro_text,
        "source_conclusion_text": conclusion_text,
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_json(raw: str) -> dict:
    text = str(raw or "").strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("MLX応答から指定JSONを読み取れません")


def _validate_text(value: object, *, label: str, allow_empty: bool = False) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text and allow_empty:
        return ""
    if not text:
        raise ValueError(f"{label}が空です")
    if len(text) > 3000:
        raise ValueError(f"{label}が長すぎます")
    if text.lstrip().startswith(("#", "---", "```")):
        raise ValueError(f"{label}へ見出し・メタ情報・コードフェンスを出力できません")
    if "<br" in text.lower():
        raise ValueError(f"{label}へHTML改行を出力できません")
    if "http://" in text or "https://" in text or "▼" in text:
        raise ValueError(f"{label}へURLまたは商品ブロックを出力できません")
    return text


def parse_engine_result(raw: str, *, keyword: str, conclusion_required: bool) -> dict[str, str]:
    value = _extract_json(raw)
    allowed = {"intro_text", "conclusion_text"}
    if set(value) != allowed:
        raise ValueError("MLX応答JSONのキーが指定と一致しません")
    return {
        "intro_text": _validate_text(value.get("intro_text"), label="冒頭文"),
        "conclusion_text": _validate_text(
            value.get("conclusion_text"),
            label="結論文",
            allow_empty=not conclusion_required,
        ),
    }
