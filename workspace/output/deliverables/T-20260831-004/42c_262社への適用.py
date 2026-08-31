# -*- coding: utf-8 -*-
"""262社に困り度v2を付け、2軸（困り度 × 期待月利）と提案タイプを出す。"""
import csv, json, statistics as st, collections, os
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
DL = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260831-004"
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(HERE + "/t45_prod_v2.json"))
rows = list(csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")))
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None
c262 = list(csv.DictReader(open(DL + "/33_連絡候補_規模情報つき.csv", encoding="utf-8-sig")))

bym = collections.defaultdict(list)
for r in rows:
    p = P.get(r['ASIN'])
    if not p: continue
    prof = None
    pr, ms = num(r['上限で仕入れた時の純利益']), num(r['想定月販'])
    if pr is not None and ms is not None: prof = pr * ms
    bym[r['メーカー/ブランド']].append((r, p, prof))

out = []
for c in c262:
    m = c['メーカー']
    lst = bym.get(m) or []
    if not lst:
        out.append(dict(c, 困り度=None)); continue
    ds = [x[1]['distress'] for x in lst]
    downs = [x[1]['down'] or 0 for x in lst]
    dcnts = [x[1]['dcnt'] if x[1]['dcnt'] is not None else 0 for x in lst]
    drops = [x[1]['drop'] if x[1]['drop'] is not None else 0 for x in lst]
    profs = [x[2] for x in lst if x[2] is not None]
    direct = any((x[0].get('メーカー直販フラグ') or '').strip() not in ('', '0', 'なし', 'False') for x in lst)
    best = max(lst, key=lambda x: x[1]['distress'])
    n_down15 = sum(1 for d in downs if d >= .15)
    n_up1 = sum(1 for d in dcnts if d >= 1)
    typ = ('①値崩れ＋相乗り増（提案が最も刺さる）' if (max(downs) >= .15 and max(dcnts) >= 1)
           else '②値崩れのみ' if max(downs) >= .15
           else '③相乗り増のみ' if max(dcnts) >= 1
           else '④静か（独占提案は早い。まず仕入れ）')
    out.append(dict(c,
        困り度=round(max(ds), 1), 困り度中央値=round(st.median(ds), 1),
        値崩れ幅_最大=round(max(downs) * 100, 1), 直近下落_最大=round(max(drops) * 100, 1),
        オファー増_最大=int(max(dcnts)),
        値崩れSKU数=n_down15, 相乗り増SKU数=n_up1, 対象SKU数=len(lst),
        提案タイプ=typ,
        メーカー直販=('あり' if direct else 'なし'),
        期待月利_合計=int(sum(profs)) if profs else '',
        期待月利_最大=int(max(profs)) if profs else '',
        証拠SKU=best[1]['title'][:50],
        証拠=f"{int(best[1]['p50']) if best[1]['p50'] else '?'}円→{int(best[1]['pnow']) if best[1]['pnow'] else '?'}円 / オファー{int(best[1]['cnow']) if best[1]['cnow'] is not None else '?'}件({int(best[1]['dcnt']) if best[1]['dcnt'] is not None else 0:+d}) / 改定{best[1]['chg']}回",
    ))

有 = [o for o in out if o.get('困り度') is not None]
print("困り度を出せた社:", len(有), "/", len(out))
print("\n=== 提案タイプの分布（262社） ===")
c = collections.Counter(o['提案タイプ'] for o in 有)
for k, v in sorted(c.items()):
    print(f"  {k:<32}{v:>4}社 ({v/len(有)*100:.1f}%)")
print("\n=== 2軸マトリクス（困り度45以上 × 期待月利1万円以上） ===")
def q(o, k): 
    v = o.get(k); return v if isinstance(v, int) else 0
hi_d = [o for o in 有 if o['困り度'] >= 45]
hi_p = [o for o in 有 if q(o, '期待月利_合計') >= 10000]
both = [o for o in 有 if o['困り度'] >= 45 and q(o, '期待月利_合計') >= 10000]
print(f"  困り度45以上          : {len(hi_d)}社")
print(f"  期待月利1万円以上      : {len(hi_p)}社")
print(f"  両方（最優先レーン）    : {len(both)}社")
print(f"  相関: 困り度 × 期待月利 →", end=" ")
import math
xs=[(o['困り度'], math.log10(max(q(o,'期待月利_合計'),1)+1)) for o in 有]
mx=st.mean([a for a,_ in xs]); my=st.mean([b for _,b in xs])
sx=math.sqrt(sum((a-mx)**2 for a,_ in xs)); sy=math.sqrt(sum((b-my)**2 for _,b in xs))
print(f"r={sum((a-mx)*(b-my) for a,b in xs)/(sx*sy):+.3f}")

print("\n=== 最優先レーン（困り度×期待月利 の両方が上位）上位20 ===")
both.sort(key=lambda o: -(o['困り度'] * math.log10(q(o,'期待月利_合計')+10)))
print(f"{'メーカー':<24}{'困り度':>6}{'値崩れ':>7}{'増':>4}{'期待月利':>9}{'規模':>6}  証拠")
for o in both[:20]:
    print(f"{o['メーカー'][:22]:<24}{o['困り度']:>6.0f}{o['値崩れ幅_最大']:>6.0f}%{o['オファー増_最大']:>4}{q(o,'期待月利_合計'):>9}{(o.get('規模区分') or '不明')[:5]:>6}  {o['証拠']}")

flds = list(out[0].keys())
with open(HERE + "/t47_262_困り度.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=flds); w.writeheader()
    for o in sorted(out, key=lambda x: -(x.get('困り度') or -1)): w.writerow(o)
json.dump(out, open(HERE + "/t47_262.json", "w"), ensure_ascii=False)
print("\nwrote t47_262_困り度.csv")
