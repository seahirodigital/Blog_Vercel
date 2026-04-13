import re
from typing import Any

import requests

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_USER_AGENT = "DiscordBot (https://github.com/discord/discord-api-docs, 10)"
X_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/(?:i/(?:status|article)|[^/\s]+/status)/[0-9]+",
    flags=re.I,
)


def _request_messages(bot_token: str, channel_id: str, after_message_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    params = {"limit": str(max(1, min(limit, 100)))}
    if after_message_id:
        params["after"] = str(after_message_id)

    response = requests.get(
        f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {bot_token}",
            "User-Agent": DISCORD_USER_AGENT,
        },
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def extract_x_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in X_URL_PATTERN.findall(str(text or "")):
        normalized = match.rstrip(")]}>,.\"'")
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def fetch_channel_posts(
    bot_token: str,
    guild_id: str,
    channel_id: str,
    channel_name: str,
    after_message_id: str = "",
    max_pages: int = 5,
) -> dict[str, Any]:
    scanned_messages = 0
    last_message_id = str(after_message_id or "")
    discovered_posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    current_after = str(after_message_id or "")
    for _ in range(max(1, max_pages)):
        messages = _request_messages(bot_token, channel_id, after_message_id=current_after, limit=100)
        if not messages:
            break

        messages = sorted(messages, key=lambda item: int(item.get("id", "0")))
        scanned_messages += len(messages)
        current_after = str(messages[-1].get("id", current_after))
        last_message_id = current_after

        for message in messages:
            urls = extract_x_urls(message.get("content", ""))
            if not urls:
                continue

            for post_url in urls:
                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)
                discovered_posts.append(
                    {
                        "post_url": post_url,
                        "discord_message_id": str(message.get("id", "")),
                        "discord_channel_id": str(channel_id),
                        "discord_channel_name": channel_name,
                        "discord_author_id": str((message.get("author") or {}).get("id", "")),
                        "discord_author_name": (message.get("author") or {}).get("global_name")
                        or (message.get("author") or {}).get("username", ""),
                        "discord_jump_url": f"https://discord.com/channels/{guild_id}/{channel_id}/{message.get('id', '')}",
                        "observed_at": message.get("timestamp", ""),
                    }
                )

        if len(messages) < 100:
            break

    return {
        "ok": True,
        "posts": discovered_posts,
        "lastMessageId": last_message_id,
        "scannedMessages": scanned_messages,
    }