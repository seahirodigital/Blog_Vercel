"""周辺機器子記事をGeminiまたはMLXの一方だけで完結させる共通実行器。"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from typing import Callable

from .affiliate_group import extract_group
from .article_assembler import assemble_article, immutable_content_sha256
from .article_validator import validate_public_markdown
from .conclusion_builder import build_conclusion_addition
from .job_schema import utc_now, validate_job
from .metadata_store import save_metadata
from .onedrive_store import (
    AFFILIATE_FILE_PATH,
    acquire_job,
    download_article,
    download_text_path,
    read_job,
    save_child_article,
    save_job,
)
from .parent_analyzer import analyze_parent, extract_generation_evidence
from .prompt_builder import parse_engine_result
from .prompt_store import verified_prompt
from .sheet_registry import update_job


MAX_GENERATION_ATTEMPTS = 3


def _service_account_info() -> dict:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSONが設定されていません")
    return json.loads(raw)


def _filename(job: dict) -> str:
    parent_id = re.sub(r"[^A-Za-z0-9_-]", "_", job["parent"]["id"])
    category_id = re.sub(r"[^a-z0-9_-]", "_", job["category"]["id"].lower())
    return f"{parent_id}_child_{category_id}.md"


def process_job(
    job_id: str,
    *,
    engine_name: str,
    mlx_generator: Callable[..., str] | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict:
    def report(stage: str, message: str) -> None:
        if progress_callback is not None:
            progress_callback(stage, message)

    owner = f"{engine_name.lower()}:{socket.gethostname()}:{os.getpid()}"
    report("job_check", "OneDriveのジョブ内容を確認しています")
    candidate, candidate_etag = read_job(job_id)
    validate_job(candidate)
    if candidate["engine"].casefold() != engine_name.casefold():
        raise ValueError(f"ジョブの生成エンジンが一致しません: {candidate['engine']} != {engine_name}")
    if candidate["state"] == "completed":
        if candidate.get("registry", {}).get("sync") == "completed":
            raise RuntimeError("完了済みジョブは再処理しません")
        update_job(
            _service_account_info(),
            job_id=job_id,
            status="完了",
            completed_at=str(candidate.get("completed_at", "")),
            article_url=str(candidate.get("result", {}).get("article_url", "")),
        )
        candidate["registry"]["sync"] = "completed"
        candidate["registry"].pop("last_error", None)
        save_job(candidate, if_match=candidate_etag)
        return candidate
    report("job_lock", "このジョブの処理権を確保しています")
    job, etag = acquire_job(job_id, owner)

    try:
        report("source_loading", "親記事・おすすめ商品・プロンプトを読み込んでいます")
        parent_markdown = download_article(job["parent"]["id"])
        parent = analyze_parent(parent_markdown)
        group = extract_group(
            download_text_path(AFFILIATE_FILE_PATH),
            job["category"]["affiliate_section"],
        )
        evidence = extract_generation_evidence(parent)
        prompt_content = verified_prompt(job["prompt_snapshot"])

        last_generation_error: Exception | None = None
        result = None
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                report(
                    "generating",
                    f"{engine_name}で記事差分を生成しています（{attempt}/{MAX_GENERATION_ATTEMPTS}回目）",
                )
                if engine_name == "Gemini":
                    # MLX実行時にGemini SDKを要求しない。各エンジンを依存関係も含めて独立させる。
                    from .engines import gemini_engine

                    result = gemini_engine.generate(
                        product_name=parent.product_name,
                        category_name=job["category"]["name"],
                        evidence=evidence,
                        affiliate_group=group,
                        prompt_content=prompt_content,
                    )
                elif engine_name == "MLX":
                    if mlx_generator is None:
                        raise ValueError("MLX生成関数が設定されていません")
                    raw_result = mlx_generator(
                        prompt=prompt_content,
                        product_name=parent.product_name,
                        category_name=job["category"]["name"],
                        evidence=evidence,
                        affiliate_group=group,
                        attempt=attempt,
                    )
                    result = parse_engine_result(raw_result, len(group.products))
                else:
                    raise ValueError(f"非対応の生成エンジンです: {engine_name}")
                break
            except Exception as generation_error:
                last_generation_error = generation_error
                if attempt == MAX_GENERATION_ATTEMPTS:
                    raise RuntimeError(
                        f"{engine_name}生成結果が{MAX_GENERATION_ATTEMPTS}回とも不合格でした: {generation_error}"
                    ) from generation_error
        if result is None:
            raise RuntimeError(f"{engine_name}生成結果を取得できませんでした: {last_generation_error}")

        report("assembling", "生成結果を親記事へ反映し、結論の商品一覧を組み立てています")
        addition = build_conclusion_addition(
            product_name=parent.product_name,
            category_name=job["category"]["name"],
            spec_summary=result["spec_summary"],
            recommendation_reasons=result["recommendation_reasons"],
            affiliate_group=group,
        )
        child_markdown, _ = assemble_article(
            parent_markdown,
            category_name=job["category"]["name"],
            title_format=job["category"].get("title_format", ""),
            conclusion_addition=addition,
        )
        report("validating", "本文外メタ情報・Frontmatter・リンク構成を検査しています")
        validate_public_markdown(
            child_markdown,
            affiliate_group=group,
            allowed_new_urls=[url for product in group.products for url in product.urls],
        )
        report("saving", "合格した子記事をOneDriveの周辺機器フォルダへ保存しています")
        article_item = save_child_article(job, _filename(job), child_markdown)
        product_titles = [product.title for product in group.products]
        management_seo = {
            "title": job["article_title"],
            "keyword": f"{parent.product_name} {job['category']['name']} おすすめ",
            "description": (
                f"{parent.product_name}の主要仕様と、おすすめ{job['category']['name']}を紹介します。"
                f"{result['spec_summary']}"
            )[:160],
            "product_name": parent.product_name,
            "recommended_products": product_titles,
            "source": "parent-title-and-validated-engine-result",
        }
        integrity = {
            "parent_immutable_sha256": immutable_content_sha256(
                parent_markdown,
                category_name=job["category"]["name"],
                title_format=job["category"].get("title_format", ""),
            ),
            "editable_regions": ["h1_text", "matched_h2_text_after_conclusion", "conclusion_append"],
        }
        job["state"] = "completed"
        job["completed_at"] = utc_now()
        job["lease"] = {"owner": "", "expires_at": "", "etag": ""}
        job["result"] = {
            "article_id": article_item.get("id", ""),
            "article_url": article_item.get("webUrl", ""),
            "error_summary": "",
            "management_seo": management_seo,
            "integrity": integrity,
        }
        job["registry"]["status"] = "完了"
        job["registry"]["sync"] = "pending"
        save_job(job, if_match=etag)
        save_metadata(job, article_item)
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
        except Exception as registry_error:
            job["registry"]["sync"] = "pending"
            job["registry"]["last_error"] = str(registry_error)[:300]
            save_job(job)
        report("completed", "子記事の生成と保存が完了しました")
        return job
    except Exception as error:
        job["state"] = "failed"
        job["lease"] = {"owner": "", "expires_at": "", "etag": ""}
        job["result"]["error_summary"] = str(error)[:300]
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


def main() -> int:
    parser = argparse.ArgumentParser(description="周辺機器子記事を生成します")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--engine", choices=("Gemini", "MLX"), required=True)
    args = parser.parse_args()
    if args.engine == "MLX":
        raise SystemExit("MLXはaccessories_worker.pyから共通関数を呼び出してください")
    result = process_job(args.job_id, engine_name=args.engine)
    print(json.dumps({"job_id": result["job_id"], "state": result["state"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
