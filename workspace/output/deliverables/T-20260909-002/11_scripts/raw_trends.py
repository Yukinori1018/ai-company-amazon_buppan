"""売れ筋(monthlySold>=100) と 非売れ筋(公表なし) の傾向を、保存済み Keepa raw だけで比べる（0トークン）。

データ:
  A = T-20260817-005/raw        4,002件 product(stats付き・offers無し) 2026-08-21取得
  B = T-20260817-005/raw_offers   355件 product(offers付き・stats無し)   2026-08-23取得
    → 評価・評価件数・実セラー数・Buy Box は B でしか測れない
注意:
  - A/B とも v1.3 Finder（Amazon本体なし・新品オファー2〜6・価格1,500〜20,000・評価件数5〜300・
    バリエーション1〜3・ランク30万以内）で選んだ棚。全Amazonの縮図ではない。
  - monthlySold は 2026-04 以降 50 未満が出ない（Amazon の表示下限）。「月10未満」は直接見えないので
    「公表なし」を非売れ筋として扱う。値はバリエーション単位・下限値（100 は「100以上」）。
  - 新品価格 csv[1] は 2026-02-23 から送料込みに定義変更。境界以降の点だけ使う。
"""
import collections
import datetime
import glob
import gzip
import json
import re
import statistics as st

R = "workspace/output/deliverables/"
BASE = datetime.datetime(2011, 1, 1)
BOUND = (datetime.datetime(2026, 2, 23) - BASE).total_seconds() / 60
AMAZON_JP = "AN1VRQENFRJN5"
SET_RE = re.compile(r"(×|x|X|\*)\s*\d+\s*(個|本|袋|箱|パック|セット|枚|缶)?|\d+\s*(個|本|袋|箱|パック|缶)\s*(セット|組)|まとめ買い|セット")


def km(t):
    return BASE + datetime.timedelta(minutes=t)


def pairs(a):
    return list(zip(a[0::2], a[1::2])) if a else []


def group(ms):
    if isinstance(ms, int) and ms >= 100:
        return "売れ筋(月100以上)"
    if isinstance(ms, int):
        return "中間(月50)"
    return "非売れ筋(公表なし)"


ORDER = ["売れ筋(月100以上)", "中間(月50)", "非売れ筋(公表なし)"]


def med(v):
    v = [x for x in v if x is not None]
    return round(st.median(v), 2) if v else None


def pct(v):
    v = list(v)
    return f"{100 * sum(v) / len(v):.0f}%" if v else "-"


def monthly(msh, now):
    """monthlySoldHistory → 直近12か月の月末値（-1 は表示下限未満とみなし 0）。"""
    out = {}
    for t, v in pairs(msh):
        d = km(t)
        out[(d.year, d.month)] = max(v, 0)
    keys = []
    y, m = now.year, now.month
    for _ in range(12):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    # 値が無い月は直前の値を持ち越す
    last = None
    series = []
    for k in sorted(keys):
        if k in out:
            last = out[k]
        else:
            prior = [v for kk, v in out.items() if kk < k]
            last = prior[-1] if prior and last is None else last
        series.append(last)
    return series


# ---- NETSEA の JAN とブランド -------------------------------------------------
netsea_jan = set()
for line in open(R + "T-20260831-006/out/netsea_items.jsonl"):
    j = json.loads(line).get("jan_code")
    if j:
        netsea_jan.add(j.strip())
netsea_brand = set()
for line in open(R + "T-20260831-006/out/keepa_facts.jsonl"):
    b = json.loads(line).get("brand")
    if b:
        netsea_brand.add(b)

# ---- A: raw 4,002 -------------------------------------------------------------
rows = []
for f in sorted(glob.glob(R + "T-20260817-005/raw/*.json.gz")):
    for p in json.load(gzip.open(f)).get("products") or []:
        s = p.get("stats") or {}
        cur, a90 = s.get("current") or [], s.get("avg90") or []
        now = km(p["lastUpdate"])
        g = lambda arr, i: arr[i] if len(arr) > i and arr[i] is not None and arr[i] >= 0 else None
        price = g(cur, 1) or g(a90, 1)
        c1 = [(t, v) for t, v in pairs((p.get("csv") or [None, None])[1]) if t >= max(BOUND, p["lastUpdate"] - 90 * 1440) and v > 0]
        vals = [v for _, v in c1]
        vol = (max(vals) - min(vals)) / st.median(vals) if len(vals) >= 3 else None
        drop = (g(cur, 1) / g(a90, 1)) if g(cur, 1) and g(a90, 1) else None
        tree = p.get("categoryTree") or []
        fba34 = pairs((p.get("csv") or [])[34] if len(p.get("csv") or []) > 34 else None)
        ser = monthly(p.get("monthlySoldHistory"), now)
        known = [v for v in ser if v is not None]
        title = p.get("title") or ""
        rows.append(dict(
            asin=p["asin"], grp=group(p.get("monthlySold")), ms=p.get("monthlySold"),
            cat=tree[0]["name"] if tree else "?", sub=tree[1]["name"] if len(tree) > 1 else "?",
            price=price, rank=g(cur, 3),
            offers=g(cur, 11), offers90=g(a90, 11),
            fba=fba34[-1][1] if fba34 and fba34[-1][1] >= 0 else None,
            amz_now=p.get("availabilityAmazon", -1) != -1, amz90=bool(g(a90, 0)),
            vol=vol, drop=drop,
            var=bool(p.get("parentAsin") or p.get("variations")),
            setlike=(p.get("numberOfItems") or 0) > 1 or (p.get("packageQuantity") or 0) > 1 or bool(SET_RE.search(title)),
            months_on=sum(1 for v in known if v >= 100) if known else None,
            months_zero=sum(1 for v in known if v == 0) if known else None,
            peak=max(known) if known else None, low=min(known) if known else None,
            jan_netsea=any(e in netsea_jan for e in (p.get("eanList") or [])),
            brand_netsea=(p.get("brand") in netsea_brand),
            age_y=(p["lastUpdate"] - p["listedSince"]) / 525600 if p.get("listedSince", 0) > 0 else None,
            brand=p.get("brand"),
        ))

G = {k: [r for r in rows if r["grp"] == k] for k in ORDER}
print("## A. raw 4,002件（2026-08-21 取得・stats付き）\n")
print("| 指標 | " + " | ".join(f"{k}（{len(G[k])}件）" for k in ORDER) + " |")
print("|---|" + "---|" * len(ORDER))


def line(name, fn):
    print(f"| {name} | " + " | ".join(str(fn(G[k])) for k in ORDER) + " |")


line("新品価格 中央値(円)", lambda v: med(r["price"] for r in v))
line("ランキング 中央値", lambda v: med(r["rank"] for r in v))
line("新品オファー数 中央値（現在）", lambda v: med(r["offers"] for r in v))
line("新品オファー数 中央値（90日平均）", lambda v: med(r["offers90"] for r in v))
line("新品オファー数 5以上", lambda v: pct((r["offers"] or 0) >= 5 for r in v))
line("オファー数が90日平均より増えた", lambda v: pct((r["offers"] or 0) > (r["offers90"] or 0) for r in v))
line("FBAオファー数 中央値(Amazon込)", lambda v: med(r["fba"] for r in v))
line("Amazon本体 現在あり", lambda v: pct(r["amz_now"] for r in v))
line("Amazon本体 90日内に価格あり", lambda v: pct(r["amz90"] for r in v))
line("90日の価格振れ幅 中央値（(最高-最低)/中央値）", lambda v: med(r["vol"] for r in v))
line("価格振れ幅 20%超", lambda v: pct((r["vol"] or 0) > 0.2 for r in v if r["vol"] is not None))
line("現在値/90日平均 中央値", lambda v: med(r["drop"] for r in v))
line("現在値が90日平均より5%以上安い", lambda v: pct((r["drop"] or 1) < 0.95 for r in v if r["drop"] is not None))
line("バリエーションあり", lambda v: pct(r["var"] for r in v))
line("セット・複数入り（疑い含む）", lambda v: pct(r["setlike"] for r in v))
line("出品からの年数 中央値", lambda v: med(r["age_y"] for r in v))
line("JANがNETSEAに在る", lambda v: pct(r["jan_netsea"] for r in v))
line("ブランドがNETSEAに在る", lambda v: pct(r["brand_netsea"] for r in v))
line("直近12か月で月100以上だった月数 中央値", lambda v: med(r["months_on"] for r in v))
line("直近12か月で表示下限未満の月が1つ以上", lambda v: pct((r["months_zero"] or 0) >= 1 for r in v if r["months_zero"] is not None))

# 季節性（売れ筋のうち、ピーク÷底 >=3 または 下限未満の月あり）
hot = G[ORDER[0]]
seas = [r for r in hot if r["peak"] and (r["low"] == 0 or (r["low"] and r["peak"] / r["low"] >= 3))]
print(f"\n売れ筋{len(hot)}件のうち季節・波あり（直近12か月にピーク÷底≧3 または下限未満の月あり）: {len(seas)}件（{100*len(seas)/max(len(hot),1):.0f}%）")
steady = [r for r in hot if r["months_on"] is not None and r["months_on"] >= 10]
print(f"売れ筋のうち 12か月中10か月以上 月100以上: {len(steady)}件（{100*len(steady)/max(len(hot),1):.0f}%）")

print("\n### カテゴリ別（件数30以上）\n\n| カテゴリ | 件数 | 売れ筋 | 率 | 中間 | 公表なし |\n|---|---:|---:|---:|---:|---:|")
cc = collections.Counter(r["cat"] for r in rows)
for c, n in cc.most_common():
    if n < 30:
        continue
    v = [r for r in rows if r["cat"] == c]
    h = sum(r["grp"] == ORDER[0] for r in v)
    print(f"| {c} | {n} | {h} | {100*h/n:.0f}% | {sum(r['grp']==ORDER[1] for r in v)} | {sum(r['grp']==ORDER[2] for r in v)} |")

print("\n### サブカテゴリ 売れ筋率の上位・下位（件数20以上）\n")
sc = collections.Counter((r["cat"], r["sub"]) for r in rows)
subs = []
for k, n in sc.items():
    if n >= 20:
        v = [r for r in rows if (r["cat"], r["sub"]) == k]
        subs.append((sum(r["grp"] == ORDER[0] for r in v) / n, n, k))
subs.sort(reverse=True)
print("| サブカテゴリ | 件数 | 売れ筋率 |\n|---|---:|---:|")
for item in subs[:8]:
    print(f"| {item[2][0]} > {item[2][1]} | {item[1]} | {100*item[0]:.0f}% |")
print("| … | | |")
for item in subs[-6:]:
    print(f"| {item[2][0]} > {item[2][1]} | {item[1]} | {100*item[0]:.0f}% |")

print("\n### 価格帯別\n\n| 価格帯(円) | 件数 | 売れ筋率 | 公表なし率 |\n|---|---:|---:|---:|")
for lo, hi in [(0, 2000), (2000, 3000), (3000, 5000), (5000, 8000), (8000, 12000), (12000, 10**9)]:
    v = [r for r in rows if r["price"] and lo <= r["price"] < hi]
    if v:
        print(f"| {lo:,}〜{'' if hi >= 10**9 else f'{hi:,}'} | {len(v)} | {pct(r['grp']==ORDER[0] for r in v)} | {pct(r['grp']==ORDER[2] for r in v)} |")

print("\n### 新品オファー数別\n\n| 新品オファー数 | 件数 | 売れ筋率 |\n|---|---:|---:|")
for lo, hi in [(0, 3), (3, 4), (4, 5), (5, 7), (7, 99)]:
    v = [r for r in rows if r["offers"] is not None and lo <= r["offers"] < hi]
    if v:
        print(f"| {lo}〜{hi-1} | {len(v)} | {pct(r['grp']==ORDER[0] for r in v)} |")

# ブランド単位: 売れ筋を持つブランドは他の商品も売れているか
bb = collections.defaultdict(list)
for r in rows:
    if r["brand"]:
        bb[r["brand"]].append(r)
multi = {b: v for b, v in bb.items() if len(v) >= 2}
with_hot = [v for v in multi.values() if any(r["grp"] == ORDER[0] for r in v)]
no_hot = [v for v in multi.values() if not any(r["grp"] == ORDER[0] for r in v)]


def sib_rate(vs):
    tot = hits = 0
    for v in vs:
        n_hot = sum(r["grp"] == ORDER[0] for r in v)
        # 売れ筋1件を除いた残りの売れ筋率（ブランド内の類似が売れているか）
        rest = len(v) - 1 if n_hot else len(v)
        tot += rest
        hits += max(n_hot - 1, 0)
    return f"{100*hits/max(tot,1):.0f}%（{hits}/{tot}）"


print(f"\n### ブランド内の連れ売れ（同ブランド2件以上のブランド {len(multi)}）\n")
print(f"- 売れ筋を1件以上持つブランドの、残りの商品の売れ筋率: {sib_rate(with_hot)}")
print(f"- 売れ筋を持たないブランドの商品の売れ筋率: 0%（定義上）／全体の売れ筋率 {pct(r['grp']==ORDER[0] for r in rows)}")

# ---- B: raw_offers 355 ---------------------------------------------------------
print("\n## B. raw_offers 355件（2026-08-23 取得・offers付き）\n")
brow = []
for f in sorted(glob.glob(R + "T-20260817-005/raw_offers/*.json.gz")):
    for p in json.load(gzip.open(f)).get("products") or []:
        c = p.get("csv") or []
        last = lambda i: (pairs(c[i])[-1][1] if len(c) > i and c[i] else None)
        live = set(p.get("liveOffersOrder") or [])
        offers = p.get("offers") or []
        sellers = {o["sellerId"] for i, o in enumerate(offers) if i in live and o.get("condition") == 1 and o.get("sellerId") != AMAZON_JP}
        amz_live = any(i in live and o.get("sellerId") == AMAZON_JP for i, o in enumerate(offers))
        bb = [(t, v) for t, v in pairs(c[18] if len(c) > 18 else None) if t >= p["lastUpdate"] - 90 * 1440 and v > 0]
        bv = [v for _, v in bb]
        bbh = pairs(p.get("buyBoxSellerIdHistory"))
        bb90 = {s for t, s in ((int(t), s) for t, s in bbh) if t >= p["lastUpdate"] - 90 * 1440 and s not in ("-1", "-2")}
        brow.append(dict(
            grp=group(p.get("monthlySold")), rating=last(16), reviews=last(17),
            sellers=len(sellers), amz=amz_live,
            bbvol=(max(bv) - min(bv)) / st.median(bv) if len(bv) >= 3 else None,
            bbchg=len(bv), bbsellers=len(bb90),
        ))
GB = {k: [r for r in brow if r["grp"] == k] for k in ORDER}
print("| 指標 | " + " | ".join(f"{k}（{len(GB[k])}件）" for k in ORDER) + " |")
print("|---|" + "---|" * len(ORDER))


def lineb(name, fn):
    print(f"| {name} | " + " | ".join(str(fn(GB[k])) for k in ORDER) + " |")


lineb("評価 中央値（★）", lambda v: med((r["rating"] or 0) / 10 for r in v if r["rating"]))
lineb("評価件数 中央値", lambda v: med(r["reviews"] for r in v))
lineb("評価件数 100以上", lambda v: pct((r["reviews"] or 0) >= 100 for r in v))
lineb("実セラー数 中央値（生存・新品・Amazon除く）", lambda v: med(r["sellers"] for r in v))
lineb("実セラー数 5以上", lambda v: pct(r["sellers"] >= 5 for r in v))
lineb("実セラー数 1以下（独占）", lambda v: pct(r["sellers"] <= 1 for r in v))
lineb("Amazon本体が生存オファーにいる", lambda v: pct(r["amz"] for r in v))
lineb("90日 Buy Box 価格の振れ幅 中央値", lambda v: med(r["bbvol"] for r in v))
lineb("90日 Buy Box 価格の記録点数 中央値（変動回数の目安）", lambda v: med(r["bbchg"] for r in v))
lineb("90日で Buy Box を取った出品者の数 中央値", lambda v: med(r["bbsellers"] for r in v))
