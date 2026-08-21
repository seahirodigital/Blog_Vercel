import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INFO_VIEWER_ROOT = PROJECT_ROOT / "scripts" / "info_viewer"
if str(INFO_VIEWER_ROOT) not in sys.path:
    sys.path.insert(0, str(INFO_VIEWER_ROOT))

import manual_url
from modules import onedrive_writer, state_store


class ManualUrlTest(unittest.TestCase):
    def test_manual_url_is_normalized_without_using_regular_runner(self):
        normalized = manual_url._normalized_video_url(
            "https://www.youtube.com/shorts/abc123?feature=share"
        )

        self.assertEqual(normalized, "https://www.youtube.com/watch?v=abc123")

    def test_oembed_supplies_manual_channel_metadata(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "title": "手動処理テスト",
            "author_name": "Sample Channel",
            "author_url": "https://www.youtube.com/@sample",
            "thumbnail_url": "https://example.com/thumbnail.jpg",
        }

        with patch.object(manual_url.requests, "get", return_value=response) as request:
            result = manual_url._fetch_oembed(
                "https://www.youtube.com/watch?v=abc123"
            )

        request.assert_called_once()
        self.assertEqual(result["title"], "手動処理テスト")
        self.assertEqual(result["channel_name"], "Sample Channel")
        self.assertEqual(result["channel_url"], "https://www.youtube.com/@sample")

    def test_existing_article_is_found_by_normalized_url(self):
        saved_articles = [
            {
                "youtubeUrlNormalized": "https://www.youtube.com/watch?v=abc123",
                "relativePath": "Sample Channel/20260821_test.md",
            }
        ]

        article = manual_url._find_existing_article(saved_articles, "https://youtu.be/abc123?t=30")

        self.assertEqual(article["relativePath"], "Sample Channel/20260821_test.md")

    def test_gemini_candidates_remove_duplicate_tokens(self):
        candidates = (
            ("primary", "same-token"),
            ("secondary", "same-token"),
            ("tech", "different-token"),
        )

        with patch.object(manual_url, "GEMINI_TOKEN_CANDIDATES", candidates):
            result = manual_url._gemini_candidates()

        self.assertEqual(result, [("primary", "same-token"), ("tech", "different-token")])

    def test_manual_main_completes_without_calling_regular_runner(self):
        state = {"version": 1, "updatedAt": "", "videos": {}}
        upload_result = {
            "id": "article-1",
            "relativePath": "Sample Channel/20260821_test.md",
            "title": "手動処理テスト",
        }

        with (
            patch.object(
                manual_url,
                "parse_args",
                return_value=SimpleNamespace(video_url="https://youtu.be/abc123"),
            ),
            patch.object(manual_url, "APIFY_API_KEY", "test-apify-key"),
            patch.object(manual_url, "GEMINI_TOKEN_CANDIDATES", (("primary", "test-gemini-key"),)),
            patch.object(manual_url.onedrive_writer, "list_saved_articles", return_value=[]),
            patch.object(
                manual_url,
                "_fetch_oembed",
                return_value={
                    "title": "手動処理テスト",
                    "channel_name": "Sample Channel",
                    "channel_url": "https://www.youtube.com/@sample",
                    "thumbnail_url": "https://example.com/thumbnail.jpg",
                },
            ),
            patch.object(manual_url.state_store, "load_state", return_value=state),
            patch.object(manual_url.state_store, "save_state"),
            patch.object(
                manual_url.apify_fetcher,
                "get_transcript",
                return_value={
                    "ok": True,
                    "transcript": {
                        "title": "手動処理テスト",
                        "captions": "文字起こし本文",
                        "url": "https://www.youtube.com/watch?v=abc123",
                    },
                },
            ),
            patch.object(
                manual_url.gemini_formatter,
                "format_transcript",
                return_value={"ok": True, "markdown": "# 手動処理テスト"},
            ),
            patch.object(
                manual_url.onedrive_writer,
                "upload_markdown",
                return_value=upload_result,
            ) as upload,
            patch.object(manual_url.notion_writer, "is_configured", return_value=False),
            patch.object(manual_url, "_save_github_output"),
        ):
            result = manual_url.main()

        self.assertEqual(result, 0)
        upload.assert_called_once()
        normalized_url = "https://www.youtube.com/watch?v=abc123"
        self.assertEqual(state["videos"][normalized_url]["status"], state_store.DONE_STATUS)

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
