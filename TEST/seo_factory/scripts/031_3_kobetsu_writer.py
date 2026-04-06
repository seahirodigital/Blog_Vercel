"""031_3 個別記事生成器。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]

DEFAULT_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


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
    response = client.models.generate_content(
        model=model_name,
        contents=full_input,
    )
    return str(getattr(response, "text", "") or "").strip()


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


def render_base_variant_article(
    seed_keyword: str,
    target_keyword: str,
    volume_label: str,
    query_type: str,
    master_article_markdown: str,
) -> str:
    sections = _parse_h2_sections(seed_keyword, master_article_markdown)
    lines = [
        f"# {target_keyword}",
        "",
        f"{target_keyword} で迷いやすい論点を、先に結論から確認しやすい順で整理する。",
        "",
    ]

    compact_priority = re.sub(r"\s+", "", f"{query_type}{volume_label}")[:20] or "優先確認"
    compact_keyword = re.sub(r"\s+", "", target_keyword)[:20] or "対象論点"

    for section in sections:
        label = str(section["section_label"])
        lines.append(f"## {_make_h2_prefix(target_keyword)}{label}")
        lines.append("")
        lines.append(f"{target_keyword} で {label} を確認するときは、先に答えを絞ってから詳細を見た方が判断しやすいです。")
        lines.append("")
        lines.append(f"- 結論：{compact_keyword}")
        lines.append(f"- 論点：{re.sub(r'\\s+', '', label)[:20] or '主要論点'}")
        lines.append(f"- 優先：{compact_priority}")
        lines.append("- 方法：基準先確認")
        lines.append("")
        if section["body_markdown"]:
            lines.append(section["body_markdown"])
            lines.append("")
        lines.append(f"{target_keyword} の {label} は、確認順を固定すると迷いを減らしやすいです。")
        lines.append("")

    return _normalize_h2_prefixes("\n".join(lines).strip() + "\n", target_keyword)


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
    gemini_api_key: str | None = None,
    prompt_dir: Path | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> list[dict[str, Any]]:
    prompt_text = _load_prompt("031-3-kobetsu-writer-prompt.md", prompt_dir)
    client: Any | None = None
    if gemini_api_key:
        if genai is None:
            raise RuntimeError("google-genai がインストールされていないため、個別記事生成を実行できません。")
        client = genai.Client(api_key=gemini_api_key)
    else:
        return []

    variants: list[dict[str, Any]] = []
    for record in selected_records:
        target_keyword = str(record.get("suggest_keyword", "")).strip()
        if not target_keyword:
            continue
        volume_label = str(record.get("volume_label", "")).strip()
        query_type = str(record.get("query_type", "")).strip() or "Know"

        base_article = render_base_variant_article(
            seed_keyword=seed_keyword,
            target_keyword=target_keyword,
            volume_label=volume_label,
            query_type=query_type,
            master_article_markdown=master_article_markdown,
        )
        article_markdown = base_article
        used_llm = False
        if client is not None:
            payload = _build_payload(
                seed_keyword=seed_keyword,
                target_keyword=target_keyword,
                volume_label=volume_label,
                query_type=query_type,
                master_article_markdown=master_article_markdown,
                outline=outline,
            )
            article_markdown = _run_generation(
                client=client,
                input_text=payload,
                system_prompt=prompt_text,
                model_name=model_name,
            ) or base_article
            article_markdown = _normalize_h2_prefixes(article_markdown, target_keyword)
            used_llm = True

        variants.append(
            {
                "target_keyword": target_keyword,
                "volume_label": volume_label,
                "query_type": query_type,
                "used_llm": used_llm,
                "article_markdown": article_markdown,
            }
        )

    return variants


__all__ = [
    "generate_variant_articles",
    "render_base_variant_article",
]
