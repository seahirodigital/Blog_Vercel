"""
note下書きポスター v4.0 — API直接投稿版（Playwright不要）
noteの内部APIにHTTPリクエストで直接下書き保存する。

【完全自動化の仕組み】
1. NOTE_STORAGE_STATE (GitHub Secret) からCookieを復元
2. Cookie無効時 → APIログインで自動再認証（ブラウザ不要）
3. POST /api/v1/text_notes で下書き作成
4. 操作後、最新CookieをGitHub Secretに自動上書き
5. 定期cron（note-keepalive.yml）でセッションを延命

【初回セットアップのみ手動】
  python note_draft_poster.py --save-cookies
  → 出力されたJSONをGitHub Secret「NOTE_STORAGE_STATE」に登録

【通常実行（GitHub Actions）】
  python note_draft_poster.py <file.md>
"""

import os
import sys
import json
import time
import re
import base64
import argparse
from pathlib import Path

import requests as http_requests

# ── 設定 ──────────────────────────────────────────────
NOTE_API_BASE       = "https://note.com/api"
NOTE_EMAIL          = os.getenv("NOTE_EMAIL", "")
NOTE_PASSWORD       = os.getenv("NOTE_PASSWORD", "")
NOTE_STORAGE_STATE  = os.getenv("NOTE_STORAGE_STATE", "")   # JSON (GitHub Secret)
GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN", "")          # PAT (secrets:write)
GITHUB_REPO_OWNER   = "seahirodigital"
GITHUB_REPO_NAME    = "Blog_Vercel"
SECRET_NAME         = "NOTE_STORAGE_STATE"

SCRIPT_DIR        = Path(__file__).parent
LOCAL_STATE_FILE  = SCRIPT_DIR / "note_storage_state.json"   # ローカル保存先

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


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


# ── Markdown → noteエディタHTML変換 ───────────────────
def _inline_format(text: str) -> str:
    """インライン要素の変換（太字、リンク、コード）"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def markdown_to_note_html(md: str) -> str:
    """MarkdownをnoteのエディタHTML形式に変換"""
    html_parts = []
    lines = md.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 空行 → スキップ（<br>は422エラーの原因になるため除外）
        if not stripped:
            i += 1
            continue

        # ### → h3
        if stripped.startswith('### '):
            text = _inline_format(stripped[4:].strip())
            html_parts.append(f'<h3>{text}</h3>')
            i += 1
            continue

        # ## → h2
        if stripped.startswith('## '):
            text = _inline_format(stripped[3:].strip())
            html_parts.append(f'<h2>{text}</h2>')
            i += 1
            continue

        # リスト項目（- または *）
        if stripped.startswith('- ') or stripped.startswith('* '):
            items = []
            while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                item_text = lines[i].strip()[2:].strip()
                items.append(f'<li>{_inline_format(item_text)}</li>')
                i += 1
            html_parts.append(f'<ul>{"".join(items)}</ul>')
            continue

        # URL単独行 → そのまま段落（noteが自動OGP展開）
        if re.match(r'^https?://\S+$', stripped):
            html_parts.append(f'<p>{stripped}</p>')
            i += 1
            continue

        # 通常段落
        text = _inline_format(stripped)
        html_parts.append(f'<p>{text}</p>')
        i += 1

    return '\n'.join(html_parts)


# ── Cookie管理 ────────────────────────────────────────
def _load_cookies() -> dict:
    """StorageStateまたはCookieファイルからCookie辞書を生成"""
    raw = ""
    if NOTE_STORAGE_STATE:
        raw = NOTE_STORAGE_STATE
        print("   🍪 Cookieを環境変数から読み込み")
    elif LOCAL_STATE_FILE.exists():
        raw = LOCAL_STATE_FILE.read_text(encoding="utf-8")
        print("   🍪 Cookieをローカルファイルから読み込み")

    if not raw:
        return {}

    try:
        data = json.loads(raw)
        cookies = {}
        # Playwright StorageState形式 {"cookies": [...]}
        if isinstance(data, dict) and "cookies" in data:
            for c in data["cookies"]:
                if ".note.com" in c.get("domain", "") or "note.com" in c.get("domain", ""):
                    cookies[c["name"]] = c["value"]
        # シンプルなCookie辞書形式 {"name": "value", ...}
        elif isinstance(data, dict):
            cookies = data
        # Cookie配列形式 [{"name": ..., "value": ...}, ...]
        elif isinstance(data, list):
            for c in data:
                if isinstance(c, dict) and "name" in c:
                    cookies[c["name"]] = c["value"]
        if cookies:
            print(f"   🍪 {len(cookies)}個のCookieを読み込み")
        return cookies
    except Exception as e:
        print(f"   ⚠️ Cookie読み込み失敗: {e}")
        return {}


def _save_cookies_state(session: http_requests.Session):
    """セッションのCookieをStorageState互換形式で保存・GitHub Secret更新"""
    # 同名Cookieが複数ドメインに存在する場合があるため、iter_cookies()で安全に取得
    cookie_list = []
    seen = set()
    for cookie in session.cookies:
        key = (cookie.name, cookie.domain)
        if key in seen:
            continue
        seen.add(key)
        cookie_list.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain or ".note.com",
            "path": cookie.path or "/",
            "httpOnly": cookie.has_nonstandard_attr("HttpOnly") or cookie.name.startswith("_"),
            "secure": cookie.secure,
            "sameSite": "Lax",
        })

    if not cookie_list:
        print("   ℹ️ 保存すべきCookieがありません")
        return

    state = {"cookies": cookie_list, "origins": []}
    state_json = json.dumps(state, ensure_ascii=False)

    # ローカル保存
    LOCAL_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"   💾 ローカル保存: {LOCAL_STATE_FILE}")

    # GitHub Secret自動更新
    _auto_refresh_github_secret(state_json)


# ── GitHub Variable保存（下書きURL記録用） ────────────
def _save_draft_url_to_github_var(file_id: str, url: str):
    """下書き保存したURLをGitHub Repository Variableに記録（フロントエンドから参照可能）"""
    if not GITHUB_TOKEN or not file_id or not url:
        return
    import hashlib
    key_hash = hashlib.md5(file_id.encode()).hexdigest()[:8].upper()
    var_name = f"NOTE_DRAFT_URL_{key_hash}"
    api_base = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # 存在確認してPATCH or POST
    check = http_requests.get(f"{api_base}/actions/variables/{var_name}", headers=headers)
    if check.status_code == 200:
        res = http_requests.patch(
            f"{api_base}/actions/variables/{var_name}",
            headers=headers,
            json={"name": var_name, "value": url},
        )
    else:
        res = http_requests.post(
            f"{api_base}/actions/variables",
            headers=headers,
            json={"name": var_name, "value": url},
        )
    if res.status_code in (200, 201, 204):
        print(f"   ✅ GitHub Variable {var_name} を保存しました")
    else:
        print(f"   ⚠️ Variable保存失敗 ({res.status_code}): {res.text[:150]}")


# ── GitHub Secret自動更新 ─────────────────────────────
def _auto_refresh_github_secret(new_state_json: str):
    """GitHub APIを使ってNOTE_STORAGE_STATEシークレットを自動更新"""
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
        print("   ✅ NOTE_STORAGE_STATE を自動更新しました")
    else:
        print(f"   ⚠️ Secret更新失敗 ({res.status_code}): {res.text[:200]}")


# ── セッション作成・検証・ログイン ────────────────────
def _create_session(cookies: dict) -> http_requests.Session:
    """認証済みHTTPセッションを作成"""
    session = http_requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://note.com/",
        "Origin": "https://note.com",
        "X-Requested-With": "XMLHttpRequest",
    })
    if cookies:
        session.cookies.update(cookies)
    return session


def _verify_session(session: http_requests.Session) -> bool:
    """セッションが有効か確認（ユーザー情報取得を試行）"""
    try:
        res = session.get(f"{NOTE_API_BASE}/v1/stats/pv", timeout=15)
        if res.ok:
            print("   ✅ セッション有効（API認証成功）")
            return True
        # 別のエンドポイントでもう一度試す
        res = session.get("https://note.com/api/v1/note_sessions/me", timeout=15)
        if res.ok:
            print("   ✅ セッション有効（セッション確認成功）")
            return True
    except Exception as e:
        print(f"   ⚠️ セッション検証エラー: {e}")
    return False


def _fetch_csrf_token(session: http_requests.Session) -> str | None:
    """note.comのHTMLからCSRFトークンを取得"""
    import re as _re
    try:
        res = session.get("https://note.com/", timeout=15)
        # <meta name="csrf-token" content="...">
        m = _re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', res.text)
        if m:
            token = m.group(1)
            print(f"   🔐 CSRFトークン取得成功")
            return token
        # <meta content="..." name="csrf-token"> （順序が逆の場合）
        m = _re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']', res.text)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"   ⚠️ CSRFトークン取得失敗: {e}")
    return None


def _api_login(session: http_requests.Session) -> bool:
    """noteのAPIで直接ログインしてCookieとCSRFトークンを取得"""
    if not NOTE_EMAIL or not NOTE_PASSWORD:
        print("   ⚠️ NOTE_EMAIL/NOTE_PASSWORD未設定のためAPIログイン不可")
        return False

    print("   🔑 APIログインを試みます...")

    # 古いセッションCookieを削除（重複防止）
    remove_names = {"_note_session_v5", "_note_session"}
    cookies_to_keep = [c for c in session.cookies if c.name not in remove_names]
    session.cookies.clear()
    for c in cookies_to_keep:
        session.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
    print(f"   🧹 古いセッションCookieをクリア")

    # note.comにアクセスしてベースCookieとCSRFトークンを取得
    csrf_token = _fetch_csrf_token(session)
    if csrf_token:
        session.headers.update({"X-CSRF-Token": csrf_token})
    time.sleep(1)

    # ログインAPI候補（noteのバージョンにより異なる可能性）
    login_attempts = [
        {
            "url": "https://note.com/api/v3/sessions/sign_in",
            "payload": {"login": NOTE_EMAIL, "password": NOTE_PASSWORD},
        },
        {
            "url": "https://note.com/api/v2/sessions/sign_in",
            "payload": {"login": NOTE_EMAIL, "password": NOTE_PASSWORD},
        },
        {
            "url": "https://note.com/api/v1/sessions/sign_in",
            "payload": {"login": NOTE_EMAIL, "password": NOTE_PASSWORD},
        },
        {
            "url": "https://note.com/api/v1/sessions",
            "payload": {"login": NOTE_EMAIL, "password": NOTE_PASSWORD},
        },
    ]

    for attempt in login_attempts:
        try:
            res = session.post(
                attempt["url"],
                json=attempt["payload"],
                timeout=15,
            )
            if res.ok:
                # レスポンスbodyにerrorが含まれていないか確認
                try:
                    body = res.json()
                    if "error" in body:
                        print(f"   ❌ ログインエラー: {body['error']}")
                        break  # 認証情報が無効なので他を試しても無駄
                    # レスポンスにトークンが含まれる場合はCookieにセット
                    token = (body.get("data", {}) or {}).get("token") or body.get("token")
                    if token:
                        print(f"   🔑 レスポンストークン検出 → Cookieにセット")
                        session.cookies.set("_note_session_v5", token, domain=".note.com")
                except Exception:
                    pass
                # ログイン後のCookie状況をデバッグ出力
                note_cookies = [c.name for c in session.cookies if "note.com" in (c.domain or "")]
                print(f"   🍪 ログイン後Cookie数: {len(list(session.cookies))} 個（note.com: {note_cookies}）")
                print(f"   ✅ APIログイン成功: {attempt['url']}")
                return True
            elif res.status_code == 401:
                print(f"   ❌ 認証拒否: {attempt['url']} (401) → {res.text[:150]}")
                break  # 認証情報が無効なので他を試しても無駄
            elif res.status_code == 404:
                continue  # エンドポイント不在 → 次を試す
            else:
                print(f"   ⚠️ {attempt['url']} → {res.status_code}: {res.text[:150]}")
        except Exception as e:
            print(f"   ⚠️ {attempt['url']} → エラー: {e}")
        time.sleep(1)

    return False


# ── 記事作成API ───────────────────────────────────────
import urllib.parse as _urlparse


def _xsrf_token(session: http_requests.Session) -> str:
    """Cookie から XSRF-TOKEN を取得（URLデコード済み）"""
    for cookie in session.cookies:
        if cookie.name == "XSRF-TOKEN":
            return _urlparse.unquote(cookie.value)
    return ""


def _create_draft_api(session: http_requests.Session, title: str, body_html: str) -> dict:
    """
    2ステップで下書き作成:
    1. POST /api/v1/text_notes でスケルトン作成 → ID取得
    2. POST /api/v1/text_notes/draft_save?id={id}&is_temp_saved=true で本文を保存
    ※ PUT は公開用。下書き保存には draft_save エンドポイントを使う（NoteClient2準拠）
    """
    import re as _re

    # ── Step 1: 記事スケルトン作成 ──
    print("   📝 Step1: 記事スケルトン作成...")
    res = session.post(
        f"{NOTE_API_BASE}/v1/text_notes",
        json={"template_key": None},
        timeout=30,
    )
    print(f"   🔍 POST {res.status_code}")
    if not res.ok:
        print(f"   ❌ 記事作成失敗 ({res.status_code}): {res.text[:300]}")
        return {}

    try:
        result = res.json()
    except Exception:
        print(f"   ❌ レスポンスパース失敗: {res.text[:200]}")
        return {}

    note_data = result.get("data") or {}
    article_id = note_data.get("id")
    article_key = note_data.get("key")
    if not article_id:
        print(f"   ❌ IDが取得できません: {json.dumps(result, ensure_ascii=False)[:300]}")
        return {}
    print(f"   ✅ スケルトン作成成功: ID={article_id}, key={article_key}")

    # ── Step 2: draft_save で本文保存 ──
    print("   📝 Step2: 本文を draft_save で保存...")
    xsrf = _xsrf_token(session)
    if not xsrf:
        # XSRF-TOKEN がない場合はnote.comにアクセスして取得
        print("   🔐 XSRF-TOKEN未取得 → note.comにアクセスして取得...")
        session.get("https://note.com/", timeout=15)
        xsrf = _xsrf_token(session)

    plain_text = _re.sub(r"<[^>]+>", "", body_html)
    payload = {
        "body": body_html,
        "body_length": len(plain_text),
        "name": title,
        "index": False,
        "is_lead_form": False,
        "image_keys": [],
    }
    draft_headers = {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": xsrf,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://editor.note.com",
        "Referer": "https://editor.note.com/",
    }
    draft_url = f"{NOTE_API_BASE}/v1/text_notes/draft_save?id={article_id}&is_temp_saved=true"
    res2 = session.post(draft_url, json=payload, headers=draft_headers, timeout=30)
    print(f"   🔍 draft_save {res2.status_code}")
    if not res2.ok:
        print(f"   ❌ 本文保存失敗 ({res2.status_code}): {res2.text[:300]}")
        # タイトルなしでも下書き自体は作成済みなので editor URL は返す
    else:
        print(f"   ✅ 本文保存成功")

    editor_url = f"https://editor.note.com/notes/{article_key}/edit/"

    # ── Step 3: OGP展開JS実行 → 再保存 ──
    _run_ogp_formatter(session, article_key, article_id, title)

    return {"id": article_id, "key": article_key, "url": editor_url}


def _run_ogp_formatter(session: http_requests.Session, article_key: str, article_id: int, title: str) -> bool:
    """
    Playwrightでnoteエディタを開き、OGP展開JSを3回実行して再保存する。
    Amazon等のアフィリエイトリンクをカードレイアウトで表示した状態で保存。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   ⏭️ Playwright未インストール → OGPステップスキップ")
        return False

    js_file = SCRIPT_DIR / "prompts" / "05-note_ogp_formatter.js"
    if not js_file.exists():
        print(f"   ⏭️ OGP Formatter JS未検出 ({js_file}) → スキップ")
        return False

    js_code = js_file.read_text(encoding="utf-8")
    editor_url = f"https://editor.note.com/notes/{article_key}/edit/"

    # リクエストセッションのCookieをPlaywright用に変換
    pw_cookies = []
    seen = set()
    for cookie in session.cookies:
        key = (cookie.name, cookie.domain)
        if key in seen:
            continue
        seen.add(key)
        domain = cookie.domain or ".note.com"
        # Playwrightはdomain先頭の "." をそのまま受け付ける
        pw_cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
            "httpOnly": cookie.name.startswith("_"),
            "sameSite": "Lax",
        })

    print(f"   🌐 Playwrightでエディタを開きます: {editor_url}")

    import re as _re

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 900},
            )
            context.add_cookies(pw_cookies)
            page = context.new_page()

            page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # エディタ要素を確認
            try:
                page.wait_for_selector('.note-editable, [contenteditable="true"]', timeout=15000)
                print("   ✅ エディタ読み込み完了")
            except Exception:
                print("   ❌ エディタが見つかりません → OGPスキップ")
                browser.close()
                return False

            # JS 3回実行（1回目: 7秒待機、2回目: 5秒待機、3回目: 3秒待機）
            for i, wait_ms in enumerate([(1, 7000), (2, 5000), (3, 3000)], 0):
                idx, ms = wait_ms
                print(f"   🔧 OGP Formatter JS実行 ({idx}/3)...")
                page.evaluate(js_code)
                page.wait_for_timeout(ms)

            # 展開後のエディタHTMLを取得
            updated_html = page.evaluate("""
                () => {
                    const ed = document.querySelector('.note-editable, [contenteditable="true"]');
                    return ed ? ed.innerHTML : null;
                }
            """)
            browser.close()

        if not updated_html:
            print("   ⚠️ エディタHTML取得失敗 → 再保存スキップ")
            return False

        # draft_save で OGP展開済み本文を再保存
        plain_text = _re.sub(r"<[^>]+>", "", updated_html)
        xsrf = _xsrf_token(session)
        payload = {
            "body": updated_html,
            "body_length": len(plain_text),
            "name": title,
            "index": False,
            "is_lead_form": False,
            "image_keys": [],
        }
        draft_headers = {
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://editor.note.com",
            "Referer": "https://editor.note.com/",
        }
        draft_url = f"{NOTE_API_BASE}/v1/text_notes/draft_save?id={article_id}&is_temp_saved=true"
        res2 = session.post(draft_url, json=payload, headers=draft_headers, timeout=30)
        print(f"   🔍 OGP後のdraft_save: {res2.status_code}")
        if res2.ok:
            print("   ✅ OGP展開済み本文を再保存しました")
            return True
        else:
            print(f"   ⚠️ OGP後の再保存失敗 ({res2.status_code}): {res2.text[:200]}")
            return False

    except Exception as e:
        print(f"   ⚠️ OGPフォーマッターでエラー: {e}")
        return False


# ── save-cookies（初回のみ） ──────────────────────────
def save_storage_state_locally():
    """
    ブラウザを開いて手動ログイン → Cookieを保存。
    初回のみ実行。以降はAPIログイン + keepaliveで自動維持。
    """
    from playwright.sync_api import sync_playwright

    print("🔑 ブラウザでnote.comにログインしてください...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
        )
        page = context.new_page()
        page.goto("https://note.com/login", wait_until="domcontentloaded")

        print("\nブラウザでnote.comへのログインを完了してください。")
        print("ログイン後、Enterを押してください: ", end="", flush=True)
        input()

        state = context.storage_state()
        state_json = json.dumps(state, ensure_ascii=False, indent=2)
        LOCAL_STATE_FILE.write_text(state_json, encoding="utf-8")
        browser.close()

    print(f"\n✅ StorageState保存完了: {LOCAL_STATE_FILE}")

    # GITHUB_TOKENがあれば即自動登録
    if GITHUB_TOKEN:
        print("\n🔄 GITHUB_TOKEN検出 → GitHub Secretを自動更新します...")
        _auto_refresh_github_secret(json.dumps(state, ensure_ascii=False))
    else:
        print("\n📋 以下をGitHub Secret「NOTE_STORAGE_STATE」に登録してください:")
        print(state_json)


# ── keepaliveモード ───────────────────────────────────
def keepalive():
    """
    セッション維持用: Cookieでnoteにアクセスし、有効なら更新して保存。
    無効ならAPIログインで再取得。
    """
    print("🔄 セッション維持チェック...")
    cookies = _load_cookies()
    session = _create_session(cookies)

    if _verify_session(session):
        print("   セッション有効 → Cookie更新して保存")
    else:
        print("   セッション切れ → APIログインで再取得")
        if not _api_login(session):
            print("❌ セッション復旧失敗")
            sys.exit(1)

    _save_cookies_state(session)
    print("✅ セッション維持完了")


# ── メイン処理 ────────────────────────────────────────
def post_draft_to_note(markdown: str) -> dict:
    title, body = extract_title_and_body(markdown)
    if not title or not body:
        print("❌ タイトルまたは本文が空です")
        return {"success": False, "url": "", "title": title}

    body_html = markdown_to_note_html(body)
    print(f"📋 タイトル: 「{title}」")
    print(f"📋 本文: {len(body)} 文字 → HTML {len(body_html)} 文字")
    result = {"success": False, "url": "", "title": title}

    # Phase 1: 認証
    print("\n── Phase 1: 認証 ──")
    cookies = _load_cookies()
    session = _create_session(cookies)

    if not _verify_session(session):
        print("   ⚠️ Cookie無効 → APIログインにフォールバック")
        if not _api_login(session):
            print("❌ 全ての認証手段が失敗しました")
            return result

    # Phase 2: 下書き作成
    print("\n── Phase 2: 下書き作成（API） ──")
    draft = _create_draft_api(session, title, body_html)
    if not draft:
        return result

    result["success"] = True
    result["url"] = draft.get("url", "")

    # Phase 3: セッション更新
    print("\n── Phase 3: セッション更新 ──")
    _save_cookies_state(session)

    return result


# ── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="note.com 下書きポスター v4.0（API直接投稿版）")
    parser.add_argument("file", nargs="?", help="Markdownファイルパス")
    parser.add_argument("--content", help="Markdown文字列を直接指定")
    parser.add_argument("--save-cookies", action="store_true",
                        help="初回セットアップ: ブラウザで手動ログインしてCookieを保存")
    parser.add_argument("--keepalive", action="store_true",
                        help="セッション維持モード: Cookieの有効性確認・更新")
    args = parser.parse_args()

    if args.save_cookies:
        save_storage_state_locally()
        sys.exit(0)

    if args.keepalive:
        keepalive()
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

    result = post_draft_to_note(md)
    if result["success"]:
        print(f"\n🎉 下書き投稿成功！\n   タイトル: {result['title']}\n   URL: {result['url']}")
        file_id = os.getenv("FILE_ID", "")
        if file_id:
            _save_draft_url_to_github_var(file_id, result["url"])
    else:
        print("\n❌ 下書き投稿失敗")
        sys.exit(1)
