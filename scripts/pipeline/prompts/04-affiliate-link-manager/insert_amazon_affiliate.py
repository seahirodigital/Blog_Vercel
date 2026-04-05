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

# requests 用ヘッダー（ブラウザに偽装してブロック回避）
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _keyword_matches_title(keywords: list[str], title: str) -> bool:
    """
    商品ページのタイトルに、検索キーワードがすべて含まれるか確認（AND条件）。
    大文字小文字を無視して部分一致。
    """
    title_lower = title.lower()
    return all(kw.lower() in title_lower for kw in keywords)


def _parse_organic_asins_from_html(html: str) -> list[str]:
    """
    Amazon 検索結果HTMLから、広告を除いたASINリストを抽出する。
    data-asin属性を正規表現で収集し、スポンサー判定はHTMLの前後文脈で判断。
    """
    import re
    # data-asin="XXXXXXXXXX" を持つブロックを抽出
    # 広告ブロックは AdHolder クラスまたは puis-sponsored-label-text を持つ
    sponsored_asins: set[str] = set()
    # スポンサーASINを収集（AdHolderクラスのdivに含まれるASIN）
    for block in re.finditer(
        r'<div[^>]+class="[^"]*AdHolder[^"]*"[^>]*data-asin="([A-Z0-9]{10})"',
        html,
    ):
        sponsored_asins.add(block.group(1))
    # puis-sponsored-label-text を含むブロックのASINも広告として除外
    for block in re.finditer(
        r'data-asin="([A-Z0-9]{10})"[^>]*>.*?puis-sponsored-label-text',
        html,
        re.DOTALL,
    ):
        sponsored_asins.add(block.group(1))

    # 全 data-asin を順序を保って収集
    seen: set[str] = set()
    organics: list[str] = []
    for m in re.finditer(r'data-asin="([A-Z0-9]{10})"', html):
        asin = m.group(1)
        if asin in seen or asin in sponsored_asins:
            continue
        seen.add(asin)
        organics.append(asin)
        if len(organics) >= 10:
            break
    return organics


def _get_product_title_requests(session, asin: str) -> str:
    """requests で商品ページを取得してタイトルを抽出する"""
    import re
    url = f"https://www.amazon.co.jp/dp/{asin}"
    try:
        r = session.get(url, headers=_HEADERS, timeout=15)
        if not r.ok:
            return ""
        html = r.text
        # #productTitle span の1行テキストのみを抽出（re.DOTALL は使わない）
        # <span id="productTitle" ...>タイトルテキスト</span> を想定
        m = re.search(r'id="productTitle"[^>]*>([^<]{3,300})<', html)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
        # フォールバック: <title> タグ（Amazonページタイトル）
        m2 = re.search(r'<title>([^<]{3,200})</title>', html)
        if m2:
            # "商品名: Amazon.co.jp: ..." の形式から商品名部分だけ取り出す
            t = m2.group(1).split("Amazon.co.jp")[0].strip(" :-:：")
            return t if t else m2.group(1).strip()
    except Exception:
        pass
    return ""


def _fetch_asin_via_requests(product_name: str, keywords: list[str]) -> str | None:
    """
    requests ライブラリで Amazon を検索してASINを返す（CI環境向け軽量実装）。
    Playwright より高速でタイムアウトしにくい。
    """
    import requests as req
    import re

    search_url = AMAZON_SEARCH_BASE + quote(product_name)
    try:
        session = req.Session()
        r = session.get(search_url, headers=_HEADERS, timeout=20)
        if not r.ok:
            print(f"   [WARN] requests: Amazon検索HTTPエラー {r.status_code}")
            return None

        organic_asins = _parse_organic_asins_from_html(r.text)
        print(f"   [INFO] requests: Organic候補 {len(organic_asins)}件")

        for asin in organic_asins:
            title = _get_product_title_requests(session, asin)
            matched = _keyword_matches_title(keywords, title) if title else False
            print(f"   [CHECK] {asin} | match={matched} | {title[:60]}")
            if matched:
                print(f"   [OK] ASIN確定: {asin}")
                return asin
    except Exception as e:
        print(f"   [WARN] requests失敗: {e}")
    return None


def _fetch_asin_via_playwright(product_name: str, keywords: list[str]) -> str | None:
    """
    Playwright で Amazon を検索してASINを返す（ローカル環境フォールバック）。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    search_url = AMAZON_SEARCH_BASE + quote(product_name)
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
                user_agent=_HEADERS["User-Agent"],
                locale="ja-JP",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("div[data-asin]", timeout=20000)
            except Exception:
                print("   [WARN] Playwright: 検索結果タイムアウト")
                browser.close()
                return None

            organic_asins = page.evaluate(js_get_organics)
            print(f"   [INFO] Playwright: Organic候補 {len(organic_asins)}件")

            for asin in organic_asins:
                page.goto(f"https://www.amazon.co.jp/dp/{asin}", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(800)
                title = page.evaluate(js_get_title)
                matched = _keyword_matches_title(keywords, title)
                print(f"   [CHECK] {asin} | match={matched} | {title[:60]}")
                if matched:
                    browser.close()
                    print(f"   [OK] ASIN確定: {asin}")
                    return asin
            browser.close()
    except Exception as e:
        print(f"   [WARN] Playwright失敗: {e}")
    return None


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
        token_res = req.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "advertising::audiences",
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
        search_res = req.get(
            "https://creators-api.amazon.com/v1/SearchItems",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            params={
                "keywords": product_name,
                "searchIndex": "All",
                "itemCount": 10,
                "partnerTag": ASSOCIATE_TAG,
                "partnerType": "Associates",
                "marketplace": "www.amazon.co.jp",
                "resources": "ItemInfo.Title,Images.Primary.Medium",
            },
            timeout=20,
        )
        if not search_res.ok:
            print(f"   [WARN] Creators API SearchItems失敗: {search_res.status_code} | {search_res.text[:300]}")
            return None

        data = search_res.json()
        items = data.get("SearchResult", {}).get("Items", [])
        print(f"   [INFO] Creators API: {len(items)}件の検索結果")

        asin_re = re.compile(r"[A-Z0-9]{10}")

        for item in items:
            asin = item.get("ASIN", "")
            if not asin or not asin_re.fullmatch(asin):
                continue
            title = (item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "") or "").lower()
            matched = all(kw.lower() in title for kw in keywords)
            print(f"   [CHECK] {asin} | match={matched} | {title[:60]}")
            if matched:
                print(f"   [OK] Creators API ASIN確定: {asin}")
                return asin

        # AND条件マッチなし → 最初のASINをフォールバック
        if items:
            asin = items[0].get("ASIN", "")
            if asin:
                title = items[0].get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
                print(f"   [OK] Creators API ASIN確定(フォールバック): {asin} | {title[:60]}")
                return asin

        print("   [WARN] Creators API: 検索結果にASINが見つかりません")
        return None
    except Exception as e:
        print(f"   [WARN] Creators API SearchItems例外: {e}")
        return None


def _fetch_asin_via_google_cse(product_name: str, keywords: list[str]) -> str | None:
    """
    Google Custom Search API を直接呼び出してASINを取得する（最優先）。
    Google API はクラウドIPをブロックしないため、GitHub Actions から直接呼べる。
    Vercel を経由しないので障害ポイントが減り、最も信頼性が高い。

    必要な環境変数:
      GOOGLE_CSE_API_KEY : Google Custom Search API キー
      GOOGLE_CSE_CX      : カスタム検索エンジンID (cx)
    """
    import requests as req
    import re

    api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_CX", "")
    if not api_key or not cx:
        print("   [WARN] Google CSE: GOOGLE_CSE_API_KEY または GOOGLE_CSE_CX が未設定 → スキップ")
        return None

    query = f"{product_name} site:amazon.co.jp"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": 10,
        "gl": "jp",
        "hl": "ja",
    }

    try:
        r = req.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=20)
        if not r.ok:
            body = r.text[:200]
            print(f"   [WARN] Google CSE HTTPエラー: {r.status_code} | {body}")
            return None

        data = r.json()
        items = data.get("items", [])
        print(f"   [INFO] Google CSE: {len(items)}件の検索結果")

        # URLから ASIN を抽出
        asin_re = re.compile(r"(?:dp|gp/product)/([A-Z0-9]{10})")

        for item in items:
            link = item.get("link", "")
            title = (item.get("title", "") or "").lower()
            snippet = (item.get("snippet", "") or "").lower()

            m = asin_re.search(link)
            if not m:
                continue

            asin = m.group(1)
            combined = title + " " + snippet

            # AND条件: すべてのキーワードがタイトルまたはスニペットに含まれるか
            matched = all(kw.lower() in combined for kw in keywords)
            print(f"   [CHECK] {asin} | match={matched} | {item.get('title', '')[:60]}")
            if matched:
                print(f"   [OK] Google CSE ASIN確定: {asin}")
                return asin

        # AND条件でマッチしなかった場合、URL内にASINがある最初の結果をフォールバック
        for item in items:
            link = item.get("link", "")
            m = asin_re.search(link)
            if m:
                asin = m.group(1)
                print(f"   [OK] Google CSE ASIN確定(フォールバック): {asin} | {item.get('title', '')[:60]}")
                return asin

        print("   [WARN] Google CSE: ASIN含むURLが見つかりませんでした")
        return None
    except Exception as e:
        print(f"   [WARN] Google CSE失敗: {e}")
        return None


def _fetch_asin_via_vercel(product_name: str) -> str | None:
    """
    Vercel Serverless Function (/api/amazon-asin) 経由でASINを取得する（フォールバック）。
    """
    import requests as req

    vercel_url = os.environ.get("VERCEL_URL", "https://blog-vercel-dun.vercel.app")
    endpoint = f"{vercel_url.rstrip('/')}/api/amazon-asin"
    params = {"product_name": product_name}

    try:
        r = req.get(endpoint, params=params, timeout=30)
        if not r.ok:
            body = ""
            try:
                body = r.text[:200]
            except Exception:
                pass
            print(f"   [WARN] Vercel API HTTPエラー: {r.status_code} | {body}")
            return None
        data = r.json()
        asin = data.get("asin")
        if asin:
            title = data.get("title", "")
            print(f"   [OK] Vercel API ASIN確定: {asin} | {title[:50]}")
            return asin
        msg = data.get("message", "不明")
        print(f"   [WARN] Vercel API: {msg}")
        return None
    except Exception as e:
        print(f"   [WARN] Vercel API失敗: {e}")
        return None


def fetch_amazon_asin(product_name: str) -> str | None:
    """
    Amazon.co.jp の ASIN を取得する。
    Google CSE直接（最優先）→ Vercel API → requests → Playwright の順で試行。
    """
    if not product_name:
        return None

    print(f"   [SEARCH] Amazon: {product_name}")
    keywords = [w for w in product_name.replace("&", " ").split() if len(w) >= 2]

    # 最優先: Amazon Creators API（公式・IPブロックなし）
    asin = _fetch_asin_via_creators_api(product_name, keywords)
    if asin:
        return asin

    # フォールバック1: Google CSE API 直接呼び出し
    print("   [INFO] Creators APIで取得できず → Google CSEでリトライ")
    asin = _fetch_asin_via_google_cse(product_name, keywords)
    if asin:
        return asin

    # フォールバック2: Vercel API経由
    print("   [INFO] Google CSEで取得できず → Vercel APIでリトライ")
    asin = _fetch_asin_via_vercel(product_name)
    if asin:
        return asin

    # フォールバック3: requests（ローカル環境向け）
    print("   [INFO] Vercel APIで取得できず → requestsでリトライ")
    asin = _fetch_asin_via_requests(product_name, keywords)
    if asin:
        return asin

    # フォールバック4: Playwright（ローカル環境）
    print("   [INFO] requestsで取得できず → Playwrightでリトライ")
    return _fetch_asin_via_playwright(product_name, keywords)


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
