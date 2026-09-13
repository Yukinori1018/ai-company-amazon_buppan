#!/usr/bin/env python3
"""1出品ぶんの利益を 2026 年の手数料体系で引く純関数 — T-20260914-001。

UI や集計からは切り離してあります（テスト可能・1円もごまかさない）。
料率・FBA 配送代行・保管料の**数値は持ちません**。すべて
`T-20260521-005/code/calc/fees.py`（経理ハジメ 2026-08-24 更新・2026-04 改定反映）から取ります。

引き算の順（`breakdown()` の返り値の順と同じ）:

    売価
    − 卸値（税込・1出品ぶん＝NETSEA 単価 × 入数 × 1.1）
    − 販売手数料（カテゴリ料率 × 売価。750円超は +0.4pt 込みの料率。請求は消費税 ×1.1）
    − FBA 配送代行（サイズ区分の固定額。1,000円超の列）
    − 保管料（体積 × 繁忙期レート × 1.5ヶ月）
    − 納品（納品代行 12円/点 ＋ FBA 納品送料 37.5円/点）
    − 資材（セット・N個パックの外装。単品は 0）
    − 返品引当（3% × (FBA配送代行 ＋ 返金処理手数料 ＋ 卸値×50%)）
    − 広告（売価 × 広告率。PDF G3 は 10%）
    ＝ 純利益

大口プラン前提なので**基本成約料は 0**（2026-09-12 に日本は大口へ切替済み）。

⚠️ 推定が入るのは 保管月数(1.5)・納品(49.5円)・資材・返品率(3%)・広告率 の5つ。
   卸値と売価は実額です。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260521-005/code"))
from calc import fees  # noqa: E402

# ── 前提の定数（すべて推定。出所を横に書く）──────────────────────────────
PREP_SERVICE_YEN = 12.0        # 納品代行の作業費（e-fba 公開料金・T-20260904-004 C1）
FBA_INBOUND_YEN = 37.5         # 納品代行 → FBA 750円/箱 ÷ 20点（同上）
STORAGE_MONTHS = 1.5           # 3ヶ月で線形に売り切る＝平均在庫は半分（T-20260831-006 config）
STORAGE_PEAK = True            # 保管が 10〜12月に重なる前提で繁忙期レート（保守側）
RETURN_RATE = 0.03             # 自社実績ゼロ。初回販売後に置き換える
RETURN_UNSELLABLE = 0.50       # 返品の半分は再販不可という仮定
REFUND_ADMIN_CAP = 500.0
REFUND_ADMIN_RATE = 0.10
REFERRAL_TAX = 0.10            # 販売手数料は税抜表示・請求は ×1.1（ハジメ実測 2026-09-04）
CLOSING_FEE_YEN = 0.0          # 大口。小口なら 110
BUNDLE_MATERIAL_YEN = 30.0     # セット/N個パックの外装（OPP袋・帯・ラベル）。推測
AD_RATE_PDF = 0.10             # PDF G3「広告費10%込み」

# FBA サイズ区分の目安（T-20260831-006/pipeline/keepa_verify.py と同じ規則）
FBA_STD_DIMS_MM = (450, 350, 200)
FBA_STD_WEIGHT_G = 9000


def fba_size_key(package_mm: list, package_g: float | None) -> tuple[str, str]:
    """寸法(mm)と重量(g) → (fees の size_key, 表示)。不明は standard_2 で仮置きし「不明」と書く。"""
    dims = sorted(package_mm or [], reverse=True)
    g = package_g
    if len(dims) < 3 and g is None:
        return "standard_2", "不明(標準2で仮置き)"
    if len(dims) == 3 and any(d > lim for d, lim in zip(dims, FBA_STD_DIMS_MM)):
        return "large_1", "大型"
    if g is not None and g > FBA_STD_WEIGHT_G:
        return "large_1", "大型"
    if g is None:
        return "standard_2", "不明(重量なし・標準2で仮置き)"
    if g <= 250 and (not dims or dims[0] <= 250):
        return "small", "小型"
    if g <= 1000:
        return "standard_1", "標準1"
    if g <= 2000:
        return "standard_2", "標準2"
    return "standard_3", "標準3"


def combine_packages(items: list[tuple[list, float | None]]) -> tuple[list, float | None]:
    """複数点を1梱包にしたときの寸法・重量（推測）。

    最長辺・第2辺は最大値、最短辺は合計（平積み）。重量は合計。
    どれか1点でも寸法が無ければ寸法は不明のまま返す（推測で埋めない）。
    """
    dims_list = [sorted(d, reverse=True) for d, _ in items if len(d or []) == 3]
    if len(dims_list) != len(items):
        dims = []
    else:
        dims = [max(d[0] for d in dims_list), max(d[1] for d in dims_list),
                sum(d[2] for d in dims_list)]
    gs = [g for _, g in items]
    g = sum(gs) if all(x is not None for x in gs) else None
    return dims, g


@dataclass
class Line:
    label: str
    yen: float
    why: str


@dataclass
class Profit:
    price: float
    lines: list[Line] = field(default_factory=list)
    net: float = 0.0
    margin: float = 0.0
    fba_fee: float = 0.0
    referral_fee: float = 0.0
    ad: float = 0.0
    size_label: str = ""
    category_key: str = ""

    def as_row(self) -> dict:
        d = {"売価": round(self.price)}
        for ln in self.lines:
            d[ln.label] = round(ln.yen, 1)
        d["純利益"] = round(self.net)
        d["利益率%"] = round(self.margin * 100, 1)
        return d


def breakdown(*, price: float, wholesale_incl: float, category_key: str,
              package_mm: list, package_g: float | None,
              n_units: int = 1, ad_rate: float = AD_RATE_PDF,
              material_yen: float = 0.0) -> Profit:
    """1出品ぶんの引き算。n_units は納品作業費を何点ぶん掛けるか（セット構成点数）。"""
    p = Profit(price=price, category_key=category_key)
    cfg = fees.get_referral_rate(category_key, price=price)
    referral = max(price * cfg["rate"], cfg["min_fee_yen"]) * (1 + REFERRAL_TAX)
    size_key, size_label = fba_size_key(package_mm, package_g)
    fba = fees.get_fba_fee(size_key)["fba_fee_yen"]
    vol = 0.0
    if len(package_mm or []) == 3:
        vol = (package_mm[0] / 10) * (package_mm[1] / 10) * (package_mm[2] / 10)
    storage = fees.get_storage_fee_yen(
        vol, STORAGE_MONTHS,
        size_class="large" if size_key.startswith("large") else "standard",
        peak_season=STORAGE_PEAK) if vol else 0.0
    inbound = (PREP_SERVICE_YEN + FBA_INBOUND_YEN) * max(n_units, 1) if n_units > 1 \
        else PREP_SERVICE_YEN + FBA_INBOUND_YEN
    refund_admin = min(REFUND_ADMIN_CAP, referral * REFUND_ADMIN_RATE)
    ret = RETURN_RATE * (fba + refund_admin + wholesale_incl * RETURN_UNSELLABLE)
    ad = price * ad_rate

    p.lines = [
        Line("卸値(税込・1出品)", wholesale_incl, "NETSEA 税抜単価 × 入数 × 1.1"),
        Line("販売手数料", referral,
             f"{cfg['label']} {cfg['rate']*100:.1f}% × 売価 × 1.1（消費税）"),
        Line("FBA配送代行", fba, f"{size_label}（1,000円超の列）"),
        Line("保管料", storage, f"体積{vol/1000:.2f}L × 繁忙期 × {STORAGE_MONTHS}ヶ月" if vol else "寸法なし・未計上"),
        Line("納品", inbound, f"納品代行{PREP_SERVICE_YEN:.0f}円＋FBA納品送料{FBA_INBOUND_YEN}円 × {max(n_units,1)}点"),
        Line("資材", material_yen, "セット/パック外装（推測）" if material_yen else "単品は 0"),
        Line("返品引当", ret, f"{RETURN_RATE*100:.0f}% × (FBA＋返金処理＋卸値×{RETURN_UNSELLABLE*100:.0f}%)"),
        Line("基本成約料", CLOSING_FEE_YEN, "大口＝0"),
        Line("広告", ad, f"売価 × {ad_rate*100:.0f}%"),
    ]
    p.net = price - sum(ln.yen for ln in p.lines)
    p.margin = p.net / price if price else 0.0
    p.fba_fee, p.referral_fee, p.ad, p.size_label = fba, referral, ad, size_label
    return p


def passes_g3(p: Profit, *, min_net: float = 500, min_margin: float = 0.20,
              fba_share_cap: float = 0.25) -> tuple[bool, bool]:
    """PDF G3。返り値 (利益額・利益率を満たす, さらに FBA配送代行 ≤ 利益×25% も満たす)。"""
    a = p.net >= min_net and p.margin >= min_margin
    b = a and (p.net > 0 and p.fba_fee <= fba_share_cap * p.net)
    return a, b
