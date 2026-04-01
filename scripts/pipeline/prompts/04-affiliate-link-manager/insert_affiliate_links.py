"""
アフィリエイトリンク挿入 v2 - C案実装
OneDriveを直接参照し、MEMOごとのルール(mode/position)に基づいて挿入する

【MEMOフォーマット】
===MEMOx===
mode=random        # ランダム位置に挿入
mode=fixed         # position で指定した場所に固定挿入
mode=disabled      # このMEMOをスキップ
position=end           # 末尾
position=start         # 冒頭
position=after_h2      # 最初のH2直後
position=before_h2     # 最初のH2直前
position=after_conclusion  # 「結論」見出し直後
---
（ここからリンク本文）
"""

import os
import re
import random
import requests
from urllib.parse import quote

# ── OneDrive 設定 ──────────────────────────────────────
GRAPH_API = "https://graph.microsoft.com/v1.0"
TOKEN_URL  = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
AFFILIATE_FILE_PATH = (
    "開発/Blog_Vercel/scripts/pipeline/prompts/"
    "04-affiliate-link-manager/affiliate_links.txt"
)

DISCLAIMER = "(Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。)"


# ── OneDrive 認証 ──────────────────────────────────────
def _get_access_token() -> str:
    res = requests.post(TOKEN_URL, data={
        "client_id":     os.environ["ONEDRIVE_CLIENT_ID"],
        "client_secret": os.environ["ONEDRIVE_CLIENT_SECRET"],
        "refresh_token": os.environ["ONEDRIVE_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
        "scope":         "Files.ReadWrite.All offline_access",
    })
    res.raise_for_status()
    return res.json()["access_token"]


def _fetch_from_onedrive() -> str:
    """OneDriveからアフィリエイトリンクファイルを取得して返す"""
    token   = _get_access_token()
    encoded = "/".join(quote(p, safe="") for p in AFFILIATE_FILE_PATH.split("/"))
    url     = f"{GRAPH_API}/me/drive/root:/{encoded}:/content"
    res     = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    res.raise_for_status()
    return res.text


# ── パーサー ────────────────────────────────────────────
def _parse_memos(raw: str) -> list[dict]:
    """
    MEMOセクションをパースして設定リストを返す。
    無効(disabled)や本文が空のMEMOは除外。

    Returns:
        [{"num": 1, "mode": "random", "position": "random", "content": "..."}, ...]
    """
    memos = []
    parts = re.split(r"===MEMO(\d+)===", raw)

    for i in range(1, len(parts), 2):
        num  = int(parts[i])
        body = (parts[i + 1] if i + 1 < len(parts) else "").strip()

        # デフォルト設定
        cfg = {"num": num, "mode": "random", "position": "random"}

        # --- セパレータで メタ / 本文を分割
        if "---" in body:
            meta_str, content = body.split("---", 1)
            for line in meta_str.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip().lower()] = v.strip().lower()
        else:
            content = body  # メタなし（後方互換）

        cfg["content"] = content.strip()

        if cfg["mode"] == "disabled":
            continue
        if not cfg["content"]:
            continue

        memos.append(cfg)

    return memos


# ── 挿入ロジック ────────────────────────────────────────
def _find_h2_positions(lines: list[str]) -> list[int]:
    return [i for i, ln in enumerate(lines) if ln.startswith("## ")]


def _insert_block(lines: list[str], index: int, block: str) -> list[str]:
    insert = ["\n", block + "\n", "\n"]
    return lines[:index] + insert + lines[index:]


def _apply_memo(lines: list[str], memo: dict) -> list[str]:
    content  = memo["content"]
    mode     = memo["mode"]
    position = memo.get("position", "random")
    block    = content + f"\n\n{DISCLAIMER}"

    h2_pos = _find_h2_positions(lines)

    if mode == "fixed":
        if position == "end":
            lines = lines + ["\n\n---\n\n", block + "\n"]

        elif position == "start":
            lines = [block + "\n", "\n"] + lines

        elif position == "after_h2":
            if h2_pos:
                lines = _insert_block(lines, h2_pos[0] + 1, block)
            else:
                lines = lines + ["\n\n---\n\n", block + "\n"]

        elif position == "before_h2":
            if h2_pos:
                lines = _insert_block(lines, h2_pos[0], block)
            else:
                lines = [block + "\n", "\n"] + lines

        elif position == "after_conclusion":
            idx = next(
                (i for i in h2_pos if "結論" in lines[i]),
                None
            )
            if idx is not None:
                lines = _insert_block(lines, idx + 1, block)
            else:
                lines = lines + ["\n\n---\n\n", block + "\n"]

        else:
            # position 未知 → 末尾
            lines = lines + ["\n\n---\n\n", block + "\n"]

    elif mode == "random":
        # 段落境界（空行）の位置を取得してランダム挿入
        para_boundaries = [
            i for i in range(1, len(lines) - 1)
            if not lines[i].strip() and lines[i - 1].strip()
        ]
        if para_boundaries:
            idx = random.choice(para_boundaries)
            lines = _insert_block(lines, idx, block)
        else:
            lines = lines + ["\n\n---\n\n", block + "\n"]

    return lines


# ── メインエントリーポイント ────────────────────────────
def insert_affiliate_links(markdown_content: str) -> str:
    """
    OneDriveからアフィリエイトリンク設定を取得し、
    MEMOごとのルールに従ってMarkdownに挿入して返す。

    Args:
        markdown_content: 挿入前のMarkdown文字列
    Returns:
        挿入後のMarkdown文字列（失敗時は元の文字列をそのまま返す）
    """
    try:
        raw   = _fetch_from_onedrive()
        memos = _parse_memos(raw)
    except Exception as e:
        print(f"   ⚠️ OneDrive取得失敗（ローカルフォールバック試行）: {e}")
        # フォールバック: スクリプトと同階層の local ファイルを参照
        local_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "affiliate_links.txt"
        )
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                raw = f.read()
            memos = _parse_memos(raw)
            print("   ✅ ローカルファイルで代替")
        else:
            print("   ❌ ローカルファイルも未検出 - アフィリ挿入スキップ")
            return markdown_content

    if not memos:
        print("   ⚠️ 有効なMEMOが見つかりません（全disabled or 空）")
        return markdown_content

    print(f"   📋 有効MEMO数: {len(memos)}件")
    lines = markdown_content.splitlines(keepends=True)

    for memo in memos:
        lines = _apply_memo(lines, memo)
        print(f"   ✅ MEMO{memo['num']} 挿入 (mode={memo['mode']}, position={memo.get('position','-')})")

    return "".join(lines)


# ── CLI実行（デバッグ用）────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        article_file = sys.argv[1]
        with open(article_file, "r", encoding="utf-8") as f:
            md = f.read()
        result = insert_affiliate_links(md)
        with open(article_file, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"✅ {article_file} への挿入完了")
    else:
        print("使用方法: python insert_affiliate_links.py <article.md>")
