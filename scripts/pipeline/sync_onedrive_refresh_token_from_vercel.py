import base64
import json
import os
import sys

import requests

SECRET_NAME = "ONEDRIVE_REFRESH_TOKEN"
DEFAULT_VERCEL_URL = "https://blog-vercel-dun.vercel.app"
DEFAULT_REPOSITORY = "seahirodigital/Blog_Vercel"


def _response_preview(response: requests.Response, limit: int = 800) -> str:
    text = response.text or ""
    try:
        text = json.dumps(response.json(), ensure_ascii=False)
    except ValueError:
        pass
    return text[:limit]


def _fetch_refresh_token_from_vercel() -> str:
    vercel_url = os.getenv("VERCEL_URL", DEFAULT_VERCEL_URL).rstrip("/")
    sync_secret = os.getenv("ONEDRIVE_SYNC_SECRET") or os.getenv("ONEDRIVE_CLIENT_SECRET")
    if not sync_secret:
        raise RuntimeError("ONEDRIVE_SYNC_SECRET または ONEDRIVE_CLIENT_SECRET が未設定です。")

    response = requests.post(
        f"{vercel_url}/api/onedrive-token-sync",
        headers={"x-onedrive-sync-secret": sync_secret},
        timeout=90,
    )
    if not response.ok:
        raise RuntimeError(f"Vercel OneDrive token 同期APIが失敗しました: {response.status_code} {_response_preview(response)}")

    payload = response.json()
    refresh_token = str(payload.get("refreshToken") or "").strip()
    if not refresh_token:
        raise RuntimeError(f"Vercel OneDrive token 同期APIの応答に refreshToken がありません: {_response_preview(response)}")
    return refresh_token


def _write_github_env(refresh_token: str) -> None:
    env_path = os.getenv("GITHUB_ENV")
    if not env_path:
        return

    with open(env_path, "a", encoding="utf-8") as env_file:
        env_file.write("ONEDRIVE_REFRESH_TOKEN<<__ONEDRIVE_REFRESH_TOKEN__\n")
        env_file.write(refresh_token)
        env_file.write("\n__ONEDRIVE_REFRESH_TOKEN__\n")


def _update_github_secret(refresh_token: str) -> None:
    github_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT")
    repository = os.getenv("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    if not github_token:
        print("   ℹ️ GITHUB_TOKEN/GH_PAT 未設定のため、GitHub Secret更新をスキップします。")
        return

    try:
        import nacl.encoding
        import nacl.public
    except ImportError as error:
        raise RuntimeError("PyNaCl が未インストールのため、GitHub Secretを更新できません。") from error

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api_base = f"https://api.github.com/repos/{repository}"
    key_res = requests.get(f"{api_base}/actions/secrets/public-key", headers=headers, timeout=30)
    if not key_res.ok:
        raise RuntimeError(f"GitHub公開鍵取得に失敗しました: {key_res.status_code} {_response_preview(key_res)}")

    key_data = key_res.json()
    public_key = nacl.public.PublicKey(key_data["key"].encode(), nacl.encoding.Base64Encoder)
    sealed_box = nacl.public.SealedBox(public_key)
    encrypted_value = base64.b64encode(sealed_box.encrypt(refresh_token.encode())).decode()
    put_res = requests.put(
        f"{api_base}/actions/secrets/{SECRET_NAME}",
        headers=headers,
        json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
        timeout=30,
    )
    if put_res.status_code not in (201, 204):
        raise RuntimeError(f"GitHub Secret更新に失敗しました: {put_res.status_code} {_response_preview(put_res)}")
    print(f"   ✅ GitHub Actions Secret {SECRET_NAME} をVercel側の有効トークンで更新しました。")


def main() -> int:
    try:
        refresh_token = _fetch_refresh_token_from_vercel()
        print(f"::add-mask::{refresh_token}")
        _write_github_env(refresh_token)
        _update_github_secret(refresh_token)
        print("   ✅ このActions実行で使う OneDrive refresh token をVercelから同期しました。")
        return 0
    except Exception as error:
        print(f"   ❌ OneDrive refresh token のVercel同期に失敗しました: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
