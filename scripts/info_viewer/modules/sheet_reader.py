import json
import os
import re
from datetime import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_CHANNEL_SHEET_NAME = os.getenv("INFO_VIEWER_CHANNEL_SHEET_NAME", "チャンネル設定")
DEFAULT_VIDEO_SHEET_NAME = os.getenv("INFO_VIEWER_VIDEO_SHEET_NAME", "動画リスト")


VIDEO_TITLE_ALIASES = ["動画タイトル", "タイトル", "title", "動画名"]
PUBLISHED_AT_ALIASES = ["投稿日", "公開日", "published_at", "publishedAt"]
VIDEO_UPDATED_AT_ALIASES = ["動画更新日時", "更新日時", "updated_at", "updatedAt", "video_updated_at", "videoUpdatedAt"]
DURATION_ALIASES = ["長さ", "動画時間", "再生時間", "duration"]
THUMBNAIL_ALIASES = ["サムネイル", "thumbnail", "thumb", "thumbnail_url"]


def _normalize_key(value: str) -> str:
    return str(value or "").strip().replace(" ", "").replace("_", "").lower()


def _pick_value(row: dict[str, Any], aliases: list[str], default: str = "") -> str:
    alias_set = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(key) in alias_set:
            return str(value or "").strip()
    return default


def _get_service_account_client():
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    sa_file = os.path.join(os.path.dirname(__file__), "..", "..", "pipeline", "service_account.json")
    if os.path.exists(sa_file):
        creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        return gspread.authorize(creds)

    raise FileNotFoundError("GOOGLE_SERVICE_ACCOUNT_JSON か service_account.json が見つかりません。")


def _get_worksheet(spreadsheet_id: str, sheet_name: str):
    client = _get_service_account_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(sheet_name)


def _load_rows(spreadsheet_id: str, sheet_name: str) -> list[dict[str, Any]]:
    worksheet = _get_worksheet(spreadsheet_id, sheet_name)
    values = worksheet.get_all_values()
    formula_values = worksheet.get_all_values(value_render_option="FORMULA")
    if not values:
        return []

    headers = values[0]
    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(values[1:], start=2):
        padded = raw_row + [""] * max(0, len(headers) - len(raw_row))
        row = {headers[i]: padded[i] for i in range(len(headers))}
        formula_row = formula_values[index - 1] if len(formula_values) >= index else []
        formula_padded = formula_row + [""] * max(0, len(headers) - len(formula_row))
        row["_formula"] = {headers[i]: formula_padded[i] for i in range(len(headers))}
        row["_row_number"] = index
        rows.append(row)
    return rows


def _extract_thumbnail_url(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue

        image_match = re.search(r"""IMAGE\(\s*["']([^"']+)["']""", text, flags=re.I)
        if image_match:
            return image_match.group(1).strip()

        if re.match(r"^https?://", text, flags=re.I):
            return text

    return ""


def _normalize_datetime_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    normalized = re.sub(r"\s+", " ", text)
    formats = (
        "%Y/%m/%d/%H:%M:%S",
        "%Y/%m/%d/%H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%d",
    )
    for date_format in formats:
        try:
            return datetime.strptime(normalized, date_format).isoformat()
        except ValueError:
            continue

    return text


def _normalize_gemini_profile(value: str) -> str:
    text = _normalize_key(value)
    if not text:
        return ""

    if any(keyword in text for keyword in ("geminitokeninvest", "tokeninvest", "invest", "investment", "投資", "株", "fx", "為替", "市況")):
        return "invest"
    if any(keyword in text for keyword in ("geminitokentech", "tokentech", "tech", "technology", "テック", "技術", "開発", "ガジェット", "半導体", "ソフトウェア", "人工知能")):
        return "tech"
    if any(keyword in text for keyword in ("default", "standard", "通常", "標準", "共通", "main")):
        return "default"

    return ""


def _resolve_gemini_profile(*rows: dict[str, Any]) -> str:
    profile_aliases = [
        "gemini_token",
        "gemini token",
        "Geminiトークン",
        "gemini_profile",
        "gemini profile",
        "Geminiプロファイル",
        "カテゴリ",
        "分類",
        "ジャンル",
        "type",
    ]

    for row in rows:
        if not isinstance(row, dict):
            continue
        explicit_profile = _normalize_gemini_profile(_pick_value(row, profile_aliases))
        if explicit_profile:
            return explicit_profile

    keyword_aliases = [
        "カテゴリ",
        "分類",
        "ジャンル",
        "備考",
        "description",
        "channel",
        "channel name",
        "チャンネル",
        "チャンネル名",
        "title",
        "動画タイトル",
        "タイトル",
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        for alias in keyword_aliases:
            profile = _normalize_gemini_profile(_pick_value(row, [alias]))
            if profile:
                return profile

    return ""


def get_target_channels(
    spreadsheet_id: str,
    sheet_name: str = DEFAULT_CHANNEL_SHEET_NAME,
) -> list[dict[str, Any]]:
    rows = _load_rows(spreadsheet_id, sheet_name)
    channels: list[dict[str, Any]] = []

    for row in rows:
        viewer_flag = _pick_value(row, ["info_viewer", "info viewer", "viewer"])
        if viewer_flag != "取得":
            continue

        channel_name = _pick_value(row, ["チャンネル", "チャンネル名", "channel", "channel name"])
        channel_url = _pick_value(row, ["チャンネルURL", "channel_url", "channel url"])
        if not channel_name and not channel_url:
            continue

        channels.append(
            {
                "id": _normalize_key(channel_name or channel_url),
                "name": channel_name or channel_url,
                "channel_name": channel_name or channel_url,
                "channel_url": channel_url,
                "gemini_profile": _resolve_gemini_profile(row),
                "_row_number": row["_row_number"],
                "_raw": row,
            }
        )

    return channels


def get_target_videos(
    spreadsheet_id: str,
    channel_sheet_name: str = DEFAULT_CHANNEL_SHEET_NAME,
    video_sheet_name: str = DEFAULT_VIDEO_SHEET_NAME,
    include_completed: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    channels = get_target_channels(spreadsheet_id, channel_sheet_name)
    channel_name_map = {_normalize_key(channel["channel_name"]): channel for channel in channels if channel.get("channel_name")}
    channel_url_map = {_normalize_key(channel["channel_url"]): channel for channel in channels if channel.get("channel_url")}

    video_rows = _load_rows(spreadsheet_id, video_sheet_name)
    selected_videos: list[dict[str, Any]] = []

    for row in video_rows:
        video_url = _pick_value(row, ["動画URL", "video_url", "url"])
        if not video_url:
            continue

        row_channel_name = _pick_value(row, ["チャンネル", "チャンネル名", "channel", "channel name"])
        row_channel_url = _pick_value(row, ["チャンネルURL", "channel_url", "channel url"])
        matched_channel = channel_name_map.get(_normalize_key(row_channel_name)) or channel_url_map.get(_normalize_key(row_channel_url))
        if not matched_channel:
            continue

        status = _pick_value(row, ["状況", "status"], "")
        if not include_completed and status == "完了":
            continue

        published_at = _normalize_datetime_value(_pick_value(row, PUBLISHED_AT_ALIASES))
        video_updated_at = _normalize_datetime_value(_pick_value(row, VIDEO_UPDATED_AT_ALIASES)) or published_at

        selected_videos.append(
            {
                "row_number": row["_row_number"],
                "video_url": video_url,
                "video_title": _pick_value(row, VIDEO_TITLE_ALIASES),
                "published_at": published_at,
                "video_updated_at": video_updated_at,
                "duration": _pick_value(row, DURATION_ALIASES),
                "thumbnail_url": _extract_thumbnail_url(
                    _pick_value(row.get("_formula", {}), THUMBNAIL_ALIASES),
                    _pick_value(row, THUMBNAIL_ALIASES),
                ),
                "status": status,
                "channel_name": matched_channel["channel_name"],
                "channel_url": matched_channel["channel_url"],
                "channel_id": matched_channel["id"],
                "gemini_profile": _resolve_gemini_profile(row, matched_channel.get("_raw", {})),
                "_raw": row,
            }
        )

    return channels, selected_videos


def update_video_status(
    spreadsheet_id: str,
    row_number: int,
    new_status: str = "完了",
    sheet_name: str = DEFAULT_VIDEO_SHEET_NAME,
):
    worksheet = _get_worksheet(spreadsheet_id, sheet_name)
    headers = worksheet.row_values(1)
    status_col = None
    for index, header in enumerate(headers, start=1):
        if _normalize_key(header) == _normalize_key("状況"):
            status_col = index
            break

    if status_col is None:
        raise ValueError("動画リストに「状況」列が見つかりません。")

    worksheet.update_cell(row_number, status_col, new_status)
