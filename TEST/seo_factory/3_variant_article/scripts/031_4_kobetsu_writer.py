"""031_4 個別記事生成器。"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

def _make_h2_prefix(text: str) -> str:
    return f"{str(text or '').strip()}："


def _normalize_h2_prefixes(article_markdown: str, target_keyword: str) -> str:
    prefix = _make_h2_prefix(target_keyword)
    normalized_lines: list[str] = []
    for line in str(article_markdown or "").splitlines():
        if line.startswith("### "):
            line = f"## {line[4:].strip()}"
        elif line.startswith("#### "):
            line = f"## {line[5:].strip()}"
        if line.startswith("## "):
            heading_text = line[3:].strip()
            if not heading_text.startswith(prefix):
                if "：" in heading_text:
                    heading_text = heading_text.split("：", 1)[1].strip()
                normalized_lines.append(f"## {prefix}{heading_text}")
            else:
                normalized_lines.append(line)
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines).strip() + "\n"


def _derive_section_label(seed_keyword: str, heading_text: str) -> str:
    cleaned = str(heading_text or "").strip()
    if "：" in cleaned:
        return cleaned.split("：", 1)[1].strip() or "主要論点"

    seed_pattern = re.escape(str(seed_keyword or "").strip())
    cleaned = re.sub(seed_pattern, "", cleaned, flags=re.IGNORECASE).strip(" ：:-")
    return cleaned or "主要論点"


def _parse_h2_sections(seed_keyword: str, master_article_markdown: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_body
        if current_heading is None:
            return
        sections.append(
            {
                "original_heading": current_heading,
                "section_label": _derive_section_label(seed_keyword, current_heading),
                "body_markdown": "\n".join(current_body).strip(),
            }
        )
        current_heading = None
        current_body = []

    for raw_line in str(master_article_markdown or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            continue
        if current_heading is not None:
            current_body.append(line)

    flush()
    return sections


def _build_template_sections_from_outline(seed_keyword: str, outline: Mapping[str, Any]) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for section in outline.get("sections", []):
        heading = str(section.get("heading", "")).strip()
        if heading:
            sections.append(
                {
                    "original_heading": heading,
                    "section_label": _derive_section_label(seed_keyword, heading),
                    "body_markdown": "",
                }
            )
        for subsection in section.get("subsections", []):
            subheading = str(subsection.get("heading", "")).strip()
            if subheading:
                sections.append(
                    {
                        "original_heading": subheading,
                        "section_label": _derive_section_label(seed_keyword, subheading),
                        "body_markdown": "",
                    }
                )


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _build_kobetsu_section_labels(
    seed_keyword: str,
    target_keyword: str,
    template_sections: list[Mapping[str, str]],
) -> list[str]:
    target_prefix = _make_h2_prefix(target_keyword)
    labels: list[str] = []
    for section in template_sections:
        section_label = str(section.get("section_label", "")).strip()
        if not section_label:
            continue
        labels.append(f"{target_prefix}{section_label}")

    if not labels:
        target_suffix = _derive_section_label(seed_keyword, target_keyword)
        labels = [
            f"{target_prefix}結論",
            f"{target_prefix}{target_suffix or '確認ポイント'}",
            f"{target_prefix}注意点",
            f"{target_prefix}まとめ",
        ]
    return _dedupe_preserve_order(labels)


def _find_matching_topic(
    target_keyword: str,
    master_research_bundle: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    bundle = master_research_bundle or {}
    topics = bundle.get("topics", [])
    target_lower = str(target_keyword or "").strip().lower()

    for topic in topics:
        if str(topic.get("primary_keyword", "")).strip().lower() == target_lower:
            return topic

    for topic in topics:
        related_keywords = [str(keyword).strip().lower() for keyword in topic.get("related_keywords", [])]
        if target_lower in related_keywords:
            return topic

    return {}


def build_kobetsu_job(
    seed_keyword: str,
    target_keyword: str,
    volume_label: str,
    query_type: str,
    outline: Mapping[str, Any],
    master_research_bundle: Mapping[str, Any] | None = None,
    master_article_markdown: str = "",
) -> dict[str, Any]:
    template_sections = _parse_h2_sections(seed_keyword, master_article_markdown)
    if not template_sections:
        template_sections = _build_template_sections_from_outline(seed_keyword, outline)
    matched_topic = _find_matching_topic(target_keyword, master_research_bundle)
    required_h2 = _build_kobetsu_section_labels(seed_keyword, target_keyword, template_sections)

    opening_focus = str(matched_topic.get("opening_focus", "")).strip() or "対象キーワードへの結論を最初の一文で答える"
    research_questions = list(matched_topic.get("research_questions", [])) or [
        "このキーワードで読者が最初に知りたい結論は何か",
        "比較や判断に必要な事実は何か",
        "一般論ではなく固有の確認事項は何か",
    ]
    source_checkpoints = list(matched_topic.get("source_checkpoints", [])) or [
        "公式製品ページで仕様と正式名称を確認",
        "信頼できるレビューや一次情報で判断材料を確認",
    ]
    reuse_candidates = _dedupe_preserve_order(
        [str(matched_topic.get("section_heading", "")).strip()]
        + [str(matched_topic.get("h2_candidate", "")).strip()]
        + [section.get("original_heading", "") for section in template_sections]
    )
    master_h2_headings = [
        str(section.get("original_heading", "")).strip()
        for section in template_sections
        if str(section.get("original_heading", "")).strip()
    ]

    return {
        "seed_keyword": seed_keyword,
        "target_keyword": target_keyword,
        "query_type": query_type,
        "volume_label": volume_label,
        "required_h2_prefix": _make_h2_prefix(target_keyword),
        "opening_focus": opening_focus,
        "reuse_candidates": reuse_candidates,
        "master_h2_headings": master_h2_headings,
        "required_h2_headings": required_h2,
        "minimum_h2_count": len(required_h2),
        "research_questions": research_questions,
        "source_checkpoints": source_checkpoints,
        "writing_requirements": [
            "母艦記事の良い文章資産と論点順を土台にする",
            "母艦記事の H2 構成は原則すべて維持する",
            "4見出し前後へ圧縮してはいけない",
            "H2 は必ず対象検索キーワード：見出し名 で始める",
            "H2直下の最初の一文も、その見出しキーワードを自然に含めて始める",
            "おすすめ系でも商品推薦ではなく、判断軸を渡す記事にする",
        ],
        "forbidden_phrases": [
            "母艦記事",
            "このキーワードでは",
            "この記事の使い方",
            "テンプレート",
            "構造",
            "検索キーワード",
        ],
        "outline_title": str(outline.get("title", "")),
    }


def generate_kobetsu_jobs(
    seed_keyword: str,
    selected_records: list[Mapping[str, Any]],
    outline: Mapping[str, Any],
    master_research_bundle: Mapping[str, Any] | None = None,
    master_article_markdown: str = "",
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for record in selected_records:
        target_keyword = str(record.get("suggest_keyword", "")).strip()
        if not target_keyword:
            continue
        jobs.append(
            build_kobetsu_job(
                seed_keyword=seed_keyword,
                target_keyword=target_keyword,
                volume_label=str(record.get("volume_label", "")).strip(),
                query_type=str(record.get("query_type", "")).strip() or "Know",
                outline=outline,
                master_research_bundle=master_research_bundle,
                master_article_markdown=master_article_markdown,
            )
        )
    return jobs


def render_kobetsu_jobs_markdown(seed_keyword: str, jobs: list[Mapping[str, Any]]) -> str:
    lines = [
        f"# {seed_keyword} 個別記事ジョブ一覧",
        "",
        "## このファイルの役割",
        "",
        "- このチャットで個別記事本文を書く前の指示書",
        "- Python 側では本文を書かず、必要な論点整理だけを済ませる",
        "",
    ]

    for job in jobs:
        lines.append(f"## {job.get('target_keyword', '')}")
        lines.append("")
        lines.append(f"- クエリタイプ: {job.get('query_type', '')}")
        lines.append(f"- 検索ボリューム: {job.get('volume_label', '')}")
        lines.append(f"- 冒頭で最初に答えること: {job.get('opening_focus', '')}")
        lines.append(f"- H2 接頭辞: {job.get('required_h2_prefix', '')}")
        lines.append(f"- 母艦から流用したい見出し候補: {', '.join(job.get('reuse_candidates', []))}")
        lines.append(f"- 母艦 H2 数: {job.get('minimum_h2_count', 0)}")
        lines.append(f"- 母艦 H2 全維持: {' / '.join(job.get('master_h2_headings', []))}")
        lines.append("- 必須 H2 候補:")
        for heading in job.get("required_h2_headings", []):
            lines.append(f"  - {heading}")
        lines.append("- 調査質問:")
        for question in job.get("research_questions", []):
            lines.append(f"  - {question}")
        lines.append("- 確認先:")
        for checkpoint in job.get("source_checkpoints", []):
            lines.append(f"  - {checkpoint}")
        lines.append("- 執筆条件:")
        for requirement in job.get("writing_requirements", []):
            lines.append(f"  - {requirement}")
        lines.append("- 禁止表現:")
        for phrase in job.get("forbidden_phrases", []):
            lines.append(f"  - {phrase}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _build_payload(
    seed_keyword: str,
    target_keyword: str,
    volume_label: str,
    query_type: str,
    master_article_markdown: str,
    outline: Mapping[str, Any],
) -> str:
    template_sections = _parse_h2_sections(seed_keyword, master_article_markdown)
    payload = {
        "seed_keyword": seed_keyword,
        "target_keyword": target_keyword,
        "volume_label": volume_label,
        "query_type": query_type,
        "target_heading_prefix": _make_h2_prefix(target_keyword),
        "outline_title": str(outline.get("title", "")),
        "priority_groups": outline.get("priority_groups", []),
        "template_sections": template_sections,
        "master_article_markdown": master_article_markdown,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_variant_articles(
    seed_keyword: str,
    master_article_markdown: str,
    selected_records: list[Mapping[str, Any]],
    outline: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _ = seed_keyword
    _ = master_article_markdown
    _ = selected_records
    _ = outline
    return []


__all__ = [
    "build_kobetsu_job",
    "generate_kobetsu_jobs",
    "generate_variant_articles",
    "render_kobetsu_jobs_markdown",
]
