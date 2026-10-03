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

from dataclasses import dataclass, field

import fba_cost

# 消費税。販売手数料（税抜表示）と仕入れ（税抜）の両方に効く。
TAX = 1.1

# 半値処分の前提（成果物20・23 と同じ）。
# メルカリで売価の半額で捌く想定。販売手数料10%、送料は1個500円を当社負担。
HALF_DISPOSAL_FEE_RATE = 0.10
HALF_DISPOSAL_SHIPPING_YEN = 500

# 出品許可申請の書類要件（納品書10点以上）。発注点数の下限に使う。
MIN_QTY_FOR_UNGATING = 10

# 🔴 **旧 `OTHER_UNIT_COSTS_YEN = 206` は廃止しました（2026-10-04 / 成果物33）。**
#
# 206円は 22cm土鍋 L001（体積 6,728cm³・FBA標準区分7）1点の実測を**全商品に当てた**
# ものでした。小型雑貨（600cm³）の実額は **63円**で、3.3倍の過大計上です。内訳の誤り：
#   保管料   87円 → 小型 **5.1円**（体積比例。土鍋の26〜58倍だった）
#   納品送料 64円 → 1箱30個で **20.3円**（箱あたりの費用を按分していなかった）
#   梱包資材 55円 → 1箱30個で **12.8円**（同じ）
# さらに外注費25円が旧モデルには入っていませんでした。
#
# 以後、FBA配送代行以外の固定費は **サイズ区分から `fba_cost.other_costs()` で引きます。**
# サイズ区分は Keepa の `fbaFees.pickAndPackFee` から逆引きできます（`fba_cost.tier_from_fba_fee`）。
# **区分が決まらないときは推測で埋めず UNKNOWN にしてください**（222円〜1,756円まで動きます）。


@dataclass
class Economics:
    sell: int                      # Amazon の実売価格
    unit_cost_incl: int            # 1個あたり原価（税込・卸値×1.1）
    referral_fee_yen: int          # 販売手数料（円・税込）
    fba_yen: int                   # FBA 配送代行手数料（円）
    gross_per_unit: int            # 1個粗利（成果物22・23 と同じ定義。保管/納品/梱包を含まない）
    margin_pct: float              # 利益率（売価比）
    other_unit_costs: int          # 保管料+納品送料+梱包資材+外注（**サイズ区分別**）
    net_per_unit: int              # 1個あたりの手残り（gross - other_unit_costs）
    net_margin_pct: float          # 手残りの率
    qty: int                       # 発注点数
    order_total: int               # 発注額（税込）
    months_to_sell: float | None   # 売り切る月数（月販から）
    half_disposal_loss: int        # 半値処分したときの損失（円）
    cost_ratio_pct: float          # 卸率（売価比）
    # ── ここから下は 2026-10-04 に追加（原価モデル v2）────────────────────
    size_tier: str | None = None   # FBA サイズ区分。None なら**決まっていない**（推測しない）
    other_breakdown: dict = field(default_factory=dict)  # その他固定費の内訳
    grade: str = fba_cost.GRADE_UNKNOWN                  # A / B / C / UNKNOWN
    grade_reason: str = ""                               # 等級の根拠（中央値と悲観値）
    worst_net_per_unit: int | None = None                # 悲観シナリオの手残り
    worst_margin_pct: float | None = None                # 悲観シナリオの利益率
    cliff_note: str = ""                                 # 750円 / 1,000円 の崖の助言

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
            monthly_sold: int | None = None,
            size_tier: str | None = None,
            category: str | None = None,
            unit_decided: bool = True,
            peak: bool = False, apparel: bool = False) -> Economics:
    """1 SKU ぶんの採算。すべて円・整数に丸めて返す（報告と同じ粒度）。

    2026-10-04 に変わったところ（成果物33 / 34）
    --------------------------------------------
    1. **その他固定費は固定206円ではなく、サイズ区分から引く**（小型63円〜標準8 739円）。
       `size_tier` を渡さなければ **Keepa の FBA配送代行手数料から逆引き**します。
       逆引きできなければ `size_tier=None` のままで、等級は UNKNOWN になります。
    2. **販売手数料は750円の崖を効かせる**（売上の合計が750円以下なら一律5%・最低30円税抜）。
       `fee_pct`（Keepa の丸めた率）は公式の段へ**切り上げ**て使います。
    3. **誤差幅（売価7%＋200円）は撤去**し、`grade`（A/B/C/UNKNOWN）に置き換えました。
    """
    sell_i = int(round(sell))
    cost_i = int(round(unit_cost_incl))
    tier = size_tier or fba_cost.tier_from_fba_fee(int(fba_yen or 0) or None, sell_i)
    # 販売手数料は 750円の崖つきで引き直す（Keepa の率は「切り上げの手がかり」として渡す）。
    fee_i = fba_cost.referral_yen(sell_i, category, fee_pct)
    # FBA配送代行は区分が判ればそちらを使う（売価1,000円以下の安い列が効く）。
    fba_i = fba_cost.fba_fee_yen(tier, sell_i) if tier else int(round(fba_yen))
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

    # 消化月数は保管料の計上月数（＝消化月数÷2）に効く。読めなければ3ヶ月を置く。
    months_for_storage = months if months else 3.0
    oc = (fba_cost.other_costs(tier, months_for_storage, peak, apparel)
          if tier else None)
    other = int(round(oc.total)) if oc else 0
    net = gross - other

    g = fba_cost.grade(sell_i, cost_i, tier, category=category, keepa_pct=fee_pct,
                       months_to_sell=months_for_storage, peak=peak, apparel=apparel,
                       unit_decided=unit_decided)

    return Economics(
        sell=sell_i,
        unit_cost_incl=cost_i,
        referral_fee_yen=fee_i,
        fba_yen=fba_i,
        gross_per_unit=gross,
        margin_pct=round(gross / sell_i * 100, 1) if sell_i else 0.0,
        other_unit_costs=other,
        net_per_unit=net,
        net_margin_pct=round(net / sell_i * 100, 1) if sell_i else 0.0,
        qty=qty,
        order_total=order_total,
        months_to_sell=months,
        half_disposal_loss=half_loss,
        cost_ratio_pct=round(cost_i / sell_i * 100, 1) if sell_i else 0.0,
        size_tier=tier,
        other_breakdown=(oc.as_dict() if oc else {}),
        grade=g.grade,
        grade_reason=g.reason,
        worst_net_per_unit=g.worst.get("手残り"),
        worst_margin_pct=g.worst.get("利益率(%)"),
        cliff_note=g.cliff,
    )
