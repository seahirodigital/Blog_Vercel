"""親記事のSEO見出し文字列だけを周辺機器向けに変換する。"""

from __future__ import annotations

import re

from .parent_analyzer import ParentArticle


def _suffix(title: str) -> str:
    parts = re.split(r"([:：│|])", title, maxsplit=1)
    if len(parts) >= 3:
        return parts[2].strip()
    return title.strip()


def build_title(
    product_name: str,
    category_name: str,
    original_title: str,
    title_format: str = "",
) -> str:
    suffix = _suffix(original_title)
    prefix = str(title_format or "").strip()
    prefix = prefix.replace("{製品名}", product_name)
    prefix = re.sub(r"^製品名", product_name, prefix)
    prefix = prefix or f"{product_name} {category_name}おすすめ："
    if not suffix:
        return prefix.rstrip(":：│| ")
    return f"{prefix}{suffix}" if re.search(r"[:：│|]\s*$", prefix) else f"{prefix}：{suffix}"


def heading_replacements(
    parent: ParentArticle,
    category_name: str,
    title_format: str = "",
) -> dict[int, str]:
    replacements = {
        parent.h1.start: build_title(
            parent.product_name,
            category_name,
            parent.h1.title,
            title_format,
        )
    }
    for heading in parent.h2_headings:
        # 既存エディタ規則と同じく、結論より後ろのSEO形式H2だけを変換する。
        if heading.start >= parent.conclusion_insert_at and heading.title.startswith(parent.product_name):
            replacements[heading.start] = build_title(
                parent.product_name,
                category_name,
                heading.title,
                title_format,
            )
    return replacements
