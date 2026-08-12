import unittest

from scripts.accessories.onedrive_store import child_folder_name


class ChildFolderTest(unittest.TestCase):
    def test_uses_jst_creation_minute_and_first_twenty_title_characters(self):
        job = {
            "created_at": "2026-08-12T14:03:45Z",
            "parent": {"title": "M5 iPad Pro レビュー比較違いまとめ"},
        }
        self.assertEqual("20260812_2303_M5 iPad Pro レビュー比較違い", child_folder_name(job))

    def test_removes_onedrive_invalid_characters(self):
        job = {
            "created_at": "2026-08-12T14:03:45+00:00",
            "parent": {"title": "製品/A:レビューまとめ"},
        }
        self.assertNotRegex(child_folder_name(job), r"[\\/:*?\"<>|]")


if __name__ == "__main__":
    unittest.main()
