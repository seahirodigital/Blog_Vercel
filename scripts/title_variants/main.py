"""MLXで冒頭と結論の先頭文だけを調整し、SEO派生記事を保存する。"""

from __future__ import annotations

import json
import os
import socket
from typing import Callable

from scripts.accessories.job_schema import utc_now
from scripts.accessories.onedrive_store import (
    acquire_job,
    download_article,
    read_job,
    save_job,
    save_title_variant_article,
)
from scripts.accessories.sheet_registry import update_job
from scripts.title_variants.article_transformer import assemble_variant, validate_variant
from scripts.title_variants.job_schema import validate_title_variant_job
from scripts.title_variants.prompt_builder import build_prompt_input, parse_engine_result


def _service_account_info() -> dict:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSONが設定されていません")
    return json.loads(raw)


def _source_fallback(source) -> dict[str, str]:
    return {
        "intro_text": source.intro.text,
        "conclusion_text": source.conclusion.text,
    }


def process_title_variant_job(
    job_id: str,
    *,
    mlx_generator: Callable[..., str],
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict:
    def report(stage: str, message: str) -> None:
        if progress_callback:
            progress_callback(stage, message)

    candidate, _ = read_job(job_id)
    validate_title_variant_job(candidate)
    owner = f"mlx-title-variant:{socket.gethostname()}:{os.getpid()}"
    report("job_lock", "このタイトル派生ジョブの処理権を確保しています")
    job, etag = acquire_job(job_id, owner)
    try:
        report("source_loading", "元記事とタイトル派生プロンプトを読み込んでいます")
        source_markdown = download_article(job["parent"]["id"])
        fallback_markdown, source = assemble_variant(
            source_markdown,
            keyword=job["target"]["keyword"],
        )
        validate_variant(fallback_markdown, source_markdown, job["target"]["keyword"])
        prompt_content = str(job["prompt_snapshot"]["content"])
        system_prompt, input_text = build_prompt_input(
            template_content=prompt_content,
            source_title=source.source_title,
            target_title=source.target_title,
            keyword=job["target"]["keyword"],
            intro_text=source.intro.text,
            conclusion_text=source.conclusion.text,
        )
        generation_errors: list[str] = []
        result = None
        max_attempts = int(job["generation_options"]["max_attempts"])
        for attempt in range(1, max_attempts + 1):
            try:
                report("generating", f"MLXで冒頭文と結論文を調整しています（{attempt}/{max_attempts}回目）")
                raw = mlx_generator(
                    system_prompt=system_prompt,
                    input_text=input_text,
                    attempt=attempt,
                    validation_feedback=tuple(generation_errors),
                )
                result = parse_engine_result(
                    raw,
                    keyword=job["target"]["keyword"],
                    conclusion_required=bool(source.conclusion.text),
                )
                break
            except Exception as error:
                generation_errors.append(f"{attempt}回目: {str(error)[:500]}")
        fallback_used = result is None
        if fallback_used:
            result = _source_fallback(source)
            report("fallback", "MLX調整は不合格でしたが、元本文を保ったタイトル派生記事を出力します")
        report("assembling", "全見出しと限定された冒頭文・結論文を反映しています")
        article, _ = assemble_variant(
            source_markdown,
            keyword=job["target"]["keyword"],
            intro_text=result["intro_text"],
            conclusion_text=result["conclusion_text"],
        )
        report("validating", "URL・商品ブロック・本文外メタ情報を検査しています")
        validate_variant(article, source_markdown, job["target"]["keyword"])
        report("saving", "元記事と同じOneDriveフォルダへ派生記事を保存しています")
        article_item = save_title_variant_article(job, job["target"]["filename"], article)
        job["state"] = "completed"
        job["completed_at"] = utc_now()
        job["lease"] = {"owner": "", "expires_at": "", "etag": ""}
        job["result"] = {
            "article_id": article_item.get("id", ""),
            "article_url": article_item.get("webUrl", ""),
            "error_summary": "",
            "warning_summary": "MLX調整が不合格のため、元の冒頭文と結論文を保持して出力しました。" if fallback_used else "",
            "generation_errors": generation_errors,
            "output_mode": "safe_source_fallback" if fallback_used else "generated",
            "integrity": {
                "editable_regions": ["h1_to_h6_text", "intro_first_paragraph", "conclusion_first_paragraph"],
                "preserved": ["affiliate_urls", "product_block_titles", "remaining_body"],
            },
        }
        job["registry"]["status"] = "完了"
        job["registry"]["sync"] = "pending"
        save_job(job, if_match=etag)
        report("registry", "周辺機器DB_LLMへ完了日時と記事リンクを反映しています")
        try:
            update_job(
                _service_account_info(),
                job_id=job_id,
                status="完了",
                completed_at=job["completed_at"],
                article_url=job["result"]["article_url"],
            )
            job["registry"]["sync"] = "completed"
            save_job(job)
        except Exception as error:
            job["registry"]["last_error"] = str(error)[:300]
            save_job(job)
        report("completed", "SEOキーワード別の記事保存が完了しました")
        return job
    except Exception as error:
        job["state"] = "failed"
        job["lease"] = {"owner": "", "expires_at": "", "etag": ""}
        job.setdefault("result", {})["error_summary"] = str(error)[:300]
        job["registry"]["status"] = "失敗"
        save_job(job)
        try:
            update_job(
                _service_account_info(),
                job_id=job_id,
                status="失敗",
                error_summary=job["result"]["error_summary"],
            )
        except Exception:
            pass
        raise
