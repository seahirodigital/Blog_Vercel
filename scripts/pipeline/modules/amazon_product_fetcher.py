from __future__ import annotations

import html
import json
import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import requests


APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_ACTOR = "junglee/free-amazon-product-scraper"
SCRAPER_ENGINE_ACTOR = "scraper-engine/amazon-product-details-scraper"
HTML_FALLBACK_ACTOR = "apify/cheerio-scraper"
DEFAULT_ACTOR_CANDIDATES = [
    "junglee/amazon-crawler",
    "junglee/free-amazon-product-scraper",
    "junglee/amazon-asins-scraper",
]
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MEMORY_MB = 2048
DEFAULT_MAX_COMMENTS = 20
SHORT_URL_HOSTS = {"amzn.asia", "amzn.to"}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
CHEERIO_PAGE_FUNCTION = r"""
async function pageFunction(context) {
    const { $, request } = context;

    const clean = (value) => String(value || '')
        .replace(/\s+/g, ' ')
        .replace(/\u200e|\u200f/g, '')
        .trim();
    const text = (selector) => clean($(selector).first().text());
    const texts = (selector) => $(selector)
        .map((_, el) => clean($(el).text()))
        .get()
        .filter(Boolean)
        .filter((value, index, array) => array.indexOf(value) === index);
    const kvRows = (selector) => {
        const rows = {};
        $(selector).each((_, row) => {
            const key = clean($(row).find('th, .a-span3, .label, .prodDetSectionEntry').first().text()).replace(/:$/, '');
            const value = clean($(row).find('td, .a-span9, .value, .prodDetAttrValue').last().text());
            if (key && value) rows[key] = value;
        });
        return rows;
    };

    const bodyText = clean($('body').text());
    const blocked = /Robot Check|Enter the characters you see below|captcha/i.test(bodyText)
        || $('form[action*="/errors/validateCaptcha"]').length > 0;
    if (blocked) {
        return { url: request.loadedUrl || request.url, error: 'Amazon captcha or robot check page returned' };
    }

    const dynamicImagesRaw = $('#landingImage').attr('data-a-dynamic-image') || '';
    let images = [];
    try { images = Object.keys(JSON.parse(dynamicImagesRaw)); } catch (e) {}
    if (!images.length) {
        images = [
            $('#landingImage').attr('src'),
            $('meta[property="og:image"]').attr('content'),
        ].filter(Boolean);
    }

    const overview = {
        ...kvRows('#productOverview_feature_div tr'),
        ...kvRows('#productDetails_techSpec_section_1 tr'),
        ...kvRows('#productDetails_detailBullets_sections1 tr'),
    };
    $('#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li').each((_, el) => {
        const raw = clean($(el).text());
        const parts = raw.split(':');
        if (parts.length >= 2) {
            const key = clean(parts.shift());
            const value = clean(parts.join(':'));
            if (key && value) overview[key] = value;
        }
    });

    const reviews = $('[data-hook="review"]').map((index, el) => ({
        title: clean($(el).find('[data-hook="review-title"]').text()),
        rating: clean($(el).find('[data-hook="review-star-rating"], [data-hook="cmps-review-star-rating"]').text()),
        date: clean($(el).find('[data-hook="review-date"]').text()),
        text: clean($(el).find('[data-hook="review-body"]').text()),
    })).get().filter((review) => review.title || review.text);

    const url = request.loadedUrl || request.url;
    const asinFromUrl = (url.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i) || [])[1] || '';
    const asin = $('#ASIN').attr('value') || $('[data-asin]').first().attr('data-asin') || asinFromUrl;

    return {
        url,
        asin,
        title: text('#productTitle') || clean($('meta[property="og:title"]').attr('content')) || text('title'),
        brand: text('#bylineInfo') || text('tr.po-brand td.a-span9 span'),
        price: text('.a-price .a-offscreen') || text('#priceblock_ourprice') || text('#priceblock_dealprice'),
        listPrice: text('.basisPrice .a-offscreen') || text('.a-text-price .a-offscreen'),
        stars: text('#acrPopover span.a-icon-alt') || text('[data-hook="rating-out-of-text"]'),
        reviewsCount: text('#acrCustomerReviewText') || text('[data-hook="total-review-count"]'),
        availability: text('#availability span'),
        seller: text('#merchant-info') || text('#sellerProfileTriggerId'),
        categories: texts('#wayfinding-breadcrumbs_feature_div li a'),
        featureBullets: texts('#feature-bullets li span.a-list-item').filter((value) => !/^make sure/i.test(value)),
        description: text('#productDescription') || text('#bookDescription_feature_div'),
        aPlusContent: text('#aplus') || text('#aplus_feature_div'),
        productOverview: overview,
        productPageReviews: reviews,
        highResolutionImages: images,
        importantInformation: text('#importantInformation') || text('#legal_feature_div'),
    };
}
"""

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


def _is_actor_not_rented(error_text: str) -> bool:
    return "actor-is-not-rented" in str(error_text or "").lower()


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


def _clean_html_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            text = re.sub(r"\s+", " ", data or "").strip()
            if text:
                self.parts.append(text)


def _visible_html_text(value: Any) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(str(value or ""))
    except Exception:
        return _clean_html_text(value)
    text = " ".join(parser.parts)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return _remove_noise_text(text)


def _remove_noise_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"\{[^{}]*(?:videoReferenceId|clickstreamNexusMetricsConfig|sushiMetricsConfig|closedCaptionsConfig)[^{}]*\}", " ", value)
    value = re.sub(r"\b(?:function|var|const|let)\s+[A-Za-z0-9_$]+[\s\S]*", " ", value)
    value = re.sub(r"\.[A-Za-z0-9_-]+\s+\{[^{}]*\}", " ", value)
    value = re.sub(r"#[A-Za-z0-9_-]+\s+\{[^{}]*\}", " ", value)
    value = re.sub(r"@media[^{]+\{[^{}]*\}", " ", value)
    value = re.sub(r"/\*.*?\*/", " ", value, flags=re.S)
    return re.sub(r"\s+", " ", value).strip()


def _format_brand_story_text(text: str) -> list[str]:
    cleaned = _remove_noise_text(text)
    cleaned = re.sub(r"(メーカーによる説明|商品の説明)", r"\n\1\n", cleaned)
    cleaned = re.sub(r"(?<=[。！？])\s+", "\n", cleaned)
    cleaned = re.sub(r"\s+-\s+", "\n- ", cleaned)

    lines: list[str] = []
    seen = set()
    for raw in cleaned.splitlines():
        line = raw.strip(" -")
        if not line:
            continue
        if len(line) < 4:
            continue
        if any(token in line for token in ("function(", "window.", ".aplus-", "{", "}", "schemaId", "videoReferenceId")):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= 40:
            break
    return lines


def _first_match(source: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.I | re.S)
        if match:
            return _clean_html_text(match.group(1))
    return ""


def _first_raw_match(source: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.I | re.S)
        if match:
            return match.group(1)
    return ""


def _extract_list_from_block(block: str, pattern: str, limit: int = 20) -> list[str]:
    values = [_clean_html_text(item) for item in re.findall(pattern, block or "", flags=re.I | re.S)]
    unique: list[str] = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
        if len(unique) >= limit:
            break
    return unique


def _extract_local_product_item(product_url: str, page_html: str) -> dict[str, Any]:
    title = _first_match(
        page_html,
        [
            r'<span[^>]+id="productTitle"[^>]*>(.*?)</span>',
            r"<span[^>]+id='productTitle'[^>]*>(.*?)</span>",
            r'<meta[^>]+property="og:title"[^>]+content="(.*?)"',
        ],
    )
    price = _first_match(
        page_html,
        [
            r'<span[^>]+class="[^"]*a-offscreen[^"]*"[^>]*>([^<]+)</span>',
            r"<span[^>]+class='[^']*a-offscreen[^']*'[^>]*>([^<]+)</span>",
        ],
    )
    rating = _first_match(page_html, [r'<span[^>]+class="[^"]*a-icon-alt[^"]*"[^>]*>([^<]+)</span>'])
    review_count = _first_match(page_html, [r'<span[^>]+id="acrCustomerReviewText"[^>]*>(.*?)</span>'])
    availability = _first_match(page_html, [r'<div[^>]+id="availability"[^>]*>(.*?)</div>'])

    features_block = _first_raw_match(
        page_html,
        [r'<div[^>]+id="feature-bullets"[^>]*>(.*?)</div>\s*</div>'],
    )
    features = _extract_list_from_block(
        features_block,
        r'<span[^>]+class="[^"]*a-list-item[^"]*"[^>]*>(.*?)</span>',
        limit=12,
    )
    features = [value for value in features if not value.lower().startswith("make sure")]

    description = _first_match(page_html, [r'<div[^>]+id="productDescription"[^>]*>(.*?)</div>'])
    aplus_raw = _first_raw_match(page_html, [r'<div[^>]+id="aplus"[^>]*>(.*?)</div>\s*</div>'])
    aplus_lines = _format_brand_story_text(_visible_html_text(aplus_raw))

    breadcrumbs_block = _first_raw_match(
        page_html,
        [r'<div[^>]+id="wayfinding-breadcrumbs_feature_div"[^>]*>(.*?)</div>'],
    )
    categories = _extract_list_from_block(breadcrumbs_block, r"<a[^>]*>(.*?)</a>", limit=10)

    overview: dict[str, str] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.I | re.S):
        key = _first_match(row, [r"<th[^>]*>(.*?)</th>", r'<span[^>]+class="[^"]*a-span3[^"]*"[^>]*>(.*?)</span>'])
        value = _first_match(row, [r"<td[^>]*>(.*?)</td>", r'<span[^>]+class="[^"]*a-span9[^"]*"[^>]*>(.*?)</span>'])
        if key and value and len(key) <= 80 and len(value) <= 400:
            overview[key.rstrip(":")] = value

    detail_bullets = _first_raw_match(
        page_html,
        [r'<div[^>]+id="detailBullets_feature_div"[^>]*>(.*?)</div>\s*</div>'],
    )
    for raw in _extract_list_from_block(detail_bullets, r"<li[^>]*>(.*?)</li>", limit=30):
        if ":" in raw:
            key, value = raw.split(":", 1)
            key = key.strip().rstrip(":")
            value = value.strip()
            if key and value:
                overview.setdefault(key, value)

    reviews: list[dict[str, str]] = []
    for block in re.findall(r'<div[^>]+data-hook="review"[^>]*>(.*?)</div>\s*</div>', page_html, flags=re.I | re.S)[:8]:
        review = {
            "title": _first_match(block, [r'data-hook="review-title"[^>]*>(.*?)</[^>]+>']),
            "rating": _first_match(block, [r'data-hook="review-star-rating"[^>]*>(.*?)</[^>]+>']),
            "date": _first_match(block, [r'data-hook="review-date"[^>]*>(.*?)</[^>]+>']),
            "text": _first_match(block, [r'data-hook="review-body"[^>]*>(.*?)</span>']),
        }
        if any(review.values()):
            reviews.append(review)

    image = _first_match(page_html, [r'<meta[^>]+property="og:image"[^>]+content="(.*?)"'])
    asin = extract_asin(product_url) or _first_match(page_html, [r'<input[^>]+id="ASIN"[^>]+value="([A-Z0-9]{10})"'])

    return {
        "url": product_url,
        "asin": asin,
        "title": title or "Amazon product",
        "price": price,
        "stars": rating,
        "reviewsCount": review_count,
        "availability": availability,
        "categories": categories,
        "featureBullets": features,
        "description": description,
        "aPlusContent": aplus_lines,
        "productOverview": overview,
        "productPageReviews": reviews,
        "highResolutionImages": [image] if image else [],
        "source": "direct-local-fallback",
    }


def get_product_details_direct(product_url: str) -> dict[str, Any] | None:
    print("   Amazon direct fallback: local HTTP extraction")
    try:
        response = requests.get(
            product_url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.6",
            },
            allow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"   Amazon direct fallback error: {_sanitize_error_text(error)}")
        return None

    page_html = response.text or ""
    if re.search(r"Robot Check|Enter the characters you see below|captcha", page_html, flags=re.I):
        print("   Amazon direct fallback returned captcha or robot check page")
        return None

    item = _extract_local_product_item(normalize_product_url(response.url or product_url), page_html)
    if not item.get("title") or item.get("title") == "Amazon product":
        print("   Amazon direct fallback could not extract product title")
        return None
    return build_transcript_from_item(item, item.get("url") or product_url)


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

    error = item.get("error") or (item.get("#debug") if item.get("#error") else None)
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


def _as_string_list(value: Any, limit: int = 300) -> list[str]:
    values: list[str] = []

    def append_text(item: Any):
        if item in (None, "", [], {}):
            return
        if isinstance(item, dict):
            text = item.get("text") or item.get("value") or item.get("label") or item.get("title") or item.get("alt")
            if text:
                append_text(text)
            return
        if isinstance(item, list):
            for child in item:
                append_text(child)
            return
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text:
            values.append(text)

    append_text(value)

    unique: list[str] = []
    seen = set()
    for text in values:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
        if len(unique) >= limit:
            break
    return unique


def _pick_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _merge_payload_maps(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            for item_key, item_value in value.items():
                if item_value not in (None, "", [], {}):
                    merged[str(item_key)] = item_value
        elif isinstance(value, list):
            for index, row in enumerate(value, start=1):
                if isinstance(row, dict):
                    row_key = row.get("name") or row.get("key") or row.get("label") or row.get("title") or f"項目{index}"
                    row_value = row.get("value") or row.get("text") or row.get("description")
                    if row_value not in (None, "", [], {}):
                        merged[str(row_key)] = row_value
    return merged


def build_transcript_from_chrome_payload(payload: dict[str, Any], source_url: str = "") -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    url = _as_text(_pick_first(payload, "url", "finalUrl", "canonicalUrl", "sourceUrl", "productUrl") or source_url)
    title = _as_text(_pick_first(payload, "title", "productTitle", "pageTitle", "name")) or "Amazon product"
    asin = _as_text(_pick_first(payload, "asin", "ASIN")) or extract_asin(url)

    metadata_rows = {
        "URL": url,
        "ASIN": asin,
        "Brand": _pick_first(payload, "brand", "manufacturer"),
        "Price": _pick_first(payload, "price", "salePrice"),
        "List price": _pick_first(payload, "listPrice", "referencePrice"),
        "Rating": _pick_first(payload, "rating", "stars", "productRating"),
        "Review count": _pick_first(payload, "reviewCount", "reviewsCount", "countReview"),
        "Availability": _pick_first(payload, "availability", "inStockText"),
        "Seller": _pick_first(payload, "seller", "soldBy"),
        "Category": _pick_first(payload, "categories", "breadCrumbs"),
        "Captured at": _pick_first(payload, "capturedAt"),
        "Extraction source": _pick_first(payload, "source"),
    }

    parts: list[str] = []
    _add_section(parts, "商品メタ情報", {k: v for k, v in metadata_rows.items() if v not in (None, "", [], {})})
    _add_section(parts, "商品特徴", _as_string_list(_pick_first(payload, "featureBullets", "features"), limit=80))
    _add_section(parts, "商品説明", _pick_first(payload, "description", "productDescription", "bookDescription"))
    _add_section(parts, "A+ Content / ブランドストーリー", _as_string_list(_pick_first(payload, "aplusLines", "aPlusLines", "aplusText", "aPlusText", "brandStory"), limit=240))
    _add_section(parts, "カルーセル・画像内候補テキスト", _as_string_list(_pick_first(payload, "carouselTexts", "imageTexts", "moduleTexts"), limit=300))
    _add_section(parts, "OCR抽出テキスト", _as_string_list(_pick_first(payload, "ocrTexts", "ocrText"), limit=200))
    _add_section(parts, "画像alt/title/aria", _as_string_list(_pick_first(payload, "imageAlts", "imageAltTexts", "altTexts"), limit=300))
    _add_section(parts, "商品概要", _merge_payload_maps(payload, "productOverview", "overview", "attributes"))
    _add_section(parts, "スペック詳細", _merge_payload_maps(payload, "specs", "specifications", "detailBullets", "technicalDetails"))
    _add_section(parts, "重要情報", _pick_first(payload, "importantInformation", "importantInfo", "support", "returnPolicy"))
    _add_section(parts, "ページ内追加テキスト", _as_string_list(_pick_first(payload, "extraTexts", "bodyTexts", "visibleTexts"), limit=300))

    captions = "\n\n".join(parts).strip()
    if len(captions) < 200:
        fallback_lines = _as_string_list(payload, limit=400)
        if fallback_lines:
            captions = "## Chrome抽出payload\n" + "\n".join(f"- {line}" for line in fallback_lines)

    if not captions:
        return None

    return {
        "title": title,
        "captions": captions,
        "video_id": asin,
        "url": url or source_url,
        "source_type": "amazon",
        "source_item": payload,
    }


def _build_scraper_engine_payload(product_url: str) -> dict[str, Any]:
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


def _build_junglee_free_payload(product_url: str) -> dict[str, Any]:
    return {
        "categoryUrls": [{"url": normalize_product_url(product_url)}],
        "maxItemsPerStartUrl": 1,
        "maxSearchPagesPerStartUrl": 1,
        "maxProductVariantsAsSeparateResults": 0,
        "useCaptchaSolver": os.getenv("AMAZON_APIFY_USE_CAPTCHA_SOLVER", "").strip().lower() in {"1", "true", "yes"},
        "scrapeProductVariantPrices": False,
        "scrapeProductDetails": True,
        "ensureLoadedProductDescriptionFields": True,
    }


def _build_junglee_crawler_payload(product_url: str) -> dict[str, Any]:
    return {
        "categoryOrProductUrls": [{"url": normalize_product_url(product_url)}],
        "maxItemsPerStartUrl": 1,
        "proxyCountry": os.getenv("AMAZON_APIFY_PROXY_COUNTRY", "AUTO_SELECT_PROXY_COUNTRY"),
        "maxSearchPagesPerStartUrl": 1,
        "maxProductVariantsAsSeparateResults": 0,
        "maxOffers": 0,
        "scrapeSellers": False,
        "ensureLoadedProductDescriptionFields": True,
        "useCaptchaSolver": os.getenv("AMAZON_APIFY_USE_CAPTCHA_SOLVER", "").strip().lower() in {"1", "true", "yes"},
        "scrapeProductVariantPrices": False,
        "scrapeProductDetails": True,
        "locationDeliverableRoutes": ["PRODUCT"],
    }


def _build_junglee_asins_payload(product_url: str) -> dict[str, Any]:
    asin = extract_asin(product_url)
    domain = _domain_from_url(product_url).replace("amazon.", "")
    return {
        "asins": [asin] if asin else [product_url],
        "domain": domain if domain else "co.jp",
        "maxOffers": 0,
        "useCaptchaSolver": os.getenv("AMAZON_APIFY_USE_CAPTCHA_SOLVER", "").strip().lower() in {"1", "true", "yes"},
    }


def build_actor_input_payload(actor_name: str, product_url: str) -> dict[str, Any]:
    normalized = str(actor_name or "").strip().lower()
    if normalized == "junglee/free-amazon-product-scraper":
        return _build_junglee_free_payload(product_url)
    if normalized == "junglee/amazon-crawler":
        return _build_junglee_crawler_payload(product_url)
    if normalized == "junglee/amazon-asins-scraper":
        return _build_junglee_asins_payload(product_url)
    if normalized == HTML_FALLBACK_ACTOR:
        return _build_cheerio_payload(product_url)
    return _build_scraper_engine_payload(product_url)


def _build_cheerio_payload(product_url: str) -> dict[str, Any]:
    use_proxy = os.getenv("AMAZON_APIFY_FALLBACK_USE_PROXY", "true").strip().lower() not in {"0", "false", "no"}
    proxy_configuration: dict[str, Any] = {"useApifyProxy": use_proxy}
    proxy_groups = os.getenv("AMAZON_APIFY_FALLBACK_PROXY_GROUPS", "").strip()
    if use_proxy and proxy_groups:
        proxy_configuration["apifyProxyGroups"] = [
            group.strip() for group in proxy_groups.split(",") if group.strip()
        ]

    return {
        "startUrls": [{"url": product_url}],
        "pageFunction": CHEERIO_PAGE_FUNCTION,
        "proxyConfiguration": proxy_configuration,
        "linkSelector": "",
        "maxPagesPerCrawl": 1,
        "maxResultsPerCrawl": 1,
        "maxRequestRetries": 2,
        "requestTimeoutSecs": 60,
        "debugLog": False,
    }


def _direct_fallback_enabled() -> bool:
    return os.getenv("AMAZON_ALLOW_DIRECT_FALLBACK", "true").strip().lower() not in {"0", "false", "no"}


def _apify_enabled() -> bool:
    return os.getenv("AMAZON_USE_APIFY", "false").strip().lower() in {"1", "true", "yes"}


def _actor_candidates(primary_actor: str) -> list[str]:
    configured = os.getenv("AMAZON_PRODUCT_DETAILS_ACTORS", "").strip()
    raw = [primary_actor]
    if configured:
        raw.extend(actor.strip() for actor in configured.split(",") if actor.strip())
    else:
        raw.extend(DEFAULT_ACTOR_CANDIDATES)
    candidates: list[str] = []
    seen = set()
    for actor in raw:
        normalized = str(actor or "").strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        candidates.append(normalized)
    return candidates


def _run_actor(actor_name: str, payload: dict[str, Any], api_key: str, timeout_seconds: int, memory_mb: int) -> tuple[list[Any] | None, str]:
    run_url = _actor_run_url(actor_name)
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
        if not isinstance(data, list):
            return None, "Apify response was not a dataset item list"
        return data, ""
    except requests.RequestException as error:
        response = getattr(error, "response", None)
        detail = _sanitize_error_text(str(error).strip(), api_key)
        body = _sanitize_error_text(_read_response_text(response)[:500], api_key)
        if body:
            detail = f"{detail} | {body}"
        return None, detail
    except ValueError as error:
        return None, f"Amazon Apify JSON parse error: {error}"


def get_product_details(product_url: str, api_key: str) -> dict[str, Any] | None:
    normalized_url = resolve_product_url(product_url)
    actor_name = os.getenv("AMAZON_PRODUCT_DETAILS_ACTOR", DEFAULT_ACTOR).strip() or DEFAULT_ACTOR
    timeout_seconds = int(os.getenv("AMAZON_APIFY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)) or DEFAULT_TIMEOUT_SECONDS)
    memory_mb = int(os.getenv("AMAZON_APIFY_MEMORY_MB", str(DEFAULT_MEMORY_MB)) or DEFAULT_MEMORY_MB)

    print(f"   Amazon URL: {normalized_url}")

    if _apify_enabled() and api_key:
        for candidate in _actor_candidates(actor_name):
            print(f"   Amazon Apify actor: {candidate}")
            payload = build_actor_input_payload(candidate, normalized_url)
            data, error_detail = _run_actor(candidate, payload, api_key, timeout_seconds, memory_mb)
            if data is None:
                if _is_actor_not_rented(error_detail):
                    print("   Amazon Apify actor is not rented; trying next candidate")
                else:
                    print(f"   Amazon Apify error: {error_detail}")
                continue
            if not data:
                print("   Amazon Apify returned no items; trying next candidate")
                continue
            transcript = build_transcript_from_item(data[0], normalized_url)
            if transcript:
                return transcript
            print("   Amazon Apify item could not be converted; trying next candidate")
    else:
        print("   Amazon Apify disabled; using direct HTML fallback")

    if _direct_fallback_enabled():
        return get_product_details_direct(normalized_url)
    return None
