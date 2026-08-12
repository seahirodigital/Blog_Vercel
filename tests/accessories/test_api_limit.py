from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ApiLimitTest(unittest.TestCase):
    def test_vercel_function_count_stays_within_hobby_limit(self):
        api_files = sorted((ROOT / "api").glob("*.js"))
        self.assertLessEqual(len(api_files), 12)
        self.assertIn(ROOT / "api/accessories.js", api_files)
        self.assertNotIn(ROOT / "api/trigger-info-viewer.js", api_files)

    def test_sidebar_right_click_reaches_accessory_creation_buttons(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        required_fragments = [
            "onContextMenu={(e) => handleContextMenu(e, article)}",
            "onCreateAccessory && onCreateAccessory(ctxMenu.article)",
            "onCreateAccessory={openAccessoryModal}",
            "createAccessoryJobs('MLX')",
            "createAccessoryJobs('Gemini')",
            "MLXで作成",
            "Geminiで作成",
        ]
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_accessory_creation_calls_single_api_function(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/accessories?action=create'", html)


if __name__ == "__main__":
    unittest.main()
