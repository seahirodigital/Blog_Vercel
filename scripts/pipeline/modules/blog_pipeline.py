"""
ブログ生成パイプライン (GitHub Actions 対応版)
Drafter → Editor → Chief の3段階生成
Gemini Interaction Hub を使用
"""

import os
import time
from google import genai
from typing import Optional

# Gemini 最新モデル
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ドラフト用スキルのマッピング (種別 → プロンプトテンプレート)
DRAFTER_PROMPTS = {
    "単品": """あなたはプロのガジェットブログライターです。
以下の文字起こしを元に、「一つの製品に特化した」SEOに強いブログ記事を初稿として作成してください。
- タイトルは具体的で検索に引っかかるもの
- 見出し (##, ###) を適切に使用
- スマホで読みやすいように改行を多めに
- メリット・デメリットを明確に
- 結論を最初と最後に配置
- Markdown形式で出力""",

    "情報": """あなたはプロのテック情報ブログライターです。
以下の文字起こしを元に、「複数の製品やニュースをまとめた」情報系SEOブログ記事を初稿として作成してください。
- 読者が一記事で全体像を把握できる構成
- 各トピックごとに見出し (##) で区切る
- ランキングやリスト形式を活用
- スマホで読みやすいように改行を多めに
- Markdown形式で出力""",

    "複数": """あなたはプロのガジェット比較ブログライターです。
以下の文字起こしを元に、「複数製品の比較レビュー」SEOブログ記事を初稿として作成してください。
- 比較表を含める
- 各製品のメリット・デメリットを明確に
- どんな人にどの製品がおすすめかを結論付ける
- Markdown形式で出力"""
}

EDITOR_PROMPT = """あなたはプロの編集者です。以下の記事を編集してください。
- 文章の読みやすさを向上（リズム・トーン統一）
- 冗長な部分を削除しつつ、情報量は維持
- SEOキーワードの自然な配置を確認
- スマホ閲覧を意識した改行・段落分け
- 事実誤認がないかチェック
- Markdown形式を維持して出力"""

CHIEF_PROMPT = """あなたは編集長です。以下の記事に最終品質チェックを行い、100点満点の完成稿に仕上げてください。
- ブランドトーン（親しみやすく、でもプロフェッショナル）の確認
- 導入文・締めの文が魅力的かチェック
- メタディスクリプション（120文字以内）をYAMLフロントマターとして追加
- 画像挿入ポイントをコメントで指示
- 最終的なMarkdown形式で出力"""


def _run_interaction(client, input_text: str, system_prompt: str, previous_id: Optional[str] = None):
    """Gemini Interaction Hub を使用したリクエスト実行"""
    full_input = f"【指示・行動指針】\n{system_prompt}\n\n【処理対象データ】\n{input_text}"

    max_retries = 3
    for i in range(max_retries):
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
            if "429" in str(e):
                wait_time = (i + 1) * 30
                print(f"   ⚠️ レート制限 (429)。{wait_time}秒待機... ({i+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"   ❌ APIエラー: {e}")
                raise e
    raise Exception("最大リトライ回数を超えました。")


def run_pipeline(transcript: dict, gemini_api_key: str, status: str = "単品") -> Optional[str]:
    """
    3段階AI生成パイプライン
    status によって Drafter のプロンプトを切り替える

    Args:
        transcript: {"title": "...", "captions": "...", "video_id": "...", "url": "..."}
        gemini_api_key: Gemini APIキー
        status: "単品" / "情報" / "複数"

    Returns:
        最終Markdown文字列 または None
    """
    client = genai.Client(api_key=gemini_api_key)
    captions = transcript["captions"]

    # Drafter のプロンプト選択
    drafter_prompt = DRAFTER_PROMPTS.get(status, DRAFTER_PROMPTS["単品"])

    try:
        # Step 1: Drafter (初稿作成)
        print(f"   ✍️  Step1: 初稿作成中 (種別: {status})...")
        int1 = _run_interaction(client, captions, drafter_prompt)
        print(f"   ✅ 初稿完成 (ID: {int1.id})")
        time.sleep(10)

        # Step 2: Editor (プロ編集)
        print(f"   ✏️  Step2: プロ編集中...")
        int2 = _run_interaction(client, "上記の下書きを編集してください。", EDITOR_PROMPT, previous_id=int1.id)
        print(f"   ✅ 編集完了 (ID: {int2.id})")
        time.sleep(10)

        # Step 3: Chief (最終品質チェック)
        print(f"   👑 Step3: 最終品質チェック中...")
        int3 = _run_interaction(client, "上記の記事を100点満点に仕上げてください。", CHIEF_PROMPT, previous_id=int2.id)
        final_text = int3.outputs[-1].text
        print(f"   ✅ 最終版完成 (ID: {int3.id})")

        return final_text

    except Exception as e:
        print(f"   ❌ パイプラインエラー: {e}")
        return None
