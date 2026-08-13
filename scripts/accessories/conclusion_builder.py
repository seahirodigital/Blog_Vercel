"""親記事の最初の商品ブロック直後へ置く周辺機器結論本文を組み立てる。"""

from __future__ import annotations

from collections.abc import Sequence


def build_conclusion_addition(
    *,
    adapted_section_intro: str = "",
    adapted_product_texts: Sequence[str],
) -> str:
    blocks = [str(value or "").strip() for value in adapted_product_texts]
    if not blocks or any(not block for block in blocks):
        raise ValueError("調整済み商品ブロックが空です")
    intro = str(adapted_section_intro or "").strip()
    return "\n\n".join(([intro] if intro else []) + blocks)
