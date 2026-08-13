"""本文を保護し、見出しと二つの限定領域だけを差し替える。"""

from __future__ import annotations

import re
from dataclasses import dataclass


HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*(\r?\n|$)")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
PRODUCT_RE = re.compile(r"^[ \t]*(?:\*\*)?▼")
URL_RE = re.compile(r"https?://[^\s)\]]+")
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
class TextRegion:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class VariantSource:
    source_title: str
    target_title: str
    headings: tuple[Heading, ...]
    intro: TextRegion
    conclusion: TextRegion
    conclusion_heading: Heading | None
    conclusion_insert_at: int


def normalize_keyword(value: str) -> str:
    keyword = str(value or "").replace("\u3000", " ")
    keyword = re.sub(r"[\x00-\x1f\x7f]", " ", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip(" \t:：|│。．")
    if not keyword:
        raise ValueError("変換キーワードが空です")
    if len(keyword) > 120:
        raise ValueError("変換キーワードは120文字以内にしてください")
    if URL_RE.search(keyword):
        raise ValueError("変換キーワードにURLを含めることはできません")
    return keyword


def target_title(keyword: str) -> str:
    normalized = normalize_keyword(keyword)
    return normalized if normalized.endswith("まとめ") else f"{normalized}まとめ"


def target_filename(keyword: str) -> str:
    title = target_title(keyword)
    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title:
        raise ValueError("記事ファイル名を作成できません")
    return f"{title[:150].rstrip(' .')}.md"


def _headings(markdown: str) -> tuple[Heading, ...]:
    headings: list[Heading] = []
    offset = 0
    fence_marker = ""
    for line in markdown.splitlines(keepends=True):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if not fence_marker:
                fence_marker = marker
            elif marker == fence_marker:
                fence_marker = ""
            offset += len(line)
            continue
        if not fence_marker:
            match = HEADING_LINE_RE.match(line)
            if match:
                headings.append(
                    Heading(
                        level=len(match.group(1)),
                        title=match.group(2).strip(),
                        start=offset,
                        end=offset + match.end(),
                        newline=match.group(3),
                    )
                )
        offset += len(line)
    return tuple(headings)


def _first_text_region(markdown: str, start: int, stop: int | None = None) -> TextRegion:
    boundary = len(markdown) if stop is None else stop
    cursor = start
    while cursor < boundary:
        line_end = markdown.find("\n", cursor, boundary)
        line_end = boundary if line_end < 0 else line_end + 1
        if markdown[cursor:line_end].strip():
            break
        cursor = line_end
    region_start = cursor
    while cursor < boundary:
        line_end = markdown.find("\n", cursor, boundary)
        line_end = boundary if line_end < 0 else line_end + 1
        line = markdown[cursor:line_end]
        stripped = line.strip()
        if cursor > region_start and not stripped:
            break
        if HEADING_LINE_RE.match(line) or PRODUCT_RE.match(line):
            break
        cursor = line_end
    return TextRegion(region_start, cursor, markdown[region_start:cursor].rstrip("\r\n"))


def _is_conclusion(title: str) -> bool:
    value = str(title or "").strip().strip("*_")
    return bool(re.search(r"(?:^|[:：│|])\s*結論\s*$", value))


def _is_summary(title: str) -> bool:
    value = str(title or "").strip().strip("*_")
    return bool(re.search(r"(?:^|[:：│|])\s*まとめ\s*$", value))


def _first_product_insert_at(markdown: str, h1: Heading, headings: tuple[Heading, ...]) -> int:
    lines: list[tuple[int, str]] = []
    offset = 0
    for line in markdown.splitlines(keepends=True):
        lines.append((offset, line))
        offset += len(line)
    first_index = next(
        (index for index, (position, line) in enumerate(lines) if position >= h1.end and PRODUCT_RE.match(line)),
        None,
    )
    if first_index is None:
        return next((heading.start for heading in headings if heading.start > h1.start), len(markdown))
    first_start = lines[first_index][0]
    next_product = next(
        (position for position, line in lines[first_index + 1 :] if PRODUCT_RE.match(line)),
        None,
    )
    next_heading = next((heading.start for heading in headings if heading.start > first_start), None)
    boundaries = [value for value in (next_product, next_heading) if value is not None]
    fallback_insert_at = min(boundaries) if boundaries else len(markdown)
    amazon_url = AMAZON_URL_RE.search(markdown, first_start, fallback_insert_at)
    if not amazon_url:
        return fallback_insert_at
    line_end = markdown.find("\n", amazon_url.end(), fallback_insert_at)
    return line_end + 1 if line_end >= 0 else fallback_insert_at


def analyze_variant_source(markdown: str, keyword: str) -> VariantSource:
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("元記事本文が空です")
    headings = _headings(markdown)
    h1s = [heading for heading in headings if heading.level == 1]
    if len(h1s) != 1:
        raise ValueError(f"H1は1件だけ必要です: {len(h1s)}件")
    h1 = h1s[0]
    if markdown[: h1.start].strip():
        raise ValueError("元記事の最初の空白でない行がH1ではありません")
    conclusion_heading = next(
        (heading for heading in headings if heading.level >= 2 and _is_conclusion(heading.title)),
        None,
    )
    intro_stop = next((heading.start for heading in headings if heading.start > h1.start), len(markdown))
    intro = _first_text_region(markdown, h1.end, intro_stop)
    if not intro.text:
        raise ValueError("元記事の冒頭文を特定できません")
    if conclusion_heading is not None:
        next_heading = next(
            (heading for heading in headings if heading.start > conclusion_heading.start),
            None,
        )
        conclusion = _first_text_region(
            markdown,
            conclusion_heading.end,
            next_heading.start if next_heading else len(markdown),
        )
        conclusion_insert_at = conclusion_heading.start
    else:
        summary_heading = next(
            (heading for heading in reversed(headings) if heading.level >= 2 and _is_summary(heading.title)),
            None,
        )
        if summary_heading is not None:
            following = next((heading for heading in headings if heading.start > summary_heading.start), None)
            conclusion = _first_text_region(
                markdown,
                summary_heading.end,
                following.start if following else len(markdown),
            )
        else:
            conclusion = TextRegion(intro.start, intro.end, intro.text)
        conclusion_insert_at = _first_product_insert_at(markdown, h1, headings)
    return VariantSource(
        source_title=h1.title,
        target_title=target_title(keyword),
        headings=headings,
        intro=intro,
        conclusion=conclusion,
        conclusion_heading=conclusion_heading,
        conclusion_insert_at=conclusion_insert_at,
    )


def _heading_topic(title: str, source_title: str) -> str:
    value = str(title or "").strip().strip("*_")
    if _is_conclusion(value):
        return "結論"
    delimiter = re.search(r"[:：│|]", value)
    if delimiter:
        topic = value[delimiter.end() :].strip(" :：│|")
        if topic:
            return topic
    source_prefix = re.split(r"[:：│|]", source_title, maxsplit=1)[0].strip()
    product = re.split(r"\s*(?:レビュー|比較|違い|おすすめ|まとめ)", source_prefix, maxsplit=1)[0].strip()
    if product and value.startswith(product):
        value = value[len(product) :].lstrip()
        value = re.sub(r"^(?:(?:レビュー|比較|違い|おすすめ|まとめ)(?:ます)?[。．.!！?？]?\s*)+", "", value)
        value = value.lstrip(" :：│|")
    return value or "概要"


def _normalized_replacement(value: str, newline: str) -> str:
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized.replace("\n", newline)


def _region_replacement(markdown: str, region: TextRegion, value: str, newline: str) -> str:
    replacement = _normalized_replacement(value, newline)
    original = markdown[region.start : region.end]
    return f"{replacement}{newline}" if original.endswith(("\n", "\r")) else replacement


def assemble_variant(
    markdown: str,
    *,
    keyword: str,
    intro_text: str | None = None,
    conclusion_text: str | None = None,
) -> tuple[str, VariantSource]:
    source = analyze_variant_source(markdown, keyword)
    newline = "\r\n" if "\r\n" in markdown else "\n"
    edits: list[tuple[int, int, str]] = []
    for heading in source.headings:
        marker = "#" * heading.level
        if heading.level == 1:
            replacement = source.target_title
        else:
            topic = _heading_topic(heading.title, source.source_title)
            replacement = f"{source.target_title}：{topic}"
        edits.append((heading.start, heading.end, f"{marker} {replacement}{heading.newline}"))
    if intro_text is not None:
        edits.append(
            (
                source.intro.start,
                source.intro.end,
                _region_replacement(markdown, source.intro, intro_text, newline),
            )
        )
    if conclusion_text is not None and source.conclusion.text and source.conclusion_heading is not None:
        edits.append(
            (
                source.conclusion.start,
                source.conclusion.end,
                _region_replacement(markdown, source.conclusion, conclusion_text, newline),
            )
        )
    if source.conclusion_heading is None:
        inserted_conclusion = _normalized_replacement(
            conclusion_text if conclusion_text is not None else source.conclusion.text,
            newline,
        )
        before = markdown[: source.conclusion_insert_at]
        after = markdown[source.conclusion_insert_at :]
        prefix = "" if before.endswith(newline * 2) else newline if before.endswith(newline) else newline * 2
        suffix = "" if after.startswith(newline * 2) else newline if after.startswith(newline) else newline * 2
        insertion = f"{prefix}## {source.target_title}：結論{newline}{newline}{inserted_conclusion}{suffix}"
        edits.append((source.conclusion_insert_at, source.conclusion_insert_at, insertion))
    article = markdown
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        article = f"{article[:start]}{replacement}{article[end:]}"
    return article, source


def validate_variant(markdown: str, source_markdown: str, keyword: str) -> None:
    source = analyze_variant_source(source_markdown, keyword)
    headings = _headings(markdown)
    h1s = [heading for heading in headings if heading.level == 1]
    if len(h1s) != 1 or h1s[0].title != source.target_title:
        raise ValueError("変換後のH1が指定キーワードと一致しません")
    if markdown.lstrip().startswith("---"):
        raise ValueError("記事本文へFrontmatterまたはYAMLを出力できません")
    if "<br" in markdown.lower():
        raise ValueError("保存本文へHTML改行を出力できません")
    if markdown.lstrip().startswith(("```json", "```yaml")):
        raise ValueError("記事本文へLLM応答形式を出力できません")
    source_urls = URL_RE.findall(source_markdown)
    output_urls = URL_RE.findall(markdown)
    if source_urls != output_urls:
        raise ValueError("元記事のURLが変更または欠落しています")
    source_products = [line.strip() for line in source_markdown.splitlines() if PRODUCT_RE.match(line)]
    output_products = [line.strip() for line in markdown.splitlines() if PRODUCT_RE.match(line)]
    if source_products != output_products:
        raise ValueError("元記事の商品ブロック見出しが変更または欠落しています")
    if not any(heading.level >= 2 and heading.title == f"{source.target_title}：結論" for heading in headings):
        raise ValueError("変換後の結論見出しがありません")
