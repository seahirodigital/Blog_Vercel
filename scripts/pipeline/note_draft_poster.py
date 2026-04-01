"""
note下書きポスター v1.1
Playwright でnote.comにログインし、Markdownから下書き記事を作成する。

【2段階設計】
Phase 1: ログイン → タイトル・本文ペースト → 下書き保存
Phase 2: OGP展開JS（note_ogp_formatter.js）を3回実行

使い方:
  python note_draft_poster.py <markdown_file>
  python note_draft_poster.py --content "# タイトル\n本文..."
"""

import os
import sys
import re
import json
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
def extract_title_and_body(markdown: str) -> tuple:
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
        if stripped.startswith('## 🎬') or stripped.startswith('## Captions'):
            skip = True
            continue
        if skip and stripped.startswith('## '):
            skip = False
        if not skip:
            body_lines.append(line)

    body = '\n'.join(body_lines).strip()
    return title, body


# ── Phase 1: ログイン＆下書き保存 ──────────────────────
def _ensure_login(page):
    """ログイン状態をチェックし、未ログインならログインする"""
    page.goto(NOTE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # ログイン済みチェック
    logged_in = page.query_selector('[class*="UserMenu"], [class*="user-menu"], img[alt*="アイコン"]')
    if logged_in:
        print("   ✅ 既にログイン済み")
        return

    print("   🔑 ログイン処理を開始...")
    page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # note.comのログインフォームを段階的にセレクタ探索
    # ログインページのフォーム入力欄を検索
    email_selectors = [
        'input[type="email"]',
        'input[name="login"]',
        'input[name="email"]',
        'input[placeholder*="メール"]',
        'input[placeholder*="note ID"]',
        'input[placeholder*="アドレス"]',
        # 一般的なフォーム構造
        'form input:first-of-type',
        'input:not([type="password"]):not([type="hidden"]):not([type="submit"])',
    ]

    email_input = None
    for sel in email_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                email_input = el
                print(f"   📧 メール欄を発見: {sel}")
                break
        except Exception:
            continue

    if not email_input:
        # デバッグ: ページの全input要素を列挙
        inputs_info = page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(el => ({
                type: el.type,
                name: el.name,
                id: el.id,
                placeholder: el.placeholder,
                className: el.className,
                visible: el.offsetParent !== null
            }))
        """)
        print(f"   🔍 ページ上のinput要素: {json.dumps(inputs_info, ensure_ascii=False, indent=2)}")

        # スクリーンショットを残す（デバッグ用）
        page.screenshot(path="/tmp/note_login_debug.png")
        print("   📸 デバッグスクショ: /tmp/note_login_debug.png")

        raise Exception("メールアドレス入力欄が見つかりません。ログインページの構造が変わった可能性があります。")

    # メールアドレス入力
    email_input.click()
    time.sleep(0.3)
    email_input.fill(NOTE_EMAIL)
    time.sleep(0.5)

    # パスワード入力
    pw_selectors = [
        'input[type="password"]',
        'input[name="password"]',
    ]
    pw_input = None
    for sel in pw_selectors:
        el = page.query_selector(sel)
        if el and el.is_visible():
            pw_input = el
            print(f"   🔒 パスワード欄を発見: {sel}")
            break

    if not pw_input:
        raise Exception("パスワード入力欄が見つかりません")

    pw_input.click()
    time.sleep(0.3)
    pw_input.fill(NOTE_PASSWORD)
    time.sleep(0.5)

    # ログインボタン
    login_selectors = [
        'button[type="submit"]',
        'button:has-text("ログイン")',
        'input[type="submit"]',
        'button[class*="login"]',
        'button[class*="Login"]',
    ]
    clicked = False
    for sel in login_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                clicked = True
                print(f"   🖱️ ログインボタンをクリック: {sel}")
                break
        except Exception:
            continue

    if not clicked:
        pw_input.press("Enter")
        print("   ⏎ Enterキーでログイン")

    # ログイン完了待ち
    page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(4)
    print("   ✅ ログイン完了")


def _paste_text(page, element, text: str):
    """テキストを安全にペースト（クリップボード経由、フォールバック付き）"""
    element.click()
    time.sleep(0.3)

    # 方法1: evaluate で直接テキストセット → inputイベント発火
    try:
        page.evaluate("""
            ([el, text]) => {
                el.focus();
                // contenteditable の場合
                if (el.contentEditable === 'true') {
                    el.innerHTML = '';
                    el.textContent = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    // input/textarea の場合
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set || Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    )?.set;
                    if (nativeSetter) nativeSetter.call(el, text);
                    else el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        """, [element, text])
        time.sleep(0.5)
        return
    except Exception as e:
        print(f"   ⚠️ evaluate方式失敗、クリップボード方式へ: {e}")

    # 方法2: クリップボード経由
    try:
        page.evaluate("text => navigator.clipboard.writeText(text)", text)
        time.sleep(0.3)
        element.click()
        time.sleep(0.2)
        page.keyboard.press("Control+a")
        time.sleep(0.1)
        page.keyboard.press("Control+v")
        time.sleep(1)
    except Exception as e:
        print(f"   ⚠️ クリップボード方式も失敗、fill方式へ: {e}")
        # 方法3: fill（最終手段）
        element.click()
        element.press("Control+a")
        element.type(text, delay=5)
        time.sleep(0.5)


def _create_draft(page, title: str, body: str):
    """記事作成画面でタイトル・本文をペーストして下書き保存"""

    print("   📝 記事作成画面を開きます...")
    page.goto("https://note.com/notes/new", wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    # タイトル入力
    print("   📌 タイトルを入力...")
    title_selectors = [
        '.note-editor__title-input',
        '[placeholder*="タイトル"]',
        '[placeholder*="記事タイトル"]',
        'textarea[class*="title"]',
        'div[class*="title"][contenteditable]',
    ]

    title_el = None
    for sel in title_selectors:
        el = page.query_selector(sel)
        if el and el.is_visible():
            title_el = el
            print(f"   📌 タイトル欄を発見: {sel}")
            break

    if not title_el:
        # デバッグ情報
        page.screenshot(path="/tmp/note_editor_debug.png")
        print("   📸 デバッグスクショ: /tmp/note_editor_debug.png")
        raise Exception("タイトル入力欄が見つかりません")

    _paste_text(page, title_el, title)
    time.sleep(1)

    # タイトル確認ループ
    for attempt in range(3):
        try:
            current = page.evaluate("el => el.textContent || el.value || ''", title_el).strip()
            if current and len(current) > 3:
                print(f"   ✅ タイトル確認: 「{current[:30]}...」")
                break
        except Exception:
            pass
        print(f"   ⚠️ タイトル未入力（リトライ {attempt+1}/3）")
        _paste_text(page, title_el, title)
        time.sleep(1)

    # 本文入力
    print("   📄 本文を入力...")
    body_selectors = [
        '.note-editable',
        '[contenteditable="true"]',
        '.ProseMirror',
        '[class*="editor"][contenteditable]',
        '[role="textbox"]',
    ]

    body_el = None
    for sel in body_selectors:
        el = page.query_selector(sel)
        if el and el.is_visible():
            body_el = el
            print(f"   📄 本文欄を発見: {sel}")
            break

    if not body_el:
        raise Exception("本文入力欄が見つかりません")

    _paste_text(page, body_el, body)
    time.sleep(2)

    # 本文確認ループ
    for attempt in range(3):
        try:
            body_text = page.evaluate("el => el.textContent || el.innerText || ''", body_el).strip()
            if body_text and len(body_text) > 10:
                print(f"   ✅ 本文確認: {len(body_text)} 文字")
                break
        except Exception:
            pass
        print(f"   ⚠️ 本文未入力（リトライ {attempt+1}/3）")
        _paste_text(page, body_el, body)
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

    save_selectors = [
        'button:has-text("下書き保存")',
        'button:has-text("保存")',
        '[data-test="save-draft"]',
        '.p-postEditor__action button',
        'button[class*="draft"]',
        'button[class*="save"]',
    ]

    for sel in save_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(3)
                print("   ✅ 下書き保存完了")
                current_url = page.url
                print(f"   🔗 URL: {current_url}")
                return current_url
        except Exception:
            continue

    print("   ⚠️ 下書き保存ボタンが見つかりませんでした")
    # デバッグ用スクリーンショット
    page.screenshot(path="/tmp/note_save_debug.png")
    return None


# ── エントリーポイント ──────────────────────────────────
def post_draft_to_note(markdown: str, headless: bool = False, skip_ogp: bool = False) -> dict:
    """
    noteに下書きを投稿するメイン関数。
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
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
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
            # デバッグ用スクリーンショット
            try:
                page.screenshot(path="/tmp/note_error_debug.png")
                print("   📸 エラー時スクショ: /tmp/note_error_debug.png")
            except Exception:
                pass
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
