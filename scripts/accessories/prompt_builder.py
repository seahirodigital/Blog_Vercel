"""LLMに限定JSONだけを返させる入力と応答検査。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .affiliate_group import AffiliateGroup


def build_prompt_input(
    *,
    template_path: str | Path | None = None,
    template_content: str = "",
    product_name: str,
    category_name: str,
    evidence: str,
    affiliate_group: AffiliateGroup,
) -> tuple[str, str]:
    prompt = str(template_content or "").strip()
    if not prompt and template_path is not None:
        prompt = Path(template_path).read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError("生成プロンプトが空です")
    blocks = "\n\n".join(
        f"【商品{product.index}】\n{product.text}" for product in affiliate_group.products
    )
    input_text = (
        f"親製品名: {product_name}\n"
        f"対象周辺機器: {category_name}\n\n"
        f"{evidence}\n\n"
        f"【おすすめ商品ブロック】\n{blocks}"
    )
    return prompt, input_text


def parse_engine_result(text: str, product_count: int) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[-1].strip() == "```":
            raw = "\n".join(lines[1:-1]).strip()
            if raw.startswith("json"):
                raw = raw[4:].lstrip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("LLM応答が指定JSONではありません") from error
    if set(data) != {"spec_summary", "recommendations"}:
        raise ValueError("LLM応答のキーが指定と一致しません")
    summary = str(data.get("spec_summary", "")).strip()
    recommendations = data.get("recommendations")
    if not summary or not isinstance(recommendations, list) or len(recommendations) != product_count:
        raise ValueError("LLM応答の要約またはおすすめ理由件数が不正です")
    ordered: list[str] = []
    for expected_index, item in enumerate(recommendations, start=1):
        if not isinstance(item, dict) or item.get("index") != expected_index:
            raise ValueError(f"商品{expected_index}の参照番号が不正です")
        reason = str(item.get("reason", "")).strip()
        if not reason:
            raise ValueError(f"商品{expected_index}のおすすめ理由が空です")
        if any(
            token in reason
            for token in (
                "http://",
                "https://",
                "<think>",
                "job_id",
                "Amazonのアソシエイトとして",
                "AIの整形・編集",
            )
        ):
            raise ValueError(f"商品{expected_index}のおすすめ理由に禁止値があります")
        ordered.append(reason)
    return {"spec_summary": summary, "recommendation_reasons": ordered}
