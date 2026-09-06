#!/usr/bin/env python3
"""S5 を通過した 32 SKU に新条件①〜④を当て、何件残るかを測る。

offers を付ける（BuyBox 系は offers なしでは更新されない）。
1 ASIN あたり 1 → 7 token になるので、**32件だけ**に当てる前提。
"""
import gzip, json, urllib.parse, urllib.request
from fetch_keepa import api_key

A = json.load(open("s5_asins.json"))["passed"]
print("S5 通過:", len(A))

def get(asins):
    q = urllib.parse.urlencode({"key": api_key(), "domain": 5,
                                "asin": ",".join(asins), "stats": 365,
                                "offers": 20, "buybox": 1, "rating": 1})
    req = urllib.request.Request("https://api.keepa.com/product?" + q,
                                 headers={"Accept-Encoding": "gzip"})
    b = urllib.request.urlopen(req, timeout=300).read()
    return json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)

d = get(A)
print("tokensConsumed", d.get("tokensConsumed"), "left", d.get("tokensLeft"))
json.dump(d, open("raw_32.json", "w"))

p = d["products"][0]
s = p.get("stats") or {}
print("\n=== 使えるフィールドの実地確認（1件目）===")
for k in ["parentAsin", "variationCount", "lastUpdate", "lastPriceChange",
          "lastRatingUpdate", "monthlySold", "buyBoxSellerIdHistory"]:
    v = p.get(k)
    print(f"  product.{k:24} {'あり' if v not in (None, []) else '無し'}"
          f" ({type(v).__name__}{', len=%d' % len(v) if isinstance(v, list) else ''})")
for k in ["buyBoxIsUnqualified", "buyBoxIsAmazon", "buyBoxIsFBA", "buyBoxIsPreorder",
          "buyBoxSellerId", "buyBoxPrice", "outOfStockPercentage30",
          "buyBoxStats", "totalOfferCount", "salesRankDrops30"]:
    v = s.get(k)
    print(f"  stats.{k:26} {'あり' if v is not None else '無し'} ({type(v).__name__})")
print("\n  csv[18] BUY_BOX_SHIPPING 履歴:",
      "あり len=%d" % len(p["csv"][18]) if len(p.get("csv") or []) > 18 and p["csv"][18] else "無し")
