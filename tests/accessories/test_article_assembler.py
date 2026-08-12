from pathlib import Path
import re
import unittest

from scripts.accessories.affiliate_group import load_group
from scripts.accessories.article_assembler import assemble_article, immutable_content_sha256
from scripts.accessories.article_validator import validate_public_markdown
from scripts.accessories.conclusion_builder import build_conclusion_addition


ROOT = Path(__file__).resolve().parents[2]


class ArticleAssemblerTest(unittest.TestCase):
    def setUp(self):
        self.parent = (ROOT / "docs/accessories_sample_article.md").read_text(encoding="utf-8")
        self.group = load_group(
            ROOT / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt",
            "battery",
        )

    def test_only_headings_and_conclusion_are_extended(self):
        addition = build_conclusion_addition(
            product_name="iPad Pro M5 13インチ",
            category_name="バッテリー",
            spec_summary="M5チップ、高速充電、メモリ増量が主要な特徴です。",
            recommendation_reasons=[
                "20000mAhと45W出力、USB-Cケーブル内蔵で持ち運びに適します。",
                "20000mAhと67W出力で、複数端子を使い分けられます。",
            ],
            affiliate_group=self.group,
        )
        child, parsed = assemble_article(
            self.parent,
            category_name="バッテリー",
            conclusion_addition=addition,
        )
        validate_public_markdown(child, affiliate_group=self.group)
        self.assertTrue(child.startswith("# iPad Pro M5 13インチ バッテリーおすすめまとめ\n"))
        self.assertLess(child.find(self.group.products[0].text), child.find("## iPad Pro M5 13インチ バッテリーおすすめ: 主要な課題と論点"))
        self.assertEqual(len(re.findall(r"(?m)^## ", self.parent)), len(re.findall(r"(?m)^## ", child)))
        self.assertEqual(len(re.findall(r"(?m)^### ", self.parent)), len(re.findall(r"(?m)^### ", child)))
        self.assertTrue(all(
            heading.startswith("## iPad Pro M5 13インチ バッテリーおすすめ: ")
            for heading in re.findall(r"(?m)^## .+$", child)
        ))
        self.assertIn("主要な課題と論点", child)
        self.assertEqual(parsed.product_name, "iPad Pro M5 13インチ")
        self.assertNotIn("Amazonのアソシエイトとして", child)

    def test_frontmatter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "H1|Frontmatter"):
            validate_public_markdown("---\ntitle: x\n---\n# 記事")

    def test_immutable_hash_ignores_editable_heading_text_only(self):
        original_hash = immutable_content_sha256(self.parent, category_name="バッテリー")
        changed_heading = self.parent.replace(
            "# iPad Pro M5 13インチレビューまとめ：最新チップ搭載モデルの進化点と買い替えの必要性",
            "# iPad Pro M5 13インチレビューまとめ：別の題意",
            1,
        )
        self.assertEqual(
            original_hash,
            immutable_content_sha256(changed_heading, category_name="バッテリー"),
        )
        changed_body = self.parent.replace("高速充電対応", "急速充電対応", 1)
        self.assertNotEqual(
            original_hash,
            immutable_content_sha256(changed_body, category_name="バッテリー"),
        )

    def test_explicit_conclusion_converts_every_h2_text(self):
        parent = (
            "# 製品レビューまとめ：題意\n\n"
            "## 製品レビューまとめ：結論前の章\n本文A\n\n"
            "## 結論\n本文B\n\n"
            "## 製品レビューまとめ：結論後の章\n本文C\n"
        )
        addition = build_conclusion_addition(
            product_name="製品",
            category_name="バッテリー",
            spec_summary="USB-C充電に対応します。",
            recommendation_reasons=["45W出力に対応します。", "67W出力に対応します。"],
            affiliate_group=self.group,
        )
        child, _ = assemble_article(
            parent,
            category_name="バッテリー",
            title_format="製品名 バッテリーおすすめ：",
            conclusion_addition=addition,
        )
        self.assertIn("# 製品 バッテリーおすすめまとめ", child)
        self.assertIn("## 製品 バッテリーおすすめ: 結論前の章", child)
        self.assertIn("## 製品 バッテリーおすすめ: 結論", child)
        self.assertIn("## 製品 バッテリーおすすめ: 結論後の章", child)
        self.assertLess(child.find(self.group.products[0].text), child.find("## 製品 バッテリーおすすめ: 結論後の章"))

    def test_review_axis_is_removed_from_product_name_and_headings(self):
        parent = (
            "# M5 iPad Pro レビュー比較違いまとめます。\n\n"
            "## M5 iPad Pro レビュー比較違いまとめ：結論\n本文A\n\n"
            "## Captions\n本文B\n"
        )
        addition = build_conclusion_addition(
            product_name="M5 iPad Pro",
            category_name="充電器",
            spec_summary="USB-C充電に対応します。",
            recommendation_reasons=["45W出力です。", "67W出力です。"],
            affiliate_group=self.group,
        )
        child, parsed = assemble_article(
            parent,
            category_name="充電器",
            title_format="製品名 充電器おすすめ：",
            conclusion_addition=addition,
        )
        self.assertEqual("M5 iPad Pro", parsed.product_name)
        self.assertTrue(child.startswith("# M5 iPad Pro 充電器おすすめまとめ\n"))
        self.assertIn("## M5 iPad Pro 充電器おすすめ: 結論", child)
        self.assertIn("## M5 iPad Pro 充電器おすすめ: Captions", child)
        self.assertNotIn("レビュー比較違いまとめ", "\n".join(
            line for line in child.splitlines() if line.startswith(("# ", "## "))
        ))


if __name__ == "__main__":
    unittest.main()
