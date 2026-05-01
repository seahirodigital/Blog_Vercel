"""
Vibe Blog Engine - メインパイプライン
スプレッドシート → 文字起こし → 3段階AI → OneDrive保存

GitHub Actions または ローカルから実行可能
"""

from __future__ import annotations

import os
import re
import sys
import hashlib
import json
import importlib.util
import requests
from datetime import datetime
from dotenv import load_dotenv

# 環境変数読み込み（ローカル実行時用）
load_dotenv()

# モジュールインポート
from modules import amazon_product_fetcher

# 設定
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "動画リスト")
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_TOKEN_SUB = os.getenv("GEMINI_TOKEN_sub", "") or os.getenv("GEMINI_TOKEN_SUB", "")
GEMINI_TOKEN_SUB2 = os.getenv("GEMINI_TOKEN_sub2", "") or os.getenv("GEMINI_TOKEN_SUB2", "")
GEMINI_TOKEN_SUB3 = os.getenv("GEMINI_TOKEN_sub3", "") or os.getenv("GEMINI_TOKEN_SUB3", "")
INPUT_SOURCE_TYPE = os.getenv("INPUT_SOURCE_TYPE", "").strip()
INPUT_SOURCE_URLS = os.getenv("INPUT_SOURCE_URLS", "").strip()
INPUT_SOURCE_URL = os.getenv("INPUT_SOURCE_URL", "").strip()
INPUT_SOURCE_PAYLOADS = os.getenv("INPUT_SOURCE_PAYLOADS", "").strip()
INPUT_STATUS = os.getenv("INPUT_STATUS", "単品").strip() or "単品"
_GEMINI_CANDIDATES_LOGGED = False


def _make_safe_filename(title: str, max_length: int = 60) -> str:
    """ファイル名に使えない文字を除去"""
    safe = re.sub(r'[\\/:*?"<>|]', '', title)
    return safe[:max_length].strip()


def _fingerprint_secret(secret: str) -> str:
    normalized = str(secret or "").strip()
    if not normalized:
        return "missing"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def _raw_gemini_key_sources() -> list[tuple[str, str]]:
    return [
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("GEMINI_TOKEN_sub", GEMINI_TOKEN_SUB),
        ("GEMINI_TOKEN_SUB2", GEMINI_TOKEN_SUB2),
        ("GEMINI_TOKEN_SUB3", GEMINI_TOKEN_SUB3),
    ]


def _build_gemini_key_candidates() -> list[tuple[str, str]]:
    global _GEMINI_CANDIDATES_LOGGED
    candidates: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    candidate_labels: list[str] = []
    duplicate_messages: list[str] = []

    for label, api_key in _raw_gemini_key_sources():
        normalized = str(api_key or "").strip()
        if not normalized:
            continue

        fingerprint = _fingerprint_secret(normalized)
        display_label = f"{label}[{fingerprint}]"

        if normalized in seen:
            duplicate_messages.append(f"{display_label} は {seen[normalized]} と同じキーです")
            continue

        seen[normalized] = display_label
        candidate_labels.append(display_label)
        candidates.append((display_label, normalized))

    if not _GEMINI_CANDIDATES_LOGGED:
        if candidate_labels:
            print(f"   Gemini候補: {', '.join(candidate_labels)}")
        else:
            print("   Gemini候補: なし")
        for message in duplicate_messages:
            print(f"   注意: {message}")
        _GEMINI_CANDIDATES_LOGGED = True

    return candidates


def _normalize_source_type(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"amazon", "amzn"}:
        return "amazon"
    return "youtube"


def _parse_input_urls(*values: str) -> list[str]:
    urls: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                urls.extend(str(item).strip() for item in parsed if str(item).strip())
                continue
            if isinstance(parsed, str) and parsed.strip():
                urls.append(parsed.strip())
                continue
        except json.JSONDecodeError:
            pass

        normalized = text.replace("\r", "\n").replace(",", "\n")
        urls.extend(part.strip() for part in normalized.split("\n") if part.strip())

    unique: list[str] = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _parse_input_payloads(value: str) -> list[dict]:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        print(f"   ⚠️ source_payloads JSON parse error: {error}")
        return []

    if isinstance(parsed, dict):
        candidates = parsed.get("items") if isinstance(parsed.get("items"), list) else [parsed]
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        return []

    payloads: list[dict] = []
    for item in candidates:
        if isinstance(item, dict):
            payloads.append(item)
    return payloads


def _payload_source_url(payload: dict, fallback_url: str = "") -> str:
    for key in ("url", "finalUrl", "canonicalUrl", "sourceUrl", "productUrl"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return fallback_url


def _prepend_source_metadata(markdown: str, source_type: str) -> str:
    normalized = _normalize_source_type(source_type)
    if re.search(r"<!--\s*source_type\s*:", markdown, flags=re.I):
        return markdown
    return f"<!-- source_type: {normalized} -->\n\n{markdown}"


def _save_source_variable(filename: str, source_url: str, source_type: str):
    gh_token = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN")
    gh_repo = os.getenv("GITHUB_REPO", "seahirodigital/Blog_Vercel")
    if not gh_token or not source_url:
        return

    hash_key = hashlib.md5(filename.encode()).hexdigest()[:8].upper()
    prefix = "AMZN_SOURCE" if _normalize_source_type(source_type) == "amazon" else "YT_SOURCE"
    variables = {
        f"{prefix}_{hash_key}": source_url,
        f"SOURCE_TYPE_{hash_key}": _normalize_source_type(source_type),
    }
    gh_headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    gh_api = f"https://api.github.com/repos/{gh_repo}/actions/variables"

    for var_name, value in variables.items():
        r = requests.patch(
            f"{gh_api}/{var_name}",
            json={"name": var_name, "value": value},
            headers=gh_headers,
        )
        if r.status_code == 404:
            requests.post(gh_api, json={"name": var_name, "value": value}, headers=gh_headers)
        print(f"   🔗 source metadata を GitHub Variables に保存: {var_name}")


def _run_article_generation(
    *,
    transcript: dict,
    url: str,
    status: str,
    index: int,
    total: int,
    source_type: str = "youtube",
    update_sheet: bool = False,
) -> dict:
    result = {"success": False, "title": "", "filename": "", "url": url}
    normalized_source = _normalize_source_type(source_type)
    result["title"] = transcript.get("title", "")

    from modules import blog_pipeline, onedrive_sync

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

    # Step 4: OneDriveに保存（記事はクリーンなまま）
    now = datetime.now()
    safe_title = _make_safe_filename(transcript["title"])
    source_prefix = "AMZN_" if normalized_source == "amazon" else ""
    filename = f"{now.strftime('%Y%m%d')}_{now.strftime('%H%M')}_{source_prefix}{safe_title}.md"
    markdown = _prepend_source_metadata(markdown, normalized_source)

    onedrive_url = onedrive_sync.upload_markdown(filename, markdown)
    result["filename"] = filename

    # Step 4.5: 元URLとsource種別を GitHub Variables に保存（記事内容とは分離）
    try:
        _save_source_variable(filename, url, normalized_source)
    except Exception as e:
        print(f"   ⚠️ source metadata の記録に失敗（続行します）: {e}")

    # Step 5: スプレッドシートのステータス更新
    if update_sheet:
        from modules import sheets_reader

        sheets_reader.update_status(SPREADSHEET_ID, SHEET_NAME, url, "完了")

    result["success"] = True
    print(f"\n   🎉 完了: {filename}")
    return result


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
    from modules import apify_fetcher

    transcript = apify_fetcher.get_transcript(url, APIFY_API_KEY)
    if not transcript:
        print("   ⚠️ 文字起こし取得失敗 - スキップ")
        return result

    return _run_article_generation(
        transcript=transcript,
        url=url,
        status=status,
        index=index,
        total=total,
        source_type="youtube",
        update_sheet=True,
    )


def process_amazon_url(product_url: str, index: int, total: int) -> dict:
    print(f"\n{'='*60}")
    print(f"🛒 [{index}/{total}] Amazon商品処理開始")
    print(f"   URL: {product_url}")
    print("   入力: URLのみ（サーバーHTML fallback）")
    print(f"{'='*60}")

    result = {"success": False, "title": "", "filename": "", "url": product_url}
    transcript = amazon_product_fetcher.get_product_details(product_url, APIFY_API_KEY)
    if not transcript:
        print("   ⚠️ Amazon商品詳細取得失敗 - スキップ")
        return result

    return _run_article_generation(
        transcript=transcript,
        url=product_url,
        status=INPUT_STATUS,
        index=index,
        total=total,
        source_type="amazon",
        update_sheet=False,
    )


def process_amazon_payload(payload: dict, fallback_url: str, index: int, total: int) -> dict:
    source_url = _payload_source_url(payload, fallback_url)
    print(f"\n{'='*60}")
    print(f"🛒 [{index}/{total}] Amazon商品処理開始")
    print(f"   URL: {source_url or fallback_url}")
    print("   入力: Chrome拡張抽出payload（Apify/サーバー再取得なし）")
    print(f"{'='*60}")

    result = {"success": False, "title": "", "filename": "", "url": source_url or fallback_url}
    transcript = amazon_product_fetcher.build_transcript_from_chrome_payload(payload, source_url or fallback_url)
    if not transcript:
        print("   ⚠️ Chrome抽出payloadから商品詳細を組み立てられませんでした - スキップ")
        return result

    return _run_article_generation(
        transcript=transcript,
        url=source_url or fallback_url,
        status=INPUT_STATUS,
        index=index,
        total=total,
        source_type="amazon",
        update_sheet=False,
    )


def main():
    """メインエントリーポイント"""
    print("=" * 60)
    print("🚀 Vibe Blog Engine - パイプライン起動")
    print(f"   時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    source_type = _normalize_source_type(INPUT_SOURCE_TYPE)
    direct_urls = _parse_input_urls(INPUT_SOURCE_URLS, INPUT_SOURCE_URL)
    source_payloads = _parse_input_payloads(INPUT_SOURCE_PAYLOADS)
    direct_amazon_mode = source_type == "amazon" and (len(direct_urls) > 0 or len(source_payloads) > 0)

    # バリデーション
    missing = []
    if not direct_amazon_mode and not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")
    if source_type != "amazon" and not APIFY_API_KEY:
        missing.append("APIFY_API_KEY")
    if not (GEMINI_API_KEY or GEMINI_TOKEN_SUB or GEMINI_TOKEN_SUB2 or GEMINI_TOKEN_SUB3):
        missing.append("GEMINI_API_KEY / GEMINI_TOKEN_sub / GEMINI_TOKEN_SUB2 / GEMINI_TOKEN_SUB3")

    if missing:
        print(f"❌ 必須環境変数が未設定です: {', '.join(missing)}")
        sys.exit(1)

    if direct_amazon_mode:
        payload_count = len(source_payloads)
        url_only_count = max(0, len(direct_urls) - payload_count)
        print(f"\n🛒 Amazon直接入力モード: Chrome payload {payload_count}件 / URLのみ {url_only_count}件")
        results = []
        total = payload_count + url_only_count
        for i, payload in enumerate(source_payloads, 1):
            fallback_url = direct_urls[i - 1] if i - 1 < len(direct_urls) else ""
            results.append(process_amazon_payload(payload, fallback_url, i, total))
        for offset, product_url in enumerate(direct_urls[payload_count:], 1):
            results.append(process_amazon_url(product_url, payload_count + offset, total))
        _print_final_report(results)
        return

    # スプレッドシートから対象を取得
    from modules import sheets_reader

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

    _print_final_report(results)


def _print_final_report(results: list[dict]):
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
