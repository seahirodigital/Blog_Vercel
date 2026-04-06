"""
Amazonアフィリエイトリンク自動挿入モジュール

【処理フロー】
1. 記事タイトルから商品名を抽出（「XXX レビュー比較まとめ：〜」の XXX 部分）
2. Playwrightで Amazon 検索を実行
3. 検索結果から広告（スポンサー）を除外した1番目の商品のASINを取得
4. アフィリエイトリンクを生成（tag=hiroshit-22）
5. 記事に挿入
   (a) 最初に出現する▼の直前に1つ
   (b) 偶数番目のH2（2,4,6...番目）の直前
       ※ public/index.html のクリップボード添付アイコンと同一ロジック

【安全性】
- 商品名抽出失敗 / ASIN取得失敗 / H2が無い等の場合は原文を返す
- 既存の insert_affiliate_links.py は無改変
"""

import os
from urllib.parse import quote

ASSOCIATE_TAG = "hiroshit-22"
AMAZON_SEARCH_BASE = "https://www.amazon.co.jp/s?k="

# 商品名抽出用の区切りマーカー（優先度順）
TITLE_MARKERS = [
    "レビュー比較まとめ",
    "レビュー比較",
    "比較まとめ",
    "レビュー",
    "比較",
    "まとめ",
]

# タイトル末尾からトリミングする記号
TRIM_CHARS = "：:・　 \t\r\n、，,"

# 商品名として不適切な日本語の説明ワード（これ以降を切り捨て）
JP_NOISE_WORDS = [
    "デスクトップ", "スピーカー", "イヤホン", "ヘッドホン", "ヘッドフォン",
    "ワイヤレス", "ノイズ", "対応", "搭載", "機能", "高音質", "ハイレゾ",
    "コスパ", "おすすめ", "レビュー", "比較", "まとめ",
]


# ── ① 商品名抽出 ────────────────────────────────────────
def _trim_jp_noise(name: str) -> str:
    """
    商品名末尾の日本語説明ワードを除去して、純粋な製品名部分のみ残す。
    例: "Edifier M90 デスクトップスピーカー、高音質..." → "Edifier M90"
    """
    for word in JP_NOISE_WORDS:
        idx = name.find(word)
        if idx > 0:
            name = name[:idx]
    return name.strip(TRIM_CHARS)


def extract_product_name(title: str) -> str:
    """
    タイトルから商品名部分を抽出する。
    例: "Bowers & Wilkins PI8 レビュー比較まとめ：高音質..." → "Bowers & Wilkins PI8"
    例: "Edifier M90 デスクトップスピーカー、高音質PCスピーカーのレビュー比較まとめ"
        → "Edifier M90"
    """
    if not title:
        return ""
    # TITLE_MARKERS で分割（最短になるものを優先）
    for marker in TITLE_MARKERS:
        if marker in title:
            name = title.split(marker, 1)[0]
            name = name.strip(TRIM_CHARS)
            # さらに日本語ノイズワードを除去
            name = _trim_jp_noise(name)
            return name
    # マーカーがない場合：日本語ノイズワードのみで除去を試みる
    return _trim_jp_noise(title.strip(TRIM_CHARS))


def _extract_product_name_from_h2s(markdown: str) -> str:
    """
    H2見出しの共通語句から商品名を抽出するフォールバック戦略。
    H2が "## Edifier M90 レビュー比較まとめ：結論" のように
    共通プレフィックスを持つ場合に有効。
    """
    h2_lines = [
        ln.strip()[3:].strip()  # "## " を除去
        for ln in markdown.splitlines()
        if ln.strip().startswith("## ")
    ]
    if len(h2_lines) < 2:
        return ""

    # 共通プレフィックスをトークン（スペース区切り）単位で求める
    first_tokens = h2_lines[0].split()
    common_tokens = []
    for token in first_tokens:
        if all(token in h2 for h2 in h2_lines[1:]):
            common_tokens.append(token)
        else:
            break  # 最初に一致しなくなったら終了

    if not common_tokens:
        return ""

    common_prefix = " ".join(common_tokens)
    return extract_product_name(common_prefix)


# ── ② Amazon検索 → ASIN取得 ────────────────────────────

def _fetch_asin_via_creators_api(product_name: str, keywords: list[str]) -> str | None:
    """
    Amazon Creators API (OAuth2) の SearchItems でASINを取得する（最優先）。
    公式APIのためクラウドIPのブロックがなく、GitHub Actionsから直接呼べる。

    必要な環境変数:
      AMAZON_CLIENT_ID     : Creators API クライアントID
      AMAZON_CLIENT_SECRET : Creators API クライアントシークレット
    """
    import requests as req
    import re

    client_id = os.environ.get("AMAZON_CLIENT_ID", "")
    client_secret = os.environ.get("AMAZON_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("   [WARN] Creators API: AMAZON_CLIENT_ID または AMAZON_CLIENT_SECRET が未設定 → スキップ")
        return None

    # Step1: OAuth2 クライアントクレデンシャルでアクセストークン取得
    try:
        # 日本向けトークンエンドポイント
        token_res = req.post(
            "https://api.amazon.co.jp/auth/o2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "creatorsapi::default",
            },
            timeout=15,
        )
        if not token_res.ok:
            print(f"   [WARN] Creators API トークン取得失敗: {token_res.status_code} | {token_res.text[:200]}")
            return None
        access_token = token_res.json().get("access_token", "")
        if not access_token:
            print("   [WARN] Creators API: アクセストークンが空")
            return None
        print("   [INFO] Creators API: アクセストークン取得成功")
    except Exception as e:
        print(f"   [WARN] Creators API トークン取得例外: {e}")
        return None

    # Step2: SearchItems でキーワード検索
    try:
        search_res = req.post(
            "https://creatorsapi.amazon/catalog/v1/searchItems",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "x-marketplace": "www.amazon.co.jp",
            },
            json={
                "keywords": product_name,
                "partnerTag": ASSOCIATE_TAG,
                "marketplace": "www.amazon.co.jp",
                "resources": ["itemInfo.title"],
                "itemCount": 5,
            },
            timeout=20,
        )
        if not search_res.ok:
            print(f"   [WARN] Creators API SearchItems失敗: {search_res.status_code} | {search_res.text[:300]}")
            return None

        data = search_res.json()
        items = data.get("searchResult", {}).get("items", [])
        print(f"   [INFO] Creators API: {len(items)}件の検索結果")

        asin_re = re.compile(r"[A-Z0-9]{10}")

        for item in items:
            asin = item.get("asin", "")
            if not asin or not asin_re.fullmatch(asin):
                continue
            title = (item.get("itemInfo", {}).get("title", {}).get("displayValue", "") or "").lower()
            matched = all(kw.lower() in title for kw in keywords)
            print(f"   [CHECK] {asin} | match={matched} | {title[:60]}")
            if matched:
                print(f"   [OK] Creators API ASIN確定: {asin}")
                return asin

        # AND条件マッチなし → 最初のASINをフォールバック
        if items:
            asin = items[0].get("asin", "")
            if asin:
                title = items[0].get("itemInfo", {}).get("title", {}).get("displayValue", "")
                print(f"   [OK] Creators API ASIN確定(フォールバック): {asin} | {title[:60]}")
                return asin

        print("   [WARN] Creators API: 検索結果にASINが見つかりません")
        return None
    except Exception as e:
        print(f"   [WARN] Creators API SearchItems例外: {e}")
        return None


def fetch_amazon_asin(product_name: str) -> str | None:
    """
    Amazon.co.jp の ASIN を取得する。
    Amazon Creators API（公式）を利用して取得する。過去のスクレイピング・CSE・Vercel等のフォールバックは廃止。
    """
    if not product_name:
        return None

    print(f"   [SEARCH] Amazon: {product_name}")
    keywords = [w for w in product_name.replace("&", " ").split() if len(w) >= 2]

    # Amazon Creators API（公式・IPブロックなし）
    asin = _fetch_asin_via_creators_api(product_name, keywords)
    if asin:
        return asin

    print("   [WARN] Creators API でASINを取得できませんでした。")
    return None


# ── ③ アフィリエイトリンク生成 ──────────────────────────
def build_affiliate_link(asin: str) -> str:
    """ASINからアフィリエイトリンクを生成"""
    return f"https://www.amazon.co.jp/dp/{asin}/ref=nosim?tag={ASSOCIATE_TAG}"


# ── ④ 記事への挿入 ──────────────────────────────────────
def _insertion_positions(lines: list[str]) -> list[int]:
    """
    挿入位置の行番号リストを返す。
    (a) 最初の▼の直前
    (b) 偶数番目のH2（1-indexedで2,4,6...→0-indexedで1,3,5...）の直前
    """
    positions: list[int] = []

    # (a) 最初の▼
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("▼"):
            positions.append(i)
            break

    # (b) 偶数番目H2
    h2_line_indices = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    for idx, line_idx in enumerate(h2_line_indices):
        if idx % 2 == 1:  # 2番目, 4番目, 6番目...
            positions.append(line_idx)

    # 重複除去（▼とH2の位置が偶然同じ行になるケースへの保険）
    return sorted(set(positions))


# ── メインエントリーポイント ────────────────────────────
def _extract_h1_from_markdown(markdown: str) -> str:
    """
    Markdownの先頭付近から `# タイトル` 形式のH1を抽出して返す。
    見つからなければ空文字列を返す。
    """
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""


def insert_amazon_affiliate(markdown_content: str, article_title: str = "") -> str:
    """
    記事タイトルから Amazonアフィリエイトリンクを生成し、Markdownに挿入して返す。
    タイトル解析はmarkdown内のH1を優先し、なければ article_title 引数にフォールバック。
    失敗時は元の markdown_content をそのまま返す。
    """
    print("   [SHOP] Amazonアフィリエイト自動挿入開始")

    # 商品名抽出：H1 → article_title → H2共通語句 の優先順でフォールバック
    h1_title = _extract_h1_from_markdown(markdown_content)
    source_title = h1_title if h1_title else article_title

    product_name = ""
    if source_title:
        print(f"   [LIST] タイトル: {source_title}")
        product_name = extract_product_name(source_title)

    # H1/引数から取れない or 長すぎる場合 → H2共通語句で再抽出
    if not product_name or len(product_name) > 30:
        h2_name = _extract_product_name_from_h2s(markdown_content)
        if h2_name and len(h2_name) < len(product_name or "x" * 999):
            print(f"   [INFO] H2共通語句から商品名再抽出: {h2_name}")
            product_name = h2_name

    if not product_name:
        print("   [WARN] 商品名抽出失敗 - スキップ")
        return markdown_content
    print(f"   [PKG] 商品名: {product_name}")

    asin = fetch_amazon_asin(product_name)
    if not asin:
        return markdown_content

    link = build_affiliate_link(asin)
    print(f"   [LINK] リンク: {link}")

    lines = markdown_content.splitlines(keepends=True)
    positions = _insertion_positions(lines)
    if not positions:
        print("   [WARN] 挿入位置が見つかりません（▼も偶数H2も無し）- スキップ")
        return markdown_content

    # 挿入ブロック（前後に空行を確保）
    insert_block = f"\n{link}\n\n"

    # 行番号ズレを防ぐため後方から逆順に挿入
    for pos in sorted(positions, reverse=True):
        lines = lines[:pos] + [insert_block] + lines[pos:]

    print(f"   [OK] Amazonアフィリエイトリンク挿入完了（{len(positions)}箇所）")
    return "".join(lines)


# ── CLI実行（デバッグ用）────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        article_file = sys.argv[1]
        title = sys.argv[2]
        with open(article_file, "r", encoding="utf-8") as f:
            md = f.read()
        result = insert_amazon_affiliate(md, title)
        with open(article_file, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[OK] {article_file} への挿入完了")
    else:
        print("使用方法: python insert_amazon_affiliate.py <article.md> <記事タイトル>")
