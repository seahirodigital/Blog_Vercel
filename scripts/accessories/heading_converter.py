"""親記事のSEO見出し文字列だけを周辺機器向けに変換する。"""

from __future__ import annotations

import re

from .parent_analyzer import ParentArticle


def _configured_prefix(product_name: str, category_name: str, title_format: str) -> str:
    prefix = str(title_format or "").strip()
    prefix = prefix.replace("{製品名}", product_name)
    prefix = re.sub(r"^製品名", product_name, prefix)
    prefix = prefix or f"{product_name} {category_name}おすすめ"
    return prefix.rstrip(":：│| ")


def _heading_topic(title: str, product_name: str) -> str:
    topic = str(title or "").strip()
    if topic.startswith(product_name):
        topic = topic[len(product_name) :].lstrip()
        topic = re.sub(r"^(?:(?:レビュー|比較|違い|まとめ)(?:ます)?[。．.!！?？]?\s*)+", "", topic)
        topic = topic.lstrip(":：│| ")
    return topic or str(title or "").strip()


def build_title(
    product_name: str,
    category_name: str,
    original_title: str,
    title_format: str = "",
) -> str:
    prefix = _configured_prefix(product_name, category_name, title_format)
    topic = _heading_topic(original_title, product_name)
    return f"{prefix}: {topic}" if topic else prefix


def build_h1_title(product_name: str, category_name: str, title_format: str = "") -> str:
    return f"{_configured_prefix(product_name, category_name, title_format)}まとめ"


def heading_replacements(
    parent: ParentArticle,
    category_name: str,
    title_format: str = "",
) -> dict[int, str]:
    replacements = {
        parent.h1.start: build_h1_title(
            parent.product_name,
            category_name,
            title_format,
        )
    }
    for heading in parent.h2_headings:
        replacements[heading.start] = build_title(
            parent.product_name,
            category_name,
            heading.title,
            title_format,
        )
    return replacements
