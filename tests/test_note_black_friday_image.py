import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py"
)
spec = importlib.util.spec_from_file_location("note_draft_black_friday_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BlackFridayImageTests(unittest.TestCase):
    def test_各タイトル表記で共通画像を選ぶ(self):
        titles = [
            "アマゾンブラックフライデー 2026 おすすめ",
            "Amazon ブラックフライデー 2026 iPad",
            "Ａｍａｚｏｎ　ブラック　フライデー",
            "Amazon Black Friday 2026",
            "amazon BLACK-FRIDAY セール",
        ]
        for title in titles:
            with self.subTest(title=title):
                path = module._black_friday_top_image_for_title(title)
                self.assertEqual(path, module.BLACK_FRIDAY_TOP_IMAGE)
                self.assertTrue(path.is_file())

    def test_タイトル以外の本文では画像を切り替えない(self):
        markdown = "# 通常のiPadレビュー\n\nAmazon ブラックフライデーの参考情報。"
        title, _ = module.extract_title_and_body(markdown)
        self.assertIsNone(module._black_friday_top_image_for_title(title))

    def test_通常タイトルではAmazon画像処理に戻す(self):
        for title in ["iPadのレビュー", "Amazon プライムデーおすすめ", "", "金曜日の買い物"]:
            with self.subTest(title=title):
                self.assertIsNone(module._black_friday_top_image_for_title(title))

    def test_編集画面の誤判定を無視し公開設定画面を待つ(self):
        page = Mock()
        states = [
            {"ready": True, "reason": "tag_input_candidate", "url": "https://editor.note.com/notes/n123/edit/"},
            {"ready": False, "reason": "not_ready", "url": "https://editor.note.com/notes/n123/publish/"},
            {"ready": True, "reason": "final_post_button", "url": "https://editor.note.com/notes/n123/publish/"},
        ]
        with patch.object(module, "_get_publish_settings_ready_state", side_effect=states) as probe:
            result = module._wait_for_publish_settings_ready(page, timeout_ms=1000, poll_ms=100)
        self.assertEqual(result, "final_post_button")
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(page.wait_for_timeout.call_count, 2)


if __name__ == "__main__":
    unittest.main()
