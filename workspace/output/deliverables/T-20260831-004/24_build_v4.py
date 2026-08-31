# -*- coding: utf-8 -*-
"""v3: 規模ゲートを「大企業確定」だけに絞り、卸証拠をゲートから階層へ降格。"""
import csv, json, re, sys, collections, statistics
sys.path.insert(0, ".")
from rules_v2 import *
from size_strict import is_large_certain
from hand_labels import LABELS

OUT = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260831-004"
csv.field_size_limit(10**7)
ROWS = list(csv.DictReader(open("snapshot_02.csv", encoding="utf-8-sig")))
EAN = json.load(open("ean_index.json", encoding="utf-8"))

def num(x):
    try: return float(str(x).replace(",", ""))
    except Exception: return None

for r in ROWS:
    r["_ean"] = (EAN.get(r["ASIN"], {}) or {}).get("ean") or []
    r["_cc"] = ean_cc(r["_ean"])
    r["_maker"] = (r["メーカー/ブランド"] or "").strip()
    r["_mfr"] = (r["manufacturer"] or "").strip()
    r["_root"] = (r["カテゴリ"] or "").split(" > ")[0].strip()
    sl = [x.strip() for x in (r["セラー名一覧"] or "").split(" / ") if x.strip()]
    r["_sellers"] = sl
    bn = nrm(r["ブランド"]) or nrm(r["_mfr"]) or nrm(r["_maker"])
    r["_indep"] = independent_sellers(bn, sl)
    r["_jpindep"] = jp_sellers(r["_indep"])
    r["_unres"] = unresolved_sellers(sl)

M = collections.defaultdict(list)
for r in ROWS: M[r["_maker"]].append(r)

recs = []
for k, rs in M.items():
    cc = collections.Counter(x["_cc"] for x in rs if x["_cc"])
    mfrs = [x["_mfr"] for x in rs if x["_mfr"]]
    sellers = sorted({s for x in rs for s in x["_sellers"]})
    s_jp = s_jp_signals(k, mfrs, cc)
    cn, cnl = cn_signals(k, mfrs, sellers)
    root = collections.Counter(x["_root"] for x in rs).most_common(1)[0][0]
    redist = root in REDIST_ROOT
    mi = max(len(x["_indep"]) for x in rs)
    mj = max(len(x["_jpindep"]) for x in rs)
    mu = max(len(x["_unres"]) for x in rs)
    if   mi >= 2 and mj >= 1: tier, tname = "A", "A: 国内の第三者が2社以上で扱っている"
    elif mi >= 1 and mj >= 1: tier, tname = "B", "B: 国内の第三者が1社扱っている"
    elif mi == 0 and mu >= 2: tier, tname = "E", "E: セラー名未解決のため判定保留（Keepa再取得が要る）"
    elif mi >= 1:             tier, tname = "C", "C: 第三者はいるが国内事業者ではない"
    else:                     tier, tname = "D", "D: 直営・系列店しかいない"
    label = LABELS.get(k, "?")
    large = is_large_certain(k)
    best = max(rs, key=lambda x: (len(x["_jpindep"]), len(x["_indep"])))
    proc = [p for p in (num(x["想定仕入れ金額(上限)"]) for x in rs) if p]
    if   redist:            st, why = "条件付き（再販/版元カテゴリ）", f"ルートカテゴリ={root}"
    elif not s_jp and cn:   st, why = "除外（海外・国内窓口なし）", "／".join(sorted(cn))
    elif not s_jp:          st, why = "除外（日本実体の証拠なし）", "JAN45/49・日本語社名・日本法人格のいずれも無し"
    elif tier == "C" and ("メーカー名日本語" in s_jp or "日本法人格" in s_jp):
        st, why = "連絡候補", ""          # 日本語社名のメーカー＋第三者セラーあり。国籍不明でも残す
    elif tier in ("C", "D"): st, why = "除外（卸の証拠なし）", tname
    elif tier == "E" and large: st, why = "除外（規模：大企業確定）", "誰でも知る大企業"
    elif label == "N":      st, why = "除外（会社名でない）", "商品名/作品名/PB のため問い合わせ先が存在しない"
    elif large:             st, why = "除外（規模：大企業確定）", "誰でも知る大企業・上場グループ・グローバル本社"
    else:                   st, why = "連絡候補", ""
    size = ("大企業確定" if large else
            {"M": "中小の見込み（手判定）", "U": "規模未確認", "N": "会社名でない",
             "L": "規模未確認（大きい可能性あり）", "?": "規模未確認"}[label])
    recs.append(dict(
        メーカー=k, 該当商品数=len(rs), 主なカテゴリ=root, 判定=st, 判定理由=why,
        卸の証拠=tname, 規模=size,
        日本実体シグナル="／".join(sorted(s_jp)) or "なし",
        海外シグナル="／".join(sorted(cn)) or "なし",
        国内独立セラー例=" / ".join(best["_jpindep"][:3]),
        国内独立セラー数=mj, 独立セラー数=mi, 実セラー数_現行=best["実セラー数"],
        想定仕入れ金額の中央値=(int(statistics.median(proc)) if proc else ""),
        代表ASIN=best["ASIN"], 代表商品名=best["商品名"][:60],
        代表Amazonページ=best["Amazonページ"], メーカー検索=best["メーカー検索(Google)"],
        _tier=tier))

order = {"連絡候補": 0, "条件付き（再販/版元カテゴリ）": 1, "除外（規模：大企業確定）": 2,
         "除外（卸の証拠なし）": 3, "除外（会社名でない）": 4,
         "除外（日本実体の証拠なし）": 5, "除外（海外・国内窓口なし）": 6}
recs.sort(key=lambda x: (order[x["判定"]], x["_tier"], -x["該当商品数"], x["メーカー"]))
COLS = [c for c in recs[0] if not c.startswith("_")]
def dump(p, rs):
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rs: w.writerow({c: r[c] for c in COLS})

cand = [r for r in recs if r["判定"] == "連絡候補"]
dump(f"{OUT}/10_連絡候補メーカー.csv", cand)
dump(f"{OUT}/11_条件付き候補_再販版元カテゴリ.csv", [r for r in recs if r["判定"].startswith("条件付き")])
dump(f"{OUT}/12_全メーカー判定台帳.csv", recs)

c = collections.Counter(r["判定"] for r in recs); p = collections.Counter()
for r in recs: p[r["判定"]] += r["該当商品数"]
for k in order: print(f"  {k:28s} {c[k]:5d}社 / 商品{p[k]:5d}件")
print("\n連絡候補の卸証拠:", dict(collections.Counter(r['卸の証拠'][:1] for r in cand)))
print("連絡候補の規模  :", dict(collections.Counter(r['規模'] for r in cand)))
json.dump({"メーカー総数": len(recs), "商品総数": len(ROWS),
           "判定内訳": {k: {"社": c[k], "商品": p[k]} for k in order},
           "連絡候補_卸証拠": dict(collections.Counter(r['卸の証拠'] for r in cand)),
           "連絡候補_規模": dict(collections.Counter(r['規模'] for r in cand))},
          open(f"{OUT}/13_集計.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---- 並行実装の手作業ラベル200社で精度を測る（独立した検証セット）----
lab = json.load(open(f"{OUT}/11_手作業ラベル200社.json", encoding="utf-8"))
mine = {r["メーカー"] for r in cand}
POS = {"A1", "A2"}
pos = [x for x in lab if x["label"] in POS]
inl = [x for x in lab if x["maker"] in mine]
tp = [x for x in inl if x["label"] in POS]
print(f"\n--- 検証（並行実装のラベル200社・独立検証セット）---")
print(f"  適合率 {len(tp)}/{len(inl)} = {len(tp)/max(len(inl),1)*100:.1f}%")
print(f"  再現率 {len(tp)}/{len(pos)} = {len(tp)/max(len(pos),1)*100:.1f}%")
led = {r["メーカー"]: r for r in recs}
print("  取りこぼした本命:")
for x in pos:
    if x["maker"] not in mine:
        r = led.get(x["maker"])
        print(f"    {x['maker'][:24]:26s} {r['判定'] if r else 'リスト外'} / {r['判定理由'][:34] if r else ''}")
