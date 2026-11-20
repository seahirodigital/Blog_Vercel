import json
import os
import time
import requests

queries = [
    "Apple iPhone 17", "Apple iPhone 16", "Apple iPad Air", "Apple iPad mini",
    "Apple iPad Pro", "Apple AirPods 5", "Apple AirPods Pro 3",
    "Sony PlayStation 5", "Sony PlayStation 5 Pro", "Google Pixel 9a",
    "Apple Watch", "Adobe Creative Cloud", "Anker モバイルバッテリー",
    "Apple Gift Card", "腕時計 メンズ", "ウイスキー",
    "羽毛布団 シングル", "エアコン 6畳", "空気清浄機",
    "クリスマス プレゼント", "ケルヒャー 高圧洗浄機",
    "ケノン 脱毛器", "電動 工具", "コーヒーメーカー",
    "電気シェーバー", "Nintendo Switch 2", "洗濯機 全自動",
    "掃除機 コードレス", "自動車 タイヤ", "タブレット"
]
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
            items = response.json().get("searchResult", {}).get("items", [])
            output = []
            for item in items:
                title = item.get("itemInfo", {}).get("title", {}).get("displayValue", "")
                asin = item.get("asin", "")
                if title and asin:
                    output.append({"title": title, "asin": asin})
            print("検索結果_JSON " + json.dumps({"query": query, "items": output},
                                                ensure_ascii=False), flush=True)
    except requests.RequestException:
        print("検索結果_JSON " + json.dumps({"query": query, "error": "通信失敗"},
                                            ensure_ascii=False), flush=True)
    time.sleep(1.2)
