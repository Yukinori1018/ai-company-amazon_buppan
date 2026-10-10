"""SD 照会キュー（大）を作る。Keepa キャッシュのみ（トークン0）。

母集団: monthlySold>=50 × JAN あり × Amazon 本体がカートを持たない。
並び: 過去1か月の多い順。上限なし（§3.3-34）。50行ずつ書き出す。
"""
import csv, json, os, pickle, re, sys, glob, datetime
PIPE = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
sys.path.insert(0, PIPE)
import fba_cost as fc
import price_history as ph
import set_count as sc

S = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003/sd_queue_big"
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/"
T3 = AO + "T-20260920-003/"
OUT = T3 + "sd_lookup_queue_big_20261011.csv"
AMZ = "AN1VRQENFRJN5"

best = pickle.load(open(f"{S}/best.pkl", "rb"))

# ── 既に照会済み・照会中の JAN ─────────────────────────────
done = set()
def add_jans(text):
    for j in re.findall(r"\b\d{13}\b|\b\d{8}\b", text):
        done.add(j)
for f in [T3 + "sd_lookup_queue_20261011.csv",
          T3 + "sd_buylist20261009/laneA_jans_20261009.txt",
          T3 + "sd/laneA_jans_20261001.txt"]:
    add_jans(open(f, encoding="utf-8-sig").read())
for f in [T3 + "sd/laneA_jan_hits.jsonl", T3 + "sd_buylist20261009/laneA_hits_20261009.jsonl"]:
    for l in open(f):
        try: done.add(json.loads(l)["jan"])
        except Exception: pass
n_done = len(done)
# SD の索引で既に JAN が分かっている商品（照会しなくても SD にあると分かっている）
sd_known = set()
for r in json.load(open(T3 + "pipeline/sd_rows.json")):
    if r.get("jan"): sd_known.add(r["jan"])
for l in open(T3 + "sd_buylist20261009/sd_rows_harvested.jsonl"):
    try:
        j = json.loads(l).get("jan")
        if j: sd_known.add(j)
    except Exception: pass

# ── メーカー台帳（代表 ASIN とカート保持者）─────────────────
M = AO + "T-20260930-001/"
maker = {}   # asin -> (出所, カート保持者)
maker_brands = set()
for f in sorted(glob.glob(M + "24_連絡先_batch?.csv")) + ["22_連絡先_印付き.csv", "10_メーカー候補_完全版.csv"]:  # 実画面の確認がある台帳を優先
    path = f if f.startswith("/") else M + f
    name = os.path.basename(path)
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        a = (r.get("代表ASIN") or r.get("代表ASIN(タカシ)") or "").strip()
        cart = (r.get("カート保持者(実画面9/30)") or r.get("カート保持セラー(代表)") or "").strip()
        for x in [a] + re.split(r"[／/;, ]+", r.get("統合した行のASIN", "")):
            x = x.strip()
            if re.match(r"^B0[0-9A-Z]{8}$", x) and x not in maker:
                maker[x] = (f"メーカー台帳({name.split('_')[0]}_{name.split('_')[-1].replace('.csv','')})", cart if x == a else "")
        if r.get("ブランド"): maker_brands.add(r["ブランド"].strip().lower())

def kdate(lu):
    return (datetime.datetime(2011, 1, 1) + datetime.timedelta(minutes=lu)).date() if lu else None

def set_count(r):
    """(表示, 計算に使う数, 確定か)。

    商品名の数字は「28枚入り」（中身）と「×2個セット」（セット）が同じ書き方で逆の意味になる
    （CLAUDE.md §3.3-17）。**商品名からは決めない。**確定させるのは Keepa PQ が 1〜24 で
    商品名と食い違わないときだけ。それ以外は「Amazon1個＝卸1点」として上限を出し、要確認と書く。
    """
    pq, title = r.get("pq"), r.get("title") or ""
    t = sc.parse_amazon_set_count(title)
    if pq == 1 and not (t and t > 1):
        return ("1", 1, True)
    if pq and 1 < pq <= 24 and (not t or t == pq):
        return (str(pq), pq, True)
    parts = []
    if pq: parts.append(f"Keepa PQ={pq}")
    if t and t > 1: parts.append(f"商品名に数字{t}")
    return ("要確認(" + "・".join(parts) + ")" if parts else "1?", 1, False)

def price(r):
    """(中央, 悲観, 根拠)"""
    csvl = [None] * 19
    csvl[1] = r.get("csv1"); csvl[18] = r.get("csv18")
    if r.get("csv1") or r.get("csv18"):
        lv = ph.from_product({"csv": csvl})
        if lv.median90:
            return lv.median90, lv.p25_90 or lv.median90, f"90日中央値({lv.source.split('（')[0]})・{lv.verdict}"
    a = r.get("avg90") or []
    cands = [v for v in (a[18] if len(a) > 18 else -1, a[1] if len(a) > 1 else -1) if v and v > 0]
    if not cands:
        return None, None, "価格なし"
    mid = min(cands)
    m = r.get("min90") or []
    lows = [x[1] for x in (m[1] if len(m) > 1 else None, m[18] if len(m) > 18 else None) if x and x[1] and x[1] > 0]
    worst = min(lows) if lows else mid
    return mid, min(worst, mid), "履歴なし→90日平均で代用(悲観=90日最安)"

def tier(r, sell):
    t = fc.tier_from_fba_fee(r.get("fba"), sell)
    if t: return t
    d = r.get("dims") or (None,) * 4
    return fc.tier_from_dimensions(*d)

def cap(sell, worst, t, pct, n, want):
    """卸1点あたり上限（税抜）。want='B' or 'A'。二分探索。"""
    if not (sell and t and n): return None
    def ok(cost):
        g = fc.grade(sell, cost, t, keepa_pct=pct, sell_worst=worst).grade
        return g == "A" if want == "A" else g in ("A", "B")
    lo, hi = 1.0, float(sell)
    if not ok(lo): return 0
    for _ in range(30):
        mid = (lo + hi) / 2
        if ok(mid): lo = mid
        else: hi = mid
    return int(lo / 1.1 / n)

def cart(r, mk):
    bbs = r.get("bbs")
    if not bbs and r.get("bbsh"):
        bbs = r["bbsh"][-1]
    if mk and mk[1]:
        h = mk[1]
        if "Amazon" in h and "本体" not in h and ("co.jp" in h or h.strip() == "Amazon"):
            return "AMAZON", h
        return "3P", h + "(台帳)"
    if bbs == AMZ or r.get("bbamz"):
        return "AMAZON", "Amazon.co.jp"
    if bbs and bbs not in ("-1", "-2"):
        return "3P", f"第三者({bbs})"
    ac = r.get("amzcur")
    if ac and ac > 0:
        return "AMZ_STOCK", "不明(本体在庫あり・本体カートの可能性)"
    return "UNK", "不明(本体在庫なし)"

rows, stats = [], dict(pool=0, noean=0, amazon=0, amzstock=0, done=0, sdknown=0, dupjan=0, rare=0)
seen_jan = {}
cands = [r for r in best.values() if (r.get("ms") or 0) >= 50]
stats["pool"] = len(cands)
cands.sort(key=lambda r: (-(r["ms"] or 0), r["asin"]))
for r in cands:
    jans = [j for j in (r.get("ean") or []) if re.fullmatch(r"\d{8}|\d{13}", j or "")]
    if not jans:
        stats["noean"] += 1; continue
    mk = maker.get(r["asin"])
    kind, holder = cart(r, mk)
    if kind == "AMAZON":
        stats["amazon"] += 1; continue
    if kind == "AMZ_STOCK":
        stats["amzstock"] += 1; continue
    if any(j in done for j in jans):
        stats["done"] += 1; continue
    if any(j in sd_known for j in jans):
        stats["sdknown"] += 1; continue
    key = jans[0]
    if key in seen_jan:
        seen_jan[key]["_dups"].append(f"{r['asin']}(月{r['ms']})"); stats["dupjan"] += 1; continue
    sell, worst, why = price(r)
    disp, n, decided = set_count(r)
    t = tier(r, sell) if sell else None
    pct = r.get("refpct")
    capB = cap(sell, worst, t, pct, n, "B")
    capA = cap(sell, worst, t, pct, n, "A")
    if mk:
        src = mk[0]
    elif (r.get("brand") or "").strip().lower() in maker_brands:
        src = "メーカー台帳と同ブランド"
    else:
        src = "Keepaプール"
    src += f" / {r['src'].split('/')[0]}/{r['src'].split('/')[1]}"
    note = []
    if not t: note.append("サイズ区分不明→上限計算不可")
    if not decided: note.append("セット数未確定→上限は「Amazon1個＝卸1点」として計算。卸と単位を揃えてから比べる")
    row = {"ASIN": r["asin"], "JAN": ";".join(jans), "商品名": (r.get("title") or "")[:80],
           "ブランド": r.get("brand") or "", "過去1か月(monthlySold)": f"{r['ms']}+",
           "カート保持者": holder, "セット数": disp,
           "売価90日中央値": sell or "", "B等級に必要な卸1点上限(税抜)": "" if capB is None else capB,
           "A等級に必要な卸1点上限(税抜)": "" if capA is None else capA,
           "母集団の出所": src, "価格の根拠": why, "Keepa取得日": str(kdate(r.get("lu"))),
           "Amazon URL": f"https://www.amazon.co.jp/dp/{r['asin']}",
           "SD検索URL": f"https://www.superdelivery.com/p/do/psl/?word={key}",
           "注意": "・".join(note), "_dups": []}
    seen_jan[key] = row
    rows.append(row)

cols = ["順位", "ASIN", "JAN", "商品名", "ブランド", "過去1か月(monthlySold)", "カート保持者", "セット数",
        "売価90日中央値", "B等級に必要な卸1点上限(税抜)", "A等級に必要な卸1点上限(税抜)", "母集団の出所",
        "価格の根拠", "Keepa取得日", "同じJANの他ASIN", "Amazon URL", "SD検索URL", "注意"]
tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for i, row in enumerate(rows, 1):
        row["順位"] = i
        row["同じJANの他ASIN"] = " ".join(row.pop("_dups"))
        w.writerow(row)
        if i % 50 == 0: fh.flush()
os.replace(tmp, OUT)
stats.update(rows=len(rows), done_jans=n_done, sd_known=len(sd_known))
print(json.dumps(stats, ensure_ascii=False))
import collections
print(collections.Counter(r["母集団の出所"].split(" / ")[0] for r in rows))
print(collections.Counter(r["カート保持者"][:6] for r in rows))
