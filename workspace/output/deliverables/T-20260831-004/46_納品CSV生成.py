# -*- coding: utf-8 -*-
"""納品用CSVと、レポートに貼る表を生成する。"""
import json, csv, collections, math, os
HERE = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260831-004/t40"
DL = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260831-004"
out = json.load(open(HERE + "/t47_262.json"))
def q(o):
    v = o.get('期待月利_合計'); return v if isinstance(v, int) else 0
有 = [o for o in out if o.get('困り度') is not None]
def quad(o):
    d = o['困り度'] >= 45; p = q(o) >= 10000
    return ('Q1 最優先（困っている×儲かる）' if d and p else
            'Q2 提案は刺さるが薄い' if d else
            'Q3 普通に仕入れる（独占提案は早い）' if p else
            'Q4 後回し')
cnt = collections.Counter(quad(o) for o in 有)
print("=== 2軸の象限（262社） ===")
for k in sorted(cnt): print(f"  {k:<32}{cnt[k]:>4}社")

COLS = ["優先順位","象限","メーカー","困り度","提案タイプ","値崩れ幅_最大","直近下落_最大","オファー増_最大",
        "値崩れSKU数","相乗り増SKU数","対象SKU数","期待月利_合計","期待月利_最大","メーカー直販",
        "直接交渉の目安","規模区分","従業員数","法人番号","gBiz商号","所在地","企業URL",
        "国内独立セラー数","独立セラー数","主なカテゴリ","証拠SKU","証拠","代表ASIN","代表Amazonページ","メーカー検索"]
def key(o):
    return (0 if quad(o).startswith('Q1') else 1 if quad(o).startswith('Q2') else 2 if quad(o).startswith('Q3') else 3,
            -(o['困り度'] * math.log10(q(o) + 10)))
srt = sorted(有, key=key) + [o for o in out if o.get('困り度') is None]
path = DL + "/43_連絡候補_困り度2軸つき.csv"
with open(path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore'); w.writeheader()
    for i, o in enumerate(srt, 1):
        r = dict(o); r['優先順位'] = i; r['象限'] = quad(o) if o.get('困り度') is not None else ''
        w.writerow(r)
print("wrote", path)

print("\n=== Q1 最優先レーン（全件） ===")
q1 = [o for o in srt if o.get('困り度') is not None and quad(o).startswith('Q1')]
print("| # | メーカー | 困り度 | 値崩れ幅 | オファー増 | 期待月利 | 規模 | 証拠（代表SKU） |")
print("|---|---|---:|---:|---:|---:|---|---|")
for i, o in enumerate(q1, 1):
    print(f"| {i} | {o['メーカー']} | {o['困り度']:.0f} | {o['値崩れ幅_最大']:.0f}% | +{o['オファー増_最大']} | {q(o):,}円 | {(o.get('規模区分') or '不明')} | {o['証拠']} |")
print("\n=== Q2（困っているが薄い）上位10 ===")
q2 = [o for o in srt if o.get('困り度') is not None and quad(o).startswith('Q2')][:10]
for o in q2: print(f"  {o['メーカー']:<24}困り度{o['困り度']:.0f} 値崩れ{o['値崩れ幅_最大']:.0f}% 期待月利{q(o):,}円")
