# -*- coding: utf-8 -*-
"""③ 非Amazon起点：「類似商品」から需要をどこまで言えるかを実測する。

被説明変数 = Keepa の 月間販売数（monthlySold＝Amazon表示の実測。階級値）
「類似」の定義を4段階に変え、分散のどれだけを説明できるかを測る。
"""
import csv, json, math, statistics as st, collections, re, os
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
DL = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables"
HERE = os.path.dirname(os.path.abspath(__file__))
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None

rows = []
for r in csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")):
    ms = num(r['月間販売数']); pr = num(r['Amazon価格']); rk = num(r['ランク'])
    of = num(r['新品オファー数'])
    if not ms or ms <= 0 or not pr or pr <= 0: continue
    cat = r['カテゴリ'].split(' > ')
    rows.append(dict(asin=r['ASIN'], y=math.log10(ms), ms=ms, price=pr, rank=rk, offers=of,
                     c1=cat[0], c2=' > '.join(cat[:2]), c3=' > '.join(cat[:3]),
                     title=r['商品名']))
print("解析対象（月間販売数が取れた商品）:", len(rows))

def pband(p):
    return int(math.floor(math.log(p, 1.6)))       # 1.6倍刻みの価格帯

def r2(groups, ys):
    """群ごとの平均で説明できる割合"""
    mu = st.mean(ys); sst = sum((y - mu) ** 2 for y in ys)
    ssw = 0.0
    for g, vs in groups.items():
        if not vs: continue
        m = st.mean(vs); ssw += sum((v - m) ** 2 for v in vs)
    return 1 - ssw / sst if sst else 0

ys = [r['y'] for r in rows]
defs = {
    "① 大カテゴリのみ":        lambda r: r['c1'],
    "② 中カテゴリ":            lambda r: r['c2'],
    "③ 小カテゴリ":            lambda r: r['c3'],
    "④ 中カテゴリ × 価格帯":    lambda r: (r['c2'], pband(r['price'])),
    "⑤ 小カテゴリ × 価格帯":    lambda r: (r['c3'], pband(r['price'])),
}
print("\n=== 「類似」の定義ごとに、月間販売数（対数）の分散をどれだけ説明できるか ===")
print(f"{'定義':<24}{'群数':>6}{'説明率R2':>10}{'群あたり中央n':>12}")
for name, f in defs.items():
    g = collections.defaultdict(list)
    for r in rows: g[f(r)].append(r['y'])
    ns = sorted(len(v) for v in g.values())
    print(f"{name:<24}{len(g):>6}{r2(g, ys)*100:>9.1f}%{ns[len(ns)//2]:>12}")

# 参考: ランクを使えたらどれだけ説明できるか（＝Amazonに既にある商品の場合）
xs = [(math.log10(r['rank']), r['y']) for r in rows if r['rank'] and r['rank'] > 0]
mx = st.mean([a for a, _ in xs]); my = st.mean([b for _, b in xs])
sxx = sum((a - mx) ** 2 for a, _ in xs); sxy = sum((a - mx) * (b - my) for a, b in xs)
b = sxy / sxx; a0 = my - b * mx
ss = sum((y - (a0 + b * x)) ** 2 for x, y in xs); sst = sum((y - my) ** 2 for _, y in xs)
print(f"\n[参考] ランク(対数)による回帰: R2={1-ss/sst:.3f}  log10(月販) = {a0:.3f} {b:+.3f}*log10(rank)")
print(f"        → ランク1万位のとき 月販 {10**(a0+b*4):.0f}個 / 5万位 {10**(a0+b*math.log10(50000)):.0f}個 / 15万位 {10**(a0+b*math.log10(150000)):.0f}個")

# ---- コホートの実用形：中カテゴリ×価格帯 の分位点 ----
g = collections.defaultdict(list)
for r in rows: g[(r['c2'], pband(r['price']))].append(r)
big = {k: v for k, v in g.items() if len(v) >= 20}
print(f"\n=== 実用コホート（中カテゴリ×価格帯・n≧20）: {len(big)}群 / 対象商品 {sum(len(v) for v in big.values())}件 ===")
spreads = []
for k, v in big.items():
    ms = sorted(x['ms'] for x in v)
    p20, p50, p80 = ms[int(len(ms)*.2)], ms[len(ms)//2], ms[int(len(ms)*.8)]
    spreads.append(p80 / max(p20, 1))
spreads.sort()
print(f"  コホート内の p80/p20 倍率: 中央 {spreads[len(spreads)//2]:.1f}倍 / 最小 {spreads[0]:.1f}倍 / 最大 {spreads[-1]:.1f}倍")

print("\n=== 主要コホートの実測（上位15群） ===")
print(f"{'カテゴリ':<38}{'価格帯':>16}{'n':>5}{'p20':>6}{'中央':>6}{'p80':>6}{'出品者中央':>10}{'1社あたり':>9}")
for k, v in sorted(big.items(), key=lambda x: -len(x[1]))[:15]:
    ms = sorted(x['ms'] for x in v)
    p20, p50, p80 = ms[int(len(ms)*.2)], ms[len(ms)//2], ms[int(len(ms)*.8)]
    of = sorted(x['offers'] for x in v if x['offers'])
    ofm = of[len(of)//2] if of else 0
    lo = 1.6 ** k[1]; hi = 1.6 ** (k[1]+1)
    print(f"{k[0][:36]:<38}{f'{int(lo):,}-{int(hi):,}円':>16}{len(v):>5}{p20:>6.0f}{p50:>6.0f}{p80:>6.0f}{ofm:>10.0f}{p50/(ofm+1):>9.1f}")

json.dump({str(k): dict(n=len(v), p20=sorted(x['ms'] for x in v)[int(len(v)*.2)],
                        p50=sorted(x['ms'] for x in v)[len(v)//2],
                        p80=sorted(x['ms'] for x in v)[int(len(v)*.8)])
           for k, v in big.items()}, open(HERE + "/t48_cohorts.json", "w"), ensure_ascii=False)
