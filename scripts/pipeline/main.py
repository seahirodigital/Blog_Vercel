"""
Vibe Blog Engine - メインパイプライン
スプレッドシート → 文字起こし → 3段階AI → OneDrive保存

GitHub Actions または ローカルから実行可能
"""

import os
import re
import sys
import hashlib
import importlib.util
import requests
from datetime import datetime
from dotenv import load_dotenv

# 環境変数読み込み（ローカル実行時用）
load_dotenv()

# モジュールインポート
from modules import sheets_reader, apify_fetcher, blog_pipeline, onedrive_sync

# 設定
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "動画リスト")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_TOKEN_SUB = os.getenv("GEMINI_TOKEN_sub", "") or os.getenv("GEMINI_TOKEN_SUB", "")
GEMINI_TOKEN_SUB2 = os.getenv("GEMINI_TOKEN_sub2", "") or os.getenv("GEMINI_TOKEN_SUB2", "")


def _make_safe_filename(title: str, max_length: int = 60) -> str:
    """ファイル名に使えない文字を除去"""
    safe = re.sub(r'[\\/:*?"<>|]', '', title)
    return safe[:max_length].strip()


def _prepend_source_url(markdown: str, video_url: str) -> str:
    source_url = str(video_url or "").strip()
    body = str(markdown or "").strip()
    if not source_url:
        return body
    if body.startswith(source_url):
        return body
    if not body:
        return f"{source_url}\n"
    return f"{source_url}\n\n{body}"


def _build_gemini_key_candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, api_key in (
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("GEMINI_TOKEN_sub", GEMINI_TOKEN_SUB),
        ("GEMINI_TOKEN_SUB2", GEMINI_TOKEN_SUB2),
    ):
        normalized = str(api_key or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append((label, normalized))
    return candidates


def process_single(row: dict, index: int, total: int) -> dict:
    """
    1本の動画を処理する

    Returns:
        {"success": bool, "title": str, "filename": str, "url": str}
    """
    url = row.get("動画URL", "").strip()
    status = str(row.get("状況", "単品")).strip()
    is_mass_source = status == "量産元"

    print(f"\n{'='*60}")
    print(f"📹 [{index}/{total}] 処理開始")
    print(f"   URL: {url}")
    print(f"   種別: {status}")
    print(f"   フロー: {'通常 + ベスト記事化' if is_mass_source else '通常'}")
    print(f"{'='*60}")

    result = {"success": False, "title": "", "filename": "", "url": url}

    # Step 1: 文字起こし取得
    transcript = apify_fetcher.get_transcript(url, APIFY_API_KEY)
    if not transcript:
        print("   ⚠️ 文字起こし取得失敗 - スキップ")
        return result

    result["title"] = transcript["title"]

    # Step 2: AI生成（量産元は 01→02→03→031→032 まで拡張）
    markdown = blog_pipeline.run_pipeline_with_fallback(transcript, _build_gemini_key_candidates(), status=status)
    if not markdown:
        print("   ⚠️ AI生成失敗 - スキップ")
        return result

    # Step 3: アフィリエイトリンク自動挿入（C案: OneDrive直接参照）
    print("   🔗 Step 3: アフィリエイトリンク挿入中...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    aff_script = os.path.join(script_dir, "prompts", "04-affiliate-link-manager", "insert_affiliate_links.py")

    if os.path.exists(aff_script):
        try:
            spec = importlib.util.spec_from_file_location("insert_affiliate_links", aff_script)
            aff_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(aff_mod)
            # 新インターフェース: markdown文字列を渡し、挿入済み文字列を返す
            markdown = aff_mod.insert_affiliate_links(markdown)
            print("   ✅ アフィリエイトリンク挿入完了")
        except Exception as e:
            print(f"   ⚠️ アフィリエイトリンク挿入失敗（続行します）: {e}")
    else:
        print("   ⏭️ アフィリエイトスクリプト未検出 - スキップ")

    # Step 3.5: Amazonアフィリエイトリンク自動挿入
    #   タイトルから商品名を抽出 → Amazon検索 → ASIN取得 → 記事へ挿入
    print("   🛒 Step 3.5: Amazonアフィリエイト自動挿入中...")
    amz_script = os.path.join(script_dir, "prompts", "04-affiliate-link-manager", "insert_amazon_affiliate.py")
    if os.path.exists(amz_script):
        try:
            spec = importlib.util.spec_from_file_location("insert_amazon_affiliate", amz_script)
            amz_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(amz_mod)
            markdown = amz_mod.insert_amazon_affiliate(markdown, transcript["title"])
        except Exception as e:
            print(f"   ⚠️ Amazonアフィリエイト挿入失敗（続行します）: {e}")
    else:
        print("   ⏭️ Amazonアフィリエイトスクリプト未検出 - スキップ")

    markdown = _prepend_source_url(markdown, url)

    # Step 4: OneDriveに保存（記事はクリーンなまま）
    now = datetime.now()
    safe_title = _make_safe_filename(transcript["title"])
    filename = f"{now.strftime('%Y%m%d')}_{now.strftime('%H%M')}_{safe_title}.md"

    onedrive_url = onedrive_sync.upload_markdown(filename, markdown)
    result["filename"] = filename

    # Step 4.5: YouTube URL を GitHub Variables に保存（記事内容とは完全分離）
    gh_token = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN")
    gh_repo = os.getenv("GITHUB_REPO", "seahirodigital/Blog_Vercel")
    if gh_token and url:
        try:
            hash_key = hashlib.md5(filename.encode()).hexdigest()[:8].upper()
            var_name = f"YT_SOURCE_{hash_key}"
            gh_headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            gh_api = f"https://api.github.com/repos/{gh_repo}/actions/variables"
            # 既存なら PATCH、なければ POST
            r = requests.patch(
                f"{gh_api}/{var_name}",
                json={"name": var_name, "value": url},
                headers=gh_headers,
            )
            if r.status_code == 404:
                requests.post(gh_api, json={"name": var_name, "value": url}, headers=gh_headers)
            print(f"   🔗 YouTube URL を GitHub Variables に保存: {var_name}")
        except Exception as e:
            print(f"   ⚠️ YouTube URL の記録に失敗（続行します）: {e}")

    # Step 5: スプレッドシートのステータス更新
    sheets_reader.update_status(SPREADSHEET_ID, SHEET_NAME, url, "完了")

    result["success"] = True
    print(f"\n   🎉 完了: {filename}")
    return result


def main():
    """メインエントリーポイント"""
    print("=" * 60)
    print("🚀 Vibe Blog Engine - パイプライン起動")
    print(f"   時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # バリデーション
    missing = []
    if not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")
    if not APIFY_API_KEY:
        missing.append("APIFY_API_KEY")
    if not (GEMINI_API_KEY or GEMINI_TOKEN_SUB or GEMINI_TOKEN_SUB2):
        missing.append("GEMINI_API_KEY / GEMINI_TOKEN_sub / GEMINI_TOKEN_SUB2")

    if missing:
        print(f"❌ 必須環境変数が未設定です: {', '.join(missing)}")
        sys.exit(1)

    # スプレッドシートから対象を取得
    print("\n📋 スプレッドシートから対象動画を取得中...")
    rows = sheets_reader.get_pending_rows(SPREADSHEET_ID, SHEET_NAME, ["単品", "複数", "情報", "量産元"])

    if not rows:
        print("✅ 処理対象がありません。パイプラインを終了します。")
        return

    print(f"\n📊 処理対象: {len(rows)}件")

    # バッチ処理
    results = []
    for i, row in enumerate(rows, 1):
        result = process_single(row, i, len(rows))
        results.append(result)

    # 最終レポート
    print("\n" + "=" * 60)
    print("📊 最終レポート")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    print(f"   ✅ 成功: {success_count}件")
    print(f"   ❌ 失敗: {fail_count}件")

    for r in results:
        icon = "✅" if r["success"] else "❌"
        print(f"   {icon} {r.get('title', r['url'])} → {r.get('filename', 'N/A')}")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
