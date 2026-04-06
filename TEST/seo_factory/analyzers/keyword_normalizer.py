"""サジェストキーワードの正規化と重複除去。"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

try:
    from .keyword_intent_classifier import (
        article_status_label,
        classify_intent,
        make_intent_sort_key,
        should_mark_article_candidate,
    )
except ImportError:  # pragma: no cover
    from keyword_intent_classifier import (  # type: ignore
        article_status_label,
        classify_intent,
        make_intent_sort_key,
        should_mark_article_candidate,
    )


def normalize_keyword_text(text: str, lower: bool = False) -> str:
    """全角半角・空白ゆれを抑えて扱いやすくする。"""
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower() if lower else normalized


def build_keyword_key(text: str) -> str:
    return normalize_keyword_text(text, lower=True)


def extract_keyword_suffix(seed_keyword: str, suggest_keyword: str) -> str:
    """`seed + suffix` 形式なら suffix を返し、難しい場合は suggest 全体を返す。"""
    seed = normalize_keyword_text(seed_keyword)
    suggest = normalize_keyword_text(suggest_keyword)

    if not seed:
        return suggest

    seed_folded = seed.casefold()
    suggest_folded = suggest.casefold()
    if suggest_folded.startswith(seed_folded):
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
    return (
        0 if record.get("article_candidate") else 1,
        0 if record.get("volume_label") == "大" else 1 if record.get("volume_label") == "中" else 2,
        page if page is not None else 99999,
        0,
    )


def normalize_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """正規化しながら重複を潰し、分類と並び順も安定させる。"""
    merged: dict[str, dict[str, Any]] = {}

    for raw in records:
        suggest_keyword = normalize_keyword_text(
            str(raw.get("suggest_keyword") or raw.get("keyword") or "")
        )
        if not suggest_keyword:
            continue

        seed_keyword = normalize_keyword_text(str(raw.get("seed_keyword") or ""))
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

        key = normalized["normalized_keyword"]
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
                str(existing.get("source", "rakkokeyword")),
                str(normalized.get("source", "rakkokeyword")),
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

