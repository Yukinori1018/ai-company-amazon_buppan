#!/usr/bin/env python3
"""ドロップ数の足切り閾値 X を実測で決めるための標本を作る。

正解ラベル = Amazon 公表の月間販売数（monthlySold）。Keepa の推定ではなく
Amazon 自身が出している一次情報なので、これを「売れている」の定義に使う。

前回との違い:
  - ASIN を保存する（追試のため）
  - ランキング履歴を取り、**30日の観測回数**を数える
    → 充填率 drops30 / (観測回数-1) を出せる。飽和仮説の検証に要る
  - 価格帯も持つ（閾値が価格帯依存かを見る）
"""
import gzip, json, sys, time, urllib.parse, urllib.request
from fetch_keepa import api_key

DOMAIN, ROOT = 5, 86731051      # 文房具・オフィス用品
BANDS = [(1, 999), (1000, 9999), (10000, 29999),
         (30000, 99999), (100000, 499999), (500000, 2000000)]
PER_BAND = 60


def get(path, params):
    q = urllib.parse.urlencode(dict(params, key=api_key(), domain=DOMAIN))
    req = urllib.request.Request(f"https://api.keepa.com/{path}?{q}",
                                 headers={"Accept-Encoding": "gzip"})
    b = urllib.request.urlopen(req, timeout=240).read()
    return json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)


def finder(lo, hi, n):
    # ★ドロップ数の条件もソートも入れない。入れると素の分布が測れない。
    sel = {"current_SALES_gte": lo, "current_SALES_lte": hi,
           "rootCategory": [ROOT], "isAdultProduct": False,
           "perPage": n, "page": 0}
    return get("query", {"selection": json.dumps(sel, separators=(",", ":"))})


def row(p, band):
    s = p.get("stats") or {}
    cur = s.get("current") or []
    sr = (p.get("csv") or [None] * 4)[3]
    n30 = n365 = None
    if sr:
        ts = sr[0::2]
        n30 = sum(1 for t in ts if t >= ts[-1] - 30 * 24 * 60)
        n365 = sum(1 for t in ts if t >= ts[-1] - 365 * 24 * 60)
    return {
        "asin": p["asin"], "band": band,
        "rank": cur[3] if len(cur) > 3 else None,
        "price_new": cur[1] if len(cur) > 1 else None,
        "d30": s.get("salesRankDrops30"), "d90": s.get("salesRankDrops90"),
        "d365": s.get("salesRankDrops365"),
        "n30": n30, "n365": n365,
        "monthlySold": p.get("monthlySold"),
        "countNew": cur[11] if len(cur) > 11 else None,
        "oos30": (s.get("outOfStockPercentage30") or [None, None])[1],
        "parentAsin": p.get("parentAsin"),
        "variationCount": p.get("variationCount"),
    }


if __name__ == "__main__":
    out = []
    for lo, hi in BANDS:
        d = finder(lo, hi, PER_BAND)
        asins = d.get("asinList") or []
        print(f"band {lo}-{hi}: {len(asins)} left={d.get('tokensLeft')}", file=sys.stderr)
        for i in range(0, len(asins), 100):
            pr = get("product", {"asin": ",".join(asins[i:i + 100]), "stats": 365})
            out += [row(p, f"{lo}-{hi}") for p in pr.get("products", [])]
            print(f"  {len(out)} left={pr.get('tokensLeft')}", file=sys.stderr)
            time.sleep(2)
    json.dump(out, open("labeled_sample.json", "w"))
    print("saved", len(out), file=sys.stderr)
