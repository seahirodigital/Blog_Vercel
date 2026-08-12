import json
import hashlib
import unittest

from scripts.accessories.job_schema import new_job, validate_job
from scripts.accessories.prompt_builder import parse_engine_result


class PromptAndJobTest(unittest.TestCase):
    def test_engine_result_must_match_product_order(self):
        result = parse_engine_result(
            json.dumps(
                {
                    "spec_summary": "USB-C充電に対応します。",
                    "recommendations": [
                        {"index": 1, "reason": "45W出力です。"},
                        {"index": 2, "reason": "67W出力です。"},
                    ],
                },
                ensure_ascii=False,
            ),
            2,
        )
        self.assertEqual(2, len(result["recommendation_reasons"]))

    def test_engine_result_rejects_affiliate_disclaimer_in_reason(self):
        with self.assertRaisesRegex(ValueError, "禁止値"):
            parse_engine_result(
                json.dumps(
                    {
                        "spec_summary": "USB-C充電に対応します。",
                        "recommendations": [
                            {
                                "index": 1,
                                "reason": "Amazonのアソシエイトとして適格販売により収入を得ています。",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                1,
            )

    def test_job_schema_v2(self):
        master_values = {"周辺機器カテゴリID": "battery"}
        master_sha = hashlib.sha256(
            json.dumps(master_values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        prompt_content = "JSONだけを返してください"
        job = new_job(
            batch_id="batch-1",
            engine="MLX",
            parent={"id": "p1", "title": "親", "web_url": "https://example.com/p1"},
            category={
                "id": "battery",
                "name": "バッテリー",
                "affiliate_section": "battery",
                "template_file": "tpl_default.md",
            },
            master_snapshot={
                "spreadsheet_id": "sheet",
                "sheet_name": "周辺機器DB",
                "row_number": 2,
                "values": master_values,
                "sha256": master_sha,
            },
            prompt_snapshot={
                "id": "mlx-default",
                "revision": 1,
                "content": prompt_content,
                "sha256": hashlib.sha256(prompt_content.encode("utf-8")).hexdigest(),
            },
            article_title="親 バッテリーおすすめ：",
        )
        validate_job(job)
        self.assertEqual(2, job["schema_version"])
        self.assertEqual("記事化", job["registry"]["status"])

        job["master_snapshot"]["values"]["周辺機器カテゴリID"] = "cable"
        with self.assertRaisesRegex(ValueError, "スナップショット"):
            validate_job(job)


if __name__ == "__main__":
    unittest.main()
