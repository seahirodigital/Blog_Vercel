"""Geminiだけで仕様要約と商品別理由を生成する。"""

from __future__ import annotations

import os
from pathlib import Path

from scripts.gemini_runtime import (
    build_generation_config,
    create_client,
    get_text_model_name,
    run_text_generation,
)

from ..affiliate_group import AffiliateGroup
from ..prompt_builder import build_prompt_input, parse_engine_result


def generate(
    *,
    product_name: str,
    category_name: str,
    evidence: str,
    affiliate_group: AffiliateGroup,
    template_path: str | Path | None = None,
    prompt_content: str = "",
    api_key: str | None = None,
) -> dict:
    key = str(api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise ValueError("GEMINI_API_KEYが設定されていません")
    prompt, input_text = build_prompt_input(
        template_path=template_path,
        template_content=prompt_content,
        product_name=product_name,
        category_name=category_name,
        evidence=evidence,
        affiliate_group=affiliate_group,
    )
    client = create_client(key)
    _, output = run_text_generation(
        client,
        model=get_text_model_name("ACCESSORIES_GEMINI_MODEL"),
        transport="models.generate_content",
        prompt=prompt,
        input_text=input_text,
        generation_config=build_generation_config(temperature=0.2, max_output_tokens=4096),
    )
    return parse_engine_result(output, len(affiliate_group.products))
