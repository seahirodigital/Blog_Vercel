from pathlib import Path
import unittest

from scripts.accessories.affiliate_group import extract_group, load_group


ROOT = Path(__file__).resolve().parents[2]
AFFILIATE_FILE = ROOT / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt"


class AffiliateGroupTest(unittest.TestCase):
    def test_legacy_english_section_name_resolves_japanese_marker(self):
        text = "===バッテリー===\n説明\n▼商品\nhttps://example.com/item\n"
        group = extract_group(text, "battery")
        self.assertEqual("battery", group.name)
        self.assertEqual("商品", group.products[0].title)

    def test_named_groups_keep_intro_and_all_triangle_blocks(self):
        expected_asins = {
            "battery": ["B0FS5XT48F", "B0GMWVL8FD"],
            "adapter": ["B08X11GD52", "B0DPWW49HK"],
            "cable": ["B0FXKF11B1", "B0CWH33BSK", "B0B2PR2QD4"],
        }
        for section, asin_order in expected_asins.items():
            group = load_group(AFFILIATE_FILE, section)
            self.assertTrue(group.section_intro)
            actual = [
                url.split("/dp/")[1].split("/")[0]
                for product in group.products
                for url in product.urls
                if "/dp/" in url
            ]
            positions = [actual.index(asin) for asin in asin_order]
            self.assertEqual(positions, sorted(positions))
            self.assertTrue(all(product.text.startswith("▼") for product in group.products))

    def test_section_stops_at_next_marker(self):
        battery = load_group(AFFILIATE_FILE, "battery")
        self.assertNotIn("Anker Nano II", battery.raw_text)
        adapter = load_group(AFFILIATE_FILE, "adapter")
        self.assertNotIn("===cable===", adapter.raw_text)


if __name__ == "__main__":
    unittest.main()
