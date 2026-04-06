"""ラッコキーワード結果を Google Spreadsheet に保存し、再開用に読み戻す。"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

try:
    from ..analyzers.keyword_intent_classifier import make_intent_sort_key
except ImportError:  # pragma: no cover
    from analyzers.keyword_intent_classifier import make_intent_sort_key  # type: ignore

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_ROW = ["キーワード", "検索ボリューム", "クエリタイプ", "状況"]
EXCLUDE_STATUS = {"不要"}
PARTICLE_PREFIXES = ("の ", "を ", "に ", "で ", "は ", "が ", "と ")


def _get_gs_client() -> gspread.Client:
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    local_candidates = [
        r"C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\env\google-service-account.json",
        r"C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\service_account.json",
        r"C:\Users\HCY\OneDrive\開発\Blog_Vercel\service_account.json",
    ]
    for path in local_candidates:
        if os.path.exists(path):
            creds = Credentials.from_service_account_file(path, scopes=SCOPES)
            return gspread.authorize(creds)

    raise FileNotFoundError(
        "Google Sheets 認証情報が見つかりません。"
        " 環境変数 GOOGLE_SERVICE_ACCOUNT_JSON か service_account.json を用意してください。"
    )


def _sanitize_sheet_title(title: str, max_length: int = 100) -> str:
    normalized = re.sub(r"[\[\]\:\*\?/\\]", " ", str(title or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return (normalized or "seed_keyword")[:max_length]


def _move_sheet_to_rightmost(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet) -> None:
    worksheets = spreadsheet.worksheets()
    reordered = [sheet for sheet in worksheets if sheet.id != worksheet.id] + [worksheet]
    spreadsheet.reorder_worksheets(reordered)


def _format_header(worksheet: gspread.Worksheet) -> None:
    worksheet.format(
        "A1:D1",
        {
            "backgroundColor": {"red": 0, "green": 0, "blue": 0},
            "textFormat": {
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                "bold": True,
            },
        },
    )
    worksheet.freeze(rows=1)
    worksheet.set_basic_filter("A1:D1")


def _sort_records_for_sheet(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared = [dict(record) for record in records]
    prepared.sort(
        key=lambda record: make_intent_sort_key(
            query_type=str(record.get("query_type", "")).strip(),
            volume_label=str(record.get("volume_label", "")).strip(),
            suggest_keyword=str(record.get("suggest_keyword", "")).strip(),
            article_candidate=bool(record.get("article_candidate")),
        )
    )
    return prepared


def _default_sheet_status(record: Mapping[str, Any]) -> str:
    seed_keyword = str(record.get("seed_keyword", "")).strip()
    suggest_keyword = str(record.get("suggest_keyword", "")).strip()
    volume_label = str(record.get("volume_label", "")).strip()
    query_type = str(record.get("query_type", "")).strip()

    normalized_seed = re.sub(r"\s+", " ", seed_keyword).strip().casefold()
    normalized_suggest = re.sub(r"\s+", " ", suggest_keyword).strip().casefold()
    suffix = normalized_suggest
    if normalized_seed and normalized_suggest.startswith(normalized_seed):
        suffix = normalized_suggest[len(normalized_seed):].strip(" 　-ー_")
    original_suffix = suggest_keyword
    if seed_keyword and suggest_keyword.casefold().startswith(seed_keyword.casefold()):
        original_suffix = suggest_keyword[len(seed_keyword):].strip(" 　-ー_")

    if normalized_seed and normalized_suggest == normalized_seed:
        return "不要"
    if any(original_suffix.startswith(prefix) for prefix in PARTICLE_PREFIXES):
        return "不要"
    if suffix == "とは":
        return "不要"
    if suggest_keyword and re.fullmatch(r"[A-Za-z0-9 _\\-\\./+]+", suggest_keyword):
        return "不要"
    if volume_label == "小":
        return "不要"
    if volume_label == "中" and query_type in {"Know", "Do"}:
        return "不要"
    return ""


def write_keyword_records_to_sheet(
    spreadsheet_id: str,
    sheet_title: str,
    records: Iterable[Mapping[str, Any]],
) -> str:
    """キーワード一覧を右端シートへ保存する。"""
    client = _get_gs_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    safe_title = _sanitize_sheet_title(sheet_title)
    sorted_records = _sort_records_for_sheet(records)
    rows = [
        [
            str(record.get("suggest_keyword", "")),
            str(record.get("volume_label", "")),
            str(record.get("query_type", "")),
            _default_sheet_status(record),
        ]
        for record in sorted_records
        if str(record.get("suggest_keyword", "")).strip()
    ]

    try:
        worksheet = spreadsheet.worksheet(safe_title)
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=safe_title,
            rows=max(len(rows) + 50, 200),
            cols=len(HEADER_ROW),
        )

    worksheet.resize(rows=max(len(rows) + 50, 200), cols=len(HEADER_ROW))
    worksheet.update(values=[HEADER_ROW, *rows], range_name="A1")
    _format_header(worksheet)
    _move_sheet_to_rightmost(spreadsheet, worksheet)
    return safe_title


def load_keyword_records_from_sheet(spreadsheet_id: str, sheet_title: str) -> list[dict[str, Any]]:
    """保存済みシートからキーワード一覧を読む。"""
    client = _get_gs_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(_sanitize_sheet_title(sheet_title))
    records = worksheet.get_all_records()
    loaded: list[dict[str, Any]] = []
    for record in records:
        keyword = str(record.get("キーワード", "")).strip()
        if not keyword:
            continue
        loaded.append(
            {
                "suggest_keyword": keyword,
                "volume_label": str(record.get("検索ボリューム", "")).strip(),
                "query_type": str(record.get("クエリタイプ", "")).strip(),
                "sheet_status": str(record.get("状況", "")).strip(),
            }
        )
    return loaded


def select_keyword_records_for_generation(
    seed_keyword: str,
    sheet_records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """シートの手動選別結果を、母艦記事生成向けレコードに変換する。"""
    normalized_rows: list[dict[str, Any]] = []
    positive_rows: list[dict[str, Any]] = []

    for record in sheet_records:
        keyword = str(record.get("suggest_keyword", "")).strip()
        if not keyword:
            continue

        status = str(record.get("sheet_status", "")).strip()
        if status in EXCLUDE_STATUS:
            continue

        normalized = {
            "seed_keyword": seed_keyword,
            "suggest_keyword": keyword,
            "volume_label": str(record.get("volume_label", "")).strip(),
            "query_type": str(record.get("query_type", "")).strip() or "Know",
            "sheet_status": status,
            "article_candidate": bool(status),
            "article_status": status,
            "source": "google_sheet",
        }
        normalized_rows.append(normalized)
        if status:
            positive_rows.append(normalized)

    return positive_rows if positive_rows else normalized_rows


__all__ = [
    "load_keyword_records_from_sheet",
    "select_keyword_records_for_generation",
    "write_keyword_records_to_sheet",
]
