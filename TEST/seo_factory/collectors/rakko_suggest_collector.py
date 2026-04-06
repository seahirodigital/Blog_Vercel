"""ラッコキーワードのサジェスト取得器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from urllib.parse import quote_plus

from playwright.sync_api import Locator, Page, sync_playwright

try:
    from ..analyzers.keyword_intent_classifier import (
        article_status_label,
        classify_intent,
        make_intent_sort_key,
        should_mark_article_candidate,
    )
except ImportError:  # pragma: no cover
    from analyzers.keyword_intent_classifier import (  # type: ignore
        article_status_label,
        classify_intent,
        make_intent_sort_key,
        should_mark_article_candidate,
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


def build_search_url(seed_keyword: str, mode: str = DEFAULT_MODE) -> str:
    encoded_keyword = quote_plus(seed_keyword)
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
    """Playwright でラッコキーワードを全ページ取得する。"""
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


__all__ = [
    "KUBUN_MAP",
    "SuggestKeywordRecord",
    "build_search_url",
    "collect_suggest_keywords",
]
