# -*- coding: utf-8 -*-
"""(a) ランク帯 × 本命率 の実測 / (b) 大カテゴリ順位 vs サブカテゴリ順位。追加トークン0。"""
import csv, json, glob, gzip, statistics, collections, os, sys
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
V14 = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14"

labels = {x['maker']: x['label'] for x in json.load(open(AO + "/sample200_labeled.json"))}
rows = list(csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")))
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None

# --- 商品レベル：メーカーのラベルを継承 ---
per_maker_ranks = collections.defaultdict(list)
for r in rows:
    m = r['メーカー/ブランド']; rk = num(r['ランク'])
    if rk: per_maker_ranks[m].append(rk)

BANDS = [(1, 50_000), (50_001, 100_000), (100_001, 150_000), (150_001, 300_000), (300_001, 10**9)]
def band(v):
    for lo, hi in BANDS:
        if lo <= v <= hi: return f"{lo:,}–{hi:,}" if hi < 10**9 else f"{lo:,}–"
    return "?"

print("=== (a) ランク帯 × ラベル構成（ラベル済み200社・メーカーのランク中央値で分類） ===")
tab = collections.defaultdict(collections.Counter)
for m, lab in labels.items():
    rks = per_maker_ranks.get(m)
    if not rks: continue
    tab[band(statistics.median(rks))][lab] += 1
order = [f"{lo:,}–{hi:,}" if hi < 10**9 else f"{lo:,}–" for lo, hi in BANDS]
print(f"{'帯':>18} {'n':>4} {'A1':>4} {'A2':>4} {'B':>4} {'C':>4} {'D':>4} {'E':>4} {'本命率':>8}")
tot = collections.Counter()
for b in order:
    c = tab.get(b)
    if not c: continue
    n = sum(c.values()); hon = c['A1'] + c['A2']
    tot.update(c)
    print(f"{b:>18} {n:>4} {c['A1']:>4} {c['A2']:>4} {c['B']:>4} {c['C']:>4} {c['D']:>4} {c['E']:>4} {hon/n*100:>7.1f}%")
n = sum(tot.values()); print(f"{'合計':>18} {n:>4} {tot['A1']:>4} {tot['A2']:>4} {tot['B']:>4} {tot['C']:>4} {tot['D']:>4} {tot['E']:>4} {(tot['A1']+tot['A2'])/n*100:>7.1f}%")

# 商品レベルでも（メーカー単位だと n が小さいため）
print()
print("=== (a-2) 商品レベル（ラベル済みメーカーの商品のみ・商品ごとのランクで分類） ===")
tab2 = collections.defaultdict(collections.Counter)
for r in rows:
    lab = labels.get(r['メーカー/ブランド'])
    rk = num(r['ランク'])
    if not lab or not rk: continue
    tab2[band(rk)][lab] += 1
print(f"{'帯':>18} {'n':>5} {'A1+A2':>6} {'本命率':>8} {'C(版元)':>8} {'D(中国系)':>9} {'B(大企業)':>9}")
for b in order:
    c = tab2.get(b)
    if not c: continue
    n = sum(c.values()); hon = c['A1'] + c['A2']
    print(f"{b:>18} {n:>5} {hon:>6} {hon/n*100:>7.1f}% {c['C']/n*100:>7.1f}% {c['D']/n*100:>8.1f}% {c['B']/n*100:>8.1f}%")

# --- (b) root rank vs subcategory rank ---
print()
print("=== (b) 大カテゴリ順位 vs サブカテゴリ順位（raw_offers 全件） ===")
pairs = []
cat_of = {}
for f in sorted(glob.glob(V14 + "/raw_offers/*.json.gz")):
    d = json.loads(gzip.open(f, 'rt', encoding='utf-8').read())
    for p in d.get('products', []):
        csvv = p.get('csv') or []
        root = None
        if len(csvv) > 3 and csvv[3]:
            root = csvv[3][-1]
        sr = p.get('salesRanks') or {}
        subs = []
        for cid, arr in sr.items():
            if arr and len(arr) >= 2 and arr[-1] and arr[-1] > 0:
                subs.append((int(cid), arr[-1]))
        if root and root > 0 and subs:
            best = min(v for _, v in subs)
            pairs.append((p['asin'], root, best, len(subs)))
            cat_of[p['asin']] = " > ".join([c.get('name','') for c in (p.get('categoryTree') or [])][:2])
print("商品数:", len(pairs))
r_le50 = sum(1 for _, r, s, _ in pairs if r <= 50_000)
s_le50 = sum(1 for _, r, s, _ in pairs if s <= 50_000)
both = sum(1 for _, r, s, _ in pairs if r <= 50_000 and s <= 50_000)
only_sub = sum(1 for _, r, s, _ in pairs if r > 50_000 and s <= 50_000)
print(f"大カテゴリ順位 ≤5万: {r_le50} ({r_le50/len(pairs)*100:.1f}%)")
print(f"サブ最良順位 ≤5万: {s_le50} ({s_le50/len(pairs)*100:.1f}%)")
print(f"大カテゴリ>5万 だがサブ ≤5万: {only_sub} ({only_sub/len(pairs)*100:.1f}%)")
ratios = sorted(r / s for _, r, s, _ in pairs if s > 0)
print("root/sub 比の p25/p50/p75:", [round(ratios[int(len(ratios)*q)],1) for q in (.25,.5,.75)])
nsub = sorted(n for *_, n in pairs)
print("サブカテゴリ数 p50:", nsub[len(nsub)//2])
json.dump({"pairs": pairs[:20]}, open("t42_sample.json","w"), ensure_ascii=False)
