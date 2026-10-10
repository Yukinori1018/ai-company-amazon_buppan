"""SD 照会キュー（大）の前段: agent_output 配下の全 Keepa キャッシュ（json/jsonl/json.gz）から
商品レコードを集め、ASIN ごとに lastUpdate が最新のものを残す（トークン0）。
入力ファイル一覧は files.txt / gzfiles.txt（grep -l '"monthlySold"' と prod_*.json.gz で作る）。
旧: 全 Keepa キャッシュから商品レコードを集め、ASIN ごとに最新を残す（トークン0）。"""
import json, sys, os, pickle, gzip
S = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003/sd_queue_big"  # 作業ディレクトリ（gitignore 対象）
ROOT = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/"
files = [l.strip() for l in open(f"{S}/files.txt") if l.strip()] + [l.strip() for l in open(f"{S}/gzfiles.txt") if l.strip()]
best = {}
def take(p, src):
    a = p.get("asin")
    if not a or not isinstance(a, str): return
    lu = p.get("lastUpdate") or 0
    st = p.get("stats") or {}
    rec = dict(asin=a, title=p.get("title"), brand=p.get("brand"), mfr=p.get("manufacturer"),
               ean=p.get("eanList") or [], upc=p.get("upcList") or [],
               ms=p.get("monthlySold"), pq=p.get("packageQuantity"), noi=p.get("numberOfItems"),
               bbs=st.get("buyBoxSellerId"), bbamz=st.get("buyBoxIsAmazon"),
               oos365=None, csv1=(p.get("csv") or [None,None])[1] if p.get("csv") and len(p["csv"])>1 else None,
               csv18=(p["csv"][18] if p.get("csv") and len(p["csv"])>18 else None),
               cur=st.get("current"), avg90=st.get("avg90"),
               fba=(p.get("fbaFees") or {}).get("pickAndPackFee"),
               dims=(p.get("packageLength"),p.get("packageWidth"),p.get("packageHeight"),p.get("packageWeight")),
               root=p.get("rootCategory"), cattree=[c.get("name") for c in (p.get("categoryTree") or [])],
               refpct=p.get("referralFeePercentage"), lu=lu, src=src.replace(ROOT,""),
               parent=p.get("parentAsin"), model=p.get("model"),
               bbsh=(p.get("buyBoxSellerIdHistory") or [])[-1:] ,
               min90=st.get("minInInterval"), amzcur=(st.get("current") or [None])[0])
    o = st.get("outOfStockPercentage365")
    if isinstance(o, list) and o: rec["oos365"] = o[0]
    cur = best.get(a)
    if cur is None or lu > cur["lu"] or (lu == cur["lu"] and rec["csv1"] and not cur["csv1"]):
        best[a] = rec
def walk(x, src):
    if isinstance(x, dict):
        if "asin" in x and ("csv" in x or "monthlySold" in x or "eanList" in x):
            take(x, src); return
        for v in x.values(): walk(v, src)
    elif isinstance(x, list):
        for v in x: walk(v, src)
for f in files:
    path = ROOT + f[2:]
    try:
        if f.endswith(".jsonl"):
            for line in open(path):
                line=line.strip()
                if line:
                    try: walk(json.loads(line), path)
                    except Exception: pass
        elif f.endswith(".gz"):
            walk(json.load(gzip.open(path)), path)
        else:
            walk(json.load(open(path)), path)
    except Exception as e:
        print("ERR", f, e, file=sys.stderr)
pickle.dump(best, open(f"{S}/best.pkl","wb"))
print(len(best))
