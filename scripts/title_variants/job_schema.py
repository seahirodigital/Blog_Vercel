"""タイトル派生ジョブの入力契約。"""

from __future__ import annotations

import hashlib
from typing import Any


ALLOWED_STATES = {
    "registration_pending",
    "registration_failed",
    "pending",
    "processing",
    "failed",
    "completed",
}


def validate_title_variant_job(job: dict[str, Any]) -> None:
    required = (
        "job_id",
        "batch_id",
        "job_type",
        "state",
        "engine",
        "article_title",
        "parent",
        "target",
        "generation_options",
        "prompt_snapshot",
        "registry",
        "result",
    )
    missing = [key for key in required if key not in job]
    if missing:
        raise ValueError(f"タイトル派生ジョブの必須項目が不足しています: {', '.join(missing)}")
    if job.get("job_type") != "title_variant":
        raise ValueError("タイトル派生ジョブの種別が不正です")
    if job.get("engine") != "MLX":
        raise ValueError("タイトル派生ジョブはMLXだけで処理します")
    if job.get("state") not in ALLOWED_STATES:
        raise ValueError(f"タイトル派生ジョブの状態が不正です: {job.get('state')}")
    for key in ("id", "title"):
        if not str(job.get("parent", {}).get(key, "")).strip():
            raise ValueError(f"元記事情報が不足しています: {key}")
    for key in ("keyword", "title", "filename"):
        if not str(job.get("target", {}).get(key, "")).strip():
            raise ValueError(f"変換先情報が不足しています: {key}")
    attempts = int(job.get("generation_options", {}).get("max_attempts", 0))
    if attempts not in (1, 2, 3):
        raise ValueError("MLXの記事作成・修正回数は1回から3回で指定してください")
    prompt = job.get("prompt_snapshot", {})
    content = str(prompt.get("content", ""))
    if not content or hashlib.sha256(content.encode("utf-8")).hexdigest() != str(prompt.get("sha256", "")):
        raise ValueError("タイトル派生プロンプトのSHA-256が一致しません")
