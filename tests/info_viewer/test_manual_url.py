import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFO_VIEWER_ROOT = PROJECT_ROOT / "scripts" / "info_viewer"
if str(INFO_VIEWER_ROOT) not in sys.path:
    sys.path.insert(0, str(INFO_VIEWER_ROOT))

import runner
from modules import apify_fetcher, onedrive_writer, state_store


class ManualUrlTest(unittest.TestCase):
    def setUp(self):
        self.channel = {
            "id": "sample-channel",
            "channel_name": "Sample Channel",
            "channel_url": "https://www.youtube.com/@sample",
            "gemini_profile": "invest",
        }

    def test_url_filter_compares_normalized_video_ids(self):
        args = SimpleNamespace(channel_name="", video_url="https://youtu.be/abc123?t=30")
        video = {"video_url": "https://www.youtube.com/watch?v=abc123"}

        self.assertTrue(runner._matches_filter(video, args))

    def test_manual_video_uses_detected_channel_metadata(self):
        apify_result = {
            "ok": True,
            "transcript": {
                "title": "手動処理テスト",
                "channel_name": "Sample Channel",
                "channel_url": "https://www.youtube.com/@sample",
                "published_at": "2026-08-21T00:00:00Z",
                "duration": "600",
                "thumbnail_url": "https://example.com/thumbnail.jpg",
            },
        }

        video = runner._build_manual_video(
            "https://www.youtube.com/shorts/abc123?feature=share",
            [self.channel],
            apify_result,
        )

        self.assertEqual(video["video_url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(video["channel_name"], "Sample Channel")
        self.assertEqual(video["gemini_profile"], "invest")
        self.assertIsNone(video["row_number"])

    def test_apify_result_keeps_channel_metadata_for_manual_video(self):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {
                "videoId": "abc123",
                "title": "手動処理テスト",
                "captions": "文字起こし本文",
                "channelName": "Sample Channel",
                "channelUrl": "https://www.youtube.com/@sample",
                "publishedAt": "2026-08-21T00:00:00Z",
                "durationSeconds": 600,
            }
        ]

        with patch.object(apify_fetcher.requests, "post", return_value=response):
            result = apify_fetcher.get_transcript(
                "https://www.youtube.com/watch?v=abc123",
                "test-api-key",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["transcript"]["channel_name"], "Sample Channel")
        self.assertEqual(result["transcript"]["channel_url"], "https://www.youtube.com/@sample")
        self.assertEqual(result["transcript"]["duration"], "600")

    def test_later_sheet_row_merges_with_manual_video_without_reprocessing(self):
        state = {"version": 1, "updatedAt": "", "videos": {}}
        manual_video = {
            "row_number": None,
            "video_url": "https://youtu.be/abc123",
            "video_title": "手動処理テスト",
            "published_at": "",
            "video_updated_at": "",
            "duration": "",
            "thumbnail_url": "",
            "status": "",
            "channel_name": "Sample Channel",
            "channel_url": "https://www.youtube.com/@sample",
            "gemini_profile": "invest",
        }

        with patch.object(state_store, "REQUIRE_NOTION_SAVE", False):
            first_sync = state_store.sync_target_videos(state, [manual_video], {})
            self.assertEqual(first_sync["added"], 1)

            normalized_url = onedrive_writer.normalize_youtube_url(manual_video["video_url"])
            sheet_video = {
                **manual_video,
                "row_number": 42,
                "video_url": "https://www.youtube.com/watch?v=abc123&feature=youtu.be",
            }
            article_map = {
                normalized_url: {
                    "youtubeUrlNormalized": normalized_url,
                    "relativePath": "Sample Channel/20260821_test.md",
                    "fileId": "article-1",
                    "title": "手動処理テスト",
                }
            }
            second_sync = state_store.sync_target_videos(state, [sheet_video], article_map)

        self.assertEqual(len(state["videos"]), 1)
        self.assertEqual(second_sync["added"], 0)
        self.assertEqual(state["videos"][normalized_url]["status"], state_store.DONE_STATUS)
        self.assertEqual(state["videos"][normalized_url]["rowNumber"], 42)
        self.assertEqual(
            state_store.list_processable_videos(state, video_url="https://youtu.be/abc123"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
