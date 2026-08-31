# -*- coding: utf-8 -*-
"""困り度スコア v2（下方向に限定）＋ ラベル別の検証 ＋ 交絡の確認。"""
import csv, json, statistics as st, collections, os, sys, math
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
DL = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260831-004"
HERE = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(HERE + "/t41_asin_features.json")); feats = F['feats']
rows = list(csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")))
asin2row = {r['ASIN']: r for r in rows}
labels = {x['maker']: x['label'] for x in json.load(open(AO + "/sample200_labeled.json"))}
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None

CAPS = dict(down=0.30, chg=40, drop=0.20, dcnt=3.0)
def nz(x, cap):
    return None if x is None else max(0.0, min(1.0, x / cap))

prod = {}
for a, f in feats.items():
    if (f['hist_days'] or 0) < 120: continue
    p50, p10 = f['p50_180'], f['p10_180']
    down = ((p50 - p10) / p50) if (p50 and p50 > 0 and p10 is not None) else None   # 下方向の値幅
    d1 = nz(down, CAPS['down'])
    d2 = nz(f['n_change_180'], CAPS['chg'])
    d3 = nz(max(0.0, f['drop_30v180']) if f['drop_30v180'] is not None else None, CAPS['drop'])
    d4 = nz(max(0.0, f['d_count_new']) if f['d_count_new'] is not None else None, CAPS['dcnt'])
    c = [x for x in (d1, d2, d3, d4) if x is not None]
    if len(c) < 3: continue
    prod[a] = dict(f, D1=d1, D2=d2, D3=d3, D4=d4, down=down, distress=100*sum(c)/len(c))

# ---- 検証1: ラベル別の困り度（中国系OEMに偏っていないか） ----
by = collections.defaultdict(list)
for a, p in prod.items():
    r = asin2row.get(a)
    if not r: continue
    lab = labels.get(r['メーカー/ブランド'])
    if lab: by[lab].append(p['distress'])
print("=== 検証1: ラベル別の困り度（商品単位・ラベル済みメーカーの商品のみ） ===")
print(f"{'区分':<26}{'n':>5}{'中央値':>8}{'≥45の割合':>10}")
NAME = {'A1':'A1 日本の小規模メーカー','A2':'A2 日本の中堅','B':'B 大企業','C':'C 版元/レーベル','D':'D 中国系OEM','E':'E 海外(非中国)','F':'F その他'}
for k in ('A1','A2','B','C','D','E'):
    v = by.get(k) or []
    if not v: continue
    print(f"{NAME[k]:<26}{len(v):>5}{st.median(v):>8.1f}{sum(1 for x in v if x>=45)/len(v)*100:>9.1f}%")

# ---- 検証2: 交絡（困り度は単に「オファーが多い商品」を拾っていないか） ----
xs = [(p['count_new_now'] or 0, p['distress']) for p in prod.values() if p['count_new_now'] is not None]
def corr(pairs):
    x=[a for a,_ in pairs]; y=[b for _,b in pairs]
    mx,my=st.mean(x),st.mean(y)
    sx=math.sqrt(sum((a-mx)**2 for a in x)); sy=math.sqrt(sum((b-my)**2 for b in y))
    return sum((a-mx)*(b-my) for a,b in pairs)/(sx*sy) if sx and sy else 0
print("\n=== 検証2: 交絡チェック（相関係数） ===")
print(f"  困り度 × 現在のオファー数 : r={corr(xs):+.3f}")
ys = [(p['rank30'] or 0, p['distress']) for p in prod.values() if p['rank30']]
print(f"  困り度 × ランク          : r={corr(ys):+.3f}")
zs = [(p['price_now'] or 0, p['distress']) for p in prod.values() if p['price_now']]
print(f"  困り度 × 価格            : r={corr(zs):+.3f}")
ws = [(p['hist_days'] or 0, p['distress']) for p in prod.values() if p['hist_days']]
print(f"  困り度 × 履歴の長さ       : r={corr(ws):+.3f}")

# ---- 成分どうしの独立性 ----
print("\n=== 成分間の相関（重複していないか） ===")
for a1,a2 in (('D1','D2'),('D1','D3'),('D1','D4'),('D2','D4'),('D3','D4')):
    pr=[(p[a1],p[a2]) for p in prod.values() if p[a1] is not None and p[a2] is not None]
    print(f"  {a1}×{a2}: r={corr(pr):+.3f}  (n={len(pr)})")

json.dump({a: dict(distress=p['distress'], D1=p['D1'], D2=p['D2'], D3=p['D3'], D4=p['D4'],
                   down=p['down'], p50=p['p50_180'], pnow=p['price_now'],
                   cnow=p['count_new_now'], dcnt=p['d_count_new'], chg=p['n_change_180'],
                   drop=p['drop_30v180'], amz=p['amz_instock_180'], rank30=p['rank30'],
                   title=p['title'])
           for a, p in prod.items()}, open(HERE + "/t45_prod_v2.json", "w"), ensure_ascii=False)
print("\n商品:", len(prod), file=sys.stderr)
