#!/usr/bin/env python3
"""層化抽出したサンプルから、ドロップ数の素の分布と裏取り指標との関係を出す。"""
import json, math, statistics, collections

rows = json.load(open("baseline_sample.json"))
BANDS = ["1-999", "1000-9999", "10000-29999", "30000-99999",
         "100000-499999", "500000-2000000"]
LABEL = {"1-999": "#1千未満", "1000-9999": "#1千-1万", "10000-29999": "#1万-3万",
         "30000-99999": "#3万-10万", "100000-499999": "#10万-50万",
         "500000-2000000": "#50万超"}

def q(v, f):
    v = sorted(v); return v[min(len(v)-1, int(len(v)*f))]

print("== ランク帯別 salesRankDrops30 の素の分布（文房具・オフィス用品 / 各帯50件）==")
print(f"{'帯':10} {'n':>4} {'min':>4} {'p25':>5} {'中央':>5} {'p75':>5} {'p90':>5} {'max':>5} "
      f"{'販売数あり':>8} {'drops>=1':>8}")
for b in BANDS:
    g = [r for r in rows if r["band"] == b]
    d = [r["d30"] for r in g if r["d30"] is not None]
    if not d: continue
    ms = sum(1 for r in g if r.get("monthlySold"))
    ge1 = sum(1 for x in d if x >= 1)
    print(f"{LABEL[b]:10} {len(d):4d} {min(d):4d} {q(d,.25):5d} {int(statistics.median(d)):5d} "
          f"{q(d,.75):5d} {q(d,.9):5d} {max(d):5d} {100*ms/len(g):7.0f}% {100*ge1/len(d):7.0f}%")

print("\n== 窓を月あたりに正規化したときの安定性（=販売ではなくサンプリングの産物かの検定）==")
print("販売を測っているなら 30日/365日 の月率は個体ごとにばらつく（レジームが変わるため）。")
ratios = []
for r in rows:
    if r["d30"] and r["d365"]:
        ratios.append((r["d30"]) / (r["d365"] / 12.0))
print(f"  n={len(ratios)}  中央={statistics.median(ratios):.2f}  "
      f"p10={q(ratios,.1):.2f}  p90={q(ratios,.9):.2f}")
print("  1.0 付近に集中するほど『窓の長さに比例して数が増えるだけ』＝販売の代理になっていない")
near1 = sum(1 for x in ratios if 0.7 <= x <= 1.4)
print(f"  0.7〜1.4 に入る割合: {100*near1/len(ratios):.0f}%")

print("\n== 独立指標 monthlySold（Amazon 公表『過去1か月で〇点購入』）との関係 ==")
pair = [(r["d30"], r["monthlySold"]) for r in rows
        if r["d30"] is not None and r.get("monthlySold")]
print(f"  両方ある件数: {len(pair)} / {len(rows)}")
if len(pair) > 10:
    xs, ys = [p[0] for p in pair], [p[1] for p in pair]
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); o = [0]*len(v)
        for k, i in enumerate(s): o[i] = k
        return o
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    rs = sum((a-mx)*(b-my) for a, b in zip(rx, ry)) / math.sqrt(
        sum((a-mx)**2 for a in rx) * sum((b-my)**2 for b in ry))
    print(f"  順位相関(Spearman) drops30 vs monthlySold: {rs:.3f}")

print("\n== 『死んでいる』群と『生きている』群の対比 ==")
# 生きている根拠: monthlySold が付いている（Amazon 自身が販売実績を出している）
# 死んでいる根拠: 新品オファーが 0〜1 かつ Amazon 本体不在
alive = [r for r in rows if r.get("monthlySold")]
dead = [r for r in rows if not r.get("monthlySold")
        and (r.get("countNew") in (None, -1) or (r.get("countNew") or 0) <= 1)]
for name, g in (("生きている(販売数公表あり)", alive), ("死んでいる疑い(販売数なし・オファー0〜1)", dead)):
    d = [r["d30"] for r in g if r["d30"] is not None]
    if not d: continue
    print(f"  {name:38} n={len(d):3d} 中央={int(statistics.median(d)):3d} "
          f"p25={q(d,.25):3d} p75={q(d,.75):3d} drops>=1: {100*sum(1 for x in d if x>=1)/len(d):.0f}%")

print("\n== 現行 S5（drops30 >= 1）の弁別力 ==")
tp = sum(1 for r in alive if (r["d30"] or 0) >= 1)
fp = sum(1 for r in dead if (r["d30"] or 0) >= 1)
print(f"  生きている群の通過率: {100*tp/max(1,len(alive)):.0f}%（取りこぼしは少ない）")
print(f"  死んでいる疑い群の通過率: {100*fp/max(1,len(dead)):.0f}%（＝素通しの割合）")

print("\n== 閾値を上げたら弁別できるようになるか ==")
print(f"{'閾値':>6} {'生き通過':>8} {'死に通過':>8} {'差':>6}")
for t in (1, 3, 5, 10, 15, 20, 25, 30, 40):
    a = 100*sum(1 for r in alive if (r["d30"] or 0) >= t)/max(1, len(alive))
    b = 100*sum(1 for r in dead if (r["d30"] or 0) >= t)/max(1, len(dead))
    print(f"{t:6d} {a:7.0f}% {b:7.0f}% {a-b:5.0f}pt")
