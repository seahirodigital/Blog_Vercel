import unittest
from pathlib import Path

from scripts.accessories.sheet_master_loader import REQUIRED_HEADERS, matching_categories, parse_master_rows
from scripts.accessories.sheet_registry import HEADERS, safe_sheet_text


class SheetContractsTest(unittest.TestCase):
    def test_master_rows_and_keyword_matching(self):
        headers = [*REQUIRED_HEADERS, "表示優先度"]
        rows = [
            ["USB-C, iPad", "battery", "バッテリー", "{PRODUCT} バッテリーおすすめ：", "battery", "TRUE", "tpl_default.md", "2"],
            ["USB-C, MacBook", "cable", "ケーブル", "{PRODUCT} ケーブルおすすめ：", "cable", "TRUE", "tpl_default.md", "1"],
        ]
        parsed = parse_master_rows(headers, rows)
        self.assertEqual(["cable", "battery"], [item.category_id for item in parsed])
        matched = matching_categories("iPad ProはUSB-Cを搭載", parsed)
        self.assertEqual(["cable", "battery"], [item.category_id for item in matched])
        self.assertTrue(all(len(item.sha256) == 64 for item in parsed))

    def test_initial_three_categories_match_sample_parent(self):
        headers = [*REQUIRED_HEADERS, "表示優先度"]
        keywords = "iPhone、iPad、MacBook、スマートフォン、タブレット、ノートパソコン、USB-C"
        rows = [
            [keywords, "battery", "バッテリー", "製品名 バッテリーおすすめ：", "battery", "TRUE", "tpl_default.md", "10"],
            [keywords, "adapter", "アダプター", "製品名 アダプターおすすめ：", "adapter", "TRUE", "tpl_default.md", "20"],
            [keywords, "cable", "ケーブル", "製品名 ケーブルおすすめ：", "cable", "TRUE", "tpl_default.md", "30"],
        ]
        sample = (Path(__file__).resolve().parents[2] / "docs/accessories_sample_article.md").read_text(encoding="utf-8")
        matched = matching_categories(sample, parse_master_rows(headers, rows))
        self.assertEqual(["battery", "adapter", "cable"], [item.category_id for item in matched])
        adapter = next(item for item in matched if item.category_id == "adapter")
        self.assertEqual("充電器", adapter.category_name)
        self.assertEqual("製品名 充電器おすすめ：", adapter.title_format)
        self.assertEqual("アダプター", adapter.raw["周辺機器カテゴリ名"])

    def test_registry_headers_and_formula_injection(self):
        self.assertEqual(
            ("作成日時", "完了日時", "記事タイトル", "進捗", "記事URLリンク", "大元記事タイトル", "大元記事リンク"),
            HEADERS[:7],
        )
        self.assertEqual("'=IMPORTXML(...)" , safe_sheet_text("=IMPORTXML(...)"))


if __name__ == "__main__":
    unittest.main()
