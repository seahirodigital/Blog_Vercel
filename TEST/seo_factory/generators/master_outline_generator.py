"""サジェスト群から母艦記事の見出し案を生成する。"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from typing import Any

try:
    from ..analyzers.keyword_intent_classifier import make_intent_sort_key
    from ..analyzers.keyword_normalizer import extract_keyword_suffix, normalize_records
except ImportError:  # pragma: no cover
    from analyzers.keyword_intent_classifier import make_intent_sort_key  # type: ignore
    from analyzers.keyword_normalizer import extract_keyword_suffix, normalize_records  # type: ignore

BASE_SECTION_ORDER = [
    "conclusion",
    "selection_criteria",
    "use_cases",
    "comparison",
    "merits",
    "demerits",
    "faq",
    "reputation",
    "summary",
]

SECTION_TITLES = {
    "conclusion": "結論",
    "selection_criteria": "選定基準",
    "use_cases": "利用シーン",
    "comparison": "比較",
    "merits": "メリット",
    "demerits": "デメリット",
    "faq": "FAQ",
    "reputation": "評判",
    "summary": "まとめ",
}

SECTION_RULES = {
    "reputation": ("評判", "口コミ", "レビュー", "評価", "感想", "使用感", "体験談", "本音"),
    "comparison": ("比較", "違い", "どっちがいい", "どっち", "vs", "型落ち", "旧型", "新型"),
    "demerits": ("後悔", "やめとけ", "買うな", "デメリット", "不便", "不満", "最悪", "微妙", "注意点", "問題点", "向いてない", "いらない", "発熱", "壊れやすい", "不具合"),
    "selection_criteria": ("価格", "値段", "料金", "金額", "費用", "相場", "コスパ", "サイズ", "重さ", "スペック", "性能", "バッテリー", "カメラ", "充電", "usb", "magsafe", "qi", "qi2", "sim", "case", "pencil", "charger", "ケーブル", "cable"),
    "use_cases": ("仕事", "ビジネス", "通勤", "通学", "動画", "ゲーム", "旅行", "撮影", "学生", "クリエイター", "家族"),
    "faq": ("いつ", "どこ", "どう", "なぜ", "設定", "使い方", "ログイン", "登録", "ダウンロード", "インストール", "解約", "修理", "交換", "引き継ぎ", "再起動"),
    "merits": ("おすすめ", "人気", "満足度", "便利", "快適", "お得", "ランキング"),
    "conclusion": ("買う", "購入", "おすすめ", "人気", "どっち", "比較", "評判", "レビュー"),
}

PRIORITY_BUCKET_LABELS = [
    ("Buy", "大", "最優先の購入判断"),
    ("Know", "大", "最優先の疑問解消"),
    ("Buy", "中", "比較前に確認する購入判断"),
    ("Know", "中", "比較前に潰す疑問"),
    ("Buy", "小", "補助的な購入論点"),
]


def _is_previous_model_record(record: Mapping[str, Any]) -> bool:
    source_scope = str(record.get("source_scope", "")).strip().lower()
    if source_scope == "previous":
        return True
    model_generation = str(record.get("model_generation", "")).strip().lower()
    return model_generation == "previous"


def _assign_section(record: Mapping[str, Any]) -> str:
    suggest_keyword = str(record.get("suggest_keyword", ""))
    suffix = extract_keyword_suffix(str(record.get("seed_keyword", "")), suggest_keyword).lower()
    lowered = f"{suggest_keyword.lower()} {suffix}".strip()

    for section_id in ("reputation", "comparison", "demerits", "selection_criteria", "use_cases", "faq", "merits", "conclusion"):
        if any(token.lower() in lowered for token in SECTION_RULES[section_id]):
            return section_id

    query_type = str(record.get("query_type", "Know"))
    if query_type == "Do":
        return "faq"
    if query_type == "Buy":
        return "selection_criteria"
    return "conclusion"


def _base_section_heading(seed_keyword: str, section_id: str) -> str:
    return f"{seed_keyword}レビュー比較まとめ：{SECTION_TITLES[section_id]}"


def _make_subheading(seed_keyword: str, suggest_keyword: str) -> str:
    suffix = extract_keyword_suffix(seed_keyword, suggest_keyword)
    if suffix == suggest_keyword:
        return suggest_keyword
    return f"{seed_keyword} {suffix}".strip()


def _build_section_topic_entries(
    seed_keyword: str,
    records: list[dict[str, Any]],
    max_topics_per_section: int,
) -> list[dict[str, Any]]:
    parent_candidates = []
    for index, record in enumerate(records):
        if str(record.get("volume_label", "")) == "大":
            parent_candidates.append(
                {
                    "index": index,
                    "record": record,
                    "suffix": extract_keyword_suffix(seed_keyword, str(record.get("suggest_keyword", ""))),
                }
            )

    child_parent_map: dict[int, int] = {}
    for index, record in enumerate(records):
        child_suffix = extract_keyword_suffix(seed_keyword, str(record.get("suggest_keyword", "")))
        child_query = str(record.get("query_type", ""))
        child_volume = str(record.get("volume_label", ""))
        if child_volume == "大":
            continue

        matched_parent_index: int | None = None
        matched_parent_length = -1
        for parent in parent_candidates:
            parent_suffix = str(parent["suffix"])
            parent_record = parent["record"]
            if str(parent_record.get("query_type", "")) != child_query:
                continue
            if child_suffix == parent_suffix:
                continue
            if child_suffix.startswith(parent_suffix) and len(parent_suffix) > matched_parent_length:
                matched_parent_index = int(parent["index"])
                matched_parent_length = len(parent_suffix)

        if matched_parent_index is not None:
            child_parent_map[index] = matched_parent_index

    entries: list[dict[str, Any]] = []
    seen_root_indices: set[int] = set()
    for index, record in enumerate(records):
        if index in child_parent_map:
            continue
        seen_root_indices.add(index)
        child_topics = []
        for child_index, parent_index in child_parent_map.items():
            if parent_index != index:
                continue
            child_record = records[child_index]
            child_topics.append(
                {
                    "heading": _make_subheading(seed_keyword, str(child_record["suggest_keyword"])),
                    "suggest_keyword": str(child_record["suggest_keyword"]),
                    "query_type": str(child_record["query_type"]),
                    "volume_label": str(child_record["volume_label"]),
                    "article_candidate": bool(child_record["article_candidate"]),
                    "source_scope": "前作継承" if _is_previous_model_record(child_record) else "現行需要",
                }
            )

        entries.append(
            {
                "heading": _make_subheading(seed_keyword, str(record["suggest_keyword"])),
                "suggest_keyword": str(record["suggest_keyword"]),
                "query_type": str(record["query_type"]),
                "volume_label": str(record["volume_label"]),
                "article_candidate": bool(record["article_candidate"]),
                "source_scope": "前作継承" if _is_previous_model_record(record) else "現行需要",
                "child_h2_topics": child_topics,
            }
        )

    return entries[:max_topics_per_section]


def _sort_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_records = [dict(record) for record in records]
    sorted_records.sort(
        key=lambda record: make_intent_sort_key(
            query_type=str(record.get("query_type", "")),
            volume_label=str(record.get("volume_label", "")),
            suggest_keyword=str(record.get("suggest_keyword", "")),
            article_candidate=bool(record.get("article_candidate")),
        )
    )
    return sorted_records


def _build_priority_groups(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    sorted_records = _sort_records(records)
    for query_type, volume_label, label in PRIORITY_BUCKET_LABELS:
        keywords = [
            str(record.get("suggest_keyword", ""))
            for record in sorted_records
            if str(record.get("query_type", "")) == query_type
            and str(record.get("volume_label", "")) == volume_label
        ]
        if not keywords:
            continue
        groups.append(
            {
                "label": label,
                "query_type": query_type,
                "volume_label": volume_label,
                "keywords": keywords,
            }
        )
    return groups


def generate_master_outline(
    seed_keyword: str,
    current_records: Iterable[Mapping[str, Any]],
    previous_records: Iterable[Mapping[str, Any]] | None = None,
    max_subsections_per_section: int = 6,
) -> dict[str, Any]:
    """サジェスト群から、03の骨格を活かした母艦記事用アウトラインを作る。"""
    normalized_current = _sort_records(normalize_records(current_records))
    normalized_previous = _sort_records(normalize_records(previous_records or []))

    for record in normalized_current:
        record["source_scope"] = "current"
    for record in normalized_previous:
        record["source_scope"] = "previous"

    all_records = _sort_records(normalized_current + normalized_previous)
    grouped: dict[str, list[dict[str, Any]]] = {section_id: [] for section_id in BASE_SECTION_ORDER}

    for record in all_records:
        section_id = _assign_section(record)
        grouped[section_id].append(record)

    sections: list[dict[str, Any]] = []
    for section_id in BASE_SECTION_ORDER:
        bucket = grouped.get(section_id, [])
        seen_keywords: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for record in bucket:
            keyword = str(record["suggest_keyword"])
            if keyword not in seen_keywords:
                seen_keywords[keyword] = record

        topic_entries = _build_section_topic_entries(
            seed_keyword=seed_keyword,
            records=list(seen_keywords.values()),
            max_topics_per_section=max_subsections_per_section,
        )

        sections.append(
            {
                "id": section_id,
                "heading": _base_section_heading(seed_keyword, section_id),
                "subsections": topic_entries,
                "supporting_keywords": [
                    keyword
                    for entry in topic_entries
                    for keyword in [entry["suggest_keyword"], *[child["suggest_keyword"] for child in entry.get("child_h2_topics", [])]]
                ],
            }
        )

    summary_keywords = [str(record["suggest_keyword"]) for record in all_records[:10]]

    return {
        "seed_keyword": seed_keyword,
        "title": f"{seed_keyword} レビュー比較まとめ",
        "summary_focus_keywords": summary_keywords,
        "current_keyword_count": len(normalized_current),
        "previous_keyword_count": len(normalized_previous),
        "priority_groups": _build_priority_groups(all_records),
        "sections": sections,
    }


def render_markdown_outline(outline: Mapping[str, Any]) -> str:
    """生成したアウトラインを Markdown に整形する。"""
    lines = [
        f"# {outline['title']}",
        "",
        "## 母艦記事の設計メモ",
        "",
        f"- 現行サジェスト件数: {outline['current_keyword_count']}",
        f"- 前作サジェスト件数: {outline['previous_keyword_count']}",
        f"- 優先論点: {', '.join(outline.get('summary_focus_keywords', [])) or 'なし'}",
        "",
    ]

    priority_groups = outline.get("priority_groups", [])
    if priority_groups:
        lines.extend(
            [
                "## ユーザー需要順の主要論点",
                "",
                "優先順は `Buy大 → Know大 → Buy中 → Know中 → Buy小` を基本とする。",
                "",
            ]
        )
        for group in priority_groups:
            lines.append(f"### {group['label']}")
            lines.append("")
            lines.append(f"- クエリタイプ: {group['query_type']}")
            lines.append(f"- 検索ボリューム: {group['volume_label']}")
            lines.append(f"- 対応キーワード: {', '.join(group['keywords'])}")
            lines.append("")

    for section in outline["sections"]:
        lines.append(f"## {section['heading']}")
        lines.append("")
        if section["supporting_keywords"]:
            lines.append(f"- 対応サジェスト: {', '.join(section['supporting_keywords'])}")
            lines.append("")
        for subsection in section["subsections"]:
            lines.append(f"## {subsection['heading']}")
            lines.append("")
            lines.append(f"- 対応サジェスト: {subsection['suggest_keyword']}")
            lines.append(f"- クエリタイプ: {subsection['query_type']}")
            lines.append(f"- 区分: {subsection['volume_label']}")
            lines.append(f"- 需要ソース: {subsection['source_scope']}")
            lines.append("")
            for child_topic in subsection.get("child_h2_topics", []):
                lines.append(f"## {child_topic['heading']}")
                lines.append("")
                lines.append(f"- 対応サジェスト: {child_topic['suggest_keyword']}")
                lines.append(f"- クエリタイプ: {child_topic['query_type']}")
                lines.append(f"- 区分: {child_topic['volume_label']}")
                lines.append(f"- 需要ソース: {child_topic['source_scope']}")
                lines.append("")

    return "\n".join(lines).strip() + "\n"


__all__ = [
    "generate_master_outline",
    "render_markdown_outline",
]
