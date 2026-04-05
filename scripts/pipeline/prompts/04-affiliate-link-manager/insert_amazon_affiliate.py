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
TRIM_CHARS = "：:・　 \t\r\n"


# ── ① 商品名抽出 ────────────────────────────────────────
def extract_product_name(title: str) -> str:
    """
    タイトルから商品名部分を抽出する。
    例: "Bowers & Wilkins PI8 レビュー比較まとめ：高音質..." → "Bowers & Wilkins PI8"
    """
    if not title:
        return ""
    for marker in TITLE_MARKERS:
        if marker in title:
            name = title.split(marker, 1)[0]
            return name.strip(TRIM_CHARS)
    return title.strip(TRIM_CHARS)


# ── ② Amazon検索 → ASIN取得 ────────────────────────────
def _keyword_matches_title(keywords: list[str], title: str) -> bool:
    """
    商品ページのタイトルに、検索キーワードがすべて含まれるか確認（AND条件）。
    大文字小文字を無視して部分一致。
    """
    title_lower = title.lower()
    return all(kw.lower() in title_lower for kw in keywords)


def fetch_amazon_asin(product_name: str) -> str | None:
    """
    Playwrightで Amazon.co.jp を検索し、広告を除外かつ商品名が一致する
    最初の商品のASINを返す。
    検索キーワードと一致しない Organic 商品（別ブランド等）は除外する。
    失敗時は None を返す。
    """
    if not product_name:
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   [WARN] playwright未インストール - Amazonアフィリエイト挿入スキップ")
        return None

    search_url = AMAZON_SEARCH_BASE + quote(product_name)
    print(f"   [SEARCH] Amazon: {product_name}")

    # 商品名をスペースで分割してマッチ用キーワードを生成
    # 例: "Bowers & Wilkins PI8" → ["Bowers", "Wilkins", "PI8"]
    keywords = [w for w in product_name.replace("&", " ").split() if len(w) >= 2]

    # 検索結果から Organic 商品を最大10件取得
    js_get_organics = """
    () => {
        const products = Array.from(document.querySelectorAll('div[data-asin]'));
        const organics = [];
        for (const p of products) {
            const asin = p.getAttribute('data-asin');
            if (!asin || asin.length !== 10) continue;
            const isAd = p.classList.contains('AdHolder') ||
                !!p.querySelector('.puis-sponsored-label-text') ||
                (p.innerText && (p.innerText.includes('スポンサー') || p.innerText.includes('Sponsored')));
            if (!isAd) organics.push(asin);
            if (organics.length >= 10) break;
        }
        return organics;
    }
    """

    # 商品ページのタイトル取得
    js_get_title = """
    () => {
        const el = document.querySelector('#productTitle') ||
                   document.querySelector('#title span') ||
                   document.querySelector('.product-title-word-break');
        return el ? el.innerText.trim() : '';
    }
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # 検索結果ページ
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("div[data-asin]", timeout=15000)
            except Exception:
                print("   [WARN] Amazon検索結果の読み込みタイムアウト")
                browser.close()
                return None

            organic_asins = page.evaluate(js_get_organics)
            print(f"   [INFO] Organic候補: {len(organic_asins)}件 → タイトル検証開始")

            # 各商品ページを開いてタイトルを確認
            for asin in organic_asins:
                product_url = f"https://www.amazon.co.jp/dp/{asin}"
                page.goto(product_url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(800)
                title = page.evaluate(js_get_title)
                matched = _keyword_matches_title(keywords, title)
                print(f"   [CHECK] {asin} | match={matched} | {title[:60]}")
                if matched:
                    browser.close()
                    print(f"   [OK] ASIN確定: {asin}")
                    return asin

            browser.close()
            print("   [WARN] 商品名が一致するOrganicな商品が見つかりません")
            return None
    except Exception as e:
        print(f"   [WARN] Amazon検索失敗: {e}")
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

    # H1をmarkdown本文から直接抽出（パイプラインが生成したブログ記事タイトルを使用）
    h1_title = _extract_h1_from_markdown(markdown_content)
    source_title = h1_title if h1_title else article_title
    if not source_title:
        print("   [WARN] タイトル取得失敗（H1なし・引数なし）- スキップ")
        return markdown_content
    print(f"   [LIST] タイトル: {source_title}")

    product_name = extract_product_name(source_title)
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
