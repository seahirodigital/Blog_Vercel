"""既存Info Viewer記事へMoomoo検索リンクだけを再適用する。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = PROJECT_ROOT / "info_viewer_site" / "content" / "articles"
MODULE_DIR = Path(__file__).resolve().parent / "modules"

# Gemini実行環境を必要としない既存記事の再リンク処理では、必要な二つのモジュールだけを読む。
sys.path.insert(0, str(MODULE_DIR))
import jp_stock_linker  # noqa: E402
import onedrive_writer  # noqa: E402


def _split_frontmatter(document: str) -> tuple[str, str]:
    match = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", document, flags=re.S)
    if not match:
        return "", document
    return match.group(1), match.group(2)


def _target_article(article_id: str) -> dict:
    source = CONTENT_DIR / f"{article_id}.md"
    if not source.is_file():
        raise FileNotFoundError(f"対象記事が見つかりません: {source}")

    metadata, _ = onedrive_writer.parse_frontmatter(source.read_text(encoding="utf-8-sig"))
    video_url = onedrive_writer.normalize_youtube_url(metadata.get("video_url", ""))
    if not video_url:
        raise ValueError("対象記事の動画URLを確認できません")

    matched = [
        article
        for article in onedrive_writer.list_saved_articles()
        if onedrive_writer.normalize_youtube_url(article.get("youtubeUrl", "")) == video_url
    ]
    if len(matched) != 1:
        raise ValueError(f"OneDrive上の対象記事を一意に特定できません: {len(matched)}件")
    return {"source": source, "article": matched[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description="既存記事へMoomoo検索リンクを再適用")
    parser.add_argument("--article-id", required=True, help="Info Viewerの記事ID")
    parser.add_argument("--apply", action="store_true", help="OneDriveと静的Markdownへ反映する")
    args = parser.parse_args()

    load_dotenv()
    target = _target_article(args.article_id)
    source: Path = target["source"]
    original = source.read_text(encoding="utf-8-sig")
    frontmatter, body = _split_frontmatter(original)
    result = jp_stock_linker.link_gemini_markdown(body)
    if result.error:
        raise RuntimeError(f"名称辞書を取得できません: {result.error}")

    updated = frontmatter + result.markdown
    company_links = {
        name: f"[{name}](ftmm://search?keyword={name})" in updated
        for name in ("Google", "Amazon", "SpaceX")
    }
    print(f"対象記事: {args.article_id}")
    print(f"Moomoo検索リンク付与: {result.linked_count}件")
    print("Google/Amazon/SpaceX: " + "/".join("有" if company_links[name] else "無" for name in company_links))

    if not args.apply:
        return 0
    if updated == original:
        print("変更対象はありません")
        return 0

    onedrive_writer.update_item_text(target["article"]["fileId"], updated)
    source.write_text(updated, encoding="utf-8", newline="\n")
    print("OneDrive正本と静的Markdownを更新しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
