"""
note下書きポスター v1.0
Playwright でnote.comにログインし、Markdownから下書き記事を作成する。

【2段階設計】
Phase 1: ログイン → タイトル・本文ペースト → 下書き保存
Phase 2: OGP展開JS（note_ogp_formatter.js）を3回実行

使い方:
  python note_draft_poster.py <markdown_file_or_content>
  python note_draft_poster.py --content "# タイトル\n本文..."
"""

import os
import sys
import re
import time
import argparse
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────
NOTE_URL       = "https://note.com/"
NOTE_LOGIN_URL = "https://note.com/login"
NOTE_EMAIL     = os.getenv("NOTE_EMAIL", "seahiro@gmail.com")
NOTE_PASSWORD  = os.getenv("NOTE_PASSWORD", "appleblog0227")

# OGP Formatter JSの場所（同ディレクトリの prompts/ 配下）
SCRIPT_DIR     = Path(__file__).parent
OGP_JS_PATH    = SCRIPT_DIR / "prompts" / "05-note_ogp_formatter.js"


# ── Markdown前処理 ─────────────────────────────────────
def extract_title_and_body(markdown: str) -> tuple[str, str]:
    """
    Markdownから H1 をタイトル、それ以降を本文として分離。
    不要セクション（YouTube埋め込み、Captions）は除外。
    """
    lines = markdown.replace('\r\n', '\n').split('\n')

    title = ""
    body_start = 0

    # H1を探す
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('# ') and not stripped.startswith('## '):
            title = stripped.lstrip('# ').strip()
            body_start = i + 1
            break

    if not title:
        # H1がなければ最初の非空行をタイトルに
        for i, line in enumerate(lines):
            if line.strip():
                title = line.strip().lstrip('# ').strip()
                body_start = i + 1
                break

    # 本文を構築（不要セクション除外）
    body_lines = []
    skip = False
    for line in lines[body_start:]:
        stripped = line.strip()

        # 除外セクション判定
        if stripped.startswith('## 🎬') or stripped.startswith('## Captions'):
            skip = True
            continue
        if skip and stripped.startswith('## '):
            skip = False  # 次のH2で復帰

        if not skip:
            body_lines.append(line)

    body = '\n'.join(body_lines).strip()
    return title, body


# ── Phase 1: ログイン＆下書き保存 ──────────────────────
def _ensure_login(page):
    """ログイン状態をチェックし、未ログインならログインする"""
    page.goto(NOTE_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # ログイン済みチェック: プロフィールアイコンや投稿ボタンがあればOK
    if page.query_selector('[data-test="header-user-menu"]') or page.query_selector('a[href="/notes/new"]'):
        print("   ✅ 既にログイン済み")
        return

    print("   🔑 ログイン処理を開始...")
    page.goto(NOTE_LOGIN_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # メールアドレス入力
    email_input = page.wait_for_selector('input[name="login"], input[type="email"], input[placeholder*="メール"]', timeout=10000)
    email_input.click()
    email_input.fill(NOTE_EMAIL)
    time.sleep(0.5)

    # パスワード入力
    pw_input = page.wait_for_selector('input[name="password"], input[type="password"]', timeout=10000)
    pw_input.click()
    pw_input.fill(NOTE_PASSWORD)
    time.sleep(0.5)

    # ログインボタン
    login_btn = page.query_selector('button[type="submit"], button:has-text("ログイン")')
    if login_btn:
        login_btn.click()
    else:
        pw_input.press("Enter")

    # ログイン完了待ち
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)
    print("   ✅ ログイン完了")


def _paste_via_clipboard(page, selector_or_element, text: str):
    """クリップボード経由でテキストをペースト（日本語文字化け回避）"""
    # クリップボードにセット
    page.evaluate(f"""
        (async () => {{
            await navigator.clipboard.writeText({repr(text)});
        }})()
    """)
    time.sleep(0.3)

    # 要素をクリック
    if isinstance(selector_or_element, str):
        el = page.wait_for_selector(selector_or_element, timeout=10000)
    else:
        el = selector_or_element
    el.click()
    time.sleep(0.3)

    # Ctrl+V でペースト
    page.keyboard.press("Control+a")  # 既存をすべて選択
    time.sleep(0.1)
    page.keyboard.press("Control+v")
    time.sleep(1)


def _create_draft(page, title: str, body: str):
    """記事作成画面でタイトル・本文をペーストして下書き保存"""

    # 新規記事作成画面へ
    print("   📝 記事作成画面を開きます...")
    page.goto("https://note.com/notes/new", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # タイトル入力（Ctrl+V）
    print("   📌 タイトルをペースト...")
    title_sel = '.note-editor__title-input, [placeholder*="タイトル"], [placeholder*="記事タイトル"]'
    _paste_via_clipboard(page, title_sel, title)
    time.sleep(1)

    # タイトルが入ったか確認
    for attempt in range(3):
        title_el = page.query_selector(title_sel)
        if title_el:
            current = title_el.inner_text().strip() or title_el.input_value() if title_el.evaluate('el => el.tagName') == 'INPUT' else title_el.inner_text().strip()
            if current and len(current) > 3:
                print(f"   ✅ タイトル確認: 「{current[:30]}...」")
                break
        print(f"   ⚠️ タイトル未入力（リトライ {attempt+1}/3）")
        _paste_via_clipboard(page, title_sel, title)
        time.sleep(1)

    # 本文入力（Ctrl+V）
    print("   📄 本文をペースト...")
    body_sel = '.note-editable, [contenteditable="true"]'
    _paste_via_clipboard(page, body_sel, body)
    time.sleep(2)

    # 本文が入ったか確認
    for attempt in range(3):
        body_el = page.query_selector(body_sel)
        if body_el:
            body_text = body_el.inner_text().strip()
            if body_text and len(body_text) > 10:
                print(f"   ✅ 本文確認: {len(body_text)} 文字")
                break
        print(f"   ⚠️ 本文未入力（リトライ {attempt+1}/3）")
        _paste_via_clipboard(page, body_sel, body)
        time.sleep(2)

    return True


# ── Phase 2: OGP展開JS実行 ────────────────────────────
def _run_ogp_formatter(page):
    """OGP Formatter JSを3回実行してリンク展開・見出し変換を行う"""
    if not OGP_JS_PATH.exists():
        print(f"   ⚠️ OGP Formatter JSが見つかりません: {OGP_JS_PATH}")
        return

    js_code = OGP_JS_PATH.read_text(encoding="utf-8")
    print("   🔧 OGP Formatter JS 実行開始...")

    # 3回実行（DOMの構造上1回では不完全）
    schedules = [(1, 7), (2, 5), (3, 0)]
    for run_num, wait_sec in schedules:
        print(f"   ▶️  {run_num}回目のJS実行...")
        try:
            page.evaluate(js_code)
        except Exception as e:
            print(f"   ⚠️ JS実行エラー（続行）: {e}")
        if wait_sec > 0:
            print(f"   ⏳ {wait_sec}秒待機...")
            time.sleep(wait_sec)

    print("   ✅ OGP Formatter 完了")


# ── 下書き保存 ─────────────────────────────────────────
def _save_draft(page):
    """下書き保存ボタンをクリック"""
    print("   💾 下書き保存中...")

    # 下書き保存ボタンを探す
    save_selectors = [
        'button:has-text("下書き保存")',
        'button:has-text("保存")',
        '[data-test="save-draft"]',
        '.p-postEditor__action button',
    ]

    for sel in save_selectors:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            btn.click()
            time.sleep(3)
            print("   ✅ 下書き保存完了")

            # 保存後のURL取得
            current_url = page.url
            print(f"   🔗 URL: {current_url}")
            return current_url

    print("   ⚠️ 下書き保存ボタンが見つかりませんでした")
    return None


# ── エントリーポイント ──────────────────────────────────
def post_draft_to_note(markdown: str, headless: bool = False, skip_ogp: bool = False) -> dict:
    """
    noteに下書きを投稿するメイン関数。

    Args:
        markdown: Markdown文字列
        headless: ヘッドレスモードで実行するか（デフォルト: False = ブラウザ表示）
        skip_ogp: OGP展開をスキップするか

    Returns:
        {"success": bool, "url": str, "title": str}
    """
    from playwright.sync_api import sync_playwright

    title, body = extract_title_and_body(markdown)
    if not title or not body:
        print("❌ タイトルまたは本文が空です")
        return {"success": False, "url": "", "title": title}

    print(f"📋 タイトル: 「{title}」")
    print(f"📋 本文: {len(body)} 文字")

    result = {"success": False, "url": "", "title": title}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # クリップボードAPIを有効化
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()

        try:
            # Phase 1: ログイン → 入力 → 下書き保存
            print("\n── Phase 1: ログイン＆下書き作成 ──")
            _ensure_login(page)
            _create_draft(page, title, body)

            # Phase 2: OGP展開
            if not skip_ogp:
                print("\n── Phase 2: OGP展開 ──")
                _run_ogp_formatter(page)

            # 下書き保存
            url = _save_draft(page)
            if url:
                result["success"] = True
                result["url"] = url

        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()
        finally:
            time.sleep(2)
            browser.close()

    return result


# ── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="note.com 下書きポスター")
    parser.add_argument("file", nargs="?", help="Markdownファイルパス")
    parser.add_argument("--content", help="直接Markdown文字列を指定")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    parser.add_argument("--skip-ogp", action="store_true", help="OGP展開をスキップ")
    args = parser.parse_args()

    if args.content:
        md = args.content
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            md = f.read()
    else:
        print("❌ Markdownファイルパスまたは --content を指定してください")
        sys.exit(1)

    result = post_draft_to_note(md, headless=args.headless, skip_ogp=args.skip_ogp)

    if result["success"]:
        print(f"\n🎉 下書き投稿成功！")
        print(f"   タイトル: {result['title']}")
        print(f"   URL: {result['url']}")
    else:
        print(f"\n❌ 下書き投稿失敗")
        sys.exit(1)
