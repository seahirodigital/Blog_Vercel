from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = ROOT / "scripts" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from modules import amazon_product_fetcher as fetcher  # noqa: E402


DEFAULT_ACTORS = [
    "junglee/amazon-crawler",
    "junglee/free-amazon-product-scraper",
    "junglee/amazon-asins-scraper",
]


def _as_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return json.dumps(value, ensure_ascii=False)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}, []):
        return []
    return [value]


def _kv_count(value: Any) -> int:
    if isinstance(value, dict):
        return len([k for k, v in value.items() if k and v not in (None, "", [], {})])
    if isinstance(value, list):
        count = 0
        for item in value:
            if isinstance(item, dict):
                if any(v not in (None, "", [], {}) for v in item.values()):
                    count += 1
            elif item:
                count += 1
        return count
    return 1 if value not in (None, "", [], {}) else 0


def coverage_from_item(item: dict[str, Any], source_url: str) -> dict[str, Any]:
    transcript = fetcher.build_transcript_from_item(item, source_url)
    features = item.get("features") or item.get("featureBullets")
    description = item.get("description") or item.get("productDescription") or item.get("bookDescription")
    aplus = item.get("aPlusContent") or item.get("brandStory")
    specs = (
        item.get("productOverview")
        or item.get("attributes")
        or item.get("productSpecification")
        or item.get("manufacturerAttributes")
        or item.get("detailInfo")
    )
    reviews = item.get("reviews") or item.get("productPageReviews")
    images = item.get("highResolutionImages") or item.get("imageUrlList") or item.get("images")

    return {
        "ok": bool(transcript),
        "title": _as_text(item.get("title") or item.get("productTitle") or item.get("name"))[:140],
        "asin": _as_text(item.get("asin") or item.get("originalAsin")),
        "has_price": bool(_as_text(item.get("price") or item.get("retailPrice"))),
        "has_rating": bool(_as_text(item.get("stars") or item.get("rating") or item.get("productRating"))),
        "has_review_count": bool(_as_text(item.get("reviewsCount") or item.get("reviewCount") or item.get("countReview"))),
        "has_availability": bool(_as_text(item.get("availability") or item.get("warehouseAvailability") or item.get("inStockText"))),
        "features_count": len(_as_list(features)),
        "description_len": len(_as_text(description)),
        "aplus_len": len(_as_text(aplus)),
        "specs_count": _kv_count(specs),
        "reviews_count": len(_as_list(reviews)),
        "images_count": len(_as_list(images)),
        "captions_len": len(transcript.get("captions", "")) if transcript else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Amazon Apify actors and report field coverage.")
    parser.add_argument("--url", required=True, help="Amazon product URL or ASIN")
    parser.add_argument("--actors", default=",".join(DEFAULT_ACTORS), help="Comma-separated Actor IDs")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("AMAZON_APIFY_TIMEOUT_SECONDS", "300")))
    parser.add_argument("--memory", type=int, default=int(os.getenv("AMAZON_APIFY_MEMORY_MB", "2048")))
    parser.add_argument("--include-direct-fallback", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.getenv("APIFY_API_KEY", "").strip()
    product_url = fetcher.resolve_product_url(args.url)

    print(f"Target URL: {product_url}")
    print(f"ASIN: {fetcher.extract_asin(product_url) or '(not detected)'}")

    if not api_key:
        print("APIFY_API_KEY is missing; Apify actor probes cannot run.", file=sys.stderr)
        return 2

    actors = [actor.strip() for actor in args.actors.split(",") if actor.strip()]
    results = []

    for actor in actors:
        print(f"\n=== {actor} ===")
        payload = fetcher.build_actor_input_payload(actor, product_url)
        print("Input:")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
        data, error = fetcher._run_actor(actor, payload, api_key, args.timeout, args.memory)
        if data is None:
            result = {"actor": actor, "status": "error", "error": error}
            print("ERROR:", error)
        elif not data:
            result = {"actor": actor, "status": "empty"}
            print("EMPTY")
        else:
            item = data[0] if isinstance(data[0], dict) else {"value": data[0]}
            coverage = coverage_from_item(item, product_url)
            result = {"actor": actor, "status": "ok", **coverage}
            print(json.dumps(coverage, ensure_ascii=False, indent=2))
        results.append(result)

    if args.include_direct_fallback:
        print("\n=== direct-local-fallback ===")
        transcript = fetcher.get_product_details_direct(product_url)
        result = {
            "actor": "direct-local-fallback",
            "status": "ok" if transcript else "error",
            "title": (transcript or {}).get("title", "")[:140],
            "captions_len": len((transcript or {}).get("captions", "")),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        results.append(result)

    print("\n=== SUMMARY ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if any(item.get("status") == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
