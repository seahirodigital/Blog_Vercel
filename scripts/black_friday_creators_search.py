import json
import os
import time
import requests

queries = ["PS5", "iPad", "洗濯機"]
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
