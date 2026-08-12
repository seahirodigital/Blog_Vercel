"""周辺機器DBを読み込み、ユーザー編集値を検査する。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import gspread
from google.oauth2.service_account import Credentials


SPREADSHEET_ID = "1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94"
SHEET_NAME = "周辺機器DB"
REQUIRED_HEADERS = (
    "親製品検出キーワード",
    "周辺機器カテゴリID",
    "周辺機器カテゴリ名",
    "タイトル形式",
    "アフィリエイトセクション",
    "デフォルト有効",
    "使用テンプレートファイル",
)
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


@dataclass(frozen=True)
class MasterCategory:
    row_number: int
    keywords: tuple[str, ...]
    category_id: str
    category_name: str
    title_format: str
    affiliate_section: str
    default_enabled: bool
    template_file: str
    display_priority: int
    raw: dict[str, str]
    sha256: str


def _client(service_account_info: dict[str, Any]):
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return gspread.authorize(credentials)


def _parse_bool(value: Any, row_number: int) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y", "はい", "有効"}:
        return True
    if normalized in {"false", "0", "no", "n", "いいえ", "無効"}:
        return False
    raise ValueError(f"周辺機器DB {row_number}行目のデフォルト有効が不正です: {value}")


def _keywords(value: str) -> tuple[str, ...]:
    values = [item.strip() for item in re.split(r"[,\n、。|]", str(value or ""))]
    return tuple(item for item in values if item)


def parse_master_rows(headers: list[str], rows: list[list[Any]]) -> tuple[MasterCategory, ...]:
    missing = [header for header in REQUIRED_HEADERS if header not in headers]
    if missing:
        raise ValueError(f"周辺機器DBの必須列が不足しています: {', '.join(missing)}")

    categories: list[MasterCategory] = []
    seen_ids: set[str] = set()
    for row_number, values in enumerate(rows, start=2):
        padded = list(values) + [""] * max(0, len(headers) - len(values))
        raw = {header: str(padded[index] or "").strip() for index, header in enumerate(headers)}
        if not any(raw.values()):
            continue
        category_id = raw["周辺機器カテゴリID"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", category_id):
            raise ValueError(f"周辺機器DB {row_number}行目のカテゴリIDが不正です")
        if category_id in seen_ids:
            raise ValueError(f"周辺機器DBのカテゴリIDが重複しています: {category_id}")
        seen_ids.add(category_id)
        keywords = _keywords(raw["親製品検出キーワード"])
        if not keywords:
            raise ValueError(f"周辺機器DB {row_number}行目の検出キーワードが空です")
        for required in REQUIRED_HEADERS[2:5] + (REQUIRED_HEADERS[6],):
            if not raw[required]:
                raise ValueError(f"周辺機器DB {row_number}行目の{required}が空です")
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        try:
            priority = int(raw.get("表示優先度") or 999)
        except ValueError as error:
            raise ValueError(f"周辺機器DB {row_number}行目の表示優先度が不正です") from error
        categories.append(
            MasterCategory(
                row_number=row_number,
                keywords=keywords,
                category_id=category_id,
                category_name=raw["周辺機器カテゴリ名"],
                title_format=raw["タイトル形式"],
                affiliate_section=raw["アフィリエイトセクション"],
                default_enabled=_parse_bool(raw["デフォルト有効"], row_number),
                template_file=raw["使用テンプレートファイル"],
                display_priority=priority,
                raw=raw,
                sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(sorted(categories, key=lambda item: (item.display_priority, item.row_number)))


def load_master(service_account_info: dict[str, Any]) -> tuple[MasterCategory, ...]:
    worksheet = _client(service_account_info).open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    values = worksheet.get_all_values()
    if not values:
        raise ValueError("周辺機器DBが空です")
    return parse_master_rows(values[0], values[1:])


def matching_categories(article_text: str, categories: tuple[MasterCategory, ...]) -> tuple[MasterCategory, ...]:
    normalized = str(article_text or "").casefold()
    return tuple(
        category
        for category in categories
        if any(keyword.casefold() in normalized for keyword in category.keywords)
    )
