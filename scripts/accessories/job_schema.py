"""周辺機器ジョブSchema v2と状態遷移。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = 2
ENGINES = {"MLX", "Gemini"}
JOB_STATES = {
    "registration_pending",
    "registration_failed",
    "pending",
    "processing",
    "failed",
    "completed",
}
SHEET_STATUSES = {"記事化", "失敗", "完了"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _master_sha256(values: dict[str, Any]) -> str:
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical)


def new_job(
    *,
    batch_id: str,
    engine: str,
    parent: dict[str, Any],
    category: dict[str, Any],
    master_snapshot: dict[str, Any],
    prompt_snapshot: dict[str, Any],
    article_title: str,
    max_generation_attempts: int | None = None,
) -> dict[str, Any]:
    if engine not in ENGINES:
        raise ValueError(f"生成エンジンが不正です: {engine}")
    job_id = str(uuid4())
    attempts = max_generation_attempts if max_generation_attempts is not None else (1 if engine == "MLX" else 2)
    if attempts not in (1, 2, 3):
        raise ValueError("記事作成・修正回数は1回から3回で指定してください")
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "batch_id": batch_id,
        "created_at": utc_now(),
        "completed_at": "",
        "state": "registration_pending",
        "attempt_count": 0,
        "engine": engine,
        "article_title": article_title,
        "parent": parent,
        "category": category,
        "generation_options": {"max_attempts": attempts},
        "master_snapshot": master_snapshot,
        "prompt_snapshot": prompt_snapshot,
        "registry": {
            "spreadsheet_id": "",
            "sheet_name": "周辺機器DB_LLM",
            "status": "記事化",
            "sync": "pending",
        },
        "lease": {"owner": "", "expires_at": "", "etag": ""},
        "result": {"article_id": "", "article_url": "", "error_summary": ""},
    }
    validate_job(job)
    return job


def validate_job(job: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "job_id",
        "batch_id",
        "state",
        "engine",
        "article_title",
        "parent",
        "category",
        "master_snapshot",
        "prompt_snapshot",
        "registry",
        "lease",
        "result",
    )
    missing = [key for key in required if key not in job]
    if missing:
        raise ValueError(f"ジョブ必須項目が不足しています: {', '.join(missing)}")
    if job["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"非対応のジョブSchemaです: {job['schema_version']}")
    if job["engine"] not in ENGINES:
        raise ValueError(f"生成エンジンが不正です: {job['engine']}")
    if job["state"] not in JOB_STATES:
        raise ValueError(f"ジョブ状態が不正です: {job['state']}")
    if "generation_options" in job:
        try:
            max_attempts = int(job["generation_options"].get("max_attempts"))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("記事作成・修正回数は1回から3回で指定してください") from error
        if max_attempts not in (1, 2, 3):
            raise ValueError("記事作成・修正回数は1回から3回で指定してください")
    if job["registry"].get("status") not in SHEET_STATUSES:
        raise ValueError(f"シート進捗が不正です: {job['registry'].get('status')}")
    for parent_key in ("id", "title"):
        if not str(job["parent"].get(parent_key, "")).strip():
            raise ValueError(f"親記事情報が不足しています: {parent_key}")
    for category_key in ("id", "name", "affiliate_section", "template_file"):
        if not str(job["category"].get(category_key, "")).strip():
            raise ValueError(f"周辺機器カテゴリ情報が不足しています: {category_key}")
    master = job["master_snapshot"]
    for master_key in ("spreadsheet_id", "sheet_name", "row_number", "values", "sha256"):
        if master_key not in master:
            raise ValueError(f"周辺機器DBスナップショットが不足しています: {master_key}")
    if not isinstance(master["values"], dict) or _master_sha256(master["values"]) != master["sha256"]:
        raise ValueError("周辺機器DBスナップショットのSHA-256が一致しません")
    prompt = job["prompt_snapshot"]
    content = str(prompt.get("content", ""))
    if not content or _sha256(content) != str(prompt.get("sha256", "")):
        raise ValueError("プロンプトスナップショットのSHA-256が一致しません")
