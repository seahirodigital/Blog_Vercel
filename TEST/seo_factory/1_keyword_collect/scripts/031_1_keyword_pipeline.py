"""031_1 前処理パイプライン。

ラッコキーワード取得、正規化、Know / Do / Buy 分類、
Google Spreadsheet への保存と再読込を1ファイルにまとめる。
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import Locator, Page, sync_playwright

INTENT_BUY = "Buy"
INTENT_DO = "Do"
INTENT_KNOW = "Know"

INTENT_ORDER: Mapping[str, int] = {
    INTENT_BUY: 0,
    INTENT_KNOW: 1,
    INTENT_DO: 2,
}

VOLUME_ORDER: Mapping[str, int] = {
    "大": 0,
    "中": 1,
    "小": 2,
    "極小": 3,
}

PRIORITY_BUCKET_ORDER: Mapping[tuple[str, str], int] = {
    (INTENT_BUY, "大"): 0,
    (INTENT_KNOW, "大"): 1,
    (INTENT_BUY, "中"): 2,
    (INTENT_KNOW, "中"): 3,
    (INTENT_BUY, "小"): 4,
}

BUY_KEYWORDS = (
    "価格", "値段", "料金", "金額", "費用", "相場", "定価", "値引き", "割引",
    "安い", "高い", "格安", "激安", "特価", "最安値", "割安", "お得",
    "コスパ", "セール価格", "キャンペーン価格",
    "購入", "買う", "買いたい", "注文", "予約", "予約販売", "発売日",
    "販売開始", "再販", "入手", "手に入れる", "契約", "申し込み",
    "お取り寄せ", "発注",
    "在庫", "在庫あり", "在庫なし", "在庫確認",
    "入荷", "入荷予定", "再入荷",
    "即納", "即日発送", "当日発送",
    "納期", "お届け", "配送", "発送", "到着", "いつ届く",
    "セール", "タイムセール", "初売り", "福袋", "限定セール",
    "数量限定", "初回限定", "期間限定",
    "特典付き", "クーポン", "クーポンコード",
    "ポイント還元", "ポイントアップ", "キャッシュバック",
    "キャンペーン", "ノベルティ", "おまけ付き",
    "公式サイト", "正規", "正規品", "正規代理店", "直販",
    "販売店", "取扱店", "取り扱い", "店舗", "実店舗",
    "どこで買える", "どこで売ってる", "販売先",
    "公式ショップ", "ショップ限定", "アウトレット",
    "純正", "本物", "偽物",
    "新品", "中古", "リユース", "リサイクル", "リファービッシュ", "再生品",
    "型落ち", "旧型", "新型", "新作", "最新モデル",
    "限定モデル", "特別仕様", "限定カラー",
    "支払い方法", "分割払い", "月額", "月々", "一括払い",
    "分割手数料", "無金利",
    "クレジット対応", "代引き", "後払い",
    "サブスク", "定期購入", "定期便",
    "Amazon限定", "Amazonベーシック",
    "プライム限定", "プライムデー",
    "ブラックフライデー", "サイバーマンデー",
    "タイムセール祭り", "初売りセール", "ポイント祭り",
    "通販", "ネット通販", "オンライン購入", "ネット購入",
    "宅配", "送料無料",
    "レビュー", "口コミ", "評判", "評価",
    "感想", "経験談", "実際どう", "実際に使ってみた",
    "体験談", "本音", "ユーザーの声", "利用者の声",
    "使用感", "比較", "違い",
    "おすすめ", "ランキング", "人気",
    "満足度", "採点", "どっちがいい",
    "au", "docomo", "softbank", "rakuten", "ahamo", "linemo",
    "uq", "ymobile", "amazon", "sim", "case", "qi", "qi2",
    "magsafe", "usb", "pencil", "charger", "ケーブル", "cable",
)

KNOW_HINT_KEYWORDS = (
    "やめとけ", "買うな", "やめたほうがいい",
    "使えない", "付いてない",
    "不具合", "故障しやすい", "壊れやすい",
    "返品", "失敗した", "後悔",
    "最悪", "ダメ", "微妙",
    "デメリット", "不便", "不満",
    "注意点", "問題点", "良くない",
    "気をつけろ", "向いてない", "いらない",
)

DO_KEYWORDS = (
    "ログイン", "登録", "ダウンロード", "インストール", "解約", "計算", "変換",
    "アクセス", "地図", "やり方", "アップデート", "update", "設定",
    "修理", "交換", "再起動", "電源off", "引き継ぎ",
)

TABLE_ROW_SELECTOR = "tr:has(td.SuggestKeywordsTableDataRow_keywordTableDataCell__lC3Aj)"
KEYWORD_CELL_SELECTOR = "td.SuggestKeywordsTableDataRow_keywordTableDataCell__lC3Aj"
ACTIVE_PAGE_SELECTOR = "ul.pagination li.page.active a"
NEXT_PAGE_SELECTOR = "ul.pagination li.next a"
NEXT_BUTTON_SELECTOR = "button.SuggestKeywordsTablePagination_nextPageButton__qfvrR"
DEFAULT_MODE = "google"
DEFAULT_SOURCE = "rakkokeyword"

KUBUN_MAP = {
    "＋": "大",
    "＋＋": "中",
    "α": "小",
    "＋α": "小",
    "＋＋＋": "極小",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_ROW = ["キーワード", "検索ボリューム", "クエリタイプ", "状況"]
EXCLUDE_STATUS = {"不要"}
PARTICLE_PREFIXES = ("の ", "を ", "に ", "で ", "は ", "が ", "と ")


@dataclass(slots=True)
class SuggestKeywordRecord:
    seed_keyword: str
    suggest_keyword: str
    volume_label: str
    query_type: str
    article_candidate: bool
    article_status: str
    source: str
    mode: str
    page: int | None
    fetched_at: str
    original_volume_label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower()


def classify_intent(keyword: str) -> str:
    normalized = _normalize_for_match(keyword)
    if any(token.lower() in normalized for token in BUY_KEYWORDS):
        return INTENT_BUY
    if any(token.lower() in normalized for token in DO_KEYWORDS):
        return INTENT_DO
    if any(token.lower() in normalized for token in KNOW_HINT_KEYWORDS):
        return INTENT_KNOW
    return INTENT_KNOW


def should_mark_article_candidate(query_type: str, volume_label: str) -> bool:
    return query_type == INTENT_BUY and volume_label in {"大", "中"}


def article_status_label(query_type: str, volume_label: str) -> str:
    _ = query_type
    _ = volume_label
    return ""


def make_intent_sort_key(
    query_type: str,
    volume_label: str,
    suggest_keyword: str = "",
    article_candidate: bool | None = None,
) -> tuple[int, int, int, str]:
    _ = article_candidate
    return (
        PRIORITY_BUCKET_ORDER.get((query_type, volume_label), 99),
        VOLUME_ORDER.get(volume_label, 99),
        INTENT_ORDER.get(query_type, 99),
        _normalize_for_match(suggest_keyword),
    )


def normalize_keyword_text(text: str, lower: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower() if lower else normalized


def normalize_seed_keyword_input(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u3000", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def build_keyword_key(text: str) -> str:
    return normalize_keyword_text(text, lower=True)


def extract_keyword_suffix(seed_keyword: str, suggest_keyword: str) -> str:
    seed = normalize_seed_keyword_input(seed_keyword)
    suggest = normalize_keyword_text(suggest_keyword)
    if not seed:
        return suggest
    if suggest.casefold().startswith(seed.casefold()):
        suffix = suggest[len(seed):].strip(" 　-ー_")
        return suffix or suggest
    return suggest


def _coerce_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_rank(record: Mapping[str, Any]) -> tuple[int, int, int, int]:
    page = _coerce_int(record.get("page"))
    volume = str(record.get("volume_label", ""))
    return (
        0 if record.get("article_candidate") else 1,
        0 if volume == "大" else 1 if volume == "中" else 2,
        page if page is not None else 99999,
        0,
    )


def normalize_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in records:
        suggest_keyword = normalize_keyword_text(
            str(raw.get("suggest_keyword") or raw.get("keyword") or "")
        )
        if not suggest_keyword:
            continue

        seed_keyword = normalize_seed_keyword_input(str(raw.get("seed_keyword") or ""))
        volume_label = normalize_keyword_text(
            str(raw.get("volume_label") or raw.get("search_volume_label") or raw.get("kubun") or "")
        )
        query_type = str(raw.get("query_type") or "").strip() or classify_intent(suggest_keyword)
        article_candidate = bool(raw.get("article_candidate"))
        if not article_candidate:
            article_candidate = should_mark_article_candidate(query_type, volume_label)

        normalized = {
            **dict(raw),
            "seed_keyword": seed_keyword,
            "suggest_keyword": suggest_keyword,
            "volume_label": volume_label,
            "query_type": query_type,
            "article_candidate": article_candidate,
            "article_status": article_status_label(query_type, volume_label),
            "normalized_seed_keyword": build_keyword_key(seed_keyword),
            "normalized_keyword": build_keyword_key(suggest_keyword),
            "suffix": extract_keyword_suffix(seed_keyword, suggest_keyword),
            "pages": [],
        }

        page = _coerce_int(raw.get("page"))
        if page is not None:
            normalized["pages"] = [page]

        key = str(normalized["normalized_keyword"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = normalized
            continue

        existing_pages = set(existing.get("pages", []))
        existing_pages.update(normalized.get("pages", []))
        winner = normalized if _record_rank(normalized) < _record_rank(existing) else existing
        winner["pages"] = sorted(existing_pages)
        winner["sources"] = sorted(
            {
                str(existing.get("source", DEFAULT_SOURCE)),
                str(normalized.get("source", DEFAULT_SOURCE)),
            }
        )
        merged[key] = winner

    normalized_records = list(merged.values())
    normalized_records.sort(
        key=lambda record: make_intent_sort_key(
            query_type=str(record.get("query_type", "")),
            volume_label=str(record.get("volume_label", "")),
            suggest_keyword=str(record.get("suggest_keyword", "")),
            article_candidate=bool(record.get("article_candidate")),
        )
    )
    return normalized_records


def group_records_by_intent(records: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"Buy": [], "Do": [], "Know": []}
    for record in normalize_records(records):
        grouped.setdefault(str(record["query_type"]), []).append(record)
    return grouped


def build_search_url(seed_keyword: str, mode: str = DEFAULT_MODE) -> str:
    encoded_keyword = quote_plus(normalize_seed_keyword_input(seed_keyword))
    return f"https://rakkokeyword.com/result/suggestKeywords?q={encoded_keyword}&mode={mode}"


def _get_active_page_number(page: Page) -> int | None:
    active_page = page.locator(ACTIVE_PAGE_SELECTOR)
    if active_page.count() == 0:
        return 1
    text = active_page.first.inner_text().strip()
    return int(text) if text.isdigit() else None


def _resolve_next_control(page: Page) -> Locator | None:
    paged_next = page.locator(NEXT_PAGE_SELECTOR)
    if paged_next.count() > 0 and paged_next.first.get_attribute("aria-disabled") != "true":
        return paged_next.first
    next_button = page.locator(NEXT_BUTTON_SELECTOR)
    if next_button.count() > 0 and next_button.first.is_enabled():
        return next_button.first
    return None


def _save_debug_artifacts(page: Page, debug_dir: str | None, name_prefix: str) -> None:
    if not debug_dir:
        return
    target_dir = Path(debug_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    screenshot_path = target_dir / f"{name_prefix}_{timestamp}.png"
    html_path = target_dir / f"{name_prefix}_{timestamp}.html"
    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content(), encoding="utf-8")


def _parse_current_page(
    page: Page,
    seed_keyword: str,
    mode: str,
    fetched_at: str,
) -> list[SuggestKeywordRecord]:
    rows = page.locator(TABLE_ROW_SELECTOR)
    active_page = _get_active_page_number(page)
    results: list[SuggestKeywordRecord] = []
    for index in range(rows.count()):
        row = rows.nth(index)
        keyword_cell = row.locator(KEYWORD_CELL_SELECTOR)
        cells = row.locator("td")
        if keyword_cell.count() == 0 or cells.count() < 3:
            continue

        suggest_keyword = keyword_cell.first.inner_text().strip()
        original_volume_label = cells.nth(2).inner_text().strip()
        if not suggest_keyword:
            continue

        volume_label = KUBUN_MAP.get(original_volume_label, original_volume_label)
        query_type = classify_intent(suggest_keyword)
        article_candidate = should_mark_article_candidate(query_type, volume_label)
        results.append(
            SuggestKeywordRecord(
                seed_keyword=seed_keyword,
                suggest_keyword=suggest_keyword,
                volume_label=volume_label,
                query_type=query_type,
                article_candidate=article_candidate,
                article_status=article_status_label(query_type, volume_label),
                source=DEFAULT_SOURCE,
                mode=mode,
                page=active_page,
                fetched_at=fetched_at,
                original_volume_label=original_volume_label,
            )
        )
    return results


def collect_suggest_keywords(
    seed_keyword: str,
    mode: str = DEFAULT_MODE,
    headless: bool = True,
    timeout_ms: int = 45000,
    wait_after_click_ms: int = 350,
    debug_dir: str | None = None,
) -> list[dict[str, object]]:
    seed_keyword = normalize_seed_keyword_input(seed_keyword)
    fetched_at = datetime.now(timezone.utc).isoformat()
    collected: list[SuggestKeywordRecord] = []
    search_url = build_search_url(seed_keyword, mode)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(KEYWORD_CELL_SELECTOR, timeout=timeout_ms)
            while True:
                current_page_number = _get_active_page_number(page)
                collected.extend(_parse_current_page(page, seed_keyword, mode, fetched_at))

                next_control = _resolve_next_control(page)
                if next_control is None:
                    break

                next_control.click()
                page.wait_for_timeout(wait_after_click_ms)
                deadline = time.time() + (timeout_ms / 1000)
                while time.time() < deadline:
                    new_page_number = _get_active_page_number(page)
                    if (
                        current_page_number is not None
                        and new_page_number is not None
                        and new_page_number != current_page_number
                    ):
                        break
                    page.wait_for_timeout(200)
                else:
                    raise TimeoutError("ラッコキーワードのページ切り替えがタイムアウトしました。")
                page.wait_for_selector(KEYWORD_CELL_SELECTOR, timeout=timeout_ms)
        except Exception:
            _save_debug_artifacts(page, debug_dir, "rakko_suggest_error")
            raise
        finally:
            browser.close()

    records = [record.to_dict() for record in collected]
    records.sort(
        key=lambda record: make_intent_sort_key(
            query_type=str(record["query_type"]),
            volume_label=str(record["volume_label"]),
            suggest_keyword=str(record["suggest_keyword"]),
            article_candidate=bool(record["article_candidate"]),
        )
    )
    return records


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
    normalized = normalize_seed_keyword_input(title)
    normalized = re.sub(r"[\[\]\:\*\?/\\]", " ", normalized)
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
    "KUBUN_MAP",
    "SuggestKeywordRecord",
    "article_status_label",
    "build_keyword_key",
    "build_search_url",
    "classify_intent",
    "collect_suggest_keywords",
    "extract_keyword_suffix",
    "group_records_by_intent",
    "load_keyword_records_from_sheet",
    "make_intent_sort_key",
    "normalize_keyword_text",
    "normalize_records",
    "select_keyword_records_for_generation",
    "should_mark_article_candidate",
    "write_keyword_records_to_sheet",
]
