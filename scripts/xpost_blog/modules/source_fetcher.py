from typing import Any

from . import apify_fetcher, socialdata_fetcher
from .onedrive_writer import normalize_x_url

SUPPORTED_PROVIDERS = {"auto", "apify", "socialdata"}


def normalize_provider_name(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORTED_PROVIDERS else "auto"


def validate_environment(run_mode: str, preferred_provider: str, socialdata_api_key: str, apify_api_key: str):
    if run_mode not in {"process_queue", "full"}:
        return

    provider = normalize_provider_name(preferred_provider)
    if provider == "socialdata" and not socialdata_api_key:
        raise ValueError("SOCIALDATA_API_KEY が設定されていません")
    if provider == "apify" and not apify_api_key:
        raise ValueError("APIFY_API_KEY が設定されていません")
    if provider == "auto" and not any((socialdata_api_key, apify_api_key)):
        raise ValueError("APIFY_API_KEY または SOCIALDATA_API_KEY が設定されていません")


def _provider_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_provider": bundle.get("provider", ""),
        "source_provider_label": bundle.get("providerLabel", ""),
        "source_provider_detail": bundle.get("providerDetail", ""),
    }


def _tag_bundle(bundle: dict[str, Any], *, provider: str, label: str, detail: str) -> dict[str, Any]:
    tagged = dict(bundle)
    tagged.setdefault("provider", provider)
    tagged.setdefault("providerLabel", label)
    tagged.setdefault("providerDetail", detail)
    return tagged


def _with_provider_metadata(
    bundle: dict[str, Any],
    attempted_providers: list[str],
    fallback_used: bool = False,
    fallback_reason: str = "",
    fallback_from: str = "",
) -> dict[str, Any]:
    enriched = dict(bundle)
    summary = _provider_summary(bundle)
    enriched.update(summary)
    enriched["attempted_providers"] = attempted_providers
    enriched["fallback_used"] = bool(fallback_used)
    enriched["fallback_reason"] = fallback_reason
    enriched["fallback_from"] = fallback_from
    return enriched


def _compose_failure(
    attempted_providers: list[str],
    first_failure: dict[str, Any] | None,
    second_failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages = []
    http_status = None
    for failure in (first_failure, second_failure):
        if not failure:
            continue
        label = failure.get("providerLabel") or failure.get("source_provider_label") or "取得"
        detail = str(failure.get("error") or "").strip()
        if detail:
            messages.append(f"{label}: {detail}")
        if http_status is None and failure.get("httpStatus") not in (None, ""):
            http_status = failure.get("httpStatus")

    return {
        "ok": False,
        "error": " / ".join(messages) or "取得に失敗しました",
        "httpStatus": http_status,
        "attempted_providers": attempted_providers,
        "provider": (second_failure or first_failure or {}).get("provider", ""),
        "providerLabel": (second_failure or first_failure or {}).get("providerLabel", ""),
        "providerDetail": (second_failure or first_failure or {}).get("providerDetail", ""),
        "source_provider": (second_failure or first_failure or {}).get("provider", ""),
        "source_provider_label": (second_failure or first_failure or {}).get("providerLabel", ""),
        "source_provider_detail": (second_failure or first_failure or {}).get("providerDetail", ""),
        "fallback_used": bool(second_failure),
        "fallback_reason": "primary_failed" if second_failure else "",
        "fallback_from": (first_failure or {}).get("provider", "") if second_failure else "",
    }


def fetch_post_bundle(
    post_url: str,
    *,
    socialdata_api_key: str = "",
    apify_api_key: str = "",
    preferred_provider: str = "auto",
    apify_actor_name: str = apify_fetcher.DEFAULT_XPOST_ACTOR,
) -> dict[str, Any]:
    provider = normalize_provider_name(preferred_provider)
    normalized_post_url = normalize_x_url(post_url)
    attempted_providers: list[str] = []

    needs_article_body = "/i/article/" in normalized_post_url

    if provider == "socialdata":
        socialdata_bundle = _tag_bundle(
            socialdata_fetcher.fetch_post_bundle(normalized_post_url, socialdata_api_key),
            provider="socialdata",
            label="SocialData",
            detail="SocialData API",
        )
        attempted_providers.append("SocialData")
        return _with_provider_metadata(socialdata_bundle, attempted_providers)

    def run_apify() -> dict[str, Any]:
        attempted_providers.append("Apify")
        return apify_fetcher.fetch_post_bundle(
            normalized_post_url,
            apify_api_key,
            actor_name=apify_actor_name,
        )

    def run_socialdata() -> dict[str, Any]:
        attempted_providers.append("SocialData")
        return _tag_bundle(
            socialdata_fetcher.fetch_post_bundle(normalized_post_url, socialdata_api_key),
            provider="socialdata",
            label="SocialData",
            detail="SocialData API",
        )

    if provider == "apify":
        apify_bundle = run_apify()
        if apify_bundle.get("ok") and not apify_bundle.get("requires_article_fallback"):
            return _with_provider_metadata(apify_bundle, attempted_providers)
        if socialdata_api_key:
            socialdata_bundle = run_socialdata()
            if socialdata_bundle.get("ok"):
                return _with_provider_metadata(
                    socialdata_bundle,
                    attempted_providers,
                    fallback_used=True,
                    fallback_reason=(
                        "article_body_required" if apify_bundle.get("requires_article_fallback") else "apify_failed"
                    ),
                    fallback_from="apify",
                )
            if apify_bundle.get("ok"):
                return _with_provider_metadata(
                    apify_bundle,
                    attempted_providers,
                    fallback_used=False,
                    fallback_reason="socialdata_failed_after_apify_partial",
                    fallback_from="socialdata",
                )
            return _compose_failure(attempted_providers, apify_bundle, socialdata_bundle)
        return _with_provider_metadata(apify_bundle, attempted_providers)

    if apify_api_key and not needs_article_body:
        apify_bundle = run_apify()
        if apify_bundle.get("ok") and not apify_bundle.get("requires_article_fallback"):
            return _with_provider_metadata(apify_bundle, attempted_providers)
        if apify_bundle.get("ok") and apify_bundle.get("requires_article_fallback") and socialdata_api_key:
            socialdata_bundle = run_socialdata()
            if socialdata_bundle.get("ok"):
                return _with_provider_metadata(
                    socialdata_bundle,
                    attempted_providers,
                    fallback_used=True,
                    fallback_reason="article_body_required",
                    fallback_from="apify",
                )
            return _with_provider_metadata(
                apify_bundle,
                attempted_providers,
                fallback_used=False,
                fallback_reason="socialdata_failed_after_apify_partial",
                fallback_from="socialdata",
            )
        if apify_bundle.get("ok"):
            return _with_provider_metadata(apify_bundle, attempted_providers)
        if socialdata_api_key:
            socialdata_bundle = run_socialdata()
            if socialdata_bundle.get("ok"):
                return _with_provider_metadata(
                    socialdata_bundle,
                    attempted_providers,
                    fallback_used=True,
                    fallback_reason="apify_failed",
                    fallback_from="apify",
                )
            return _compose_failure(attempted_providers, apify_bundle, socialdata_bundle)
        return _with_provider_metadata(apify_bundle, attempted_providers)

    if socialdata_api_key:
        socialdata_bundle = run_socialdata()
        if socialdata_bundle.get("ok"):
            return _with_provider_metadata(
                socialdata_bundle,
                attempted_providers,
                fallback_used=bool(apify_api_key and needs_article_body),
                fallback_reason="direct_article_socialdata" if apify_api_key and needs_article_body else "",
                fallback_from="apify" if apify_api_key and needs_article_body else "",
            )
        if apify_api_key:
            apify_bundle = run_apify()
            if apify_bundle.get("ok"):
                return _with_provider_metadata(
                    apify_bundle,
                    attempted_providers,
                    fallback_used=False,
                    fallback_reason="socialdata_failed_apify_partial",
                    fallback_from="socialdata",
                )
            return _compose_failure(attempted_providers, socialdata_bundle, apify_bundle)
        return _with_provider_metadata(
            socialdata_bundle,
            attempted_providers,
            fallback_used=False,
            fallback_reason="",
            fallback_from="",
        )

    return {
        "ok": False,
        "error": "利用可能な取得プロバイダがありません",
        "httpStatus": 400,
        "attempted_providers": attempted_providers,
        "source_provider": "",
        "source_provider_label": "",
        "source_provider_detail": "",
        "fallback_used": False,
        "fallback_reason": "",
        "fallback_from": "",
    }
