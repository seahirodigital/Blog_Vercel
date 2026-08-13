import json
import subprocess
import unittest
from pathlib import Path

from scripts.title_variants.article_transformer import (
    analyze_variant_source,
    assemble_variant,
    target_filename,
    validate_variant,
)
from scripts.title_variants.prompt_builder import parse_engine_result


ROOT = Path(__file__).resolve().parents[2]
WORKER = Path("/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py")
ENGINE = Path("/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py")


SOURCE = (
    "# Insta360 X6 バッテリーおすすめまとめ\n\n"
    "Insta360 X6におすすめのバッテリーを紹介します。\n\n"
    "▼元記事の商品\n説明は変更しません。\nhttps://www.amazon.co.jp/dp/PARENT\n\n"
    "## Insta360 X6 バッテリーおすすめまとめ：結論\n\n"
    "Insta360 X6向け商品の判断基準です。\n\n"
    "▼おすすめ商品\n商品本文は変更しません。\nhttps://www.amazon.co.jp/dp/ACCESSORY\n\n"
    "## Insta360 X6 バッテリーおすすめ: 仕様\n\n"
    "### 注意点\n\n本文はそのままです。\n"
)


class TitleVariantTest(unittest.TestCase):
    def test_headings_change_and_body_products_urls_are_preserved(self):
        keyword = "insta360 x6 空間キャプチャー"
        article, source = assemble_variant(
            SOURCE,
            keyword=keyword,
            intro_text="insta360 x6 空間キャプチャーを調べている方向けに要点を紹介します。",
            conclusion_text="insta360 x6 空間キャプチャーについて元記事の情報から結論を整理します。",
        )
        validate_variant(article, SOURCE, keyword)
        self.assertTrue(article.startswith("# insta360 x6 空間キャプチャーまとめ\n"))
        self.assertIn("## insta360 x6 空間キャプチャーまとめ：結論", article)
        self.assertIn("## insta360 x6 空間キャプチャーまとめ：仕様", article)
        self.assertIn("### insta360 x6 空間キャプチャーまとめ：注意点", article)
        self.assertIn("\n\n▼元記事の商品", article)
        self.assertEqual(SOURCE.count("https://"), article.count("https://"))
        self.assertIn("商品本文は変更しません。", article)
        self.assertEqual("Insta360 X6 バッテリーおすすめまとめ", source.source_title)

    def test_fallback_changes_only_headings(self):
        article, source = assemble_variant(SOURCE, keyword="insta360 x6 ケース")
        validate_variant(article, SOURCE, "insta360 x6 ケース")
        self.assertIn(source.intro.text, article)
        self.assertIn(source.conclusion.text, article)

    def test_article_without_conclusion_gets_one_after_first_product(self):
        source = (
            "# Insta360 X6レビューまとめ\n\n冒頭です。\n\n"
            "▼最初の商品\n説明\nhttps://example.com/first\n\n"
            "▼二つ目の商品\n説明\nhttps://example.com/second\n\n"
            "## Insta360 X6レビューまとめ：まとめ\n\n既存のまとめです。\n"
        )
        article, parsed = assemble_variant(
            source,
            keyword="insta360 x6 スペック",
            conclusion_text="insta360 x6 スペックについて結論を整理します。",
        )
        validate_variant(article, source, "insta360 x6 スペック")
        heading = "## insta360 x6 スペックまとめ：結論"
        self.assertIsNone(parsed.conclusion_heading)
        self.assertLess(article.find("https://example.com/first"), article.find(heading))
        self.assertLess(article.find(heading), article.find("▼二つ目の商品"))

    def test_target_filename_is_safe(self):
        self.assertEqual("insta360 x6 sonyまとめ.md", target_filename("insta360 x6 sony"))
        self.assertNotIn("/", target_filename("insta360 x6 ケース/保護"))

    def test_mlx_json_is_limited_to_two_text_regions(self):
        result = parse_engine_result(
            json.dumps(
                {
                    "intro_text": "insta360 x6 ケースを探している方向けに紹介します。",
                    "conclusion_text": "insta360 x6 ケースについて元記事の情報をまとめます。",
                },
                ensure_ascii=False,
            ),
            keyword="insta360 x6 ケース",
            conclusion_required=True,
        )
        self.assertEqual(2, len(result))
        with self.assertRaisesRegex(ValueError, "URL"):
            parse_engine_result(
                json.dumps(
                    {
                        "intro_text": "insta360 x6 ケース https://example.com",
                        "conclusion_text": "insta360 x6 ケースの結論です。",
                    },
                    ensure_ascii=False,
                ),
                keyword="insta360 x6 ケース",
                conclusion_required=True,
            )

    def test_mlx_may_naturalize_keyword_word_order(self):
        result = parse_engine_result(
            json.dumps(
                {
                    "intro_text": "Insta360 X6とSony製品の違いを調べている方向けに紹介します。",
                    "conclusion_text": "Sonyとの比較で確認したい点を元記事から整理します。",
                },
                ensure_ascii=False,
            ),
            keyword="insta360 x6 sony",
            conclusion_required=True,
        )
        self.assertIn("Sony", result["intro_text"])

    def test_server_keyword_cleanup_handles_spreadsheet_copy(self):
        script = (
            "import('./lib/title-variants.js').then(m => "
            "process.stdout.write(JSON.stringify(m.normalizeTitleVariantKeywords(process.argv[1]))))"
        )
        raw = (
            "[insta360 x6 空間キャプチャー](https://www.google.co.jp/search?q=one)\t＋\n"
            "insta360 x6 アクセサリー\thttps://www.google.co.jp/search?q=two\n"
            "＋\ninsta360 x6 アクセサリー"
        )
        completed = subprocess.run(
            ["node", "-e", script, raw],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            ["insta360 x6 空間キャプチャー", "insta360 x6 アクセサリー"],
            json.loads(completed.stdout),
        )

    def test_worker_and_engine_have_title_variant_routes(self):
        worker_source = WORKER.read_text(encoding="utf-8")
        engine_source = ENGINE.read_text(encoding="utf-8")
        self.assertIn('job.get("job_type") == "title_variant"', worker_source)
        self.assertIn("process_title_variant_job", worker_source)
        self.assertIn("generate_title_variant_json", worker_source)
        self.assertIn("TITLE_VARIANT_RESPONSE_FORMAT", engine_source)


if __name__ == "__main__":
    unittest.main()
