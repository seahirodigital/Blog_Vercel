import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APIFY_FETCHER_PATH = PROJECT_ROOT / "scripts" / "info_viewer" / "modules" / "apify_fetcher.py"
SPEC = importlib.util.spec_from_file_location("info_viewer_apify_fetcher", APIFY_FETCHER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"テスト対象を読み込めません: {APIFY_FETCHER_PATH}")
apify_fetcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = apify_fetcher
SPEC.loader.exec_module(apify_fetcher)


class ApifyFetcherTest(unittest.TestCase):
    def test_uses_bearer_auth_without_token_or_memory_query(self):
        response = Mock()
        response.status_code = 201
        response.json.return_value = [
            {
                "title": "テスト動画",
                "videoId": "abc123",
                "captions": [{"text": "最初"}, {"text": "次"}],
            }
        ]
        response.raise_for_status.return_value = None

        with patch.object(apify_fetcher.requests, "post", return_value=response) as post:
            result = apify_fetcher.get_transcript(
                "https://www.youtube.com/watch?v=abc123",
                "new-api-key",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["transcript"]["captions"], "最初 次")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer new-api-key")
        self.assertNotIn("token", kwargs["params"])
        self.assertNotIn("memory", kwargs["params"])
        self.assertEqual(kwargs["params"]["maxItems"], 1)

    def test_retries_temporary_server_error(self):
        temporary = Mock()
        temporary.status_code = 503
        success = Mock()
        success.status_code = 201
        success.raise_for_status.return_value = None
        success.json.return_value = [{"captions": "本文", "videoId": "abc123"}]

        with patch.object(apify_fetcher, "MAX_RETRIES", 3):
            with patch.object(apify_fetcher, "RETRY_WAIT_SECONDS", 1):
                with patch.object(apify_fetcher.time, "sleep") as sleep:
                    with patch.object(
                        apify_fetcher.requests,
                        "post",
                        side_effect=[temporary, success],
                    ) as post:
                        result = apify_fetcher.get_transcript(
                            "https://www.youtube.com/watch?v=abc123",
                            "new-api-key",
                        )

        self.assertTrue(result["ok"])
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_does_not_retry_permission_error(self):
        response = Mock()
        response.status_code = 403
        response.text = '{"error":{"type":"insufficient-permissions"}}'
        error = requests.HTTPError("403 Client Error", response=response)
        response.raise_for_status.side_effect = error

        with patch.object(apify_fetcher, "MAX_RETRIES", 3):
            with patch.object(apify_fetcher.time, "sleep") as sleep:
                with patch.object(
                    apify_fetcher.requests,
                    "post",
                    return_value=response,
                ) as post:
                    result = apify_fetcher.get_transcript(
                        "https://www.youtube.com/watch?v=abc123",
                        "restricted-key",
                    )

        self.assertFalse(result["ok"])
        self.assertEqual(result["httpStatus"], 403)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
