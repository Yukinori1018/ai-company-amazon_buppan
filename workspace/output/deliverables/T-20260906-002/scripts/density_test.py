#!/usr/bin/env python3
"""ドロップ数 vs Keepa の観測サンプル数。

salesRankDrops は履歴上、隣り合うサンプル間でランクが下がった回数。
30日の観測サンプル数 N に対して構造的に drops <= N-1 の上限がかかる。
売れ行きが上限を超えても数字は増えない（右側打ち切り）。実測で確かめる。
"""
import gzip, json, statistics, urllib.parse, urllib.request
from fetch_keepa import api_key

DOMAIN, ROOT = 5, 86731051


def get(path, params):
    q = urllib.parse.urlencode(dict(params, key=api_key(), domain=DOMAIN))
    req = urllib.request.Request(f"https://api.keepa.com/{path}?{q}",
                                 headers={"Accept-Encoding": "gzip"})
    b = urllib.request.urlopen(req, timeout=180).read()
    return json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)


sel = {"current_SALES_gte": 1, "current_SALES_lte": 29999,
       "rootCategory": [ROOT], "isAdultProduct": False, "perPage": 50, "page": 0}
asins = get("query", {"selection": json.dumps(sel, separators=(",", ":"))})["asinList"]
d = get("product", {"asin": ",".join(asins), "stats": 365})
print("tokensLeft", d.get("tokensLeft"))

out = []
for p in d["products"]:
    s = p.get("stats") or {}
    sr = (p.get("csv") or [None] * 4)[3]
    if not sr or s.get("salesRankDrops30") is None:
        continue
    ts = sr[0::2]
    n30 = sum(1 for t in ts if t >= ts[-1] - 30 * 24 * 60)
    n365 = sum(1 for t in ts if t >= ts[-1] - 365 * 24 * 60)
    out.append({"n30": n30, "d30": s["salesRankDrops30"],
                "n365": n365, "d365": s.get("salesRankDrops365"),
                "sold": p.get("monthlySold")})

print(f"\nn={len(out)}")
print(f"{'30日のサンプル数':>14} {'ドロップ数':>9} {'上限に対する充填率':>18}")
for r in sorted(out, key=lambda r: -r["d30"])[:20]:
    cap = max(1, r["n30"] - 1)
    print(f"{r['n30']:14d} {r['d30']:9d} {100*r['d30']/cap:17.0f}%")

fills = [r["d30"] / max(1, r["n30"] - 1) for r in out if r["n30"] > 3]
print(f"\n充填率（drops30 ÷ (サンプル数-1)）: n={len(fills)} "
      f"中央={statistics.median(fills):.2f} 最大={max(fills):.2f}")
xs = [r["n30"] for r in out]; ys = [r["d30"] for r in out]
import math
mx, my = statistics.mean(xs), statistics.mean(ys)
r = sum((a-mx)*(b-my) for a, b in zip(xs, ys)) / math.sqrt(
    sum((a-mx)**2 for a in xs) * sum((b-my)**2 for b in ys))
print(f"相関 サンプル数 vs ドロップ数: {r:.3f}")
sold = [(r["n30"], r["d30"], r["sold"]) for r in out if r["sold"]]
if sold:
    mx2 = statistics.mean([s[2] for s in sold])
    print(f"monthlySold あり n={len(sold)} 平均販売数={mx2:.0f} "
          f"→ 平均ドロップ数={statistics.mean([s[1] for s in sold]):.1f}"
          f"（販売数の桁に全く追随していないことを見る）")
json.dump(out, open("density_test.json", "w"))
