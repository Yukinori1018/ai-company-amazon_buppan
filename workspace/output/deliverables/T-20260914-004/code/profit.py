#!/usr/bin/env python3
"""T-2: 照合できた行に 2026 手数料・大口・広告0（相乗り）で利益と回転を付ける。0 API call。

入力: matches.jsonl（match.py）／T-1 raw product（寸法・カテゴリ・カート90日平均）
出力: ../../../deliverables/T-20260914-004/out/t2_matched.csv（金額入り・Git 追跡外）
      ../../../deliverables/T-20260914-004/out/t2_summary.json（件数のみ）

前提（profit2026.py と同じ。推定は5つ: 保管1.5ヶ月・納品49.5円・資材・返品3%・広告）:
- 売値 = Keepa stats.avg90[18]（カート＋送料の90日平均）。無ければ新品最安（T-1 取得時点）
- 卸値 = NETSEA 税抜単価 × 入数倍率 × 1.1。入数が確定できない行は倍率1で計算し「入数要確認」
- 資材 30円（単品でも付ける＝依頼の置き値）。広告 0（相乗り）
- 取り分 = 公表の月間購入数(下限) ÷ (新品オファー＋1)（T-1 の列）
- ロット = max(最小発注の出品数, 10)。回転 = ロット ÷ 取り分
"""
import csv, gzip, json, math, re, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
D = REPO / "workspace/output/deliverables"
sys.path.insert(0, str(D / "T-20260914-001")); sys.path.insert(0, str(D / "T-20260521-005/code"))
sys.path.insert(0, str(D / "T-20260831-006"))
import profit2026 as P
from adapters.amazon_data import _CATEGORY_NAME_MAP
from pipeline.pack import resolve_multiplier
from recut import GATE_KNOWN
RAW = REPO / "workspace/output/agent_output/T-20260914-002/t1_raw"
OUTD = D / "T-20260914-004/out"; OUTD.mkdir(parents=True, exist_ok=True)
MATERIAL = 30.0; LOT_MIN = 10
MARGINS = (0.10, 0.12, 0.15); TURN_MAX = 2.5; SHARE_MIN = 6.0
POOL = {r["ASIN"]: r["供給ステータス"] for r in csv.DictReader(open(D / "T-20260909-002/pool.csv", encoding="utf-8-sig"))}

def cat_key(tree):
    for n in [c["name"] for c in (tree or [])]:
        for needle, key in _CATEGORY_NAME_MAP:
            if needle in n: return key
    return "default"

prods = {}
for f in sorted(RAW.glob("prod_*.json.gz")):
    for p in json.loads(gzip.decompress(f.read_bytes())).get("products") or []: prods[p["asin"]] = p

RANK = {"JAN一致": 0, "JAN一致(Keepa経由)": 1, "型番一致": 2}
def tier(how): return how if how in RANK else "名称近似"

rows = []
for line in open(HERE / "matches.jsonl", encoding="utf-8"):
    m = json.loads(line); t2 = m["t2"]; p = prods.get(m["asin"], {})
    title = p.get("title") or t2["タイトル"]
    avg90 = (p.get("stats") or {}).get("avg90") or []
    bb = avg90[18] if len(avg90) > 18 and avg90[18] and avg90[18] > 0 else None
    price = float(bb) if bb else float(t2["価格(新品最安)"] or 0)
    price_src = "カート90日平均" if bb else "新品最安(T-1時点)"
    dims = [p.get(k) for k in ("packageLength", "packageWidth", "packageHeight")]
    dims = dims if all(d and d > 0 for d in dims) else []
    g = p.get("packageWeight") if (p.get("packageWeight") or 0) > 0 else None
    ck = cat_key(p.get("categoryTree"))
    share = float(t2["取り分"] or 0)
    best = None
    for s in m["matches"]:
        if not s.get("price"): continue
        mult, why, unc = resolve_multiplier(f"{s['name']} {s.get('label') or ''}", title)
        w_incl = s["price"] * mult * 1.1
        pr = P.breakdown(price=price, wholesale_incl=w_incl, category_key=ck, package_mm=dims, package_g=g,
                         ad_rate=0.0, material_yen=MATERIAL)
        moq = max(1, math.ceil((s.get("set_num") or 1) / mult))
        lot = max(moq, LOT_MIN)
        cand = dict(s=s, mult=mult, why=why, unc=unc, w=w_incl, pr=pr, moq=moq, lot=lot)
        # 優先: 確度 → 在庫あり・ネット販売可 → 利益率
        key = (RANK.get(tier(s["how"]), 3), s.get("sold_out") == "Y", s.get("net_ok") != "Y", -pr.margin)
        if best is None or key < best[0]: best = (key, cand)
    if not best: continue
    c = best[1]; s = c["s"]; pr = c["pr"]
    turn = c["lot"] / share if share else None
    rows.append({
        "ASIN": m["asin"], "JAN(T-1)": t2["JAN"], "照合の確度": tier(s["how"]), "照合の詳細": s["how"],
        "ブランド": t2["ブランド"], "メーカー": t2["メーカー"], "区分": t2["区分"], "大手": t2["大手"],
        "タイトル": title[:80], "NETSEA商品名": f"{s['name']} {s.get('label') or ''}"[:80],
        "サプライヤー": s["shop"], "NETSEA URL": s["url"], "NETSEA JAN": s["jan"],
        "ネット販売可": s.get("net_ok"), "在庫切れ": s.get("sold_out"), "NETSEA更新日": s.get("upd"),
        "売値": round(price), "売値の出どころ": price_src, "卸単価(税抜)": s["price"], "入数倍率": c["mult"],
        "入数の根拠": c["why"], "入数要確認": "要確認" if c["unc"] else "",
        "卸値(税込・1出品)": round(c["w"]), "純利益": round(pr.net), "利益率%": round(pr.margin * 100, 1),
        "販売手数料": round(pr.referral_fee), "FBA配送代行": round(pr.fba_fee), "FBAサイズ": pr.size_label,
        "カテゴリ": ck, "月販推定(公表下限)": t2["月販推定(公表下限)"], "新品オファー数": t2["新品オファー数"],
        "取り分": share, "最小発注の出品数": c["moq"], "ロット": c["lot"], "ロット金額": round(c["lot"] * c["w"]),
        "回転月数": round(turn, 2) if turn else None,
        "ゲート": GATE_KNOWN.get(m["asin"], "未確認"), "終売の兆候": t2["終売の兆候"],
        "供給(9/12人手)": POOL.get(m["asin"], ""), "他の候補規格数": len(m["matches"]) - 1,
    })

rows.sort(key=lambda r: (-(r["利益率%"] >= 12), r["回転月数"] or 99, -r["利益率%"]))
with open(OUTD / "t2_matched.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def funnel(rs, mline):
    st = [("照合できた", rs)]
    rs = [r for r in rs if r["利益率%"] >= mline * 100]; st.append((f"利益率≥{int(mline*100)}%", rs))
    rs = [r for r in rs if r["回転月数"] is not None and r["回転月数"] <= TURN_MAX]; st.append(("回転≤2.5ヶ月", rs))
    rs = [r for r in rs if r["取り分"] >= SHARE_MIN]; st.append(("取り分≥6", rs))
    rs = [r for r in rs if not r["ゲート"].startswith("要解除")]; st.append(("既知ゲートなし", rs))
    rs2 = [r for r in rs if not r["終売の兆候"]]; st.append(("終売の兆候なし", rs2))
    rs3 = [r for r in rs2 if r["ネット販売可"] == "Y" and r["在庫切れ"] != "Y"]; st.append(("ネット販売可・在庫あり", rs3))
    rs4 = [r for r in rs3 if not r["入数要確認"]]; st.append(("入数確定", rs4))
    return [(n, len(x), len({r["ブランド"] for r in x})) for n, x in st]

summary = {"照合行": len(rows), "確度別": Counter(r["照合の確度"] for r in rows),
           "funnel": {f"{int(m*100)}%": funnel(rows, m) for m in MARGINS},
           "確度別_12%全条件": {}, "卸別": Counter(r["サプライヤー"] for r in rows).most_common(30),
           "売値の出どころ": Counter(r["売値の出どころ"] for r in rows)}
for t in RANK.keys() | {"名称近似"}:
    summary["確度別_12%全条件"][t] = funnel([r for r in rows if r["照合の確度"] == t], 0.12)[-1][1]
json.dump(summary, open(OUTD / "t2_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=list)
print(json.dumps(summary, ensure_ascii=False, indent=1, default=list))
