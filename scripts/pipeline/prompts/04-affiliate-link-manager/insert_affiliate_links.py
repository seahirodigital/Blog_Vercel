"""
アフィリエイトリンク挿入 v4
OneDriveを直接参照し、MEMO1の▼ブロックをルールに基づいて挿入する

【挿入ルール】
1. H2「結論」の直前: MEMO1全文（手動リンク用・スクリプトは挿入のみ）
2. 奇数番目のH2で1番目を除く（3,5,7...番目）の直前: ▼ブロック1つをランダム選択（重複なし）
   ※1番目・偶数番目のH2直前は手動挿入のためスクリプトでは何もしない
   ※「結論」H2は1で処理済みのためスキップ
3. 免責事項は最初の挿入位置に1回のみ付与（各ブロックには付与しない）
4. 記事末尾への挿入は行わない
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
    return res.content.decode("utf-8")


# ── パーサー ────────────────────────────────────────────
def _parse_memo1(raw: str) -> str:
    """
    MEMO1のコンテンツを取得。
    ===MEMO1=== マーカーおよび --- 以前のメタデータを除去し、純粋な本文のみ返す。
    記事本文に ===MEMOx=== などの文字が混入しないよう保証する。
    """
    parts = re.split(r"===MEMO(\d+)===", raw)
    for i in range(1, len(parts), 2):
        if int(parts[i]) == 1:
            body = (parts[i + 1] if i + 1 < len(parts) else "").strip()
            # --- セパレータがある場合はその前のメタデータを除去
            if "---" in body:
                _, content = body.split("---", 1)
                return content.strip()
            return body
    return ""


def _split_blocks(content: str) -> list[str]:
    """
    ▼から次の▼までを1ブロックとして分割。
    ▼で始まらない先頭部分は破棄する。
    """
    blocks = re.split(r'(?=▼)', content)
    return [b.strip() for b in blocks if b.strip() and b.strip().startswith("▼")]


# ── 挿入ロジック ────────────────────────────────────────
def _insert_before(lines: list[str], index: int, block: str) -> list[str]:
    """指定行インデックスの直前にブロックを挿入"""
    insert = ["\n", block + "\n", "\n"]
    return lines[:index] + insert + lines[index:]


# ── メインエントリーポイント ────────────────────────────
def insert_affiliate_links(markdown_content: str) -> str:
    """
    OneDriveからMEMO1を取得し、ルールに従ってMarkdownに挿入して返す。
    失敗時は元の文字列をそのまま返す。
    """
    try:
        raw = _fetch_from_onedrive()
    except Exception as e:
        print(f"   ⚠️ OneDrive取得失敗（ローカルフォールバック試行）: {e}")
        local_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "affiliate_links.txt"
        )
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                raw = f.read()
            print("   ✅ ローカルファイルで代替")
        else:
            print("   ❌ ローカルファイルも未検出 - アフィリ挿入スキップ")
            return markdown_content

    memo1_content = _parse_memo1(raw)
    if not memo1_content:
        print("   ⚠️ MEMO1が空または未検出 - アフィリ挿入スキップ")
        return markdown_content

    blocks = _split_blocks(memo1_content)
    print(f"   📋 ▼ブロック数: {len(blocks)}件")

    lines = markdown_content.splitlines(keepends=True)
    h2_indices = [i for i, ln in enumerate(lines) if ln.startswith("## ")]

    # ── 挿入計画を作成（後で逆順に適用し行番号ズレを防ぐ）──
    insertions = []  # [(line_index, text), ...]

    # 1. H2「結論」の直前（固定: MEMO1全文）
    conclusion_idx = next((i for i in h2_indices if "結論" in lines[i]), None)
    if conclusion_idx is not None:
        insertions.append((conclusion_idx, memo1_content))
        print("   ✅ 「結論」直前: MEMO1全文を挿入予約")
    else:
        print("   ⚠️ H2「結論」が見つかりません - 固定挿入をスキップ")

    # 2. 奇数番目のH2で1番目を除く（3,5,7...）直前（ランダム▼ブロック、重複なし）
    random.shuffle(blocks)
    block_iter = iter(blocks)
    for count, h2_idx in enumerate(h2_indices, start=1):
        if count == 1 or count % 2 == 0:
            continue  # 1番目・偶数番目はスキップ（手動挿入）
        if h2_idx == conclusion_idx:
            continue  # 結論は1で処理済みのためスキップ
        try:
            block = next(block_iter)
            insertions.append((h2_idx, block))
            print(f"   ✅ {count}番目H2直前: ▼ブロック挿入予約")
        except StopIteration:
            print(f"   ⚠️ {count}番目H2: 挿入可能なブロックが不足 - スキップ")
            break

    # 免責事項を最も早い挿入位置（行番号が最小）に1回のみ付与
    if insertions:
        insertions.sort(key=lambda x: x[0])
        first_pos, first_text = insertions[0]
        insertions[0] = (first_pos, first_text + f"\n\n{DISCLAIMER}")

    # 挿入位置が大きい順に適用（行番号のズレを防ぐ）
    insertions.sort(key=lambda x: x[0], reverse=True)
    for pos, text in insertions:
        lines = _insert_before(lines, pos, text)

    print("   ✅ アフィリエイトリンク挿入完了")
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
