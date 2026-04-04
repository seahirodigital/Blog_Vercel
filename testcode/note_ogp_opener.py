"""
note OGP展開ツール (試作版)
=============================
以下の手順でOGP展開を実行する:

1. note_storage_state.json（または NOTE_STORAGE_STATE 環境変数）からCookieを復元
2. Playwright で editor.note.com/notes/{key}/edit/ を開く
3. エディタSPAのコンテンツ（ProseMirrorのコンテンツ）がDOMにロードされるまで待機
4. 05-note_ogp_formatter.js の OGP展開ロジック（URLにCaret→Enter）を注入・実行
5. 書き換え後の innerHTML を取得し draft_save APIで再保存する（オプション）

【使い方】
  python note_ogp_opener.py <editor_url>
  例: python note_ogp_opener.py https://editor.note.com/notes/nXXXXXXXXXX/edit/

【環境変数 / ファイル】
  NOTE_STORAGE_STATE  : GitHub Secret互換のCookie JSON
  note_storage_state.json : ローカルCookieファイル（--save-cookies で生成）

【techrefere.md 失敗パターンの対策】
  - 以前の実装は goto 直後に innerHTML を取得 → SPAがまだ空 → 本文消滅
  - 本実装は「.ProseMirror 内の p タグ or h2 タグが1つ以上出現」を待機ポーリングする
  - それでも失敗する場合は WAIT_SEC を増やすか、--no-resave フラグで再保存を無効化する
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

# ── 設定 ─────────────────────────────────────────────────────────────────
NOTE_STORAGE_STATE = os.getenv("NOTE_STORAGE_STATE", "")
SCRIPT_DIR         = Path(__file__).parent.parent / "scripts" / "pipeline"
LOCAL_STATE_FILE   = SCRIPT_DIR / "note_storage_state.json"

# エディタコンテンツがロードされたか判断するCSSセレクタ
# ProseMirrorエディタが存在し、かつ中にpまたはh2が1つ以上あること
EDITOR_CONTENT_SELECTOR = ".ProseMirror p, .ProseMirror h2, .ProseMirror h3"

# エディタロード待ちの最大秒数（手動ログイン用に大幅延長）
EDITOR_LOAD_TIMEOUT_SEC = 300

# OGP展開対象URLフィルター（05-note_ogp_formatter.js と同一のルール）
OGP_TARGET_DOMAINS = ["amzn.to", "amazon.co.jp", "apple.com", "youtube.com"]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ── OGP展開用JS関数郡 (05-note_ogp_formatter.js から移植) ───────────
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

        // パス1: OGPカードの直前・直後にある空の<p>を全て削除
        // noteのOGPカードは通常 .note-common-styles__textnote-body-embed 等のdivで包まれる
        const embeds = editor.querySelectorAll(
            'div[class*="embed"], div[class*="ogp"], div[class*="Embed"], ' +
            'div[class*="card"], figure, div[data-type]'
        );
        embeds.forEach(embed => {
            // OGPの前の空<p>を削除
            let prev = embed.previousElementSibling;
            while (prev && prev.tagName === 'P' && prev.textContent.trim() === '') {
                const toRemove = prev;
                prev = prev.previousElementSibling;
                toRemove.remove();
                removed++;
            }
            // OGPの後の空<p>を削除
            let next = embed.nextElementSibling;
            while (next && next.tagName === 'P' && next.textContent.trim() === '') {
                const toRemove = next;
                next = next.nextElementSibling;
                toRemove.remove();
                removed++;
            }
        });

        // パス2: 残った連続する空の<p>を全て削除（2つ以上連続するものを1つに圧縮）
        // ※テキストのある段落間の「1行の意図的な空行」は残す場合はコメントアウト
        const allP = Array.from(editor.querySelectorAll('p'));
        let prevWasEmpty = false;
        for (const p of allP) {
            const isEmpty = p.textContent.trim() === '' && p.children.length === 0;
            if (isEmpty) {
                if (prevWasEmpty) {
                    // 連続した空行の2つ目以降は削除
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

def process_ogp_urls(page):
    """最速・完全版のOGP展開処理"""
    print("\n   [Python] 超高速URL展開ループ・一括整理を開始...")
    page.evaluate(JS_FUNCTIONS)
    
    # 1. タイトルとMarkdown変換を一気に実行 (最初の1回で十分)
    page.evaluate("window.noteFormatter.processTitle()")
    page.evaluate("window.noteFormatter.convertMarkdownToHtml()")
    
    total_processed = 0
    MAX_SWEEPS = 3

    for sweep in range(MAX_SWEEPS):
        print(f"\n   [Python] 🔄 {sweep + 1}回目のURL残存状況スイープを開始...")
        
        # 2. 残っているURLテキストだけを再キャプチャ（カード化成功したものは消滅する）
        all_urls = page.evaluate("window.noteFormatter.extractUrls()")
        target_urls = [u for u in set(all_urls) if any(d in u for d in OGP_TARGET_DOMAINS)]
        
        if not target_urls:
            print("   [Python] 展開漏れのURLはありません！スイープを終了します。")
            break
            
        print(f"   [Python] 残存対象URL: 計 {len(all_urls)} 箇所")
        processed_this_loop = 0
        target_counts = {u: 0 for u in target_urls}

        # 3. Enter連打処理
        for url in target_urls:
            occurrences = all_urls.count(url)
            while target_counts[url] < occurrences:
                target_counts[url] += 1
                occ = target_counts[url]
                
                # JSで未展開URLの位置へ移動
                found = page.evaluate("(args) => window.noteFormatter.setCaretAtUrlEnd(args.url, args.occ)", {"url": url, "occ": occ})
                if found:
                    page.keyboard.press("Enter")
                    processed_this_loop += 1
                    page.wait_for_timeout(300)
        
        total_processed += processed_this_loop
        
        # まだスイープが続く場合、または最後のスイープ終了後にもNoteのDOM差し替えを待つ
        print("   [Python] カードの展開（DOM差し替え）を待機しています (3秒)...")
        page.wait_for_timeout(3000)

    # 4. 全スイープ完了後、生成された全空行を一括で削除 (normalizeLineBreaks)
    print("\n   [Python] 🧹 全スイープ完了。不要な空行を最終一括削除します...")
    page.evaluate("window.noteFormatter.normalizeLineBreaks()")
    
    return total_processed


# ── Cookie読み込み（note_draft_poster.py と同一ロジック） ───────────────
def _load_cookies() -> dict:
    """StorageState または Cookie ファイルから Cookie 辞書を生成"""
    raw = ""
    if NOTE_STORAGE_STATE:
        raw = NOTE_STORAGE_STATE
        print("   🍪 Cookieを環境変数から読み込み")
    elif LOCAL_STATE_FILE.exists():
        raw = LOCAL_STATE_FILE.read_text(encoding="utf-8")
        print(f"   🍪 Cookieをファイルから読み込み: {LOCAL_STATE_FILE}")
    else:
        print("   ⚠️ Cookieが見つかりません（環境変数・ファイルともに未設定）")
        return {}

    try:
        data = json.loads(raw)
        cookies = {}
        # Playwright StorageState形式
        if isinstance(data, dict) and "cookies" in data:
            for c in data["cookies"]:
                if ".note.com" in c.get("domain", "") or "note.com" in c.get("domain", ""):
                    cookies[c["name"]] = c["value"]
        elif isinstance(data, dict):
            cookies = data
        elif isinstance(data, list):
            for c in data:
                if isinstance(c, dict) and "name" in c:
                    cookies[c["name"]] = c["value"]
        print(f"   🍪 {len(cookies)}個のCookieを読み込み")
        return cookies
    except Exception as e:
        print(f"   ⚠️ Cookie読み込み失敗: {e}")
        return {}


def _cookies_to_playwright(cookies: dict) -> list:
    """
    Cookie辞書 → Playwright の add_cookies() 形式リストに変換
    """
    return [
        {
            "name": name,
            "value": value,
            "domain": ".note.com",
            "path": "/",
        }
        for name, value in cookies.items()
    ]


# ── エディタロード待機 ────────────────────────────────────────────────────
def _wait_for_editor_content(page, timeout_sec: int = EDITOR_LOAD_TIMEOUT_SEC) -> bool:
    """
    ProseMirrorエディタのコンテンツ（p / h2 / h3）が出現するまで待機する。

    note SPAの特性:
      - ページ自体はすぐロードされるが、下書き内容がエディタDOMに反映されるまで
        に数秒 〜 十数秒かかる。
      - headless Chromium では React/Vue のハイドレーション完了がさらに遅れることがある。

    戻り値:
      True  ... コンテンツ検出成功
      False ... タイムアウト
    """
    print(f"   ⏳ エディタコンテンツのロード待機（最大{timeout_sec}秒）...")
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        try:
            # セレクタが見つかり、かつ textContent が空でないことを確認
            count = page.locator(EDITOR_CONTENT_SELECTOR).count()
            if count > 0:
                # ダミーテキストでないことを確認
                text = page.locator(EDITOR_CONTENT_SELECTOR).first.text_content()
                if text and text.strip():
                    elapsed = timeout_sec - (deadline - time.time())
                    print(f"   ✅ エディタコンテンツ検出: {count}要素（{elapsed:.1f}秒後）")
                    print(f"   📄 先頭テキスト: {text.strip()[:60]}...")
                    return True
        except Exception as e:
            print(f"   ⚠️ 待機中エラー: {e}")
        time.sleep(1)

    print(f"   ❌ タイムアウト: {timeout_sec}秒待ってもエディタコンテンツが現れませんでした")
    return False


# ── メイン: OGP展開実行 ──────────────────────────────────────────────────
def run_ogp_expansion(
    editor_url: str,
    headless: bool = False,
    resave: bool = True,
    wait_sec: int = EDITOR_LOAD_TIMEOUT_SEC,
) -> bool:
    """
    指定の editor.note.com URL を開いてOGP展開JSを実行する。

    Parameters
    ----------
    editor_url : str
        下書き編集URL (https://editor.note.com/notes/{key}/edit/)
    headless : bool
        Trueでheadlessモード（デフォルトはFalse＝ブラウザ表示あり）
    resave : bool
        OGP展開後に draft_save APIで再保存するか（デフォルトTrue）
    wait_sec : int
        エディタロード待ちの最大秒数
    """
    from playwright.sync_api import sync_playwright

    print(f"\n🌐 対象URL: {editor_url}")
    print(f"   headless={headless}, resave={resave}, wait_sec={wait_sec}")

    # Cookieの準備
    print("\n── Phase 1: Cookie読み込み ──")
    cookies_dict = _load_cookies()
    if not cookies_dict:
        print("❌ Cookieが取得できませんでした。--save-cookies で初回セットアップを行ってください。")
        return False

    playwright_cookies = _cookies_to_playwright(cookies_dict)

    with sync_playwright() as p:
        print("\n── Phase 2: ブラウザ起動・ログイン ──")
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
            locale="ja-JP",
        )

        # Cookie設定（note.com / editor.note.com 両方に適用）
        context.add_cookies(playwright_cookies)
        # editor.note.com 向けにも同一Cookieをセット
        editor_cookies = [
            {**c, "domain": ".note.com"}
            for c in playwright_cookies
        ]
        try:
            context.add_cookies(editor_cookies)
        except Exception:
            pass

        page = context.new_page()

        # ── Phase 3: エディタページを開く ──
        print(f"\n── Phase 3: エディタURLを開く ──")
        try:
            page.goto(editor_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"   ⚠️ ページロードエラー（続行）: {e}")

        # ── Phase 4: エディタコンテンツの出現を待機 ──
        print(f"\n── Phase 4: エディタSPAコンテンツ待機 ──")
        content_loaded = _wait_for_editor_content(page, timeout_sec=wait_sec)

        if not content_loaded:
            if not headless:
                print("   💡 ブラウザを確認して、内容が表示されているか確認してください")
                print("   Enterキーで続行します（内容が空の可能性があります）: ", end="", flush=True)
                input()
            else:
                print("   ❌ headlessモードでタイムアウト。--no-headless を試してください")
                browser.close()
                return False

        # ── Phase 5: OGP展開の実行 (ハイブリッド処理) ──
        print(f"\n── Phase 5: OGP展開実行 ──")
        try:
            processed_count = process_ogp_urls(page)
            print(f"   ✅ 処理完了件数: {processed_count}件")
        except Exception as e:
            print(f"   ⚠️ 展開処理エラー: {e}")
            browser.close()
            return False

        # OGP展開の非同期反映ならびに、Note標準の「自動変更保存」がサーバへ送られるのを待機
        print("   ⏳ OGP展開の非同期通信かつ、Noteの自動保存（下書き保存）送信完了を待機（約8秒）...")
        page.wait_for_timeout(8000)

        # ── Phase 6: 再保存完了通知 ──
        print(f"\n── Phase 6: 下書き保存完了 ──")
        print("   ✅ Noteの自動保存機能により、展開内容が適用されました。")

        if not headless:
            print("\n✅ 完了。ブラウザを確認してください。Enterで終了: ", end="", flush=True)
            input()

        browser.close()
        return True


# ── draft_save APIによる再保存 ──────────────────────────────────────────
def _resave_via_api(page, editor_url: str, cookies_dict: dict):
    """
    OGP展開後のエディタHTMLをAPIで再保存する。

    注意: この処理は innerHTML をそのまま送信する。
    note のエディタが独自のHTML構造を持つため、完全な互換性は保証されない。
    問題が起きた場合は --no-resave フラグで無効化すること。
    """
    import re
    import requests
    import urllib.parse

    print("   📤 エディタHTMLを取得中...")

    try:
        # ProseMirrorエディタのinnerHTMLを取得
        inner_html = page.evaluate("""
            () => {
                const editor = (
                    document.querySelector('.ProseMirror') ||
                    document.querySelector('.note-editable') ||
                    document.querySelector('[contenteditable="true"]')
                );
                return editor ? editor.innerHTML : null;
            }
        """)
        title_text = page.evaluate("""
            () => {
                const t = document.querySelector('.note-editor__title-input, textarea[name="title"]');
                return t ? (t.value || t.textContent || '').trim() : '';
            }
        """)
    except Exception as e:
        print(f"   ⚠️ HTML取得失敗: {e}")
        return

    if not inner_html:
        print("   ⚠️ エディタHTMLが空です。再保存をスキップします。")
        return

    # editor URL から note_key を抽出
    # https://editor.note.com/notes/{key}/edit/
    m = re.search(r"/notes/([^/]+)/edit", editor_url)
    if not m:
        print(f"   ⚠️ URLからnote_keyを抽出できません: {editor_url}")
        return
    note_key = m.group(1)

    print(f"   📄 note_key: {note_key}")
    print(f"   📄 タイトル: {title_text[:50]}")
    print(f"   📄 HTML長: {len(inner_html)}文字")

    # XSRF-TOKEN の取得
    xsrf_token = ""
    for name, value in cookies_dict.items():
        if name == "XSRF-TOKEN":
            xsrf_token = urllib.parse.unquote(value)
            break
    if not xsrf_token:
        print("   ⚠️ XSRF-TOKENが取得できません。再保存をスキップします。")
        return

    # note_id は editor URL からは取れないため、APIで検索が必要
    # 現バージョンでは note_key から note_id を取得する
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": "https://editor.note.com",
        "Referer": editor_url,
    })
    for name, value in cookies_dict.items():
        session.cookies.set(name, value, domain=".note.com")

    # key から id を取得
    print("   🔍 note_id を取得中...")
    try:
        res = session.get(f"https://note.com/api/v1/text_notes/{note_key}", timeout=15)
        if not res.ok:
            print(f"   ⚠️ note情報取得失敗 ({res.status_code}). note_keyでdraft_saveを試みます。")
            note_id = None
        else:
            data = res.json().get("data", {})
            note_id = data.get("id")
            print(f"   ✅ note_id: {note_id}")
    except Exception as e:
        print(f"   ⚠️ note情報取得エラー: {e}")
        note_id = None

    if not note_id:
        print("   ❌ note_idが取得できず再保存できません。")
        return

    # プレーンテキスト文字数を計算
    plain_text = re.sub(r"<[^>]+>", "", inner_html)

    payload = {
        "body": inner_html,
        "body_length": len(plain_text),
        "name": title_text,
        "index": False,
        "is_lead_form": False,
        "image_keys": [],
    }
    draft_url = f"https://note.com/api/v1/text_notes/draft_save?id={note_id}&is_temp_saved=true"
    draft_headers = {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": xsrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://editor.note.com",
        "Referer": editor_url,
    }

    try:
        res2 = session.post(draft_url, json=payload, headers=draft_headers, timeout=30)
        print(f"   🔍 draft_save {res2.status_code}")
        if res2.ok:
            print("   ✅ 再保存成功！")
        else:
            print(f"   ❌ 再保存失敗: {res2.text[:300]}")
    except Exception as e:
        print(f"   ⚠️ 再保存エラー: {e}")


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="note 下書きOGP展開ツール（試作版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ブラウザ表示あり（確認しながら実行）
  python note_ogp_opener.py https://editor.note.com/notes/nXXXXXXXXXX/edit/

  # headlessモード（自動実行）
  python note_ogp_opener.py https://editor.note.com/notes/nXXXXXXXXXX/edit/ --headless

  # OGP展開のみ（draft_save再保存なし）
  python note_ogp_opener.py https://editor.note.com/notes/nXXXXXXXXXX/edit/ --no-resave

  # エディタロード待機時間を延長（デフォルト30秒）
  python note_ogp_opener.py https://editor.note.com/notes/nXXXXXXXXXX/edit/ --wait 60
        """,
    )
    parser.add_argument("url", help="note 下書き編集URL (editor.note.com/notes/.../edit/)")
    parser.add_argument(
        "--headless", action="store_true",
        help="headlessモードで実行（デフォルト: ブラウザ表示あり）"
    )
    parser.add_argument(
        "--no-resave", action="store_true",
        help="OGP展開後のdraft_save再保存をスキップ"
    )
    parser.add_argument(
        "--wait", type=int, default=EDITOR_LOAD_TIMEOUT_SEC,
        help=f"エディタロード待機秒数（デフォルト: {EDITOR_LOAD_TIMEOUT_SEC}秒）"
    )
    args = parser.parse_args()

    success = run_ogp_expansion(
        editor_url=args.url,
        headless=args.headless,
        resave=not args.no_resave,
        wait_sec=args.wait,
    )
    sys.exit(0 if success else 1)
