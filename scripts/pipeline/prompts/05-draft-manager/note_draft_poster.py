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
  python prompts/05-draft-manager/note_draft_poster.py --save-cookies
  → 出力されたJSONをGitHub Secret「NOTE_STORAGE_STATE」に登録

【通常実行（GitHub Actions）】
  python prompts/05-draft-manager/note_draft_poster.py <file.md>
"""

import os
import sys
import json
import time
import re
import base64
import argparse
import importlib.util
import tempfile
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

SCRIPT_DIR        = Path(__file__).resolve().parent
LOCAL_STATE_FILE  = SCRIPT_DIR / "note_storage_state.json"   # ローカル保存先
ADOBE_STORAGE_STATE_FILE = SCRIPT_DIR / "adobe_express_storage_state.json"
AMAZON_PROMPTS_DIR = SCRIPT_DIR.parent / "04-affiliate-link-manager"
AMAZON_AFFILIATE_SCRIPT = AMAZON_PROMPTS_DIR / "insert_amazon_affiliate.py"
AMAZON_TOP_IMAGE_SCRIPT = AMAZON_PROMPTS_DIR / "amazon_gazo_get.py"
NOTE_TOP_IMAGE_ARTIFACTS_DIR = SCRIPT_DIR.parent.parent / "debug" / "note_gazo_test" / "artifacts"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ── OGP展開設定 ────────────────────────────────────────
EDITOR_CONTENT_SELECTOR  = ".ProseMirror p, .ProseMirror h2, .ProseMirror h3"
EDITOR_LOAD_TIMEOUT_SEC  = 60
OGP_TARGET_DOMAINS       = ["amzn.to", "amazon.co.jp", "apple.com", "youtube.com"]
TOP_IMAGE_BUTTON_SELECTOR = 'button[aria-label="画像を追加"]'
PAGE_IMAGE_SELECTOR = "main img"
CROP_DIALOG_SELECTOR = "div.ReactModal__Content.CropModal__content[role='dialog'][aria-modal='true']"
TOP_IMAGE_LOADING_SELECTOR = "main div[class*='sc-e17b66d3-0']"
URL_RE = re.compile(r"https?://[^\s\n\r<>\"']+")

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


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"モジュールを読み込めません: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_amazon_affiliate_module():
    return _load_module_from_path("insert_amazon_affiliate_runtime", AMAZON_AFFILIATE_SCRIPT)


def _load_amazon_top_image_module():
    return _load_module_from_path("amazon_gazo_get_runtime", AMAZON_TOP_IMAGE_SCRIPT)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dump_page_artifacts(page, artifacts_dir: Path, stem: str) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifacts_dir / f"{stem}.png"
    html_path = artifacts_dir / f"{stem}.html"
    page.screenshot(path=str(screenshot_path), full_page=True)
    _write_text(html_path, page.content())
    return {
        "screenshot": str(screenshot_path),
        "html": str(html_path),
    }


def _collect_control_snapshot(page) -> list[dict]:
    locator = page.locator("input[type='file'], button, [role='button'], label")
    return locator.evaluate_all(
        """
        (els) => els.map((el, index) => {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          const text = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
          return {
            index,
            tag: (el.tagName || "").toLowerCase(),
            type: el.getAttribute("type") || "",
            role: el.getAttribute("role") || "",
            text,
            aria_label: el.getAttribute("aria-label") || "",
            title: el.getAttribute("title") || "",
            accept: el.getAttribute("accept") || "",
            class_name: String(el.className || ""),
            visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0,
            disabled: Boolean(el.disabled) || el.getAttribute("aria-disabled") === "true"
          };
        })
        """
    )


def _count_page_images(page) -> int:
    return page.locator(PAGE_IMAGE_SELECTOR).count()


def _iter_playwright_scopes(page):
    scopes = [("page", page)]
    for idx, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        scopes.append((f"frame#{idx}", frame))
    return scopes


def _find_visible_candidate(candidates, description: str, timeout_ms: int = 1500):
    errors = []
    for strategy, locator in candidates:
        try:
            total = locator.count()
        except Exception as exc:
            errors.append(f"{strategy}: count失敗={exc}")
            continue

        for idx in range(total - 1, -1, -1):
            candidate = locator.nth(idx)
            try:
                candidate.wait_for(state="visible", timeout=timeout_ms)
                return f"{strategy}#{idx}", candidate
            except Exception as exc:
                errors.append(f"{strategy}#{idx}: {exc}")

    raise RuntimeError(f"{description} を特定できませんでした: {' / '.join(errors[:6])}")


def _click_locator_with_fallback(page, locator, strategy: str, description: str, timeout_ms: int = 4000) -> None:
    locator.scroll_into_view_if_needed()
    click_errors = []
    for click_name, clicker in [
        ("通常click", lambda: locator.click(timeout=timeout_ms)),
        ("force click", lambda: locator.click(timeout=timeout_ms, force=True)),
        ("DOM click", lambda: locator.evaluate("(element) => element.click()")),
    ]:
        try:
            clicker()
            page.wait_for_timeout(1000)
            print(f"   ✅ {description}: {strategy} ({click_name})")
            return
        except Exception as exc:
            click_errors.append(f"{click_name}={exc}")

    raise RuntimeError(f"{description} の click に失敗しました: {strategy}: {' / '.join(click_errors[:3])}")


def _click_visible_candidate(page, candidates, description: str, timeout_ms: int = 4000) -> str:
    strategy, locator = _find_visible_candidate(candidates, description)
    _click_locator_with_fallback(page, locator, strategy, description, timeout_ms=timeout_ms)
    return strategy


def _find_visible_scoped_candidate(page, candidate_builders, description: str, timeout_ms: int = 1500):
    errors = []
    for scope_name, scope in _iter_playwright_scopes(page):
        for strategy, builder in candidate_builders:
            try:
                locator = builder(scope)
                total = locator.count()
            except Exception as exc:
                errors.append(f"{scope_name}:{strategy}: count失敗={exc}")
                continue

            for idx in range(total - 1, -1, -1):
                candidate = locator.nth(idx)
                try:
                    candidate.wait_for(state="visible", timeout=timeout_ms)
                    return f"{scope_name}:{strategy}#{idx}", candidate
                except Exception as exc:
                    errors.append(f"{scope_name}:{strategy}#{idx}: {exc}")

    raise RuntimeError(f"{description} を特定できませんでした: {' / '.join(errors[:6])}")


def _click_visible_scoped_candidate(page, candidate_builders, description: str, timeout_ms: int = 4000) -> str:
    strategy, locator = _find_visible_scoped_candidate(page, candidate_builders, description)
    _click_locator_with_fallback(page, locator, strategy, description, timeout_ms=timeout_ms)
    return strategy


def _click_rightmost_scoped_candidate(page, candidate_builders, description: str, timeout_ms: int = 4000) -> str:
    best = None
    errors = []
    for scope_name, scope in _iter_playwright_scopes(page):
        for strategy, builder in candidate_builders:
            try:
                locator = builder(scope)
                total = locator.count()
            except Exception as exc:
                errors.append(f"{scope_name}:{strategy}: count失敗={exc}")
                continue
            for idx in range(total):
                candidate = locator.nth(idx)
                try:
                    candidate.wait_for(state="visible", timeout=1200)
                    box = candidate.bounding_box() or {}
                    x = box.get("x", -1)
                    if best is None or x > best[0]:
                        best = (x, f"{scope_name}:{strategy}#{idx}", candidate)
                except Exception as exc:
                    errors.append(f"{scope_name}:{strategy}#{idx}: {exc}")
    if best is None:
        raise RuntimeError(f"{description} を特定できませんでした: {' / '.join(errors[:6])}")
    _, strategy, locator = best
    _click_locator_with_fallback(page, locator, strategy, description, timeout_ms=timeout_ms)
    return strategy


def _collect_file_input_candidates(page, prefer_adobe: bool = False) -> list[tuple[int, str, int, object, dict]]:
    candidates = []
    for scope_name, scope in _iter_playwright_scopes(page):
        file_inputs = scope.locator("input[type='file']")
        total = 0
        try:
            total = file_inputs.count()
        except Exception:
            continue
        for idx in range(total):
            input_locator = file_inputs.nth(idx)
            try:
                metadata = input_locator.evaluate(
                    """
                    (el) => {
                      const root = el.getRootNode();
                      const host = root && root.host ? root.host : null;
                      const rect = el.getBoundingClientRect();
                      const style = window.getComputedStyle(el);
                      return {
                        accept: el.getAttribute('accept') || '',
                        id: el.id || '',
                        class_name: String(el.className || ''),
                        visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                        root_kind: root && root.toString ? root.toString() : '',
                        host_tag: host && host.tagName ? host.tagName.toLowerCase() : '',
                        host_id: host && host.id ? host.id : '',
                        host_class: host ? String(host.className || '') : ''
                      };
                    }
                    """
                )
            except Exception:
                continue

            accept = (metadata.get("accept") or "").lower()
            if accept and "image" not in accept:
                continue

            combined = " ".join(
                [
                    scope_name,
                    metadata.get("id") or "",
                    metadata.get("class_name") or "",
                    metadata.get("host_tag") or "",
                    metadata.get("host_id") or "",
                    metadata.get("host_class") or "",
                ]
            ).lower()
            root_kind = (metadata.get("root_kind") or "").lower()
            score = 0
            if accept:
                score += 20
            if "shadowroot" in root_kind:
                score += 40
            if "cc-everywhere-container" in combined:
                score += 120
            if any(token in combined for token in ["adobe", "express", "upload", "asset", "media"]):
                score += 30
            if metadata.get("visible"):
                score += 5
            if prefer_adobe and "shadowroot" not in root_kind:
                score -= 30

            candidates.append((score, scope_name, idx, input_locator, metadata))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def _try_set_existing_file_input_any_scope(page, image_path: Path, prefer_adobe: bool = False) -> str | None:
    for score, scope_name, idx, input_locator, metadata in _collect_file_input_candidates(page, prefer_adobe=prefer_adobe):
        try:
            input_locator.set_input_files(str(image_path))
            page.wait_for_timeout(1500)
            root_kind = metadata.get("root_kind") or ""
            host_tag = metadata.get("host_tag") or ""
            used = f"{scope_name}:input[type='file']#{idx}:score={score}:root={root_kind}:host={host_tag}"
            print(f"   ✅ 画像ファイル指定: {used}")
            return used
        except Exception:
            continue
    return None


def _try_set_existing_file_input_with_brief_wait(
    page,
    image_path: Path,
    prefer_adobe: bool = False,
    wait_ms: int = 500,
) -> str | None:
    if wait_ms > 0:
        page.wait_for_timeout(wait_ms)
    return _try_set_existing_file_input_any_scope(page, image_path, prefer_adobe=prefer_adobe)


def _wait_for_existing_file_input_any_scope(
    page,
    image_path: Path,
    prefer_adobe: bool = False,
    timeout_ms: int = 4000,
    poll_ms: int = 250,
) -> str | None:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        direct_input = _try_set_existing_file_input_any_scope(page, image_path, prefer_adobe=prefer_adobe)
        if direct_input:
            return direct_input
        page.wait_for_timeout(poll_ms)
    return _try_set_existing_file_input_any_scope(page, image_path, prefer_adobe=prefer_adobe)


def _serialize_file_input_candidates(page, prefer_adobe: bool = False, limit: int = 20) -> list[dict]:
    serialized = []
    for score, scope_name, idx, _input_locator, metadata in _collect_file_input_candidates(
        page,
        prefer_adobe=prefer_adobe,
    ):
        serialized.append(
            {
                "score": score,
                "scope_name": scope_name,
                "index": idx,
                "accept": metadata.get("accept") or "",
                "id": metadata.get("id") or "",
                "class_name": metadata.get("class_name") or "",
                "visible": bool(metadata.get("visible")),
                "root_kind": metadata.get("root_kind") or "",
                "host_tag": metadata.get("host_tag") or "",
                "host_id": metadata.get("host_id") or "",
                "host_class": metadata.get("host_class") or "",
            }
        )
        if len(serialized) >= limit:
            break
    return serialized


def _has_adobe_file_input_candidate(page) -> bool:
    for score, scope_name, _idx, _input_locator, metadata in _collect_file_input_candidates(
        page,
        prefer_adobe=True,
    ):
        combined = " ".join(
            [
                scope_name,
                metadata.get("id") or "",
                metadata.get("class_name") or "",
                metadata.get("host_tag") or "",
                metadata.get("host_id") or "",
                metadata.get("host_class") or "",
            ]
        ).lower()
        if score >= 100:
            return True
        if "cc-everywhere-container" in combined:
            return True
        if any(token in combined for token in ["adobe", "express"]):
            return True
    return False


def _write_control_snapshot(path: Path, page) -> None:
    _write_json(path, _collect_control_snapshot(page))


def _dump_upload_retry_artifacts(page, artifacts_dir: Path | None, stem: str) -> None:
    if not artifacts_dir:
        return
    _dump_page_artifacts(page, artifacts_dir, stem)
    _write_control_snapshot(artifacts_dir / f"{stem}_controls.json", page)


def _click_top_image_button(page) -> str:
    return _click_visible_candidate(
        page,
        candidates=[
            ("button[aria-label='画像を追加']", page.locator(TOP_IMAGE_BUTTON_SELECTOR)),
            ("button[aria-label*='画像']", page.locator("button[aria-label*='画像']")),
        ],
        description="トップ画像ボタン",
    )


def _choose_direct_upload_image_file(page, image_path: Path, artifacts_dir: Path | None = None) -> str:
    upload_text_pattern = re.compile(r"画像\s*を?\s*アップロード|^アップロード$")
    errors = []

    def build_candidate_locators():
        return [
            (
                "button_role_label_regex_upload",
                page.locator("button, [role='button'], label").filter(has_text=upload_text_pattern),
            ),
            (
                "role_button_regex_upload",
                page.get_by_role("button", name=upload_text_pattern),
            ),
            (
                "aria_label_contains_upload",
                page.locator("[aria-label*='アップロード'], [title*='アップロード']"),
            ),
            (
                "xpath_clickable_upload_ancestor",
                page.locator(
                    "xpath=//*[contains(normalize-space(.), '画像をアップロード') or normalize-space(.)='アップロード']"
                    "/ancestor-or-self::*[self::button or self::label or @role='button'][1]"
                ),
            ),
            ("text_画像をアップロード", page.locator("text=画像をアップロード")),
            ("text_アップロード", page.locator("text=アップロード")),
        ]

    def has_visible_upload_entry() -> bool:
        for _strategy, locator in build_candidate_locators():
            try:
                total = locator.count()
            except Exception:
                continue
            for idx in range(total):
                try:
                    if locator.nth(idx).is_visible():
                        return True
                except Exception:
                    continue
        return False

    for attempt in range(1, 6):
        direct_input = _try_set_existing_file_input_any_scope(page, image_path)
        if direct_input:
            return direct_input

        found_candidate = False
        for strategy, locator in build_candidate_locators():
            try:
                total = locator.count()
            except Exception as exc:
                errors.append(f"{strategy}: count失敗={exc}")
                continue

            if total > 0:
                found_candidate = True

            for idx in range(total - 1, -1, -1):
                candidate = locator.nth(idx)
                try:
                    candidate.wait_for(state="visible", timeout=1500)
                except Exception as exc:
                    errors.append(f"{strategy}#{idx}: visible失敗={exc}")
                    continue

                try:
                    with page.expect_file_chooser(timeout=3000) as chooser_info:
                        _click_locator_with_fallback(
                            page,
                            candidate,
                            f"{strategy}#{idx}",
                            "画像アップロード導線",
                            timeout_ms=4000,
                        )
                    chooser_info.value.set_files(str(image_path))
                    page.wait_for_timeout(1500)
                    used = f"{strategy}#{idx}:filechooser"
                    print(f"   ✅ 画像アップロード導線: {used}")
                    return used
                except Exception as exc:
                    _dump_upload_retry_artifacts(
                        page,
                        artifacts_dir,
                        f"direct_upload_click_attempt{attempt}_{idx}",
                    )
                    direct_input = _wait_for_existing_file_input_any_scope(
                        page,
                        image_path,
                        timeout_ms=4000,
                        poll_ms=250,
                    )
                    if direct_input:
                        used = f"{strategy}#{idx}:postclick:{direct_input}"
                        print(f"   ✅ 画像アップロード導線: {used}")
                        return used
                    errors.append(f"{strategy}#{idx}: filechooser未発火={exc}")
                    try:
                        candidate.wait_for(state="visible", timeout=500)
                    except Exception as exc:
                        errors.append(f"{strategy}#{idx}: click再試行前に導線消失={exc}")
                        continue
                    try:
                        _click_locator_with_fallback(
                            page,
                            candidate,
                            f"{strategy}#{idx}",
                            "画像アップロード導線",
                            timeout_ms=1500,
                        )
                        _dump_upload_retry_artifacts(
                            page,
                            artifacts_dir,
                            f"direct_upload_reclick_attempt{attempt}_{idx}",
                        )
                        direct_input = _wait_for_existing_file_input_any_scope(
                            page,
                            image_path,
                            timeout_ms=2500,
                            poll_ms=250,
                        )
                        if direct_input:
                            used = f"{strategy}#{idx}:reclick:{direct_input}"
                            print(f"   ✅ 画像アップロード導線: {used}")
                            return used
                    except Exception as exc:
                        errors.append(f"{strategy}#{idx}: click失敗={exc}")

        if attempt < 5:
            if not found_candidate:
                errors.append(f"attempt{attempt}: no_upload_entry_visible")
            if not has_visible_upload_entry():
                try:
                    reopen_strategy = _click_top_image_button(page)
                    print(f"   🔄 トップ画像メニューを再オープン: {reopen_strategy} (attempt {attempt + 1})")
                    _dump_upload_retry_artifacts(page, artifacts_dir, f"top_image_menu_reopened_attempt{attempt + 1}")
                except Exception as exc:
                    errors.append(f"attempt{attempt}: menu_reopen_failed={exc}")
            page.wait_for_timeout(1000)

    direct_input = _try_set_existing_file_input_any_scope(page, image_path)
    if direct_input:
        return direct_input

    raise RuntimeError(f"画像アップロード導線を特定できませんでした: {' / '.join(errors[:8])}")


def _wait_for_crop_dialog(page):
    return _find_visible_candidate(
        candidates=[
            ("CropModal__content", page.locator(CROP_DIALOG_SELECTOR)),
            ("ReactModal__Content_dialog", page.locator("div.ReactModal__Content[role='dialog'][aria-modal='true']")),
            ("role_dialog", page.get_by_role("dialog")),
        ],
        description="画像保存モーダル",
        timeout_ms=15000,
    )


def _save_crop_dialog(page) -> str:
    dialog_strategy, dialog = _wait_for_crop_dialog(page)
    save_strategy = _click_visible_candidate(
        page,
        candidates=[
            (f"{dialog_strategy}->role_button_保存", dialog.get_by_role("button", name="保存")),
            (f"{dialog_strategy}->button_text_保存", dialog.locator("button").filter(has_text="保存")),
            (f"{dialog_strategy}->text_保存", dialog.locator("text=保存")),
        ],
        description="画像モーダル保存",
    )
    try:
        page.locator(CROP_DIALOG_SELECTOR).last.wait_for(state="hidden", timeout=15000)
    except Exception:
        page.wait_for_timeout(1500)
    return save_strategy


def _wait_for_uploaded_image_ready(page, previous_count: int, timeout_sec: int = 60) -> tuple[int, str]:
    for _ in range(timeout_sec):
        current_count = _count_page_images(page)
        if current_count > previous_count:
            return current_count, "main_img_detected"

        loading_locator = page.locator(TOP_IMAGE_LOADING_SELECTOR)
        if loading_locator.count() > 0:
            try:
                if loading_locator.first.is_visible():
                    page.wait_for_timeout(1000)
                    continue
            except Exception:
                page.wait_for_timeout(1000)
                continue
        page.wait_for_timeout(1000)

    return _count_page_images(page), "timeout"


def _save_editor_draft(page) -> str:
    strategy = _click_visible_candidate(
        page,
        candidates=[
            ("role_button_下書き保存", page.get_by_role("button", name="下書き保存")),
            ("header_button_下書き保存", page.locator("header button").filter(has_text="下書き保存")),
            ("button_text_下書き保存", page.locator("button").filter(has_text="下書き保存")),
        ],
        description="エディタ下書き保存",
    )
    page.wait_for_timeout(5000)
    return strategy


def _run_direct_note_image_upload(page, image_path: Path, artifacts_dir: Path, previous_count: int) -> dict:
    controls_after_menu = _collect_control_snapshot(page)
    _write_json(artifacts_dir / "controls_after_top_image_menu.json", controls_after_menu)
    upload_entry_strategy = _choose_direct_upload_image_file(page, image_path, artifacts_dir=artifacts_dir)
    crop_dialog_strategy, _ = _wait_for_crop_dialog(page)
    _dump_page_artifacts(page, artifacts_dir, "crop_modal_open")
    popup_save_strategy = _save_crop_dialog(page)
    _dump_page_artifacts(page, artifacts_dir, "after_crop_modal_save")
    ready_image_count, ready_wait_strategy = _wait_for_uploaded_image_ready(
        page,
        previous_count=previous_count,
        timeout_sec=60,
    )
    return {
        "upload_entry_strategy": upload_entry_strategy,
        "crop_dialog_strategy": crop_dialog_strategy,
        "popup_save_strategy": popup_save_strategy,
        "ready_wait_strategy": ready_wait_strategy,
        "after_ready_image_count": ready_image_count,
    }


def _is_adobe_workspace_visible(page) -> bool:
    if _is_adobe_welcome_modal_visible(page):
        return True
    if _is_adobe_login_prompt_visible(page):
        return True
    if _has_adobe_file_input_candidate(page):
        return True

    candidate_builders = [
        (
            "cc_everywhere_container",
            lambda scope: scope.locator("xpath=//*[starts-with(local-name(), 'cc-everywhere-container-')]"),
        ),
        ("text_powered_by_adobe", lambda scope: scope.locator("text=Powered by Adobe Express")),
        ("x_embed_editor_save_button", lambda scope: scope.locator("x-embed-editor-save-button")),
        ("sp_button_save_btn", lambda scope: scope.locator("sp-button#save-btn")),
        ("dialog_download_btn", lambda scope: scope.locator("sp-button#dialog-download-btn")),
        (
            "adobe_dialog",
            lambda scope: scope.locator("[role='dialog'], [aria-modal='true']").filter(
                has_text=re.compile("Adobe Express")
            ),
        ),
        ("text_ファイル形式", lambda scope: scope.locator("text=ファイル形式")),
        ("button_アップロード", lambda scope: scope.get_by_role("button", name="アップロード")),
        ("text_アップロード", lambda scope: scope.locator("text=アップロード")),
    ]
    for _, scope in _iter_playwright_scopes(page):
        for _, builder in candidate_builders:
            try:
                locator = builder(scope)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:
                continue
    return False


def _wait_for_adobe_workspace(page, timeout_sec: int = 40) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _is_adobe_workspace_visible(page):
            return
        page.wait_for_timeout(1000)
    raise RuntimeError("Adobe Express の作業画面が表示されませんでした。")


def _is_adobe_welcome_modal_visible(page) -> bool:
    candidate_builders = [
        ("text_welcome", lambda scope: scope.locator("text=Adobe Expressへようこそ")),
        ("text_welcome_spaced", lambda scope: scope.locator("text=Adobe Express へようこそ")),
        ("text_welcome_short", lambda scope: scope.locator("text=ようこそ")),
    ]
    for _, scope in _iter_playwright_scopes(page):
        for _, builder in candidate_builders:
            try:
                locator = builder(scope)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:
                continue
    return False


def _is_adobe_login_prompt_visible(page) -> bool:
    candidate_builders = [
        ("text_login", lambda scope: scope.locator("text=ログイン")),
        ("text_adobe_id", lambda scope: scope.locator("text=Adobe ID")),
        ("text_continue_using", lambda scope: scope.locator("text=続けてご利用")),
    ]
    for _, scope in _iter_playwright_scopes(page):
        for _, builder in candidate_builders:
            try:
                locator = builder(scope)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:
                continue
    return False


def _dismiss_adobe_welcome_modal(page) -> str:
    if not _is_adobe_welcome_modal_visible(page):
        return ""

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        if not _is_adobe_welcome_modal_visible(page):
            print("   ✅ Adobe welcome モーダル: Escape で閉じました")
            return "keyboard_escape"
    except Exception:
        pass

    candidate_builders = [
        ("aria_close", lambda scope: scope.locator("[aria-label='閉じる'], [aria-label='Close']")),
        ("role_button_閉じる", lambda scope: scope.get_by_role("button", name=re.compile("閉じる|Close"))),
        ("role_button_continue", lambda scope: scope.get_by_role("button", name=re.compile("続ける|続行|次へ|開始|始める|了解|スキップ"))),
        ("button_text_continue", lambda scope: scope.locator("button").filter(has_text=re.compile("続ける|続行|次へ|開始|始める|了解|スキップ"))),
    ]
    strategy = _click_rightmost_scoped_candidate(
        page,
        candidate_builders=candidate_builders,
        description="Adobe welcome モーダル解除",
        timeout_ms=4000,
    )
    page.wait_for_timeout(1500)
    return strategy


def _wait_for_adobe_workspace_closed(page, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _is_adobe_workspace_visible(page):
            return
        page.wait_for_timeout(1000)
    print("   ⚠️ Adobe Express 画面のクローズ待機がタイムアウトしました。続行します。")


def _choose_adobe_express_entry(page) -> str:
    return _click_visible_candidate(
        page,
        candidates=[
            ("text=Adobe Expressで画像をつくる", page.locator("text=Adobe Expressで画像をつくる")),
            ("button_text_Adobe", page.locator("button").filter(has_text="Adobe Expressで画像をつくる")),
            ("role_button_Adobe", page.get_by_role("button", name="Adobe Expressで画像をつくる")),
        ],
        description="Adobe Express 導線",
    )


def _open_adobe_upload_sidebar(page) -> str:
    return _click_visible_scoped_candidate(
        page,
        candidate_builders=[
            ("sidebar_upload_role_exact", lambda scope: scope.get_by_role("button", name="アップロード", exact=True)),
            ("sidebar_upload_text_exact", lambda scope: scope.locator("button, [role='button'], label").filter(has_text=re.compile(r"^アップロード$"))),
            ("sidebar_upload_aria", lambda scope: scope.locator("[aria-label='アップロード']")),
        ],
        description="Adobe Express アップロードサイドバー",
        timeout_ms=4000,
    )


def _wait_for_adobe_upload_signal(page, image_path: Path, timeout_sec: int = 15) -> str:
    candidate_builders = [
        ("blob_image", lambda scope: scope.locator("img[src^='blob:']")),
        ("blob_image_alt", lambda scope: scope.locator(f"img[alt*='{image_path.stem}']")),
        ("filename_text", lambda scope: scope.locator(f"text={image_path.name}")),
        ("filename_stem_text", lambda scope: scope.locator(f"text={image_path.stem}")),
    ]
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            strategy, _ = _find_visible_scoped_candidate(
                page,
                candidate_builders,
                "Adobe Express アップロード反映",
                timeout_ms=1200,
            )
            print(f"   ✅ Adobe アップロード反映検出: {strategy}")
            return strategy
        except Exception as exc:
            last_error = str(exc)
            page.wait_for_timeout(1000)
    print(f"   ⚠️ Adobe アップロード反映は確認できませんでした: {last_error}")
    return "timeout"


def _build_adobe_top_insert_candidate_builders():
    return [
        (
            "sp_button_save_btn",
            lambda scope: scope.locator("x-embed-editor-save-button sp-button#save-btn"),
        ),
        (
            "sp_button_save_btn_global",
            lambda scope: scope.locator("sp-button#save-btn"),
        ),
        (
            "sp_button_save_to_host_app",
            lambda scope: scope.locator("sp-button#save-btn[export-option-id='save-to-host-app']"),
        ),
        ("role_button_挿入", lambda scope: scope.get_by_role("button", name="挿入")),
        ("button_text_挿入", lambda scope: scope.locator("button").filter(has_text="挿入")),
    ]


def _build_adobe_confirm_insert_candidate_builders():
    return [
        (
            "dialog_download_btn_scoped",
            lambda scope: scope.locator(
                "x-embed-editor-save-button overlay-trigger[type='modal'] sp-button#dialog-download-btn"
            ),
        ),
        (
            "dialog_download_btn_global",
            lambda scope: scope.locator("sp-button#dialog-download-btn"),
        ),
        (
            "dialog_download_btn_host_app",
            lambda scope: scope.locator(
                "overlay-trigger[type='modal'] sp-button[export-option-id='save-to-host-app']"
            ),
        ),
        (
            "dialog_download_btn_slot_trigger",
            lambda scope: scope.locator("overlay-trigger[type='modal'] sp-button[slot='trigger']"),
        ),
        (
            "panel_button_挿入_xpath",
            lambda scope: scope.locator(
                "xpath=//div[.//*[contains(normalize-space(), 'ファイル形式')]]//button[normalize-space()='挿入']"
            ),
        ),
        (
            "panel_button_挿入_text_xpath",
            lambda scope: scope.locator(
                "xpath=//div[.//*[contains(normalize-space(), 'ファイル形式')]]//*[self::button or @role='button'][contains(normalize-space(), '挿入')]"
            ),
        ),
    ]


def _wait_for_adobe_confirm_insert_panel(page, timeout_sec: int = 20) -> str:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if _is_adobe_login_prompt_visible(page):
            raise RuntimeError("ADOBE_LOGIN_REQUIRED")
        try:
            strategy, _ = _find_visible_scoped_candidate(
                page,
                _build_adobe_confirm_insert_candidate_builders(),
                "Adobe Express 確定挿入パネル",
                timeout_ms=1200,
            )
            print(f"   ✅ Adobe Express 確定挿入パネル検出: {strategy}")
            return strategy
        except Exception as exc:
            last_error = str(exc)
            page.wait_for_timeout(800)
    raise RuntimeError(f"Adobe Express 確定挿入パネルが表示されませんでした: {last_error}")


def _upload_image_via_adobe_express(page, image_path: Path, artifacts_dir: Path, previous_count: int) -> dict:
    adobe_entry_strategy = _choose_adobe_express_entry(page)
    _dump_page_artifacts(page, artifacts_dir, "adobe_entry_clicked")
    _wait_for_adobe_workspace(page)
    _dump_page_artifacts(page, artifacts_dir, "adobe_workspace_open")
    welcome_modal_strategy = ""
    if not welcome_modal_strategy:
        try:
            welcome_modal_strategy = _dismiss_adobe_welcome_modal(page)
        except Exception as exc:
            print(f"   笞・・Adobe welcome 繝｢繝ｼ繝繝ｫ隗｣髯､螟ｱ謨暦ｼ育ｶ夊｡鯉ｼ・ {exc}")
    if welcome_modal_strategy:
        page.wait_for_timeout(1500)
        _dump_page_artifacts(page, artifacts_dir, "adobe_welcome_dismissed")

    _write_json(
        artifacts_dir / "adobe_file_input_candidates_pre_sidebar.json",
        _serialize_file_input_candidates(page, prefer_adobe=True),
    )
    pre_sidebar_input_strategy = _wait_for_existing_file_input_any_scope(
        page,
        image_path,
        prefer_adobe=True,
        timeout_ms=6000,
        poll_ms=400,
    )

    if pre_sidebar_input_strategy:
        upload_sidebar_strategy = "direct_input_pre_sidebar"
        upload_strategy = pre_sidebar_input_strategy
    else:
        upload_sidebar_strategy = _open_adobe_upload_sidebar(page)
        _dump_page_artifacts(page, artifacts_dir, "adobe_upload_sidebar_open")
        _write_json(
            artifacts_dir / "adobe_file_input_candidates_post_sidebar.json",
            _serialize_file_input_candidates(page, prefer_adobe=True),
        )
        upload_strategy = _wait_for_existing_file_input_any_scope(
            page,
            image_path,
            prefer_adobe=True,
            timeout_ms=6000,
            poll_ms=400,
        )
    if not upload_strategy:
        upload_strategy = _click_visible_scoped_candidate(
            page,
            candidate_builders=[
                ("role_button_アップロード", lambda scope: scope.get_by_role("button", name="アップロード")),
                ("text_アップロード", lambda scope: scope.locator("text=アップロード")),
                ("label_アップロード", lambda scope: scope.locator("label").filter(has_text="アップロード")),
            ],
            description="Adobe Express アップロード導線",
        )
        page.wait_for_timeout(1200)
        direct_input = _wait_for_existing_file_input_any_scope(
            page,
            image_path,
            prefer_adobe=True,
            timeout_ms=4000,
            poll_ms=300,
        )
        if direct_input:
            upload_strategy = f"{upload_strategy}:{direct_input}"

    upload_signal_strategy = _wait_for_adobe_upload_signal(page, image_path, timeout_sec=12)
    page.wait_for_timeout(2500)
    _dump_page_artifacts(page, artifacts_dir, "adobe_after_upload")
    welcome_modal_strategy = ""
    try:
        welcome_modal_strategy = _dismiss_adobe_welcome_modal(page)
    except Exception as exc:
        print(f"   ⚠️ Adobe welcome モーダル解除失敗（続行）: {exc}")

    insert_strategy = _click_visible_scoped_candidate(
        page,
        candidate_builders=_build_adobe_top_insert_candidate_builders(),
        description="Adobe Express 上部挿入",
    )
    page.wait_for_timeout(2000)
    _dump_page_artifacts(page, artifacts_dir, "adobe_after_first_insert")
    if _is_adobe_login_prompt_visible(page):
        raise RuntimeError("ADOBE_LOGIN_REQUIRED")

    confirm_panel_strategy = _wait_for_adobe_confirm_insert_panel(page, timeout_sec=20)
    confirm_insert_strategy = _click_visible_scoped_candidate(
        page,
        candidate_builders=_build_adobe_confirm_insert_candidate_builders(),
        description="Adobe Express 確定挿入",
        timeout_ms=6000,
    )
    _dump_page_artifacts(page, artifacts_dir, "adobe_insert_confirmed")

    _wait_for_adobe_workspace_closed(page)
    page.wait_for_timeout(3000)
    ready_image_count, ready_wait_strategy = _wait_for_uploaded_image_ready(
        page,
        previous_count=previous_count,
        timeout_sec=30,
    )
    return {
        "adobe_entry_strategy": adobe_entry_strategy,
        "upload_sidebar_strategy": upload_sidebar_strategy,
        "upload_entry_strategy": upload_strategy,
        "upload_signal_strategy": upload_signal_strategy,
        "welcome_modal_strategy": welcome_modal_strategy,
        "insert_strategy": insert_strategy,
        "confirm_panel_strategy": confirm_panel_strategy,
        "confirm_insert_strategy": confirm_insert_strategy,
        "ready_wait_strategy": ready_wait_strategy,
        "after_ready_image_count": ready_image_count,
    }


def _collect_note_editor_snapshot(page) -> dict:
    return page.evaluate(
        """
        () => {
          const titleEl = document.querySelector('.note-editor__title-input');
          const editor = document.querySelector('.note-editable, [contenteditable="true"]') || document.querySelector('.ProseMirror');
          const normalize = (value) => (value || '').replace(/\\u200B/g, '').replace(/\\s+/g, ' ').trim();
          if (!editor) {
            return { title: normalize(titleEl?.value || titleEl?.innerText || titleEl?.textContent || ''), editor_text: '', h1s: [], h2s: [] };
          }
          return {
            title: normalize(titleEl?.value || titleEl?.innerText || titleEl?.textContent || ''),
            editor_text: normalize(editor.innerText || editor.textContent || ''),
            h1s: Array.from(editor.querySelectorAll('h1')).map((el) => normalize(el.innerText || el.textContent || '')).filter(Boolean),
            h2s: Array.from(editor.querySelectorAll('h2')).map((el) => normalize(el.innerText || el.textContent || '')).filter(Boolean),
          };
        }
        """
    )


def _extract_first_url_before_marker(markdown: str) -> str:
    before_marker = (markdown or "").split("▼", 1)[0]
    match = URL_RE.search(before_marker)
    if not match:
        return ""
    return match.group(0).strip()


def _extract_product_name_from_note_context(snapshot: dict) -> tuple[str, str]:
    affiliate_module = _load_amazon_affiliate_module()

    title = (snapshot.get("title") or "").strip()
    if title:
        product_name = affiliate_module.extract_product_name(title)
        if product_name and len(product_name) <= 30:
            return product_name, "note_title"

    h1s = snapshot.get("h1s") or []
    if h1s:
        product_name = affiliate_module.extract_product_name(h1s[0])
        if product_name and len(product_name) <= 30:
            return product_name, "note_h1"

    h2s = snapshot.get("h2s") or []
    if h2s:
        synthetic_markdown = "\n".join(f"## {h2}" for h2 in h2s)
        product_name = affiliate_module._extract_product_name_from_h2s(synthetic_markdown)
        if product_name:
            return product_name, "note_h2"

    return "", ""


def _resolve_amazon_image_target(page, source_markdown: str) -> dict:
    snapshot = _collect_note_editor_snapshot(page)
    first_url = _extract_first_url_before_marker(source_markdown)
    if first_url:
        amazon_image_module = _load_amazon_top_image_module()
        asin = amazon_image_module.extract_asin_from_url(first_url)
        if asin:
            return {
                "mode": "asin",
                "asin": asin,
                "keyword": "",
                "source": "body_url_before_marker",
                "source_url": first_url,
                "snapshot": snapshot,
            }
        print(f"   ⚠️ 先頭URLから ASIN を抽出できませんでした。タイトル/H2 フォールバックへ進みます: {first_url}")

    product_name, source = _extract_product_name_from_note_context(snapshot)
    if product_name:
        return {
            "mode": "keyword",
            "asin": "",
            "keyword": product_name,
            "source": source,
            "source_url": "",
            "snapshot": snapshot,
        }

    return {
        "mode": "skip",
        "asin": "",
        "keyword": "",
        "source": "unresolved",
        "source_url": "",
        "snapshot": snapshot,
    }


def _attach_amazon_top_image_to_page(page, source_markdown: str, artifacts_dir: Path | None = None) -> dict:
    artifacts_dir = artifacts_dir or NOTE_TOP_IMAGE_ARTIFACTS_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    force_direct_upload = os.getenv("NOTE_TOP_IMAGE_FORCE_DIRECT", "").strip().lower() in {"1", "true", "yes", "on"}

    target = _resolve_amazon_image_target(page, source_markdown)
    _write_json(artifacts_dir / "amazon_target_resolution.json", target)

    if target["mode"] == "skip":
        print("   ⚠️ Amazon 画像対象を特定できなかったため、トップ画像挿入をスキップします。")
        return {
            "image_flow": "skipped",
            "image_target_source": target["source"],
            "draft_save_strategy": "",
            "before_image_count": _count_page_images(page),
        }

    amazon_image_module = _load_amazon_top_image_module()
    fetch_result = amazon_image_module.fetch_and_save_top_images(
        keyword=target["keyword"],
        asin=target["asin"],
    )
    amazon_hires_probe = {
        "detail_page_url": fetch_result.detail_page_url,
        "asin": fetch_result.asin,
        "requests_hires_url": fetch_result.hires_image.image_url if fetch_result.hires_image else "",
        "browser_probe_used": False,
        "browser_hires_url": "",
        "browser_hires_saved_path": "",
        "requests_error": "",
        "browser_error": "",
    }
    try:
        requests_html = amazon_image_module.fetch_detail_page_html(
            fetch_result.asin,
            getattr(amazon_image_module, "DEFAULT_MARKETPLACE", "www.amazon.co.jp"),
        )
        _write_text(artifacts_dir / "amazon_detail_requests.html", requests_html)
        amazon_hires_probe["requests_hires_url"] = (
            amazon_image_module.extract_hires_from_html(requests_html) or ""
        )
    except Exception as exc:
        amazon_hires_probe["requests_error"] = str(exc)

    if not fetch_result.hires_image:
        amazon_hires_probe["browser_probe_used"] = True
        browser_page = None
        try:
            browser_page = page.context.new_page()
            browser_page.goto(fetch_result.detail_page_url, wait_until="domcontentloaded", timeout=60_000)
            browser_page.wait_for_timeout(2500)
            browser_html = browser_page.content()
            _write_text(artifacts_dir / "amazon_detail_browser.html", browser_html)
            browser_hires_url = amazon_image_module.extract_hires_from_html(browser_html) or ""
            amazon_hires_probe["browser_hires_url"] = browser_hires_url
            if browser_hires_url:
                hires_image = amazon_image_module.save_image(
                    label="hires",
                    keyword=fetch_result.asin or target["keyword"] or "amazon_image",
                    image_url=browser_hires_url,
                    output_dir=fetch_result.api_image.local_path.parent,
                    suffix="_hires",
                )
                hires_image = amazon_image_module.save_and_optionally_upload(
                    hires_image,
                    getattr(amazon_image_module, "DEFAULT_ONEDRIVE_FOLDER", ""),
                )
                fetch_result.hires_image = hires_image
                amazon_hires_probe["browser_hires_saved_path"] = str(hires_image.local_path)
        except Exception as exc:
            amazon_hires_probe["browser_error"] = str(exc)
        finally:
            try:
                if browser_page:
                    browser_page.close()
            except Exception:
                pass
    _write_json(artifacts_dir / "amazon_hires_probe.json", amazon_hires_probe)

    before_count = _count_page_images(page)
    controls_before = _collect_control_snapshot(page)
    _write_json(artifacts_dir / "controls_before_top_image.json", controls_before)

    image_button_strategy = _click_top_image_button(page)
    _dump_page_artifacts(page, artifacts_dir, "top_image_menu_open")

    if force_direct_upload:
        print("   ℹ️ NOTE_TOP_IMAGE_FORCE_DIRECT=1 のため通常アップロードを強制します")

    if fetch_result.hires_image and not force_direct_upload:
        try:
            flow_result = _upload_image_via_adobe_express(
                page,
                fetch_result.hires_image.local_path,
                artifacts_dir,
                previous_count=before_count,
            )
            image_flow = "adobe_hires"
            selected_image_path = str(fetch_result.hires_image.local_path)
        except Exception as exc:
            print(f"   ⚠️ Adobe Express フロー失敗のため通常アップロードへフォールバックします: {exc}")
            page.reload(wait_until="domcontentloaded", timeout=60_000)
            if not _wait_for_editor_content(page, timeout_sec=EDITOR_LOAD_TIMEOUT_SEC):
                raise RuntimeError("Adobe Express 失敗後のエディタ再読込に失敗しました。")
            before_count = _count_page_images(page)
            image_button_strategy = _click_top_image_button(page)
            _dump_page_artifacts(page, artifacts_dir, "top_image_menu_reopen_after_adobe_failure")
            flow_result = _run_direct_note_image_upload(
                page,
                fetch_result.api_image.local_path,
                artifacts_dir,
                previous_count=before_count,
            )
            flow_result["adobe_error"] = str(exc)
            image_flow = "direct_api_after_adobe_failure"
            selected_image_path = str(fetch_result.api_image.local_path)
    else:
        flow_result = _run_direct_note_image_upload(
            page,
            fetch_result.api_image.local_path,
            artifacts_dir,
            previous_count=before_count,
        )
        image_flow = "direct_api_forced" if force_direct_upload else "direct_api"
        selected_image_path = str(fetch_result.api_image.local_path)

    draft_save_strategy = _save_editor_draft(page)
    _dump_page_artifacts(page, artifacts_dir, "after_top_image_draft_save")

    result = {
        "image_flow": image_flow,
        "image_target_source": target["source"],
        "image_target_asin": fetch_result.asin,
        "image_target_keyword": target["keyword"],
        "image_target_url": target["source_url"],
        "image_button_strategy": image_button_strategy,
        "draft_save_strategy": draft_save_strategy,
        "api_image_path": str(fetch_result.api_image.local_path),
        "api_image_url": fetch_result.api_image.image_url,
        "hires_image_path": str(fetch_result.hires_image.local_path) if fetch_result.hires_image else "",
        "hires_image_url": fetch_result.hires_image.image_url if fetch_result.hires_image else "",
        "selected_image_path": selected_image_path,
        "before_image_count": before_count,
    }
    result.update(flow_result)
    _write_json(artifacts_dir / "top_image_result.json", result)
    return result


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


def _resolve_browser_storage_state_path() -> str | None:
    adobe_state_env = os.getenv("ADOBE_EXPRESS_STORAGE_STATE", "").strip()
    if adobe_state_env:
        try:
            state = json.loads(adobe_state_env)
        except Exception as exc:
            adobe_state_path = Path(adobe_state_env)
            try:
                if adobe_state_path.exists():
                    return str(adobe_state_path)
            except OSError as path_exc:
                print(f"   [WARN] ADOBE_EXPRESS_STORAGE_STATE をパスとして確認できませんでした: {path_exc}")
            print(f"   [WARN] ADOBE_EXPRESS_STORAGE_STATE を storage_state JSON として解釈できませんでした: {exc}")
        else:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="note_browser_state_",
                delete=False,
            ) as temp_state_file:
                json.dump(state, temp_state_file, ensure_ascii=False, indent=2)
                temp_state_path = temp_state_file.name
            print(f"   📦 ADOBE_EXPRESS_STORAGE_STATE を一時ファイル化しました: {temp_state_path}")
            return temp_state_path
    if ADOBE_STORAGE_STATE_FILE.exists():
        return str(ADOBE_STORAGE_STATE_FILE)
    return None


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


def _run_ogp_expansion_on_draft(
    editor_url: str,
    cookies_dict: dict,
    headless: bool = True,
    source_markdown: str = "",
    run_ogp: bool = True,
    artifacts_dir: Path | None = None,
) -> dict:
    """
    下書き作成後のエディタURLへPlaywrightでアクセスし、OGP展開とトップ画像処理を実行する。
    OGP処理後に Amazon トップ画像挿入を行い、最後に note の下書き保存を押す。
    """
    from playwright.sync_api import sync_playwright

    artifacts_dir = artifacts_dir or NOTE_TOP_IMAGE_ARTIFACTS_DIR
    result = {
        "editor_url": editor_url,
        "ogp_processed_count": 0,
        "top_image": {},
        "success": False,
    }

    print(f"\n── Phase 4: OGP展開 + トップ画像（Playwright） ──")
    print(f"   対象URL: {editor_url}")

    playwright_cookies = _cookies_to_playwright(cookies_dict)

    with sync_playwright() as p:
        storage_state_path = _resolve_browser_storage_state_path()
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=UA,
            locale="ja-JP",
            storage_state=storage_state_path,
        )
        if storage_state_path:
            print(f"   📦 追加のブラウザ state を読込: {storage_state_path}")
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
            return result

        if run_ogp:
            try:
                processed_count = process_ogp_urls(page)
                result["ogp_processed_count"] = processed_count
                print(f"   ✅ OGP展開処理完了: {processed_count}件")
            except Exception as e:
                print(f"   ⚠️ OGP展開エラー: {e}")
        else:
            print("   ⏭️ OGP展開はスキップします。")

        print("   ⏳ OGP反映待機（5秒）...")
        page.wait_for_timeout(5000)

        top_image_result = _attach_amazon_top_image_to_page(
            page,
            source_markdown=source_markdown,
            artifacts_dir=artifacts_dir,
        )
        result["top_image"] = top_image_result

        if top_image_result.get("image_flow") == "skipped":
            print("   💾 トップ画像スキップのため Ctrl+S で保存を要求します...")
            try:
                editor = page.locator(".ProseMirror, .note-editable, [contenteditable='true']").first
                editor.click()
                page.keyboard.press("Control+s")
            except Exception as e:
                print(f"   ⚠️ 保存トリガーエラー（続行）: {e}")
            page.wait_for_timeout(8000)
        else:
            print("   ⏳ トップ画像保存後の安定待機（8秒）...")
            page.wait_for_timeout(8000)

        result["success"] = True
        browser.close()

    print("   ✅ OGP展開 + トップ画像保存が完了しました。")
    return result


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

    # Phase 2: 下書き作成
    print("\n── Phase 2: 下書き作成（API） ──")
    draft = _create_draft_api(session, title, body_html)
    if not draft:
        if not _verify_session(session):
            print("   ⚠️ Cookie無効 → APIログインにフォールバック")
            if not _api_login(session):
                print("❌ 全ての認証手段が失敗しました")
                return result
        draft = _create_draft_api(session, title, body_html)
    if not draft:
        return result

    result["success"] = True
    result["url"] = draft.get("url", "")

    # Phase 3: セッション更新
    print("\n── Phase 3: セッション更新 ──")
    _save_cookies_state(session)

    # Phase 4: OGP展開（Playwright）
    if result["url"]:
        # APIログイン後の最新セッションCookieをsessionオブジェクトから直接取得
        # （_load_cookies()は古い環境変数を返すため使用しない）
        session_cookies = {c.name: c.value for c in session.cookies}
        print(f"   🍪 Playwrightへ渡すCookie: {len(session_cookies)}個")
        editor_result = _run_ogp_expansion_on_draft(
            result["url"],
            session_cookies,
            headless=True,
            source_markdown=markdown,
            run_ogp=run_ogp,
        )
        result["editor_result"] = editor_result

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
        print("   初回セットアップ: python prompts/05-draft-manager/note_draft_poster.py --save-cookies")
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
