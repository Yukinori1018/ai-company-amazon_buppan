#!/usr/bin/env python3
"""T-20261014-001：判定の費用モデルに足した3費目・卸率の表示ずれ・入口の順番のテスト（通信0）。

    python3 test_cost_20261014.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import entry_order as EO   # noqa: E402
import fba_cost as F       # noqa: E402
import profit              # noqa: E402

FAILS: list[str] = []


def check(name, got, want) -> None:
    ok = got == want
    print(f"  {'ok' if ok else 'NG'} {name}（got={got!r} want={want!r}）")
    if not ok:
        FAILS.append(name)


def near(name, got, want, tol=0.6) -> None:
    check(name, abs(got - want) <= tol, True)


# ── ① 卸→代行の送料 ────────────────────────────────────────────────
F.TODAY_OVERRIDE = date(2026, 7, 1)          # 繁忙期の影響を外して送料だけ見る
base = F.other_costs("小型", 3.0, supplier_freight=0).total
check("既定は仮置き40円/点", F.SUPPLIER_FREIGHT_YEN, 40.0)
near("送料が既定で40円足される", F.other_costs("小型", 3.0).total - base, 40.0)
near("国分のように按分済みなら0を渡せば足さない", F.other_costs("小型", 3.0, supplier_freight=0).total, base)

# ── ③ 10〜12月の保管単価 ───────────────────────────────────────────
check("7月から3か月は繁忙期0%", F.peak_share(3.0, 7), 0.0)
check("10月から3か月は繁忙期100%", F.peak_share(3.0, 10), 1.0)
check("12月から3か月は1/3", round(F.peak_share(3.0, 12), 3), 0.333)
F.TODAY_OVERRIDE = date(2026, 10, 14)
on = F.other_costs("標準6", 3.0, supplier_freight=0).storage
F.TODAY_OVERRIDE = date(2026, 7, 1)
off = F.other_costs("標準6", 3.0, supplier_freight=0).storage
near("標準6・3か月の保管は10月開始で 10.087/5.676 倍", on / off, 10.087 / 5.676, 0.01)
check("peak=False を渡せば通常単価（旧版の再現）",
      round(F.other_costs("標準6", 3.0, peak=False, supplier_freight=0).storage, 3), round(off, 3))

# ── ② 返品引当 ──────────────────────────────────────────────────────
# 売価3,000円・料率15.4% → 販売手数料 508円 → 返金手数料 50.8円
r = F.return_reserve_yen(508, 288, 1500, 100)
near("返品引当 = 2.5%×(288＋50.8＋0.5×(1500＋100))", r, 0.025 * (288 + 50.8 + 0.5 * 1600), 0.01)
check("返金手数料は上限500円", round(F.return_reserve_yen(9000, 0, 0, 0, 1.0), 1), 500.0)

# ── 等級：推定費目なので最高 B（§3.5 #18）────────────────────────────
g = F.grade(3000, 600, "小型", sell_worst=3000)
check("数字が A でも、送料・返品が仮置きなので最高 B", g.grade, "B")
check("推定費目の名前が判定理由に出る（送料）", "40円/点の仮置き" in g.reason, True)
check("推定費目の名前が判定理由に出る（返品）", "返品率2.5%" in g.reason, True)
g0 = F.grade(3000, 600, "小型", sell_worst=3000, supplier_freight=0)
check("送料が実額（0）でも返品引当は残るので B", g0.grade, "B")
check("その他固定費に返品引当が内数で入る", g.mid["うち返品引当"] > 0, True)

# ── profit.compute と grade の中央値が一致する（1円もずらさない）───────
e = profit.compute(3000, 15.0, 288, 600, 10, monthly_sold=5)
check("compute の手残り＝grade の中央値の手残り", e.net_per_unit, e.mid_net_per_unit)
check("compute の内訳に返品引当", "返品引当" in e.other_breakdown, True)
e0 = profit.compute(3000, 15.0, 288, 600, 10, monthly_sold=5, supplier_freight=0)
near("supplier_freight=0 で手残りが40円戻る", e0.net_per_unit - e.net_per_unit, 40, 1.5)

# 損益分岐（required_sell）にも返品引当と送料が入っている：その売価で中央の手残りが ≒ 0
need = F.required_sell(1200, "小型", 0.0)
mid = F._scenario(need, 1200, "小型", worst=False, category=None, keepa_pct=None,
                  months_to_sell=3.0, peak=None, apparel=False)
near("required_sell の売価で手残り ≒ 0", mid["手残り"], 0, 1.0)

# ── 卸率の表示ずれ（ledger_refresh）────────────────────────────────
try:
    import ledger_refresh as L
    check("数値 58.2 は '58.2%' で書く", L.ratio_cell(58.2), "58.2%")
    check("表示 5820.00%（生値58.2）を直す", L.ratio_from_sheet("5820.00%", 58.2), "58.2%")
    check("表示 58.20%（生値0.582）はそのまま", L.ratio_from_sheet("58.20%", 0.582), "58.2%")
    check("% 書式なしの 71 は 71%", L.ratio_from_sheet("71", 71), "71.0%")
    check("赤字の卸率 120%（生値1.2）は100で割らない", L.ratio_from_sheet("120.00%", 1.2), "120.0%")
    check("単位ずれ疑いの本当の 624.8%（生値6.248）は壊さない", L.ratio_from_sheet("624.80%", 6.248), "624.8%")
    check("文字はそのまま", L.ratio_from_sheet("未確認", "未確認"), "未確認")
    check("2回目も同じ（冪等）", L.ratio_from_sheet("58.20%", 0.582), L.ratio_from_sheet("5820.00%", 58.2))
except ImportError as ex:            # gspread 等が無い環境
    print(f"  （ledger_refresh を読めないので卸率の検査は飛ばす: {ex}）")

# ── 入口の順番（捨てない）────────────────────────────────────────────
check("定価比45%・Amazon=定価×0.86 → 見込み52.3%で先", EO.group_of(EO.effective_rate(450, 1000)), EO.GROUP_FIRST)
check("定価比50%・Amazon90日中央値が定価税込どおり → 50%で先",
      EO.group_of(EO.effective_rate(500, 1000, 1100)), EO.GROUP_FIRST)
check("定価比50%・Amazonが定価の半値 → 100%で後（捨てない）",
      EO.group_of(EO.effective_rate(500, 1000, 550)), EO.GROUP_LATER)
check("定価なしは真ん中", EO.group_of(EO.effective_rate(500, None)), EO.GROUP_UNKNOWN)
near("セット3点の中央値は1点あたりに割る", EO.effective_rate(500, 1000, 3300, 3), 0.5, 1e-9)
xs = [None, 0.9, 0.4, 0.55, 0.56]
check("並べると 55%以下 → 定価なし → 55%超、件数は減らない",
      sorted(xs, key=EO.sort_key), [0.4, 0.55, None, 0.56, 0.9])

print(f"\n{'全部 ok' if not FAILS else f'NG {len(FAILS)}件: {FAILS}'}")
sys.exit(1 if FAILS else 0)
