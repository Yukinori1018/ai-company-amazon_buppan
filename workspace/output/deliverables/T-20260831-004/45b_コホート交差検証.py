# -*- coding: utf-8 -*-
"""③ 交差検証つき：類似の定義ごとに「新しい1件」をどれだけ当てられるか（LOO）。
併せてキーワード一致が効くかを検定する。"""
import csv, math, statistics as st, collections, re, os
AO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004"
def num(s):
    try: return float(str(s).replace(',', ''))
    except: return None
rows = []
for r in csv.DictReader(open(AO + "/snapshot_02.csv", encoding="utf-8-sig")):
    ms = num(r['月間販売数']); pr = num(r['Amazon価格'])
    if not ms or ms <= 0 or not pr or pr <= 0: continue
    cat = r['カテゴリ'].split(' > ')
    rows.append(dict(y=math.log10(ms), ms=ms, price=pr, c1=cat[0], c2=' > '.join(cat[:2]),
                     c3=' > '.join(cat[:3]), title=r['商品名'], offers=num(r['新品オファー数'])))
ys = [r['y'] for r in rows]; mu = st.mean(ys)
sst = sum((y - mu) ** 2 for y in ys)
def pband(p): return int(math.floor(math.log(p, 1.6)))

def loo_r2(keyf, minn):
    """自分自身を除いた同群の中央値で予測する（過学習を排した説明力）"""
    g = collections.defaultdict(list)
    for i, r in enumerate(rows): g[keyf(r)].append(i)
    ss = 0.0; n = 0; fallback = 0
    for i, r in enumerate(rows):
        idx = [j for j in g[keyf(r)] if j != i]
        if len(idx) < minn:
            fallback += 1
            pred = mu                      # 群が小さいときは全体の平均に退避
        else:
            pred = st.median(rows[j]['y'] for j in idx)
        ss += (r['y'] - pred) ** 2; n += 1
    return 1 - ss / sst, fallback

print("=== 交差検証（Leave-One-Out）：新しい1件をどれだけ当てられるか ===")
print(f"{'「類似」の定義':<28}{'説明力R2(LOO)':>14}{'群が小さく退避':>14}")
for name, f, mn in [
    ("① 大カテゴリのみ", lambda r: r['c1'], 3),
    ("② 中カテゴリ", lambda r: r['c2'], 3),
    ("③ 小カテゴリ", lambda r: r['c3'], 3),
    ("④ 中カテゴリ × 価格帯", lambda r: (r['c2'], pband(r['price'])), 3),
    ("⑤ 小カテゴリ × 価格帯", lambda r: (r['c3'], pband(r['price'])), 3),
    ("⑥ 中カテゴリ × 価格帯 (n≧10)", lambda r: (r['c2'], pband(r['price'])), 10),
]:
    r2, fb = loo_r2(f, mn)
    print(f"{name:<28}{r2*100:>13.1f}%{fb:>13}件")

# キーワード一致が効くか（同じ中カテゴリ内で、タイトル語の重なりと販売数の近さ）
SEP = re.compile("[（）()【】\\[\\]、。,.\\-_/×\"\u2018\u2019\u201c\u201d ]+")
def toks(t):
    return {w for w in SEP.split(t or "") if len(w) >= 2}
import random
random.seed(0)
by2 = collections.defaultdict(list)
for r in rows: by2[r['c2']].append(r)
hi, lo = [], []
for c, v in by2.items():
    if len(v) < 8: continue
    for _ in range(min(400, len(v) * 4)):
        a, b = random.sample(v, 2)
        ta, tb = toks(a['title']), toks(b['title'])
        if not ta or not tb: continue
        j = len(ta & tb) / len(ta | tb)
        d = abs(a['y'] - b['y'])
        (hi if j >= 0.15 else lo).append(d)
print(f"\n=== キーワード一致は効くか（同じ中カテゴリ内のペア比較） ===")
print(f"  タイトル語の重なり15%以上のペア : n={len(hi):>5}  月販の差(対数)の中央値 {st.median(hi):.3f}  → 実数で {10**st.median(hi):.2f}倍")
print(f"  15%未満のペア                  : n={len(lo):>5}  月販の差(対数)の中央値 {st.median(lo):.3f}  → 実数で {10**st.median(lo):.2f}倍")

# コホート中央値から「1社あたり月販」を出したときの誤差
print("\n=== 実務形の誤差（コホート中央値 ÷ (出品者数+1) で予測した場合） ===")
g = collections.defaultdict(list)
for r in rows: g[(r['c2'], pband(r['price']))].append(r)
errs = []
for k, v in g.items():
    if len(v) < 10: continue
    for r in v:
        others = [x['ms'] for x in v if x is not r]
        pred = st.median(others) / ((r['offers'] or 2) + 1)
        act = r['ms'] / ((r['offers'] or 2) + 1)
        if pred > 0 and act > 0: errs.append(math.log10(act / pred))
errs.sort()
print(f"  n={len(errs)}  予測比の p10/p50/p90 = "
      f"{10**errs[int(len(errs)*.1)]:.2f}倍 / {10**errs[len(errs)//2]:.2f}倍 / {10**errs[int(len(errs)*.9)]:.2f}倍")
print(f"  → 予測の 80% 区間はおよそ {10**errs[int(len(errs)*.1)]:.1f}〜{10**errs[int(len(errs)*.9)]:.1f} 倍の幅")
