"""
note下書きポスター v2.0
Playwright でnote.comに下書き記事を作成する。

【reCAPTCHA回避策】
GitHub ActionsのヘッドレスブラウザはreCAPTCHAで弾かれるため、
ローカルで手動ログインしてクッキーを保存→GitHub Secretに登録する方式を採用。

【使い方】
  # Step 1: ローカルでクッキーを取得（初回・期限切れ時）
  python note_draft_poster.py --save-cookies

  # Step 2: 出力されたJSONをGitHub Secret「NOTE_COOKIES」に登録

  # Step 3: 記事を投稿
  python note_draft_poster.py <markdown_file.md>
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
NOTE_COOKIES   = os.getenv("NOTE_COOKIES", "")  # JSON形式（GitHub Secret）

SCRIPT_DIR   = Path(__file__).parent
OGP_JS_PATH  = SCRIPT_DIR / "prompts" / "05-note_ogp_formatter.js"
COOKIES_FILE = SCRIPT_DIR / "note_cookies.json"  # ローカル保存先


# ── Markdown前処理 ─────────────────────────────────────
def extract_title_and_body(markdown: str) -> tuple:
    """H1をタイトル、それ以降を本文として分離。不要セクションを除外。"""
    lines = markdown.replace('\r\n', '\n').split('\n')
    title = ""
    body_start = 0

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

    return title, '\n'.join(body_lines).strip()


# ── クッキー管理 ───────────────────────────────────────
def _load_cookies(context) -> bool:
    """
    クッキーを復元する。優先順:
    1. NOTE_COOKIES 環境変数（GitHub Secret）
    2. ローカルの note_cookies.json
    """
    if NOTE_COOKIES:
        try:
            cookies = json.loads(NOTE_COOKIES)
            context.add_cookies(cookies)
            print("   🍪 クッキーを環境変数（NOTE_COOKIES）から復元")
            return True
        except Exception as e:
            print(f"   ⚠️ NOTE_COOKIESのパース失敗: {e}")

    if COOKIES_FILE.exists():
        try:
            cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            context.add_cookies(cookies)
            print(f"   🍪 クッキーをローカルファイルから復元: {COOKIES_FILE}")
            return True
        except Exception as e:
            print(f"   ⚠️ ローカルクッキーの読み込み失敗: {e}")

    return False


def save_cookies_locally():
    """
    ローカルで手動ログインしてクッキーを保存するヘルパー。
    実行後、note_cookies.json の内容をGitHub Secret「NOTE_COOKIES」に登録すること。
    """
    from playwright.sync_api import sync_playwright

    print("\n🔑 ブラウザでnote.comにログインしてください...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()
        page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded")

        print("\nブラウザでnote.comへのログインを完了してください。")
        print("ログイン後、このターミナルでEnterを押してください: ", end="")
        input()

        cookies = context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()

    print(f"\n✅ クッキー保存完了: {COOKIES_FILE}")
    print(f"\n📋 以下をGitHub Secret「NOTE_COOKIES」に登録してください:")
    print(COOKIES_FILE.read_text(encoding="utf-8"))


# ── Phase 1: ログイン ─────────────────────────────────
def _ensure_login(page, context):
    """クッキー復元またはフォールバックログインでセッションを確立する"""

    # クッキーを復元してからnote.comへアクセス
    cookies_loaded = _load_cookies(context)
    page.goto(NOTE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # ログイン確認: /loginへのリダイレクトがなければOK
    if "login" not in page.url:
        print(f"   ✅ セッション有効 (URL: {page.url})")
        return

    if cookies_loaded:
        print("   ⚠️ クッキーが期限切れです")
        print("   ↳ ローカルで: python note_draft_poster.py --save-cookies を実行してください")

    # フォールバック: パスワードログイン（reCAPTCHAがない場合のみ成功）
    print("   🔑 パスワードログインを試みます...")
    page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    email_input = None
    for sel in ['input[placeholder*="note ID"]', 'input[type="email"]', 'input[name="login"]']:
        el = page.query_selector(sel)
        if el and el.is_visible():
            email_input = el
            print(f"   📧 メール欄: {sel}")
            break

    if not email_input:
        info = page.evaluate("() => Array.from(document.querySelectorAll('input')).map(e=>({type:e.type,ph:e.placeholder,v:e.offsetParent!==null}))")
        print(f"   🔍 input一覧: {json.dumps(info, ensure_ascii=False)}")
        raise Exception("メール入力欄が見つかりません。先に --save-cookies を実行してください。")

    email_input.click()
    email_input.fill(NOTE_EMAIL)
    time.sleep(0.5)

    pw = page.query_selector('input[type="password"]')
    if not pw:
        raise Exception("パスワード入力欄が見つかりません")
    pw.fill(NOTE_PASSWORD)
    time.sleep(0.5)

    btn = page.query_selector('button[type="submit"]') or page.query_selector('button:has-text("ログイン")')
    if btn:
        btn.click()
    else:
        pw.press("Enter")

    page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(4)

    if "login" in page.url:
        raise Exception(
            "ログイン失敗（reCAPTCHAで拒否）。\n"
            "ローカルで実行: python note_draft_poster.py --save-cookies\n"
            "出力されたJSONをGitHub Secret「NOTE_COOKIES」に登録してください。"
        )

    print("   ✅ ログイン完了")


# ── 本文ペースト ─────────────────────────────────────
def _paste_text(page, element, text: str):
    """テキストを安全にペースト（3段階フォールバック）"""
    element.click()
    time.sleep(0.3)

    # 方法1: evaluate で直接セット
    try:
        page.evaluate("""
            ([el, text]) => {
                el.focus();
                if (el.contentEditable === 'true') {
                    el.textContent = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    const s = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    )?.set;
                    if (s) s.call(el, text); else el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        """, [element, text])
        time.sleep(0.5)
        return
    except Exception as e:
        print(f"   ⚠️ 直接セット失敗 → クリップボード方式: {e}")

    # 方法2: クリップボード
    try:
        page.evaluate("text => navigator.clipboard.writeText(text)", text)
        time.sleep(0.3)
        element.click()
        page.keyboard.press("Control+a")
        time.sleep(0.1)
        page.keyboard.press("Control+v")
        time.sleep(1)
        return
    except Exception as e:
        print(f"   ⚠️ クリップボード失敗 → fill方式: {e}")

    # 方法3: fill/type
    try:
        element.click()
        element.press("Control+a")
        element.type(text, delay=5)
    except Exception as e:
        print(f"   ⚠️ fill方式も失敗: {e}")


# ── Phase 1: エディタ操作 ─────────────────────────────
def _create_draft(page, title: str, body: str):
    """記事作成画面でタイトル・本文を入力して下書き保存"""

    print("   📝 記事作成画面を開きます...")
    # note.com/notes/new → editor.note.com にリダイレクトされる
    page.goto("https://note.com/notes/new", wait_until="networkidle", timeout=45000)
    time.sleep(5)
    print(f"   🔗 現在のURL: {page.url}")

    # ログインページに戻された場合
    if "login" in page.url:
        raise Exception("ノートエディタに遷移できません（セッション無効）。--save-cookiesを再実行してください。")

    # ── タイトル入力（textarea が実態） ──
    print("   📌 タイトルを入力...")
    title_el = None
    for sel in [
        'textarea[placeholder="記事タイトル"]',
        'textarea[placeholder*="タイトル"]',
        'textarea[class*="title"]',
        'textarea[class*="Title"]',
    ]:
        try:
            el = page.wait_for_selector(sel, timeout=10000, state="visible")
            if el:
                title_el = el
                print(f"   📌 タイトル欄: {sel}")
                break
        except Exception:
            continue

    if not title_el:
        elems = page.evaluate("""
            () => Array.from(document.querySelectorAll('textarea,[contenteditable]')).map(e=>({
                tag: e.tagName, ph: e.placeholder||'', cls: e.className.slice(0,60), v: e.offsetParent!==null
            }))
        """)
        print(f"   🔍 textarea/contenteditable: {json.dumps(elems, ensure_ascii=False)}")
        page.screenshot(path="/tmp/note_editor_debug.png")
        raise Exception("タイトル入力欄が見つかりません")

    # textarea は fill で確実に入力
    title_el.click()
    time.sleep(0.3)
    title_el.fill(title)
    time.sleep(0.5)

    # 確認ループ
    for attempt in range(3):
        val = page.evaluate("el => el.value || ''", title_el).strip()
        if val and len(val) > 3:
            print(f"   ✅ タイトル確認: 「{val[:40]}」")
            break
        print(f"   ⚠️ タイトル未入力（リトライ {attempt+1}/3）")
        title_el.click()
        title_el.fill(title)
        time.sleep(1)

    # ── 本文入力（ProseMirror エディタ） ──
    print("   📄 本文を入力...")
    body_el = None
    for sel in [
        'div.ProseMirror',
        '.ProseMirror',
        'div[class*="ProseMirror"]',
        '[role="textbox"]',
        '.note-editable',
        '[contenteditable="true"]',
    ]:
        try:
            el = page.wait_for_selector(sel, timeout=8000, state="visible")
            if el:
                body_el = el
                print(f"   📄 本文欄: {sel}")
                break
        except Exception:
            continue

    if not body_el:
        raise Exception("本文入力欄が見つかりません")

    _paste_text(page, body_el, body)
    time.sleep(2)

    for attempt in range(3):
        txt = page.evaluate("el => el.textContent || el.innerText || ''", body_el).strip()
        if txt and len(txt) > 10:
            print(f"   ✅ 本文確認: {len(txt)} 文字")
            break
        print(f"   ⚠️ 本文未入力（リトライ {attempt+1}/3）")
        _paste_text(page, body_el, body)
        time.sleep(2)

    return True


# ── Phase 2: OGP展開JS ────────────────────────────────
def _run_ogp_formatter(page):
    """OGP Formatter JSを3回実行"""
    if not OGP_JS_PATH.exists():
        print(f"   ⚠️ OGP Formatter JS未検出: {OGP_JS_PATH}")
        return

    js_code = OGP_JS_PATH.read_text(encoding="utf-8")
    print("   🔧 OGP Formatter JS 実行開始...")

    for run_num, wait_sec in [(1, 7), (2, 5), (3, 0)]:
        print(f"   ▶️  {run_num}回目...")
        try:
            page.evaluate(js_code)
        except Exception as e:
            print(f"   ⚠️ JS実行エラー（続行）: {e}")
        if wait_sec > 0:
            print(f"   ⏳ {wait_sec}秒待機...")
            time.sleep(wait_sec)

    print("   ✅ OGP Formatter 完了")


# ── 下書き保存 ────────────────────────────────────────
def _save_draft(page):
    """下書き保存ボタンをクリック"""
    print("   💾 下書き保存中...")

    for sel in [
        'button:has-text("下書き保存")',
        'button:has-text("保存")',
        '[data-test="save-draft"]',
        'button[class*="draft"]',
        'button[class*="save"]',
        '.p-postEditor__action button',
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(3)
                url = page.url
                print(f"   ✅ 下書き保存完了: {url}")
                return url
        except Exception:
            continue

    page.screenshot(path="/tmp/note_save_debug.png")
    print("   ⚠️ 下書き保存ボタンが見つかりませんでした")
    return None


# ── エントリーポイント ────────────────────────────────
def post_draft_to_note(markdown: str, headless: bool = True, skip_ogp: bool = False) -> dict:
    """noteに下書きを投稿するメイン関数"""
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
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()

        try:
            print("\n── Phase 1: ログイン＆下書き作成 ──")
            _ensure_login(page, context)
            _create_draft(page, title, body)

            if not skip_ogp:
                print("\n── Phase 2: OGP展開 ──")
                _run_ogp_formatter(page)

            url = _save_draft(page)
            if url:
                result["success"] = True
                result["url"] = url

        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path="/tmp/note_error_debug.png")
                print("   📸 エラー時スクショ: /tmp/note_error_debug.png")
            except Exception:
                pass
        finally:
            time.sleep(2)
            browser.close()

    return result


# ── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="note.com 下書きポスター v2.0")
    parser.add_argument("file", nargs="?", help="Markdownファイルパス")
    parser.add_argument("--content", help="Markdown文字列を直接指定")
    parser.add_argument("--headless", action="store_true", default=True, help="ヘッドレスモード（デフォルト: True）")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="ブラウザを表示して実行")
    parser.add_argument("--skip-ogp", action="store_true", help="OGP展開をスキップ")
    parser.add_argument("--save-cookies", action="store_true", help="ローカルでログインしてクッキーを保存")
    args = parser.parse_args()

    # クッキー保存モード
    if args.save_cookies:
        save_cookies_locally()
        sys.exit(0)

    if args.content:
        md = args.content
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            md = f.read()
    else:
        print("❌ Markdownファイルパスまたは --content を指定してください")
        print("   クッキー保存: python note_draft_poster.py --save-cookies")
        sys.exit(1)

    result = post_draft_to_note(md, headless=args.headless, skip_ogp=args.skip_ogp)

    if result["success"]:
        print(f"\n🎉 下書き投稿成功！")
        print(f"   タイトル: {result['title']}")
        print(f"   URL: {result['url']}")
    else:
        print(f"\n❌ 下書き投稿失敗")
        sys.exit(1)
