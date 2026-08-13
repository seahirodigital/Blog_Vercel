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

    def adapted_blocks(self, product_name="iPad Pro M5 13インチ"):
        return [
            f"{product.text}\n\n{product_name}におすすめな理由として、持ち運びやすい選択肢です。"
            for product in self.group.products
        ]

    def adapted_section_intro(self, product_name="iPad Pro M5 13インチ"):
        lines = self.group.section_intro.splitlines()
        lines[0] = f"{product_name}におすすめの" + lines[0].replace("のおすすめ", "", 1)
        return "\n".join(lines)

    def test_only_headings_and_conclusion_are_extended(self):
        addition = build_conclusion_addition(
            adapted_section_intro=self.adapted_section_intro(),
            adapted_product_texts=self.adapted_blocks(),
        )
        child, parsed = assemble_article(
            self.parent,
            category_name="バッテリー",
            intro_addition="iPad Pro M5 13インチにおすすめのバッテリーも紹介します。",
            conclusion_addition=addition,
        )
        validate_public_markdown(
            child,
            affiliate_group=self.group,
            adapted_section_intro=self.adapted_section_intro(),
            adapted_product_texts=self.adapted_blocks(),
        )
        self.assertTrue(child.startswith("# iPad Pro M5 13インチ バッテリーおすすめまとめ\n"))
        self.assertLess(child.find(self.group.products[0].text), child.find("## iPad Pro M5 13インチ バッテリーおすすめ: 主要な課題と論点"))
        self.assertEqual(len(re.findall(r"(?m)^## ", self.parent)) + 1, len(re.findall(r"(?m)^## ", child)))
        self.assertEqual(len(re.findall(r"(?m)^### ", self.parent)), len(re.findall(r"(?m)^### ", child)))
        self.assertTrue(all(
            heading == "## iPad Pro M5 13インチ バッテリーおすすめまとめ：結論"
            or heading.startswith("## iPad Pro M5 13インチ バッテリーおすすめ: ")
            for heading in re.findall(r"(?m)^## .+$", child)
        ))
        self.assertIn("主要な課題と論点", child)
        self.assertEqual(parsed.product_name, "iPad Pro M5 13インチ")
        self.assertIn("iPad Pro M5 13インチにおすすめのバッテリーも紹介します。", child)
        self.assertNotIn("おすすめ商品のリンクまとめ", child)
        self.assertNotIn("Amazonのアソシエイトとして", child)

    def test_recommendation_section_is_inserted_immediately_after_first_amazon_url(self):
        parent = (
            "# Insta360 X6レビュー比較まとめ\n\n"
            "親記事の冒頭です。\n\n"
            "https://www.amazon.co.jp/dp/PARENT1\n\n"
            "▼脅威の65％OFF!? 親商品の案内\nhttps://amzn.to/PARENT2\n\n"
            "## 仕様\n本文\n"
        )
        addition = build_conclusion_addition(
            adapted_section_intro=self.adapted_section_intro("Insta360 X6"),
            adapted_product_texts=self.adapted_blocks("Insta360 X6"),
        )
        child, parsed = assemble_article(
            parent,
            category_name="バッテリー",
            intro_addition="Insta360 X6におすすめのバッテリーを紹介します。",
            conclusion_addition=addition,
        )
        heading = "## Insta360 X6 バッテリーおすすめまとめ：結論"
        self.assertLess(child.find("https://www.amazon.co.jp/dp/PARENT1"), child.find(heading))
        self.assertLess(child.find(heading), child.find(self.group.products[0].text))
        self.assertLess(child.find(self.group.products[-1].text), child.find("▼脅威の65％OFF!? 親商品の案内"))
        self.assertLess(child.find(self.group.products[-1].text), child.find("https://amzn.to/PARENT2"))
        self.assertEqual(
            parsed.first_product_insert_at,
            parent.find("https://www.amazon.co.jp/dp/PARENT1")
            + len("https://www.amazon.co.jp/dp/PARENT1\n"),
        )

    def test_product_without_amazon_url_uses_original_block_boundary(self):
        parent = (
            "# 製品レビューまとめ\n\n"
            "▼親商品の1件目\n説明だけです。\n\n"
            "▼親商品の2件目\n説明2\n"
        )
        _, parsed = assemble_article(
            parent,
            category_name="バッテリー",
            conclusion_addition="おすすめ商品です。",
        )
        self.assertEqual(parsed.first_product_insert_at, parent.find("▼親商品の2件目"))

    def test_frontmatter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "H1|Frontmatter"):
            validate_public_markdown("---\ntitle: x\n---\n# 記事")

    def test_product_validation_accepts_crlf_article(self):
        blocks = self.adapted_blocks()
        section_intro = self.adapted_section_intro()
        article = ("# 記事\n\n" + section_intro + "\n\n" + "\n\n".join(blocks)).replace("\n", "\r\n")
        validate_public_markdown(
            article,
            affiliate_group=self.group,
            adapted_section_intro=section_intro,
            adapted_product_texts=blocks,
            allowed_new_urls=[url for product in self.group.products for url in product.urls],
        )

    def test_link_summary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "リンクまとめ"):
            validate_public_markdown("# 記事\n\n**おすすめ商品のリンクまとめ**")

    def test_duplicate_product_blocks_are_allowed_in_source_order(self):
        adapter_group = load_group(
            ROOT / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt",
            "adapter",
        )
        article = (
            "# 充電器記事\n\n"
            + adapter_group.section_intro
            + "\n\n"
            + "\n\n".join(product.text for product in adapter_group.products)
        )
        validate_public_markdown(
            article,
            affiliate_group=adapter_group,
            adapted_section_intro=adapter_group.section_intro,
        )

        duplicate = next(
            product.text
            for product in adapter_group.products
            if sum(candidate.text == product.text for candidate in adapter_group.products) > 1
        )
        article_with_extra_duplicate = f"{article}\n\n{duplicate}\n"
        validate_public_markdown(
            article_with_extra_duplicate,
            affiliate_group=adapter_group,
            adapted_section_intro=adapter_group.section_intro,
        )

    def test_missing_second_identical_product_is_rejected(self):
        adapter_group = load_group(
            ROOT / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt",
            "adapter",
        )
        blocks = [product.text for product in adapter_group.products]
        duplicate_index = next(
            index
            for index, block in enumerate(blocks)
            if block in blocks[:index]
        )
        del blocks[duplicate_index]
        article = f"# 充電器記事\n\n{adapter_group.section_intro}\n\n" + "\n\n".join(blocks)
        with self.assertRaisesRegex(ValueError, "調整済み商品ブロックが掲載されていません"):
            validate_public_markdown(
                article,
                affiliate_group=adapter_group,
                adapted_section_intro=adapter_group.section_intro,
            )

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
            adapted_section_intro=self.adapted_section_intro("製品"),
            adapted_product_texts=self.adapted_blocks("製品"),
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
            adapted_section_intro=self.adapted_section_intro("M5 iPad Pro"),
            adapted_product_texts=self.adapted_blocks("M5 iPad Pro"),
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
        self.assertLess(
            child.find(self.group.products[0].text),
            child.find("## M5 iPad Pro 充電器おすすめ: 結論"),
        )
        self.assertIn("## M5 iPad Pro 充電器おすすめまとめ：結論", child)
        self.assertLess(
            child.find(self.group.products[0].text),
            child.find("## M5 iPad Pro 充電器おすすめ: Captions"),
        )
        self.assertNotIn("レビュー比較違いまとめ", "\n".join(
            line for line in child.splitlines() if line.startswith(("# ", "## "))
        ))


if __name__ == "__main__":
    unittest.main()
