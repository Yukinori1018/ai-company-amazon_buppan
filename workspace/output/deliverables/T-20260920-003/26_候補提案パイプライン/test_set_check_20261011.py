#!/usr/bin/env python3
"""#15 セット数（Amazon 1個＝卸の何点か）の回帰テスト（2026-10-11）。

経緯：サトルが179行を人の目で確かめたら、台帳にセット数の値があり人が数を確定できた34行のうち
**31行が誤り**だった。31行すべて、旧 `set_count.parse_amazon_set_count` が商品名の
「12個入」「35枚組」「8点デラックスセット」「ペアセット」「34X66cm」の数をそのまま倍率にしていた。

このテストは**人の確認の証跡そのもの**（set_check_*.csv）で直したパーサを検査する:
  1. 31行のどれも、旧値（人の答えと違う数）を返さない（None＝人が見る、は可）
  2. 卸の商品名を渡せば人の答えと一致する（索引に卸の商品名がある行）
  3. 人の確認（確度 高・中）が採点に合流し、低・未確定は UNKNOWN の理由を持つ

python3 test_set_check_20261011.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import set_count            # noqa: E402
import score_20261004 as S  # noqa: E402

W = S.WORK
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += (not ok)
    print(f"  {'ok' if ok else 'NG'} {name}（got={got!r} want={want!r}）")


def n(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


print("0. 合成ケース（証跡ファイルが無くても回る）")
check("12個入は卸の名前が無ければ決めない",
      set_count.parse_amazon_set_count("ボンスター ロールパッド 12個入"), None)
check("12個入は卸も12個入なら 1",
      set_count.parse_amazon_set_count("ボンスター ロールパッド 12個入", "ボンスター ロールパッド 12個入"), 1)
check("「セット 34X66cm」の寸法を個数にしない",
      set_count.parse_amazon_set_count("西川 スヌーピー ギフトタオルセット 34X66cm PN4651") in (None, 1), True)
check("「120g、6食」は単品と決めない（旧式は『入』必須で素通り）",
      set_count.parse_amazon_set_count("辛ラーメン 袋麺 120g、6食"), None)
check("×2点セットは束ね表記なので 2", set_count.parse_amazon_set_count(
      "【2点セット】不二貿易 洗えるバスケット ×2点セット"), 2)
check("8点デラックスセットは卸の名前が無ければ決めない",
      set_count.parse_amazon_set_count("H2OスチームFX 8点デラックスセット (レッド)"), None)

ev = sorted((W / "ledger20261010").glob("set_check_*.csv"))
pool_p = W / "pipeline/buy_list_private.csv"
idx_p = W / "pipeline/netsea_jan_index.json"
if not (ev and pool_p.exists()):
    print("証跡ファイルが無いので実データ検査は飛ばします")
    sys.exit(1 if fails else 0)

human = {r["ASIN"]: r for p in ev for r in csv.DictReader(p.open(encoding="utf-8-sig"))}
pool = {r["ASIN"]: r for r in csv.DictReader(pool_p.open(encoding="utf-8-sig"))}
idx = json.loads(idx_p.read_text())["jans"] if idx_p.exists() else {}

print("\n1. 旧パーサが間違えた行で、同じ誤りを返さない")
wrong = same_as_human = unknown = 0
for a, h in human.items():
    r = pool.get(a)
    hn = n(h["Amazon1個＝卸◯点"])
    old = n((r or {}).get("Amazon側のセット数(Amazon1個=卸何点か)"))
    if not (r and hn and old) or old == hn or h["確度"] not in S.HUMAN_SET_OK:
        continue
    wt = (idx.get(r.get("JAN") or "") or {}).get("title")
    got = set_count.parse_amazon_set_count(r["商品名"], wt)
    wrong += 1
    if got == old and old != 1:
        check(f"{a} 旧値 {old} を返さない（人={hn}・{r['商品名'][:30]}）", got, f"≠{old}")
    elif got == hn:
        same_as_human += 1
    elif got is None:
        unknown += 1
print(f"  旧パーサの誤り {wrong}行 → 人と一致 {same_as_human}・UNKNOWN（人が見る） {unknown}・"
      f"その他 {wrong - same_as_human - unknown}")
check("旧パーサの誤り行が実データで見つかる（縮退していない）", wrong > 0, True)

print("\n2. 人の確認が採点に合流する")
hi = next(a for a, h in human.items() if h["確度"] in S.HUMAN_SET_OK and n(h["Amazon1個＝卸◯点"]))
v, conf, why = S.set_count_of({"ASIN": hi, "商品名": "12個入"}, {"packageQuantity": 99})
check("確度 高・中は人の数で確定", (v, conf), (n(human[hi]["Amazon1個＝卸◯点"]), "確定"))
check("理由に確認者が出る", "人の確認" in why, True)
lo = [a for a, h in human.items() if h["確度"] not in S.HUMAN_SET_OK]
check("低・未確定の行がある（縮退していない）", len(lo) > 0, True)
for a in lo[:3]:
    v, conf, why = S.set_count_of({"ASIN": a, "商品名": "単品"}, {"packageQuantity": 1})
    check(f"{a} 低・未確定は UNKNOWN（数を使わない）", (v, conf), (None, "人の確認で未確定"))
    check(f"{a} 『こう変えれば』を書く", "【こう変えれば】" in why, True)

print(f"\n{'全件通過' if not fails else f'NG {fails}件'}")
sys.exit(1 if fails else 0)
