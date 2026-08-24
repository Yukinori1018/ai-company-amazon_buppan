"""想定仕入れ金額（上限）の計算ロジック（T-20260817-005 / scan_v14）。

社長の使い方（2026-08-24 の方針）:

> 「脳死で連絡をして、利益が確保出来る金額で仕入れられるのであれば、仕入れたい。
>   その為に **想定仕入れ金額もリストにして欲しい**」

つまりこの数字は「**メーカーにいくらまでなら出せるかの提示上限**」です。
社長はリストの `想定仕入れ金額(上限)` 列だけを見て交渉に入れる必要があるので、
**1円もごまかさない**こと、**何を引いたかが全部見える**ことの2つを設計要件にしています。

---

## 式

    想定仕入れ金額(上限, 税込)
      = 基準売価
        − 販売手数料（カテゴリ料率・最低手数料あり・不確実性バッファ込み）
        − FBA配送代行手数料（サイズ区分別）
        − FBA在庫保管手数料（推定・保管月数ぶん）
        − 納品外注費（ラベル貼付 + 梱包 + 納品送料）
        − その他経費
        − 目標純利益（基準売価 × TARGET_NET_MARGIN）

`赤字ライン` は同じ式から目標純利益だけを外したもの（純利益0の上限）。

## 基準売価をどう選ぶか（ここが一番効く）

「今の売値」で計算すると、相乗りが増えて値下がりした瞬間に赤字になります。
そこで **保守側**に倒し、次のうち小さい方を採用します。

  1. 現在の新品最安値（送料込）
  2. 2026-02-23 以降に記録された最安値（＝価格定義が一貫している窓の底値）

> なぜ 2026-02-23 かというと、Keepa の NEW 系列はこの日を境に
> 「出品価格」→「着地価格（出品価格+送料）」へ定義が変わっており、
> それ以前と混ぜた最小値は意味が壊れるためです（T-20260824-001 D1）。

## 正直に書いておく前提（〔推定〕は数字を鵜呑みにしないこと）

- **販売手数料率**は `calc/fees.py` の表を使います。2026-08-24、経理ハジメが
  `fee-rates-2026-08.md`（T-20260817-005 第1段成果物）に基づき `calc/fees.py` の料率・
  FBA配送代行手数料を **2026年4月改定後の現行値へ更新済み**です（二次情報4系統相互一致で
  確認。一次情報の目視確認はできていないため確度は「確認」であって「確定」ではない）。
  これに伴い、**`FEE_RATE_BUFFER_PT` の不確実性バッファは 0.0 に落としました**
  （表そのものが現行値になったため、二重に安全側へ倒す必要がなくなったため）。
  詳細・確度・出典は `fee-rates-2026-08.md` を参照。
- **FBA在庫保管手数料**は `calc/fees.py` に無いので、このモジュールで独自に推定します。
  レートは繁忙期（10〜12月）の高い方を採用＝保守側。2026-08-24、経理ハジメが
  `STORAGE_FEE_YEN_PER_M3_MONTH` を公式値（繁忙期10.087円/1,000cm³=10,087円/m³）へ
  補正しました（旧9,170円は暫定値）。〔確認・二次情報2系統一致〕
- **消費税**は税込で通します（Amazon の手数料も税込売値ベース）。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

# calc/fees.py（共有の料率表）を借りる。数値の出典管理はあちらに一本化しておく。
_CODE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan"
             "/workspace/output/agent_output/T-20260521-005/code")
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))
from calc import fees  # noqa: E402

# ==========================================================================
# 定数（ここだけ直せば全列が変わる）
# ==========================================================================

# 会社KPI（CLAUDE.md §1）が「利益率20%以上」なので、目標純利益率も20%に合わせる。
# 「この値段までなら20%取れます」＝社長がメーカーに出せる上限、という意味になる。
TARGET_NET_MARGIN = 0.20

# 販売手数料率の不確実性バッファ（ポイント）。
# 2026-08-24: calc/fees.py の表を現行値へ更新したため 0.0 に変更（旧 0.010）。
# 表そのものが2026年4月改定後の値になったので、二重に安全側マージンを乗せる必要はない。
# 残る不確実性（drugstore区分の実在・大型サイズの細目など）は fee-rates-2026-08.md §6 参照。
# 将来また改定の疑いが出たら、ここではなく先に fees.py 側を検証・更新すること。
FEE_RATE_BUFFER_PT = 0.0

# 納品外注費（サイズ別・円）。内訳 = Amazon商品ラベル貼付(公式 G200483750) + 梱包外注(WAM NET) + 納品送料。
# v1.3 実走（scan_v13）と同じ値を使う。ここを変えると過去の列と比較できなくなるので慎重に。
OUTSOURCE_COST = {"small": 182, "standard_1": 282, "standard_2": 332,
                  "large_1": 500, "large_2": 700, "unknown": 282}

# その他経費（円/個）。返品・不良・振込手数料などの雑費の丸め。
OTHER_COSTS = 100

# FBA在庫保管手数料。円/m³/月。
# 2026-08-24 ハジメ更新: 公式の繁忙期(10〜12月)レート 10.087円/1,000cm³ = 10,087円/m³ に補正
# （旧9,170円は暫定値。fee-rates-2026-08.md §4 参照）。
# 通常期(1〜9月)は 5.676円/1,000cm³=5,676円/m³ だが、年間を通して繁忙期レートを採用＝保守側。
STORAGE_FEE_YEN_PER_M3_MONTH = 10087
# 保管月数の上限。消化月数がこれを超えても、これ以上は積まない（長期保管は撤退判断の領域）。
STORAGE_MONTHS_CAP = 6.0
# 寸法が取れない商品の保管料〔推定〕。標準サイズの代表値として固定額を置く。
STORAGE_FEE_FALLBACK_YEN = 60


def storage_fee_yen(dims_mm: Optional[tuple], months: Optional[float]) -> tuple:
    """FBA在庫保管手数料の推定額（円）と、その計算根拠の文字列を返す。

    dims_mm は (長さ, 幅, 高さ) の mm タプル。1つでも欠けたら固定額にフォールバックする。
    months は消化月数（在庫が捌けるまでの月数）。None なら1ヶ月とみなす。
    """
    m = min(months if months and months > 0 else 1.0, STORAGE_MONTHS_CAP)
    if not dims_mm or len(dims_mm) != 3 or any(not d or d <= 0 for d in dims_mm):
        return round(STORAGE_FEE_FALLBACK_YEN * m), f"固定額{STORAGE_FEE_FALLBACK_YEN}円×{m:.1f}ヶ月(寸法欠落)"
    volume_m3 = (dims_mm[0] / 1000) * (dims_mm[1] / 1000) * (dims_mm[2] / 1000)
    fee = volume_m3 * STORAGE_FEE_YEN_PER_M3_MONTH * m
    return round(fee), f"{volume_m3 * 1000:.2f}L×{STORAGE_FEE_YEN_PER_M3_MONTH}円/m³×{m:.1f}ヶ月"


def referral_fee_yen(price: float, category_key: str) -> tuple:
    """販売手数料（円）と、適用した料率（％表示用の小数）を返す。

    不確実性バッファぶん料率を上乗せしてから、カテゴリの最低手数料と比較する。
    """
    cfg = fees.REFERRAL_FEE_TABLE.get(category_key, fees.REFERRAL_FEE_TABLE["default"])
    rate = cfg["rate"] + FEE_RATE_BUFFER_PT
    fee = max(price * rate, cfg.get("min_fee_yen", 0))
    return fee, rate


def compute(
    *,
    current_price: Optional[float],
    floor_price: Optional[float],
    category_key: str,
    size_key: str,
    dims_mm: Optional[tuple] = None,
    turnover_months: Optional[float] = None,
    target_margin: float = TARGET_NET_MARGIN,
) -> dict:
    """1商品ぶんの想定仕入れ金額（上限）を計算する。

    引数:
      current_price   : 現在の新品最安値（送料込・税込・円）
      floor_price     : 2026-02-23 以降に記録された最安値（円）。無ければ None
      category_key    : calc/fees.py のカテゴリキー
      size_key        : calc/fees.py のサイズキー（small / standard_1 / ...）
      dims_mm         : (長さ, 幅, 高さ) mm。保管料の推定に使う
      turnover_months : 消化月数。保管月数として使う
      target_margin   : 目標純利益率（既定 20%）

    返り値の dict はそのまま CSV の列になる。**値が出せないときは None を返し、
    0 や適当な数で埋めない**（0円で仕入れられる、と誤読されるのが一番まずい）。
    """
    prices = [p for p in (current_price, floor_price) if p and p > 0]
    if not prices:
        return {"limit": None, "breakeven": None, "base_price": None, "basis": "",
                "referral_rate": None, "cost_breakdown": "価格が取れず計算不能",
                "net_at_limit": None, "buy_rate_pct": None}
    base = min(prices)
    basis = ("過去最安値(2026-02-23以降)" if floor_price and base == floor_price
             else "現在の新品最安値")

    referral, rate = referral_fee_yen(base, category_key)
    fba_key = size_key if size_key in fees.FBA_FEE_TABLE else "standard_1"
    fba = fees.FBA_FEE_TABLE[fba_key]["fba_fee_yen"]
    storage, storage_note = storage_fee_yen(dims_mm, turnover_months)
    outsource = OUTSOURCE_COST.get(size_key, OUTSOURCE_COST["unknown"])

    fixed = referral + fba + storage + outsource + OTHER_COSTS
    breakeven = base - fixed                       # 純利益0の仕入れ上限
    limit = breakeven - base * target_margin       # 目標利益率を確保できる仕入れ上限

    breakdown = (f"基準売価{int(base)} − 販売手数料{int(referral)}({rate * 100:.1f}%) "
                 f"− FBA配送{int(fba)} − 保管{int(storage)}[{storage_note}] "
                 f"− 外注{outsource} − 雑費{OTHER_COSTS} "
                 f"− 目標利益{int(base * target_margin)}({target_margin * 100:.0f}%)")

    return {
        "limit": int(math.floor(limit)) if limit > 0 else None,
        "breakeven": int(math.floor(breakeven)) if breakeven > 0 else None,
        "base_price": int(base),
        "basis": basis,
        "referral_rate": round(rate * 100, 1),
        "cost_breakdown": breakdown,
        # 上限ちょうどで仕入れたときの純利益（＝目標利益そのもの）。社長が金額感を掴むため。
        "net_at_limit": int(round(base * target_margin)) if limit > 0 else None,
        # 掛け率＝上限 ÷ 基準売価。「定価の何％まで出せるか」の交渉感覚に直結する。
        "buy_rate_pct": round(limit / base * 100, 1) if limit > 0 else None,
    }
