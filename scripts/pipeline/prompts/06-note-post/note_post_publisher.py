"""
note公開ポスター v1.0

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/05-draft-manager/note_draft_poster.py`
の下書き作成・OGP・目次処理を再利用し、最後にnoteの公開投稿画面まで進める。
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parents[1]
NOTE_DRAFT_SCRIPT = SCRIPT_DIR.parent / "05-draft-manager" / "note_draft_poster.py"
DEFAULT_RESULT_JSON = Path("/tmp/note_post_result.json")
GITHUB_API = "https://api.github.com"
GITHUB_REPO_OWNER = "seahirodigital"
GITHUB_REPO_NAME = "Blog_Vercel"


def _load_note_draft_module():
    spec = importlib.util.spec_from_file_location("note_draft_poster_runtime", NOTE_DRAFT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"note下書きモジュールを読み込めません: {NOTE_DRAFT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["note_draft_poster_runtime"] = module
    spec.loader.exec_module(module)
    return module


def _save_post_url_to_github_var(file_id: str, url: str) -> None:
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token or not file_id or not url:
        return

    key_hash = hashlib.md5(file_id.encode()).hexdigest()[:8].upper()
    var_name = f"NOTE_POST_URL_{key_hash}"
    api_base = f"{GITHUB_API}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    check = requests.get(f"{api_base}/actions/variables/{var_name}", headers=headers, timeout=30)
    payload = {"name": var_name, "value": url}
    if check.status_code == 200:
        response = requests.patch(
            f"{api_base}/actions/variables/{var_name}",
            headers=headers,
            json=payload,
            timeout=30,
        )
    else:
        response = requests.post(
            f"{api_base}/actions/variables",
            headers=headers,
            json=payload,
            timeout=30,
        )

    if response.status_code in (200, 201, 204):
        print(f"   ✅ GitHub Variable {var_name} を保存しました")
    else:
        print(f"   ⚠️ 公開URLのVariable保存失敗 ({response.status_code}): {response.text[:150]}")


def _write_result_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   🧾 結果JSONを書き出しました: {path}")


def _read_markdown(args) -> str:
    if args.editor_url and not args.content and not args.file:
        return ""
    if args.content:
        return args.content
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    raise RuntimeError("Markdownファイルパスまたは --content を指定してください")


def main() -> int:
    parser = argparse.ArgumentParser(description="note.com 公開投稿ポスター v1.0")
    parser.add_argument("file", nargs="?", help="Markdownファイルパス")
    parser.add_argument("--content", help="Markdown文字列を直接指定")
    parser.add_argument("--editor-url", help="既存note下書きの編集URLを直接指定する")
    parser.add_argument("--no-ogp", action="store_true", help="OGP展開をスキップする")
    parser.add_argument("--no-top-image", action="store_true", help="Amazonトップ画像の添付をスキップする")
    parser.add_argument("--no-toc", action="store_true", help="目次挿入をスキップする")
    parser.add_argument("--dry-run-publish", action="store_true", help="最後の「投稿する」は押さない")
    parser.add_argument(
        "--result-json",
        default=str(DEFAULT_RESULT_JSON),
        help="公開結果を書き出すJSONファイルの絶対パス",
    )
    args = parser.parse_args()

    note_module = _load_note_draft_module()
    markdown = _read_markdown(args)
    if args.editor_url:
        cookies = note_module._load_cookies()
        editor_result = note_module._run_ogp_expansion_on_draft(
            args.editor_url,
            cookies,
            headless=True,
            source_markdown=markdown,
            run_ogp=not args.no_ogp,
            run_top_image=not args.no_top_image,
            insert_toc=not args.no_toc,
            publish_after=True,
            dry_run_publish=args.dry_run_publish,
        )
        publish_result = editor_result.get("publish") or {}
        result = {
            "success": bool(publish_result.get("success")),
            "url": args.editor_url,
            "published_url": publish_result.get("final_url", ""),
            "title": "",
            "editor_result": editor_result,
        }
    else:
        result = note_module.post_draft_to_note(
            markdown,
            run_ogp=not args.no_ogp,
            run_top_image=not args.no_top_image,
            insert_toc=not args.no_toc,
            publish=True,
            dry_run_publish=args.dry_run_publish,
        )

    result_path = Path(args.result_json)
    _write_result_json(result_path, result)

    if result.get("success"):
        published_url = result.get("published_url") or result.get("url", "")
        file_id = os.getenv("FILE_ID", "")
        _save_post_url_to_github_var(file_id, published_url)
        label = "公開投稿dry-run" if args.dry_run_publish else "公開投稿"
        print(f"\n🎉 {label}成功！")
        print(f"   タイトル: {result.get('title', '')}")
        print(f"   下書きURL: {result.get('url', '')}")
        print(f"   公開後URL: {published_url}")
        return 0

    print("\n❌ 公開投稿失敗")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
