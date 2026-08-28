from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "public/index.html"


class SeoNameChangeUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.modal_html = cls.html.split("{seoRenameOpen && (", 1)[1].split("{bulkReplaceOpen && (", 1)[0]

    def test_context_menu_and_resizable_modal_are_connected(self):
        for fragment in (
            "SEO名称変更",
            "onSeoRename",
            "openSeoRenameModal",
            "seoRenameModalRect",
            "startSeoRenameModalResize",
            "SEO名称変更画面の上端をドラッグして高さを変更",
            "SEO名称変更画面の右端をドラッグして幅を変更",
            "SEO名称変更画面の左下をドラッグして大きさを変更",
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
            "onClick={() => { setSeoRenameActiveId(row.id); setSeoRenamePreviewMode('after'); }}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)

    def test_preview_boundary_and_target_panel_can_be_resized_or_toggled(self):
        for fragment in (
            "const [seoRenameSidebarOpen, setSeoRenameSidebarOpen] = useState(false)",
            "対象記事パネルを開く",
            "対象記事パネルを閉じる",
            "startSeoRenamePreviewResize",
            "フォームと記事プレビューの境界をドラッグして幅を変更",
            "--seo-preview-width",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)

    def test_amazon_url_is_an_icon_link_and_eye_icon_is_removed(self):
        for fragment in (
            "href={row.amazonUrl}",
            'target="_blank"',
            'rel="noopener noreferrer"',
            "Amazonを開く: ${row.amazonUrl}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.modal_html)
        self.assertNotIn("目のアイコン", self.modal_html)
        self.assertNotIn("{row.amazonUrl || 'Amazonリンク未検出'}", self.modal_html)

    def test_modal_uses_blog_vercel_purple_instead_of_teal(self):
        self.assertIn("#7C4DFF", self.modal_html)
        self.assertIn("purple-", self.modal_html)
        self.assertNotIn("teal-", self.modal_html)


if __name__ == "__main__":
    unittest.main()
