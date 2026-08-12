from pathlib import Path
import unittest

from scripts.accessories.affiliate_group import load_group


ROOT = Path(__file__).resolve().parents[2]
AFFILIATE_FILE = ROOT / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt"


class AffiliateGroupTest(unittest.TestCase):
    def test_initial_groups_keep_all_products_and_urls(self):
        expected = {
            "battery": (
                2,
                ["B0FS5XT48F", "B0GMWVL8FD"],
            ),
            "adapter": (
                2,
                ["B08X11GD52", "B0DPWW49HK"],
            ),
            "cable": (
                3,
                ["B0FXKF11B1", "B0CWH33BSK", "B0B2PR2QD4"],
            ),
        }
        for section, (count, asin_order) in expected.items():
            group = load_group(AFFILIATE_FILE, section)
            self.assertEqual(count, len(group.products))
            actual = [product.urls[0].split("/dp/")[1].split("/")[0] for product in group.products]
            self.assertEqual(asin_order, actual)
            self.assertTrue(all(product.text.startswith("▼") for product in group.products))

    def test_section_stops_at_next_marker(self):
        battery = load_group(AFFILIATE_FILE, "battery")
        self.assertNotIn("Anker Nano II", battery.raw_text)
        adapter = load_group(AFFILIATE_FILE, "adapter")
        self.assertNotIn("CIO フラットスパイラル", adapter.raw_text)


if __name__ == "__main__":
    unittest.main()
