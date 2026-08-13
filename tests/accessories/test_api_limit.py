from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ApiLimitTest(unittest.TestCase):
    def test_vercel_function_count_stays_within_hobby_limit(self):
        api_files = sorted((ROOT / "api").glob("*.js"))
        self.assertLessEqual(len(api_files), 12)
        self.assertIn(ROOT / "api/accessories.js", api_files)
        self.assertNotIn(ROOT / "api/trigger-info-viewer.js", api_files)

    def test_sidebar_right_click_reaches_accessory_creation_buttons(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        required_fragments = [
            "onContextMenu={(e) => handleContextMenu(e, article)}",
            "onCreateAccessory && onCreateAccessory(getContextTargetArticles(ctxMenu.article))",
            "onCreateAccessory={openAccessoryModal}",
            "createAccessoryJobs('MLX')",
            "createAccessoryJobs('Gemini')",
            "MLXで作成",
            "Geminiで作成",
            "blogvercel-mlx://run?",
            "Terminalをもう一度開く",
            "refreshAccessoryJobs",
            "accessoryProgressPercent",
            "周辺機器記事作成{getContextTargetIds(ctxMenu.article).length > 1",
            "batch_id",
            "parents: selectedParents",
            "accessorySelectionKey(parent.id, category.id)",
        ]
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertNotIn("作成する周辺機器をチェックしてください（最大5件）。", html)
        self.assertNotIn("category.productCount", html)
        self.assertNotIn("category.products?.length", html)

    def test_accessory_creation_calls_single_api_function(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/accessories?action=create'", html)

    def test_api_accepts_batch_status_without_fixed_job_limit(self):
        source = (ROOT / "api/accessories.js").read_text(encoding="utf-8")
        self.assertIn("queryValue(req.query.batchId)", source)
        self.assertIn("await listRegistryJobs()", source)
        self.assertNotIn("ids.length > 5", source)
        self.assertNotIn("categoryIds.length > 5", source)

    def test_folder_all_period_setting_is_inherited_and_child_count_is_refreshed(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        api = (ROOT / "api/articles.js").read_text(encoding="utf-8")
        for fragment in (
            "function resolveFolderLoadSetting(folderPath, settings = {})",
            "inheritedFrom: candidate !== normalizedPath ? candidate : ''",
            "resolveFolderLoadSetting(path, folderLoadSettings)",
            "typeof updater === 'function' ? updater(current) : updater",
            "onChangeFolderLoadSetting(path, requested)",
            "childCount: Number.isFinite(data.currentChildCount)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertIn("currentChildCount: items.length", api)
        self.assertIn("currentChildCount: listing.currentChildCount", api)


if __name__ == "__main__":
    unittest.main()
