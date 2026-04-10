"""
ブログ生成パイプライン (GitHub Actions 対応版)
Drafter → Editor → Chief の3段階生成
Gemini Interaction Hub を使用
プロンプトは prompts/ フォルダのテキストファイルから読み込む
"""

import os
import time
from pathlib import Path
from typing import Iterable, Optional

from google import genai

# Gemini 最新モデル
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# プロンプトファイルのディレクトリ（このファイルの親の prompts/ フォルダ）
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class GeminiQuotaExceededError(RuntimeError):
    """Gemini の quota / rate limit 到達。"""


_EXHAUSTED_GEMINI_KEYS: set[str] = set()


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
    """プロンプトファイルを読み込む（#コメント行は除去）"""
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {filepath}")
    
    lines = filepath.read_text(encoding="utf-8").splitlines()
    # '#' で始まる行（コメント）を除去して結合
    content_lines = [line for line in lines if not line.startswith("#")]
    return "\n".join(content_lines).strip()


def _parse_writer_prompt(content: str, status: str) -> str:
    """writer-prompt.txt から指定種別のプロンプトを抽出する"""
    # [種別名] セクションを解析する
    sections = {}
    current_section = None
    current_lines = []

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = stripped[1:-1]
            current_lines = []
        else:
            if current_section is not None:
                current_lines.append(line)

    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    # 指定種別が見つからなければ「単品」にフォールバック
    return sections.get(status, sections.get("単品", ""))


def _load_optional_prompt(filename: str) -> Optional[str]:
    """任意プロンプトを読み込む。未配置なら None を返す。"""
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        return None
    return _load_prompt(filename)


def _run_interaction_with_quota_handling(client, input_text: str, system_prompt: str, previous_id: Optional[str] = None):
    """Gemini への問い合わせを行い、quota 系は専用例外へ寄せる。"""
    full_input = f"【指示・役割】\n{system_prompt}\n\n【入力データ】\n{input_text}"

    try:
        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=full_input,
            previous_interaction_id=previous_id,
            generation_config={
                "temperature": 0.5,
                "thinking_level": "high",
            },
        )
        return interaction
    except Exception as error:
        if _is_quota_error(error):
            raise GeminiQuotaExceededError(str(error)) from error
        print(f"   APIエラー: {error}")
        raise


def _run_pipeline_with_candidate_client(
    client,
    transcript: dict,
    status: str,
    drafter_prompt: str,
    editor_prompt: str,
    director_prompt: str,
    best_outline_prompt: Optional[str],
    best_enhancer_prompt: Optional[str],
) -> str:
    captions = transcript["captions"]

    print(f"   Step1: 下書き生成 ({status})")
    int1 = _run_interaction_with_quota_handling(client, captions, drafter_prompt)
    print(f"   Step1 完了: {int1.id}")
    time.sleep(10)

    print("   Step2: 編集")
    int2 = _run_interaction_with_quota_handling(client, "上記の記事を編集してください。", editor_prompt, previous_id=int1.id)
    print(f"   Step2 完了: {int2.id}")
    time.sleep(10)

    print("   Step3: 最終チェック")
    int3 = _run_interaction_with_quota_handling(client, "上記の記事を100点満点へ引き上げてください。", director_prompt, previous_id=int2.id)
    final_text = int3.outputs[-1].text
    last_interaction_id = int3.id
    print(f"   Step3 完了: {int3.id}")

    if status == "ベスト版":
        if best_outline_prompt:
            print("   Step3.1: ベスト版の構成強化")
            int31 = _run_interaction_with_quota_handling(
                client,
                "この記事をベスト版記事として再構成し、不足観点を補ってください。",
                best_outline_prompt,
                previous_id=last_interaction_id,
            )
            last_interaction_id = int31.id
            print(f"   Step3.1 完了: {int31.id}")
            time.sleep(10)
        else:
            print("   031-best-outline-prompt.txt が見つからないため Step3.1 をスキップします")

        if best_enhancer_prompt:
            print("   Step3.2: ベスト版へ磨き込み")
            int32 = _run_interaction_with_quota_handling(
                client,
                "この記事と強化済み構成を統合し、公開可能なベスト版へ仕上げてください。",
                best_enhancer_prompt,
                previous_id=last_interaction_id,
            )
            final_text = int32.outputs[-1].text
            print(f"   Step3.2 完了: {int32.id}")
        else:
            print("   032-best-article-enhancer-prompt.txt が見つからないため Step3.2 をスキップします")

    return final_text


def run_pipeline_with_fallback(transcript: dict, gemini_api_keys, status: str = "単品") -> Optional[str]:
    """
    quota / rate limit を検知した場合だけ次の Gemini キーへ退避する。
    """
    try:
        writer_raw = _load_prompt("01-writer-prompt.txt")
        drafter_prompt = _parse_writer_prompt(writer_raw, status)
        editor_prompt = _load_prompt("02-editor-prompt.txt")
        director_prompt = _load_prompt("03-director-prompt.txt")
        best_outline_prompt = _load_optional_prompt("031-best-outline-prompt.txt")
        best_enhancer_prompt = _load_optional_prompt("032-best-article-enhancer-prompt.txt")
        print(f"   プロンプト読み込み完了: 01-writer({status}) / 02-editor / 03-director")
    except FileNotFoundError as error:
        print(f"   プロンプトファイルエラー: {error}")
        return None

    raw_candidates = _normalize_api_key_candidates(gemini_api_keys)
    candidates: list[tuple[str, str]] = []
    for label, api_key in raw_candidates:
        if _is_exhausted_key(api_key):
            print(f"   {label} はこの run で quota 到達済みのためスキップします")
            continue
        candidates.append((label, api_key))

    if not candidates:
        if raw_candidates:
            print("   この run で利用可能な Gemini キーが残っていません")
        else:
            print("   Gemini APIキーが設定されていません")
        return None

    for index, (label, api_key) in enumerate(candidates, start=1):
        try:
            print(f"   Geminiキーを使用: {label} ({index}/{len(candidates)})")
            client = genai.Client(api_key=api_key)
            return _run_pipeline_with_candidate_client(
                client,
                transcript,
                status,
                drafter_prompt,
                editor_prompt,
                director_prompt,
                best_outline_prompt,
                best_enhancer_prompt,
            )
        except GeminiQuotaExceededError as error:
            print(f"   {label} が quota / rate limit に到達しました: {error}")
            _mark_key_exhausted(api_key)
            if index >= len(candidates):
                print("   利用可能な Gemini キーを使い切ったため停止します")
                return None
            next_label = candidates[index][0]
            print(f"   {next_label} に切り替えて続行します")
        except Exception as error:
            print(f"   パイプラインエラー: {error}")
            return None

    return None


def _run_interaction(client, input_text: str, system_prompt: str, previous_id: Optional[str] = None):
    """Gemini Interaction Hub を使用したリクエスト実行"""
    full_input = f"【指示・行動指針】\n{system_prompt}\n\n【処理対象データ】\n{input_text}"

    try:
        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=full_input,
            previous_interaction_id=previous_id,
            generation_config={
                "temperature": 0.5,
                "thinking_level": "high"
            }
        )
        return interaction
    except Exception as e:
        if _is_quota_error(e):
            raise e
        print(f"   ❌ APIエラー: {e}")
        raise e


def run_pipeline(transcript: dict, gemini_api_key: str, status: str = "単品") -> Optional[str]:
    """
    3段階AI生成パイプライン
    status によって Drafter のプロンプトを切り替える（prompts/ から読み込み）

    Args:
        transcript: {"title": "...", "captions": "...", "video_id": "...", "url": "..."}
        gemini_api_key: Gemini APIキー
        status: "単品" / "情報" / "複数"

    Returns:
        最終Markdown文字列 または None
    """
    # プロンプトを prompts/ フォルダから読み込む
    try:
        writer_raw = _load_prompt("01-writer-prompt.txt")
        drafter_prompt = _parse_writer_prompt(writer_raw, status)
        editor_prompt = _load_prompt("02-editor-prompt.txt")
        director_prompt = _load_prompt("03-director-prompt.txt")
        best_outline_prompt = _load_optional_prompt("031-best-outline-prompt.txt")
        best_enhancer_prompt = _load_optional_prompt("032-best-article-enhancer-prompt.txt")
        print(f"   📄 プロンプト読み込み完了: 01-writer({status}) / 02-editor / 03-director")
    except FileNotFoundError as e:
        print(f"   ❌ プロンプトファイルエラー: {e}")
        return None

    client = genai.Client(api_key=gemini_api_key)
    captions = transcript["captions"]

    try:
        # Step 1: Drafter (初稿作成)
        print(f"   ✍️  Step1: 初稿作成中 (種別: {status})...")
        int1 = _run_interaction(client, captions, drafter_prompt)
        print(f"   ✅ 初稿完成 (ID: {int1.id})")
        time.sleep(10)

        # Step 2: Editor (プロ編集)
        print(f"   ✏️  Step2: プロ編集中...")
        int2 = _run_interaction(client, "上記の下書きを編集してください。", editor_prompt, previous_id=int1.id)
        print(f"   ✅ 編集完了 (ID: {int2.id})")
        time.sleep(10)

        # Step 3: Director (最終品質チェック)
        print(f"   👑 Step3: 最終品質チェック中...")
        int3 = _run_interaction(client, "上記の記事を100点満点に仕上げてください。", director_prompt, previous_id=int2.id)
        final_text = int3.outputs[-1].text
        last_interaction_id = int3.id
        print(f"   ✅ 最終版完成 (ID: {int3.id})")

        # Step 3.1: ベスト記事化の構成補強（量産元のみ）
        if status == "量産元":
            if best_outline_prompt:
                print(f"   🧭 Step3.1: ベスト記事化の補強設計中...")
                int31 = _run_interaction(
                    client,
                    "上記の記事を量産元記事として評価し、検索意図の抜け漏れ、追加すべき見出し、FAQ、比較軸を整理してください。",
                    best_outline_prompt,
                    previous_id=last_interaction_id,
                )
                last_interaction_id = int31.id
                print(f"   ✅ 補強設計完了 (ID: {int31.id})")
                time.sleep(10)
            else:
                print("   ⏭️ 031-best-outline-prompt.txt 未検出のためスキップ")

            if best_enhancer_prompt:
                print(f"   🚀 Step3.2: ベスト記事へ増強中...")
                int32 = _run_interaction(
                    client,
                    "上記の通常記事と補強設計を統合し、量産元として使える完成版のベスト記事に仕上げてください。",
                    best_enhancer_prompt,
                    previous_id=last_interaction_id,
                )
                final_text = int32.outputs[-1].text
                print(f"   ✅ ベスト記事化完了 (ID: {int32.id})")
            else:
                print("   ⏭️ 032-best-article-enhancer-prompt.txt 未検出のためスキップ")

        return final_text

    except Exception as e:
        print(f"   ❌ パイプラインエラー: {e}")
        return None
