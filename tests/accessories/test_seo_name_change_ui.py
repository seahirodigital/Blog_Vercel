from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "public/index.html"


class SeoNameChangeUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def test_context_menu_and_three_column_modal_are_connected(self):
        for fragment in (
            "SEO名称変更",
            "onSeoRename",
            "openSeoRenameModal",
            "lg:grid-cols-[240px_minmax(520px,1.2fr)_minmax(360px,1fr)]",
            "検索キーワード",
            "記事ビューアー",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)

    def test_amazon_ogp_title_length_is_configurable_and_persistent(self):
        for fragment in (
            "SEO_RENAME_TITLE_LENGTH_STORAGE_KEY",
            "SEO_RENAME_DEFAULT_TITLE_LENGTH = 40",
            "findFirstAmazonUrl",
            "truncateUnicodeText",
            "fetch(`/api/ogp?url=${encodeURIComponent(amazonUrl)}`",
            "文字数を適用",
            "replaceReady",
            "置換候補を取得できていません",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)

    def test_replace_save_undo_and_preview_controls_exist(self):
        for fragment in (
            "handleSeoReplaceRow",
            "handleSeoReplaceChecked",
            "handleSeoReplaceAll",
            "handleSeoUndoRow",
            "現状",
            "変換後",
            "選択記事を置換",
            "全てを置換",
            "目のアイコン",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)


if __name__ == "__main__":
    unittest.main()
