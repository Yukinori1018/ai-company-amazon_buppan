# -*- coding: utf-8 -*-
"""成分ごとにラベル別の中央値を出す。どの成分が本命を沈めているのかを特定する。"""
import csv, json, statistics as st, collections
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
HERE = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004/t40"
P = json.load(open(HERE + "/t45_prod_v2.json"))
rows = list(csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")))
asin2m = {r['ASIN']: r['メーカー/ブランド'] for r in rows}
labels = {x['maker']: x['label'] for x in json.load(open(AO + "/sample200_labeled.json"))}
by = collections.defaultdict(lambda: collections.defaultdict(list))
for a, p in P.items():
    lab = labels.get(asin2m.get(a, ''))
    if not lab: continue
    for k in ('D1','D2','D3','D4'):
        if p[k] is not None: by[lab][k].append(p[k])
    by[lab]['down'].append(p['down'] or 0)
    by[lab]['chg'].append(p['chg'] or 0)
    by[lab]['dcnt'].append(p['dcnt'] if p['dcnt'] is not None else 0)
    by[lab]['drop'].append(p['drop'] if p['drop'] is not None else 0)
    by[lab]['cnow'].append(p['cnow'] if p['cnow'] is not None else 0)
NAME={'A1':'A1 日本の小規模','A2':'A2 日本の中堅','B':'B 大企業','C':'C 版元','D':'D 中国系OEM','E':'E 海外'}
print(f"{'区分':<16}{'n':>4}{'下方向値幅':>10}{'改定/180d':>10}{'直近下落':>9}{'オファー増':>10}{'現オファー':>10}")
for k in ('A1','A2','B','C','D','E'):
    d = by.get(k)
    if not d: continue
    n = len(d['down'])
    print(f"{NAME[k]:<16}{n:>4}{st.median(d['down'])*100:>9.1f}%{st.median(d['chg']):>10.0f}{st.median(d['drop'])*100:>8.1f}%{st.median(d['dcnt']):>10.1f}{st.median(d['cnow']):>10.1f}")
print()
print("=== 「オファー増加」だけで見たとき（相乗りが増えている割合） ===")
for k in ('A1','A2','B','C','D','E'):
    d = by.get(k)
    if not d: continue
    v = d['dcnt']; n=len(v)
    print(f"{NAME[k]:<16}{n:>4}  +1以上:{sum(1 for x in v if x>=1)/n*100:>5.1f}%   +2以上:{sum(1 for x in v if x>=2)/n*100:>5.1f}%")
print()
print("=== 「下方向値幅15%以上」の割合（値崩れしている） ===")
for k in ('A1','A2','B','C','D','E'):
    d = by.get(k)
    if not d: continue
    v=d['down']; n=len(v)
    print(f"{NAME[k]:<16}{n:>4}  ≥15%:{sum(1 for x in v if x>=.15)/n*100:>5.1f}%   ≥30%:{sum(1 for x in v if x>=.30)/n*100:>5.1f}%")
