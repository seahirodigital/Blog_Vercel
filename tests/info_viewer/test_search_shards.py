import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "info_viewer" / "export_static_site.py"
SPEC = importlib.util.spec_from_file_location("info_viewer_export_test", SOURCE)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class SearchShardTest(unittest.TestCase):
    def test_preserves_full_text_and_produces_bounded_assets(self):
        items = [{"id": f"article-{index}", "text": f"日本語の文字起こし {index}"} for index in range(100)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "search.json"
            exporter._write_search_index(items, path)
            manifest = json.loads(path.read_text(encoding="utf-8"))
            restored = []
            for name in manifest["parts"]:
                shard = path.parent / name
                self.assertLess(shard.stat().st_size, exporter.SEARCH_ASSET_MAX_BYTES)
                restored.extend(json.loads(shard.read_text(encoding="utf-8")))
        self.assertEqual({item["id"]: item for item in restored}, {item["id"]: item for item in items})


if __name__ == "__main__":
    unittest.main()
