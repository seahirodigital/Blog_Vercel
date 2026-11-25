import json
import os
import time
import requests

queries = ["PS5","iPad","iPad Air 13インチ","AirPods 4","AirPods Max","PS5 SSD","PS5 コントローラー","PS5ソフト","PS5 本体","3Dプリンター","4K モニター","プレステ 5","ニューバランス 996","アイフォン","アレクサ","UGG","絵本","映画","Kindle 端末","クリスマスツリー","化粧品","血圧計","食品","タブレット","チョコレート","Pixel Watch","Apple Pencil","FLEXISPOT","Xiaomi タブレット","VRゴーグル","LEGO","Lenovo","Logicool"]
r = requests.post("https://api.amazon.co.jp/auth/o2/token", data={
    "grant_type": "client_credentials",
    "client_id": os.environ["AMAZON_CLIENT_ID"],
    "client_secret": os.environ["AMAZON_CLIENT_SECRET"],
    "scope": "creatorsapi::default"
}, timeout=30)
r.raise_for_status()
access_token = r.json()["access_token"]
headers = {"Authorization": "Bearer " + access_token, "Content-Type": "application/json",
           "x-marketplace": "www.amazon.co.jp"}
for query in queries:
    payload = {"keywords": query, "partnerTag": "hiroshit-22", "marketplace": "www.amazon.co.jp",
               "resources": ["itemInfo.title"], "itemCount": 5}
    try:
        for attempt in range(4):
            response = requests.post("https://creatorsapi.amazon/catalog/v1/searchItems",
                                     headers=headers, json=payload, timeout=30)
            if response.status_code != 429:
                break
            time.sleep(3 * (attempt + 1))
        if not response.ok:
            print("検索結果_JSON " + json.dumps({"query": query, "status": response.status_code},
                                                ensure_ascii=False), flush=True)
        else:
            result = response.json().get("searchResult", {})
            print("検索結果_JSON " + json.dumps({"query": query, "searchURL": result.get("searchURL", "")},
                                                ensure_ascii=False), flush=True)
    except requests.RequestException:
        print("検索結果_JSON " + json.dumps({"query": query, "error": "通信失敗"},
                                            ensure_ascii=False), flush=True)
    time.sleep(1.2)

# 検索画面がクローラーに返すステータスとプレビュー情報を比較する。
import re
from html import unescape

checks = {
    "PS5": "https://www.amazon.co.jp/s?k=PS5&rh=p_n_availability%3A2227306051&tag=hiroshit-22&linkCode=osi",
    "洗濯機_絞込なし": "https://www.amazon.co.jp/s?k=%E6%B4%97%E6%BF%AF%E6%A9%9F&tag=hiroshit-22&linkCode=osi",
    "テレビ_絞込なし": "https://www.amazon.co.jp/s?k=%E3%83%86%E3%83%AC%E3%83%93&tag=hiroshit-22&linkCode=osi",
    "テレビ_別形式": "https://www.amazon.co.jp/s/?field-keywords=%E3%83%86%E3%83%AC%E3%83%93&search-alias=aps&tag=hiroshit-22&linkCode=osi",
}
for label, url in []:
    try:
        response = requests.get(url, headers={"User-Agent": "notebot"}, timeout=20, allow_redirects=True)
        page = response.text[:300000]
        title = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
        fields = re.findall(r'<meta\b[^>]*(?:property|name)=["\']og:(?:title|description|image)["\'][^>]*>', page, flags=re.I)
        print("画面調査_JSON " + json.dumps({"label": label, "status": response.status_code,
              "title": unescape(title.group(1)).strip()[:200] if title else "",
              "og_fields": fields[:3], "final_url": response.url}, ensure_ascii=False), flush=True)
    except requests.RequestException:
        print("画面調査_JSON " + json.dumps({"label": label, "error": "通信失敗"}, ensure_ascii=False), flush=True)
    time.sleep(1.2)
