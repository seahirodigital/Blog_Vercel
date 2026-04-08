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
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import requests
from PIL import Image


TOKEN_URL = "https://api.amazon.co.jp/auth/o2/token"
SEARCH_ITEMS_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
ONEDRIVE_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

DEFAULT_MARKETPLACE = "www.amazon.co.jp"
DEFAULT_ASSOCIATE_TAG = "hiroshit-22"
DEFAULT_LOCAL_OUTPUT_DIR = Path(
    r"C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog"
)
DEFAULT_ACTIONS_SUBDIR = "amazon_top_images"
DEFAULT_ONEDRIVE_FOLDER = "Vercel_Blog/ダウンロード_トップ画像_vercel_blog"
DEFAULT_RESOURCES = [
    "itemInfo.title",
    "images.primary.large",
    "images.primary.medium",
    "images.primary.small",
]
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
LANDING_HIRES_RE = re.compile(
    r'id="landingImage"[^>]*\bdata-old-hires="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
COLOR_IMAGES_HIRES_RE = re.compile(
    r"""colorImages'\s*:\s*\{\s*'initial'\s*:\s*\[\s*\{"hiRes":"(https:[^"]+)""",
    re.DOTALL,
)
DEFAULT_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}


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


def is_github_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"


def resolve_default_output_dir() -> Path:
    runner_temp = os.getenv("RUNNER_TEMP", "").strip()
    if is_github_actions() and runner_temp:
        return Path(runner_temp) / DEFAULT_ACTIONS_SUBDIR
    return DEFAULT_LOCAL_OUTPUT_DIR


def get_env_or_raise(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AmazonCreatorsApiError(
            f"環境変数 {name} が未設定です。PowerShell または GitHub Actions の環境変数を確認してください。"
        )
    return value


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
    response = requests.post(
        SEARCH_ITEMS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-marketplace": marketplace,
        },
        json={
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


def sanitize_filename_part(value: str) -> str:
    sanitized = INVALID_FILENAME_CHARS.sub("_", value).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.rstrip(". ") or "amazon_image"


def infer_extension_from_url(image_url: str) -> str:
    suffix = Path(urlparse(image_url).path).suffix.lower()
    return suffix if suffix else ".jpg"


def build_output_path(keyword: str, image_url: str, output_dir: Path, suffix: str = "") -> Path:
    date_prefix = datetime.now().strftime("%Y%m%d")
    safe_keyword = sanitize_filename_part(keyword)
    extension = infer_extension_from_url(image_url)
    return output_dir / f"{date_prefix}_{safe_keyword}{suffix}{extension}"


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


def extract_hires_from_html(page_html: str) -> Optional[str]:
    landing_match = LANDING_HIRES_RE.search(page_html)
    if landing_match:
        hires_url = html.unescape(landing_match.group(1)).strip()
        if hires_url:
            return hires_url

    color_match = COLOR_IMAGES_HIRES_RE.search(page_html)
    if color_match:
        hires_url = html.unescape(color_match.group(1)).replace("\\/", "/").strip()
        if hires_url:
            return hires_url

    return None


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
        remove_local_file_if_exists(image.local_path)
    return image


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
            "保存先。ローカル既定値は "
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

    access_token = get_access_token()
    result = search_top_item_image(
        keyword=keyword,
        access_token=access_token,
        marketplace=args.marketplace,
        partner_tag=args.partner_tag,
    )

    saved_images: list[SavedImageInfo] = []

    api_image = save_image(
        label="api",
        keyword=keyword,
        image_url=result.image_url,
        output_dir=output_dir,
    )
    saved_images.append(save_and_optionally_upload(api_image, args.onedrive_folder))

    detail_page_html = fetch_detail_page_html(result.asin, args.marketplace)
    hires_url = extract_hires_from_html(detail_page_html)
    if hires_url:
        hires_image = save_image(
            label="hires",
            keyword=keyword,
            image_url=hires_url,
            output_dir=output_dir,
            suffix="_hires",
        )
        saved_images.append(save_and_optionally_upload(hires_image, args.onedrive_folder))
    else:
        print("[WARN] hiRes 画像は見つかりませんでした。Creator API 版のみ保存します。")

    write_github_step_outputs(saved_images)

    print(f"[INFO] 検索1位タイトル: {result.title}")
    print(f"[INFO] ASIN: {result.asin}")
    for image in saved_images:
        print_saved_image(image)
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
