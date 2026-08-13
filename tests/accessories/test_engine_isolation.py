import ast
from pathlib import Path
import unittest

from scripts.accessories.affiliate_group import AffiliateGroup, AffiliateProduct
from scripts.accessories.main import source_fallback_result


ROOT = Path(__file__).resolve().parents[2]


class EngineIsolationTest(unittest.TestCase):
    def test_common_runner_does_not_import_gemini_at_module_load(self):
        source = (ROOT / "scripts/accessories/main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        imported_names = {
            alias.name
            for node in top_level_imports
            for alias in node.names
        }
        self.assertNotIn("gemini_engine", imported_names)

    def test_mlx_source_fallback_does_not_reuse_rejected_output(self):
        group = AffiliateGroup(
            name="cable",
            raw_text="判断基準\n▼商品\nhttps://example.com/item",
            section_intro="判断基準\n・原文の改行",
            products=(
                AffiliateProduct(
                    index=1,
                    title="商品",
                    text="▼商品\nhttps://example.com/item",
                    urls=("https://example.com/item",),
                ),
            ),
        )
        result = source_fallback_result("Insta360 X6", "ケーブル", group)
        self.assertEqual(group.section_intro, result["adapted_section_intro"])
        self.assertEqual([group.products[0].text], result["adapted_product_texts"])
        self.assertNotIn("<br>", result["adapted_section_intro"])
        self.assertIn("Insta360 X6", result["intro_sentence"])

    def test_mlx_retry_receives_accumulated_validation_errors(self):
        worker = Path(
            "/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py"
        ).read_text(encoding="utf-8")
        engine = Path(
            "/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py"
        ).read_text(encoding="utf-8")
        runner = (ROOT / "scripts/accessories/main.py").read_text(encoding="utf-8")
        self.assertIn("validation_feedback=tuple(generation_errors)", runner)
        self.assertIn("generation_errors.append", runner)
        self.assertIn("validation_feedback=validation_feedback", worker)
        self.assertIn("これまでの検査エラーをすべて修正", engine)


if __name__ == "__main__":
    unittest.main()
