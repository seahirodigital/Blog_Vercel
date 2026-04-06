"""母艦記事の見出し案と本文生成。"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]

try:
    from .master_outline_generator import generate_master_outline, render_markdown_outline
except ImportError:  # pragma: no cover
    from master_outline_generator import generate_master_outline, render_markdown_outline  # type: ignore

DEFAULT_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


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
        "enhancement_plan_markdown": "",
        "master_article_markdown": base_article,
        "used_llm": False,
    }

    if not gemini_api_key:
        return result

    best_outline_prompt = _load_prompt("031-best-outline-prompt.md", prompt_dir)
    best_enhancer_prompt = _load_prompt("032-best-article-enhancer-prompt.md", prompt_dir)
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
    return result


__all__ = [
    "build_generation_payload",
    "generate_master_article",
    "render_base_master_article",
]
