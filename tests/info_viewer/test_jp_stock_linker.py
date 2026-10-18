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
GOOGLE = jp_stock_linker.AmericanListedCompany(
    name="Alphabet Inc.",
    aliases=("Alphabet", "Google", "グーグル"),
)
META = jp_stock_linker.AmericanListedCompany(
    name="Meta Platforms, Inc.",
    aliases=("Meta Platforms", "Meta", "Facebook", "メタ"),
)
AMAZON = jp_stock_linker.AmericanListedCompany(name="Amazon.com, Inc.", aliases=("Amazon", "アマゾン"))
SPACEX = jp_stock_linker.AdditionalCompany(name="SpaceX", aliases=("SpaceX",))

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
    def test_links_toyota_as_a_moomoo_search_without_a_code_lookup(self):
        result = jp_stock_linker.link_markdown("トヨタは増益を見込む。", (TOYOTA,))

        self.assertEqual(
            result.markdown,
            "[トヨタ](ftmm://search?keyword=トヨタ)は増益を見込む。",
        )
        self.assertEqual(result.linked_count, 1)

    def test_links_us_and_non_listed_company_names_with_the_text_as_the_search_query(self):
        result = jp_stock_linker.link_markdown("GoogleとMeta、Amazon、SpaceXが市場を牽引する。", (GOOGLE, META, AMAZON, SPACEX))

        self.assertEqual(
            result.markdown,
            "[Google](ftmm://search?keyword=Google)と[Meta](ftmm://search?keyword=Meta)、[Amazon](ftmm://search?keyword=Amazon)、[SpaceX](ftmm://search?keyword=SpaceX)が市場を牽引する。",
        )
        self.assertEqual(result.linked_count, 4)

    def test_preserves_existing_links_and_code_fences(self):
        source = (
            "[トヨタ](https://example.com)とトヨタを比較する。\n"
            "`トヨタ`\n"
            "```text\n"
            "トヨタ\n"
            "```\n"
        )

        result = jp_stock_linker.link_markdown(source, (TOYOTA,))

        self.assertEqual(result.linked_count, 1)
        self.assertIn("[トヨタ](https://example.com)", result.markdown)
        self.assertIn("`トヨタ`", result.markdown)
        self.assertIn("```text\nトヨタ\n```", result.markdown)
        self.assertIn("[トヨタ](ftmm://search?keyword=トヨタ)を比較", result.markdown)

    def test_apify_style_code_block_remains_raw(self):
        source = "# 要約\n\nトヨタに注目。\n\n## Apify 取得文字起こし\n\n```text\nトヨタの原文\n```\n"

        result = jp_stock_linker.link_markdown(source, (TOYOTA,))

        self.assertIn("[トヨタ](ftmm://search?keyword=トヨタ)に注目。", result.markdown)
        self.assertIn("```text\nトヨタの原文\n```", result.markdown)
        self.assertNotIn("```text\n[トヨタ]", result.markdown)

    def test_links_multiple_companies_without_nesting_generated_links(self):
        source = "NTT、ソフトバンクグループ、サーバーワークス、ベイカレント・コンサルティング。"

        result = jp_stock_linker.link_markdown(source, MULTIPLE_COMPANIES)

        self.assertEqual(result.linked_count, 4)
        self.assertIn("[NTT](ftmm://search?keyword=NTT)", result.markdown)
        self.assertIn("[ソフトバンクグループ](ftmm://search?keyword=ソフトバンクグループ)", result.markdown)
        self.assertIn("[サーバーワークス](ftmm://search?keyword=サーバーワークス)", result.markdown)
        self.assertIn("[ベイカレント](ftmm://search?keyword=ベイカレント)", result.markdown)
        self.assertNotIn("[NTT[", result.markdown)

    def test_jpx_parser_keeps_only_domestic_common_stocks(self):
        companies = jp_stock_linker._companies_from_jpx_xlsx(_sample_jpx_xlsx())
        toyota = next(company for company in companies if company.code == "7203")

        self.assertEqual(toyota.name, "トヨタ自動車")
        self.assertIn("トヨタ", toyota.aliases)
        self.assertFalse(any(company.code == "1305" for company in companies))

    def test_parses_sec_companies_and_the_major_company_aliases(self):
        companies = jp_stock_linker._companies_from_sec_json(
            b'{"0":{"ticker":"GOOG","title":"Alphabet Inc."},"1":{"ticker":"META","title":"Meta Platforms, Inc."}}'
        )

        google = next(company for company in companies if company.name == "Alphabet Inc.")
        meta = next(company for company in companies if company.name == "Meta Platforms, Inc.")
        self.assertIn("Google", google.aliases)
        self.assertIn("Meta", meta.aliases)

    def test_keeps_additional_company_links_available_when_name_masters_are_unavailable(self):
        with (
            patch.object(jp_stock_linker, "load_japanese_listed_companies", side_effect=OSError("jpx offline")),
            patch.object(jp_stock_linker, "load_american_listed_companies", side_effect=OSError("sec offline")),
        ):
            result = jp_stock_linker.link_gemini_markdown("SpaceXとトヨタに注目する。")

        self.assertEqual(result.markdown, "[SpaceX](ftmm://search?keyword=SpaceX)とトヨタに注目する。")
        self.assertEqual(result.linked_count, 1)
        self.assertEqual(result.lookup_count, 0)
        self.assertEqual(result.error, "")


if __name__ == "__main__":
    unittest.main()
