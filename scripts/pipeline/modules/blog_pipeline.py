"""
ブログ生成パイプライン (GitHub Actions 対応版)
Drafter → Editor → Director の多段生成を行う。

Gemini の quota / rate limit でキーを切り替える際も、
成功済みステップの出力を引き継ぎ、未完了ステップから再開する。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

from gemini_runtime import (  # noqa: E402
    build_generation_config,
    create_client,
    get_text_model_name,
    get_text_transport,
    run_text_generation,
)

MODEL_NAME = get_text_model_name()
TRANSPORT_NAME = get_text_transport(default="interactions.create")
GENERATION_CONFIG = build_generation_config(temperature=0.5)
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class GeminiQuotaExceededError(RuntimeError):
    """Gemini の quota / rate limit 到達。"""


_EXHAUSTED_GEMINI_KEYS: set[str] = set()


def _is_github_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"


def _escape_actions_command_text(value: str) -> str:
    return str(value or "").replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _emit_actions_notice(message: str):
    if not _is_github_actions():
        return
    print(f"::notice::{_escape_actions_command_text(message)}")


def _is_quota_error(error: Exception | str) -> bool:
    text = str(error or "").lower()
    keywords = (
        "429",
        "quota",
        "resource_exhausted",
        "rate limit",
        "too many requests",
        "exceeded",
        "throttle",
    )
    return any(keyword in text for keyword in keywords)


def _is_exhausted_key(api_key: str) -> bool:
    normalized = str(api_key or "").strip()
    return bool(normalized) and normalized in _EXHAUSTED_GEMINI_KEYS


def _mark_key_exhausted(api_key: str):
    normalized = str(api_key or "").strip()
    if normalized:
        _EXHAUSTED_GEMINI_KEYS.add(normalized)


def _normalize_api_key_candidates(gemini_api_keys) -> list[tuple[str, str]]:
    if isinstance(gemini_api_keys, str):
        return [("GEMINI_API_KEY", gemini_api_keys.strip())] if gemini_api_keys.strip() else []

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    if isinstance(gemini_api_keys, Iterable):
        for item in gemini_api_keys:
            if isinstance(item, tuple) and len(item) >= 2:
                label = str(item[0] or "").strip() or "Gemini"
                api_key = str(item[1] or "").strip()
            else:
                label = "Gemini"
                api_key = str(item or "").strip()
            if not api_key or api_key in seen:
                continue
            seen.add(api_key)
            candidates.append((label, api_key))
    return candidates


def _load_prompt(filename: str) -> str:
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {filepath}")

    lines = filepath.read_text(encoding="utf-8").splitlines()
    content_lines = [line for line in lines if not line.startswith("#")]
    return "\n".join(content_lines).strip()


def _parse_writer_prompt(content: str, status: str) -> str:
    sections: dict[str, str] = {}
    current_section = None
    current_lines: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = stripped[1:-1]
            current_lines = []
            continue

        if current_section is not None:
            current_lines.append(line)

    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections.get(status, sections.get("単品", ""))


def _load_optional_prompt(filename: str) -> Optional[str]:
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        return None
    return _load_prompt(filename)


def _load_pipeline_prompts(status: str) -> dict[str, Optional[str]]:
    writer_raw = _load_prompt("01-writer-prompt.txt")
    prompts = {
        "drafter": _parse_writer_prompt(writer_raw, status),
        "editor": _load_prompt("02-editor-prompt.txt"),
        "director": _load_prompt("03-director-prompt.txt"),
        "best_outline": _load_optional_prompt("031-best-outline-prompt.txt"),
        "best_enhancer": _load_optional_prompt("032-best-article-enhancer-prompt.txt"),
    }
    return prompts


def _build_resume_input(source_text: str, instruction: str) -> str:
    return (
        f"【引き継ぎ済みの前段出力】\n{source_text}\n\n"
        f"【今回の依頼】\n{instruction}"
    ).strip()


def _build_pipeline_steps(transcript: dict[str, Any], status: str, prompts: dict[str, Optional[str]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "code": "Step1",
            "start_message": f"   Step1: 下書き生成 ({status})",
            "success_message": "   Step1 完了",
            "prompt": prompts["drafter"] or "",
            "seed_input": transcript["captions"],
            "stateful_input": transcript["captions"],
            "resume_instruction": None,
            "sleep_after_success": True,
        },
        {
            "code": "Step2",
            "start_message": "   Step2: 編集",
            "success_message": "   Step2 完了",
            "prompt": prompts["editor"] or "",
            "seed_input": "",
            "stateful_input": "上記の記事を編集してください。",
            "resume_instruction": "次の記事を編集してください。",
            "sleep_after_success": True,
        },
        {
            "code": "Step3",
            "start_message": "   Step3: 最終チェック",
            "success_message": "   Step3 完了",
            "prompt": prompts["director"] or "",
            "seed_input": "",
            "stateful_input": "上記の記事を100点満点へ引き上げてください。",
            "resume_instruction": "次の記事を100点満点へ引き上げてください。",
            "sleep_after_success": False,
        },
    ]

    if status == "量産元":
        best_outline_prompt = prompts.get("best_outline")
        best_enhancer_prompt = prompts.get("best_enhancer")

        if best_outline_prompt:
            steps.append(
                {
                    "code": "Step3.1",
                    "start_message": "   Step3.1: ベスト記事化の補強設計",
                    "success_message": "   Step3.1 完了",
                    "prompt": best_outline_prompt,
                    "seed_input": "",
                    "stateful_input": "上記の記事を量産元記事として評価し、検索意図の抜け漏れ、追加すべき見出し、FAQ、比較軸を整理してください。",
                    "resume_instruction": "次の記事を量産元記事として評価し、検索意図の抜け漏れ、追加すべき見出し、FAQ、比較軸を整理してください。",
                    "sleep_after_success": True,
                }
            )
        else:
            print("   031-best-outline-prompt.txt が見つからないため Step3.1 をスキップします")

        if best_enhancer_prompt:
            steps.append(
                {
                    "code": "Step3.2",
                    "start_message": "   Step3.2: ベスト記事へ磨き込み",
                    "success_message": "   Step3.2 完了",
                    "prompt": best_enhancer_prompt,
                    "seed_input": "",
                    "stateful_input": "上記の通常記事と補強設計を統合し、量産元として使える完成版のベスト記事に仕上げてください。",
                    "resume_instruction": "次の記事と補強設計を統合し、量産元として使える完成版のベスト記事に仕上げてください。",
                    "sleep_after_success": False,
                }
            )
        else:
            print("   032-best-article-enhancer-prompt.txt が見つからないため Step3.2 をスキップします")

    return steps


def _run_generation_with_quota_handling(
    client,
    *,
    input_text: str,
    system_prompt: str,
    previous_id: Optional[str] = None,
) -> tuple[Any, str]:
    try:
        return run_text_generation(
            client,
            model=MODEL_NAME,
            transport=TRANSPORT_NAME,
            prompt=system_prompt,
            input_text=input_text,
            generation_config=GENERATION_CONFIG,
            previous_interaction_id=previous_id,
        )
    except Exception as error:
        if _is_quota_error(error):
            raise GeminiQuotaExceededError(str(error)) from error
        print(f"   APIエラー: {error}")
        raise


def _prepare_step_request(
    step: dict[str, Any],
    previous_output_text: Optional[str],
    previous_interaction_id: Optional[str],
) -> tuple[str, Optional[str], bool]:
    if step["resume_instruction"] is None:
        return step["seed_input"], None, False

    if TRANSPORT_NAME == "interactions.create" and previous_interaction_id:
        return step["stateful_input"], previous_interaction_id, False

    if not previous_output_text:
        raise RuntimeError(f"{step['code']} を再開するための前段出力が見つかりません")

    return _build_resume_input(previous_output_text, step["resume_instruction"]), None, True


def _run_single_step(
    client,
    step: dict[str, Any],
    *,
    previous_output_text: Optional[str],
    previous_interaction_id: Optional[str],
) -> dict[str, str]:
    input_text, previous_id, resumed = _prepare_step_request(step, previous_output_text, previous_interaction_id)
    print(step["start_message"])
    if resumed:
        print(f"   {step['code']} は前段出力を引き継いで再開します")
        _emit_actions_notice(f"Gemini パイプラインは {step['code']} から再開しました")

    response, output_text = _run_generation_with_quota_handling(
        client,
        input_text=input_text,
        system_prompt=step["prompt"],
        previous_id=previous_id,
    )

    normalized_output = str(output_text or "").strip()
    if not normalized_output:
        raise RuntimeError(f"{step['code']} の応答が空でした")

    interaction_id = str(getattr(response, "id", "") or "")
    if interaction_id:
        print(f"{step['success_message']}: {interaction_id}")
    else:
        print(f"{step['success_message']}: response received")

    return {
        "output_text": normalized_output,
        "interaction_id": interaction_id,
    }


def _run_pipeline_steps_with_candidates(
    transcript: dict[str, Any],
    status: str,
    prompts: dict[str, Optional[str]],
    candidates: list[tuple[str, str]],
) -> Optional[str]:
    steps = _build_pipeline_steps(transcript, status, prompts)
    step_index = 0
    previous_output_text: Optional[str] = None
    previous_interaction_id: Optional[str] = None
    candidate_index = 0

    while step_index < len(steps):
        if candidate_index >= len(candidates):
            print("   利用可能な Gemini キーを使い切ったため停止します")
            return None

        label, api_key = candidates[candidate_index]
        print(f"   Geminiキーを使用: {label} ({candidate_index + 1}/{len(candidates)})")
        client = create_client(api_key)

        try:
            while step_index < len(steps):
                step = steps[step_index]
                result = _run_single_step(
                    client,
                    step,
                    previous_output_text=previous_output_text,
                    previous_interaction_id=previous_interaction_id,
                )
                previous_output_text = result["output_text"]
                previous_interaction_id = result["interaction_id"] or None

                should_sleep = bool(step.get("sleep_after_success")) and step_index < len(steps) - 1
                step_index += 1
                if should_sleep:
                    time.sleep(10)

            return previous_output_text
        except GeminiQuotaExceededError as error:
            step = steps[step_index]
            print(f"   {label} が quota / rate limit に到達しました: {error}")
            _mark_key_exhausted(api_key)
            candidate_index += 1
            previous_interaction_id = None

            if candidate_index >= len(candidates):
                print("   利用可能な Gemini キーを使い切ったため停止します")
                return None

            next_label = candidates[candidate_index][0]
            if previous_output_text and step.get("resume_instruction"):
                print(f"   {next_label} に切り替え、{step['code']} から再開します")
                _emit_actions_notice(
                    f"Gemini キーを {label} から {next_label} へ切り替え、{step['code']} から再開します"
                )
            else:
                print(f"   {next_label} に切り替えて続行します")
                _emit_actions_notice(f"Gemini キーを {label} から {next_label} へ切り替えます")
        except Exception as error:
            print(f"   パイプラインエラー: {error}")
            return None

    return previous_output_text


def _build_available_candidates(gemini_api_keys) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    raw_candidates = _normalize_api_key_candidates(gemini_api_keys)
    candidates: list[tuple[str, str]] = []

    for label, api_key in raw_candidates:
        if _is_exhausted_key(api_key):
            print(f"   {label} はこの run で quota 到達済みのためスキップします")
            continue
        candidates.append((label, api_key))

    return raw_candidates, candidates


def run_pipeline_with_fallback(transcript: dict, gemini_api_keys, status: str = "単品") -> Optional[str]:
    try:
        prompts = _load_pipeline_prompts(status)
        print(f"   プロンプト読み込み完了: 01-writer({status}) / 02-editor / 03-director")
        print(f"   Gemini設定: model={MODEL_NAME} / transport={TRANSPORT_NAME}")
    except FileNotFoundError as error:
        print(f"   プロンプトファイルエラー: {error}")
        return None

    raw_candidates, candidates = _build_available_candidates(gemini_api_keys)
    if not candidates:
        if raw_candidates:
            print("   この run で利用可能な Gemini キーが残っていません")
        else:
            print("   Gemini APIキーが設定されていません")
        return None

    return _run_pipeline_steps_with_candidates(transcript, status, prompts, candidates)


def run_pipeline(transcript: dict, gemini_api_key: str, status: str = "単品") -> Optional[str]:
    """
    単一キーでブログ生成パイプラインを実行する。

    Args:
        transcript: {"title": "...", "captions": "...", "video_id": "...", "url": "..."}
        gemini_api_key: Gemini APIキー
        status: "単品" / "情報" / "複数" / "量産元"

    Returns:
        最終Markdown文字列 または None
    """
    return run_pipeline_with_fallback(
        transcript,
        [("GEMINI_API_KEY", gemini_api_key)],
        status=status,
    )
