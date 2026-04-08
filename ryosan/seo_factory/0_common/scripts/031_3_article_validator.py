"""031_3 記事バリデーター。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping


def _slugify(text: str) -> str:
    invalid = '\\/:*?"<>|'
    normalized = "".join(" " if char in invalid else char for char in str(text or ""))
    normalized = "_".join(normalized.split()).strip("_")
    return normalized or "seed_keyword"


def _extract_h2_blocks(article_markdown: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_lines
        if current_heading is None:
            return
        blocks.append(
            {
                "heading": current_heading,
                "body": "\n".join(current_lines).strip(),
            }
        )
        current_heading = None
        current_lines = []

    for raw_line in str(article_markdown or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            continue
        if current_heading is not None:
            current_lines.append(line)

    flush()
    return blocks


def _first_nonempty_line(text: str) -> str:
    for line in str(text or "").splitlines():
        normalized = line.strip()
        if normalized:
            return normalized
    return ""


def _analyze_section_body(body_markdown: str) -> dict[str, int]:
    raw_lines = [line.rstrip() for line in str(body_markdown or "").splitlines()]
    nonempty_lines = [line.strip() for line in raw_lines if line.strip()]
    bullet_count = sum(
        1
        for line in nonempty_lines
        if re.match(r"^(?:[-*]|[0-9]+\.)\s+", line)
    )
    qa_count = sum(
        1
        for line in nonempty_lines
        if re.match(r"^(?:Q|A)[0-9０-９]*\s*[:：]", line, flags=re.IGNORECASE)
    )
    return {
        "nonempty_line_count": len(nonempty_lines),
        "bullet_count": bullet_count,
        "qa_count": qa_count,
    }


def _contains_any(text: str, candidates: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(candidate or "").lower() in lowered for candidate in candidates if str(candidate or "").strip())


def _canonical_heading(text: str) -> str:
    normalized = re.sub(r"\s*&\s*cta\s*$", "", str(text or ""), flags=re.IGNORECASE)
    return "".join(normalized.lower().split())


def validate_master_article(article_markdown: str, bundle: Mapping[str, Any]) -> dict[str, Any]:
    article_text = str(article_markdown or "")
    rules = dict(bundle.get("master_validation_rules", {}))
    expected_h2 = [str(heading).strip() for heading in rules.get("required_h2_headings", []) if str(heading).strip()]
    baseline_h2 = [str(heading).strip() for heading in rules.get("baseline_h2_headings", []) if str(heading).strip()]
    topic_h2 = [str(heading).strip() for heading in rules.get("topic_h2_headings", []) if str(heading).strip()]
    topic_insert_after = str(rules.get("topic_h2_insert_after", "")).strip()
    topic_insert_before = str(rules.get("topic_h2_insert_before", "")).strip()
    preserve_h2 = [str(heading).strip() for heading in rules.get("preserve_existing_h2_headings", []) if str(heading).strip()]
    preserve_h2_order = bool(rules.get("preserve_existing_h2_order"))
    reference_section_rules = [
        dict(rule)
        for rule in rules.get("reference_section_rules", [])
        if str(rule.get("heading", "")).strip()
    ]
    forbidden_phrases = [str(phrase).strip() for phrase in rules.get("forbidden_phrases", []) if str(phrase).strip()]
    generic_markers = [str(marker).strip() for marker in rules.get("generic_draft_markers", []) if str(marker).strip()]

    errors: list[str] = []
    warnings: list[str] = []

    if "### " in article_text or "#### " in article_text:
        errors.append("母艦記事に H3/H4 が含まれている")

    for phrase in forbidden_phrases:
        if phrase and phrase in article_text:
            errors.append(f"母艦記事に禁止表現が含まれている: {phrase}")

    h2_blocks = _extract_h2_blocks(article_text)
    actual_h2 = [block["heading"] for block in h2_blocks]
    actual_h2_canonical = {_canonical_heading(heading): heading for heading in actual_h2}
    actual_h2_block_map = {
        _canonical_heading(str(block.get("heading", ""))): dict(block)
        for block in h2_blocks
        if str(block.get("heading", "")).strip()
    }

    if not actual_h2:
        errors.append("母艦記事に H2 が1つも無い")

    actual_h2_positions = {_canonical_heading(heading): index for index, heading in enumerate(actual_h2)}
    expected_positions: list[int] = []
    for heading in expected_h2:
        canonical_heading = _canonical_heading(heading)
        if canonical_heading not in actual_h2_positions:
            errors.append(f"必須 H2 が不足している: {heading}")
            continue
        expected_positions.append(actual_h2_positions[canonical_heading])
    if expected_positions and expected_positions != sorted(expected_positions):
        errors.append("必須 H2 の並び順が bundle の想定順と一致していない")

    for heading in baseline_h2:
        if _canonical_heading(heading) not in actual_h2_canonical:
            errors.append(f"80点記事 baseline の H2 が不足している: {heading}")

    if topic_h2 and topic_insert_after and topic_insert_before:
        after_index = actual_h2_positions.get(_canonical_heading(topic_insert_after), -1)
        before_index = actual_h2_positions.get(_canonical_heading(topic_insert_before), -1)
        if after_index == -1 or before_index == -1 or after_index >= before_index:
            errors.append("採用キーワード別 H2 を差し込む基準位置が成立していない")
        else:
            for heading in topic_h2:
                canonical_heading = _canonical_heading(heading)
                if canonical_heading not in actual_h2_positions:
                    continue
                heading_index = actual_h2_positions[canonical_heading]
                if not (after_index < heading_index < before_index):
                    errors.append(f"採用キーワード別 H2 が 選定基準 と 比較 の間に無い: {heading}")

    for heading in preserve_h2:
        if _canonical_heading(heading) not in actual_h2_canonical:
            errors.append(f"既存母艦から継承すべき H2 が不足している: {heading}")
    if preserve_h2_order:
        preserve_positions: list[int] = []
        for heading in preserve_h2:
            canonical_heading = _canonical_heading(heading)
            if canonical_heading not in actual_h2_positions:
                continue
            preserve_positions.append(actual_h2_positions[canonical_heading])
        if preserve_positions and preserve_positions != sorted(preserve_positions):
            errors.append("継承すべき H2 の並び順が参照記事の順序と一致していない")

    topic_map = {
        str(topic.get("h2_candidate", "")).strip(): dict(topic)
        for topic in bundle.get("topics", [])
        if str(topic.get("h2_candidate", "")).strip()
    }
    reference_section_results: list[dict[str, Any]] = []

    for block in h2_blocks:
        heading = str(block.get("heading", "")).strip()
        body = str(block.get("body", "")).strip()
        first_line = _first_nonempty_line(body)
        if not first_line:
            errors.append(f"H2 直下の本文が空: {heading}")
            continue

        if _contains_any(body, generic_markers):
            errors.append(f"generic な仮ドラフト表現が残っている: {heading}")

        topic = topic_map.get(heading, {})
        if topic:
            related_keywords = [heading]
            related_keywords.extend(str(keyword).strip() for keyword in topic.get("related_keywords", []))
            if related_keywords and not _contains_any(first_line, related_keywords):
                errors.append(f"冒頭文が対象論点に寄っていない: {heading}")

    for rule in reference_section_rules:
        heading = str(rule.get("heading", "")).strip()
        canonical_heading = _canonical_heading(heading)
        actual_block = actual_h2_block_map.get(canonical_heading)
        if actual_block is None:
            continue

        actual_metrics = _analyze_section_body(str(actual_block.get("body", "")))
        minimum_nonempty_line_count = int(rule.get("minimum_nonempty_line_count", 0) or 0)
        minimum_bullet_count = int(rule.get("minimum_bullet_count", 0) or 0)
        minimum_qa_count = int(rule.get("minimum_qa_count", 0) or 0)
        reference_section_results.append(
            {
                "heading": heading,
                "reference_nonempty_line_count": int(rule.get("reference_nonempty_line_count", 0) or 0),
                "minimum_nonempty_line_count": minimum_nonempty_line_count,
                "actual_nonempty_line_count": actual_metrics["nonempty_line_count"],
                "reference_bullet_count": int(rule.get("reference_bullet_count", 0) or 0),
                "minimum_bullet_count": minimum_bullet_count,
                "actual_bullet_count": actual_metrics["bullet_count"],
                "reference_qa_count": int(rule.get("reference_qa_count", 0) or 0),
                "minimum_qa_count": minimum_qa_count,
                "actual_qa_count": actual_metrics["qa_count"],
            }
        )

        if minimum_nonempty_line_count and actual_metrics["nonempty_line_count"] < minimum_nonempty_line_count:
            errors.append(
                f"参照記事の章内説明量を維持できていない: {heading} "
                f"(実際 {actual_metrics['nonempty_line_count']} 行 / 最低 {minimum_nonempty_line_count} 行)"
            )
        if minimum_bullet_count and actual_metrics["bullet_count"] < minimum_bullet_count:
            errors.append(
                f"参照記事の箇条書き構成を維持できていない: {heading} "
                f"(実際 {actual_metrics['bullet_count']} 件 / 最低 {minimum_bullet_count} 件)"
            )
        if minimum_qa_count and actual_metrics["qa_count"] < minimum_qa_count:
            errors.append(
                f"参照記事のQ&A構成を維持できていない: {heading} "
                f"(実際 {actual_metrics['qa_count']} 件 / 最低 {minimum_qa_count} 件)"
            )

    if expected_h2 and len(actual_h2) >= len(expected_h2):
        warnings.append("母艦記事の必須 H2 は最低限そろっている")

    return {
        "seed_keyword": str(bundle.get("seed_keyword", "")).strip(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "actual_h2_headings": actual_h2,
        "expected_h2_headings": expected_h2,
        "reference_section_results": reference_section_results,
    }


def validate_variant_article(article_markdown: str, job: Mapping[str, Any]) -> dict[str, Any]:
    target_keyword = str(job.get("target_keyword", "")).strip()
    prefix = str(job.get("required_h2_prefix", "")).strip()
    expected_h2 = [str(heading).strip() for heading in job.get("required_h2_headings", []) if str(heading).strip()]
    forbidden_phrases = [str(phrase).strip() for phrase in job.get("forbidden_phrases", []) if str(phrase).strip()]
    minimum_h2_count = int(job.get("minimum_h2_count", 0) or 0)

    errors: list[str] = []
    warnings: list[str] = []

    article_text = str(article_markdown or "")
    if "### " in article_text or "#### " in article_text:
        errors.append("H3/H4 が含まれている")

    for phrase in forbidden_phrases:
        if phrase and phrase in article_text:
            errors.append(f"禁止表現が含まれている: {phrase}")

    h2_blocks = _extract_h2_blocks(article_text)
    actual_h2 = [block["heading"] for block in h2_blocks]

    if minimum_h2_count and len(actual_h2) < minimum_h2_count:
        errors.append(f"H2 数が不足している: {len(actual_h2)} / {minimum_h2_count}")

    if expected_h2 and actual_h2 != expected_h2:
        errors.append("H2 構成が母艦由来の必須構成と一致していない")

    for heading in actual_h2:
        if prefix and not heading.startswith(prefix):
            errors.append(f"H2 が対象キーワード始まりではない: {heading}")

    for block in h2_blocks:
        first_line = _first_nonempty_line(block["body"])
        if not first_line:
            errors.append(f"H2 直下の本文が空: {block['heading']}")
            continue
        if target_keyword and target_keyword not in first_line:
            errors.append(f"H2 直下の最初の1文に対象検索キーワードが無い: {block['heading']}")

    if expected_h2 and not actual_h2:
        errors.append("H2 が1つも無い")

    if expected_h2 and len(actual_h2) == len(expected_h2) and actual_h2 == expected_h2:
        warnings.append("H2 構成は必須条件を満たしている")

    return {
        "target_keyword": target_keyword,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "actual_h2_headings": actual_h2,
        "expected_h2_headings": expected_h2,
    }


def validate_variant_articles(
    jobs: list[Mapping[str, Any]],
    variants_dir: Path,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    passed = 0

    for job in jobs:
        target_keyword = str(job.get("target_keyword", "")).strip()
        article_path = variants_dir / f"{_slugify(target_keyword)}.md"
        if not article_path.exists():
            results.append(
                {
                    "target_keyword": target_keyword,
                    "passed": False,
                    "errors": [f"記事ファイルが存在しない: {article_path}"],
                    "warnings": [],
                    "actual_h2_headings": [],
                    "expected_h2_headings": [str(heading) for heading in job.get("required_h2_headings", [])],
                }
            )
            continue

        article_markdown = article_path.read_text(encoding="utf-8")
        result = validate_variant_article(article_markdown, job)
        result["article_path"] = str(article_path)
        results.append(result)
        if result["passed"]:
            passed += 1

    return {
        "total": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "passed": passed == len(results),
        "results": results,
    }


def render_validation_report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# 031_3 個別記事検証レポート",
        "",
        f"- 総件数: {report.get('total', 0)}",
        f"- 合格件数: {report.get('passed_count', 0)}",
        f"- 失敗件数: {report.get('failed_count', 0)}",
        "",
    ]

    for result in report.get("results", []):
        status = "OK" if result.get("passed") else "NG"
        lines.append(f"## {status} {result.get('target_keyword', '')}")
        lines.append("")
        if result.get("article_path"):
            lines.append(f"- 記事パス: {result.get('article_path', '')}")
        lines.append(f"- 実際の H2 数: {len(result.get('actual_h2_headings', []))}")
        lines.append(f"- 期待 H2 数: {len(result.get('expected_h2_headings', []))}")
        if result.get("errors"):
            lines.append("- エラー:")
            for error in result.get("errors", []):
                lines.append(f"  - {error}")
        if result.get("warnings"):
            lines.append("- 補足:")
            for warning in result.get("warnings", []):
                lines.append(f"  - {warning}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_master_validation_report_markdown(report: Mapping[str, Any]) -> str:
    status = "OK" if report.get("passed") else "NG"
    lines = [
        "# 031_3 母艦記事検証レポート",
        "",
        f"- 判定: {status}",
        f"- 対象シード: {report.get('seed_keyword', '')}",
        f"- 実際の H2 数: {len(report.get('actual_h2_headings', []))}",
        f"- 期待 H2 数: {len(report.get('expected_h2_headings', []))}",
        "",
    ]

    if report.get("errors"):
        lines.append("## エラー")
        lines.append("")
        for error in report.get("errors", []):
            lines.append(f"- {error}")
        lines.append("")

    if report.get("warnings"):
        lines.append("## 補足")
        lines.append("")
        for warning in report.get("warnings", []):
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## 実際の H2")
    lines.append("")
    for heading in report.get("actual_h2_headings", []):
        lines.append(f"- {heading}")
    lines.append("")

    lines.append("## 期待 H2")
    lines.append("")
    for heading in report.get("expected_h2_headings", []):
        lines.append(f"- {heading}")
    lines.append("")

    reference_section_results = report.get("reference_section_results", [])
    if reference_section_results:
        lines.append("## 参照記事構造チェック")
        lines.append("")
        for result in reference_section_results:
            lines.append(
                f"- {result.get('heading', '')}: "
                f"行数 {result.get('actual_nonempty_line_count', 0)}/{result.get('minimum_nonempty_line_count', 0)} "
                f"(参照 {result.get('reference_nonempty_line_count', 0)}), "
                f"箇条書き {result.get('actual_bullet_count', 0)}/{result.get('minimum_bullet_count', 0)} "
                f"(参照 {result.get('reference_bullet_count', 0)}), "
                f"Q&A {result.get('actual_qa_count', 0)}/{result.get('minimum_qa_count', 0)} "
                f"(参照 {result.get('reference_qa_count', 0)})"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="031_3 記事バリデーター")
    parser.add_argument("--jobs-json", required=True, help="031_4_kobetsu_jobs.json のパス")
    parser.add_argument("--variants-dir", required=True, help="variants ディレクトリのパス")
    parser.add_argument("--output-json", help="検証結果 JSON の保存先")
    parser.add_argument("--output-md", help="検証結果 Markdown の保存先")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    jobs = json.loads(Path(args.jobs_json).read_text(encoding="utf-8"))
    report = validate_variant_articles(jobs, Path(args.variants_dir))

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(render_validation_report_markdown(report), encoding="utf-8")

    if report["passed"]:
        print("検証合格")
    else:
        print("検証失敗")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
