#!/usr/bin/env python3
"""単位ずれを二度と出さないためのテスト（2026-10-01 カズヨ依頼）。

    python3 test_units.py

守る不変条件は4つです。**どれも実際に破った**ので、文章ではなくテストで固定します。

1. 「Amazon の1個 ＝ 卸の何点か」が読めないときは **1 と決め打たない**
2. `発注額 ＝ Amazon1個あたり原価 × 発注点数`（原価と点数の**単位が揃っている**）
3. 卸率15%未満 / 利益率50%超は **UNKNOWN**（単位ずれの番兵）
4. 1 SKU の発注額が **8万円**を超えたら NO-GO（残枠を超える案は出さない）
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import candidate_pipeline as CP            # noqa: E402
import profit                              # noqa: E402
import set_count                           # noqa: E402
from verdict import FAIL, PASS, UNKNOWN    # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  NG {name}: {got!r} ≠ {want!r}")
    else:
        print(f"  ok {name}")


# ── 1. セット数が読めないときは 1 と決め打たない ──────────────────────────

print("1. set_count — 読めないものは None（UNKNOWN）")

# 🔴 2026-10-01 の事故そのもの。卸268円/点 × 18 = 4,824円が正しい原価なのに、
#    単品（倍率1）と読んで「利益率75.5%・手残り +3,706円」と報告した（実際は ▲778円/個）。
check("カップ麺 18食入り は読めない",
      set_count.parse_amazon_set_count(
          "【paldo】王の蓋 ワントゥッコン カップ麺 110g、18食入り 並行輸入品"), None)
check("バスタオル2P は読めない",
      set_count.parse_amazon_set_count("いいタオル・ふっくらふわふわ バスタオル2P PIG-81100"),
      None)

# 「N〈単位〉入り」でも、数が大きければ内容量（卸1点の中身）。ここは 1 で正しい。
check("青汁 90包入り は内容量＝単品",
      set_count.parse_amazon_set_count("青汁 90包入り 国産"), 1)
check("600粒 は内容量＝単品",
      set_count.parse_amazon_set_count("オリヒロ 玉葱エキス粒 徳用 約60日分 600粒"), 1)

# 読めるものは読む（過剰に UNKNOWN へ倒して母数を削らない）。
check("2点セットは 2", set_count.parse_amazon_set_count("ステンレスボトル 500ml ×2点セット"), 2)
check("4袋入は 4", set_count.parse_amazon_set_count("ウルフピー 4袋入"), 4)
check("ヘッドセットは単品", set_count.parse_amazon_set_count("エレコム ゲーミングヘッドセット"), 1)
check("寸法を拾わない",
      set_count.parse_amazon_set_count("キャビネット 幅100×奥行32×高さ70cm"), 1)
check("蛍光灯の型番を拾わない",
      set_count.parse_amazon_set_count("DNライティング エースライン FLR72T6EX-WW"), 1)


# ── 2. 発注額 ＝ Amazon1個あたり原価 × 発注点数 ───────────────────────────

print("\n2. 単位の整合 — 発注額 ＝ Amazon1個あたり原価 × 発注点数")

# 卸268円/点・Amazon 1個 = 卸18点 → Amazon 1個の原価は 4,824円。
wholesale, mult = 268, 18
unit = wholesale * mult
pack_in_amazon_units = set_count.order_lot_in_amazon_units(18, mult)   # 卸18点 → Amazon 1個
qty = profit.order_qty(5, pack_in_amazon_units)                        # 月販5個
e = profit.compute(5180, 8.0, 472, unit, qty, monthly_sold=5)
check("原価は卸の1点ではなく Amazon の1個ぶん", e.unit_cost_incl, 4824)
check("発注額＝原価×点数", e.order_total, e.unit_cost_incl * e.qty)
check("この行は赤字（カズヨの実画面計算と符号が一致）", e.net_per_unit < 0, True)

# 単位が揃っていない組み合わせは、式の上で必ず矛盾する。
bad = profit.compute(5180, 8.0, 472, wholesale, 18, monthly_sold=5)     # 卸1点の原価 × 18
check("単位がずれた組み合わせは発注額が1/18になる", bad.order_total, 268 * 18)
check("  → そのとき卸率が異常に小さくなる（番兵が効く値）", bad.cost_ratio_pct < 15.0, True)


# ── 3. 番兵 — 卸率15%未満 / 利益率50%超は UNKNOWN ────────────────────────

print("\n3. 番兵 — ありえない数字は UNKNOWN に落とす")

check("卸率5.2%は UNKNOWN", CP.economics_status(bad, 5)[0], UNKNOWN)
check("  理由に『単位』が出る", "単位" in CP.economics_status(bad, 5)[1], True)

high = profit.compute(10000, 10.0, 400, 1000, 10, monthly_sold=50)     # 卸率10%
check("卸率10%は UNKNOWN", CP.economics_status(high, 50)[0], UNKNOWN)

# まともな行は通す（番兵が母数を削らないこと）。
# 卸率45%・利益率30%・手残り1,347円（誤差幅 550円を十分に超える）。
ok = profit.compute(5000, 15.0, 430, 2250, 10, monthly_sold=60)
check("卸率45%・利益率30%は PASS", CP.economics_status(ok, 60)[0], PASS)
check("  手残りが誤差幅を超えている", ok.net_per_unit > int(ok.sell * 0.07) + 200, True)
# 番兵の境界。利益率50.0%ちょうどは通す（超えたら落とす）。
edge = profit.compute(5000, 15.0, 430, 1245, 10, monthly_sold=60)
check("  境界: 利益率50.0%ちょうど", edge.margin_pct, 50.0)
check("  境界は UNKNOWN でない", CP.economics_status(edge, 60)[0] != UNKNOWN, True)
over = profit.compute(5000, 15.0, 430, 1200, 10, monthly_sold=60)
check("  50%超は UNKNOWN", CP.economics_status(over, 60)[0], UNKNOWN)

# 2つの番兵は独立ではない。**卸率が低ければ利益率は必ず高くなる**（同じ式の裏表）。
# 両方置いているのは、どちらの側から見ても気づけるようにするため。
low_ratio = profit.compute(5000, 15.0, 430, 750, 10, monthly_sold=60)
check("卸率15%の行は利益率でも引っかかる", low_ratio.margin_pct > 50.0, True)


# ── 4. 予算のゲート ──────────────────────────────────────────────────────

print("\n4. 予算 — 1 SKU の発注額が8万円を超えたら NO-GO")

big = profit.compute(30428, 15.0, 3573, 19350, 10, monthly_sold=60)    # 発注額 193,500円
check("発注額193,500円は FAIL", CP.economics_status(big, 60)[0], FAIL)
check("  理由に残枠が出る", "80,000" in CP.economics_status(big, 60)[1], True)

small = profit.compute(3000, 15.0, 430, 1500, 10, monthly_sold=60)     # 発注額 15,000円
check("発注額15,000円は FAIL でない", CP.economics_status(small, 60)[0] != FAIL, True)

# 境界。上限ちょうどは通す（超えたら落とす）。
edge_cost = CP.MAX_ORDER_TOTAL_YEN // 10
edge = profit.compute(edge_cost * 3, 15.0, 430, edge_cost, 10, monthly_sold=60)
check("上限ちょうど(80,000円)は FAIL でない", CP.economics_status(edge, 60)[0] != FAIL, True)


print()
if FAILS:
    print(f"NG {len(FAILS)}件")
    raise SystemExit(1)
print("全部 ok")
