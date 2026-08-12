"""親記事の結論末尾に追加する公開本文を組み立てる。"""

from __future__ import annotations

from collections.abc import Sequence

from .affiliate_group import AffiliateGroup


DISCLAIMER = "(Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。文章にはAIの整形・編集が含まれます。)"


def _clean_paragraph(value: str, label: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{label}が空です")
    if cleaned.startswith(("{", "[", "---", "```")):
        raise ValueError(f"{label}に管理形式が混入しています")
    return cleaned


def build_conclusion_addition(
    *,
    product_name: str,
    category_name: str,
    spec_summary: str,
    recommendation_reasons: Sequence[str],
    affiliate_group: AffiliateGroup,
) -> str:
    if len(recommendation_reasons) != len(affiliate_group.products):
        raise ValueError(
            "おすすめ理由と商品ブロックの件数が一致しません: "
            f"{len(recommendation_reasons)} != {len(affiliate_group.products)}"
        )

    lines = [
        f"**{product_name}の主要スペック**",
        "",
        _clean_paragraph(spec_summary, "主要スペック要約"),
        "",
        f"**おすすめ{category_name}一覧**",
        "",
        DISCLAIMER,
        "",
    ]

    for product, reason in zip(affiliate_group.products, recommendation_reasons):
        lines.extend(
            [
                f"**{product.title}をおすすめする理由**",
                "",
                _clean_paragraph(reason, f"商品{product.index}のおすすめ理由"),
                "",
                product.text,
                "",
            ]
        )

    lines.extend(["**おすすめ商品のリンクまとめ**", ""])
    for product in affiliate_group.products:
        for url in product.urls:
            lines.append(f"- [{product.title}]({url})")
    return "\n".join(lines).strip()
