import unittest

from scripts.accessories.onedrive_store import _decode_utf8_text


class OneDriveTextEncodingTest(unittest.TestCase):
    def test_decodes_japanese_affiliate_marker_as_utf8(self):
        source = "\ufeff===battery===\n▼モバイルバッテリー\nhttps://example.com/item\n"
        self.assertEqual(
            "===battery===\n▼モバイルバッテリー\nhttps://example.com/item\n",
            _decode_utf8_text(source.encode("utf-8")),
        )

    def test_rejects_non_utf8_content(self):
        with self.assertRaisesRegex(RuntimeError, "UTF-8"):
            _decode_utf8_text(b"\x81\x82\x83")


if __name__ == "__main__":
    unittest.main()
