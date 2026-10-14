import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class GasDispatchContractTest(unittest.TestCase):
    def test_actions_uses_gas_payload_without_scheduled_polling(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "info-viewer-queue.yml").read_text(encoding="utf-8")

        self.assertNotIn("schedule:", workflow)
        self.assertIn("timeout-minutes: 90", workflow)
        self.assertIn('INPUT_MAX_ITEMS: "4"', workflow)
        self.assertIn("github.event.client_payload.video_url", workflow)
        self.assertIn("ref: main", workflow)

    def test_gas_polls_target_sheet_and_keeps_secret_out_of_source(self):
        gas_source = (
            PROJECT_ROOT / "scripts" / "info_viewer" / "google_apps_script" / "Code.js"
        ).read_text(encoding="utf-8")

        self.assertIn("1cw6RC1XX4nAYvfZrBq7nmTtrr2oGFsSI0r_pVIxGxAc", gas_source)
        self.assertIn("everyMinutes(1)", gas_source)
        self.assertIn("x-info-viewer-gas-secret", gas_source)
        self.assertIn("PropertiesService.getScriptProperties()", gas_source)
        self.assertNotIn("ghp_", gas_source)

    def test_vercel_routes_gas_request_to_repository_dispatch(self):
        api_source = (PROJECT_ROOT / "api" / "info-viewer.js").read_text(encoding="utf-8")

        self.assertIn("INFO_VIEWER_GAS_SECRET", api_source)
        self.assertIn("gas-sheet-watcher", api_source)
        self.assertIn("trigger-from-appsheet-info-viewer", api_source)
        self.assertIn("client_payload", api_source)


if __name__ == "__main__":
    unittest.main()
