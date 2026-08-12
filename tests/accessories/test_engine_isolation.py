import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class EngineIsolationTest(unittest.TestCase):
    def test_common_runner_does_not_import_gemini_at_module_load(self):
        source = (ROOT / "scripts/accessories/main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        imported_names = {
            alias.name
            for node in top_level_imports
            for alias in node.names
        }
        self.assertNotIn("gemini_engine", imported_names)


if __name__ == "__main__":
    unittest.main()
