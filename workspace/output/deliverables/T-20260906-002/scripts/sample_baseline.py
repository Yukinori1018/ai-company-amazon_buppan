#!/usr/bin/env python3
"""ドロップ数の「素の」分布を測る。

現行パイプライン（scan_v14）のプールは salesRankDrops30_gte で足切り済み・
drops 降順ソートで取られているため、低い側が構造的に欠けている。
ここでは **ドロップ数を一切条件に入れず**、ランク帯だけで層化抽出する。

トークン節約:
  - Product Finder = 10 tokens / query
  - product 取得 = 1 token / ASIN（offers を付けない）
    offers を付けると +6/ASIN。ドロップ数と monthlySold には offers は要らない。
"""
import gzip, json, sys, time, urllib.parse, urllib.request
from fetch_keepa import api_key

DOMAIN = 5
ROOT_STATIONERY = 86731051   # 文房具・オフィス用品（amazon.co.jp のルートカテゴリ）
BANDS = [(1, 999), (1000, 9999), (10000, 29999), (30000, 99999),
         (100000, 499999), (500000, 2000000)]
PER_BAND = 50


def _get(url):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    b = urllib.request.urlopen(req, timeout=180).read()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return json.loads(b)


def finder(lo, hi, n):
    sel = {
        "current_SALES_gte": lo, "current_SALES_lte": hi,
        "rootCategory": [ROOT_STATIONERY],
        "isAdultProduct": False,
        # ★ドロップ数の条件は**入れない**。ソートもしない（drops 降順で取ると
        #   上位だけを見ることになり、素の分布が測れない）。
        "perPage": n, "page": 0,
    }
    q = urllib.parse.urlencode({"key": api_key(), "domain": DOMAIN,
                                "selection": json.dumps(sel)})
    d = _get("https://api.keepa.com/query?" + q)
    return d.get("asinList", []), d.get("tokensLeft")


def products(asins):
    out = []
    for i in range(0, len(asins), 100):
        chunk = asins[i:i + 100]
        q = urllib.parse.urlencode({"key": api_key(), "domain": DOMAIN,
                                    "asin": ",".join(chunk), "stats": 365,
                                    "history": 0})
        d = _get("https://api.keepa.com/product?" + q)
        out += d.get("products", [])
        print("  fetched %d  tokensLeft=%s" % (len(out), d.get("tokensLeft")),
              file=sys.stderr)
        time.sleep(2)
    return out


if __name__ == "__main__":
    rows = []
    for lo, hi in BANDS:
        asins, left = finder(lo, hi, PER_BAND)
        print("band %d-%d: %d asins (tokensLeft=%s)" % (lo, hi, len(asins), left),
              file=sys.stderr)
        for p in products(asins):
            s = p.get("stats") or {}
            cur = s.get("current") or []
            rows.append({
                "band": "%d-%d" % (lo, hi),
                "rank": cur[3] if len(cur) > 3 else None,
                "d30": s.get("salesRankDrops30"), "d90": s.get("salesRankDrops90"),
                "d180": s.get("salesRankDrops180"), "d365": s.get("salesRankDrops365"),
                "monthlySold": p.get("monthlySold"),
                "countNew": cur[11] if len(cur) > 11 else None,
                "reviews": cur[17] if len(cur) > 17 else None,
                "oos30": (s.get("outOfStockPercentage30") or [None] * 2)[1],
                "trackingSince": p.get("trackingSince"),
                "lastUpdate": p.get("lastUpdate"),
                "availAmazon": p.get("availabilityAmazon"),
            })
    json.dump(rows, open("baseline_sample.json", "w"))
    print("saved %d rows" % len(rows), file=sys.stderr)
