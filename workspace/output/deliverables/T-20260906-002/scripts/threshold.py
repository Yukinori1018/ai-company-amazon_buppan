#!/usr/bin/env python3
"""足切り閾値 X を決める。

正解ラベル: Amazon 公表の月間販売数（monthlySold）。
  SOLD  = 値がある（Amazon が「過去1か月で〇点購入」を出している）
  以下では「値がない」を DEAD とは呼ばない。**被覆率がランク依存で落ちる**ため、
  値がないことは「売れていない」の証拠にならない（前回の調査で確認済み）。
  よって足切りの評価は「取りこぼし率（SOLD を何%落とすか）」を主に見る。
"""
import json, statistics
rows = json.load(open("labeled_sample.json"))
D = [r for r in rows if r["d30"] is not None]

print(f"標本 {len(D)} 件（文房具・オフィス用品・ランク帯で層化・ドロップ数では絞っていない）")
sold = [r for r in D if r.get("monthlySold")]
print(f"うち Amazon が販売数を公表 = {len(sold)} 件\n")

print("== ドロップ数の値ごとの『実際に売れている確率』 ==")
buckets = [(0, 0), (1, 2), (3, 5), (6, 9), (10, 13), (14, 15), (16, 19), (20, 99)]
print(f"{'drops30':>10} {'n':>5} {'売れている率':>12} {'販売数の中央値':>14}")
for lo, hi in buckets:
    g = [r for r in D if lo <= r["d30"] <= hi]
    if not g: continue
    s = [r["monthlySold"] for r in g if r.get("monthlySold")]
    med = int(statistics.median(s)) if s else 0
    print(f"{f'{lo}-{hi}':>10} {len(g):5d} {100*len(s)/len(g):11.0f}% {med:14d}")

print("\n== 足切り X ごとの成績 ==")
print(f"{'X':>4} {'通過数':>7} {'SOLDの取りこぼし':>16} {'通過分の売れている率':>20}")
for x in range(0, 21):
    p = [r for r in D if r["d30"] >= x]
    lost = [r for r in sold if r["d30"] < x]
    s = [r for r in p if r.get("monthlySold")]
    print(f"{x:4d} {len(p):7d} {100*len(lost)/max(1,len(sold)):15.0f}% "
          f"{100*len(s)/max(1,len(p)):19.0f}%")

print("\n== 飽和仮説の検証: 14〜15 は『1日1回観測』の飽和値か ==")
have = [r for r in D if r["n30"] and r["n30"] > 3]
print(f"{'観測回数(30日)':>14} {'n':>5} {'drops30 中央値':>15} {'充填率 中央値':>14} {'売れている率':>12}")
for lo, hi, lab in [(4, 15, "4-15回(数日に1回)"), (16, 25, "16-25回"),
                    (26, 34, "26-34回(≒1日1回)"), (35, 45, "35-45回"),
                    (46, 999, "46回以上(1日2回以上)")]:
    g = [r for r in have if lo <= r["n30"] <= hi]
    if not g: continue
    d = [r["d30"] for r in g]
    f = [r["d30"] / (r["n30"] - 1) for r in g]
    s = sum(1 for r in g if r.get("monthlySold"))
    print(f"{lab:>14} {len(g):5d} {int(statistics.median(d)):15d} "
          f"{statistics.median(f):14.2f} {100*s/len(g):11.0f}%")

print("\n  → 『1日1回観測』の群のドロップ数の中央値が 14-15 付近なら、社長の仮説どおり")
print("     その値は情報ゼロのゾーン（観測頻度だけで決まる値）ということになる。")

print("\n== 充填率を条件に使えるか（観測回数で正規化した指標） ==")
print(f"{'充填率':>12} {'n':>5} {'売れている率':>12}")
for lo, hi in [(0, 0.001), (0.001, 0.2), (0.2, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 2)]:
    g = [r for r in have if lo <= r["d30"] / (r["n30"] - 1) < hi]
    if not g: continue
    s = sum(1 for r in g if r.get("monthlySold"))
    print(f"{f'{lo}-{hi}':>12} {len(g):5d} {100*s/len(g):11.0f}%")

print("\n== 閾値は価格帯に依存するか ==")
print(f"{'価格帯':>14} {'n':>5} {'SOLD群のdrops30 中央値':>24} {'非SOLD群':>10}")
for lo, hi, lab in [(0, 1000, "〜1,000円"), (1000, 3000, "1,000-3,000"),
                    (3000, 10000, "3,000-10,000"), (10000, 10**9, "10,000円〜")]:
    g = [r for r in D if r["price_new"] and lo <= r["price_new"] / 100 < hi]
    if len(g) < 10: continue
    a = [r["d30"] for r in g if r.get("monthlySold")]
    b = [r["d30"] for r in g if not r.get("monthlySold")]
    print(f"{lab:>14} {len(g):5d} {int(statistics.median(a)) if a else -1:24d} "
          f"{int(statistics.median(b)) if b else -1:10d}")

print("\n== 閾値はランク帯に依存するか ==")
print(f"{'ランク帯':>16} {'n':>5} {'SOLD群のdrops30 中央値':>24} {'非SOLD群':>10}")
for b in ["1-999", "1000-9999", "10000-29999", "30000-99999",
          "100000-499999", "500000-2000000"]:
    g = [r for r in D if r["band"] == b]
    a = [r["d30"] for r in g if r.get("monthlySold")]
    c = [r["d30"] for r in g if not r.get("monthlySold")]
    print(f"{b:>16} {len(g):5d} {int(statistics.median(a)) if a else -1:24d} "
          f"{int(statistics.median(c)) if c else -1:10d}")
