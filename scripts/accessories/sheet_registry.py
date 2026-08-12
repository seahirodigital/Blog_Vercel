"""周辺機器DB_LLMの一子記事一行キューを管理する。"""

from __future__ import annotations

from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .sheet_master_loader import SPREADSHEET_ID


SHEET_NAME = "周辺機器DB_LLM"
HEADERS = (
    "作成日時",
    "完了日時",
    "記事タイトル",
    "進捗",
    "記事URLリンク",
    "大元記事タイトル",
    "大元記事リンク",
    "対象周辺機器",
    "生成エンジン",
    "エラー概要",
    "ジョブID",
    "バッチID",
)
STATUSES = {"記事化", "失敗", "完了"}
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def _worksheet(service_account_info: dict[str, Any]):
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    actual = worksheet.row_values(1)[: len(HEADERS)]
    if tuple(actual) != HEADERS:
        raise ValueError("周辺機器DB_LLMの先頭12列が仕様と一致しません")
    return worksheet


def safe_sheet_text(value: Any) -> str:
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def append_job(service_account_info: dict[str, Any], job: dict[str, Any]) -> None:
    row = [
        job["created_at"],
        "",
        job["article_title"],
        "記事化",
        "",
        job["parent"].get("title", ""),
        job["parent"].get("web_url", ""),
        job["category"].get("name", ""),
        job["engine"],
        "",
        job["job_id"],
        job["batch_id"],
    ]
    _worksheet(service_account_info).append_row(
        [safe_sheet_text(value) for value in row],
        value_input_option="RAW",
    )


def _job_row(worksheet, job_id: str) -> int:
    values = worksheet.col_values(HEADERS.index("ジョブID") + 1)
    rows = [index + 1 for index, value in enumerate(values) if value == job_id]
    if len(rows) != 1:
        raise ValueError(f"周辺機器DB_LLMのジョブIDは1行だけ必要です: {job_id} ({len(rows)}行)")
    return rows[0]


def update_job(
    service_account_info: dict[str, Any],
    *,
    job_id: str,
    status: str,
    completed_at: str = "",
    article_url: str = "",
    error_summary: str = "",
) -> None:
    if status not in STATUSES:
        raise ValueError(f"進捗が不正です: {status}")
    worksheet = _worksheet(service_account_info)
    row = _job_row(worksheet, job_id)
    updates = {
        "完了日時": completed_at if status == "完了" else "",
        "進捗": status,
        "記事URLリンク": article_url if status == "完了" else "",
        "エラー概要": error_summary if status == "失敗" else "",
    }
    values = worksheet.row_values(row)[: len(HEADERS)]
    values += [""] * (len(HEADERS) - len(values))
    for header, value in updates.items():
        values[HEADERS.index(header)] = safe_sheet_text(value)
    worksheet.update(
        range_name=f"A{row}:L{row}",
        values=[values],
        value_input_option="RAW",
    )


def list_pending(service_account_info: dict[str, Any], engine: str) -> list[dict[str, str]]:
    records = _worksheet(service_account_info).get_all_records()
    return [
        {header: str(record.get(header, "")) for header in HEADERS}
        for record in records
        if str(record.get("進捗", "")).strip() == "記事化"
        and str(record.get("生成エンジン", "")).strip() == engine
        and str(record.get("ジョブID", "")).strip()
    ]
