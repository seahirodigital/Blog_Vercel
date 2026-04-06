"""SEO記事量産ワークフローのPoC実行入口。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = CURRENT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from seo_factory.analyzers.keyword_normalizer import normalize_records
from seo_factory.collectors.rakko_suggest_collector import collect_suggest_keywords
from seo_factory.generators.master_article_generator import generate_master_article
from seo_factory.generators.master_outline_generator import generate_master_outline, render_markdown_outline
from seo_factory.generators.keyword_variant_rewriter import generate_variant_articles
from seo_factory.integrations.google_sheets_keyword_store import (
    load_keyword_records_from_sheet,
    select_keyword_records_for_generation,
    write_keyword_records_to_sheet,
)

DEFAULT_SPREADSHEET_ID = os.getenv(
    "SEO_FACTORY_SPREADSHEET_ID",
    "1_qjAWcrgGHY8xTQdiUrK-v_gJsXEb8FH9ABUvEpcVMo",
)


def _slugify(text: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", " ", str(text or ""))
    normalized = re.sub(r"\s+", "_", normalized).strip(" _")
    return normalized or "seed_keyword"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_variant_articles(target_dir: Path, variants: list[dict[str, Any]]) -> None:
    variants_dir = target_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        slug = _slugify(str(variant.get("target_keyword", "")))
        _write_text(variants_dir / f"{slug}.md", str(variant.get("article_markdown", "")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SEO記事量産ワークフロー PoC")
    parser.add_argument("seed_keyword", help="現行製品のシードキーワード")
    parser.add_argument("--previous-seed-keyword", help="前作製品のシードキーワード")
    parser.add_argument("--mode", default="google", help="ラッコキーワードのモード")
    parser.add_argument("--show-browser", action="store_true", help="Playwright を headful で開く")
    parser.add_argument(
        "--output-dir",
        default=r"C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output",
        help="出力ディレクトリ",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=DEFAULT_SPREADSHEET_ID,
        help="保存先 Google Spreadsheet ID",
    )
    parser.add_argument(
        "--resume-from-sheet",
        action="store_true",
        help="既存シートを読み込み、不要を除外して母艦記事生成を再開する",
    )
    parser.add_argument(
        "--sheet-tab-name",
        help="読み書きするシート名。未指定時はシードキーワードを使用",
    )
    parser.add_argument(
        "--continue-after-collection",
        action="store_true",
        help="シート保存後も停止せず、そのまま母艦記事生成へ進む",
    )
    parser.add_argument("--skip-llm", action="store_true", help="LLM を使わずローカル生成だけで出力する")
    parser.add_argument("--use-llm", action="store_true", help="明示指定時のみ LLM を使う")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_dir)
    slug = _slugify(args.seed_keyword)
    target_dir = output_root / slug
    sheet_tab_name = args.sheet_tab_name or args.seed_keyword

    if args.resume_from_sheet:
        print(f"シート読込開始: {sheet_tab_name}")
        sheet_rows = load_keyword_records_from_sheet(args.spreadsheet_id, sheet_tab_name)
        current_records = normalize_records(
            select_keyword_records_for_generation(args.seed_keyword, sheet_rows)
        )
        print(f"シート採用件数: {len(current_records)}")
        if not current_records:
            print("採用対象が0件のため停止します。状況列を確認してください。")
            return
    else:
        print(f"収集開始: {args.seed_keyword}")
        current_raw = collect_suggest_keywords(
            seed_keyword=args.seed_keyword,
            mode=args.mode,
            headless=not args.show_browser,
            debug_dir=str(target_dir / "debug"),
        )
        current_records = normalize_records(current_raw)
        print(f"現行サジェスト件数: {len(current_records)}")
        saved_sheet_name = write_keyword_records_to_sheet(
            spreadsheet_id=args.spreadsheet_id,
            sheet_title=sheet_tab_name,
            records=current_records,
        )
        print(f"シート保存完了: {saved_sheet_name}")
        print("状況列を手動で編集後、--resume-from-sheet で再開できます。")

        _write_json(target_dir / "current_keywords.json", current_records)
        if not args.continue_after_collection:
            print(f"停止地点: {target_dir}")
            return

    previous_records: list[dict[str, Any]] = []
    if args.previous_seed_keyword:
        print(f"前作収集開始: {args.previous_seed_keyword}")
        previous_raw = collect_suggest_keywords(
            seed_keyword=args.previous_seed_keyword,
            mode=args.mode,
            headless=not args.show_browser,
            debug_dir=str(target_dir / "debug"),
        )
        previous_records = normalize_records(previous_raw)
        for record in previous_records:
            record["source_scope"] = "previous"
        print(f"前作サジェスト件数: {len(previous_records)}")

    outline = generate_master_outline(
        seed_keyword=args.seed_keyword,
        current_records=current_records,
        previous_records=previous_records,
    )
    base_generation = generate_master_article(
        seed_keyword=args.seed_keyword,
        current_records=current_records,
        previous_records=previous_records,
        outline=outline,
        gemini_api_key=None,
    )

    _write_json(target_dir / "current_keywords.json", current_records)
    _write_json(target_dir / "previous_keywords.json", previous_records)
    _write_json(target_dir / "outline.json", outline)
    _write_text(target_dir / "outline.md", render_markdown_outline(outline))
    _write_text(target_dir / "base_article.md", base_generation["base_article_markdown"])
    _write_text(target_dir / "master_article.md", base_generation["master_article_markdown"])

    generation = base_generation
    gemini_api_key = ""
    if args.use_llm and not args.skip_llm:
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_api_key:
        generation = generate_master_article(
            seed_keyword=args.seed_keyword,
            current_records=current_records,
            previous_records=previous_records,
            outline=outline,
            gemini_api_key=gemini_api_key,
        )
        _write_text(target_dir / "master_article.md", generation["master_article_markdown"])
        if generation["enhancement_plan_markdown"]:
            _write_text(target_dir / "031_enhancement_plan.md", generation["enhancement_plan_markdown"])

    variants = generate_variant_articles(
        seed_keyword=args.seed_keyword,
        master_article_markdown=str(generation["master_article_markdown"]),
        selected_records=current_records,
        outline=outline,
        gemini_api_key=gemini_api_key,
    )
    _write_variant_articles(target_dir, variants)
    _write_json(target_dir / "variant_articles.json", variants)

    print(f"出力先: {target_dir}")
    print(f"LLM使用: {'あり' if generation['used_llm'] else 'なし'}")
    print(f"母艦記事タイトル: {generation['outline']['title']}")
    print(f"個別記事件数: {len(variants)}")


if __name__ == "__main__":
    main()
