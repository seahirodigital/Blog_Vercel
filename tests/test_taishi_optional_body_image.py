"""大志の記事画像がない場合の投稿処理を確認する。"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/pipeline'))
from modules.note_onedrive_assets import find_article_assets

spec = importlib.util.spec_from_file_location(
    'note_draft_poster', ROOT / 'scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py'
)
poster = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poster)


class OptionalBodyImageTest(unittest.TestCase):
    def test_asset_matching(self):
        entry = lambda name: {'name': name, 'file': {}}
        thumbnail = entry('A-01_サムネイル.jpeg')
        body, cover = find_article_assets('A-01_記事.md', [thumbnail, entry('A-010_サムネイル.png')])
        self.assertIsNone(body)
        self.assertEqual(cover, thumbnail)
        with self.assertRaises(ValueError):
            find_article_assets('A-01_記事.md', [thumbnail, entry('A-01_記事.png'), entry('A-01_記事.jpg')])
        with self.assertRaises(ValueError):
            find_article_assets('A-01_記事.md', [])

    def test_missing_image_inserts_toc_and_is_idempotent(self):
        class Keyboard:
            def press(self, key):
                pass

        class Page:
            keyboard = Keyboard()

            def wait_for_timeout(self, milliseconds):
                pass

        initial = {'ok': False, 'toc': False, 'intro': False, 'heading': '見出し'}
        complete = {'ok': False, 'toc': True, 'toc_before_heading': True, 'intro': False, 'heading': '見出し'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(poster, '_taishi_layout_status', side_effect=[initial, complete]), \
                 patch.object(poster, '_place_caret_at_first_body_heading', return_value='見出し'), \
                 patch.object(poster, '_insert_toc_by_slash_popup') as insert:
                result = poster._insert_taishi_toc_and_image(Page(), directory)
                self.assertTrue(result['image_skipped'])
                insert.assert_called_once()
            with patch.object(poster, '_taishi_layout_status', return_value=complete), \
                 patch.object(poster, '_insert_toc_by_slash_popup') as insert:
                result = poster._insert_taishi_toc_and_image(Page(), directory)
                self.assertTrue(result['already_exists'])
                insert.assert_not_called()

    def test_partial_existing_layout_stops(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(poster, '_taishi_layout_status', return_value={'ok': False, 'toc': True, 'intro': True}):
            with self.assertRaises(RuntimeError):
                poster._insert_taishi_toc_and_image(None, directory)


if __name__ == '__main__':
    unittest.main()
