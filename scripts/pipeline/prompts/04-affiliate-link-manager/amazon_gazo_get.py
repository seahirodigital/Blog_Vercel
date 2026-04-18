r"""
Amazon のトップ画像を保存する試験スクリプト。

方針:
1. Creator API で検索1位商品の Primary 画像を必ず保存する
2. 商品詳細ページから高画質画像を取得できた場合は _hires 付きでも保存する
3. ローカルでは OneDrive 同期フォルダへ直接保存する
4. GitHub Actions では一時フォルダへ保存し、OneDrive へアップロード後に一時ファイルを削除する

使い方:
    python "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py" "MacBook Neo"
"""

from __future__ import annotations

import argparse
import html
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import requests
from PIL import Image, ImageOps


TOKEN_URL = "https://api.amazon.co.jp/auth/o2/token"
SEARCH_ITEMS_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
GET_ITEMS_URL = "https://creatorsapi.amazon/catalog/v1/getItems"
DEFAULT_APIFY_AMAZON_ACTOR = "kawsar/amazon-product-details-scrapper"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
ONEDRIVE_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

DEFAULT_MARKETPLACE = "www.amazon.co.jp"
DEFAULT_ASSOCIATE_TAG = "hiroshit-22"
DEFAULT_LOCAL_OUTPUT_DIR = Path(
    r"C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\Amazon_images"
)
LEGACY_DEFAULT_LOCAL_OUTPUT_DIR = DEFAULT_LOCAL_OUTPUT_DIR
DEFAULT_ACTIONS_SUBDIR = "amazon_top_images"
DEFAULT_ONEDRIVE_FOLDER = "Vercel_Blog/Amazon_images"
RAW_SUBDIR_NAME = "raw"
PREPARED_SUBDIR_NAME = "prepared"
NOTE_HERO_CANVAS_SIZE = (1600, 836)
NOTE_HERO_JPEG_QUALITY = 92
NOTE_HERO_BACKGROUND_COLOR = (255, 255, 255)
DEFAULT_RESOURCES = [
    "itemInfo.title",
    "images.primary.large",
    "images.primary.medium",
    "images.primary.small",
]
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
LANDING_IMAGE_TAG_RE = re.compile(
    r"<img[^>]*\bid=[\"']landingImage[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
COLOR_IMAGES_HIRES_RE = re.compile(
    r"""colorImages'\s*:\s*\{\s*'initial'\s*:\s*\[\s*\{"hiRes":"(https:[^"]+)""",
    re.DOTALL,
)
PRODUCT_TITLE_RE = re.compile(
    r'id="productTitle"[^>]*>\s*(.*?)\s*</span>',
    re.IGNORECASE | re.DOTALL,
)
ASIN_IN_URL_RE = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN)/([A-Z0-9]{10})(?:[/?]|$)",
    re.IGNORECASE,
)
HTML_SRC_RE = re.compile(r"""\bsrc=["']([^"']+)["']""", re.IGNORECASE)
HTML_DATA_OLD_HIRES_RE = re.compile(r"""\bdata-old-hires=["']([^"']+)["']""", re.IGNORECASE)
DEFAULT_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}
AMAZON_CAPTCHA_MARKERS = (
    "opfcaptcha.amazon.",
    "errors/validatecaptcha",
    "api-services-support@amazon.com",
    "robot check",
)


class AmazonCreatorsApiError(RuntimeError):
    """Amazon 画像取得関連の例外。"""


@dataclass
class SearchImageResult:
    """Creator API の検索結果。"""

    asin: str
    title: str
    image_url: str
    width: int | None
    height: int | None


@dataclass
class SavedImageInfo:
    """保存した画像の情報。"""

    label: str
    image_url: str
    local_path: Path
    width: int | None
    height: int | None
    onedrive_url: Optional[str] = None


@dataclass
class FetchTopImagesResult:
    """取得・保存した画像群の結果。"""

    asin: str
    title: str
    api_image: SavedImageInfo
    hires_image: Optional[SavedImageInfo]
    prepared_image: Optional[SavedImageInfo]
    detail_page_url: str


def is_github_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"


def resolve_default_local_output_dir() -> Path:
    override = os.getenv("AMAZON_TOP_IMAGE_LOCAL_OUTPUT_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    userprofile = os.getenv("USERPROFILE", "").strip()
    portable_default = (
        Path(userprofile)
        / "OneDrive"
        / "Obsidian in Onedrive 202602"
        / "Vercel_Blog"
        / "Amazon_images"
        if userprofile
        else LEGACY_DEFAULT_LOCAL_OUTPUT_DIR
    )
    for candidate in (portable_default, LEGACY_DEFAULT_LOCAL_OUTPUT_DIR):
        if candidate.exists():
            return candidate.resolve()
    return portable_default


def resolve_default_output_dir() -> Path:
    runner_temp = os.getenv("RUNNER_TEMP", "").strip()
    if is_github_actions() and runner_temp:
        return Path(runner_temp) / DEFAULT_ACTIONS_SUBDIR
    return resolve_default_local_output_dir()


def resolve_image_output_dirs(output_root: Path) -> tuple[Path, Path]:
    resolved_root = output_root.expanduser().resolve()
    return resolved_root / RAW_SUBDIR_NAME, resolved_root / PREPARED_SUBDIR_NAME


def build_remote_image_folder(root_folder: str, subdir: str = "") -> str:
    normalized_root = (root_folder or "").strip().strip("/")
    normalized_subdir = (subdir or "").strip().strip("/")
    if normalized_root and normalized_subdir:
        return f"{normalized_root}/{normalized_subdir}"
    return normalized_root or normalized_subdir


def infer_output_root_from_image_path(image_path: Path) -> Path:
    parent = image_path.parent
    if parent.name.lower() in {RAW_SUBDIR_NAME, PREPARED_SUBDIR_NAME}:
        return parent.parent
    return parent


def get_env_or_raise(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AmazonCreatorsApiError(
            f"環境変数 {name} が未設定です。PowerShell または GitHub Actions の環境変数を確認してください。"
        )
    return value


def get_optional_env(name: str) -> str:
    return os.getenv(name, "").strip()


def get_access_token() -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": get_env_or_raise("AMAZON_CLIENT_ID"),
            "client_secret": get_env_or_raise("AMAZON_CLIENT_SECRET"),
            "scope": "creatorsapi::default",
        },
        timeout=20,
    )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"Amazon アクセストークン取得に失敗しました: {response.status_code} {response.text[:300]}"
        )

    access_token = response.json().get("access_token", "").strip()
    if not access_token:
        raise AmazonCreatorsApiError("Amazon アクセストークン取得結果に access_token がありません。")
    return access_token


def post_creators_api(url: str, headers: dict, payload: dict, timeout: int = 30) -> requests.Response:
    last_response: requests.Response | None = None
    for attempt in range(1, 5):
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        last_response = response
        if response.status_code != 429:
            return response

        if attempt < 4:
            wait_seconds = attempt * 3
            print(f"[WARN] Creators API がスロットル中です。{wait_seconds}秒待って再試行します。")
            time.sleep(wait_seconds)

    assert last_response is not None
    return last_response


def extract_asin_from_url(url: str) -> str:
    match = ASIN_IN_URL_RE.search((url or "").strip())
    if not match:
        return ""
    return match.group(1).upper()


def get_onedrive_access_token() -> str:
    response = requests.post(
        ONEDRIVE_TOKEN_URL,
        data={
            "client_id": get_env_or_raise("ONEDRIVE_CLIENT_ID"),
            "client_secret": get_env_or_raise("ONEDRIVE_CLIENT_SECRET"),
            "refresh_token": get_env_or_raise("ONEDRIVE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
            "scope": "Files.ReadWrite.All offline_access",
        },
        timeout=20,
    )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"OneDrive アクセストークン取得に失敗しました: {response.status_code} {response.text[:300]}"
        )
    return response.json()["access_token"]


def pick_primary_image(item: dict) -> tuple[str, int | None, int | None]:
    images = item.get("images", {}) or {}
    primary = images.get("primary", {}) or {}

    for size in ("large", "medium", "small"):
        image_info = primary.get(size, {}) or {}
        image_url = (image_info.get("url") or "").strip()
        if image_url:
            return image_url, image_info.get("width"), image_info.get("height")

    raise AmazonCreatorsApiError("検索1位商品に Primary 画像がありません。")


def search_top_item_image(
    keyword: str,
    access_token: str,
    marketplace: str = DEFAULT_MARKETPLACE,
    partner_tag: str = DEFAULT_ASSOCIATE_TAG,
) -> SearchImageResult:
    response = post_creators_api(
        SEARCH_ITEMS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-marketplace": marketplace,
        },
        payload={
            "keywords": keyword,
            "partnerTag": partner_tag,
            "marketplace": marketplace,
            "resources": DEFAULT_RESOURCES,
            "itemCount": 1,
        },
        timeout=30,
    )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"SearchItems に失敗しました: {response.status_code} {response.text[:300]}"
        )

    items = response.json().get("searchResult", {}).get("items", [])
    if not items:
        raise AmazonCreatorsApiError(f"キーワード「{keyword}」の検索結果が0件でした。")

    top_item = items[0]
    image_url, width, height = pick_primary_image(top_item)
    return SearchImageResult(
        asin=(top_item.get("asin") or "").strip(),
        title=(
            top_item.get("itemInfo", {})
            .get("title", {})
            .get("displayValue", "")
            .strip()
        ),
        image_url=image_url,
        width=width,
        height=height,
    )


def _extract_items_from_get_items_response(payload: dict) -> list[dict]:
    for items in (
        payload.get("itemsResult", {}).get("items", []),
        payload.get("getItemsResult", {}).get("items", []),
        payload.get("items", []),
        payload.get("data", {}).get("items", []),
    ):
        if isinstance(items, list) and items:
            return items
    return []


def get_item_image(
    asin: str,
    access_token: str,
    marketplace: str = DEFAULT_MARKETPLACE,
    associate_tag: str = DEFAULT_ASSOCIATE_TAG,
) -> SearchImageResult:
    response = post_creators_api(
        GET_ITEMS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-marketplace": marketplace,
        },
        payload={
            "itemIds": [asin],
            "partnerTag": associate_tag,
            "marketplace": marketplace,
            "resources": DEFAULT_RESOURCES,
        },
        timeout=30,
    )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"GetItems に失敗しました: {response.status_code} {response.text[:300]}"
        )

    items = _extract_items_from_get_items_response(response.json())
    if not items:
        raise AmazonCreatorsApiError(f"ASIN「{asin}」の GetItems 結果が0件でした。")

    item = items[0]
    image_url, width, height = pick_primary_image(item)
    return SearchImageResult(
        asin=(item.get("asin") or asin).strip().upper(),
        title=(
            item.get("itemInfo", {})
            .get("title", {})
            .get("displayValue", "")
            .strip()
        ),
        image_url=image_url,
        width=width,
        height=height,
    )


def sanitize_filename_part(value: str) -> str:
    sanitized = INVALID_FILENAME_CHARS.sub("_", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.rstrip(". ") or "amazon_image"


def infer_extension_from_url(image_url: str) -> str:
    suffix = Path(urlparse(image_url).path).suffix.lower()
    return suffix if suffix else ".jpg"


def build_output_path(
    keyword: str,
    image_url: str,
    output_dir: Path,
    suffix: str = "",
    extension: str | None = None,
) -> Path:
    date_prefix = datetime.now().strftime("%Y%m%d")
    safe_keyword = sanitize_filename_part(keyword)
    resolved_extension = extension or infer_extension_from_url(image_url)
    return output_dir / f"{date_prefix}_{safe_keyword}{suffix}{resolved_extension}"


def download_image(image_url: str, output_path: Path) -> tuple[Path, int | None, int | None]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(image_url, timeout=60)
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"画像ダウンロードに失敗しました: {response.status_code} {response.text[:300]}"
        )

    output_path.write_bytes(response.content)
    width: int | None = None
    height: int | None = None
    try:
        with Image.open(BytesIO(response.content)) as img:
            width, height = img.size
    except Exception:
        pass
    return output_path, width, height


def build_detail_page_url(asin: str, marketplace: str) -> str:
    return f"https://{marketplace}/dp/{asin}"


def fetch_detail_page_html(asin: str, marketplace: str) -> str:
    response = requests.get(
        build_detail_page_url(asin, marketplace),
        headers=DEFAULT_PAGE_HEADERS,
        timeout=30,
    )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"商品詳細ページ取得に失敗しました: {response.status_code} {response.text[:300]}"
        )
    return response.text


def is_amazon_captcha_html(page_html: str) -> bool:
    lowered = (page_html or "").lower()
    return any(marker in lowered for marker in AMAZON_CAPTCHA_MARKERS)


def build_apify_actor_run_url() -> str:
    actor_name = get_optional_env("APIFY_AMAZON_PRODUCT_ACTOR") or DEFAULT_APIFY_AMAZON_ACTOR
    return f"https://api.apify.com/v2/acts/{actor_name.replace('/', '~')}/run-sync-get-dataset-items"


def extract_hires_from_apify_payload(payload: object) -> Optional[str]:
    if not isinstance(payload, list) or not payload:
        return None

    first_item = payload[0] if isinstance(payload[0], dict) else {}
    if not isinstance(first_item, dict):
        return None

    images = first_item.get("images") or []
    if isinstance(images, list):
        for image_url in images:
            if isinstance(image_url, str) and image_url.strip():
                return image_url.strip()
    return None


def fetch_hires_from_apify(
    asin: str,
    marketplace: str = DEFAULT_MARKETPLACE,
) -> Optional[str]:
    apify_token = get_optional_env("APIFY_API_KEY")
    if not apify_token:
        return None

    actor_url = build_apify_actor_run_url()
    payload = {
        "productUrls": [build_detail_page_url(asin, marketplace)],
        "requestTimeoutSecs": 60,
    }
    try:
        response = requests.post(
            actor_url,
            params={"token": apify_token},
            json=payload,
            timeout=360,
        )
    except requests.RequestException as exc:
        print(f"[WARN] Apify hiRes 取得に失敗しました: {exc}")
        return None

    if not response.ok:
        print(
            "[WARN] Apify hiRes 取得に失敗しました: "
            f"{response.status_code} {response.text[:300]}"
        )
        return None

    try:
        apify_payload = response.json()
    except ValueError as exc:
        print(f"[WARN] Apify hiRes 応答の JSON 解析に失敗しました: {exc}")
        return None

    hires_url = extract_hires_from_apify_payload(apify_payload)
    if hires_url:
        print(f"[INFO] Apify で hiRes 画像を取得しました: {hires_url}")
    else:
        print("[WARN] Apify 応答に hiRes 画像が見つかりませんでした。")
    return hires_url


def extract_hires_from_html(page_html: str) -> Optional[str]:
    landing_tag_match = LANDING_IMAGE_TAG_RE.search(page_html)
    if landing_tag_match:
        landing_tag = landing_tag_match.group(0)
        hires_attr_match = HTML_DATA_OLD_HIRES_RE.search(landing_tag)
        if hires_attr_match:
            hires_url = html.unescape(hires_attr_match.group(1)).strip()
            if hires_url:
                return hires_url

    color_match = COLOR_IMAGES_HIRES_RE.search(page_html)
    if color_match:
        hires_url = html.unescape(color_match.group(1)).replace("\\/", "/").strip()
        if hires_url:
            return hires_url

    return None


def extract_primary_image_from_html(page_html: str) -> Optional[str]:
    landing_tag_match = LANDING_IMAGE_TAG_RE.search(page_html)
    if landing_tag_match:
        landing_tag = landing_tag_match.group(0)
        src_match = HTML_SRC_RE.search(landing_tag)
        if src_match:
            image_url = html.unescape(src_match.group(1)).strip()
            if image_url:
                return image_url
    return None


def extract_title_from_html(page_html: str) -> str:
    product_title_match = PRODUCT_TITLE_RE.search(page_html)
    if product_title_match:
        return html.unescape(product_title_match.group(1)).strip()
    return ""


def quote_onedrive_path(path: str) -> str:
    return "/".join(quote(segment, safe="") for segment in path.split("/"))


def upload_file_to_onedrive(local_path: Path, remote_folder: str) -> str:
    access_token = get_onedrive_access_token()
    remote_path = f"{remote_folder}/{local_path.name}"
    upload_url = (
        f"{GRAPH_API_BASE}/me/drive/root:/{quote_onedrive_path(remote_path)}:/content"
    )
    with open(local_path, "rb") as fh:
        response = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}"},
            data=fh.read(),
            timeout=60,
        )
    if not response.ok:
        raise AmazonCreatorsApiError(
            f"OneDrive アップロードに失敗しました: {response.status_code} {response.text[:300]}"
        )
    return response.json().get("webUrl", "")


def write_github_step_outputs(saved_images: list[SavedImageInfo]) -> None:
    github_output = os.getenv("GITHUB_OUTPUT", "").strip()
    if not github_output:
        return

    lines: list[str] = []
    for image in saved_images:
        prefix = f"amazon_{image.label}"
        lines.extend(
            [
                f"{prefix}_path={image.local_path}",
                f"{prefix}_url={image.image_url}",
            ]
        )
        if image.onedrive_url:
            lines.append(f"{prefix}_onedrive_url={image.onedrive_url}")

    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def remove_local_file_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        print(f"[WARN] 一時ファイル削除失敗: {path} | {exc}")


def save_image(
    label: str,
    keyword: str,
    image_url: str,
    output_dir: Path,
    suffix: str = "",
) -> SavedImageInfo:
    output_path = build_output_path(keyword, image_url, output_dir, suffix=suffix)
    local_path, width, height = download_image(image_url, output_path)
    return SavedImageInfo(
        label=label,
        image_url=image_url,
        local_path=local_path,
        width=width,
        height=height,
    )


def save_and_optionally_upload(
    image: SavedImageInfo,
    remote_folder: str,
) -> SavedImageInfo:
    if is_github_actions():
        image.onedrive_url = upload_file_to_onedrive(image.local_path, remote_folder)
        # note 下書き投稿では、この後 Playwright が同じローカル画像を直接アップロードする。
        # Actions 上でもアップロード完了までは手元に残しておく。
    return image


def create_prepared_note_hero_image(
    source_image: SavedImageInfo,
    keyword: str,
    output_root: Path | None = None,
    canvas_size: tuple[int, int] = NOTE_HERO_CANVAS_SIZE,
) -> SavedImageInfo:
    resolved_output_root = (
        (output_root or infer_output_root_from_image_path(source_image.local_path))
        .expanduser()
        .resolve()
    )
    _, prepared_dir = resolve_image_output_dirs(resolved_output_root)
    prepared_path = build_output_path(
        keyword=keyword,
        image_url=source_image.image_url or source_image.local_path.name,
        output_dir=prepared_dir,
        suffix="_note_hero",
        extension=".jpg",
    )
    prepared_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source_image.local_path) as opened:
            normalized = ImageOps.exif_transpose(opened).convert("RGB")
            contained = ImageOps.contain(
                normalized,
                canvas_size,
                method=Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGB", canvas_size, NOTE_HERO_BACKGROUND_COLOR)
            offset = (
                (canvas_size[0] - contained.width) // 2,
                (canvas_size[1] - contained.height) // 2,
            )
            canvas.paste(contained, offset)
            canvas.save(
                prepared_path,
                format="JPEG",
                quality=NOTE_HERO_JPEG_QUALITY,
                optimize=True,
            )
    except Exception as exc:
        raise AmazonCreatorsApiError(
            f"note HERO 用画像の整形に失敗しました: {source_image.local_path} | {exc}"
        ) from exc

    return SavedImageInfo(
        label="prepared",
        image_url=source_image.image_url,
        local_path=prepared_path,
        width=canvas_size[0],
        height=canvas_size[1],
    )


def resolve_top_item_image(
    keyword: str,
    asin: str,
    access_token: str,
    marketplace: str = DEFAULT_MARKETPLACE,
    partner_tag: str = DEFAULT_ASSOCIATE_TAG,
) -> tuple[SearchImageResult, str]:
    normalized_asin = (asin or "").strip().upper()
    if normalized_asin:
        try:
            return (
                get_item_image(
                    asin=normalized_asin,
                    access_token=access_token,
                    marketplace=marketplace,
                    associate_tag=partner_tag,
                ),
                "",
            )
        except AmazonCreatorsApiError as exc:
            print(f"[WARN] GetItems 取得失敗のため詳細ページへフォールバックします: {exc}")

        detail_page_html = fetch_detail_page_html(normalized_asin, marketplace)
        primary_url = extract_primary_image_from_html(detail_page_html)
        if primary_url:
            return (
                SearchImageResult(
                    asin=normalized_asin,
                    title=extract_title_from_html(detail_page_html),
                    image_url=primary_url,
                    width=None,
                    height=None,
                ),
                detail_page_html,
            )

        raise AmazonCreatorsApiError(
            f"ASIN「{normalized_asin}」の商品詳細ページから通常画像を取得できませんでした。"
        )

    return (
        search_top_item_image(
            keyword=keyword,
            access_token=access_token,
            marketplace=marketplace,
            partner_tag=partner_tag,
        ),
        "",
    )


def fetch_and_save_top_images(
    *,
    keyword: str = "",
    asin: str = "",
    output_dir: Path | None = None,
    marketplace: str = DEFAULT_MARKETPLACE,
    partner_tag: str = DEFAULT_ASSOCIATE_TAG,
    onedrive_folder: str = DEFAULT_ONEDRIVE_FOLDER,
) -> FetchTopImagesResult:
    normalized_keyword = (keyword or "").strip()
    normalized_asin = (asin or "").strip().upper()
    if not normalized_keyword and not normalized_asin:
        raise AmazonCreatorsApiError("検索キーワードまたは ASIN のどちらかが必要です。")

    resolved_output_root = (output_dir or resolve_default_output_dir()).expanduser().resolve()
    raw_output_dir, _ = resolve_image_output_dirs(resolved_output_root)
    access_token = get_access_token()
    result, detail_page_html = resolve_top_item_image(
        keyword=normalized_keyword,
        asin=normalized_asin,
        access_token=access_token,
        marketplace=marketplace,
        partner_tag=partner_tag,
    )
    file_keyword = result.asin or normalized_keyword or "amazon_image"

    api_image = save_image(
        label="api",
        keyword=file_keyword,
        image_url=result.image_url,
        output_dir=raw_output_dir,
    )
    api_image = save_and_optionally_upload(
        api_image,
        build_remote_image_folder(onedrive_folder, RAW_SUBDIR_NAME),
    )

    hires_image: Optional[SavedImageInfo] = None
    hires_url = fetch_hires_from_apify(result.asin, marketplace=marketplace)
    if not hires_url:
        if not detail_page_html:
            detail_page_html = fetch_detail_page_html(result.asin, marketplace)
        if is_amazon_captcha_html(detail_page_html):
            print("[WARN] Amazon 商品詳細ページが captcha 応答でした。")
        hires_url = extract_hires_from_html(detail_page_html)
    if hires_url:
        hires_image = save_image(
            label="hires",
            keyword=file_keyword,
            image_url=hires_url,
            output_dir=raw_output_dir,
            suffix="_hires",
        )
        hires_image = save_and_optionally_upload(
            hires_image,
            build_remote_image_folder(onedrive_folder, RAW_SUBDIR_NAME),
        )
    else:
        print("[WARN] hiRes 画像は見つかりませんでした。通常版のみ保存します。")

    prepared_image: Optional[SavedImageInfo] = None
    prepared_source = hires_image or api_image
    try:
        prepared_image = create_prepared_note_hero_image(
            source_image=prepared_source,
            keyword=file_keyword,
            output_root=resolved_output_root,
        )
        prepared_image = save_and_optionally_upload(
            prepared_image,
            build_remote_image_folder(onedrive_folder, PREPARED_SUBDIR_NAME),
        )
    except AmazonCreatorsApiError as exc:
        print(f"[WARN] note HERO 用の整形画像生成に失敗しました: {exc}")

    saved_images = [api_image]
    if hires_image:
        saved_images.append(hires_image)
    if prepared_image:
        saved_images.append(prepared_image)
    write_github_step_outputs(saved_images)

    return FetchTopImagesResult(
        asin=result.asin,
        title=result.title,
        api_image=api_image,
        hires_image=hires_image,
        prepared_image=prepared_image,
        detail_page_url=build_detail_page_url(result.asin, marketplace),
    )


def parse_args() -> argparse.Namespace:
    default_output_dir = resolve_default_output_dir()
    parser = argparse.ArgumentParser(
        description="Creator API 画像と hiRes 画像を保存します。"
    )
    parser.add_argument("keyword", help="Amazon で検索するキーワード")
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir),
        help=(
            "保存先ルート。raw / prepared サブフォルダを自動作成します。ローカル既定値は "
            f"{DEFAULT_LOCAL_OUTPUT_DIR}、GitHub Actions では "
            f"%%RUNNER_TEMP%%\\{DEFAULT_ACTIONS_SUBDIR} です。"
        ),
    )
    parser.add_argument(
        "--marketplace",
        default=os.getenv("AMAZON_MARKETPLACE", DEFAULT_MARKETPLACE),
        help=f"Creators API の marketplace。既定値: {DEFAULT_MARKETPLACE}",
    )
    parser.add_argument(
        "--partner-tag",
        default=os.getenv("AMAZON_ASSOCIATE_TAG", DEFAULT_ASSOCIATE_TAG),
        help=f"Creators API の partnerTag。既定値: {DEFAULT_ASSOCIATE_TAG}",
    )
    parser.add_argument(
        "--onedrive-folder",
        default=os.getenv("AMAZON_TOP_IMAGE_ONEDRIVE_FOLDER", DEFAULT_ONEDRIVE_FOLDER),
        help=f"GitHub Actions 時の OneDrive 保存先。既定値: {DEFAULT_ONEDRIVE_FOLDER}",
    )
    return parser.parse_args()


def print_saved_image(image: SavedImageInfo) -> None:
    print(f"[INFO] {image.label} 画像URL: {image.image_url}")
    print(f"[INFO] {image.label} 保存先: {image.local_path}")
    if image.width and image.height:
        print(f"[INFO] {image.label} 画像サイズ: {image.width}x{image.height}")
    if image.onedrive_url:
        print(f"[INFO] {image.label} OneDrive URL: {image.onedrive_url}")


def main() -> int:
    args = parse_args()
    keyword = args.keyword.strip()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not keyword:
        raise AmazonCreatorsApiError("検索キーワードが空です。")

    print(f"[INFO] 検索キーワード: {keyword}")
    print(f"[INFO] 保存先: {output_dir}")
    print(f"[INFO] 実行環境: {'GitHub Actions' if is_github_actions() else 'ローカル'}")

    fetch_result = fetch_and_save_top_images(
        keyword=keyword,
        output_dir=output_dir,
        marketplace=args.marketplace,
        partner_tag=args.partner_tag,
        onedrive_folder=args.onedrive_folder,
    )

    print(f"[INFO] 検索1位タイトル: {fetch_result.title}")
    print(f"[INFO] ASIN: {fetch_result.asin}")
    print_saved_image(fetch_result.api_image)
    if fetch_result.hires_image:
        print_saved_image(fetch_result.hires_image)
    if fetch_result.prepared_image:
        print_saved_image(fetch_result.prepared_image)
    if os.getenv("GITHUB_OUTPUT", "").strip():
        print("[INFO] GitHub Actions の step output に画像情報を書き出しました。")
    print("[OK] 画像保存処理が完了しました。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AmazonCreatorsApiError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)
