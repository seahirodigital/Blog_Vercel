import json
import hashlib
import unittest
from pathlib import Path

from scripts.accessories.affiliate_group import load_group
from scripts.accessories.job_schema import new_job, validate_job
from scripts.accessories.prompt_builder import parse_engine_result


class PromptAndJobTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        self.group = load_group(
            root / "scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt",
            "battery",
        )

    def valid_engine_json(self):
        return json.dumps(
            {
                "intro_sentence": "M5 iPad Proにおすすめのバッテリーを紹介します。",
                "products": [
                    {
                        "index": product.index,
                        "adapted_text": f"{product.text}\n\nM5 iPad Proにおすすめな理由として、持ち運びやすい選択肢です。",
                    }
                    for product in self.group.products
                ],
            },
            ensure_ascii=False,
        )

    def test_engine_result_must_match_product_order(self):
        result = parse_engine_result(
            self.valid_engine_json(),
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertEqual(2, len(result["adapted_product_texts"]))

    def test_engine_result_rejects_affiliate_disclaimer_in_reason(self):
        with self.assertRaisesRegex(ValueError, "禁止値"):
            data = json.loads(self.valid_engine_json())
            data["products"][0]["adapted_text"] += "\nAmazonのアソシエイトとして適格販売により収入を得ています。"
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_rejects_changed_url(self):
        data = json.loads(self.valid_engine_json())
        data["products"][0]["adapted_text"] = data["products"][0]["adapted_text"].replace("B0FS5XT48F", "B000000000")
        with self.assertRaisesRegex(ValueError, "URL"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
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
