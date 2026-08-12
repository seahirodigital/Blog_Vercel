"""親記事の允許範囲だけを変更して子記事を組み立てる。"""

from __future__ import annotations

import hashlib

from .heading_converter import heading_replacements
from .parent_analyzer import ParentArticle, analyze_parent


def immutable_content_sha256(
    parent_markdown: str,
    *,
    category_name: str,
    title_format: str = "",
) -> str:
    """変更許可した見出し文字列を除く親本文全体のSHA-256を返す。"""
    parent = analyze_parent(parent_markdown)
    replacements = heading_replacements(parent, category_name, title_format)
    ranges = sorted(
        (heading.start, heading.end)
        for heading in parent.headings
        if heading.start in replacements
    )
    cursor = 0
    immutable_parts: list[str] = []
    for start, end in ranges:
        immutable_parts.append(parent_markdown[cursor:start])
        cursor = end
    immutable_parts.append(parent_markdown[cursor:])
    immutable = "".join(immutable_parts)
    return hashlib.sha256(immutable.encode("utf-8")).hexdigest()


def assemble_article(
    parent_markdown: str,
    *,
    category_name: str,
    title_format: str = "",
    conclusion_addition: str,
) -> tuple[str, ParentArticle]:
    parent = analyze_parent(parent_markdown)
    replacements = heading_replacements(parent, category_name, title_format)
    edits: list[tuple[int, int, str]] = []

    for heading in parent.headings:
        replacement = replacements.get(heading.start)
        if replacement is None:
            continue
        marker = "#" * heading.level
        edits.append((heading.start, heading.end, f"{marker} {replacement}{heading.newline}"))

    newline = "\r\n" if "\r\n" in parent_markdown else "\n"
    addition = conclusion_addition.replace("\n", newline).strip()
    prefix = "" if parent.conclusion_insert_at == 0 else newline
    suffix = newline * 2
    edits.append(
        (
            parent.conclusion_insert_at,
            parent.conclusion_insert_at,
            f"{prefix}{addition}{suffix}",
        )
    )

    article = parent_markdown
    for start, end, value in sorted(edits, key=lambda item: item[0], reverse=True):
        article = f"{article[:start]}{value}{article[end:]}"
    return article, parent
