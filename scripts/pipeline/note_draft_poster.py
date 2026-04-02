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
def _parse_article_data(result: dict) -> dict:
    """noteのAPIレスポンスからarticleデータを抽出"""
    article_data = result.get("data", result)
    if isinstance(article_data, dict) and "note" in article_data:
        article_data = article_data["note"]
    return article_data


def _create_draft_api(session: http_requests.Session, title: str, body_html: str) -> dict:
    """
    2ステップで下書き作成:
    1. POST /api/v1/text_notes でタイトルのみ作成 → ID取得
    2. PUT /api/v1/text_notes/{id} で本文を保存
    """
    # ── Step 1: 記事作成（タイトル＋本文） ──
    print("   📝 Step1: 記事作成...")
    res = session.post(
        f"{NOTE_API_BASE}/v1/text_notes",
        json={"name": title, "body": body_html, "template_key": None},
        timeout=30,
    )

    print(f"   🔍 POST ステータス: {res.status_code}")
    print(f"   🔍 POST レスポンス: {res.text[:600]}")
    try:
        result = res.json()
    except Exception:
        print(f"   ❌ レスポンスパース失敗")
        return {}

    if "error" in result:
        print(f"   ❌ POST APIエラー: {json.dumps(result['error'], ensure_ascii=False)[:300]}")
        return {}
    if not res.ok:
        print(f"   ❌ 記事作成失敗 ({res.status_code}): {res.text[:300]}")
        return {}

    article_data = _parse_article_data(result)
    article_id = article_data.get("id")
    article_key = article_data.get("key")
    if not article_id:
        print(f"   ❌ IDが取得できません: {json.dumps(result, ensure_ascii=False)[:300]}")
        return {}
    print(f"   ✅ 記事作成成功: ID={article_id}, key={article_key}")

    # ── Step 2: PUTで本文を保存 ──
    # まず最小テスト → フル本文 → プレーンテキスト の順で試す
    put_url = f"{NOTE_API_BASE}/v1/text_notes/{article_id}"
    time.sleep(1)

    put_attempts = [
        ("HTML本文",        {"name": title, "body": body_html, "status": "draft"}),
        ("HTML本文(status無し)", {"name": title, "body": body_html}),
        ("プレーンテキスト", {"name": title, "body": body_html.replace('<p>', '').replace('</p>', '\n').replace('<h2>', '\n').replace('</h2>', '\n').replace('<h3>', '\n').replace('</h3>', '\n').replace('<ul>', '').replace('</ul>', '').replace('<li>', '- ').replace('</li>', '\n').replace('<strong>', '').replace('</strong>', '').replace('<em>', '').replace('</em>', '').replace('<a href="', '').replace('">', ' ').replace('</a>', '').replace('<code>', '').replace('</code>', ''), "status": "draft"}),
        ("最小テスト",      {"name": title, "body": "<p>テスト本文</p>", "status": "draft"}),
    ]

    put_success = False
    for label, data in put_attempts:
        print(f"   📄 PUT試行: {label}...")
        res2 = session.put(put_url, json=data, timeout=30)
        print(f"   🔍 PUT[{label}] ステータス: {res2.status_code} → {res2.text[:300]}")
        try:
            result2 = res2.json()
            if "error" not in result2 and res2.ok:
                print(f"   ✅ PUT成功: {label}")
                put_success = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not put_success:
        print(f"   ❌ 全てのPUT試行が失敗")

    editor_url = f"https://editor.note.com/notes/{article_key}/edit/"
    print(f"   ✅ 下書き作成成功: ID={article_id}, key={article_key}")
    return {"id": article_id, "key": article_key, "url": editor_url}


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
    else:
        print("\n❌ 下書き投稿失敗")
        sys.exit(1)
