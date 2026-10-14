#!/usr/bin/env python3
"""FBA の原価モデル v2 — **サイズ区分別・公式料金表ベース**（純関数・ネットワーク0）。

旧 `profit.OTHER_UNIT_COSTS_YEN = 206` と `set_family.DEFAULT_FBA_YEN = 415` を置き換えます。
数表はすべて経理ハジメが 2026-10-04 に公式ページの原文から確定させたもの
（成果物33 / `agent_output/T-20260920-003/cost_model_v2/model.py`）で、**ここで積み直しません**。

旧モデル（固定費 821円/個）の何が間違っていたか
-----------------------------------------------
| 項目 | 旧 | 正 | 誤りの性質 |
|---|---|---|---|
| 誤差幅 200円 ＋ 売価7% | 費用として加算 | **0円**（`grade()` の等級に移した） | 判定の不確実性は費用ではない。売価500円では誤差幅が売価の47%になり、低単価帯だけを狙い撃ちで落としていた |
| FBA配送代行 | 415円を全商品 | 区分別 **222〜1,756円**（小型は288円／売価1,000円以下なら222円） | 415円は別商品（標準区分3）の値。鍋 L001 の実測は472円 |
| 保管料 | 87円 | 小型 **5.1円** | 22cm土鍋（6,728cm³）の実測を小型雑貨（600cm³）に当てていた |
| 納品送料 | 64円 | 小型 **5.5〜20.3円** | 箱あたりの費用を体積で按分していなかった＝「量で薄まる」が入っていない |
| 梱包資材 | 55円 | 小型 **7.0〜12.8円** | 同じ |
| 販売手数料率 | 8.4% を全商品 | ホーム&キッチン／文房具／DIY／家具は **15.4%** | 8.4%は服&ファッション小物の率。**ここだけは旧モデルが甘かった** |
| 750円の崖 | 無かった | **売上合計750円以下は5%** | 売価751〜900円・1,001〜1,100円は値下げした方が手残りが増える「死に帯」 |

2026-10-09 追記（ハジメ・T-20260929-001 成果物15）：納品代行をおりおんFBAの実額に差し替え
-----------------------------------------------------------------------------------------
外注 25円（相場の中央値）→ `orion_prep_yen()`（ラベル11＋簡易検品11＋(荷受22＋プラン55)÷1SKUの入荷点数
＋箱代480÷1箱の点数、税別×1.1）。箱とラベルが代行料金に入るので梱包資材は0円。1箱の点数の既定は
30→20（少量期の中央）。小型のその他固定費は 63→95円。648件の再判定で A→B 22件・B→C 7件、GO は0件のまま。
`prep="legacy"`・`units_per_box=30` で 2026-10-04 版を再現できます。

公式出典（2026-10-04 に原文取得・`agent_output/T-20260920-003/lowprice34/pricing.html`）
  FBA配送代行・保管料・販売手数料  https://sell.amazon.co.jp/pricing
  逐語「商品1点あたりの売上の合計が750円以下の場合は商品代金の5%」
  逐語「上記の手数料には10％の消費税が含まれます。」（FBA配送代行）
  逐語「注: 手数料はすべて税抜き表示となっており、下記に記載の金額に加えて税金が課金されます。」（販売手数料）
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import date

TAX = 1.1

# ── 1. FBA配送代行手数料（公式・税込。(1,000円超, 1,000円以下, 寸法)）─────────
# 「価格が1,000円以下の商品」は専用の安い料金表があります（2024年4月導入・小型軽量商品
# プログラムの後継）。小型・標準1なら −66円/個。
FBA: dict[str, tuple[int, int, str]] = {
    "小型":   (288, 222, "25×18×2.0cm以下・250g以下"),
    "標準1":  (318, 252, "35×30×3.3cm以下・1kg以下"),
    "標準2":  (410, 344, "三辺合計20cm以下・2kg以下"),
    "標準3":  (415, 358, "三辺合計30cm以下・2kg以下"),
    "標準4":  (420, 371, "三辺合計40cm以下・2kg以下"),
    "標準5":  (425, 379, "三辺合計50cm以下・2kg以下"),
    "標準6":  (430, 391, "三辺合計60cm以下・2kg以下"),
    "標準7":  (472, 427, "三辺合計80cm以下・5kg以下"),
    "標準8":  (532, 466, "三辺合計100cm以下・9kg以下"),
    "大型1":  (589, 523, "三辺合計60cm以下・2kg以下（大型）"),
    "大型2":  (624, 558, "80cm以下・5kg以下"),
    "大型3":  (675, 609, "100cm以下・10kg以下"),
    "大型4":  (781, 715, "120cm以下・15kg以下"),
    "大型5": (1020, 954, "140cm以下・20kg以下"),
    "大型6": (1100, 1034, "160cm以下・25kg以下"),
    "大型7": (1532, 1466, "180cm以下・30kg以下"),
    "大型8": (1756, 1690, "200cm以下・40kg以下"),
}

# 区分の並び（「1段上」を引くため）。
TIERS: tuple[str, ...] = tuple(FBA.keys())

# 代表体積（cm³）。**仮定です。**区分の上限寸法から現実的な形を置いたもの（ハジメ）。
# 実寸（Keepa の packageLength/Width/Height）が取れるなら `tier_from_dimensions()` を使い、
# 体積もそちらの実測を渡してください。
VOL: dict[str, int] = {
    "小型": 600, "標準1": 1980, "標準2": 280, "標準3": 840, "標準4": 2106,
    "標準5": 4224, "標準6": 7280, "標準7": 17010, "標準8": 32912,
    "大型1": 7280, "大型2": 17010, "大型3": 32912, "大型4": 56000,
    "大型5": 90000, "大型6": 130000, "大型7": 180000, "大型8": 250000,
}

# ── 2. 保管料（公式・円/1,000cm³/月・税込）────────────────────────────────
# 式の原文「5.676円 × 商品サイズ(cm³) ÷ (10cm×10cm×10cm) × 保管日数 / 当月の日数」
STORAGE = {
    ("標準", False): 5.676, ("標準", True): 10.087,      # True = 10〜12月（繁忙期・1.78倍）
    ("大型", False): 3.278, ("大型", True): 6.984,
    ("服", False): 3.10,   ("服", True): 5.50,
}

# ── 3. FC納品送料・梱包資材 ───────────────────────────────────────────────
# FBAパートナーキャリア ヤマト 140サイズ（60×45×35cm）= 608円/箱・内容積 94,500cm³。
BOX_YEN = 608
BOX_VOLUME_CM3 = 94_500
FILL_RATE = 0.70              # 箱の実装率（仮定）。悲観ではこれを0.7倍する
# 1箱に入れる個数の既定（仮定）。
# 2026-10-09 に 30 → 20 へ下げました（ハジメ・T-20260929-001 成果物15）。
# 30 は月300個規模の値で、少量期（月30〜100個）は入荷がばらけて1箱10〜20個しか入らない。
# 中央値＝月100個の段（5SKU×20個を5箱）の 20個。
# 体積から計算した満載数のほうが小さければ、そちら（物理的に入る数）が勝ちます。
UNITS_PER_BOX = 20
BOX_MATERIAL_YEN = 250        # 段ボール140サイズ1枚（推定・公式値なし）※legacy のみ
PER_UNIT_MATERIAL_YEN = 4.5   # OPP袋3円 + FNSKUラベル1.5円（推定・公式値なし）※legacy のみ
OUTSOURCE_YEN = 25            # 旧：納品代行の検品/ラベル/梱包の中央値（税込）※legacy のみ

# ── 3b. 納品代行 = おりおんFBA（2026-10-09 主力確定・CLAUDE.md §3.4）──────────
# 出典：おりおんFBA 公式料金表（T-20260929-001 成果物01 §4-1・2026-09-30 取得）と
# 2026-10-07 の書面回答（1個から可・月額なし・預かり金3万円・無料保管7営業日）。
# **金額は税別。計算では ×1.1 する。**
# 箱代は「箱・梱包」の重量帯料金。段ボール代を含むかは公式に明記なし（推定：含む）。
# FNSKUラベルの用紙もラベル11円に含むと置く（推定）。→ legacy の梱包資材は0円になる。
PREP_DEFAULT = "orion"              # "legacy" で 2026-10-04 版（外注25円＋資材）を再現
ORION_LABEL_YEN = 11                # 1点
ORION_INSPECT_YEN = 11              # 簡易検品 1点（任意。直送で誰も現物を見ないので既定で入れる）
ORION_RECEIVE_PER_SKU_YEN = 22      # 荷受 1SKU
ORION_PLAN_PER_SKU_YEN = 55         # 納品プラン作成 1SKU
ORION_BOX_YEN = {10: 370, 15: 480, 20: 590, 25: 700}   # 〜kg の帯 → 1箱
ORION_BOX_BAND_KG = 15              # 既定の重量帯（仮定）
ORION_BAG_YEN = 45                  # OPP袋（Amazon が袋入れを求める商品だけ）
ORION_INSPECT_DEFAULT = True
# 1SKUあたり1回の入荷で何点届くか（仮定）。出品許可の書類要件（10点以上）に合わせた中央値。
UNITS_PER_SKU = 10
ORION_FREE_STORAGE_BUSINESS_DAYS = 7
ORION_OVERDUE_STORAGE_YEN_MONTH = 5_500   # 税別。7営業日を超えた月。単位（アカウント／棚／SKU）は未確認
ORION_DEPOSIT_YEN = 30_000                # 初回預かり金。契約終了時に全額返金＝費用ではなく資金


def orion_prep_yen(units_per_box: int, units_per_sku: int = UNITS_PER_SKU,
                   inspect: bool = ORION_INSPECT_DEFAULT,
                   box_band_kg: int = ORION_BOX_BAND_KG, bagged: bool = False) -> float:
    """おりおんFBAの作業費（1点あたり・円・税込）。FC までの送料は含まない（`BOX_YEN`）。

    1点 = (ラベル11 ＋ 検品11 ＋ 袋45? ＋ (荷受22＋プラン55)÷1SKUの入荷点数
           ＋ 箱代÷1箱の点数) × 1.1
    """
    per_unit = ORION_LABEL_YEN + (ORION_INSPECT_YEN if inspect else 0) \
        + (ORION_BAG_YEN if bagged else 0)
    per_sku = (ORION_RECEIVE_PER_SKU_YEN + ORION_PLAN_PER_SKU_YEN) / max(1, int(units_per_sku))
    per_box = ORION_BOX_YEN[box_band_kg] / max(1, int(units_per_box))
    return (per_unit + per_sku + per_box) * 1.1


def gate_storage_yen_per_unit(lot_units: int, overdue_months: float,
                              share: float = 1.0) -> float:
    """出品許可待ちで無料保管（7営業日）を超えたときの保管料（1点あたり・円・税込）。

    = 5,500円 × 1.1 × 超過月数 × 按分率 ÷ その入荷の点数

    - `overdue_months`：課金される月数。日割りの有無は未確認なので、始まった月を1と数える（保守側）
    - `share`：同じ月に超過している在庫がほかにもあるときの按分率。5,500円が
      アカウント単位の定額なら 1/k（k = その月の超過入荷数）。単位が未確認の間は 1.0（全額を負わせる）
    """
    return ORION_OVERDUE_STORAGE_YEN_MONTH * 1.1 * max(0.0, overdue_months) \
        * max(0.0, share) / max(1, int(lot_units))

# ── 3c. 2026-10-14 追加（T-20261014-001 ハジメ成果物01 §6）：判定が甘かった3費目 ──────
# ハジメの比較で「パイプラインは小型1点あたり約50円甘い」と出た。その差の中身を入れる。
#
# ① 卸→代行（おりおん）の送料。NETSEA・SD はこれまで0円だった（国分だけ卸値に按分済み）。
#    **仮置き 40円/点**（1回の注文 800円 ÷ 1箱20点・ハジメ中央シナリオ）。実額は卸ごとに違うので
#    設定値として外に出す：環境変数 `FBA_SUPPLIER_FREIGHT_YEN` で上書きできる。
#    卸値にすでに送料を按分している経路（国分ネット卸）は呼び出し側が `supplier_freight=0` を渡す。
SUPPLIER_FREIGHT_YEN = float(os.environ.get("FBA_SUPPLIER_FREIGHT_YEN", "40"))
# ② 返品の引当。返品率 2.5%（仮定）。返品1件で失うもの＝FBA配送代行（戻らない）＋返金手数料
#    （販売手数料の10%・上限500円）＋再販できない半分の「原価＋代行・送料」。
RETURN_RATE = 0.025
RETURN_UNSELLABLE_SHARE = 0.5
REFUND_ADMIN_RATE = 0.10
REFUND_ADMIN_CAP_YEN = 500
# ③ 10〜12月の保管単価（公式・`STORAGE` の True 側）。売り切る期間のうち10〜12月に当たる月の
#    割合で、通常単価と繁忙期単価を加重平均する（`peak=None` のとき・期間は今月から）。
PEAK_MONTHS = (10, 11, 12)
#: テスト用。None なら今日の日付で繁忙期の割合を決める
TODAY_OVERRIDE: date | None = None


def freeze_pre_20261014() -> None:
    """テスト用：2026-10-09 版の数字（送料0・返品0・繁忙期なし）に戻す。

    既存テストの固定値（小型95円など）はこの条件の値。10-14 の3費目は
    `test_cost_20261014.py` で別に検査する。"""
    global SUPPLIER_FREIGHT_YEN, RETURN_RATE, TODAY_OVERRIDE
    SUPPLIER_FREIGHT_YEN, RETURN_RATE, TODAY_OVERRIDE = 0.0, 0.0, date(2026, 7, 1)


def est_freight_label() -> str:
    return f"卸→代行の送料（{SUPPLIER_FREIGHT_YEN:g}円/点の仮置き）"


EST_RETURN = f"返品引当（返品率{RETURN_RATE * 100:g}%の仮置き）"


def peak_share(months_to_sell: float, start_month: int | None = None) -> float:
    """売り切る期間（今月から `months_to_sell` か月）のうち、10〜12月に当たる月の割合（0〜1）。"""
    m0 = start_month or (TODAY_OVERRIDE or date.today()).month
    n = max(1, math.ceil(max(0.0, float(months_to_sell)) - 1e-9))
    ms = [((m0 - 1 + i) % 12) + 1 for i in range(n)]
    return sum(1 for m in ms if m in PEAK_MONTHS) / n


def return_reserve_yen(referral_yen_: float, fba_yen_: float, unit_cost_incl: float,
                       other_total: float, rate: float | None = None) -> float:
    """返品の引当（1個あたり・円・税込）。**推定費目**（返品率は仮置き）。

    = 返品率 × ( FBA配送代行 ＋ 返金手数料(販売手数料の10%・上限500円)
                 ＋ 再販不可の割合 × (原価 ＋ その他固定費) )
    """
    rate = RETURN_RATE if rate is None else rate
    admin = min(REFUND_ADMIN_CAP_YEN, REFUND_ADMIN_RATE * float(referral_yen_))
    return max(0.0, rate) * (float(fba_yen_) + admin
                             + RETURN_UNSELLABLE_SHARE * (float(unit_cost_incl) + float(other_total)))


# ── 4. 販売手数料（公式）──────────────────────────────────────────────────
# 🔴 750円は**段階制ではなく閾値**です。「売上の合計が750円以下なら全額5%」。
REFERRAL_CLIFF_YEN = 750
FBA_LOW_PRICE_CLIFF_YEN = 1000      # FBA配送代行の安い列に入る上限
MIN_REFERRAL_YEN_EXCL = 30          # 最低販売手数料（税抜）

# 公式に存在する料率の段（税抜表示）。Keepa の丸めた率はここへ**切り上げ**ます。
OFFICIAL_STEPS: tuple[float, ...] = (5.0, 8.4, 10.4, 12.4, 15.4, 45.4)
WORST_STEP = 15.4                   # 当社が触る範囲のカテゴリー最高段（悲観値に使う）

# カテゴリー別（750円超の率）。カテゴリー名が取れているときだけ使います。
CATEGORY_OVER_750: dict[str, float] = {
    "ホーム&キッチン": 15.4, "文房具・オフィス用品": 15.4, "DIY・工具": 15.4,
    "ガーデニング": 15.4, "家具": 15.4, "その他のカテゴリー": 15.4,
    "おもちゃ&ホビー": 10.4, "スポーツ&アウトドア": 10.4, "カー&バイク用品": 10.4,
    "家電アクセサリー": 10.4, "ホーム&キッチン家電": 10.4, "楽器": 10.4,
    "エレクトロニクス": 8.4, "パソコン・周辺機器": 8.4, "小型家電": 8.4, "大型家電": 8.4,
}

UNKNOWN = "UNKNOWN"


# ── サイズ区分を決める ────────────────────────────────────────────────────


def tier_from_fba_fee(fba_yen: int | None, sell: float | None) -> str | None:
    """**Keepa の `fbaFees.pickAndPackFee` から逆引き**でサイズ区分を決める。

    これが一番確実です。Keepa が返す額は Amazon がその ASIN に実際に当てている料金で、
    寸法の推定が要りません（memory: `knowledge_amazon_presence_is_history_not_snapshot`
    の「手数料は Keepa で ASIN 別に実測できる」）。

    売価で列（1,000円超／以下）が決まるので、**売価を渡すと一意に決まります。**
    売価が無いときは両列から探し、候補が1つだけなら採り、複数なら None（推測しない）。
    """
    if not fba_yen or fba_yen <= 0:
        return None
    hits: list[str] = []
    if sell is not None and sell > 0:
        col = 1 if sell <= FBA_LOW_PRICE_CLIFF_YEN else 0
        hits = [t for t, v in FBA.items() if v[col] == int(fba_yen)]
    if not hits:
        hits = [t for t, v in FBA.items() if int(fba_yen) in (v[0], v[1])]
    return hits[0] if len(hits) == 1 else None


def tier_from_dimensions(length_mm, width_mm, height_mm, weight_g) -> str | None:
    """寸法・重量（Keepa は mm / g）からサイズ区分を決める。

    ⚠️ **小型に入るには「厚さ2.0cm以下」が必須**です。たわし・スポンジのような立体物は
    厚みで弾かれ、三辺合計で 標準2〜3（344〜415円）になります。立体物が288円に入ることは
    ありません（成果物33 §2 の読み方の注意）。
    """
    vals = [length_mm, width_mm, height_mm]
    if any(v is None or v in (-1, 0) for v in vals) or weight_g in (None, -1, 0):
        return None
    dims = sorted(float(v) / 10.0 for v in vals)      # cm・昇順（dims[0] が厚さ）
    thick, mid, longest = dims
    total = sum(dims)
    g = float(weight_g)
    if longest <= 25 and mid <= 18 and thick <= 2.0 and g <= 250:
        return "小型"
    if longest <= 35 and mid <= 30 and thick <= 3.3 and g <= 1000:
        return "標準1"
    for tier, cap_cm, cap_g in (("標準2", 20, 2000), ("標準3", 30, 2000),
                                ("標準4", 40, 2000), ("標準5", 50, 2000),
                                ("標準6", 60, 2000), ("標準7", 80, 5000),
                                ("標準8", 100, 9000)):
        if total <= cap_cm and g <= cap_g:
            return tier
    for tier, cap_cm, cap_g in (("大型1", 60, 2000), ("大型2", 80, 5000),
                                ("大型3", 100, 10000), ("大型4", 120, 15000),
                                ("大型5", 140, 20000), ("大型6", 160, 25000),
                                ("大型7", 180, 30000), ("大型8", 200, 40000)):
        if total <= cap_cm and g <= cap_g:
            return tier
    return None


def tier_up(tier: str, steps: int = 1) -> str:
    """1段上の区分（悲観値に使う）。最上段ならそのまま。"""
    i = TIERS.index(tier)
    return TIERS[min(i + max(0, steps), len(TIERS) - 1)]


# 代表体積の昇順。`tier_from_volume()` と `bundle_advice()` で使います。
# ⚠️ `VOL` は区分の並び順では単調ではありません（標準2 は 280cm³ で小型 600cm³ より小さい）。
# だから「体積から区分を引く」ときは必ずこの並びを使ってください。
_TIERS_BY_VOLUME: tuple[str, ...] = tuple(sorted(TIERS, key=lambda t: VOL[t]))


def tier_from_volume(volume_cm3: float) -> str:
    """体積（cm³）に収まる一番小さい区分。セットを組んだときの区分の見積りに使います。

    代表体積ベースの**目安**です。実物の寸法は現物を測るまで確定しません
    （平たい2枚重ねが標準1に収まるか等は形状で決まります）。
    """
    for t in _TIERS_BY_VOLUME:
        if VOL[t] >= volume_cm3:
            return t
    return _TIERS_BY_VOLUME[-1]


def fba_fee_yen(tier: str, sell: float) -> int:
    """FBA配送代行（円・税込）。売価1,000円以下なら安い列。"""
    hi, lo, _ = FBA[tier]
    return lo if sell <= FBA_LOW_PRICE_CLIFF_YEN else hi


# ── 販売手数料 ────────────────────────────────────────────────────────────


def referral_pct(sell: float, category: str | None = None,
                 keepa_pct: float | None = None, worst: bool = False) -> float:
    """販売手数料率（税抜表示の%）。

    - **750円以下は一律5%**（閾値。段階制ではない）
    - 750円超は ①カテゴリー名が判っていればその率 ②Keepa の実測率を公式の段へ**切り上げ**
      ③どちらも無ければ最高段（15.4%）
    - `worst=True` で悲観値（カテゴリー最高段 15.4%）

    Keepa の `referralFeePercent` は整数に丸まるので（実測 15.0 / 10.0 / 8.0）、
    公式の段（15.4 / 10.4 / 8.4）へ**切り上げ**ます。丸めで甘くならない向きに寄せます。
    """
    if sell <= REFERRAL_CLIFF_YEN:
        return 5.0
    if worst:
        return WORST_STEP
    if category and category in CATEGORY_OVER_750:
        return CATEGORY_OVER_750[category]
    if keepa_pct is not None and keepa_pct > 0:
        for s in OFFICIAL_STEPS:
            if keepa_pct <= s + 1e-9:
                return s
        return OFFICIAL_STEPS[-1]
    return WORST_STEP


def referral_yen(sell: float, category: str | None = None,
                 keepa_pct: float | None = None, worst: bool = False) -> int:
    """販売手数料（円・税込）。最低30円（税抜）＝33円（税込）。"""
    pct = referral_pct(sell, category, keepa_pct, worst)
    yen = max(sell * pct / 100.0, float(MIN_REFERRAL_YEN_EXCL))
    return int(round(yen * TAX))


# ── FBA配送代行以外の固定費 ───────────────────────────────────────────────


@dataclass
class OtherCosts:
    """1個あたりの「FBA配送代行以外」の費用（円・税込）とその内訳。"""

    storage: float
    inbound: float
    material: float
    outsource: float
    volume_cm3: float
    units_per_box: int
    freight: float = 0.0          # 卸→代行の送料（2026-10-14〜・既定は仮置き40円/点）

    @property
    def total(self) -> float:
        return self.storage + self.inbound + self.material + self.outsource + self.freight

    def as_dict(self) -> dict:
        return {"保管": round(self.storage, 1), "納品送料": round(self.inbound, 1),
                "梱包資材": round(self.material, 1), "外注": round(self.outsource, 1),
                "卸→代行の送料": round(self.freight, 1),
                "合計": round(self.total, 1), "1箱の入り数": self.units_per_box}


def _storage_rate(tier: str, peak: bool | None, apparel: bool,
                  months_to_sell: float = 3.0) -> float:
    """保管単価。`peak=None`（既定・2026-10-14〜）は売り切る期間の10〜12月の割合で加重平均。"""
    key = "服" if apparel else ("大型" if tier.startswith("大型") else "標準")
    if peak is None:
        sh = peak_share(months_to_sell)
        return STORAGE[(key, False)] * (1 - sh) + STORAGE[(key, True)] * sh
    return STORAGE[(key, bool(peak))]


def box_capacity(volume_cm3: float, fill_rate: float = FILL_RATE) -> int:
    """140サイズの箱に物理的に入る個数（実装率を掛けた容積から）。最低1個。"""
    usable = BOX_VOLUME_CM3 * max(0.05, float(fill_rate))
    return max(1, int(usable // max(1.0, float(volume_cm3))))


def other_costs(tier: str, months_to_sell: float = 3.0, peak: bool | None = None,
                apparel: bool = False, fill_rate: float = FILL_RATE,
                volume_cm3: float | None = None,
                units_per_box: int = UNITS_PER_BOX,
                outsource: float | None = None,
                prep: str = PREP_DEFAULT,
                units_per_sku: int = UNITS_PER_SKU,
                inspect: bool = ORION_INSPECT_DEFAULT,
                supplier_freight: float | None = None) -> OtherCosts:
    """保管料・FC納品送料・梱包資材・外注費・卸→代行の送料（1個あたり・円）。

    2026-10-14：`peak=None`（既定）で10〜12月の保管単価を期間の割合で効かせる。
    `supplier_freight=None` で仮置き `SUPPLIER_FREIGHT_YEN`（40円/点）を足す。卸値に送料が
    按分済みの経路は 0 を渡す。旧版を再現するなら `peak=False, supplier_freight=0`。

    **外注費は `prep="orion"`（既定・2026-10-09〜）でおりおんFBAの実額**
    （`orion_prep_yen()`：ラベル・検品・荷受/SKU・プラン/SKU・箱代）。箱代とラベルが
    代行料金に入るので梱包資材は0円。`prep="legacy"` は 2026-10-04 版（外注25円＋資材）。
    `outsource` に数値を渡すと外注費をその値で上書きします（資材は prep に従う）。

    **納品送料（608円/箱）と箱代は「1箱に入れる個数」で割ります。**
    割る個数は `units_per_box`（既定20個・2026-10-09 に30から変更）と、
    体積から計算した**物理的に入る個数**の**小さい方**です。

    社長の「固定費は量を増やせば薄まる」はここについて正しく、小型なら1箱110個入って
    1個あたり5.5円まで下がります。ただし **保管料は薄まりません**（体積比例）。
    **FBA配送代行も薄まりません**（1個につき1回）。

    `months_to_sell` は売り切る月数。保管料は**月次の平均在庫**に課されるので、
    線形に売り切る前提で **計上月数 = 消化月数 ÷ 2** を使います。
    """
    vol = float(volume_cm3 if volume_cm3 else VOL[tier])
    rate = _storage_rate(tier, peak, apparel, months_to_sell)
    storage = rate * vol / 1000.0 * (max(0.0, float(months_to_sell)) / 2.0)
    q = max(1, min(int(units_per_box), box_capacity(vol, fill_rate)))
    inbound = BOX_YEN / q
    if prep == "orion":
        material = 0.0
        out = orion_prep_yen(q, min(int(units_per_sku), 10**6), inspect)
    else:
        material = PER_UNIT_MATERIAL_YEN + BOX_MATERIAL_YEN / q
        out = OUTSOURCE_YEN
    if outsource is not None:
        out = float(outsource)
    fr = SUPPLIER_FREIGHT_YEN if supplier_freight is None else float(supplier_freight)
    return OtherCosts(storage, inbound, material, float(out), vol, q, max(0.0, fr))


# ── 必要売価 ─────────────────────────────────────────────────────────────


def required_sell(unit_cost_incl: float, tier: str, margin: float = 0.0,
                  category: str | None = None, keepa_pct: float | None = None,
                  months_to_sell: float = 3.0, peak: bool | None = None,
                  apparel: bool = False, worst: bool = False,
                  return_rate: float | None = None, **kw) -> float | None:
    """**「この原価なら、いくらで売れている棚でないと駄目か」。**

    `margin=0` で損益分岐、`0.20` で利益率20%。原価は **Amazon 1個あたりの税込原価**
    （卸1点 × セット数 × 1.1。当社は免税事業者なので仕入消費税は費用）。

    売価で FBA の列（1,000円）と販売手数料の段（750円）が変わるので、**枝ごとに解いて
    自分の枝に収まる解だけを採り、その最小値**を返します（誤差幅は入れません）。
    """
    oth = other_costs(tier, months_to_sell, peak, apparel, **kw).total
    cost = float(unit_cost_incl)
    fixed = oth + cost
    r = max(0.0, RETURN_RATE if return_rate is None else return_rate)
    cands: list[float] = []

    def feasible(p: float, low_fba: bool, pct: float) -> bool:
        """その売価が本当にこの枝（FBA の列・手数料の段）に属するか。"""
        if p <= 0:
            return False
        if low_fba != (p <= FBA_LOW_PRICE_CLIFF_YEN):
            return False
        return abs(referral_pct(p, category, keepa_pct, worst) - pct) < 1e-9

    for low_fba in (True, False):
        fba = FBA[tier][1] if low_fba else FBA[tier][0]
        for pct in sorted({5.0, referral_pct(1200, category, keepa_pct, worst),
                           referral_pct(2000, category, keepa_pct, worst),
                           referral_pct(5000, category, keepa_pct, worst)}):
            # 返品引当（2026-10-14）：r×(FBA ＋ 再販不可×(原価＋その他)) は定額、
            # 返金手数料 r×10%×販売手数料 は売価に比例（上限500円は低単価では効かないので無視）
            ret_fixed = r * (fba + RETURN_UNSELLABLE_SHARE * fixed)
            # 枝① 料率が効く帯（売価 × 率 ≥ 最低手数料30円）
            denom = 1.0 - pct * TAX / 100.0 * (1 + r * REFUND_ADMIN_RATE) - margin
            if denom > 0:
                p = (fba + fixed + ret_fixed) / denom
                if p * pct / 100.0 >= MIN_REFERRAL_YEN_EXCL and feasible(p, low_fba, pct):
                    cands.append(p)
            # 枝② 最低販売手数料30円（税抜）が効く帯。手数料が定額なので割り算が変わる
            if 1.0 - margin > 0:
                p = (fba + fixed + ret_fixed
                     + MIN_REFERRAL_YEN_EXCL * TAX * (1 + r * REFUND_ADMIN_RATE)) / (1.0 - margin)
                if p * pct / 100.0 < MIN_REFERRAL_YEN_EXCL and feasible(p, low_fba, pct):
                    cands.append(p)
    return min(cands) if cands else None


# ── 値付けの崖（750円 / 1,000円）─────────────────────────────────────────

# 🔴 死に帯。この帯に売価があるなら、崖の下へ**下げた方が手残りが増えます**。
DEAD_BANDS: tuple[tuple[int, int, int], ...] = (
    (REFERRAL_CLIFF_YEN + 1, 900, REFERRAL_CLIFF_YEN),            # 751〜900 → 750
    (FBA_LOW_PRICE_CLIFF_YEN + 1, 1100, FBA_LOW_PRICE_CLIFF_YEN),  # 1,001〜1,100 → 1,000
)


def cliff_advice(sell: float, unit_cost_incl: float, tier: str,
                 category: str | None = None, keepa_pct: float | None = None,
                 months_to_sell: float = 3.0, peak: bool | None = None,
                 apparel: bool = False, **kw) -> str:
    """売価が死に帯にあるなら「◯円に下げると手残りが増える」を1行で返す。無ければ空文字。

    - **751〜900円**：販売手数料が 5% → 15.4% に飛ぶ（750円の崖）
    - **1,001〜1,100円**：FBA配送代行が安い列から外れる（1,000円の崖）
    """
    if not sell or sell <= 0:
        return ""
    oth = other_costs(tier, months_to_sell, peak, apparel, **kw).total
    for lo, hi, target in DEAD_BANDS:
        if lo <= sell <= hi:
            def _net(p: float) -> float:
                fee, fba = referral_yen(p, category, keepa_pct), fba_fee_yen(tier, p)
                return (p - fee - fba - unit_cost_incl - oth
                        - return_reserve_yen(fee, fba, unit_cost_incl, oth))
            now, down = _net(sell), _net(target)
            if down > now:
                why = ("販売手数料が5%→15.4%に飛ぶ帯" if target == REFERRAL_CLIFF_YEN
                       else "FBA配送代行の『1,000円以下』の列から外れる帯")
                return (f"🔴 売価{int(sell):,}円は死に帯（{why}）。**{target:,}円に下げると "
                        f"手残りが {int(round(now)):,}円 → {int(round(down)):,}円 に増えます。**")
    return ""


# ── A / B / C 等級（旧「誤差幅 売価7%＋200円」の置き換え）──────────────────

GRADE_A = "A"
GRADE_B = "B"
GRADE_C = "C"
GRADE_UNKNOWN = "UNKNOWN"

TARGET_MARGIN = 0.20          # 会社KPI（利益率20%）

# 🔴 **1個あたりの手残りの下限（円）。単価では切りません。**
# 根拠：成果物34（サトル）§1。月100万以上の実践者 N=6 は**全員が単価の下限を置いておらず**、
# 置いているのは「**1個あたり利益額 400〜1,000円**」と「利益率 5〜30%」でした。
# 当社も単価ではなく利益額で切ります（2026-10-04 社長指示「単価ではなく利益額で切る」）。
# 下端の400円を採るのは、実績ゼロの段階では母数を優先するためです（CLAUDE.md §3.1）。
#
# ⚠️ **これは単独の下限ではありません。**同じ成果物34 に出てくる「750円の崖」の実践者は
# **手残り50円**（売価750円・仕入440円）で回しています。実践者の基準は型によって割れていて、
# 片方だけを下限にすると他方の型を全部落とします。だから判定は
#   **「利益率 20% 以上」 または 「手残り 400円 以上」** の **OR** です（`grade()` の `ok()`）。
# 率の線を実践者の下端（5%）ではなく当社KPIの20%に置いているのは、**厳しい側**に寄せる
# ためです。ここを5%に緩めると候補が何件増えるかは成果物35の感度表に出します。
MIN_PROFIT_YEN = 400

# 🔴 **B 等級の利益率の下限（§3.5 #18・2026-10-11 規定に合わせて実装を直した）。**
# 旧実装は「中央値で 20% または 400円」を満たさなければ C にしていたため、
# 規定上は B（中央値で 5%以上 または 400円以上）の行を C で落としていました（§3.3-22 の型）。
#   A … 中央値でも悲観値でも〔利益率 TARGET_MARGIN 以上 または 手残り MIN_PROFIT_YEN 以上〕
#   B … 中央値で〔利益率 MIN_MARGIN_B 以上 または 手残り MIN_PROFIT_YEN 以上〕かつ A でない
#   C … 中央値でどちらも満たさない
#   推定費目があれば最高 B（天井。B の下限を下げる意味ではない）
MIN_MARGIN_B = 0.05


@dataclass
class Grade:
    """採算の等級と、その根拠（中央値と悲観値の両方）。

    - **A** … 中央でも悲観でも〔利益率20%以上 または 手残り400円以上〕→ 発注候補
    - **B** … 中央で〔利益率5%以上 または 手残り400円以上〕かつ A でない
      → **最小ロットで1回だけ実測する**（落とさない）。推定費目がある行も最高 B
    - **C** … 中央でどちらも満たさない → 落とす
    - **UNKNOWN** … 原価・サイズ区分・セット数のどれかが確定していない
      → 金額を膨らませず **計算しない**（単位ずれは「幅」ではなく「真偽」）
    """

    grade: str
    reason: str
    mid: dict = field(default_factory=dict)
    worst: dict = field(default_factory=dict)
    cliff: str = ""

    @property
    def is_candidate(self) -> bool:
        return self.grade in (GRADE_A, GRADE_B)


def _scenario(sell: float, unit_cost_incl: float, tier: str, *, worst: bool,
              category: str | None, keepa_pct: float | None,
              months_to_sell: float, peak: bool | None, apparel: bool,
              supplier_freight: float | None = None) -> dict:
    """1シナリオぶんの手残り。悲観はハジメの定義（成果物33 §6.2）に合わせます。

    悲観の当て方: サイズ区分を**1段上**／料率を**カテゴリー最高段**／保管月数を**2倍**／
    箱の入り数を**7割**／**売価を90日の下位25%**（呼び出し側が `sell` に渡す）。

    売価の悲観は 2026-10-04 に入りました（`price_history.PriceLevel.sell_pessimistic`）。
    **ここで勝手に割り引きません。**呼び出し側が履歴から出した値を渡します。
    """
    t = tier_up(tier) if worst else tier
    fr = SUPPLIER_FREIGHT_YEN if supplier_freight is None else float(supplier_freight)
    oth = other_costs(t, months_to_sell * (2.0 if worst else 1.0), peak, apparel,
                      fill_rate=FILL_RATE * (0.7 if worst else 1.0),
                      units_per_box=int(UNITS_PER_BOX * (0.7 if worst else 1.0)),
                      units_per_sku=int(UNITS_PER_SKU * (0.7 if worst else 1.0)),
                      # 悲観は送料も箱7割で割る（1回の注文の送料は同じで点数が減る）
                      supplier_freight=fr / (0.7 if worst else 1.0)).total
    fee = referral_yen(sell, category, keepa_pct, worst=worst)
    fba = fba_fee_yen(t, sell)
    # 返品の引当（2026-10-14）。悲観は返品率2倍
    ret = return_reserve_yen(fee, fba, unit_cost_incl, oth,
                             RETURN_RATE * (2.0 if worst else 1.0))
    oth += ret
    net = sell - fee - fba - unit_cost_incl - oth
    return {"サイズ区分": t, "売価": int(sell), "販売手数料": fee, "FBA配送代行": fba,
            "原価": int(round(unit_cost_incl)), "その他固定費": int(round(oth)),
            "うち返品引当": int(round(ret)),
            "手残り": int(round(net)),
            "利益率(%)": round(net / sell * 100, 1) if sell else 0.0}


def grade(sell: float | None, unit_cost_incl: float | None, tier: str | None,
          *, category: str | None = None, keepa_pct: float | None = None,
          months_to_sell: float = 3.0, peak: bool | None = None, apparel: bool = False,
          unit_decided: bool = True, note: str = "",
          sell_worst: float | None = None,
          estimated: tuple[str, ...] | list[str] = (),
          supplier_freight: float | None = None) -> Grade:
    """A / B / C / UNKNOWN を返す。**UNKNOWN を GO に畳みません。**

    `sell`        … 中央ケースの売価（**90日中央値**。現在価格ではない）
    `sell_worst`  … 悲観ケースの売価（**90日の下位25%**）。省略すると `sell` と同じ

    `estimated`   … 推定で置いた費目の名前（例：「保管月数（月販非表示で3か月を仮置き）」）。
                    1つでもあれば**最高 B**（§3.5 #18「推定費目ありで A」は落とす条件）
                    2026-10-14〜：返品引当（返品率の仮置き）と、`supplier_freight` を渡さない
                    ときの卸→代行の送料（40円/点の仮置き）は**自動で推定費目に入る**
    `supplier_freight` … 卸→代行の送料の実額（1点・円）。卸値に按分済みなら 0

    切り方（CLAUDE.md §3.5 #18。2026-10-11 に規定へ合わせて直した）
      A … 中央でも悲観でも〔利益率20%以上 **または** 手残り MIN_PROFIT_YEN 以上〕
      B … 中央で〔利益率 MIN_MARGIN_B(5%) 以上 **または** 手残り MIN_PROFIT_YEN 以上〕かつ A でない
          → **最小ロットで1回だけ実測**
      C … 中央でどちらも満たさない
    **単価では切りません**（実践者 N=6 全員が単価の下限を置いていない・成果物34）。
    """
    if not unit_decided:
        return Grade(GRADE_UNKNOWN,
                     "Amazon の1個が卸の何点かが確定していません。**単位ずれは「幅」ではなく"
                     "「真偽」です。**金額を膨らませず計算しません。人が卸サイトと Amazon の"
                     "両方の画面を見てください。" + (f" {note}" if note else ""))
    if not sell or sell <= 0 or unit_cost_incl is None or unit_cost_incl <= 0:
        return Grade(GRADE_UNKNOWN,
                     "売価か原価が取れていないので採算を計算できません。"
                     + (f" {note}" if note else ""))
    if not tier:
        return Grade(GRADE_UNKNOWN,
                     "FBA のサイズ区分が決まりません（Keepa の配送代行手数料も寸法も"
                     "取れていない）。区分で固定費が 222円〜1,756円まで動くので、"
                     "**推測で埋めません。**" + (f" {note}" if note else ""))

    kw = dict(category=category, keepa_pct=keepa_pct,
              months_to_sell=months_to_sell, peak=peak, apparel=apparel)
    mid = _scenario(sell, unit_cost_incl, tier, worst=False,
                    supplier_freight=supplier_freight, **kw)
    # 悲観は**売価も下げる**（90日の下位25%）。費目だけ悲観にしても売価が中央のままだと、
    # 「価格が下がったときに赤字になる棚」を A に通してしまいます（2026-10-04 の差し戻し）。
    bad = _scenario(sell_worst if sell_worst else sell, unit_cost_incl, tier,
                    worst=True, supplier_freight=supplier_freight, **kw)
    adv = cliff_advice(sell, unit_cost_incl, tier, category=category,
                       keepa_pct=keepa_pct, months_to_sell=months_to_sell,
                       peak=peak, apparel=apparel)

    def ok_a(sc: dict) -> bool:
        """A の線。**率と額のどちらかを満たせばよい。**"""
        return (sc["利益率(%)"] >= TARGET_MARGIN * 100
                or sc["手残り"] >= MIN_PROFIT_YEN)

    def ok_b(sc: dict) -> bool:
        """B の線（中央値だけに当てる）。率は5%、額は A と同じ400円。"""
        return (sc["利益率(%)"] >= MIN_MARGIN_B * 100
                or sc["手残り"] >= MIN_PROFIT_YEN)

    est = [x for x in (estimated or ()) if x]
    # 2026-10-14：仮置きの費目は自動で推定費目に入れる（§3.5 #18「推定費目があれば最高 B」）
    if supplier_freight is None and SUPPLIER_FREIGHT_YEN > 0:
        est.append(est_freight_label())
    if RETURN_RATE > 0:
        est.append(EST_RETURN)
    if not ok_b(mid):
        need = required_sell(unit_cost_incl, tier, MIN_MARGIN_B,
                             supplier_freight=supplier_freight, **kw) or 0
        g, why = GRADE_C, (
            f"中央値（売価 {mid['売価']:,}円）で手残り {mid['手残り']:,}円・"
            f"{mid['利益率(%)']}% です。利益率{MIN_MARGIN_B * 100:g}%にも手残り "
            f"{MIN_PROFIT_YEN}円にも届きません（§3.5 #18 の C）。"
            f"利益率{MIN_MARGIN_B * 100:g}%に必要な売価は {int(round(need)):,}円 です。")
    elif ok_a(mid) and ok_a(bad) and not est:
        g, why = GRADE_A, (
            f"中央（売価 {mid['売価']:,}円）で手残り {mid['手残り']:,}円・{mid['利益率(%)']}%、"
            f"悲観（売価 {bad['売価']:,}円・区分1段上 {bad['サイズ区分']}・料率15.4%・"
            f"保管2倍・箱7割）でも {bad['手残り']:,}円・{bad['利益率(%)']}% あります。")
    else:
        if not ok_a(mid):
            head = (f"中央（売価 {mid['売価']:,}円）で手残り {mid['手残り']:,}円・"
                    f"{mid['利益率(%)']}% ＝ B の線（5%以上 または 400円以上）は越えるが、"
                    f"A の線（20%以上 または 400円以上）には届きません。")
        elif not ok_a(bad):
            head = (f"中央（売価 {mid['売価']:,}円）で手残り {mid['手残り']:,}円・"
                    f"{mid['利益率(%)']}% ですが、悲観（売価 {bad['売価']:,}円）では "
                    f"{bad['手残り']:,}円・{bad['利益率(%)']}% に落ちます。")
        else:
            head = (f"数字は A の線を越えています（中央 {mid['手残り']:,}円・"
                    f"{mid['利益率(%)']}%／悲観 {bad['手残り']:,}円・{bad['利益率(%)']}%）。")
        if est:
            head += f" 推定費目（{'・'.join(est)}）があるので**最高 B**です（§3.5 #18）。"
        g, why = GRADE_B, head + "**最小ロットで1回だけ実測してください**（落としません）。"
    if note:
        why = f"{why} {note}"
    return Grade(g, why, mid, bad, adv)


# ── セット組（まとめ売り）の向き ─────────────────────────────────────────


def bundle_advice(tier: str, sell_per_point: float, unit_cost_incl_per_point: float,
                  ns: tuple[int, ...] = (1, 2, 3, 5, 10),
                  category: str | None = None, keepa_pct: float | None = None,
                  months_to_sell: float = 3.0) -> tuple[int, str]:
    """**「この商品はセットにすべきか」を体積から決める。**

    🔴 旧モデルの「低単価だからセット組」は誤りでした。正しくは「**体積が大きいから
    セット組**」です。固定費のうち n で割れるのは **FBA配送代行と外注費だけ**で、
    保管料・納品送料・梱包資材は体積比例なので n 倍になります。さらに：

    - 小型で**すでに750円以下**の商品をセットにすると、売価が750円を超えて販売手数料が
      **5% → 15.4%** に跳ねます。固定費/個も 291円 → 339円に**悪化**します
    - 逆に標準5以上の大物は、FBA配送代行が1個につき1回なので n で割る効果が大きい

    戻り値は `(推奨するセット数, 理由)`。1 なら「単品のまま」。
    """
    best_n, best_per = 1, None
    rows: list[tuple[int, float]] = []
    for n in ns:
        n = max(1, int(n))
        # セットにすると体積が n 倍 → 区分も上がる（代表体積から当て直す）
        vol = VOL[tier] * n
        t = tier_from_volume(vol)
        need = required_sell(unit_cost_incl_per_point * n, t, 0.0, category=category,
                             keepa_pct=keepa_pct, months_to_sell=months_to_sell,
                             volume_cm3=vol)
        if need is None:
            continue
        per = need / n
        rows.append((n, per))
        if best_per is None or per < best_per - 1e-6:
            best_n, best_per = n, per

    if not rows:
        return (1, "必要売価が解けませんでした（単品のままにしてください）。")
    single = dict(rows).get(1)
    if best_n == 1:
        return (1, f"単品のままが有利です（1点あたりの必要売価 {int(round(single or 0)):,}円）。"
                   "体積が小さい商品をセットにすると、750円の崖で販売手数料が5%→15.4%に"
                   "跳ね、保管・納品送料・資材も体積ぶん増えます。")
    gain = (single - best_per) if single else 0.0
    warn = ""
    if sell_per_point and sell_per_point <= REFERRAL_CLIFF_YEN and best_n > 1:
        warn = ("⚠️ ただし単品の売価が750円以下なので、セットにすると販売手数料が "
                "5%→15.4% に跳ねます。崖を超える価値があるか実額で確認してください。")
    return (best_n, f"{best_n}個セットが有利です（1点あたりの必要売価 "
                    f"{int(round(single or 0)):,}円 → {int(round(best_per)):,}円・"
                    f"{int(round(gain)):,}円改善）。体積が大きいほど効きます。{warn}")
