"""Gemini本文中の上場企業名へMoomoo検索リンクを付与する。

Apifyの原文はこのモジュールに渡さず、Geminiが生成したMarkdown本文だけを対象にする。
企業候補はJPXとSECの公開上場企業一覧から決定的に抽出する。証券コードの照合や
Yahoo Financeへの問い合わせはせず、検出した企業名をそのままMoomooアプリの検索語に渡す。
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Iterable, Union
from zipfile import BadZipFile, ZipFile

import requests

JPX_LISTED_ISSUES_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
MOOMOO_SEARCH_URL = "ftmm://search?keyword={name}"
REQUEST_TIMEOUT_SECONDS = 12
XML_NAMESPACE = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# 正式な登記社名だけでは動画要約で使われる通称を拾えない大手企業を補う。
# 値はMoomooへ渡す検索語そのものではなく、本文内の検出別名である。
US_COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "ALPHABET INC.": ("Alphabet", "Google", "グーグル"),
    "META PLATFORMS, INC.": ("Meta Platforms", "Meta", "Facebook", "メタ"),
    "AMAZON.COM, INC.": ("Amazon", "アマゾン"),
    "APPLE INC.": ("Apple", "アップル"),
    "MICROSOFT CORP": ("Microsoft", "マイクロソフト"),
    "NVIDIA CORP": ("NVIDIA", "エヌビディア"),
    "TESLA, INC.": ("Tesla", "テスラ"),
}


@dataclass(frozen=True)
class JapaneseListedCompany:
    """JPX一覧にある内国株式の企業名と、本文で検出する別名。"""

    code: str
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class AmericanListedCompany:
    """SEC一覧にある米国上場企業の企業名と、本文で検出する別名。"""

    name: str
    aliases: tuple[str, ...]


CompanyCandidate = Union[JapaneseListedCompany, AmericanListedCompany]


@dataclass(frozen=True)
class LinkResult:
    """本文の変換結果。失敗時も元の本文を返して保存経路を止めない。"""

    markdown: str
    linked_count: int
    lookup_count: int = 0
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


def _aliases_for_us_company(name: str) -> tuple[str, ...]:
    canonical = unicodedata.normalize("NFKC", str(name or "")).strip()
    candidates = [canonical]
    legal_suffix = re.sub(
        r"(?:,?\s+(?:INCORPORATED|INC\.?|CORPORATION|CORP\.?|LTD\.?|LIMITED|PLC|LP|LLC))$",
        "",
        canonical,
        flags=re.IGNORECASE,
    ).strip(" ,")
    if legal_suffix:
        candidates.append(legal_suffix)
    candidates.extend(US_COMPANY_ALIASES.get(canonical.upper(), ()))
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


def _companies_from_sec_json(content: bytes) -> tuple[AmericanListedCompany, ...]:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("SEC上場企業一覧の形式を確認できません")

    companies: list[AmericanListedCompany] = []
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("title") or "").strip()
        aliases = _aliases_for_us_company(name)
        if aliases:
            companies.append(AmericanListedCompany(name=name, aliases=aliases))
    if not companies:
        raise ValueError("SEC上場企業一覧から企業名を取得できません")
    return tuple(companies)


@lru_cache(maxsize=1)
def load_japanese_listed_companies() -> tuple[JapaneseListedCompany, ...]:
    """JPX公式一覧を1実行につき1回だけ取得する。"""

    response = requests.get(
        JPX_LISTED_ISSUES_URL,
        headers={"User-Agent": "InfoViewerStockLinker/2.0", "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _companies_from_jpx_xlsx(response.content)


@lru_cache(maxsize=1)
def load_american_listed_companies() -> tuple[AmericanListedCompany, ...]:
    """SEC公式一覧を1実行につき1回だけ取得する。証券コードは使わない。"""

    response = requests.get(
        SEC_COMPANY_TICKERS_URL,
        headers={"User-Agent": "InfoViewerStockLinker/2.0 contact=info-viewer@example.com"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _companies_from_sec_json(response.content)


def _protected_parts(line: str) -> list[tuple[bool, str]]:
    """既存リンク、インラインコード、URLを保護して本文部分だけを返す。"""

    protected_pattern = r"(\[[^\]\n]+\]\([^\)\n]+\)|`[^`\n]*`|https?://[^\s<]+)"
    parts = re.split(protected_pattern, line)
    return [(index % 2 == 1, part) for index, part in enumerate(parts) if part]


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    if re.fullmatch(r"[A-Za-z0-9 .,&'’-]+", alias):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped)


def _link_plain_text(text: str, companies: tuple[CompanyCandidate, ...]) -> tuple[str, int]:
    aliases: list[str] = []
    folded_text = text.casefold()
    for company in companies:
        aliases.extend(alias for alias in company.aliases if alias in text or alias.casefold() in folded_text)
    aliases = sorted(set(aliases), key=len, reverse=True)

    occupied = [False] * len(text)
    replacements: list[tuple[int, int, str]] = []
    for alias in aliases:
        for match in _alias_pattern(alias).finditer(text):
            start, end = match.span()
            if any(occupied[start:end]):
                continue
            matched_name = match.group(0)
            link = f"[{matched_name}]({MOOMOO_SEARCH_URL.format(name=matched_name)})"
            replacements.append((start, end, link))
            occupied[start:end] = [True] * (end - start)

    # 検出順は社名の長さ順なので、本文の後方から適用して位置ずれを防ぐ。
    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, len(replacements)


def link_markdown(markdown: str, companies: tuple[CompanyCandidate, ...]) -> LinkResult:
    """Markdownを保持したまま、保護対象以外の企業名だけをリンク化する。"""

    in_fenced_code = False
    linked_count = 0
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
            updated, linked = _link_plain_text(part, companies)
            rebuilt_parts.append(updated)
            linked_count += linked
        rebuilt_lines.append("".join(rebuilt_parts))

    return LinkResult("".join(rebuilt_lines), linked_count)


def link_gemini_markdown(markdown: str) -> LinkResult:
    """本番用入口。取得できた日米の名称辞書だけを使い、証券コード照合はしない。"""

    companies: list[CompanyCandidate] = []
    errors: list[str] = []
    for loader in (load_japanese_listed_companies, load_american_listed_companies):
        try:
            companies.extend(loader())
        except (OSError, ValueError, requests.RequestException, BadZipFile, json.JSONDecodeError) as error:
            errors.append(str(error))

    if not companies:
        return LinkResult(str(markdown or ""), 0, error=" / ".join(errors))
    try:
        return link_markdown(str(markdown or ""), tuple(companies))
    except Exception as error:
        return LinkResult(str(markdown or ""), 0, error=str(error))
