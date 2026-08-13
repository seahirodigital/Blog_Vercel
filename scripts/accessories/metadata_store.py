"""子記事の管理値をMarkdownと分離したJSONにする。"""

from __future__ import annotations

from typing import Any

from .onedrive_store import CONTROL_FOLDER, upload_json


def save_metadata(job: dict[str, Any], article_item: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "schema_version": 1,
        "job_id": job["job_id"],
        "batch_id": job["batch_id"],
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at", ""),
        "engine": job["engine"],
        "parent": job["parent"],
        "category": job["category"],
        "master_snapshot": job["master_snapshot"],
        "prompt_snapshot": {
            key: value
            for key, value in job["prompt_snapshot"].items()
            if key != "content"
        },
        "seo": job.get("result", {}).get("management_seo", {}),
        "integrity": job.get("result", {}).get("integrity", {}),
        "generation": {
            "output_mode": job.get("result", {}).get("output_mode", "generated"),
            "warning_summary": job.get("result", {}).get("warning_summary", ""),
            "errors": job.get("result", {}).get("generation_errors", []),
        },
        "article": {
            "id": article_item.get("id", ""),
            "name": article_item.get("name", ""),
            "web_url": article_item.get("webUrl", ""),
        },
    }
    parent_id = job["parent"]["id"]
    category_id = job["category"]["id"]
    return upload_json(f"{CONTROL_FOLDER}/metadata/{parent_id}/{category_id}.json", metadata)
