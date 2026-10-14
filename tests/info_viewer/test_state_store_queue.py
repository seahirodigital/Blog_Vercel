import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = PROJECT_ROOT / "scripts" / "info_viewer" / "modules"
PACKAGE_NAME = "info_viewer_state_test_modules"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(MODULES_ROOT)]
sys.modules[PACKAGE_NAME] = package


def _load_module(module_name: str):
    full_name = f"{PACKAGE_NAME}.{module_name}"
    module_path = MODULES_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(full_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"テスト対象を読み込めません: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_load_module("onedrive_writer")
state_store = _load_module("state_store")


def _record(video_id: str, status: str, published_at: str, **overrides):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    record = {
        "active": True,
        "status": status,
        "videoUrl": video_url,
        "normalizedVideoUrl": video_url,
        "videoTitle": video_id,
        "channelName": "テスト",
        "publishedAt": published_at,
        "videoUpdatedAt": published_at,
        "nextRetryAt": "2026-10-14T00:00:00Z",
        "attemptCount": 0,
    }
    record.update(overrides)
    return video_url, record


class StateStoreQueueTest(unittest.TestCase):
    def test_processing_cutoff_ignores_old_queue_and_keeps_new_video(self):
        old_url = "https://www.youtube.com/watch?v=old-before-cutoff"
        new_url = "https://www.youtube.com/watch?v=new-after-cutoff"
        videos = [
            {
                "video_url": old_url,
                "video_title": "過去動画",
                "channel_name": "テスト",
                "published_at": "2026-10-14T12:00:00Z",
                "video_updated_at": "2026-10-14T12:00:00Z",
                "status": "",
            },
            {
                "video_url": new_url,
                "video_title": "新着動画",
                "channel_name": "テスト",
                "published_at": "2026-10-14T17:00:00Z",
                "video_updated_at": "2026-10-14T17:00:00Z",
                "status": "",
            },
        ]
        state = {"videos": {}}

        with (
            patch.object(state_store, "PROCESS_AFTER_VALUE", "2026-10-14T16:35:35Z"),
            patch.object(state_store, "_now", return_value=datetime(2026, 10, 14, 18, tzinfo=timezone.utc)),
        ):
            stats = state_store.sync_target_videos(state, videos, {})
            selected = state_store.list_processable_videos(state, max_items=4)

        self.assertEqual(stats["ignoredBeforeCutoff"], 1)
        self.assertFalse(state["videos"][old_url]["active"])
        self.assertEqual(state["videos"][old_url]["status"], state_store.INACTIVE_STATUS)
        self.assertEqual([item["video_url"] for item in selected], [new_url])

    def test_manual_trigger_can_process_video_before_cutoff(self):
        video_url = "https://www.youtube.com/watch?v=manual-before-cutoff"
        videos = [{
            "video_url": video_url,
            "video_title": "手動指定",
            "channel_name": "テスト",
            "published_at": "2026-10-13T00:00:00Z",
            "video_updated_at": "2026-10-13T00:00:00Z",
            "status": state_store.MANUAL_TRIGGER_STATUS,
        }]
        state = {"videos": {}}

        with (
            patch.object(state_store, "PROCESS_AFTER_VALUE", "2026-10-14T16:35:35Z"),
            patch.object(state_store, "_now", return_value=datetime(2026, 10, 14, 18, tzinfo=timezone.utc)),
        ):
            state_store.sync_target_videos(state, videos, {})
            selected = state_store.list_processable_videos(state, max_items=1)

        self.assertEqual([item["video_url"] for item in selected], [video_url])

    def test_pending_new_videos_are_selected_before_failed_retries(self):
        failed_url, failed = _record(
            "failed-old",
            state_store.FAILED_STATUS,
            "2026-10-13T00:00:00Z",
            attemptCount=4,
        )
        older_url, older = _record(
            "pending-older",
            state_store.PENDING_STATUS,
            "2026-10-14T01:00:00Z",
        )
        newer_url, newer = _record(
            "pending-newer",
            state_store.PENDING_STATUS,
            "2026-10-14T02:00:00Z",
        )
        state = {"videos": {failed_url: failed, older_url: older, newer_url: newer}}

        with patch.object(state_store, "_now", return_value=datetime(2026, 10, 14, 3, tzinfo=timezone.utc)):
            selected = state_store.list_processable_videos(state, max_items=2)

        self.assertEqual(
            [item["video_url"] for item in selected],
            [newer_url, older_url],
        )

    def test_manual_priority_remains_first(self):
        pending_url, pending = _record(
            "pending-newer",
            state_store.PENDING_STATUS,
            "2026-10-14T02:00:00Z",
        )
        manual_url, manual = _record(
            "manual-older",
            state_store.FAILED_STATUS,
            "2026-10-12T00:00:00Z",
            manualPriorityAt="2026-10-14T02:30:00Z",
        )
        state = {"videos": {pending_url: pending, manual_url: manual}}

        with patch.object(state_store, "_now", return_value=datetime(2026, 10, 14, 3, tzinfo=timezone.utc)):
            selected = state_store.list_processable_videos(state, max_items=1)

        self.assertEqual(selected[0]["video_url"], manual_url)

    def test_failed_retry_wait_uses_exponential_backoff(self):
        video_url, record = _record(
            "retry",
            state_store.PROCESSING_STATUS,
            "2026-10-14T00:00:00Z",
            attemptCount=3,
        )
        state = {"videos": {video_url: record}}
        fixed_now = datetime(2026, 10, 14, 3, tzinfo=timezone.utc)

        with patch.object(state_store, "_now", return_value=fixed_now):
            result = state_store.mark_retry(
                state,
                video_url,
                stage="apify",
                error="字幕なし",
                run_id="test-run",
                wait_seconds=3600,
                status=state_store.FAILED_STATUS,
            )

        self.assertEqual(
            state_store._parse_iso(result["nextRetryAt"]),
            fixed_now + timedelta(hours=4),
        )


if __name__ == "__main__":
    unittest.main()
