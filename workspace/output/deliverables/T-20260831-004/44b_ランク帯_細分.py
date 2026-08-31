# -*- coding: utf-8 -*-
"""ランク帯を細かく刻んで本命率を見る＋母集団のランク分布の実態を確認する。"""
import csv, json, statistics, collections
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
labels = {x['maker']: x['label'] for x in json.load(open(AO + "/sample200_labeled.json"))}
rows = list(csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")))
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None

ranks = sorted(r for r in (num(x['ランク']) for x in rows) if r)
print("候補プール全体のランク分布 n=", len(ranks))
for q in (.05,.25,.5,.75,.9,.95,.99,1.0):
    i = min(int(len(ranks)*q), len(ranks)-1)
    print(f"  p{int(q*100):>3}: {int(ranks[i]):,}")
print("  ≤5万:", f"{sum(1 for r in ranks if r<=50000)/len(ranks)*100:.1f}%",
      " 5万-15万:", f"{sum(1 for r in ranks if 50000<r<=150000)/len(ranks)*100:.1f}%",
      " >15万:", f"{sum(1 for r in ranks if r>150000)/len(ranks)*100:.1f}%")

FINE = [(1,5000),(5001,10000),(10001,20000),(20001,30000),(30001,50000),(50001,10**9)]
def band(v):
    for lo,hi in FINE:
        if lo<=v<=hi: return f"{lo:,}–{hi:,}" if hi<10**9 else "50,001–"
    return "?"
print()
print("=== 細かい帯 × ラベル（商品レベル・ラベル済みメーカーの商品） ===")
tab = collections.defaultdict(collections.Counter)
for r in rows:
    lab = labels.get(r['メーカー/ブランド']); rk = num(r['ランク'])
    if not lab or not rk: continue
    tab[band(rk)][lab]+=1
print(f"{'帯':>16} {'n':>5} {'本命率':>8} {'C版元':>7} {'D中国系':>8} {'B大企業':>8}")
for lo,hi in FINE:
    b = f"{lo:,}–{hi:,}" if hi<10**9 else "50,001–"
    c = tab.get(b)
    if not c: continue
    n=sum(c.values()); hon=c['A1']+c['A2']
    print(f"{b:>16} {n:>5} {hon/n*100:>7.1f}% {c['C']/n*100:>6.1f}% {c['D']/n*100:>7.1f}% {c['B']/n*100:>7.1f}%")

# メーカー単位（メーカーのランク中央値）
pm = collections.defaultdict(list)
for r in rows:
    rk=num(r['ランク'])
    if rk: pm[r['メーカー/ブランド']].append(rk)
print()
print("=== 細かい帯 × ラベル（メーカー単位・ランク中央値） ===")
tab = collections.defaultdict(collections.Counter)
for m,lab in labels.items():
    if m in pm: tab[band(statistics.median(pm[m]))][lab]+=1
print(f"{'帯':>16} {'n':>4} {'本命率':>8}")
for lo,hi in FINE:
    b = f"{lo:,}–{hi:,}" if hi<10**9 else "50,001–"
    c=tab.get(b)
    if not c: continue
    n=sum(c.values()); hon=c['A1']+c['A2']
    print(f"{b:>16} {n:>4} {hon/n*100:>7.1f}%")
