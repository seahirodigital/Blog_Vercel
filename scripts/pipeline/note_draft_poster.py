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

# ── OGP展開設定 ────────────────────────────────────────
EDITOR_CONTENT_SELECTOR  = ".ProseMirror p, .ProseMirror h2, .ProseMirror h3"
EDITOR_LOAD_TIMEOUT_SEC  = 60
OGP_TARGET_DOMAINS       = ["amzn.to", "amazon.co.jp", "apple.com", "youtube.com"]

# OGP展開用JS関数群 (note_ogp_opener.py から移植)
JS_FUNCTIONS = r"""
window.noteFormatter = {
    getTitleInput: () => document.querySelector('.note-editor__title-input'),
    getEditor: () => document.querySelector('.note-editable, [contenteditable="true"]') || document.querySelector('.ProseMirror'),

    processTitle: function() {
        const titleInput = this.getTitleInput();
        const editor = this.getEditor();
        if (!titleInput || !editor) return;
        if (titleInput.textContent.trim().length > 10) return;
        const firstP = editor.querySelector('p');
        if (firstP) {
            let text = firstP.textContent.trim().replace(/^#+\s*/, '');
            titleInput.textContent = text;
            titleInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
    },

    convertMarkdownToHtml: function() {
        const editor = this.getEditor();
        if(!editor) return;
        const paragraphs = Array.from(editor.querySelectorAll('p'));
        paragraphs.forEach(p => {
            let text = p.textContent.trim();
            let newEl = null;
            if (text.startsWith('### ')) {
                newEl = document.createElement('h3');
                newEl.textContent = text.replace('### ', '');
            } else if (text.startsWith('## ') || text.startsWith('# ')) {
                newEl = document.createElement('h2');
                newEl.textContent = text.replace(/#+\s*/, '');
            }
            if (newEl) p.parentNode.replaceChild(newEl, p);
        });

        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
        const nodesToFix = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.textContent.includes('**')) nodesToFix.push(node);
        }
        nodesToFix.forEach(textNode => {
            const parent = textNode.parentNode;
            if (!parent) return;
            const parts = textNode.textContent.split(/(\*\*.*?\*\*)/g);
            const fragment = document.createDocumentFragment();
            parts.forEach(part => {
                if (part.startsWith('**') && part.endsWith('**')) {
                    const strong = document.createElement('strong');
                    strong.textContent = part.slice(2, -2);
                    fragment.appendChild(strong);
                } else {
                    fragment.appendChild(document.createTextNode(part));
                }
            });
            parent.replaceChild(fragment, textNode);
        });
    },

    extractUrls: function() {
        const editor = this.getEditor();
        if(!editor) return [];
        const urls = [];
        const regex = /(https?:\/\/[^\s\n\r<>"]+)/g;
        let match;
        while ((match = regex.exec(editor.innerText)) !== null) {
            urls.push(match[1]);
        }
        return urls;
    },

    setCaretAtUrlEnd: function(url, occurrence) {
        const editor = this.getEditor();
        if(!editor) return false;
        const selection = window.getSelection();
        const range = document.createRange();
        const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
        let node, count = 0;
        while ((node = walker.nextNode())) {
            let startIdx = 0, idx;
            while ((idx = node.textContent.indexOf(url, startIdx)) !== -1) {
                count++;
                if (count === occurrence) {
                    range.setStart(node, idx + url.length);
                    range.setEnd(node, idx + url.length);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    editor.focus();
                    return true;
                }
                startIdx = idx + 1;
            }
        }
        return false;
    },

    normalizeLineBreaks: function() {
        const editor = this.getEditor();
        if(!editor) return 0;
        let removed = 0;

        const embeds = editor.querySelectorAll(
            'div[class*="embed"], div[class*="ogp"], div[class*="Embed"], ' +
            'div[class*="card"], figure, div[data-type]'
        );
        embeds.forEach(embed => {
            let prev = embed.previousElementSibling;
            while (prev && prev.tagName === 'P' && prev.textContent.trim() === '') {
                const toRemove = prev;
                prev = prev.previousElementSibling;
                toRemove.remove();
                removed++;
            }
            let next = embed.nextElementSibling;
            while (next && next.tagName === 'P' && next.textContent.trim() === '') {
                const toRemove = next;
                next = next.nextElementSibling;
                toRemove.remove();
                removed++;
            }
        });

        const allP = Array.from(editor.querySelectorAll('p'));
        let prevWasEmpty = false;
        for (const p of allP) {
            const isEmpty = p.textContent.trim() === '' && p.children.length === 0;
            if (isEmpty) {
                if (prevWasEmpty) {
                    p.remove();
                    removed++;
                } else {
                    prevWasEmpty = true;
                }
            } else {
                prevWasEmpty = false;
            }
        }

        return removed;
    }
};
"""


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


# ── OGP展開関数群 ─────────────────────────────────────
def _cookies_to_playwright(cookies: dict) -> list:
    """Cookie辞書 → Playwright の add_cookies() 形式リストに変換"""
    return [
        {"name": name, "value": value, "domain": ".note.com", "path": "/"}
        for name, value in cookies.items()
    ]


def _wait_for_editor_content(page, timeout_sec: int = EDITOR_LOAD_TIMEOUT_SEC) -> bool:
    """ProseMirrorエディタのコンテンツ（p/h2/h3）が出現するまでポーリング待機"""
    print(f"   ⏳ エディタコンテンツのロード待機（最大{timeout_sec}秒）...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            count = page.locator(EDITOR_CONTENT_SELECTOR).count()
            if count > 0:
                text = page.locator(EDITOR_CONTENT_SELECTOR).first.text_content()
                if text and text.strip():
                    elapsed = timeout_sec - (deadline - time.time())
                    print(f"   ✅ エディタコンテンツ検出: {count}要素（{elapsed:.1f}秒後）")
                    return True
        except Exception as e:
            print(f"   ⚠️ 待機中エラー: {e}")
        time.sleep(1)
    print(f"   ❌ タイムアウト: {timeout_sec}秒待ってもエディタコンテンツが現れませんでした")
    return False


def process_ogp_urls(page) -> int:
    """OGPカード展開 + 不要改行削除をまとめて実行する。処理URL数を返す。"""
    print("\n   [Python] OGP展開ループを開始...")
    page.evaluate(JS_FUNCTIONS)
    page.evaluate("window.noteFormatter.processTitle()")
    page.evaluate("window.noteFormatter.convertMarkdownToHtml()")

    total_processed = 0
    MAX_SWEEPS = 3

    for sweep in range(MAX_SWEEPS):
        print(f"\n   [Python] 🔄 {sweep + 1}回目のスイープ...")
        all_urls = page.evaluate("window.noteFormatter.extractUrls()")
        target_urls = [u for u in set(all_urls) if any(d in u for d in OGP_TARGET_DOMAINS)]

        if not target_urls:
            print("   [Python] 展開漏れのURLはありません。スイープ終了。")
            break

        print(f"   [Python] 残存対象URL: {len(target_urls)}種 / 計{len(all_urls)}箇所")
        processed_this_loop = 0
        target_counts = {u: 0 for u in target_urls}

        for url in target_urls:
            occurrences = all_urls.count(url)
            while target_counts[url] < occurrences:
                target_counts[url] += 1
                found = page.evaluate(
                    "(args) => window.noteFormatter.setCaretAtUrlEnd(args.url, args.occ)",
                    {"url": url, "occ": target_counts[url]},
                )
                if found:
                    page.keyboard.press("Enter")
                    processed_this_loop += 1
                    page.wait_for_timeout(300)

        total_processed += processed_this_loop
        print("   [Python] カード展開の非同期反映を待機 (3秒)...")
        page.wait_for_timeout(3000)

    print("\n   [Python] 🧹 不要な空行を最終一括削除...")
    page.evaluate("window.noteFormatter.normalizeLineBreaks()")
    return total_processed


def _run_ogp_expansion_on_draft(editor_url: str, cookies_dict: dict, headless: bool = True) -> bool:
    """
    下書き作成後のエディタURLへPlaywrightでアクセスし、OGP展開を実行する。
    noteの自動保存に委ねるため、8秒待機して終了。
    """
    from playwright.sync_api import sync_playwright

    print(f"\n── Phase 4: OGP展開（Playwright） ──")
    print(f"   対象URL: {editor_url}")

    playwright_cookies = _cookies_to_playwright(cookies_dict)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
            locale="ja-JP",
        )
        context.add_cookies(playwright_cookies)

        page = context.new_page()

        try:
            page.goto(editor_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"   ⚠️ ページロードエラー（続行）: {e}")

        content_loaded = _wait_for_editor_content(page, timeout_sec=EDITOR_LOAD_TIMEOUT_SEC)
        if not content_loaded:
            print("   ❌ エディタコンテンツが表示されませんでした。OGP展開をスキップします。")
            browser.close()
            return False

        try:
            processed_count = process_ogp_urls(page)
            print(f"   ✅ OGP展開処理完了: {processed_count}件")
        except Exception as e:
            print(f"   ⚠️ OGP展開エラー: {e}")
            browser.close()
            return False

        print("   ⏳ noteの自動保存完了を待機（8秒）...")
        page.wait_for_timeout(8000)
        browser.close()

    print("   ✅ OGP展開 + 自動保存が完了しました。")
    return True


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
def post_draft_to_note(markdown: str, run_ogp: bool = True) -> dict:
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

    # Phase 4: OGP展開（Playwright）
    if run_ogp and result["url"]:
        # セッション更新後の最新Cookieを取得
        latest_cookies = _load_cookies()
        _run_ogp_expansion_on_draft(result["url"], latest_cookies, headless=True)

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
    parser.add_argument("--no-ogp", action="store_true",
                        help="OGP展開をスキップして下書き保存のみ実行")
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

    result = post_draft_to_note(md, run_ogp=not args.no_ogp)
    if result["success"]:
        print(f"\n🎉 下書き投稿成功！\n   タイトル: {result['title']}\n   URL: {result['url']}")
        file_id = os.getenv("FILE_ID", "")
        if file_id:
            _save_draft_url_to_github_var(file_id, result["url"])
    else:
        print("\n❌ 下書き投稿失敗")
        sys.exit(1)
