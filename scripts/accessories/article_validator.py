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

    if affiliate_group:
        previous = -1
        for product in affiliate_group.products:
            position = article.find(product.text)
            if position < 0:
                raise ValueError(f"商品ブロックが原文のまま掲載されていません: {product.title}")
            if article.find(product.text, position + 1) >= 0:
                raise ValueError(f"商品ブロックが重複しています: {product.title}")
            if position <= previous:
                raise ValueError("商品ブロックの順番が変更されています")
            previous = position

        if article.count("(Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。文章にはAIの整形・編集が含まれます。)") != 1:
            raise ValueError("新規おすすめ商品群の免責事項は1件だけ必要です")

    for url in allowed_new_urls or ():
        if url not in article:
            raise ValueError(f"必要な商品URLがありません: {url}")
