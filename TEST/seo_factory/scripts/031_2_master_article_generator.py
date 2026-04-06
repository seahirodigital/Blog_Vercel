"""031_2 母艦記事生成器。

見出し設計と母艦記事生成を1ファイルへ統合する。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Mapping

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]

DEFAULT_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

PIPELINE_MODULE_PATH = Path(__file__).parent / "031_1_keyword_pipeline.py"


def _load_keyword_pipeline_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "seo_factory_031_1_keyword_pipeline",
        PIPELINE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"前処理モジュールを読み込めません: {PIPELINE_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_KEYWORD_PIPELINE = _load_keyword_pipeline_module()
extract_keyword_suffix = _KEYWORD_PIPELINE.extract_keyword_suffix
make_intent_sort_key = _KEYWORD_PIPELINE.make_intent_sort_key
normalize_records = _KEYWORD_PIPELINE.normalize_records

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
    "demerits": (
        "後悔", "やめとけ", "買うな", "デメリット", "不便", "不満", "最悪", "微妙",
        "注意点", "問題点", "向いてない", "いらない", "発熱", "壊れやすい", "不具合",
    ),
    "selection_criteria": (
        "価格", "値段", "料金", "金額", "費用", "相場", "コスパ", "サイズ", "重さ",
        "スペック", "性能", "バッテリー", "カメラ", "充電", "usb", "magsafe", "qi",
        "qi2", "sim", "case", "pencil", "charger", "ケーブル", "cable",
    ),
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


SECTION_OPENERS = {
    "conclusion": "先に大枠の結論を置き、判断を急ぐ論点から順に答える。",
    "selection_criteria": "購入判断に必要な比較軸を先に固定し、迷いを減らす。",
    "use_cases": "利用場面ごとの差を具体化し、選び方を詰める。",
    "comparison": "比較されやすい相手や旧モデルとの違いを先に整理する。",
    "merits": "選ばれやすい理由を短く整理し、判断材料を明確化する。",
    "demerits": "不安や後悔につながる要素を先に可視化する。",
    "faq": "検索されやすい具体疑問へ短く先回りする。",
    "reputation": "評判と口コミから判断を左右する要素を拾う。",
    "summary": "最後に優先論点を再整理し、次の判断へつなげる。",
}


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
    for section_id in (
        "reputation",
        "comparison",
        "demerits",
        "selection_criteria",
        "use_cases",
        "faq",
        "merits",
        "conclusion",
    ):
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
    for index, record in enumerate(records):
        if index in child_parent_map:
            continue
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
                    for keyword in [
                        entry["suggest_keyword"],
                        *[child["suggest_keyword"] for child in entry.get("child_h2_topics", [])],
                    ]
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


def _load_prompt(filename: str, prompt_dir: Path | None = None) -> str:
    directory = prompt_dir or PROMPTS_DIR
    filepath = directory / filename
    if not filepath.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {filepath}")
    return filepath.read_text(encoding="utf-8").strip()


def _run_generation(
    client: Any,
    input_text: str,
    system_prompt: str,
    model_name: str = DEFAULT_MODEL_NAME,
) -> str:
    full_input = f"【指示・行動指針】\n{system_prompt}\n\n【処理対象データ】\n{input_text}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=full_input,
            )
            return str(getattr(response, "text", "") or "").strip()
        except Exception as exc:
            if "429" in str(exc):
                wait_time = (attempt + 1) * 30
                time.sleep(wait_time)
                continue
            raise

    raise RuntimeError("Gemini の最大リトライ回数を超えました。")


def _slugify(text: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", " ", str(text or ""))
    normalized = re.sub(r"\s+", "_", normalized).strip(" _")
    return normalized or "seed_keyword"


def _collect_focus_keywords(records: list[Mapping[str, Any]], limit: int = 12) -> list[str]:
    return [str(record["suggest_keyword"]) for record in records[:limit]]


def _shorten_phrase(text: str, limit: int = 20) -> str:
    compact = re.sub(r"\s+", "", str(text or ""))
    return compact[:limit] if compact else "要点整理"


def _make_problem_text(heading: str, suggest_keyword: str) -> str:
    return f"{heading} の判断軸が曖昧で、{suggest_keyword} の答えが見えにくい状態"


def _make_solution_text(query_type: str, source_scope: str) -> str:
    if query_type == "Buy":
        base = "購入判断軸を固定し、価格・比較・選び方を順に確認する方法"
    elif query_type == "Do":
        base = "必要な手順を分解し、確認順を短く揃える方法"
    else:
        base = "疑問を先回りで整理し、判断前の不安を先に潰す方法"

    if source_scope == "前作継承":
        return f"{base}。前作で残った疑問も同時に回収する。"
    return f"{base}。"


def _build_point_lines(subsection: Mapping[str, Any]) -> list[str]:
    query_type = str(subsection.get("query_type", "Know"))
    volume_label = str(subsection.get("volume_label", ""))
    heading = _shorten_phrase(str(subsection.get("heading", "")))
    suggest_keyword = _shorten_phrase(str(subsection.get("suggest_keyword", "")))

    if query_type == "Buy":
        action = "方法：条件比較"
    elif query_type == "Do":
        action = "方法：手順分解"
    else:
        action = "方法：論点先回収"

    return [
        f"- 結論：{heading}",
        f"- 課題：{suggest_keyword}",
        action,
        f"- 優先：{_shorten_phrase(f'{query_type}{volume_label}')}",
    ]


def _build_explanation(seed_keyword: str, suggest_keyword: str, source_scope: str) -> str:
    explanation = (
        f"{suggest_keyword} という検索は、{seed_keyword} でどこを先に確認したいかを示す。"
        "結論を先に置き、比較や確認方法を短く足すと読みやすい。"
    )
    if source_scope == "前作継承":
        explanation += " 前作で残った疑問の継承も前提にする。"
    return explanation


def _append_heading_block(
    lines: list[str],
    heading_level: str,
    heading_text: str,
    problem_text: str,
    solution_text: str,
    explanation_text: str,
    point_lines: list[str],
    closing_text: str,
) -> None:
    lines.append(f"{heading_level} {heading_text}")
    lines.append("")
    lines.append(explanation_text)
    lines.append("")
    lines.extend(point_lines)
    lines.append("")
    lines.append(closing_text)
    lines.append("")


def _normalize_heading_levels(article_markdown: str) -> str:
    normalized_lines: list[str] = []
    for line in str(article_markdown or "").splitlines():
        if line.startswith("### "):
            normalized_lines.append(f"## {line[4:].strip()}")
        elif line.startswith("#### "):
            normalized_lines.append(f"## {line[5:].strip()}")
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines).strip() + "\n"


def _reduce_records_for_llm(
    records: list[Mapping[str, Any]],
    max_priority: int = 120,
    max_secondary: int = 40,
) -> list[dict[str, Any]]:
    """LLMへ渡すレコード数を現実的な範囲に圧縮する。"""
    priority: list[Mapping[str, Any]] = []
    secondary: list[Mapping[str, Any]] = []

    for record in records:
        if bool(record.get("article_candidate")) or str(record.get("volume_label")) in {"大", "中"}:
            priority.append(record)
        else:
            secondary.append(record)

    selected = list(priority[:max_priority]) + list(secondary[:max_secondary])
    reduced: list[dict[str, Any]] = []
    for record in selected:
        reduced.append(
            {
                "suggest_keyword": str(record.get("suggest_keyword", "")),
                "suffix": str(record.get("suffix", "")),
                "volume_label": str(record.get("volume_label", "")),
                "query_type": str(record.get("query_type", "")),
                "article_status": str(record.get("article_status", "")),
                "article_candidate": bool(record.get("article_candidate")),
                "source_scope": str(record.get("source_scope", "")),
            }
        )
    return reduced


def render_base_master_article(
    outline: Mapping[str, Any],
    current_records: list[Mapping[str, Any]],
    previous_records: list[Mapping[str, Any]],
) -> str:
    """LLMに渡す前の 03 相当記事を組み立てる。"""
    seed_keyword = str(outline["seed_keyword"])
    focus_keywords = _collect_focus_keywords(current_records, limit=10)
    previous_keywords = _collect_focus_keywords(previous_records, limit=8)

    lines = [
        f"# {outline['title']}",
        "",
        f"{seed_keyword} を検討するときに迷いやすい主要論点を、購入判断に必要な順で整理する。",
        "",
    ]

    priority_groups = outline.get("priority_groups", [])
    if priority_groups:
        lines.append("## ユーザー需要順の主要論点")
        lines.append("")
        for group in priority_groups:
            group_label = str(group.get("label", "主要論点"))
            keywords = [str(keyword) for keyword in group.get("keywords", [])[:8]]
            _append_heading_block(
                lines=lines,
                heading_level="##",
                heading_text=group_label,
                problem_text=f"{group_label} の確認順が曖昧な状態",
                solution_text="優先バケット単位で論点をまとめて先読みする方法",
                explanation_text="主要キーワードを先に束ねて見ると、あとで本文を読む順番が定まりやすい。",
                point_lines=[
                    f"- 区分：{_shorten_phrase(str(group.get('volume_label', '')))}",
                    f"- 種別：{_shorten_phrase(str(group.get('query_type', '')))}",
                    f"- 論点：{_shorten_phrase(keywords[0] if keywords else '主要論点')}",
                    "- 方法：先頭確認",
                ],
                closing_text=f"主に見ておきたい論点: {', '.join(keywords)}" if keywords else "この区分は優先して確認したい。",
            )

    if focus_keywords:
        lines.extend(
            [
                "## 先に確認したい主要論点",
                "",
                *(f"- {keyword}" for keyword in focus_keywords),
                "",
            ]
        )

    if previous_keywords:
        lines.extend(
            [
                "## 前作から見ておきたい論点",
                "",
                *(f"- {keyword}" for keyword in previous_keywords),
                "",
            ]
        )

    for section in outline["sections"]:
        section_id = str(section["id"])
        _append_heading_block(
            lines=lines,
            heading_level="##",
            heading_text=str(section["heading"]),
            problem_text=f"{section['heading']} に関する判断材料が分散しやすい状態",
            solution_text=SECTION_OPENERS.get(section_id, "主要論点を順に整理する方法"),
            explanation_text="見出し直下で課題と解決策を先に置き、その後に詳細論点を積み上げる。",
            point_lines=[
                f"- 結論：{_shorten_phrase(str(section['heading']))}",
                f"- 課題：{_shorten_phrase(str(section_id))}",
                "- 方法：論点分解",
                "- 目的：判断短縮",
            ],
            closing_text="この章では、見出しごとの疑問へ順番に答えを置いていく。",
        )

        subsections = section.get("subsections", [])
        if not subsections:
            lines.extend(
                [
                    "この章は現時点では土台のみ。後段で不足論点が見つかった場合に補強する。",
                    "",
                ]
            )
            continue

        for subsection in subsections:
            heading = str(subsection["heading"])
            suggest_keyword = str(subsection["suggest_keyword"])
            source_scope = str(subsection["source_scope"])
            explanation = _build_explanation(seed_keyword, suggest_keyword, source_scope)

            _append_heading_block(
                lines=lines,
                heading_level="##",
                heading_text=heading,
                problem_text=_make_problem_text(heading, suggest_keyword),
                solution_text=_make_solution_text(str(subsection.get("query_type", "Know")), source_scope),
                explanation_text=explanation,
                point_lines=_build_point_lines(subsection),
                closing_text="この論点を先に押さえておくと、購入判断や比較がかなりしやすくなる。",
            )

            for child_topic in subsection.get("child_h2_topics", []):
                child_heading = str(child_topic["heading"])
                child_keyword = str(child_topic["suggest_keyword"])
                child_source_scope = str(child_topic["source_scope"])
                _append_heading_block(
                    lines=lines,
                    heading_level="##",
                    heading_text=child_heading,
                    problem_text=_make_problem_text(child_heading, child_keyword),
                    solution_text=_make_solution_text(str(child_topic.get("query_type", "Know")), child_source_scope),
                    explanation_text=_build_explanation(seed_keyword, child_keyword, child_source_scope),
                    point_lines=_build_point_lines(child_topic),
                    closing_text="この論点も独立して確認できるようにしておくと、読み返しやすくなる。",
                )

    return "\n".join(lines).strip() + "\n"


def build_generation_payload(
    seed_keyword: str,
    current_records: list[Mapping[str, Any]],
    previous_records: list[Mapping[str, Any]],
    outline: Mapping[str, Any],
    base_article: str,
    enhancement_plan: str | None = None,
) -> str:
    reduced_current = _reduce_records_for_llm(current_records)
    reduced_previous = _reduce_records_for_llm(previous_records, max_priority=80, max_secondary=20)
    payload = {
        "seed_keyword": seed_keyword,
        "current_suggest_keyword_count": len(current_records),
        "previous_suggest_keyword_count": len(previous_records),
        "current_suggest_keywords": reduced_current,
        "previous_suggest_keywords": reduced_previous,
        "outline_title": outline["title"],
        "priority_groups": outline.get("priority_groups", []),
        "outline_sections": [
            {
                "heading": section["heading"],
                "supporting_keywords": section["supporting_keywords"],
            }
            for section in outline["sections"]
        ],
        "outline_markdown": render_markdown_outline(outline),
        "base_article_markdown": base_article,
    }
    if enhancement_plan:
        payload["enhancement_plan_markdown"] = enhancement_plan
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_master_article(
    seed_keyword: str,
    current_records: list[Mapping[str, Any]],
    previous_records: list[Mapping[str, Any]] | None = None,
    outline: Mapping[str, Any] | None = None,
    gemini_api_key: str | None = None,
    prompt_dir: Path | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    """母艦記事を生成する。"""
    previous_records = list(previous_records or [])
    outline_data = dict(outline or generate_master_outline(seed_keyword, current_records, previous_records))
    base_article = render_base_master_article(outline_data, list(current_records), previous_records)

    result = {
        "seed_keyword": seed_keyword,
        "slug": _slugify(seed_keyword),
        "outline": outline_data,
        "outline_markdown": render_markdown_outline(outline_data),
        "base_article_markdown": base_article,
        "draft_article_markdown": base_article,
        "enhancement_plan_markdown": "",
        "master_article_markdown": "",
        "used_llm": False,
        "is_draft_only": True,
    }

    if not gemini_api_key:
        return result

    best_outline_prompt = _load_prompt("031-1-best-outline-prompt.md", prompt_dir)
    best_enhancer_prompt = _load_prompt("031-2-best-article-enhancer-prompt.md", prompt_dir)
    if genai is None:
        raise RuntimeError("google-genai がインストールされていないため、LLM付き母艦記事生成を実行できません。")

    client = genai.Client(api_key=gemini_api_key)

    analysis_input = build_generation_payload(
        seed_keyword=seed_keyword,
        current_records=list(current_records),
        previous_records=previous_records,
        outline=outline_data,
        base_article=base_article,
    )
    enhancement_plan = _run_generation(
        client=client,
        input_text=analysis_input,
        system_prompt=best_outline_prompt,
        model_name=model_name,
    )

    enhancement_input = build_generation_payload(
        seed_keyword=seed_keyword,
        current_records=list(current_records),
        previous_records=previous_records,
        outline=outline_data,
        base_article=base_article,
        enhancement_plan=enhancement_plan,
    )
    master_article = _run_generation(
        client=client,
        input_text=enhancement_input,
        system_prompt=best_enhancer_prompt,
        model_name=model_name,
    )
    master_article = _normalize_heading_levels(master_article or base_article)

    result["enhancement_plan_markdown"] = enhancement_plan
    result["master_article_markdown"] = master_article
    result["used_llm"] = True
    result["is_draft_only"] = False
    return result


__all__ = [
    "build_generation_payload",
    "generate_master_article",
    "generate_master_outline",
    "render_base_master_article",
    "render_markdown_outline",
]
