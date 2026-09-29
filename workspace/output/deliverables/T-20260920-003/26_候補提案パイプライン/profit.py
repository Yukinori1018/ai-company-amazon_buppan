#!/usr/bin/env python3
"""採算計算（純関数）。成果物22・23 と**同じ式**を1箇所にまとめたもの。

ここは1円もごまかしません。UI や報告の都合で丸めを変えないでください。
計算の根拠は成果物23（ぺんてる ケリーの採算）と成果物20（商品台帳 L001）で実測突合済みです。

税の扱い（当社は免税事業者）
----------------------------
- **販売手数料率は税抜表示**なので `×1.1` して円に直す（Keepa の実測率も税抜表示）
- **仕入れの消費税は費用**（仕入税額控除ができない）。だから卸値（税抜）を `×1.1` して原価にする
- FBA 配送代行手数料は Keepa の実測値をそのまま使う（既に円・税込相当）
"""

from __future__ import annotations

from dataclasses import dataclass

# 消費税。販売手数料（税抜表示）と仕入れ（税抜）の両方に効く。
TAX = 1.1

# 半値処分の前提（成果物20・23 と同じ）。
# メルカリで売価の半額で捌く想定。販売手数料10%、送料は1個500円を当社負担。
HALF_DISPOSAL_FEE_RATE = 0.10
HALF_DISPOSAL_SHIPPING_YEN = 500

# 出品許可申請の書類要件（納品書10点以上）。発注点数の下限に使う。
MIN_QTY_FOR_UNGATING = 10


@dataclass
class Economics:
    sell: int                      # Amazon の実売価格
    unit_cost_incl: int            # 1個あたり原価（税込・卸値×1.1）
    referral_fee_yen: int          # 販売手数料（円・税込）
    fba_yen: int                   # FBA 配送代行手数料（円）
    gross_per_unit: int            # 1個粗利
    margin_pct: float              # 利益率（売価比）
    qty: int                       # 発注点数
    order_total: int               # 発注額（税込）
    months_to_sell: float | None   # 売り切る月数（月販から）
    half_disposal_loss: int        # 半値処分したときの損失（円）
    cost_ratio_pct: float          # 卸率（売価比）

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def unit_cost_incl_tax(price_excl: float) -> int:
    """NETSEA の卸値（税抜）→ **1個あたり**原価（税込）。

    ⚠️ `set[].price` は **1個の値段**で、`set_num` は「何個単位でしか買えないか」
    （最小発注ロットの倍数）です。**price を set_num で割ってはいけません。**
    2026-09-30 に一度割ってしまい、卸率1.5%・利益率71% という嘘の数字を台帳に書きました。

    根拠（人が実額で検算済みの行）:
      B0DJNX12KZ  price_excl 920 / set_num 3  → 台帳の1個原価 1,012円 = 920×1.1
      B0FN3NWKYZ  price_excl 2,529 / set_num 1 → 台帳の1個原価 2,782円 = 2,529×1.1
      B0171AC6PI  price_excl 2,098 / set_num 12 → 成果物22 の1個原価 2,308円 = 2,098×1.1
    """
    return int(round(price_excl * TAX))


def referral_fee_yen(sell: float, fee_pct: float) -> int:
    """販売手数料（円）。`fee_pct` は税抜表示の率（Keepa の実測値）。"""
    return int(round(sell * fee_pct / 100.0 * TAX))


def order_qty(monthly_sold: int | None, pack: int = 1,
              min_qty: int = MIN_QTY_FOR_UNGATING,
              max_months: float = 6.0) -> int:
    """発注点数を決める。

    - 目安は `min_qty`（出品許可申請の納品書要件が「合計10点以上」）
    - ただし **6ヶ月で売り切れる数**を超えない（社長既定の回転上限。超える案は出さない）
    - 卸はロット（pack）の倍数でしか売らないので、pack の倍数へ切り上げる

    月販が小さい商品では 10点に届きません（初回ロットと申請要件の衝突）。
    ここは無理に10点へ寄せず、**回転を優先**します。書類は他の SKU と合算します。
    """
    pack = max(1, int(pack or 1))
    qty = min_qty
    if monthly_sold:
        cap = int(monthly_sold * max_months)      # 6ヶ月で捌ける上限
        qty = max(1, min(min_qty, cap))
    lots = -(-qty // pack)                        # pack の倍数へ切り上げ
    return lots * pack


def compute(sell: float, fee_pct: float, fba_yen: float,
            unit_cost_incl: float, qty: int,
            monthly_sold: int | None = None) -> Economics:
    """1 SKU ぶんの採算。すべて円・整数に丸めて返す（報告と同じ粒度）。"""
    sell_i = int(round(sell))
    cost_i = int(round(unit_cost_incl))
    fee_i = referral_fee_yen(sell_i, fee_pct)
    fba_i = int(round(fba_yen))
    gross = sell_i - fee_i - fba_i - cost_i
    order_total = cost_i * qty

    months = None
    if monthly_sold:
        months = round(qty / float(monthly_sold), 1)

    # 半値処分: 売価の半額をメルカリで捌く。手取り = 半値×(1-手数料) - 送料。
    half_net_per_unit = max(
        0,
        int(round(sell_i / 2 * (1 - HALF_DISPOSAL_FEE_RATE) - HALF_DISPOSAL_SHIPPING_YEN)),
    )
    half_loss = order_total - half_net_per_unit * qty

    return Economics(
        sell=sell_i,
        unit_cost_incl=cost_i,
        referral_fee_yen=fee_i,
        fba_yen=fba_i,
        gross_per_unit=gross,
        margin_pct=round(gross / sell_i * 100, 1) if sell_i else 0.0,
        qty=qty,
        order_total=order_total,
        months_to_sell=months,
        half_disposal_loss=half_loss,
        cost_ratio_pct=round(cost_i / sell_i * 100, 1) if sell_i else 0.0,
    )
