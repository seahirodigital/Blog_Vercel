"""
Vibe Blog Engine - メインパイプライン
スプレッドシート → 文字起こし → 3段階AI → OneDrive保存

GitHub Actions または ローカルから実行可能
"""

import os
import re
import sys
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


def _make_safe_filename(title: str, max_length: int = 60) -> str:
    """ファイル名に使えない文字を除去"""
    safe = re.sub(r'[\\/:*?"<>|]', '', title)
    return safe[:max_length].strip()


def process_single(row: dict, index: int, total: int) -> dict:
    """
    1本の動画を処理する

    Returns:
        {"success": bool, "title": str, "filename": str, "url": str}
    """
    url = row.get("動画URL", "").strip()
    status = str(row.get("状況", "単品")).strip()

    print(f"\n{'='*60}")
    print(f"📹 [{index}/{total}] 処理開始")
    print(f"   URL: {url}")
    print(f"   種別: {status}")
    print(f"{'='*60}")

    result = {"success": False, "title": "", "filename": "", "url": url}

    # Step 1: 文字起こし取得
    transcript = apify_fetcher.get_transcript(url, APIFY_API_KEY)
    if not transcript:
        print("   ⚠️ 文字起こし取得失敗 - スキップ")
        return result

    result["title"] = transcript["title"]

    # Step 2: 3段階AI生成
    markdown = blog_pipeline.run_pipeline(transcript, GEMINI_API_KEY, status=status)
    if not markdown:
        print("   ⚠️ AI生成失敗 - スキップ")
        return result

    # Step 3: OneDriveに保存
    now = datetime.now()
    safe_title = _make_safe_filename(transcript["title"])
    filename = f"{now.strftime('%Y%m%d')}_{now.strftime('%H%M')}_{safe_title}.md"

    onedrive_url = onedrive_sync.upload_markdown(filename, markdown)
    result["filename"] = filename

    # Step 4: スプレッドシートのステータス更新
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
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        print(f"❌ 必須環境変数が未設定です: {', '.join(missing)}")
        sys.exit(1)

    # スプレッドシートから対象を取得
    print("\n📋 スプレッドシートから対象動画を取得中...")
    rows = sheets_reader.get_pending_rows(SPREADSHEET_ID, SHEET_NAME, ["単品", "複数", "情報"])

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
