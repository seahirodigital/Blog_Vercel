import contextlib
import importlib.util
import io
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py"
)
spec = importlib.util.spec_from_file_location("note_ogp_retry_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OGPRepeatTests(unittest.TestCase):
    def test_未展開が残っても最大5回で止まる(self):
        page = Mock()
        url = "https://amzn.to/example"
        page.evaluate.side_effect = lambda script, *args: [url] if script == "window.noteFormatter.extractUrls()" else (True if "setCaretAtUrlEnd" in script else None)
        log = io.StringIO()
        with patch.dict(os.environ, {"NOTE_TARGET": "blog_main"}), contextlib.redirect_stdout(log):
            count = module.process_ogp_urls(page)
        self.assertEqual(count, 5)
        self.assertEqual(page.keyboard.press.call_count, 5)
        self.assertEqual(page.wait_for_timeout.call_args_list.count(unittest.mock.call(600)), 5)
        self.assertEqual(page.wait_for_timeout.call_args_list.count(unittest.mock.call(5000)), 5)
        self.assertIn("5回目終了時の未展開対象URL: 1種 / 1箇所", log.getvalue())
        self.assertNotIn("6回目終了時の未展開対象URL", log.getvalue())

    def test_残りがなくなれば早期終了する(self):
        page = Mock()
        extracts = iter([["https://link.amazon/example"], []])
        page.evaluate.side_effect = lambda script, *args: next(extracts) if script == "window.noteFormatter.extractUrls()" else (True if "setCaretAtUrlEnd" in script else None)
        with patch.dict(os.environ, {"NOTE_TARGET": "blog_main"}), contextlib.redirect_stdout(io.StringIO()):
            count = module.process_ogp_urls(page)
        self.assertEqual(count, 1)
        page.keyboard.press.assert_called_once_with("Enter")


if __name__ == "__main__":
    unittest.main()
