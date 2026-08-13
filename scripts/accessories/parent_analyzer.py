"""親記事のH1・H2・結論範囲をバイト保存に配慮して解析する。"""

from __future__ import annotations

import re
from dataclasses import dataclass


HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*(\r?\n|$)")
PRODUCT_BLOCK_RE = re.compile(r"(?m)^[ \t]*(?:\*\*)?▼")
AMAZON_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:amazon\.co\.jp|amzn\.to)/[^\s)\]]+",
    re.I,
)


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start: int
    end: int
    newline: str


@dataclass(frozen=True)
class ParentArticle:
    markdown: str
    h1: Heading
    headings: tuple[Heading, ...]
    h2_headings: tuple[Heading, ...]
    conclusion_insert_at: int
    first_product_insert_at: int
    explicit_conclusion: bool
    product_name: str


SPEC_EVIDENCE_RE = re.compile(
    r"(?:\d|USB|PD|W\b|mAh|GB|TB|Hz|inch|インチ|チップ|充電|メモリ|SSD|CPU|GPU)",
    re.I,
)


def _is_conclusion_heading(title: str) -> bool:
    """「結論」単独と、既存SEO接頭辞付きの結論見出しを識別する。"""
    value = str(title or "").strip()
    return bool(re.search(r"(?:^|[:：│|])\s*結論(?:\s*[:：].*)?\s*$", value))


def _derive_product_name(h1_title: str) -> str:
    left = re.split(r"[:：│|]", h1_title, maxsplit=1)[0].strip()
    # 親記事のSEO用記事軸は製品名に含めない。
    # 例: 「M5 iPad Pro レビュー比較違いまとめます。」→「M5 iPad Pro」
    left = re.split(r"\s*(?:レビュー|比較|違い|まとめ)", left, maxsplit=1)[0].strip()
    left = re.sub(r"[\s。．.!！?？:：│|]+$", "", left).strip()
    return left or h1_title.strip()


def analyze_parent(markdown: str) -> ParentArticle:
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("親記事本文が空です")

    headings = tuple(
        Heading(
            level=len(match.group(1)),
            title=match.group(2).strip(),
            start=match.start(),
            end=match.end(),
            newline=match.group(3),
        )
        for match in HEADING_RE.finditer(markdown)
    )
    h1s = [heading for heading in headings if heading.level == 1]
    if len(h1s) != 1:
        raise ValueError(f"H1は1件だけ必要です: {len(h1s)}件")
    h1 = h1s[0]
    if markdown[: h1.start].strip():
        raise ValueError("親記事の最初の空白でない行がH1ではありません")

    h2s = tuple(heading for heading in headings if heading.level == 2)
    explicit = next(
        (
            heading
            for heading in h2s
            if _is_conclusion_heading(heading.title)
        ),
        None,
    )
    if explicit:
        following = next((heading for heading in h2s if heading.start > explicit.start), None)
        insert_at = following.start if following else len(markdown)
    else:
        following = next((heading for heading in h2s if heading.start > h1.start), None)
        insert_at = following.start if following else len(markdown)

    first_amazon_url = AMAZON_URL_RE.search(markdown, h1.end)
    if first_amazon_url:
        line_end = markdown.find("\n", first_amazon_url.end())
        first_product_insert_at = line_end + 1 if line_end >= 0 else len(markdown)
    else:
        first_product = PRODUCT_BLOCK_RE.search(markdown, h1.end)
        if first_product:
            next_product = PRODUCT_BLOCK_RE.search(markdown, first_product.end())
            next_h2 = next((heading for heading in h2s if heading.start > first_product.start()), None)
            boundaries = [
                position
                for position in (
                    next_product.start() if next_product else None,
                    next_h2.start if next_h2 else None,
                )
                if position is not None
            ]
            first_product_insert_at = min(boundaries) if boundaries else len(markdown)
        else:
            following_h2 = next((heading for heading in h2s if heading.start > h1.start), None)
            first_product_insert_at = following_h2.start if following_h2 else len(markdown)

    return ParentArticle(
        markdown=markdown,
        h1=h1,
        headings=headings,
        h2_headings=h2s,
        conclusion_insert_at=insert_at,
        first_product_insert_at=first_product_insert_at,
        explicit_conclusion=explicit is not None,
        product_name=_derive_product_name(h1.title),
    )


def extract_generation_evidence(parent: ParentArticle, max_chars: int = 12000) -> str:
    """結論と仕様根拠を取り出し、LLMに全文改稿の入力を与えない。"""
    if parent.explicit_conclusion:
        explicit = next(
            heading
            for heading in parent.h2_headings
            if _is_conclusion_heading(heading.title)
        )
        conclusion_start = explicit.end
    else:
        conclusion_start = parent.h1.end
    conclusion = parent.markdown[conclusion_start : parent.conclusion_insert_at].strip()

    evidence_lines: list[str] = []
    for line in parent.markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("http://", "https://", "#")):
            continue
        if SPEC_EVIDENCE_RE.search(stripped):
            evidence_lines.append(stripped)

    evidence = "\n".join(dict.fromkeys(evidence_lines))
    combined = f"【親記事の結論】\n{conclusion}\n\n【親記事から抽出した仕様根拠】\n{evidence}".strip()
    return combined[:max_chars]
