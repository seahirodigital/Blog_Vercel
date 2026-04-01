"""
note下書きポスター v3.0 — 完全自動化版
Playwright でnote.comに下書き記事を作成する。

【完全自動化の仕組み】
1. NOTE_STORAGE_STATE (GitHub Secret) からPlaywrightのStorageState(クッキー等)を復元
2. 操作完了後、最新のStorageStateをGitHub APIでSecretに自動上書き
3. 次回実行時は自動更新されたSecretを使用 → 手動操作ゼロ

【初回セットアップのみ手動】
  python note_draft_poster.py --save-cookies
  → 出力されたJSONをGitHub Secret「NOTE_STORAGE_STATE」に登録

【通常実行（GitHub Actions）】
  python note_draft_poster.py <file.md> --headless
"""

import os
import sys
import json
import time
import base64
import argparse
import tempfile
from pathlib import Path

import requests as http_requests

# ── 設定 ──────────────────────────────────────────────
NOTE_URL            = "https://note.com/"
NOTE_LOGIN_URL      = "https://note.com/login"
NOTE_EMAIL          = os.getenv("NOTE_EMAIL", "seahiro@gmail.com")
NOTE_PASSWORD       = os.getenv("NOTE_PASSWORD", "appleblog0227")
NOTE_STORAGE_STATE  = os.getenv("NOTE_STORAGE_STATE", "")   # JSON (GitHub Secret)
GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN", "")          # PAT (secrets:write)
GITHUB_REPO_OWNER   = "seahirodigital"
GITHUB_REPO_NAME    = "Blog_Vercel"
SECRET_NAME         = "NOTE_STORAGE_STATE"

SCRIPT_DIR        = Path(__file__).parent
OGP_JS_PATH       = SCRIPT_DIR / "prompts" / "05-note_ogp_formatter.js"
LOCAL_STATE_FILE  = SCRIPT_DIR / "note_storage_state.json"   # ローカル保存先


# ── Markdown前処理 ─────────────────────────────────────
def extract_title_and_body(markdown: str) -> tuple:
    """H1をタイトル、それ以降を本文として分離"""
    lines = markdown.replace('\r\n', '\n').split('\n')
    title, body_start = "", 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('# ') and not s.startswith('## '):
            title, body_start = s.lstrip('# ').strip(), i + 1
            break
    if not title:
        for i, line in enumerate(lines):
            if line.strip():
                title, body_start = line.strip().lstrip('# ').strip(), i + 1
                break
    body_lines, skip = [], False
    for line in lines[body_start:]:
        s = line.strip()
        if s.startswith('## 🎬') or s.startswith('## Captions'):
            skip = True; continue
        if skip and s.startswith('## '): skip = False
        if not skip: body_lines.append(line)
    return title, '\n'.join(body_lines).strip()


# ── StorageState 管理 ──────────────────────────────────
def _load_state_to_file() -> str | None:
    """
    StorageStateをtempファイルに書き出しパスを返す。
    優先: 環境変数 NOTE_STORAGE_STATE → ローカルファイル
    """
    raw = ""
    if NOTE_STORAGE_STATE:
        raw = NOTE_STORAGE_STATE
        print("   🍪 StorageStateを環境変数から読み込み")
    elif LOCAL_STATE_FILE.exists():
        raw = LOCAL_STATE_FILE.read_text(encoding="utf-8")
        print(f"   🍪 StorageStateをローカルファイルから読み込み: {LOCAL_STATE_FILE}")

    if not raw:
        return None

    try:
        json.loads(raw)  # 構文チェック
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        tmp.write(raw)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"   ⚠️ StorageStateのパース失敗: {e}")
        return None


def _auto_refresh_github_secret(new_state_json: str):
    """
    GitHub APIを使ってNOTE_STORAGE_STATEシークレットを自動更新する。
    GITHUB_TOKEN (PAT with secrets:write) が必要。
    """
    if not GITHUB_TOKEN:
        print("   ℹ️ GITHUB_TOKEN未設定のためSecretの自動更新をスキップ")
        return
    try:
        import nacl.encoding
        import nacl.public
    except ImportError:
        print("   ⚠️ pynacl未インストール。pip install pynacl でインストールしてください。")
        return

    api_base = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # リポジトリの公開鍵を取得
    res = http_requests.get(f"{api_base}/actions/secrets/public-key", headers=headers)
    if not res.ok:
        print(f"   ⚠️ GitHub公開鍵取得失敗 ({res.status_code}): {res.text[:200]}")
        return

    key_data = res.json()
    pub_key = nacl.public.PublicKey(key_data["key"].encode(), nacl.encoding.Base64Encoder)
    sealed = nacl.public.SealedBox(pub_key)
    encrypted = base64.b64encode(sealed.encrypt(new_state_json.encode())).decode()

    # Secretを更新
    res = http_requests.put(
        f"{api_base}/actions/secrets/{SECRET_NAME}",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
    )
    if res.status_code in (201, 204):
        print("   ✅ NOTE_STORAGE_STATE を自動更新しました（次回も手動不要）")
    else:
        print(f"   ⚠️ Secret更新失敗 ({res.status_code}): {res.text[:200]}")


# ── save-cookies モード（初回のみ） ────────────────────
def save_storage_state_locally():
    """
    ブラウザを開いて手動ログイン → StorageStateを保存。
    初回のみ実行。以降は自動更新。
    """
    from playwright.sync_api import sync_playwright

    print("🔑 ブラウザでnote.comにログインしてください...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()
        page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded")

        print("\nブラウザでnote.comへのログインを完了してください。")
        print("ログイン後、Enterを押してください: ", end="", flush=True)
        input()

        state = context.storage_state()
        state_json = json.dumps(state, ensure_ascii=False, indent=2)
        LOCAL_STATE_FILE.write_text(state_json, encoding="utf-8")
        browser.close()

    print(f"\n✅ StorageState保存完了: {LOCAL_STATE_FILE}")
    print("\n📋 以下をGitHub Secret「NOTE_STORAGE_STATE」に登録してください:")
    print(state_json)

    # GITHUB_TOKENがあれば即自動登録
    if GITHUB_TOKEN:
        print("\n🔄 GITHUB_TOKEN検出 → GitHubSecretを自動更新します...")
        _auto_refresh_github_secret(state_json)
    else:
        print("\n⚠️ GITHUB_TOKEN未設定のため手動登録が必要です。")


# ── Phase 1: ログイン確認 ─────────────────────────────
def _ensure_logged_in(page):
    """StorageState復元後のログイン状態を確認する"""
    page.goto(NOTE_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    if "login" not in page.url:
        print(f"   ✅ セッション有効")
        return

    # セッション切れ → フォールバックでパスワードログイン
    print("   ⚠️ セッション無効。パスワードログインを試みます...")
    page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    email_el = None
    for sel in ['input[placeholder*="note ID"]', 'input[type="email"]']:
        el = page.query_selector(sel)
        if el and el.is_visible():
            email_el = el; break

    if not email_el:
        info = page.evaluate("()=>Array.from(document.querySelectorAll('input')).map(e=>({type:e.type,ph:e.placeholder}))")
        print(f"   🔍 inputs: {json.dumps(info, ensure_ascii=False)}")
        raise Exception("ログイン入力欄が見つかりません。NOTE_STORAGE_STATEが無効です。")

    email_el.click(); email_el.fill(NOTE_EMAIL); time.sleep(0.5)
    pw = page.query_selector('input[type="password"]')
    if not pw: raise Exception("パスワード入力欄が見つかりません")
    pw.fill(NOTE_PASSWORD); time.sleep(0.5)

    btn = (page.query_selector('button[type="submit"]') or
           page.query_selector('button:has-text("ログイン")'))
    if btn: btn.click()
    else: pw.press("Enter")
    page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(4)

    if "login" in page.url:
        raise Exception("パスワードログインも失敗しました。NOTE_STORAGE_STATEが古い可能性があります。")
    print("   ✅ ログイン完了")


# ── テキスト入力 ──────────────────────────────────────
def _paste_text(page, element, text: str):
    """3段階フォールバックでテキストをペースト"""
    element.click(); time.sleep(0.3)
    # 1: evaluate直接セット
    try:
        page.evaluate("""([el, text]) => {
            el.focus();
            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                const s = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value')?.set;
                if (s) s.call(el, text); else el.value = text;
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
            } else {
                el.textContent = text;
                el.dispatchEvent(new Event('input',{bubbles:true}));
            }
        }""", [element, text])
        time.sleep(0.5); return
    except Exception as e:
        print(f"   ⚠️ evaluate失敗→clipboard: {e}")
    # 2: クリップボード
    try:
        page.evaluate("t => navigator.clipboard.writeText(t)", text)
        element.click(); page.keyboard.press("Control+a"); time.sleep(0.1)
        page.keyboard.press("Control+v"); time.sleep(1); return
    except Exception as e:
        print(f"   ⚠️ clipboard失敗→fill: {e}")
    # 3: fill
    element.click(); element.press("Control+a"); element.type(text, delay=5)


# ── Phase 1: エディタ操作 ─────────────────────────────
def _create_draft(page, title: str, body: str):
    """記事エディタでタイトル・本文を入力"""
    print("   📝 エディタを開きます...")
    page.goto("https://note.com/notes/new", wait_until="networkidle", timeout=45000)
    time.sleep(5)
    print(f"   🔗 現在URL: {page.url}")

    if "login" in page.url:
        raise Exception("エディタに遷移できません（セッション無効）")

    # タイトル入力（実測: textarea[placeholder="記事タイトル"]）
    print("   📌 タイトルを入力...")
    title_el = None
    for sel in ['textarea[placeholder="記事タイトル"]','textarea[placeholder*="タイトル"]','textarea[class*="title"]']:
        try:
            el = page.wait_for_selector(sel, timeout=10000, state="visible")
            if el: title_el = el; print(f"   📌 タイトル欄: {sel}"); break
        except Exception: continue

    if not title_el:
        elems = page.evaluate("()=>Array.from(document.querySelectorAll('textarea,[contenteditable]')).map(e=>({tag:e.tagName,ph:e.placeholder||'',cls:e.className.slice(0,50),v:e.offsetParent!==null}))")
        print(f"   🔍 編集要素: {json.dumps(elems, ensure_ascii=False)}")
        page.screenshot(path="/tmp/note_editor_debug.png")
        raise Exception("タイトル入力欄が見つかりません")

    title_el.click(); time.sleep(0.3)
    title_el.fill(title); time.sleep(0.5)

    for attempt in range(3):
        val = page.evaluate("el => el.value || ''", title_el).strip()
        if val and len(val) > 3:
            print(f"   ✅ タイトル確認: 「{val[:40]}」"); break
        print(f"   ⚠️ リトライ {attempt+1}/3")
        title_el.click(); title_el.fill(title); time.sleep(1)

    # 本文入力（実測: div.ProseMirror）
    print("   📄 本文を入力...")
    body_el = None
    for sel in ['div.ProseMirror','.ProseMirror','[role="textbox"]','[contenteditable="true"]']:
        try:
            el = page.wait_for_selector(sel, timeout=8000, state="visible")
            if el: body_el = el; print(f"   📄 本文欄: {sel}"); break
        except Exception: continue

    if not body_el:
        raise Exception("本文入力欄が見つかりません")

    _paste_text(page, body_el, body); time.sleep(2)

    for attempt in range(3):
        txt = page.evaluate("el => el.textContent || ''", body_el).strip()
        if txt and len(txt) > 10:
            print(f"   ✅ 本文確認: {len(txt)} 文字"); break
        print(f"   ⚠️ リトライ {attempt+1}/3")
        _paste_text(page, body_el, body); time.sleep(2)

    return True


# ── Phase 2: OGP展開 ──────────────────────────────────
def _run_ogp_formatter(page):
    if not OGP_JS_PATH.exists():
        print(f"   ⚠️ OGP JS未検出: {OGP_JS_PATH}"); return
    js = OGP_JS_PATH.read_text(encoding="utf-8")
    print("   🔧 OGP Formatter実行...")
    for n, wait in [(1,7),(2,5),(3,0)]:
        print(f"   ▶️ {n}回目")
        try: page.evaluate(js)
        except Exception as e: print(f"   ⚠️ JS実行エラー: {e}")
        if wait: print(f"   ⏳ {wait}秒待機..."); time.sleep(wait)
    print("   ✅ OGP完了")


# ── 下書き保存 ─────────────────────────────────────────
def _save_draft(page) -> str | None:
    print("   💾 下書き保存...")
    for sel in ['button:has-text("下書き保存")','button:has-text("保存")','[data-test="save-draft"]']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(); time.sleep(3)
                url = page.url
                print(f"   ✅ 保存完了: {url}")
                return url
        except Exception: continue
    page.screenshot(path="/tmp/note_save_debug.png")
    print("   ⚠️ 保存ボタンが見つかりません")
    return None


# ── エントリーポイント ────────────────────────────────
def post_draft_to_note(markdown: str, headless: bool = True, skip_ogp: bool = False) -> dict:
    from playwright.sync_api import sync_playwright

    title, body = extract_title_and_body(markdown)
    if not title or not body:
        print("❌ タイトルまたは本文が空です")
        return {"success": False, "url": "", "title": title}

    print(f"📋 タイトル: 「{title}」")
    print(f"📋 本文: {len(body)} 文字")
    result = {"success": False, "url": "", "title": title}

    # StorageStateをtempファイルに準備
    state_file = _load_state_to_file()
    if not state_file:
        print("⚠️ NOTE_STORAGE_STATE未設定。--save-cookiesで初期化してください。")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"]
        )
        ctx_kwargs = dict(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            permissions=["clipboard-read","clipboard-write"],
        )
        if state_file:
            ctx_kwargs["storage_state"] = state_file
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            print("\n── Phase 1: ログイン確認 ──")
            _ensure_logged_in(page)
            _create_draft(page, title, body)

            if not skip_ogp:
                print("\n── Phase 2: OGP展開 ──")
                _run_ogp_formatter(page)

            url = _save_draft(page)
            if url:
                result["success"] = True
                result["url"] = url

            # ── 操作後に最新StorageStateを自動更新 ──
            print("\n── StorageState自動更新 ──")
            new_state = context.storage_state()
            new_state_json = json.dumps(new_state, ensure_ascii=False)
            _auto_refresh_github_secret(new_state_json)
            # ローカルにも保存
            LOCAL_STATE_FILE.write_text(
                json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback; traceback.print_exc()
            try: page.screenshot(path="/tmp/note_error_debug.png")
            except Exception: pass
        finally:
            time.sleep(2)
            browser.close()

        # tempファイル削除
        if state_file:
            try: Path(state_file).unlink()
            except Exception: pass

    return result


# ── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="note.com 下書きポスター v3.0")
    parser.add_argument("file", nargs="?", help="Markdownファイルパス")
    parser.add_argument("--content", help="Markdown文字列を直接指定")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--skip-ogp", action="store_true")
    parser.add_argument("--save-cookies", action="store_true", help="初回セットアップ: ブラウザで手動ログインしてStorageStateを保存")
    args = parser.parse_args()

    if args.save_cookies:
        save_storage_state_locally()
        sys.exit(0)

    if args.content:
        md = args.content
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            md = f.read()
    else:
        print("❌ Markdownファイルパスまたは --content を指定してください")
        print("   初回セットアップ: python note_draft_poster.py --save-cookies")
        sys.exit(1)

    result = post_draft_to_note(md, headless=args.headless, skip_ogp=args.skip_ogp)
    if result["success"]:
        print(f"\n🎉 下書き投稿成功！\n   タイトル: {result['title']}\n   URL: {result['url']}")
    else:
        print("\n❌ 下書き投稿失敗")
        sys.exit(1)
