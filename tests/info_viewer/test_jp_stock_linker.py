import importlib.util
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFO_VIEWER_ROOT = PROJECT_ROOT / "scripts" / "info_viewer"
if str(INFO_VIEWER_ROOT) not in sys.path:
    sys.path.insert(0, str(INFO_VIEWER_ROOT))

MODULE_PATH = INFO_VIEWER_ROOT / "modules" / "jp_stock_linker.py"
SPEC = importlib.util.spec_from_file_location("jp_stock_linker", MODULE_PATH)
jp_stock_linker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = jp_stock_linker
SPEC.loader.exec_module(jp_stock_linker)


TOYOTA = jp_stock_linker.JapaneseListedCompany(
    code="7203",
    name="トヨタ自動車",
    aliases=("トヨタ自動車", "トヨタ"),
)

MULTIPLE_COMPANIES = (
    jp_stock_linker.JapaneseListedCompany(code="9432", name="ＮＴＴ", aliases=("NTT",)),
    jp_stock_linker.JapaneseListedCompany(code="9984", name="ソフトバンクグループ", aliases=("ソフトバンクグループ",)),
    jp_stock_linker.JapaneseListedCompany(code="4434", name="サーバーワークス", aliases=("サーバーワークス",)),
    jp_stock_linker.JapaneseListedCompany(code="6532", name="ベイカレント", aliases=("ベイカレント",)),
)


def _sample_jpx_xlsx() -> bytes:
    shared_strings = [
        "日付", "コード", "銘柄名", "市場・商品区分",
        "20261031", "7203", "トヨタ自動車", "プライム（内国株式）",
        "1305", "ｉＦｒｅｅＥＴＦ ＴＯＰＩＸ（年１回決算型）", "ETF・ETN",
    ]
    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
    rows = (
        "<row r=\"1\"><c t=\"s\"><v>0</v></c><c t=\"s\"><v>1</v></c>"
        "<c t=\"s\"><v>2</v></c><c t=\"s\"><v>3</v></c></row>"
        "<row r=\"2\"><c t=\"s\"><v>4</v></c><c t=\"s\"><v>5</v></c>"
        "<c t=\"s\"><v>6</v></c><c t=\"s\"><v>7</v></c></row>"
        "<row r=\"3\"><c t=\"s\"><v>4</v></c><c t=\"s\"><v>8</v></c>"
        "<c t=\"s\"><v>9</v></c><c t=\"s\"><v>10</v></c></row>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            f"{shared_xml}</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            f"<sheetData>{rows}</sheetData></worksheet>",
        )
    return buffer.getvalue()


class JapaneseStockLinkerTest(unittest.TestCase):
    def test_links_toyota_only_after_yahoo_confirms_the_jp_code(self):
        looked_up = []

        def yahoo_lookup(alias, code):
            looked_up.append((alias, code))
            return alias == "トヨタ" and code == "7203"

        result = jp_stock_linker.link_markdown("トヨタは増益を見込む。", (TOYOTA,), yahoo_lookup)

        self.assertEqual(
            result.markdown,
            "[トヨタ](https://www.moomoo.com/ja/stock/7203-JP)は増益を見込む。",
        )
        self.assertEqual(result.linked_count, 1)
        self.assertEqual(looked_up, [("トヨタ", "7203")])

    def test_preserves_existing_links_and_code_fences(self):
        source = (
            "[トヨタ](https://example.com)とトヨタを比較する。\n"
            "`トヨタ`\n"
            "```text\n"
            "トヨタ\n"
            "```\n"
        )

        result = jp_stock_linker.link_markdown(source, (TOYOTA,), lambda _alias, _code: True)

        self.assertEqual(result.linked_count, 1)
        self.assertIn("[トヨタ](https://example.com)", result.markdown)
        self.assertIn("`トヨタ`", result.markdown)
        self.assertIn("```text\nトヨタ\n```", result.markdown)
        self.assertIn("[トヨタ](https://www.moomoo.com/ja/stock/7203-JP)を比較", result.markdown)

    def test_apify_style_code_block_remains_raw(self):
        source = "# 要約\n\nトヨタに注目。\n\n## Apify 取得文字起こし\n\n```text\nトヨタの原文\n```\n"

        result = jp_stock_linker.link_markdown(source, (TOYOTA,), lambda _alias, _code: True)

        self.assertIn("[トヨタ](https://www.moomoo.com/ja/stock/7203-JP)に注目。", result.markdown)
        self.assertIn("```text\nトヨタの原文\n```", result.markdown)
        self.assertNotIn("```text\n[トヨタ]", result.markdown)

    def test_links_multiple_companies_without_nesting_generated_links(self):
        source = "NTT、ソフトバンクグループ、サーバーワークス、ベイカレント・コンサルティング。"

        result = jp_stock_linker.link_markdown(source, MULTIPLE_COMPANIES, lambda _alias, _code: True)

        self.assertEqual(result.linked_count, 4)
        self.assertIn("[NTT](https://www.moomoo.com/ja/stock/9432-JP)", result.markdown)
        self.assertIn("[ソフトバンクグループ](https://www.moomoo.com/ja/stock/9984-JP)", result.markdown)
        self.assertIn("[サーバーワークス](https://www.moomoo.com/ja/stock/4434-JP)", result.markdown)
        self.assertIn("[ベイカレント](https://www.moomoo.com/ja/stock/6532-JP)", result.markdown)
        self.assertNotIn("[NTT[", result.markdown)

    def test_jpx_parser_keeps_only_domestic_common_stocks(self):
        companies = jp_stock_linker._companies_from_jpx_xlsx(_sample_jpx_xlsx())
        toyota = next(company for company in companies if company.code == "7203")

        self.assertEqual(toyota.name, "トヨタ自動車")
        self.assertIn("トヨタ", toyota.aliases)
        self.assertFalse(any(company.code == "1305" for company in companies))

    def test_keeps_original_markdown_when_the_jpx_master_is_unavailable(self):
        with patch.object(jp_stock_linker, "load_japanese_listed_companies", side_effect=OSError("offline")):
            result = jp_stock_linker.link_gemini_markdown("トヨタは増益を見込む。")

        self.assertEqual(result.markdown, "トヨタは増益を見込む。")
        self.assertEqual(result.linked_count, 0)
        self.assertEqual(result.lookup_count, 0)
        self.assertIn("offline", result.error)


if __name__ == "__main__":
    unittest.main()
