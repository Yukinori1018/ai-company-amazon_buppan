# -*- coding: utf-8 -*-
"""再設計ルールを既存CSVに適用し、成果物CSV3本と集計JSONを出す。"""
import csv, json, re, sys, collections, statistics
sys.path.insert(0, ".")
from rules_v2 import *
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
    r["_sellers"] = [x.strip() for x in (r["セラー名一覧"] or "").split(" / ") if x.strip()]
    bn = nrm(r["ブランド"]) or nrm(r["_mfr"]) or nrm(r["_maker"])
    r["_indep"] = independent_sellers(bn, r["_sellers"])
    r["_jpindep"] = jp_sellers(r["_indep"])

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
    wholesale = any(len(x["_indep"]) >= 2 and len(x["_jpindep"]) >= 1 for x in rs)
    best = max(rs, key=lambda x: len(x["_jpindep"]))
    proc = [num(x["想定仕入れ金額(上限)"]) for x in rs]
    proc = [p for p in proc if p]
    label = LABELS.get(k, "?")
    # ---- 判定 ----
    if redist:              status, reason = "条件付き（再販/版元カテゴリ）", f"ルートカテゴリ={root}"
    elif not s_jp and cn:   status, reason = "除外（海外・国内窓口なし）", "／".join(sorted(cn))
    elif not s_jp:          status, reason = "除外（日本実体の証拠なし）", "JAN45/49・日本語社名・日本法人格のいずれも無し"
    elif not wholesale:     status, reason = "除外（卸の証拠なし）", "第三者の国内セラーが2社以上いる商品が無い"
    elif label == "N":      status, reason = "除外（会社名でない）", "商品名/作品名/PB のため問い合わせ先が存在しない"
    elif label == "L":      status, reason = "除外（規模：大企業）", "従業員300人超の見込み（手判定・要gBizINFO検証）"
    else:                   status, reason = "連絡候補", ""
    recs.append(dict(
        メーカー=k, 該当商品数=len(rs), 主なカテゴリ=root, 判定=status, 判定理由=reason,
        規模手判定={"M": "中小の見込み", "L": "大企業の見込み", "U": "判定不能",
                    "N": "会社名でない", "?": "未判定"}[label],
        日本実体シグナル="／".join(sorted(s_jp)) or "なし",
        海外シグナル="／".join(sorted(cn)) or "なし",
        卸の証拠=("あり" if wholesale else "なし"),
        国内独立セラー例=" / ".join(best["_jpindep"][:3]),
        国内独立セラー数=len(best["_jpindep"]),
        独立セラー数=len(best["_indep"]),
        実セラー数_現行=best["実セラー数"],
        想定仕入れ金額の中央値=(int(statistics.median(proc)) if proc else ""),
        代表ASIN=best["ASIN"], 代表商品名=best["商品名"][:60],
        代表Amazonページ=best["Amazonページ"], メーカー検索=best["メーカー検索(Google)"],
        _label=label, _s=len(s_jp), _w=wholesale,
    ))

order = {"連絡候補": 0, "条件付き（再販/版元カテゴリ）": 1, "除外（規模：大企業）": 2,
         "除外（卸の証拠なし）": 3, "除外（会社名でない）": 4,
         "除外（日本実体の証拠なし）": 5, "除外（海外・国内窓口なし）": 6}
recs.sort(key=lambda x: (order[x["判定"]], -x["該当商品数"], x["メーカー"]))
COLS = [c for c in recs[0] if not c.startswith("_")]

def dump(path, rs):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rs: w.writerow({c: r[c] for c in COLS})

dump(f"{OUT}/10_連絡候補メーカー.csv", [r for r in recs if r["判定"] == "連絡候補"])
dump(f"{OUT}/11_条件付き候補_再販版元カテゴリ.csv",
     [r for r in recs if r["判定"].startswith("条件付き")])
dump(f"{OUT}/12_全メーカー判定台帳.csv", recs)

c = collections.Counter(r["判定"] for r in recs)
p = collections.Counter()
for r in recs: p[r["判定"]] += r["該当商品数"]
summary = {"メーカー総数": len(recs), "商品総数": len(ROWS),
           "判定内訳": {k: {"社": c[k], "商品": p[k]} for k in order}}
cand = [r for r in recs if r["判定"] == "連絡候補"]
summary["連絡候補の規模内訳"] = dict(collections.Counter(r["規模手判定"] for r in cand))
json.dump(summary, open(f"{OUT}/13_集計.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k in order: print(f"  {k:28s} {c[k]:5d}社 / 商品{p[k]:5d}件")
print("\n連絡候補の規模内訳:", summary["連絡候補の規模内訳"])
print("連絡候補", len(cand), "社 / 商品", sum(r['該当商品数'] for r in cand), "件")
