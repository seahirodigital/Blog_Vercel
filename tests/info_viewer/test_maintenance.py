import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "info_viewer"))

with patch("dotenv.load_dotenv"):
    import runner
from modules import onedrive_writer, sheet_reader


class Worksheet:
    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def row_values(self, number):
        return self.rows[number - 1]

    def col_values(self, number):
        return [row[number - 1] for row in self.rows]

    def update_cell(self, row, col, value):
        self.writes.append((row, col, value))
        self.rows[row - 1][col - 1] = value


class MaintenanceTests(unittest.TestCase):
    def test_sheet_uses_current_url_row(self):
        sheet = Worksheet([["動画URL", "状況"], ["https://youtu.be/other", ""],
                           ["https://youtu.be/target", ""]])
        with patch.object(sheet_reader, "_get_worksheet", return_value=sheet):
            sheet_reader.update_video_status("id", 2, expected_video_url="https://www.youtube.com/watch?v=target")
        self.assertEqual(sheet.writes, [(3, 2, "完了")])

    def test_sheet_rejects_duplicate_url(self):
        sheet = Worksheet([["動画URL", "状況"], ["https://youtu.be/target", ""],
                           ["https://youtu.be/target", ""]])
        with patch.object(sheet_reader, "_get_worksheet", return_value=sheet):
            with self.assertRaises(ValueError):
                sheet_reader.update_video_status("id", 2, expected_video_url="https://youtu.be/target")
        self.assertEqual(sheet.writes, [])

    def test_sheet_rejects_movement_before_write(self):
        sheet = Worksheet([["動画URL", "状況"], ["https://youtu.be/target", ""]])
        original = sheet.col_values
        def move(column):
            values = original(column)
            sheet.rows.insert(1, ["https://youtu.be/other", ""])
            return values
        sheet.col_values = move
        with patch.object(sheet_reader, "_get_worksheet", return_value=sheet):
            with self.assertRaises(RuntimeError):
                sheet_reader.update_video_status("id", 2, expected_video_url="https://youtu.be/target")
        self.assertEqual(sheet.writes, [])

    def test_saved_done_article_missing_from_index_needs_publish(self):
        key = "https://www.youtube.com/watch?v=target"
        article = {"youtubeUrlNormalized": key, "fileId": "one", "lastModified": "date"}
        state = {"videos": {key: {"status": "done"}}}
        with patch.object(Path, "read_text", return_value=json.dumps({"articles": {}})):
            self.assertTrue(runner._viewer_needs_publish([article], state))
        state["videos"][key]["status"] = "failed"
        with patch.object(Path, "read_text", return_value=json.dumps({"articles": {}})):
            self.assertFalse(runner._viewer_needs_publish([article], state))

    def test_preview_cache_requires_matching_file_version(self):
        cache = onedrive_writer._local_preview_cache()
        self.assertTrue(cache)
        file_id, modified = next(iter(cache))
        self.assertNotIn((file_id, modified + "changed"), cache)
        self.assertNotIn((file_id + "changed", modified), cache)


if __name__ == "__main__":
    unittest.main()
