from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests


APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_ACTOR = "scraper-engine/amazon-product-details-scraper"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MEMORY_MB = 2048
DEFAULT_MAX_COMMENTS = 20
SHORT_URL_HOSTS = {"amzn.asia", "amzn.to"}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/product/|asin=)([A-Z0-9]{10})", re.I)
RAW_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.I)


def _actor_run_url(actor_name: str) -> str:
    normalized = str(actor_name or DEFAULT_ACTOR).strip() or DEFAULT_ACTOR
    return f"{APIFY_BASE_URL}/acts/{normalized.replace('/', '~')}/run-sync-get-dataset-items"


def _read_response_text(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def _sanitize_error_text(text: Any, api_key: str = "") -> str:
    sanitized = str(text or "")
    if api_key:
        sanitized = sanitized.replace(api_key, "<APIFY_API_KEY>")
    return re.sub(r"([?&]token=)[^&\s]+", r"\1<redacted>", sanitized)


def _domain_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"amzn.asia", "amzn.to"}:
        return "amazon.co.jp"
    return host or "amazon.co.jp"


def extract_asin(value: str) -> str:
    text = str(value or "").strip()
    if RAW_ASIN_RE.match(text):
        return text.upper()
    match = ASIN_RE.search(text)
    return match.group(1).upper() if match else ""


def normalize_product_url(value: str) -> str:
    text = str(value or "").strip()
    asin = extract_asin(text)
    if asin:
        domain = _domain_from_url(text) if "://" in text else "amazon.co.jp"
        if domain in {"amzn.asia", "amzn.to"}:
            domain = "amazon.co.jp"
        return f"https://www.{domain}/dp/{asin}"
    return text


def resolve_product_url(value: str) -> str:
    normalized_url = normalize_product_url(value)
    host = urlparse(normalized_url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if extract_asin(normalized_url) or host not in SHORT_URL_HOSTS:
        return normalized_url

    try:
        response = requests.get(
            normalized_url,
            allow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=15,
        )
        final_url = normalize_product_url(response.url)
        if extract_asin(final_url):
            return final_url
    except requests.RequestException as error:
        print(f"   Amazon short URL resolve warning: {error}")

    return normalized_url


def _as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return json.dumps(value, ensure_ascii=False)


def _iter_kv_list(value: Any) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item_value in value.items():
            rows.append((str(key).strip(), _as_text(item_value)))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                key = item.get("name") or item.get("key") or item.get("label") or item.get("title")
                item_value = item.get("value") or item.get("text") or item.get("description")
                if key or item_value:
                    rows.append((_as_text(key), _as_text(item_value)))
            elif item:
                rows.append(("", _as_text(item)))
    return [(k, v) for k, v in rows if k or v]


def _add_section(parts: list[str], heading: str, body: Any):
    if body in (None, "", [], {}):
        return

    if isinstance(body, list):
        lines = []
        for item in body:
            text = _as_text(item)
            if text:
                lines.append(f"- {text}")
        content = "\n".join(lines).strip()
    elif isinstance(body, dict):
        lines = []
        for key, value in body.items():
            text = _as_text(value)
            if text:
                lines.append(f"- {key}: {text}")
        content = "\n".join(lines).strip()
    else:
        content = _as_text(body)

    if content:
        parts.append(f"## {heading}\n{content}")


def _format_reviews(item: dict[str, Any]) -> list[str]:
    reviews = item.get("reviews") or item.get("productPageReviews") or []
    if not isinstance(reviews, list):
        return []

    lines: list[str] = []
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, dict):
            text = _as_text(review)
            if text:
                lines.append(f"{index}. {text}")
            continue

        title = _as_text(
            review.get("title")
            or review.get("reviewTitle")
            or review.get("headline")
        )
        rating = _as_text(
            review.get("rating")
            or review.get("ratingScore")
            or review.get("stars")
        )
        date = _as_text(review.get("date") or review.get("reviewDate") or review.get("reviewedIn"))
        text = _as_text(
            review.get("text")
            or review.get("reviewDescription")
            or review.get("body")
            or review.get("description")
        )
        variant = _as_text(review.get("variant") or review.get("variationList"))
        line_parts = [part for part in (title, rating, date, variant, text) if part]
        if line_parts:
            lines.append(f"{index}. " + " / ".join(line_parts))
    return lines


def build_transcript_from_item(item: dict[str, Any], source_url: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    error = item.get("error")
    status = str(item.get("statusMessage") or item.get("status") or "").lower()
    if error or status in {"not_found", "failed", "error"}:
        print(f"   Amazon Apify item error: {error or status}")
        return None

    title = _as_text(
        item.get("title")
        or item.get("productTitle")
        or item.get("productName")
        or item.get("name")
        or "Amazon product"
    )

    metadata_rows = {
        "URL": item.get("url") or source_url,
        "ASIN": item.get("asin") or item.get("originalAsin"),
        "Brand": item.get("brand") or item.get("manufacturer"),
        "Price": item.get("price") or item.get("retailPrice"),
        "List price": item.get("listPrice") or item.get("referencePrice"),
        "Rating": item.get("stars") or item.get("rating") or item.get("productRating"),
        "Review count": item.get("reviewsCount") or item.get("reviewCount") or item.get("countReview"),
        "Availability": item.get("availability") or item.get("warehouseAvailability") or item.get("inStockText"),
        "Seller": item.get("seller") or item.get("soldBy"),
        "Fulfilled by": item.get("fulfilledBy"),
        "Category": item.get("breadCrumbs") or item.get("categories"),
    }

    parts: list[str] = []
    _add_section(parts, "商品メタ情報", {k: v for k, v in metadata_rows.items() if v not in (None, "", [], {})})
    _add_section(parts, "商品特徴", item.get("features") or item.get("featureBullets"))
    _add_section(parts, "商品説明", item.get("description") or item.get("productDescription") or item.get("bookDescription"))
    _add_section(parts, "A+ Content / ブランドストーリー", item.get("aPlusContent") or item.get("brandStory"))
    _add_section(parts, "商品概要", item.get("productOverview") or item.get("attributes"))
    _add_section(parts, "重要情報", item.get("importantInformation") or item.get("support") or item.get("returnPolicy"))

    specs = []
    for field in ("productSpecification", "manufacturerAttributes", "detailInfo"):
      specs.extend(_iter_kv_list(item.get(field)))
    if specs:
        _add_section(parts, "スペック詳細", {k or f"項目{idx + 1}": v for idx, (k, v) in enumerate(specs)})

    review_lines = _format_reviews(item)
    if review_lines:
        parts.append("## レビュー・評判\n" + "\n".join(review_lines))

    _add_section(parts, "画像情報", item.get("highResolutionImages") or item.get("imageUrlList") or item.get("images"))

    captions = "\n\n".join(parts).strip()
    if not captions:
        captions = json.dumps(item, ensure_ascii=False, indent=2)

    asin = _as_text(item.get("asin") or item.get("originalAsin"))
    return {
        "title": title,
        "captions": captions,
        "video_id": asin,
        "url": item.get("url") or source_url,
        "source_type": "amazon",
        "source_item": item,
    }


def _build_input_payload(product_url: str) -> dict[str, Any]:
    normalized_url = normalize_product_url(product_url)
    asin = extract_asin(normalized_url)
    domain = _domain_from_url(normalized_url)
    max_comments = int(os.getenv("AMAZON_APIFY_MAX_COMMENTS", str(DEFAULT_MAX_COMMENTS)) or DEFAULT_MAX_COMMENTS)
    max_comments = max(1, min(100, max_comments))

    payload: dict[str, Any] = {
        "asins": [asin or normalized_url],
        "amazonDomain": domain,
        "language": os.getenv("AMAZON_APIFY_LANGUAGE", "ja-JP"),
        "proxyCountry": os.getenv("AMAZON_APIFY_PROXY_COUNTRY", "AUTO"),
        "useCaptchaSolver": os.getenv("AMAZON_APIFY_USE_CAPTCHA_SOLVER", "").strip().lower() in {"1", "true", "yes"},
        "sortOrder": os.getenv("AMAZON_APIFY_SORT_ORDER", "recent"),
        "maxComments": max_comments,
    }
    if not asin:
        payload["startUrls"] = [normalized_url]

    if os.getenv("AMAZON_APIFY_USE_RESIDENTIAL_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        payload["proxyConfiguration"] = {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        }

    return payload


def get_product_details(product_url: str, api_key: str) -> dict[str, Any] | None:
    normalized_url = resolve_product_url(product_url)
    actor_name = os.getenv("AMAZON_PRODUCT_DETAILS_ACTOR", DEFAULT_ACTOR).strip() or DEFAULT_ACTOR
    run_url = _actor_run_url(actor_name)
    payload = _build_input_payload(normalized_url)
    timeout_seconds = int(os.getenv("AMAZON_APIFY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)) or DEFAULT_TIMEOUT_SECONDS)
    memory_mb = int(os.getenv("AMAZON_APIFY_MEMORY_MB", str(DEFAULT_MEMORY_MB)) or DEFAULT_MEMORY_MB)

    print(f"   Amazon Apify actor: {actor_name}")
    print(f"   Amazon URL: {normalized_url}")

    try:
        response = requests.post(
            run_url,
            params={
                "token": api_key,
                "timeout": timeout_seconds,
                "memory": memory_mb,
                "maxItems": 1,
                "clean": "true",
            },
            json=payload,
            timeout=timeout_seconds + 60,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as error:
        response = getattr(error, "response", None)
        detail = _sanitize_error_text(str(error).strip(), api_key)
        body = _sanitize_error_text(_read_response_text(response)[:500], api_key)
        if body:
            detail = f"{detail} | {body}"
        print(f"   Amazon Apify error: {detail}")
        return None
    except ValueError as error:
        print(f"   Amazon Apify JSON parse error: {error}")
        return None

    if not isinstance(data, list) or not data:
        print("   Amazon Apify returned no items")
        return None

    return build_transcript_from_item(data[0], normalized_url)
