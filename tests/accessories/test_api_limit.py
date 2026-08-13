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

    def test_markdown_soft_breaks_are_rendered_without_modifying_saved_content(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        self.assertIn("breaks: true", html)
        self.assertIn("保存するMarkdown本文に<br>は追加しない", html)
        self.assertIn("警告あり・出力済み", html)
        self.assertIn("job.generationErrors.map", html)

        conclusion_builder = (ROOT / "scripts/accessories/conclusion_builder.py").read_text(encoding="utf-8")
        article_assembler = (ROOT / "scripts/accessories/article_assembler.py").read_text(encoding="utf-8")
        self.assertNotIn("<br>", conclusion_builder)
        self.assertNotIn("<br>", article_assembler)

    def test_api_accepts_batch_status_without_fixed_job_limit(self):
        source = (ROOT / "api/accessories.js").read_text(encoding="utf-8")
        self.assertIn("queryValue(req.query.batchId)", source)
        self.assertIn("await listRegistryJobs()", source)
        self.assertIn("articleId: job.result?.article_id || ''", source)
        self.assertNotIn("ids.length > 5", source)
        self.assertNotIn("categoryIds.length > 5", source)

    def test_accessory_generation_report_can_be_reopened_from_folder_menu(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        for fragment in (
            "const ACCESSORY_REPORTS_STORAGE_KEY = 'sb_accessoryReports'",
            "function loadAccessoryReports()",
            "function saveAccessoryReport(report)",
            "function accessoryJobFolderPath(job)",
            "`\u5468\u8fba\u6a5f\u5668/${timestamp}_${titlePrefix}`",
            "周辺機器の生成結果",
            "onOpenAccessoryReport && onOpenAccessoryReport(folderCtxMenu.path)",
            "const openAccessoryReport = useCallback(async (folderPath = '') =>",
            "new URLSearchParams({ action: 'status', batchId: report.batchId })",
            "onOpenAccessoryReport={openAccessoryReport}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_root_article_limit_is_configurable_in_steps_of_five(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        api = (ROOT / "api/articles.js").read_text(encoding="utf-8")
        for fragment in (
            "const ROOT_ARTICLE_LIMIT_STORAGE_KEY = 'sb_rootArticleLimit'",
            "const ROOT_ARTICLE_DEFAULT_LIMIT = 5",
            "function normalizeRootArticleLimit(value)",
            "OneDrive直下の読み込む記事数",
            "changeRootArticleLimit(-5)",
            "changeRootArticleLimit(5)",
            "includeAllArticles: true",
            "articleLimit: rootArticleLimit",
            "onContextMenu={handleRootContextMenu}",
            "onChangeRootArticleLimit={changeRootArticleLimit}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertIn("const articleLimit = safeNumber(options.articleLimit, 0, 2000)", api)
        self.assertIn("articles.slice(0, articleLimit)", api)
        self.assertIn("if (options.includeAll || options.includeAllArticles) return true", api)
        self.assertIn("includeAllArticles: allArticles", api)

    def test_accessory_checkbox_selection_supports_all_and_category_toggles(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        for fragment in (
            "const accessoryAvailableSelections = useMemo",
            "const accessoryBulkCategories = useMemo",
            "const toggleAccessoryScope = useCallback((categoryId = '') =>",
            "[{ id: '', name: 'すべて' }, ...accessoryBulkCategories]",
            "onClick={() => toggleAccessoryScope(scope.id)}",
            "{scope.name} {allSelected ? 'OFF' : 'ON'}",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

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

    def test_note_uploaded_folder_is_visible_and_defaults_to_latest_five(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        api = (ROOT / "api/articles.js").read_text(encoding="utf-8")
        self.assertNotIn("SKIPPED_FOLDER_KEYWORDS", api)
        self.assertIn("const NOTE_UPLOADED_DEFAULT_LIMIT = 5", html)
        self.assertIn("function isNoteUploadedFolderPath(folderPath)", html)
        self.assertIn("? { includeAll: true, limit: NOTE_UPLOADED_DEFAULT_LIMIT }", html)
        self.assertIn("const FOLDER_LOAD_LIMIT_OPTIONS = [5, 10, 25, 50, 100]", html)
        self.assertIn("NOTE_UPLOADED_VISIBILITY_MIGRATION_KEY", html)
        self.assertIn("if (isNoteUploadedFolderPath(path)) saved.delete(path)", html)
        self.assertIn("allFolderPaths.map(fp =>", html)

    def test_folder_delete_is_scoped_confirmed_and_supports_multiple_selection(self):
        html = (ROOT / "public/index.html").read_text(encoding="utf-8")
        api = (ROOT / "api/articles.js").read_text(encoding="utf-8")
        for fragment in (
            "function normalizeDeletableFolderPath(value)",
            "記事ルートフォルダは削除できません",
            "function collapseNestedFolderPaths(values)",
            "const fullPath = `${baseFolder}/${safePath}`",
            "if (!item?.id || !item.folder)",
            "if (Array.isArray(folderPaths))",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, api)
        for fragment in (
            "const [folderSelectMode, setFolderSelectMode] = useState(false)",
            "const [selectedFolderPaths, setSelectedFolderPaths] = useState(new Set())",
            "フォルダ {selectedFolderPaths.size}件選択",
            "setConfirmFolderDelete(getFolderContextTargets(folderCtxMenu.path))",
            "その中の記事・子フォルダをOneDriveのごみ箱へ移動します",
            "onDeleteFolders={handleDeleteFolders}",
            "deleteFoldersApi(targets)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)


if __name__ == "__main__":
    unittest.main()
