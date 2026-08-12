"""ジョブに固定したプロンプト改訂の整合性を検査する。"""

from __future__ import annotations

import hashlib


def prompt_sha256(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def verified_prompt(snapshot: dict) -> str:
    content = str(snapshot.get("content", ""))
    expected = str(snapshot.get("sha256", ""))
    if not content or not expected:
        raise ValueError("プロンプト本文またはSHA-256がありません")
    actual = prompt_sha256(content)
    if actual != expected:
        raise ValueError("ジョブのプロンプトSHA-256が一致しません")
    return content
