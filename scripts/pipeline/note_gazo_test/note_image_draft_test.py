from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
NOTE_DRAFT_POSTER_PATH = SCRIPT_DIR.parent / "note_draft_poster.py"
DEFAULT_IMAGE_PATH = Path(r"C:\Users\HCY\Downloads\Image_fx.png")
DEFAULT_ARTIFACTS_DIR = SCRIPT_DIR / "artifacts"
DEFAULT_MARKDOWN_LABEL = "embedded_default_markdown"
DEFAULT_MARKDOWN_CONTENT = """# note画像アップロード検証

この下書きは `C:\\Users\\HCY\\Downloads\\Image_fx.png` を note エディタへ追加できるかを確認するためのテストです。

## テスト内容

- 既存の API 下書き作成フローを使う
- 画像は note エディタの UI から追加する
- 保存の成否は再読み込み後の画像残存で確認する
"""
EDITOR_IMAGE_SELECTOR = ".ProseMirror img, .note-editable img, [contenteditable='true'] img"

IMAGE_KEYWORDS = [
    "画像",
    "image",
    "photo",
    "picture",
    "写真",
    "media",
    "メディア",
]
INSERT_KEYWORDS = [
    "追加",
    "挿入",
    "insert",
    "add",
    "menu",
    "メニュー",
    "block",
    "ブロック",
]


def load_note_module():
    spec = importlib.util.spec_from_file_location("note_draft_poster", NOTE_DRAFT_POSTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"モジュールを読み込めません: {NOTE_DRAFT_POSTER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_markdown(markdown_path: Path | None) -> tuple[str, str]:
    if markdown_path is None:
        return DEFAULT_MARKDOWN_CONTENT, DEFAULT_MARKDOWN_LABEL
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdownが見つかりません: {markdown_path}")
    return markdown_path.read_text(encoding="utf-8"), str(markdown_path)


def create_note_draft(note_module, markdown: str) -> tuple[dict, dict]:
    title, body = note_module.extract_title_and_body(markdown)
    if not title or not body:
        raise RuntimeError("タイトルまたは本文を抽出できませんでした")

    body_html = note_module.markdown_to_note_html(body)
    cookies = note_module._load_cookies()
    session = note_module._create_session(cookies)
    session.trust_env = False

    if not note_module._verify_session(session):
        print("Cookieが失効しているため、APIログインを試行します...")
        if not note_module._api_login(session):
            raise RuntimeError(
                "note APIログインに失敗しました。"
                "C:\\Users\\HCY\\OneDrive\\開発\\Blog_Vercel\\scripts\\pipeline\\note_draft_poster.py "
                "--save-cookies で Cookie を更新するか、NOTE_EMAIL / NOTE_PASSWORD を設定してください。"
            )

    draft = note_module._create_draft_api(session, title, body_html)
    if not draft or not draft.get("url"):
        raise RuntimeError("note下書きURLを取得できませんでした")

    session_cookies = {cookie.name: cookie.value for cookie in session.cookies}
    return draft, session_cookies


def collect_control_snapshot(page) -> list[dict]:
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def dump_page_artifacts(page, artifacts_dir: Path, stem: str) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifacts_dir / f"{stem}.png"
    html_path = artifacts_dir / f"{stem}.html"

    page.screenshot(path=str(screenshot_path), full_page=True)
    write_text(html_path, page.content())

    return {
        "screenshot": str(screenshot_path),
        "html": str(html_path),
    }


def normalize_metadata(control: dict) -> str:
    return " ".join(
        [
            control.get("text", ""),
            control.get("aria_label", ""),
            control.get("title", ""),
            control.get("accept", ""),
            control.get("role", ""),
            control.get("type", ""),
            control.get("class_name", ""),
        ]
    ).lower()


def filter_controls(controls: list[dict], keywords: list[str]) -> list[dict]:
    matched: list[dict] = []
    for control in controls:
        haystack = normalize_metadata(control)
        if any(keyword.lower() in haystack for keyword in keywords):
            matched.append(control)
    return matched


def get_control_locator(page, control: dict):
    locator = page.locator("input[type='file'], button, [role='button'], label")
    return locator.nth(control["index"])


def try_set_existing_file_input(page, image_path: Path) -> str | None:
    file_inputs = page.locator("input[type='file']")
    for idx in range(file_inputs.count()):
        input_locator = file_inputs.nth(idx)
        try:
            accept = (input_locator.get_attribute("accept") or "").lower()
            if accept and "image" not in accept:
                continue
            input_locator.set_input_files(str(image_path))
            return f"input[type='file']#{idx}"
        except Exception:
            continue
    return None


def try_controls_for_upload(page, controls: list[dict], image_path: Path, label: str) -> str | None:
    for control in controls:
        if not control.get("visible") or control.get("disabled"):
            continue

        locator = get_control_locator(page, control)
        summary = {
            "label": label,
            "text": control.get("text", ""),
            "aria_label": control.get("aria_label", ""),
            "title": control.get("title", ""),
            "index": control.get("index"),
        }
        print(f"試行中: {json.dumps(summary, ensure_ascii=False)}")

        try:
            with page.expect_file_chooser(timeout=2500) as chooser_info:
                locator.click(force=True, timeout=4000)
            chooser_info.value.set_files(str(image_path))
            return f"{label}:filechooser:{control.get('index')}"
        except PlaywrightTimeoutError:
            try:
                locator.click(force=True, timeout=4000)
                page.wait_for_timeout(1200)
                upload_via_input = try_set_existing_file_input(page, image_path)
                if upload_via_input:
                    return f"{label}:{upload_via_input}"
            except Exception:
                continue
        except Exception:
            continue
    return None


def click_controls(page, controls: list[dict], label: str) -> str | None:
    for control in controls:
        if not control.get("visible") or control.get("disabled"):
            continue

        locator = get_control_locator(page, control)
        summary = {
            "label": label,
            "text": control.get("text", ""),
            "aria_label": control.get("aria_label", ""),
            "title": control.get("title", ""),
            "index": control.get("index"),
        }
        print(f"クリック試行: {json.dumps(summary, ensure_ascii=False)}")

        try:
            locator.click(force=True, timeout=4000)
            page.wait_for_timeout(1200)
            return f"{label}:{control.get('index')}"
        except Exception:
            continue
    return None


def wait_for_editor_image(page, previous_count: int, timeout_sec: int = 30) -> int:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current_count = page.locator(EDITOR_IMAGE_SELECTOR).count()
        if current_count > previous_count:
            return current_count
        time.sleep(1)
    return previous_count


def upload_image(page, image_path: Path, artifacts_dir: Path) -> dict:
    controls_before = collect_control_snapshot(page)
    write_json(artifacts_dir / "controls_before.json", controls_before)

    before_count = page.locator(EDITOR_IMAGE_SELECTOR).count()
    strategy = try_set_existing_file_input(page, image_path)

    if not strategy:
        image_controls = filter_controls(controls_before, IMAGE_KEYWORDS)
        strategy = try_controls_for_upload(page, image_controls, image_path, "image_control")

    if not strategy:
        insert_controls = filter_controls(controls_before, INSERT_KEYWORDS)
        opened_menu = click_controls(page, insert_controls, "insert_control")
        if opened_menu:
            controls_after_insert = collect_control_snapshot(page)
            write_json(artifacts_dir / "controls_after_insert.json", controls_after_insert)

            upload_via_input = try_set_existing_file_input(page, image_path)
            if upload_via_input:
                strategy = f"{opened_menu}:{upload_via_input}"
            else:
                image_controls = filter_controls(controls_after_insert, IMAGE_KEYWORDS)
                strategy = try_controls_for_upload(page, image_controls, image_path, opened_menu)

    controls_after = collect_control_snapshot(page)
    write_json(artifacts_dir / "controls_after.json", controls_after)

    if not strategy:
        raise RuntimeError("画像アップロード導線を特定できませんでした。controls_before.json を確認してください。")

    image_count = wait_for_editor_image(page, previous_count=before_count, timeout_sec=30)
    success = image_count > before_count

    return {
        "strategy": strategy,
        "before_image_count": before_count,
        "after_image_count": image_count,
        "success": success,
    }


def save_draft(page) -> None:
    editor = page.locator(".ProseMirror, .note-editable, [contenteditable='true']").first
    editor.click()
    page.keyboard.press("Control+s")
    page.wait_for_timeout(8000)


def run_test(markdown_path: Path | None, image_path: Path, artifacts_dir: Path, headless: bool) -> dict:
    if not image_path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {image_path}")

    note_module = load_note_module()
    markdown, markdown_source = resolve_markdown(markdown_path)
    draft, session_cookies = create_note_draft(note_module, markdown)

    report = {
        "success": False,
        "draft_url": draft["url"],
        "draft_key": draft.get("key", ""),
        "image_path": str(image_path),
        "markdown_path": markdown_source,
        "headless": headless,
    }

    print(f"作成済み下書きURL: {draft['url']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent=note_module.UA,
            locale="ja-JP",
        )
        context.add_cookies(note_module._cookies_to_playwright(session_cookies))
        page = context.new_page()

        try:
            page.goto(draft["url"], wait_until="domcontentloaded", timeout=60_000)
            loaded = note_module._wait_for_editor_content(page, timeout_sec=60)
            if not loaded:
                dump = dump_page_artifacts(page, artifacts_dir, "editor_not_loaded")
                report["artifacts"] = dump
                raise RuntimeError("noteエディタの本文ロード待機に失敗しました")

            dump_page_artifacts(page, artifacts_dir, "before_upload")
            upload_result = upload_image(page, image_path, artifacts_dir)
            report.update(upload_result)

            dump_page_artifacts(page, artifacts_dir, "after_upload")

            if upload_result["success"]:
                save_draft(page)
                dump_page_artifacts(page, artifacts_dir, "after_save")

            report["success"] = upload_result["success"]
        finally:
            browser.close()

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="note画像アップロード下書きテスト")
    parser.add_argument(
        "--markdown-path",
        default="",
        help="note本文に使うMarkdownのフルパス。未指定ならスクリプト内蔵の既定本文を使う",
    )
    parser.add_argument(
        "--image-path",
        default=str(DEFAULT_IMAGE_PATH),
        help="アップロードする画像のフルパス",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(DEFAULT_ARTIFACTS_DIR),
        help="スクリーンショットやHTMLを保存する出力先",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="ブラウザを可視状態で起動する",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_path = Path(args.markdown_path) if args.markdown_path else None
    image_path = Path(args.image_path)
    artifacts_dir = Path(args.artifacts_dir)

    report_path = artifacts_dir / "run_report.json"

    try:
        report = run_test(
            markdown_path=markdown_path,
            image_path=image_path,
            artifacts_dir=artifacts_dir,
            headless=not args.headed,
        )
        write_json(report_path, report)
    except Exception as exc:
        failure_report = {
            "success": False,
            "error": str(exc),
            "markdown_path": str(markdown_path) if markdown_path else DEFAULT_MARKDOWN_LABEL,
            "image_path": str(image_path),
        }
        write_json(report_path, failure_report)
        print(f"失敗: {exc}")
        print(f"レポート: {report_path}")
        return 1

    print("完了レポート:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"レポート: {report_path}")
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
