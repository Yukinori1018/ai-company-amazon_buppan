"""T-20260915-001 実測：承認済みサプライヤーの NETSEA 商品の販売条件の分布と、
その JAN が Amazon.co.jp に存在するか（Keepa）をサンプルで数える。

用途：NETSEA 内で完結する仕入れの検討（procurement）。社名は出力しない。
出力：out/ （Git 追跡外）。公開版の成果物には比率だけを書く。
"""
import collections, gzip, io, json, os, random, sys, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
ROOT = HERE.parents[3]
CODE = ROOT / "workspace/output/deliverables/T-20260521-005/code"
ENV = ROOT / "workspace/output/agent_output/T-20260521-005/code/.env"
for line in ENV.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(CODE))
from adapters.netsea import NetseaClient  # noqa: E402

random.seed(20260915)
N_SUPPLIERS = int(os.environ.get("N_SUPPLIERS", 40))
ITEMS_PER_SUPPLIER = 100
N_JAN = int(os.environ.get("N_JAN", 300))

c = NetseaClient()
sups = c.list_suppliers()
print("approved suppliers:", len(sups), c.last_error, flush=True)
pick = random.sample(sups, min(N_SUPPLIERS, len(sups)))
rows = []
for i, s in enumerate(pick):
    r, cov = c.list_supplier_items_raw(int(s["id"]), max_items=ITEMS_PER_SUPPLIER)
    for x in r:
        x["_sid"] = int(s["id"])
    rows.extend(r)
    print(i, s["id"], len(r), cov.get("error"), flush=True)
with open(OUT / "netsea_sample_rows.jsonl", "w") as f:
    for x in rows:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")


def valid_jan(j):
    j = str(j or "").strip()
    return j.isdigit() and len(j) in (8, 13) and set(j) != {"0"}


flag_keys = ["image_copy_flag", "deal_net_shop_flag", "deal_net_auction_flag",
             "direct_send_flag", "net_bulk_order_flag", "reference_price_type"]
summ = {"n_items": len(rows), "n_suppliers_sampled": len(pick),
        "n_suppliers_approved": len(sups),
        "n_suppliers_with_items": len({x["_sid"] for x in rows})}
for k in flag_keys:
    summ[k] = dict(collections.Counter(str(x.get(k)) for x in rows))
summ["jan_valid"] = sum(valid_jan(x.get("jan_code")) or any(valid_jan(s.get("jan_code")) for s in x.get("set", [])) for x in rows)

# JAN サンプル（商品単位で1つ・サプライヤー偏りを抑えるため1社最大15件）
per = collections.defaultdict(list)
for x in rows:
    j = x.get("jan_code") if valid_jan(x.get("jan_code")) else next((s.get("jan_code") for s in x.get("set", []) if valid_jan(s.get("jan_code"))), None)
    if j:
        per[x["_sid"]].append((str(j), x))
cand = []
for sid, lst in per.items():
    random.shuffle(lst); cand.extend(lst[:15])
random.shuffle(cand)
seen = set(); jans = []
for j, x in cand:
    if j not in seen:
        seen.add(j); jans.append((j, x))
jans = jans[:N_JAN]

KEY = os.environ["KEEPA_API_KEY"]


def keepa(codes):
    q = urllib.parse.urlencode(dict(key=KEY, domain=5, code=",".join(codes), stats=1, history=0))
    b = urllib.request.urlopen(urllib.request.Request(f"https://api.keepa.com/product?{q}", headers={"Accept-Encoding": "gzip"}), timeout=300).read()
    try:
        b = gzip.decompress(b)
    except OSError:
        pass
    return json.loads(b)


found = {}
for i in range(0, len(jans), 50):
    batch = [j for j, _ in jans[i:i + 50]]
    for attempt in range(20):
        r = keepa(batch)
        if r.get("error") or ("products" not in r and r.get("tokensLeft", 0) < 0):
            print("wait", r.get("error"), r.get("tokensLeft"), flush=True); time.sleep(60); continue
        break
    print("keepa", i, "tokLeft", r.get("tokensLeft"), "consumed", r.get("tokensConsumed"), flush=True)
    for p in r.get("products") or []:
        codes = set((p.get("eanList") or []) + (p.get("upcList") or []))
        st = p.get("stats") or {}
        cur = st.get("current") or []
        rec = {"asin": p.get("asin"), "title": p.get("title"), "brand": p.get("brand"),
               "rootCategory": p.get("rootCategory"),
               "amazon_now": (cur[0] if len(cur) > 0 else None),
               "new_offer_count_now": (cur[11] if len(cur) > 11 else None),
               "salesrank_now": (cur[3] if len(cur) > 3 else None),
               "monthlySold": p.get("monthlySold"),
               "listedSince": p.get("listedSince")}
        for j in batch:
            if j in codes or j.lstrip("0") in {c.lstrip("0") for c in codes}:
                found.setdefault(j, []).append(rec)

out = []
for j, x in jans:
    recs = found.get(j, [])
    out.append({"jan": j, "sid": x["_sid"], "category_id": x.get("category_id"),
                "product_name": x.get("product_name"),
                "image_copy_flag": x.get("image_copy_flag"),
                "deal_net_shop_flag": x.get("deal_net_shop_flag"),
                "deal_net_auction_flag": x.get("deal_net_auction_flag"),
                "direct_send_flag": x.get("direct_send_flag"),
                "min_price": min((float(s.get("price") or 0) for s in x.get("set", []) if s.get("price")), default=None),
                "reference_price": max((float(s.get("reference_price") or 0) for s in x.get("set", [])), default=None),
                "n_asin": len(recs), "amazon": recs})
with open(OUT / "jan_amazon_match.jsonl", "w") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")
summ["n_jan_checked"] = len(out)
summ["n_jan_found_on_amazon"] = sum(1 for o in out if o["n_asin"])
json.dump(summ, open(OUT / "summary_raw.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(summ, ensure_ascii=False, indent=1))
