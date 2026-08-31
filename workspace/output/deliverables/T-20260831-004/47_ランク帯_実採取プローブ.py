# -*- coding: utf-8 -*-
"""ランク帯の実験：帯を変えると母集団の中身が変わるのかを実測する。
Keepa トークンのみ消費（課金なし＝月額固定）。offers は取らない（1商品1トークン）。"""
import os, json, time, urllib.request, urllib.parse, collections, re, sys, pathlib
ENV = pathlib.Path.home() / ".config/ai-company-amazon-buppan/keepa.env"
for line in ENV.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k, v.strip().strip('"'))
KEY = os.environ["KEEPA_API_KEY"]
DOMAIN = 5
HERE = os.path.dirname(os.path.abspath(__file__))

import requests
def tokens_left():
    try:
        return requests.get("https://api.keepa.com/token", params={"key": KEY}, timeout=60).json().get("tokensLeft")
    except Exception:
        return None

def wait_for(cost):
    """必要トークンが貯まるまで待つ（/token は無料）"""
    while True:
        t = tokens_left()
        if t is None: time.sleep(30); continue
        if t >= cost + 20: return t
        need = cost + 20 - t
        w = max(30, int(need / 20 * 60) + 10)
        print(f"  tokensLeft={t} 必要{cost} → {w}秒待機", file=sys.stderr, flush=True)
        time.sleep(w)

def call(path, params, cost=10):
    params = dict(params); params.update(key=KEY, domain=DOMAIN)
    wait_for(cost)
    for i in range(60):
        try:
            r = requests.get("https://api.keepa.com/" + path, params=params, timeout=300)
            if r.status_code == 429:
                print("  429 → 補充待ち", file=sys.stderr, flush=True); wait_for(cost); continue
            r.raise_for_status()
            d = r.json()
            return d
        except Exception as e:
            print("  retry", type(e).__name__, e, file=sys.stderr); time.sleep(30)
    raise SystemExit("failed")

BANDS = [("1–50,000", 1, 50_000), ("50,001–150,000", 50_001, 150_000), ("150,001–500,000", 150_001, 500_000)]
N = 60
KEEPA_EPOCH_MIN = 21564000
tracking_before = int(time.time() / 60) - KEEPA_EPOCH_MIN - 180 * 24 * 60
out = {}
for name, lo, hi in BANDS:
    sel = {
        "current_AMAZON_gte": -1, "current_AMAZON_lte": -1, "availabilityAmazon": -1,
        "current_COUNT_NEW_gte": 2, "current_COUNT_NEW_lte": 6,
        "current_NEW_gte": 1500, "current_NEW_lte": 8000,
        "current_SALES_gte": lo, "current_SALES_lte": hi,
        "variationCount_gte": 0, "variationCount_lte": 3,
        "trackingSince_lte": tracking_before, "isAdultProduct": False,
        "categories_exclude": [160384011, 52374051, 57239051],
        "salesRankDrops30_gte": 10,
        "perPage": 100, "page": 0, "sort": [["salesRankDrops30", "desc"]],
    }
    r = call("query", {"selection": json.dumps(sel, separators=(",", ":"))}, cost=15)
    asins = r.get("asinList") or []
    print(f"[{name}] 母集団 {r.get('totalResults')}件 / 取得 {len(asins)} / tokensLeft={r.get('tokensLeft')}")
    take = asins[:N]
    prods = []
    CH = 20
    for i in range(0, len(take), CH):
        part = take[i:i+CH]
        d = call("product", {"asin": ",".join(part), "stats": 0}, cost=len(part))
        prods += d.get("products", [])
        print(f"   +{len(part)}件", file=sys.stderr, flush=True)
    out[name] = dict(total=r.get("totalResults"), products=[
        dict(asin=p.get("asin"), brand=p.get("brand"), manufacturer=p.get("manufacturer"),
             title=(p.get("title") or "")[:100],
             cats=[c.get("name") for c in (p.get("categoryTree") or [])],
             ean=(p.get("eanList") or [None])[0],
             rank=(p.get("csv") or [None]*4)[3][-1] if (p.get("csv") and len(p['csv'])>3 and p['csv'][3]) else None)
        for p in prods])
    print(f"   詳細取得 {len(prods)}件")
json.dump(out, open(HERE + "/t49_probe.json", "w"), ensure_ascii=False)
print("saved")
