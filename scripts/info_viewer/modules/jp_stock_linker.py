"""Gemini本文中の日本株企業名へMoomooリンクを付与する。

Apifyの原文はこのモジュールに渡さず、Geminiが生成したMarkdown本文だけを対象にする。
企業候補はJPXの公式上場銘柄一覧から決定的に抽出し、Yahoo Finance Japanの検索結果で
同じ東証コードが見つかる場合だけリンク化する。LLMや追加の認証情報は使わない。
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Callable, Iterable
from zipfile import BadZipFile, ZipFile

import requests

JPX_LISTED_ISSUES_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
YAHOO_FINANCE_JP_SEARCH_URL = "https://finance.yahoo.co.jp/search"
MOOMOO_JP_STOCK_URL = "https://www.moomoo.com/ja/stock/{code}-JP"
REQUEST_TIMEOUT_SECONDS = 12
MAX_YAHOO_LOOKUPS_PER_ARTICLE = 20
XML_NAMESPACE = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class JapaneseListedCompany:
    """JPX一覧にある内国株式の企業名と4桁証券コード。"""

    code: str
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class LinkResult:
    """本文の変換結果。失敗時も元の本文を返して保存経路を止めない。"""

    markdown: str
    linked_count: int
    lookup_count: int
    error: str = ""


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.replace("\u3000", "").replace(" ", "")
    normalized = normalized.replace("株式会社", "").replace("(株)", "").replace("（株）", "")
    return normalized.strip()


def _aliases_for_company(name: str) -> tuple[str, ...]:
    canonical = _normalize_name(name)
    candidates = [canonical]

    # 動画要約でよく用いられる「トヨタ」「日産」などの略称を、決め打ちではなく
    # 銘柄名の一般的な末尾語から作る。短すぎる語は誤リンクを避けるため採用しない。
    for suffix in ("自動車", "ホールディングス", "グループ"):
        if canonical.endswith(suffix):
            candidates.append(canonical[: -len(suffix)])

    aliases = {candidate for candidate in candidates if len(candidate) >= 3}
    return tuple(sorted(aliases, key=len, reverse=True))


def _xlsx_rows(content: bytes) -> Iterable[list[str]]:
    """外部Excelライブラリなしで、JPXの単一シートXLSXを読む。"""

    with ZipFile(BytesIO(content)) as archive:
        shared_root = element_tree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(node.text or "" for node in item.iterfind(".//x:t", XML_NAMESPACE))
            for item in shared_root.findall("x:si", XML_NAMESPACE)
        ]
        worksheet = element_tree.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    for row in worksheet.findall(".//x:sheetData/x:row", XML_NAMESPACE):
        values: list[str] = []
        for cell in row.findall("x:c", XML_NAMESPACE):
            value = cell.findtext("x:v", default="", namespaces=XML_NAMESPACE)
            if cell.get("t") == "s" and value:
                values.append(shared_strings[int(value)])
            else:
                values.append(value)
        yield values


def _companies_from_jpx_xlsx(content: bytes) -> tuple[JapaneseListedCompany, ...]:
    rows = list(_xlsx_rows(content))
    if not rows:
        raise ValueError("JPX上場銘柄一覧が空です")

    header = rows[0]
    try:
        code_index = header.index("コード")
        name_index = header.index("銘柄名")
        market_index = header.index("市場・商品区分")
    except ValueError as error:
        raise ValueError("JPX上場銘柄一覧の列構成を確認できません") from error

    companies: list[JapaneseListedCompany] = []
    for row in rows[1:]:
        if len(row) <= max(code_index, name_index, market_index):
            continue
        code = str(row[code_index]).strip()
        name = str(row[name_index]).strip()
        market = str(row[market_index]).strip()
        if not re.fullmatch(r"\d{4}", code) or "内国株式" not in market:
            continue
        aliases = _aliases_for_company(name)
        if aliases:
            companies.append(JapaneseListedCompany(code=code, name=name, aliases=aliases))
    if not companies:
        raise ValueError("JPX上場銘柄一覧から内国株式を取得できません")
    return tuple(companies)


@lru_cache(maxsize=1)
def load_japanese_listed_companies() -> tuple[JapaneseListedCompany, ...]:
    """JPX公式一覧を1実行につき1回だけ取得する。"""

    response = requests.get(
        JPX_LISTED_ISSUES_URL,
        headers={"User-Agent": "InfoViewerStockLinker/1.0", "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _companies_from_jpx_xlsx(response.content)


def _yahoo_finance_confirms_jp_code(query: str, expected_code: str) -> bool:
    """Yahoo Finance Japan検索で候補と同じ東証コードを確認する。"""

    response = requests.get(
        YAHOO_FINANCE_JP_SEARCH_URL,
        params={"query": query},
        headers={"User-Agent": "InfoViewerStockLinker/1.0", "Accept": "text/html"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    pattern = rf"/quote/{re.escape(expected_code)}\.T(?:[\"/?]|$)"
    return bool(re.search(pattern, response.text))


def _protected_parts(line: str) -> list[tuple[bool, str]]:
    """既存リンク、インラインコード、URLを保護して本文部分だけを返す。"""

    protected_pattern = r"(\[[^\]\n]+\]\([^\)\n]+\)|`[^`\n]*`|https?://[^\s<]+)"
    parts = re.split(protected_pattern, line)
    return [(index % 2 == 1, part) for index, part in enumerate(parts) if part]


def _link_plain_text(
    text: str,
    companies: tuple[JapaneseListedCompany, ...],
    yahoo_lookup: Callable[[str, str], bool],
    lookup_cache: dict[tuple[str, str], bool],
    max_lookups: int,
) -> tuple[str, int, int]:
    aliases: list[tuple[str, JapaneseListedCompany]] = []
    for company in companies:
        aliases.extend((alias, company) for alias in company.aliases if alias in text)
    aliases.sort(key=lambda item: len(item[0]), reverse=True)

    occupied = [False] * len(text)
    replacements: list[tuple[int, int, str]] = []
    linked_count = 0
    lookup_count = 0
    for alias, company in aliases:
        for match in re.finditer(re.escape(alias), text):
            start, end = match.span()
            if any(occupied[start:end]):
                continue
            cache_key = (alias, company.code)
            confirmed = lookup_cache.get(cache_key)
            if confirmed is None:
                if lookup_count >= max_lookups:
                    continue
                lookup_count += 1
                try:
                    confirmed = yahoo_lookup(alias, company.code)
                except requests.RequestException:
                    confirmed = False
                lookup_cache[cache_key] = confirmed
            if not confirmed:
                continue
            link = f"[{match.group(0)}]({MOOMOO_JP_STOCK_URL.format(code=company.code)})"
            replacements.append((start, end, link))
            occupied[start:end] = [True] * (end - start)
            linked_count += 1

    # 検出順は社名の長さ順なので、本文の後方から適用して位置ずれを防ぐ。
    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, linked_count, lookup_count


def link_markdown(
    markdown: str,
    companies: tuple[JapaneseListedCompany, ...],
    yahoo_lookup: Callable[[str, str], bool] = _yahoo_finance_confirms_jp_code,
    max_lookups: int = MAX_YAHOO_LOOKUPS_PER_ARTICLE,
) -> LinkResult:
    """Markdownを保持したまま、保護対象以外の企業名だけをリンク化する。"""

    in_fenced_code = False
    lookup_cache: dict[tuple[str, str], bool] = {}
    linked_count = 0
    lookup_count = 0
    rebuilt_lines: list[str] = []

    for line in str(markdown or "").splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fenced_code = not in_fenced_code
            rebuilt_lines.append(line)
            continue
        if in_fenced_code:
            rebuilt_lines.append(line)
            continue

        rebuilt_parts: list[str] = []
        for is_protected, part in _protected_parts(line):
            if is_protected:
                rebuilt_parts.append(part)
                continue
            updated, linked, looked_up = _link_plain_text(
                part,
                companies,
                yahoo_lookup,
                lookup_cache,
                max(0, max_lookups - lookup_count),
            )
            rebuilt_parts.append(updated)
            linked_count += linked
            lookup_count += looked_up
        rebuilt_lines.append("".join(rebuilt_parts))

    return LinkResult("".join(rebuilt_lines), linked_count, lookup_count)


def link_gemini_markdown(markdown: str) -> LinkResult:
    """本番用入口。銘柄マスタ取得に失敗しても元本文をそのまま返す。"""

    try:
        companies = load_japanese_listed_companies()
    except (OSError, ValueError, requests.RequestException, BadZipFile) as error:
        return LinkResult(str(markdown or ""), 0, 0, str(error))
    try:
        return link_markdown(str(markdown or ""), companies)
    except Exception as error:
        return LinkResult(str(markdown or ""), 0, 0, str(error))
