#!/usr/bin/env python3
"""info-viewer 専用の note 投稿アダプタ。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
NOTE_DRAFT_SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "pipeline"
    / "prompts"
    / "05-draft-manager"
    / "note_draft_poster.py"
)
AFFILIATE_FILE = REPO_ROOT / "info_viewer" / "affiliate_links.txt"
DEFAULT_RESULT_JSON = Path("/tmp/info_viewer_note_result.json")
DEFAULT_VERCEL_URL = "https://blog-vercel-dun.vercel.app"
GITHUB_API = "https://api.github.com"
GITHUB_REPO_OWNER = "seahirodigital"
GITHUB_REPO_NAME = "Blog_Vercel"

DISCLOSURE_PREFIX = "Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています"
DISCLOSURE_TEXT = (
    "Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。"
    "文章にはAIの整形・編集が含まれます。"
)


def _load_note_draft_module():
    spec = importlib.util.spec_from_file_location("info_viewer_note_draft_runtime", NOTE_DRAFT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"note下書きモジュールを読み込めません: {NOTE_DRAFT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["info_viewer_note_draft_runtime"] = module
    spec.loader.exec_module(module)
    return module


def _strip_frontmatter(markdown: str) -> str:
    return re.sub(r"\A---\s*\n[\s\S]*?\n---\s*\n?", "", str(markdown or ""), count=1)


def _strip_apify_transcript(markdown: str) -> tuple[str, bool]:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(re.finditer(r"(?im)^##\s*Apify\s+取得文字起こし\s*$", text))
    if not matches:
        return text, False
    return text[: matches[-1].start()].rstrip() + "\n", True


def _read_affiliate_memo(memo_number: int) -> str:
    if not AFFILIATE_FILE.exists():
        print(f"   [警告] info-viewer用アフィリエイトファイルが見つかりません: {AFFILIATE_FILE}")
        return ""

    raw = AFFILIATE_FILE.read_text(encoding="utf-8")
    parts = re.split(r"===MEMO(\d+)===", raw)
    if len(parts) <= 1:
        return raw.strip()

    for index in range(1, len(parts), 2):
        if int(parts[index]) != memo_number:
            continue
        body = (parts[index + 1] if index + 1 < len(parts) else "").strip()
        if "---" in body:
            _meta, body = body.split("---", 1)
        return body.strip()
    return ""


def _split_affiliate_blocks(memo_content: str) -> list[str]:
    blocks = [
        block.strip()
        for block in re.split(r"(?=▼)", memo_content)
        if block.strip() and block.strip().startswith("▼")
    ]
    return blocks or ([memo_content.strip()] if memo_content.strip() else [])


def _ensure_disclosure_after_title(markdown: str) -> str:
    if DISCLOSURE_PREFIX in markdown:
        return markdown

    lines = markdown.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return "".join(lines[: index + 1] + ["\n", DISCLOSURE_TEXT + "\n", "\n"] + lines[index + 1 :])

    for index, line in enumerate(lines):
        if line.strip():
            return "".join(lines[: index + 1] + ["\n", DISCLOSURE_TEXT + "\n", "\n"] + lines[index + 1 :])

    return f"{DISCLOSURE_TEXT}\n"


def _insert_affiliate_after_each_h2(markdown: str, memo_number: int = 1) -> tuple[str, int]:
    memo_content = _read_affiliate_memo(memo_number)
    blocks = _split_affiliate_blocks(memo_content)
    if not blocks:
        print(f"   [警告] MEMO{memo_number}が空のため、アフィリエイト挿入をスキップします")
        return markdown, 0

    lines = markdown.splitlines(keepends=True)
    h2_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith("## ") and not line.startswith("### ")
    ]
    if not h2_indices:
        print("   [警告] H2が見つからないため、アフィリエイト挿入をスキップします")
        return markdown, 0

    insertions: list[tuple[int, str]] = []
    for h2_order, h2_index in enumerate(h2_indices):
        next_h2_index = h2_indices[h2_order + 1] if h2_order + 1 < len(h2_indices) else len(lines)
        insert_index = next_h2_index
        while insert_index > h2_index + 1 and not lines[insert_index - 1].strip():
            insert_index -= 1
        block = blocks[h2_order % len(blocks)]
        insertions.append((insert_index, f"\n\n{block}\n\n"))

    for insert_index, block in sorted(insertions, key=lambda item: item[0], reverse=True):
        lines = lines[:insert_index] + [block] + lines[insert_index:]

    print(f"   [OK] H2章末アフィリエイトを挿入しました: {len(insertions)}箇所")
    return "".join(lines), len(insertions)


def _clean_markdown_image_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value.split()[0].strip("'\"") if value else ""


def _extract_first_image_source(markdown: str) -> str:
    image_match = re.search(r"!\[[^\]]*]\(([^)]+)\)", markdown)
    if image_match:
        return _clean_markdown_image_url(image_match.group(1))

    html_match = re.search(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", markdown, flags=re.IGNORECASE)
    if html_match:
        return html_match.group(1).strip()

    return ""


def _suffix_from_mime_or_url(mime_type: str, source_url: str) -> str:
    suffix = mimetypes.guess_extension((mime_type or "").split(";")[0].strip()) or ""
    if suffix:
        return suffix
    parsed_suffix = Path(urlparse(source_url).path).suffix
    return parsed_suffix if re.match(r"^\.[A-Za-z0-9]{2,8}$", parsed_suffix) else ".png"


def _write_temp_image(data: bytes, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix="info_viewer_note_top_image_",
        suffix=suffix,
        delete=False,
    )
    with handle:
        handle.write(data)
    return Path(handle.name)


def _download_first_image(markdown: str, vercel_url: str) -> tuple[Path | None, str]:
    source = _extract_first_image_source(markdown)
    if not source:
        print("   [情報] 記事内に画像がないため、noteサムネイルは設定しません")
        return None, ""

    if source.startswith("blob:"):
        print("   [警告] blob画像はGitHub Actionsから参照できないため、noteサムネイルをスキップします")
        return None, source

    data_match = re.match(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.+)$", source, flags=re.DOTALL)
    if data_match:
        mime_type, encoded = data_match.groups()
        try:
            return _write_temp_image(base64.b64decode(encoded), _suffix_from_mime_or_url(mime_type, "")), source
        except Exception as exc:
            print(f"   [警告] data画像の復元に失敗しました: {exc}")
            return None, source

    resolved_url = source
    if source.startswith("/"):
        resolved_url = urljoin(vercel_url.rstrip("/") + "/", source.lstrip("/"))
    elif not re.match(r"^https?://", source, flags=re.IGNORECASE):
        resolved_url = urljoin(vercel_url.rstrip("/") + "/", source)

    try:
        response = requests.get(
            resolved_url,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if content_type and not content_type.lower().startswith("image/"):
            print(f"   [警告] 先頭画像URLのContent-Typeが画像ではありません: {content_type}")
            return None, resolved_url
        return _write_temp_image(response.content, _suffix_from_mime_or_url(content_type, resolved_url)), resolved_url
    except Exception as exc:
        print(f"   [警告] 先頭画像の取得に失敗しました: {resolved_url} / {exc}")
        return None, resolved_url


def _prepare_markdown(markdown: str, memo_number: int) -> tuple[str, dict]:
    body = _strip_frontmatter(markdown)
    body, removed_apify = _strip_apify_transcript(body)
    body = _ensure_disclosure_after_title(body)
    body, affiliate_insertions = _insert_affiliate_after_each_h2(body, memo_number=memo_number)
    return body.strip() + "\n", {
        "removed_apify_transcript": removed_apify,
        "affiliate_insertions": affiliate_insertions,
        "memo_number": memo_number,
    }


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
    payload = {"name": var_name, "value": url}
    check = requests.get(f"{api_base}/actions/variables/{var_name}", headers=headers, timeout=30)
    if check.status_code == 200:
        response = requests.patch(f"{api_base}/actions/variables/{var_name}", headers=headers, json=payload, timeout=30)
    else:
        response = requests.post(f"{api_base}/actions/variables", headers=headers, json=payload, timeout=30)

    if response.status_code in (200, 201, 204):
        print(f"   [OK] GitHub Variable {var_name} を保存しました")
    else:
        print(f"   [警告] 公開URLのVariable保存失敗 ({response.status_code}): {response.text[:150]}")


def _write_result_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   [情報] 結果JSONを書き出しました: {path}")


def _env_memo_number() -> int:
    try:
        value = int(os.getenv("INFO_VIEWER_AFFILIATE_MEMO", "1"))
    except ValueError:
        return 1
    return max(1, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="info-viewer記事をnoteへ投稿する")
    parser.add_argument("file", help="Markdownファイルの絶対パス")
    parser.add_argument("--publish", action="store_true", help="下書き作成後に公開投稿まで進める")
    parser.add_argument("--dry-run-publish", action="store_true", help="公開画面まで進めるが、最後の投稿ボタンは押さない")
    parser.add_argument("--no-ogp", action="store_true", help="OGP展開をスキップする")
    parser.add_argument("--no-top-image", action="store_true", help="記事内先頭画像のサムネイル設定をスキップする")
    parser.add_argument("--no-toc", action="store_true", help="目次挿入をスキップする")
    parser.add_argument("--memo", type=int, default=_env_memo_number(), help="使用するアフィリエイトMEMO番号")
    parser.add_argument("--vercel-url", default=os.getenv("VERCEL_URL", DEFAULT_VERCEL_URL), help="相対画像URLの解決に使うURL")
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON), help="結果JSONを書き出す絶対パス")
    args = parser.parse_args()

    source_markdown = Path(args.file).read_text(encoding="utf-8")
    prepared_markdown, preprocess = _prepare_markdown(source_markdown, memo_number=max(1, args.memo))
    top_image_path, top_image_source = (None, "")
    if not args.no_top_image:
        top_image_path, top_image_source = _download_first_image(prepared_markdown, args.vercel_url)

    note_module = _load_note_draft_module()
    result = note_module.post_draft_to_note(
        prepared_markdown,
        run_ogp=not args.no_ogp,
        run_top_image=bool(top_image_path),
        insert_toc=not args.no_toc,
        publish=args.publish or args.dry_run_publish,
        dry_run_publish=args.dry_run_publish,
        top_image_path=str(top_image_path) if top_image_path else "",
    )
    result["info_viewer_preprocess"] = {
        **preprocess,
        "top_image_source": top_image_source,
        "top_image_path": str(top_image_path) if top_image_path else "",
    }

    result_path = Path(args.result_json)
    _write_result_json(result_path, result)

    file_id = os.getenv("FILE_ID", "")
    if result.get("success") and file_id and result.get("url"):
        note_module._save_draft_url_to_github_var(file_id, result["url"])
    if result.get("success") and file_id and result.get("published_url"):
        _save_post_url_to_github_var(file_id, result["published_url"])

    if result.get("success"):
        label = "公開投稿" if (args.publish or args.dry_run_publish) else "下書き投稿"
        print(f"\n[OK] info-viewer note {label} が完了しました")
        print(f"   タイトル: {result.get('title', '')}")
        print(f"   下書きURL: {result.get('url', '')}")
        if result.get("published_url"):
            print(f"   公開後URL: {result.get('published_url', '')}")
        return 0

    print("\n[ERROR] info-viewer note 投稿に失敗しました")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
