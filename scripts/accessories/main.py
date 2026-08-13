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


MAX_GENERATION_ATTEMPTS = 2


def source_fallback_result(product_name: str, category_name: str, group) -> dict:
    """LLMが不合格でも、創作せず原文で記事化する。"""
    return {
        "intro_sentence": (
            f"{product_name}におすすめの{category_name}をお探しではありませんか？"
            f"この記事では、{product_name}におすすめの{category_name}と商品情報をあわせて紹介します。"
        ),
        "adapted_section_intro": group.section_intro,
        "adapted_product_texts": [product.text for product in group.products],
    }


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
        generation_errors: list[str] = []
        fallback_used = False
        result = None
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                report(
                    "generating",
                    f"{engine_name}で冒頭文と商品文を調整しています（{attempt}/{MAX_GENERATION_ATTEMPTS}回目）",
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
                        validation_feedback=tuple(generation_errors),
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
                        validation_feedback=tuple(generation_errors),
                    )
                    result = parse_engine_result(
                        raw_result,
                        product_name=parent.product_name,
                        category_name=job["category"]["name"],
                        affiliate_group=group,
                    )
                else:
                    raise ValueError(f"非対応の生成エンジンです: {engine_name}")
                break
            except Exception as generation_error:
                last_generation_error = generation_error
                generation_errors.append(f"{attempt}回目: {str(generation_error)[:500]}")
                if attempt == MAX_GENERATION_ATTEMPTS:
                    fallback_used = True
                    result = source_fallback_result(
                        parent.product_name,
                        job["category"]["name"],
                        group,
                    )
                    report(
                        "fallback",
                        f"{engine_name}生成は{MAX_GENERATION_ATTEMPTS}回不合格のため、原文を保った安全な記事を出力します",
                    )
                    break
        if result is None:
            raise RuntimeError(f"{engine_name}生成結果を取得できませんでした: {last_generation_error}")

        def assemble_and_validate(active_result: dict) -> str:
            addition = build_conclusion_addition(
                adapted_section_intro=active_result["adapted_section_intro"],
                adapted_product_texts=active_result["adapted_product_texts"],
            )
            article, _ = assemble_article(
                parent_markdown,
                category_name=job["category"]["name"],
                title_format=job["category"].get("title_format", ""),
                intro_addition=active_result["intro_sentence"],
                conclusion_addition=addition,
            )
            validate_public_markdown(
                article,
                affiliate_group=group,
                adapted_section_intro=active_result["adapted_section_intro"],
                adapted_product_texts=active_result["adapted_product_texts"],
                allowed_new_urls=[url for product in group.products for url in product.urls],
            )
            return article

        report("assembling", "冒頭案内文と調整済み商品ブロックを親記事へ反映しています")
        report("validating", "本文外メタ情報・Frontmatter・リンク構成を検査しています")
        try:
            child_markdown = assemble_and_validate(result)
        except Exception as article_validation_error:
            if engine_name != "MLX" or fallback_used:
                raise
            generation_errors.append(
                f"保存前検査: {str(article_validation_error)[:500]}"
            )
            fallback_used = True
            result = source_fallback_result(
                parent.product_name,
                job["category"]["name"],
                group,
            )
            report(
                "fallback",
                "MLX調整結果が保存前検査に不合格のため、原文で安全に記事化します",
            )
            child_markdown = assemble_and_validate(result)
        warning_summary = (
            "MLX調整結果が検査に合格しなかったため、"
            "アフィリエイト原文を使って記事を出力しました。"
        ) if fallback_used else ""
        report(
            "saving",
            "警告付き子記事をOneDriveへ保存しています"
            if fallback_used else "合格した子記事をOneDriveの周辺機器フォルダへ保存しています",
        )
        article_item = save_child_article(job, _filename(job), child_markdown)
        product_titles = [product.title for product in group.products]
        management_seo = {
            "title": job["article_title"],
            "keyword": f"{parent.product_name} {job['category']['name']} おすすめ",
            "description": (
                f"{parent.product_name}におすすめの{job['category']['name']}を、"
                "商品情報を維持して紹介します。"
            )[:160],
            "product_name": parent.product_name,
            "recommended_products": product_titles,
            "source": "parent-title-and-minimally-adapted-affiliate-text",
        }
        integrity = {
            "parent_immutable_sha256": immutable_content_sha256(
                parent_markdown,
                category_name=job["category"]["name"],
                title_format=job["category"].get("title_format", ""),
            ),
            "editable_regions": ["h1_text", "all_h2_text", "intro_append", "conclusion_append"],
        }
        job["state"] = "completed"
        job["completed_at"] = utc_now()
        job["lease"] = {"owner": "", "expires_at": "", "etag": ""}
        job["result"] = {
            "article_id": article_item.get("id", ""),
            "article_url": article_item.get("webUrl", ""),
            "error_summary": "",
            "warning_summary": warning_summary,
            "generation_errors": generation_errors,
            "output_mode": "safe_source_fallback" if fallback_used else "generated",
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
        report(
            "completed",
            "MLX出力は不合格でしたが、原文を使った記事の保存が完了しました"
            if fallback_used else "子記事の生成と保存が完了しました",
        )
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
