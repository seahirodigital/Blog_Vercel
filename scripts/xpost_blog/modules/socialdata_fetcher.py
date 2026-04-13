import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from .onedrive_writer import extract_post_id, normalize_x_url

SOCIALDATA_API_BASE = "https://api.socialdata.tools"
SOCIALDATA_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def _request_json(path: str, api_key: str) -> tuple[int, Any]:
    response = requests.get(
        f"{SOCIALDATA_API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "User-Agent": SOCIALDATA_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=90,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return response.status_code, payload


def _unwrap_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("data", "tweet", "result", "article"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
    return payload if isinstance(payload, dict) else {}


def _nested_get(payload: Any, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = payload
        valid = True
        for key in path:
            if not isinstance(current, dict) or key not in current:
                valid = False
                break
            current = current[key]
        if valid and current not in (None, ""):
            return current
    return ""


def _entity_map(article_payload: dict[str, Any]) -> dict[str, Any]:
    content_state = _nested_get(article_payload, ("content_state",), ("contentState",))
    if isinstance(content_state, dict):
        entity_map = content_state.get("entityMap") or {}
        if isinstance(entity_map, dict):
            return entity_map
    entity_map = article_payload.get("entityMap") or {}
    return entity_map if isinstance(entity_map, dict) else {}


def _draftjs_to_markdown(article_payload: dict[str, Any]) -> str:
    content_state = _nested_get(article_payload, ("content_state",), ("contentState",))
    if not isinstance(content_state, dict):
        return ""

    blocks = content_state.get("blocks") or []
    if not isinstance(blocks, list):
        return ""

    entity_map = _entity_map(article_payload)
    lines: list[str] = []
    ordered_index = 0

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "unstyled")
        text = str(block.get("text") or "").strip()

        if block_type == "ordered-list-item":
            ordered_index += 1
        else:
            ordered_index = 0

        if block_type == "header-one":
            lines.append(f"# {text}" if text else "# 見出し")
        elif block_type == "header-two":
            lines.append(f"## {text}" if text else "## 見出し")
        elif block_type == "header-three":
            lines.append(f"### {text}" if text else "### 見出し")
        elif block_type == "unordered-list-item":
            lines.append(f"- {text}" if text else "- ")
        elif block_type == "ordered-list-item":
            lines.append(f"{ordered_index}. {text}" if text else f"{ordered_index}. ")
        elif block_type == "blockquote":
            lines.append(f"> {text}" if text else "> ")
        elif text:
            lines.append(text)
        else:
            lines.append("")

        for entity_range in block.get("entityRanges") or []:
            key = str(entity_range.get("key", ""))
            entity = entity_map.get(key)
            if not isinstance(entity, dict):
                continue
            if str(entity.get("type") or "").upper() != "IMAGE":
                continue
            data = entity.get("data") or {}
            image_url = data.get("url") or data.get("src") or data.get("image_url") or ""
            if image_url:
                lines.append(f"![image]({image_url})")

    return "\n\n".join(line for line in lines if line is not None).strip()


def _collect_urls(tweet_payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    entities = _nested_get(tweet_payload, ("entities",), ("legacy", "entities"))
    if isinstance(entities, dict):
        for entry in entities.get("urls") or []:
            if not isinstance(entry, dict):
                continue
            expanded = entry.get("expanded_url") or entry.get("expandedUrl") or entry.get("url") or ""
            if expanded:
                urls.append(str(expanded))
    return urls


def _tweet_text(tweet_payload: dict[str, Any]) -> str:
    return str(
        _nested_get(
            tweet_payload,
            ("full_text",),
            ("legacy", "full_text"),
            ("text",),
            ("legacy", "text"),
        )
        or ""
    ).strip()


def _extract_author(tweet_payload: dict[str, Any]) -> tuple[str, str]:
    author = _nested_get(tweet_payload, ("user",), ("author",), ("core", "user_results", "result", "legacy"))
    if isinstance(author, dict):
        name = author.get("name") or author.get("screen_name") or author.get("screenName") or ""
        screen_name = author.get("screen_name") or author.get("screenName") or author.get("username") or ""
        return str(name), str(screen_name)
    return "", ""


def _build_source_title(tweet_payload: dict[str, Any], article_payload: dict[str, Any], post_url: str) -> str:
    article_title = _nested_get(article_payload, ("title",), ("headline",))
    if article_title:
        return str(article_title)

    tweet_text = _tweet_text(tweet_payload)
    if tweet_text:
        clean = re.sub(r"\s+", " ", tweet_text).strip()
        return clean[:48]

    post_id = extract_post_id(post_url)
    return f"X投稿_{post_id}" if post_id else "X投稿"


def _build_source_markdown(
    post_url: str,
    tweet_payload: dict[str, Any],
    article_payload: dict[str, Any],
    author_name: str,
    author_screen_name: str,
    published_at: str,
) -> tuple[str, str]:
    tweet_text = _tweet_text(tweet_payload)
    article_markdown = _draftjs_to_markdown(article_payload)
    lines = [f"# 元投稿ソース: {_build_source_title(tweet_payload, article_payload, post_url)}", ""]
    lines.append(f"- X URL: {normalize_x_url(post_url)}")
    if author_name:
        lines.append(f"- 投稿者: {author_name}")
    if author_screen_name:
        lines.append(f"- アカウント: @{author_screen_name}")
    if published_at:
        lines.append(f"- 投稿日時: {published_at}")
    lines.append("")

    if tweet_text:
        lines.append("## ポスト本文")
        lines.append("")
        lines.append(tweet_text)
        lines.append("")

    expanded_urls = [url for url in _collect_urls(tweet_payload) if url != post_url]
    if expanded_urls:
        lines.append("## 展開URL")
        lines.append("")
        for url in expanded_urls:
            lines.append(f"- {url}")
        lines.append("")

    if article_markdown:
        lines.append("## Article 本文")
        lines.append("")
        lines.append(article_markdown)
        lines.append("")

    plain_text = article_markdown or tweet_text or ""
    return "\n".join(lines).strip() + "\n", plain_text.strip()


def fetch_post_bundle(post_url: str, api_key: str) -> dict[str, Any]:
    normalized_post_url = normalize_x_url(post_url)
    tweet_id = extract_post_id(normalized_post_url)
    if not tweet_id:
        return {
            "ok": False,
            "error": "X URL から投稿IDを抽出できませんでした",
            "httpStatus": 400,
        }

    tweet_status, tweet_payload_raw = _request_json(f"/twitter/tweets/{tweet_id}", api_key)
    if tweet_status >= 400:
        return {
            "ok": False,
            "error": f"SocialData tweet 取得失敗: HTTP {tweet_status}",
            "httpStatus": tweet_status,
            "payload": tweet_payload_raw,
        }

    tweet_payload = _unwrap_payload(tweet_payload_raw)
    article_status = 0
    article_payload_raw: Any = {}
    article_payload: dict[str, Any] = {}

    should_fetch_article = "/i/article/" in normalized_post_url or any(
        "/i/article/" in url for url in _collect_urls(tweet_payload)
    ) or bool(tweet_payload.get("article"))

    if should_fetch_article:
        article_status, article_payload_raw = _request_json(f"/twitter/article/{tweet_id}", api_key)
        if article_status < 400:
            article_payload = _unwrap_payload(article_payload_raw)

    author_name, author_screen_name = _extract_author(tweet_payload)
    published_at = str(
        _nested_get(tweet_payload, ("created_at",), ("legacy", "created_at"))
        or _nested_get(article_payload, ("created_at",), ("published_at",))
        or ""
    )

    source_title = _build_source_title(tweet_payload, article_payload, normalized_post_url)
    source_markdown, plain_text = _build_source_markdown(
        normalized_post_url,
        tweet_payload,
        article_payload,
        author_name,
        author_screen_name,
        published_at,
    )

    source_excerpt = re.sub(r"\s+", " ", plain_text).strip()[:280]
    return {
        "ok": True,
        "post_url": normalized_post_url,
        "normalized_post_url": normalized_post_url,
        "tweet_id": tweet_id,
        "article_id": str(article_payload.get("id", "") or ""),
        "published_at": published_at,
        "title": source_title,
        "source_title": source_title,
        "author_name": author_name,
        "author_screen_name": author_screen_name,
        "favorite_count": _nested_get(tweet_payload, ("favorite_count",), ("legacy", "favorite_count")) or 0,
        "repost_count": _nested_get(tweet_payload, ("retweet_count",), ("legacy", "retweet_count")) or 0,
        "reply_count": _nested_get(tweet_payload, ("reply_count",), ("legacy", "reply_count")) or 0,
        "quote_count": _nested_get(tweet_payload, ("quote_count",), ("legacy", "quote_count")) or 0,
        "bookmark_count": _nested_get(tweet_payload, ("bookmark_count",), ("legacy", "bookmark_count")) or 0,
        "view_count": _nested_get(tweet_payload, ("view_count",), ("views", "count")) or 0,
        "is_article": bool(article_payload),
        "source_markdown": source_markdown,
        "plain_text": plain_text,
        "source_excerpt": source_excerpt,
        "tweet_payload": tweet_payload,
        "article_payload": article_payload,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "article_http_status": article_status,
    }