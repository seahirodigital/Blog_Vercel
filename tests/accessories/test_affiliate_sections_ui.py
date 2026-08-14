import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AffiliateSectionsUiTest(unittest.TestCase):
    def test_all_sections_round_trip_in_original_order(self):
        source = (
            "===MEMO1===\nメモ\n\n"
            "===battery===\n説明\n▼商品\nhttps://example.com/a\n\n"
            "===adapter===\n充電器説明\n"
        )
        script = (
            "import {parseAffiliateSections,serializeAffiliateSections} from './lib/accessories-core.js';"
            f"const source={json.dumps(source, ensure_ascii=False)};"
            "const sections=parseAffiliateSections(source);"
            "console.log(JSON.stringify({sections,roundTrip:serializeAffiliateSections(sections)}));"
        )
        result = subprocess.run(
            ["node", "--experimental-default-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        self.assertEqual(["MEMO1", "battery", "adapter"], [item["id"] for item in data["sections"]])
        self.assertEqual(["メモ1", "バッテリー", "充電器"], [item["label"] for item in data["sections"]])
        self.assertEqual(source, data["roundTrip"])

    def test_editing_names_match_serialized_markers_and_support_new_japanese_tabs(self):
        source = (
            "===MEMO1===\nメモ\n\n"
            "===battery===\nバッテリー本文\n\n"
            "===SSD===\nSSD本文\n"
        )
        script = (
            "import {normalizeAffiliateSectionsForEditing,parseAffiliateSections,serializeAffiliateSections} "
            "from './lib/accessories-core.js';"
            f"const source={json.dumps(source, ensure_ascii=False)};"
            "const sections=normalizeAffiliateSectionsForEditing(parseAffiliateSections(source));"
            "console.log(JSON.stringify({sections,serialized:serializeAffiliateSections(sections)}));"
        )
        result = subprocess.run(
            ["node", "--experimental-default-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        self.assertEqual(["MEMO1", "バッテリー", "SSD"], [item["id"] for item in data["sections"]])
        self.assertIn("===バッテリー===", data["serialized"])
        self.assertIn("===SSD===", data["serialized"])
        self.assertNotIn("===battery===", data["serialized"])

    def test_ui_uses_section_array_instead_of_memo_only_object(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        api = (ROOT / "api/affiliate-links.js").read_text(encoding="utf-8")
        for fragment in (
            "fetchAffiliateSections()",
            "saveAffiliateSections(sections)",
            "sections.map(section =>",
            "{section.label}",
            "JSON.stringify({ sections })",
            'className="aff-tab-add"',
            "onContextMenu={event => openTabMenu(event, section)}",
            "名前を編集",
            "deleteSection",
        ):
            self.assertIn(fragment, html)
        self.assertIn("normalizeAffiliateSectionsForEditing(parseAffiliateSections(await r.text()))", api)
        self.assertIn("parseAffiliateSections(await r.text())", api)
        self.assertIn("serializeAffiliateSections(sections)", api)
        self.assertNotIn("function parseMemos", api)


if __name__ == "__main__":
    unittest.main()
