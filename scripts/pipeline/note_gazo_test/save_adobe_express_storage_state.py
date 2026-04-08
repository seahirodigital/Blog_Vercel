from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
NOTE_DRAFT_POSTER_PATH = PIPELINE_DIR / "note_draft_poster.py"
DEFAULT_MARKDOWN_PATH = Path(
    r"C:\Users\HCY\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\output\macbook_neo\variants\macbook_neo_gakuwari.md"
)
DEFAULT_OUTPUT_PATH = PIPELINE_DIR / "adobe_express_storage_state.json"
DEFAULT_ARTIFACTS_DIR = SCRIPT_DIR / "artifacts"


def load_note_module():
    spec = importlib.util.spec_from_file_location("note_draft_poster_for_adobe_login", NOTE_DRAFT_POSTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"モジュールを読み込めません: {NOTE_DRAFT_POSTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_markdown(markdown_path: Path) -> str:
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdownが見つかりません: {markdown_path}")
    return markdown_path.read_text(encoding="utf-8")


def create_note_draft(note_module, markdown: str) -> tuple[dict, dict]:
    title, body = note_module.extract_title_and_body(markdown)
    if not title or not body:
        raise RuntimeError("タイトルまたは本文を抽出できませんでした。")

    body_html = note_module.markdown_to_note_html(body)
    cookies = note_module._load_cookies()
    session = note_module._create_session(cookies)
    session.trust_env = False

    draft = note_module._create_draft_api(session, title, body_html)
    if not draft or not draft.get("url"):
        if not note_module._verify_session(session):
            if not note_module._api_login(session):
                raise RuntimeError("note APIログインに失敗しました。")
        draft = note_module._create_draft_api(session, title, body_html)

    if not draft or not draft.get("url"):
        raise RuntimeError("note下書きURLを取得できませんでした。")

    session_cookies = {cookie.name: cookie.value for cookie in session.cookies}
    return draft, session_cookies


def dump_page(page, artifacts_dir: Path, stem: str) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifacts_dir / f"{stem}.png"
    html_path = artifacts_dir / f"{stem}.html"
    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content(), encoding="utf-8")


def wait_for_adobe_login_completion(note_module, page, timeout_sec: int = 600) -> None:
    print("")
    print("ブラウザで Google サインインを完了してください。")
    print("Adobe のログイン要求が消えたら、自動で state を保存します。")
    deadline = note_module.time.time() + timeout_sec
    while note_module.time.time() < deadline:
        try:
            if not note_module._is_adobe_login_prompt_visible(page):
                page.wait_for_timeout(2000)
                if not note_module._is_adobe_login_prompt_visible(page):
                    return
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise RuntimeError("Adobe ログイン完了待機がタイムアウトしました。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adobe Express のログイン state を保存します。")
    parser.add_argument(
        "--markdown-path",
        default=str(DEFAULT_MARKDOWN_PATH),
        help="Adobe Express ログイン導線を開くために使う Markdown のフルパス",
    )
    parser.add_argument(
        "--output-path",
        default=str(DEFAULT_OUTPUT_PATH),
        help="保存する Adobe Express storage_state.json のフルパス",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(DEFAULT_ARTIFACTS_DIR),
        help="スクリーンショット保存先",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_path = Path(args.markdown_path)
    output_path = Path(args.output_path)
    artifacts_dir = Path(args.artifacts_dir)

    note_module = load_note_module()
    markdown = resolve_markdown(markdown_path)
    draft, session_cookies = create_note_draft(note_module, markdown)

    print(f"作成済み下書きURL: {draft['url']}")
    print(f"Adobe state 保存先: {output_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            user_agent=note_module.UA,
            locale="ja-JP",
        )
        context.add_cookies(note_module._cookies_to_playwright(session_cookies))
        page = context.new_page()

        page.goto(draft["url"], wait_until="domcontentloaded", timeout=60_000)
        if not note_module._wait_for_editor_content(page, timeout_sec=60):
            dump_page(page, artifacts_dir, "adobe_login_editor_not_loaded")
            raise RuntimeError("note エディタのロードに失敗しました。")

        dump_page(page, artifacts_dir, "adobe_login_before_top_image")
        note_module._click_top_image_button(page)
        dump_page(page, artifacts_dir, "adobe_login_menu_open")
        note_module._choose_adobe_express_entry(page)
        note_module._wait_for_adobe_workspace(page)
        dump_page(page, artifacts_dir, "adobe_login_workspace_open")

        image_target = note_module._resolve_amazon_image_target(page, markdown)
        if image_target.get("mode") == "skip":
            dump_page(page, artifacts_dir, "adobe_login_target_skip")
            raise RuntimeError("Adobe Express 用の画像対象を特定できませんでした。")

        amazon_module = note_module._load_amazon_top_image_module()
        fetch_result = amazon_module.fetch_and_save_top_images(
            keyword=image_target.get("keyword", ""),
            asin=image_target.get("asin", ""),
        )
        target_path = fetch_result.hires_image.local_path if fetch_result.hires_image else fetch_result.api_image.local_path
        used_input = note_module._try_set_existing_file_input_any_scope(page, target_path)
        if not used_input:
            note_module._click_visible_scoped_candidate(
                page,
                candidate_builders=[
                    ("role_button_アップロード", lambda scope: scope.get_by_role("button", name="アップロード")),
                    ("text_アップロード", lambda scope: scope.locator("text=アップロード")),
                ],
                description="Adobe Express アップロード導線",
            )
            used_input = note_module._try_set_existing_file_input_any_scope(page, target_path)
        if not used_input:
            dump_page(page, artifacts_dir, "adobe_login_upload_failed")
            raise RuntimeError("Adobe Express への画像アップロードに失敗しました。")

        page.wait_for_timeout(4000)
        dump_page(page, artifacts_dir, "adobe_login_after_upload")
        try:
            note_module._dismiss_adobe_welcome_modal(page)
        except Exception:
            pass

        note_module._click_rightmost_scoped_candidate(
            page,
            candidate_builders=[
                ("role_button_挿入", lambda scope: scope.get_by_role("button", name="挿入")),
                ("button_text_挿入", lambda scope: scope.locator("button").filter(has_text="挿入")),
            ],
            description="Adobe Express 上部挿入",
        )
        page.wait_for_timeout(2000)
        dump_page(page, artifacts_dir, "adobe_login_prompt_open")

        print("Adobe の Google サインイン画面まで到達しました。")
        wait_for_adobe_login_completion(note_module, page)

        dump_page(page, artifacts_dir, "adobe_login_after_manual_signin")
        state = context.storage_state()
        output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Adobe Express storage state 保存完了: {output_path}")
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
