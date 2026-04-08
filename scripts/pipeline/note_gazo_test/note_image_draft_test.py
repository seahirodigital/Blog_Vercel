from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from playwright.sync_api import Locator
from playwright.sync_api import Page
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
SCRIPT_VERSION = "2.0"
PAGE_IMAGE_SELECTOR = "main img"
TOP_IMAGE_BUTTON_SELECTOR = 'button[aria-label="画像を追加"]'
CROP_DIALOG_SELECTOR = "div.ReactModal__Content.CropModal__content[role='dialog'][aria-modal='true']"
TOP_IMAGE_LOADING_SELECTOR = "main div[class*='sc-e17b66d3-0']"


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

    draft = note_module._create_draft_api(session, title, body_html)
    if draft and draft.get("url"):
        session_cookies = {cookie.name: cookie.value for cookie in session.cookies}
        return draft, session_cookies

    if not note_module._verify_session(session):
        print("セッション確認に失敗したため、APIログインを試行します...")
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


def count_page_images(page: Page) -> int:
    return page.locator(PAGE_IMAGE_SELECTOR).count()


def find_visible_candidate(
    candidates: list[tuple[str, Locator]],
    description: str,
    timeout_ms: int = 1500,
) -> tuple[str, Locator]:
    errors: list[str] = []

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

    joined = " / ".join(errors[:6])
    raise RuntimeError(f"{description} を特定できませんでした: {joined}")


def click_visible_candidate(
    page: Page,
    candidates: list[tuple[str, Locator]],
    description: str,
    timeout_ms: int = 4000,
) -> str:
    strategy, locator = find_visible_candidate(candidates, description)
    locator.scroll_into_view_if_needed()
    locator.click(timeout=timeout_ms)
    page.wait_for_timeout(800)
    print(f"{description} 成功: {strategy}")
    return strategy


def try_set_existing_file_input(page: Page, image_path: Path) -> str | None:
    file_inputs = page.locator("input[type='file']")
    for idx in range(file_inputs.count()):
        input_locator = file_inputs.nth(idx)
        try:
            accept = (input_locator.get_attribute("accept") or "").lower()
            if accept and "image" not in accept:
                continue
            input_locator.set_input_files(str(image_path))
            page.wait_for_timeout(1200)
            print(f"画像ファイル入力 成功: input[type='file']#{idx}")
            return f"input[type='file']#{idx}"
        except Exception:
            continue
    return None


def click_top_image_button(page: Page) -> str:
    return click_visible_candidate(
        page,
        candidates=[
            ("button[aria-label='画像を追加']", page.locator(TOP_IMAGE_BUTTON_SELECTOR)),
            ("button[aria-label*='画像']", page.locator("button[aria-label*='画像']")),
        ],
        description="トップ画像ボタン",
    )


def choose_image_file(page: Page, image_path: Path) -> str:
    direct_input = try_set_existing_file_input(page, image_path)
    if direct_input:
        return direct_input

    candidate_locators = [
        ("text=画像をアップロード", page.locator("text=画像をアップロード")),
        ("button_text_画像をアップロード", page.locator("button").filter(has_text="画像をアップロード")),
        ("label_text_画像をアップロード", page.locator("label").filter(has_text="画像をアップロード")),
        ("role_button_画像をアップロード", page.get_by_role("button", name="画像をアップロード")),
    ]
    errors: list[str] = []

    for strategy, locator in candidate_locators:
        try:
            total = locator.count()
        except Exception as exc:
            errors.append(f"{strategy}: count失敗={exc}")
            continue

        for idx in range(total - 1, -1, -1):
            candidate = locator.nth(idx)
            try:
                candidate.wait_for(state="visible", timeout=1500)
            except Exception as exc:
                errors.append(f"{strategy}#{idx}: visible失敗={exc}")
                continue

            try:
                with page.expect_file_chooser(timeout=3000) as chooser_info:
                    candidate.click(timeout=4000)
                chooser_info.value.set_files(str(image_path))
                page.wait_for_timeout(1200)
                used = f"{strategy}#{idx}:filechooser"
                print(f"画像アップロード導線 成功: {used}")
                return used
            except PlaywrightTimeoutError:
                try:
                    candidate.click(timeout=4000)
                    page.wait_for_timeout(800)
                    direct_input = try_set_existing_file_input(page, image_path)
                    if direct_input:
                        used = f"{strategy}#{idx}:{direct_input}"
                        print(f"画像アップロード導線 成功: {used}")
                        return used
                except Exception as exc:
                    errors.append(f"{strategy}#{idx}: click失敗={exc}")
            except Exception as exc:
                errors.append(f"{strategy}#{idx}: chooser失敗={exc}")

    direct_input = try_set_existing_file_input(page, image_path)
    if direct_input:
        return direct_input

    joined = " / ".join(errors[:6])
    raise RuntimeError(f"画像アップロード導線を特定できませんでした: {joined}")


def wait_for_crop_dialog(page: Page) -> tuple[str, Locator]:
    return find_visible_candidate(
        candidates=[
            ("CropModal__content", page.locator(CROP_DIALOG_SELECTOR)),
            ("ReactModal__Content_dialog", page.locator("div.ReactModal__Content[role='dialog'][aria-modal='true']")),
            ("role_dialog", page.get_by_role("dialog")),
        ],
        description="画像保存モーダル",
        timeout_ms=15000,
    )


def save_crop_dialog(page: Page) -> str:
    dialog_strategy, dialog = wait_for_crop_dialog(page)
    save_strategy = click_visible_candidate(
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


def save_editor_draft(page: Page) -> str:
    strategy = click_visible_candidate(
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


def wait_for_uploaded_image_ready(page: Page, previous_count: int, timeout_sec: int = 60) -> tuple[int, str]:
    for _ in range(timeout_sec):
        current_count = count_page_images(page)
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

    return count_page_images(page), "timeout"


def upload_image(page: Page, image_path: Path, artifacts_dir: Path) -> dict:
    controls_before = collect_control_snapshot(page)
    write_json(artifacts_dir / "controls_before.json", controls_before)

    before_count = count_page_images(page)
    image_button_strategy = click_top_image_button(page)
    dump_page_artifacts(page, artifacts_dir, "after_menu_open")

    controls_after_menu = collect_control_snapshot(page)
    write_json(artifacts_dir / "controls_after_menu.json", controls_after_menu)

    upload_entry_strategy = choose_image_file(page, image_path)
    crop_dialog_strategy, _ = wait_for_crop_dialog(page)
    dump_page_artifacts(page, artifacts_dir, "crop_modal_open")

    popup_save_strategy = save_crop_dialog(page)
    dump_page_artifacts(page, artifacts_dir, "after_popup_save")

    controls_after_popup_save = collect_control_snapshot(page)
    write_json(artifacts_dir / "controls_after_popup_save.json", controls_after_popup_save)

    ready_image_count, ready_wait_strategy = wait_for_uploaded_image_ready(page, previous_count=before_count)
    dump_page_artifacts(page, artifacts_dir, "after_upload_ready")

    draft_save_strategy = save_editor_draft(page)
    dump_page_artifacts(page, artifacts_dir, "after_draft_save")

    return {
        "image_button_strategy": image_button_strategy,
        "upload_entry_strategy": upload_entry_strategy,
        "crop_dialog_strategy": crop_dialog_strategy,
        "popup_save_strategy": popup_save_strategy,
        "ready_wait_strategy": ready_wait_strategy,
        "draft_save_strategy": draft_save_strategy,
        "before_image_count": before_count,
        "after_ready_image_count": ready_image_count,
    }


def reload_and_count_images(page: Page, note_module, artifacts_dir: Path) -> int:
    page.reload(wait_until="domcontentloaded", timeout=60_000)
    loaded = note_module._wait_for_editor_content(page, timeout_sec=60)
    if not loaded:
        dump_page_artifacts(page, artifacts_dir, "reload_failed")
        raise RuntimeError("再読み込み後の note エディタ本文ロード待機に失敗しました")

    dump_page_artifacts(page, artifacts_dir, "after_reload")
    return count_page_images(page)


def run_test(markdown_path: Path | None, image_path: Path, artifacts_dir: Path, headless: bool) -> dict:
    if not image_path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {image_path}")

    note_module = load_note_module()
    markdown, markdown_source = resolve_markdown(markdown_path)
    draft, session_cookies = create_note_draft(note_module, markdown)

    report = {
        "success": False,
        "version": SCRIPT_VERSION,
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
            report["after_reload_image_count"] = reload_and_count_images(page, note_module, artifacts_dir)
            report["success"] = report["after_reload_image_count"] > report["before_image_count"]
        finally:
            browser.close()

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="note画像アップロード下書きテスト ver2.0")
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
            "version": SCRIPT_VERSION,
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
