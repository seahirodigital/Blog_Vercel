"""完成Markdownへ管理値やLLM内部出力が混入していないか検査する。"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .affiliate_group import AffiliateGroup


FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("YAML Frontmatter", re.compile(r"\A\ufeff?\s*---(?:\r?\n)")),
    ("JSON包み", re.compile(r"\A\ufeff?\s*[\[{]")),
    ("記事全体のコードフェンス", re.compile(r"\A\ufeff?\s*```")),
    ("内部思考", re.compile(r"<\/?think>|\u3010\s*\u601d\u8003\u30d7\u30edセス\s*\u3011", re.I)),
    ("作業説明", re.compile(r"(?:以下のように修正|作業手順|出力フォーマット)")),
    ("管理キー", re.compile(r"(?:job_id|batch_id|parent_id|prompt_revision|engine_name|seo_metadata)\s*[:=]", re.I)),
    ("HTML管理コメント", re.compile(r"<!--[^>]*(?:job|parent|prompt|engine|metadata)[^>]*-->", re.I)),
)


def validate_public_markdown(
    article: str,
    *,
    affiliate_group: AffiliateGroup | None = None,
    adapted_section_intro: str = "",
    adapted_product_texts: Sequence[str] | None = None,
    allowed_new_urls: Sequence[str] | None = None,
) -> None:
    if article.startswith("\ufeff"):
        raise ValueError("UTF-8 BOMが混入しています")
    first_nonblank = next((line.strip() for line in article.splitlines() if line.strip()), "")
    if not first_nonblank.startswith("# ") or first_nonblank.startswith("## "):
        raise ValueError("最初の空白でない行がH1ではありません")
    if len(re.findall(r"(?m)^# [^#]", article)) != 1:
        raise ValueError("H1は1件だけ必要です")

    for label, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(article):
            raise ValueError(f"完成Markdownに{label}が混入しています")

    if "おすすめ商品のリンクまとめ" in article:
        raise ValueError("おすすめ商品のリンクまとめを掲載することはできません")

    if affiliate_group:
        normalized_article = article.replace("\r\n", "\n").replace("\r", "\n")
        normalized_intro = str(adapted_section_intro or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        blocks = list(adapted_product_texts or [product.text for product in affiliate_group.products])
        if len(blocks) != len(affiliate_group.products):
            raise ValueError("商品ブロック件数が一致しません")
        search_from = 0
        if affiliate_group.section_intro:
            if not normalized_intro:
                raise ValueError("カテゴリ共通説明文がありません")
            intro_position = normalized_article.find(normalized_intro)
            if intro_position < 0 or normalized_article.find(normalized_intro, intro_position + 1) >= 0:
                raise ValueError("カテゴリ共通説明文は1回だけ掲載してください")
            search_from = intro_position + len(normalized_intro)
        for product, block in zip(affiliate_group.products, blocks):
            normalized_block = str(block).replace("\r\n", "\n").replace("\r", "\n").strip()
            position = normalized_article.find(normalized_block, search_from)
            if position < 0:
                raise ValueError(f"調整済み商品ブロックが掲載されていません: {product.title}")
            search_from = position + len(normalized_block)

    for url in allowed_new_urls or ():
        if url not in article:
            raise ValueError(f"必要な商品URLがありません: {url}")
