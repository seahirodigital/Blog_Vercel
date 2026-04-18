"""SEO記事量産ワークフローのPoC実行入口。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
SEO_FACTORY_DIR = CURRENT_DIR.parent.parent
RYOSAN_DIR = SEO_FACTORY_DIR.parent
INPUT_DIR = RYOSAN_DIR / "input"


def _load_module(module_path: Path, module_alias: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_alias, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"モジュールを読み込めません: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

KEYWORD_PIPELINE_MODULE = _load_module(
    SEO_FACTORY_DIR / "1_keyword_collect" / "scripts" / "031_1_keyword_pipeline.py",
    "seo_factory_031_1_keyword_pipeline",
)
MASTER_ARTICLE_MODULE = _load_module(
    SEO_FACTORY_DIR / "2_base_article" / "scripts" / "031_2_master_article_generator.py",
    "seo_factory_031_2_master_article_generator",
)
ARTICLE_VALIDATOR_MODULE = _load_module(
    CURRENT_DIR / "031_3_article_validator.py",
    "seo_factory_031_3_article_validator",
)
KOBETSU_WRITER_MODULE = _load_module(
    SEO_FACTORY_DIR / "3_variant_article" / "scripts" / "031_4_kobetsu_writer.py",
    "seo_factory_031_4_kobetsu_writer",
)

normalize_records = KEYWORD_PIPELINE_MODULE.normalize_records
collect_suggest_keywords = KEYWORD_PIPELINE_MODULE.collect_suggest_keywords
load_keyword_records_from_sheet = KEYWORD_PIPELINE_MODULE.load_keyword_records_from_sheet
select_keyword_records_for_generation = KEYWORD_PIPELINE_MODULE.select_keyword_records_for_generation
write_keyword_records_to_sheet = KEYWORD_PIPELINE_MODULE.write_keyword_records_to_sheet
generate_master_outline = MASTER_ARTICLE_MODULE.generate_master_outline
build_master_research_bundle = MASTER_ARTICLE_MODULE.build_master_research_bundle
render_markdown_outline = MASTER_ARTICLE_MODULE.render_markdown_outline
render_master_research_bundle_markdown = MASTER_ARTICLE_MODULE.render_master_research_bundle_markdown
generate_kobetsu_jobs = KOBETSU_WRITER_MODULE.generate_kobetsu_jobs
render_kobetsu_jobs_markdown = KOBETSU_WRITER_MODULE.render_kobetsu_jobs_markdown
validate_master_article = ARTICLE_VALIDATOR_MODULE.validate_master_article
render_master_validation_report_markdown = ARTICLE_VALIDATOR_MODULE.render_master_validation_report_markdown

DEFAULT_SPREADSHEET_ID = os.getenv(
    "SEO_FACTORY_SPREADSHEET_ID",
    "1_qjAWcrgGHY8xTQdiUrK-v_gJsXEb8FH9ABUvEpcVMo",
)
LEGACY_DEFAULT_OUTPUT_DIR = Path(r"C:\Users\HCY\OneDrive\髢狗匱\Blog_Vercel\ryosan\seo_factory\output")


def resolve_default_output_dir() -> Path:
    override = os.getenv("SEO_FACTORY_OUTPUT_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    portable_default = SEO_FACTORY_DIR / "output"
    for candidate in (portable_default, LEGACY_DEFAULT_OUTPUT_DIR):
        if candidate.exists():
            return candidate.resolve()
    return portable_default


def _normalize_search_keyword(text: str) -> str:
    normalized = str(text or "").replace("\u3000", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


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


def _memo_dir(target_dir: Path) -> Path:
    memo_dir = target_dir / "memo"
    memo_dir.mkdir(parents=True, exist_ok=True)
    return memo_dir


def _write_master_research_bundle(target_dir: Path, bundle: dict[str, Any]) -> None:
    memo_dir = _memo_dir(target_dir)
    _write_json(memo_dir / "031_2_master_research_bundle.json", bundle)
    _write_text(
        memo_dir / "031_2_master_research_bundle.md",
        render_master_research_bundle_markdown(bundle),
    )


def _write_kobetsu_jobs(target_dir: Path, seed_keyword: str, jobs: list[dict[str, Any]]) -> None:
    memo_dir = _memo_dir(target_dir)
    _write_json(memo_dir / "031_4_kobetsu_jobs.json", jobs)
    _write_text(
        memo_dir / "031_4_kobetsu_jobs.md",
        render_kobetsu_jobs_markdown(seed_keyword, jobs),
    )


def _write_master_validation_report(target_dir: Path, report: dict[str, Any]) -> None:
    memo_dir = _memo_dir(target_dir)
    _write_json(memo_dir / "031_3_master_validation_report.json", report)
    _write_text(
        memo_dir / "031_3_master_validation_report.md",
        render_master_validation_report_markdown(report),
    )


def _find_reference_article_path() -> Path | None:
    if not INPUT_DIR.exists():
        return None

    markdown_files = sorted(INPUT_DIR.glob("*.md"))
    non_backup_files = [
        path for path in markdown_files
        if not path.name.startswith("master_article_backup_")
    ]
    candidates = non_backup_files or markdown_files
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_reference_article() -> tuple[str, str]:
    reference_path = _find_reference_article_path()
    if reference_path is None:
        return "", ""
    return str(reference_path), reference_path.read_text(encoding="utf-8")


def _build_resume_command(search_keyword: str, sheet_tab_name: str, script_path: Path) -> str:
    command = f'python {script_path} "{search_keyword}" --resume-from-sheet'
    if sheet_tab_name != search_keyword:
        command += f' --sheet-tab-name "{sheet_tab_name}"'
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SEO記事量産ワークフロー PoC")
    parser.add_argument("seed_keyword", help="ユーザーがチャットで提示した現行製品のラッコ検索キーワード")
    parser.add_argument("--previous-seed-keyword", help="前作製品のラッコ検索キーワード")
    parser.add_argument("--mode", default="google", help="ラッコキーワードのモード")
    parser.add_argument("--show-browser", action="store_true", help="Playwright を headful で開く")
    parser.add_argument(
        "--output-dir",
        default=str(resolve_default_output_dir()),
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
        help="読み書きするシート名。未指定時は正規化済みのラッコ検索キーワードを使用",
    )
    parser.add_argument(
        "--continue-after-collection",
        action="store_true",
        help="シート保存後も停止せず、そのまま母艦記事生成へ進む",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="互換用オプション。現在は常に Python 側で材料のみを出力する",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="互換用オプション。現在の本文作成はこのチャットで行う",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output_dir == str(LEGACY_DEFAULT_OUTPUT_DIR) and not Path(args.output_dir).exists():
        args.output_dir = str(resolve_default_output_dir())
    output_root = Path(args.output_dir)
    search_keyword = _normalize_search_keyword(args.seed_keyword)
    if not search_keyword:
        raise SystemExit("ラッコ検索キーワードが空です。ユーザーがチャットで提示した検索キーワードを指定してください。")

    previous_seed_keyword = ""
    if args.previous_seed_keyword:
        previous_seed_keyword = _normalize_search_keyword(args.previous_seed_keyword)
        if not previous_seed_keyword:
            raise SystemExit("前作製品のラッコ検索キーワードが空です。")

    sheet_tab_name = _normalize_search_keyword(args.sheet_tab_name or search_keyword)
    slug = _slugify(search_keyword)
    target_dir = output_root / slug
    if args.seed_keyword != search_keyword:
        print(f"入力キーワード補正: {args.seed_keyword} -> {search_keyword}")
    if args.sheet_tab_name and args.sheet_tab_name != sheet_tab_name:
        print(f"シート名補正: {args.sheet_tab_name} -> {sheet_tab_name}")
    if args.previous_seed_keyword and args.previous_seed_keyword != previous_seed_keyword:
        print(f"前作キーワード補正: {args.previous_seed_keyword} -> {previous_seed_keyword}")
    print(f"ラッコ検索キーワード: {search_keyword}")
    print(f"スプレッドシートタブ名: {sheet_tab_name}")
    print(f"出力スラッグ: {slug}")

    if args.resume_from_sheet:
        print(f"シート読込開始: {sheet_tab_name}")
        sheet_rows = load_keyword_records_from_sheet(args.spreadsheet_id, sheet_tab_name)
        current_records = normalize_records(
            select_keyword_records_for_generation(search_keyword, sheet_rows)
        )
        print(f"シート採用件数: {len(current_records)}")
        if not current_records:
            print("採用対象が0件のため停止します。状況列を確認してください。")
            return
    else:
        print(f"収集開始: {search_keyword}")
        current_raw = collect_suggest_keywords(
            seed_keyword=search_keyword,
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

        _write_json(_memo_dir(target_dir) / "current_keywords.json", current_records)
        if not args.continue_after_collection:
            print(f"停止地点: {target_dir}")
            return

    previous_records: list[dict[str, Any]] = []
    if previous_seed_keyword:
        print(f"前作収集開始: {previous_seed_keyword}")
        previous_raw = collect_suggest_keywords(
            seed_keyword=previous_seed_keyword,
            mode=args.mode,
            headless=not args.show_browser,
            debug_dir=str(target_dir / "debug"),
        )
        previous_records = normalize_records(previous_raw)
        for record in previous_records:
            record["source_scope"] = "previous"
        print(f"前作サジェスト件数: {len(previous_records)}")

    outline = generate_master_outline(
        seed_keyword=search_keyword,
        current_records=current_records,
        previous_records=previous_records,
    )
    reference_article_path, reference_article_markdown = _load_reference_article()
    existing_master_article_markdown = ""
    existing_master_article_path = target_dir / "master_article.md"
    if existing_master_article_path.exists():
        existing_master_article_markdown = existing_master_article_path.read_text(encoding="utf-8")
    master_research_bundle = build_master_research_bundle(
        seed_keyword=search_keyword,
        current_records=current_records,
        previous_records=previous_records,
        outline=outline,
        reference_article_markdown=reference_article_markdown,
        reference_article_path=reference_article_path,
        existing_master_article_markdown=existing_master_article_markdown,
    )
    _write_json(_memo_dir(target_dir) / "current_keywords.json", current_records)
    _write_json(_memo_dir(target_dir) / "previous_keywords.json", previous_records)
    _write_json(_memo_dir(target_dir) / "outline.json", outline)
    _write_text(_memo_dir(target_dir) / "outline.md", render_markdown_outline(outline))
    _write_master_research_bundle(target_dir, master_research_bundle)

    if args.use_llm or args.skip_llm:
        print("補足: --use-llm / --skip-llm は互換用オプションです。本文作成は常にこのチャットで行います。")

    if not existing_master_article_markdown:
        print("Python 側で材料のみ保存しました。本文作成はこのチャットで行います。")
        if reference_article_path:
            print(f"土台記事: {reference_article_path}")
        else:
            print(f"土台記事: 未検出 ({INPUT_DIR})")
        print(f"母艦記事用材料: {_memo_dir(target_dir) / '031_2_master_research_bundle.md'}")
        print(
            "次の工程: "
            f"このチャットで {target_dir / 'master_article.md'} を作成し、その後 "
            f"{_build_resume_command(search_keyword, sheet_tab_name, CURRENT_DIR / '031_5_run_factory.py')} "
            "を再実行"
        )
        print(f"出力先: {target_dir}")
        return

    master_validation_report = validate_master_article(existing_master_article_markdown, master_research_bundle)
    _write_master_validation_report(target_dir, master_validation_report)
    if not master_validation_report["passed"]:
        print("母艦記事が検証で NG になったため、個別記事ジョブ生成を停止しました。")
        if reference_article_path:
            print(f"土台記事: {reference_article_path}")
        print(f"母艦記事用材料: {_memo_dir(target_dir) / '031_2_master_research_bundle.md'}")
        print(f"母艦記事検証レポート: {_memo_dir(target_dir) / '031_3_master_validation_report.md'}")
        print(f"出力先: {target_dir}")
        return

    kobetsu_jobs = generate_kobetsu_jobs(
        seed_keyword=search_keyword,
        selected_records=current_records,
        outline=outline,
        master_research_bundle=master_research_bundle,
        master_article_markdown=existing_master_article_markdown,
    )
    _write_kobetsu_jobs(target_dir, search_keyword, kobetsu_jobs)
    print("材料保存、母艦記事検証、個別記事ジョブ生成まで完了しました。")
    if reference_article_path:
        print(f"土台記事: {reference_article_path}")
    print(f"母艦記事: {existing_master_article_path}")
    print(f"母艦記事用材料: {_memo_dir(target_dir) / '031_2_master_research_bundle.md'}")
    print(f"母艦記事検証レポート: {_memo_dir(target_dir) / '031_3_master_validation_report.md'}")
    print(f"個別記事ジョブ: {_memo_dir(target_dir) / '031_4_kobetsu_jobs.md'}")
    print(f"出力先: {target_dir}")


if __name__ == "__main__":
    main()
