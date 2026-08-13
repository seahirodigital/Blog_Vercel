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
        intro_lines = self.group.section_intro.splitlines()
        intro_lines[0] = "M5 iPad Proにおすすめの" + intro_lines[0].replace("のおすすめ", "", 1)
        return json.dumps(
            {
                "intro_sentence": "M5 iPad Proにおすすめのバッテリーをお探しではありませんか？この記事では、M5 iPad Proにおすすめのバッテリーと商品情報をあわせて紹介します。",
                "adapted_section_intro": "\n".join(intro_lines),
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
        self.assertEqual(len(self.group.products), len(result["adapted_product_texts"]))
        self.assertIn("M5 iPad Pro", result["adapted_section_intro"])

    def test_engine_result_intro_starts_with_product_and_addresses_search_intent(self):
        result = parse_engine_result(
            self.valid_engine_json(),
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertTrue(result["intro_sentence"].startswith("M5 iPad Pro"))
        self.assertIn("お探しではありませんか", result["intro_sentence"])
        self.assertIn("商品情報をあわせて紹介", result["intro_sentence"])

    def test_engine_result_rejects_intro_starting_with_this_article(self):
        data = json.loads(self.valid_engine_json())
        data["intro_sentence"] = "この記事では、M5 iPad Proにおすすめのバッテリーと商品情報をあわせて紹介します。"
        with self.assertRaisesRegex(ValueError, "親製品名から開始"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_accepts_unchanged_subject_text(self):
        data = json.loads(self.valid_engine_json())
        data["adapted_section_intro"] = self.group.section_intro
        data["products"] = [
            {"index": product.index, "adapted_text": product.text}
            for product in self.group.products
        ]
        result = parse_engine_result(
            json.dumps(data, ensure_ascii=False),
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertEqual(self.group.section_intro.strip(), result["adapted_section_intro"])
        self.assertEqual(self.group.products[0].text.strip(), result["adapted_product_texts"][0])

    def test_engine_result_extracts_json_with_explanatory_prefix(self):
        result = parse_engine_result(
            f"以下が結果です。\n{self.valid_engine_json()}\n以上です。",
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertEqual(len(self.group.products), len(result["adapted_product_texts"]))

    def test_engine_result_reports_json_position(self):
        with self.assertRaisesRegex(ValueError, r"JSON解析に失敗.*\d+行\d+列"):
            parse_engine_result(
                '{"intro_sentence": "途中で終了',
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_rejects_changed_section_intro_body(self):
        data = json.loads(self.valid_engine_json())
        data["adapted_section_intro"] = data["adapted_section_intro"].replace("通勤中", "自宅")
        with self.assertRaisesRegex(ValueError, "削除または大きく書き換え"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_accepts_added_section_intro_lines(self):
        data = json.loads(self.valid_engine_json())
        data["adapted_section_intro"] += "\n\n追加行は後から削除できます。"
        result = parse_engine_result(
            json.dumps(data, ensure_ascii=False),
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertIn("追加行は後から削除できます。", result["adapted_section_intro"])

    def test_engine_result_rejects_reduced_section_intro_lines(self):
        data = json.loads(self.valid_engine_json())
        data["adapted_section_intro"] = "\n".join(data["adapted_section_intro"].splitlines()[:-1])
        with self.assertRaisesRegex(ValueError, "行数が減少"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_rejects_literal_html_break(self):
        data = json.loads(self.valid_engine_json())
        data["adapted_section_intro"] = data["adapted_section_intro"].replace("\n", "<br>\n", 1)
        with self.assertRaisesRegex(ValueError, "HTML改行"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_rejects_reduced_product_lines(self):
        data = json.loads(self.valid_engine_json())
        data["products"][0]["adapted_text"] = data["products"][0]["adapted_text"].replace("\n", " ")
        with self.assertRaisesRegex(ValueError, "商品紹介文の行数が減少"):
            parse_engine_result(
                json.dumps(data, ensure_ascii=False),
                product_name="M5 iPad Pro",
                category_name="バッテリー",
                affiliate_group=self.group,
            )

    def test_engine_result_accepts_added_product_lines_when_source_is_preserved(self):
        data = json.loads(self.valid_engine_json())
        data["products"][0]["adapted_text"] = self.group.products[0].text + "\n\n後から削除できる補足です。"
        result = parse_engine_result(
            json.dumps(data, ensure_ascii=False),
            product_name="M5 iPad Pro",
            category_name="バッテリー",
            affiliate_group=self.group,
        )
        self.assertIn("後から削除できる補足です。", result["adapted_product_texts"][0])

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
        product_index = next(index for index, product in enumerate(self.group.products) if product.urls)
        source_url = self.group.products[product_index].urls[0]
        data["products"][product_index]["adapted_text"] = data["products"][product_index]["adapted_text"].replace(
            source_url,
            "https://example.com/changed",
        )
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
        self.assertEqual(1, job["generation_options"]["max_attempts"])

        job["master_snapshot"]["values"]["周辺機器カテゴリID"] = "cable"
        with self.assertRaisesRegex(ValueError, "スナップショット"):
            validate_job(job)

    def test_job_schema_rejects_invalid_generation_attempts(self):
        with self.assertRaisesRegex(ValueError, "1回から3回"):
            new_job(
                batch_id="batch-1",
                engine="MLX",
                parent={"id": "p1", "title": "親"},
                category={"id": "battery", "name": "バッテリー", "affiliate_section": "battery", "template_file": "tpl_default.md"},
                master_snapshot={"spreadsheet_id": "sheet", "sheet_name": "周辺機器DB", "row_number": 2, "values": {}, "sha256": hashlib.sha256(b"{}").hexdigest()},
                prompt_snapshot={"content": "x", "sha256": hashlib.sha256(b"x").hexdigest()},
                article_title="親 バッテリーおすすめまとめ",
                max_generation_attempts=4,
            )


if __name__ == "__main__":
    unittest.main()
