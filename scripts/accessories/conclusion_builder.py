"""親記事の結論末尾に追加する公開本文を組み立てる。"""

from __future__ import annotations

from collections.abc import Sequence


def build_conclusion_addition(
    *,
    adapted_product_texts: Sequence[str],
) -> str:
    blocks = [str(value or "").strip() for value in adapted_product_texts]
    if not blocks or any(not block for block in blocks):
        raise ValueError("調整済み商品ブロックが空です")
    return "\n\n".join(blocks)
