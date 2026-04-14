import re
from datetime import datetime
from typing import Any

import requests

from .onedrive_writer import extract_post_id, normalize_x_url

APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_XPOST_ACTOR = "fastdata/twitter-scraper"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MEMORY_MB = 1024


def _read_response_text(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def _actor_run_url(actor_name: str) -> str:
    normalized = str(actor_name or DEFAULT_XPOST_ACTOR).strip() or DEFAULT_XPOST_ACTOR
    return f"{APIFY_BASE_URL}/acts/{normalized.replace('/', '~')}/run-sync-get-dataset-items"


def _input_payload(actor_name: str, lookup_url: str) -> dict[str, Any]:
    normalized = str(actor_name or DEFAULT_XPOST_ACTOR).strip() or DEFAULT_XPOST_ACTOR
    if normalized == "fastdata/twitter-scraper":
        return {
            "tweetUrls": [lookup_url],
            "mode": "tweets",
            "maxTweets": 1,
            "includeReplies": False,
            "includeRetweets": True,
            "deduplicate": True,
        }

    return {
        "startUrls": [lookup_url],
        "maxItems": 1,
    }


def _first_value(payload: Any, *keys: str) -> Any:
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def _extract_text(item: dict[str, Any]) -> str:
    direct = _first_value(item, "text", "full_text", "fullText", "tweetText", "tweet_text")
    if direct:
        return str(direct).strip()

    tweet = item.get("tweet")
    if isinstance(tweet, dict):
        nested = _first_value(tweet, "text", "full_text", "fullText")
        if nested:
            return str(nested).strip()
    return ""


def _extract_author(item: dict[str, Any]) -> tuple[str, str]:
    author = item.get("author")
    if isinstance(author, dict):
        display_name = _first_value(author, "displayName", "name", "fullName")
        username = _first_value(author, "username", "userName", "screen_name", "screenName", "handle")
        return str(display_name).strip(), str(username).strip().lstrip("@")

    user_name = _first_value(item, "userName", "username", "screenName", "screen_name")
    name = _first_value(item, "displayName", "authorName", "name")
    return str(name).strip(), str(user_name).strip().lstrip("@")


def _extract_media_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    media = item.get("media")
    if isinstance(media, list):
        for entry in media:
            if isinstance(entry, str) and entry.strip():
                urls.append(entry.strip())
                continue
            if not isinstance(entry, dict):
                continue
            for key in ("mediaUrl", "url", "expandedUrl", "downloadUrl"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    urls.append(value.strip())
                    break
    return urls


def _extract_urls(item: dict[str, Any]) -> list[str]:
    found: list[str] = []

    for key in ("urls", "expandedUrls"):
        value = item.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    found.append(entry.strip())
                    continue
                if not isinstance(entry, dict):
                    continue
                for nested_key in ("expanded_url", "expandedUrl", "url", "destUrl"):
                    nested_value = entry.get(nested_key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        found.append(nested_value.strip())
                        break

    entities = item.get("entities")
    if isinstance(entities, dict):
        for entry in entities.get("urls") or []:
            if not isinstance(entry, dict):
                continue
            expanded = _first_value(entry, "expanded_url", "expandedUrl", "url")
            if expanded:
                found.append(str(expanded).strip())

    card = item.get("card")
    if isinstance(card, dict):
        for key in ("url", "destinationUrl", "expandedUrl"):
            value = card.get(key)
            if isinstance(value, str) and value.strip():
                found.append(value.strip())

    unique: list[str] = []
    seen = set()
    for value in found:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _extract_created_at(item: dict[str, Any]) -> str:
    created_at = _first_value(item, "createdAt", "created_at", "date")
    if not created_at:
        return ""
    return str(created_at).strip()


def _build_source_title(post_text: str, article_urls: list[str], post_url: str) -> str:
    if article_urls:
        return f"X記事付き投稿_{extract_post_id(post_url) or 'article'}"
    clean = re.sub(r"\s+", " ", str(post_text or "")).strip()
    if clean:
        return clean[:48]
    post_id = extract_post_id(post_url)
    return f"X投稿_{post_id}" if post_id else "X投稿"


def _build_source_markdown(
    *,
    post_url: str,
    source_title: str,
    post_text: str,
    author_name: str,
    author_screen_name: str,
    published_at: str,
    expanded_urls: list[str],
    media_urls: list[str],
    actor_name: str,
    requires_article_fallback: bool,
) -> tuple[str, str]:
    lines = [f"# 元投稿ソース: {source_title}", ""]
    lines.append(f"- X URL: {normalize_x_url(post_url)}")
    lines.append(f"- 取得元: Apify ({actor_name})")
    if author_name:
        lines.append(f"- 投稿者: {author_name}")
    if author_screen_name:
        lines.append(f"- アカウント: @{author_screen_name}")
    if published_at:
        lines.append(f"- 投稿日時: {published_at}")
    if requires_article_fallback:
        lines.append("- 補足: X記事本文は Apify 単独では未取得のため、必要に応じて SocialData fallback 対象")
    lines.append("")

    if post_text:
        lines.append("## ポスト本文")
        lines.append("")
        lines.append(post_text)
        lines.append("")

    external_urls = [url for url in expanded_urls if normalize_x_url(url) != normalize_x_url(post_url)]
    if external_urls:
        lines.append("## 展開URL")
        lines.append("")
        for url in external_urls:
            lines.append(f"- {url}")
        lines.append("")

    if media_urls:
        lines.append("## メディアURL")
        lines.append("")
        for url in media_urls:
            lines.append(f"- {url}")
        lines.append("")

    plain_text = post_text.strip()
    return "\n".join(lines).strip() + "\n", plain_text


def _select_best_item(items: list[Any], normalized_post_url: str) -> dict[str, Any]:
    normalized_post_id = extract_post_id(normalized_post_url)
    fallback: dict[str, Any] | None = None

    for entry in items:
        if not isinstance(entry, dict):
            continue
        if fallback is None:
            fallback = entry
        entry_url = normalize_x_url(str(_first_value(entry, "url", "tweetUrl") or ""))
        entry_id = str(_first_value(entry, "id", "tweetId") or "")
        if entry_url and entry_url == normalized_post_url:
            return entry
        if normalized_post_id and entry_id == normalized_post_id:
            return entry
    return fallback or {}


def fetch_post_bundle(
    post_url: str,
    api_key: str,
    actor_name: str = DEFAULT_XPOST_ACTOR,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> dict[str, Any]:
    normalized_post_url = normalize_x_url(post_url)
    tweet_id = extract_post_id(normalized_post_url)
    if not tweet_id:
        return {
            "ok": False,
            "error": "X URL から投稿IDを抽出できませんでした",
            "httpStatus": 400,
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
        }

    lookup_url = normalized_post_url
    direct_article_requested = "/i/article/" in normalized_post_url
    if direct_article_requested:
        lookup_url = f"https://x.com/i/status/{tweet_id}"

    run_url = _actor_run_url(actor_name)
    payload = _input_payload(actor_name, lookup_url)
    params = {
        "token": api_key,
        "timeout": max(30, int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS)),
        "memory": max(256, int(memory_mb or DEFAULT_MEMORY_MB)),
    }

    try:
        response = requests.post(run_url, json=payload, params=params, timeout=max(120, params["timeout"] + 30))
        status_code = response.status_code
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as error:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        body = _read_response_text(response)[:400]
        detail = str(error).strip() or "Apify リクエストに失敗しました"
        if status_code and f"{status_code}" not in detail:
            detail = f"HTTP {status_code}: {detail}"
        if body and body not in detail:
            detail = f"{detail} | {body}"
        return {
            "ok": False,
            "error": detail,
            "httpStatus": status_code,
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
        }
    except ValueError as error:
        return {
            "ok": False,
            "error": f"Apify 応答の JSON 解析に失敗しました: {error}",
            "httpStatus": getattr(locals().get("response"), "status_code", None),
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
        }

    if not isinstance(data, list) or not data:
        return {
            "ok": False,
            "error": "Apify のデータセット結果が空でした",
            "httpStatus": status_code,
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
            "itemCount": len(data) if isinstance(data, list) else 0,
        }

    item = _select_best_item(data, normalize_x_url(lookup_url))
    if not item:
        return {
            "ok": False,
            "error": "Apify 応答から対象投稿を特定できませんでした",
            "httpStatus": status_code,
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
            "itemCount": len(data),
        }

    post_text = _extract_text(item)
    if not post_text:
        return {
            "ok": False,
            "error": "Apify 応答に本文がありませんでした",
            "httpStatus": status_code,
            "provider": "apify",
            "providerLabel": "Apify",
            "providerDetail": f"Apify ({actor_name})",
            "itemCount": len(data),
        }

    author_name, author_screen_name = _extract_author(item)
    published_at = _extract_created_at(item)
    expanded_urls = _extract_urls(item)
    media_urls = _extract_media_urls(item)
    article_urls = [url for url in expanded_urls if "/i/article/" in str(url or "")]
    requires_article_fallback = bool(direct_article_requested or article_urls)
    source_title = _build_source_title(post_text, article_urls, normalized_post_url)
    source_markdown, plain_text = _build_source_markdown(
        post_url=normalized_post_url,
        source_title=source_title,
        post_text=post_text,
        author_name=author_name,
        author_screen_name=author_screen_name,
        published_at=published_at,
        expanded_urls=expanded_urls,
        media_urls=media_urls,
        actor_name=actor_name,
        requires_article_fallback=requires_article_fallback,
    )

    article_id = ""
    if article_urls:
        article_id = extract_post_id(article_urls[0])
    elif direct_article_requested:
        article_id = tweet_id

    return {
        "ok": True,
        "post_url": normalized_post_url,
        "normalized_post_url": normalized_post_url,
        "tweet_id": str(_first_value(item, "id", "tweetId") or tweet_id),
        "article_id": article_id,
        "published_at": published_at,
        "title": source_title,
        "source_title": source_title,
        "author_name": author_name,
        "author_screen_name": author_screen_name,
        "favorite_count": _as_int(_first_value(item, "likeCount", "favorite_count", "favoriteCount")),
        "repost_count": _as_int(_first_value(item, "retweetCount", "repost_count", "retweet_count")),
        "reply_count": _as_int(_first_value(item, "replyCount", "reply_count")),
        "quote_count": _as_int(_first_value(item, "quoteCount", "quote_count")),
        "bookmark_count": _as_int(_first_value(item, "bookmarkCount", "bookmark_count")),
        "view_count": _as_int(_first_value(item, "viewCount", "view_count")),
        "is_article": bool(direct_article_requested or article_urls),
        "source_markdown": source_markdown,
        "plain_text": plain_text,
        "source_excerpt": re.sub(r"\s+", " ", plain_text).strip()[:280],
        "tweet_payload": item,
        "article_payload": {},
        "expanded_urls": expanded_urls,
        "media_urls": media_urls,
        "article_urls": article_urls,
        "requires_article_fallback": requires_article_fallback,
        "lookup_post_url": lookup_url,
        "httpStatus": status_code,
        "itemCount": len(data),
        "provider": "apify",
        "providerLabel": "Apify",
        "providerDetail": f"Apify ({actor_name})",
        "providerActor": actor_name,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
