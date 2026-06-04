"""利益計算エンジン（UIから完全分離・テスト可能な純ロジック層）。

タカシの設計方針:
- ここには「数値（料率・送料）」を一切ハードコードしない。すべて fees.py から取る。
- UI（Streamlit）にもフレームワークにも依存しない。dataclass と関数だけ。
- 「データは正直であれ」—— 1円もごまかさず、丸めは最終表示の直前まで行わない。

────────────────────────────────────────────────────────────
消費税の扱い（重要・経理確認ポイント）
────────────────────────────────────────────────────────────
- 仕入原価: 卸価格は「税込原価」で扱う。税抜で渡された場合は税込へ換算する
  （wholesale_price_is_tax_included=False のとき CONSUMPTION_TAX_RATE で換算）。
- Amazon 販売手数料: Amazon は「税込売値」を基準に料率を掛ける。本モジュールも
  税込売値ベースで手数料を算定する。
- FBA 手数料: fees.py の固定額（税込相当）をそのまま使う。
- 本モジュールは「キャッシュベースの手取り利益」を出す簡易版で、
  仕入時に払った消費税の仕入税額控除（インボイス）は考慮しない。
  → 課税事業者/免税事業者で実質利益が変わる点は経理ハジメの領域（YAGNIで未実装）。
"""

from dataclasses import dataclass, field
from typing import Optional

from . import fees


# =============================================================================
# 判定閾値（定数で調整可能に）
# =============================================================================
# ⚠️ 経理ハジメ/社長の感覚で調整するパラメータ。コードを触らず変えられるよう定数化。
THRESHOLD_MARGIN_RATE = 0.15   # 「原石」に必要な最低利益率（15%）
THRESHOLD_NET_PROFIT_YEN = 500  # 「原石」に必要な最低純利益額（円）


# 判定ラベル（社長UIの表記とテストで共有）
VERDICT_GEM = "原石"        # 利益率15%以上 かつ 純利益500円以上
VERDICT_SUSPICIOUS = "あやしい"  # プラスだが閾値未満
VERDICT_MISS = "はずれ"      # 赤字（純利益0以下）


@dataclass
class ProfitInput:
    """利益計算の入力。UIから渡される生データをそのまま受ける。"""

    wholesale_price: float           # 卸仕入価格（税込 or 税抜は次フラグで指定）
    amazon_price: float              # Amazon 売値（税込）
    category_key: str = "default"    # fees.REFERRAL_FEE_TABLE のキー
    size_key: str = "standard_1"     # fees.FBA_FEE_TABLE のキー
    inbound_shipping: float = 0.0    # 仕入送料（卸→自分 or FBA倉庫への送料の按分）
    other_costs: float = 0.0         # その他経費（梱包資材・ラベル・返品引当など）
    wholesale_price_is_tax_included: bool = True  # 卸価格が税込か
    tax_rate: float = fees.CONSUMPTION_TAX_RATE   # 税抜→税込換算に使う税率

    # 閾値はインスタンス単位でも上書き可能（A/Bテストや社長の気分調整用）
    threshold_margin_rate: float = THRESHOLD_MARGIN_RATE
    threshold_net_profit_yen: float = THRESHOLD_NET_PROFIT_YEN


@dataclass
class ProfitResult:
    """利益計算の出力。表示・テストの両方が参照する。"""

    # 入力の正規化値
    wholesale_price_incl_tax: float
    amazon_price: float

    # コスト内訳
    referral_fee: float       # Amazon 販売手数料
    fba_fee: float            # FBA 配送代行手数料
    inbound_shipping: float
    other_costs: float
    total_cost: float         # 仕入総原価（純利益を引く前の全コスト合計）

    # 結果指標
    net_profit: float         # 純利益（円）
    margin_rate: float        # 利益率 = 純利益 / 売値
    roi: float                # ROI = 純利益 / 仕入総原価
    breakeven_price: float    # 損益分岐売値（この売値なら純利益=0）

    # 判定
    verdict: str              # 原石 / あやしい / はずれ

    # 監査用メタ
    category_label: str = ""
    size_label: str = ""
    referral_rate: float = 0.0
    notes: list = field(default_factory=list)


def _to_tax_included(price: float, is_included: bool, tax_rate: float) -> float:
    """税抜価格なら税込へ換算。税込ならそのまま。"""
    if is_included:
        return price
    return price * (1.0 + tax_rate)


def _referral_fee(amazon_price: float, category_key: str) -> tuple:
    """Amazon 販売手数料を算定。最低手数料を下回る場合は最低手数料を採用。

    返り値: (手数料額, 料率, カテゴリ表示名)
    """
    cfg = fees.get_referral_rate(category_key)
    raw = amazon_price * cfg["rate"]
    fee = max(raw, cfg["min_fee_yen"])
    return fee, cfg["rate"], cfg["label"]


def calculate(data: ProfitInput) -> ProfitResult:
    """利益計算の本体。ProfitInput を受けて ProfitResult を返す純関数。"""
    notes = []

    # 1. 仕入原価を税込へ正規化
    wholesale_incl = _to_tax_included(
        data.wholesale_price,
        data.wholesale_price_is_tax_included,
        data.tax_rate,
    )
    if not data.wholesale_price_is_tax_included:
        notes.append(
            f"卸価格を税抜{data.wholesale_price:.0f}円→税込{wholesale_incl:.0f}円に換算"
            f"（税率{data.tax_rate*100:.0f}%）"
        )

    # 2. Amazon 販売手数料（税込売値ベース）
    referral_fee, referral_rate, category_label = _referral_fee(
        data.amazon_price, data.category_key
    )
    cfg = fees.get_referral_rate(data.category_key)
    if referral_fee == cfg["min_fee_yen"] and cfg["min_fee_yen"] > 0:
        notes.append(f"最低手数料{cfg['min_fee_yen']:.0f}円が適用されました")

    # 3. FBA 手数料（サイズ区分別固定額）
    fba_cfg = fees.get_fba_fee(data.size_key)
    fba_fee = fba_cfg["fba_fee_yen"]
    size_label = fba_cfg["label"]

    # 4. 純利益 = 売値 − (販売手数料 + FBA手数料 + 仕入税込原価 + 仕入送料 + その他経費)
    total_cost = (
        referral_fee
        + fba_fee
        + wholesale_incl
        + data.inbound_shipping
        + data.other_costs
    )
    net_profit = data.amazon_price - total_cost

    # 5. 利益率・ROI
    margin_rate = net_profit / data.amazon_price if data.amazon_price > 0 else 0.0
    # ROI の分母は「自分が実際に投じた仕入原価」（仕入＋送料＋その他経費）。
    # Amazon 手数料は売れて初めて発生する控除なので投下原価には含めない。
    invested_cost = wholesale_incl + data.inbound_shipping + data.other_costs
    roi = net_profit / invested_cost if invested_cost > 0 else 0.0

    # 6. 損益分岐売値: 売値を p としたとき、p − (p*rate以上の手数料 + 固定費) = 0
    #    固定費 = FBA + 仕入税込原価 + 仕入送料 + その他経費
    #    p − max(p*rate, min_fee) − 固定費 = 0
    #    最低手数料が効かない通常域では p*(1-rate) = 固定費 → p = 固定費/(1-rate)
    fixed_cost = fba_fee + wholesale_incl + data.inbound_shipping + data.other_costs
    if referral_rate < 1.0:
        breakeven_price = fixed_cost / (1.0 - referral_rate)
    else:
        breakeven_price = float("inf")
    # 最低手数料が分岐点で支配的になるケースの補正（簡易: 最低手数料採用域なら加算）
    if breakeven_price * referral_rate < cfg["min_fee_yen"]:
        breakeven_price = fixed_cost + cfg["min_fee_yen"]

    # 7. 判定
    verdict = _verdict(net_profit, margin_rate, data)

    return ProfitResult(
        wholesale_price_incl_tax=wholesale_incl,
        amazon_price=data.amazon_price,
        referral_fee=referral_fee,
        fba_fee=fba_fee,
        inbound_shipping=data.inbound_shipping,
        other_costs=data.other_costs,
        total_cost=total_cost,
        net_profit=net_profit,
        margin_rate=margin_rate,
        roi=roi,
        breakeven_price=breakeven_price,
        verdict=verdict,
        category_label=category_label,
        size_label=size_label,
        referral_rate=referral_rate,
        notes=notes,
    )


def _verdict(net_profit: float, margin_rate: float, data: ProfitInput) -> str:
    """判定フラグを返す。閾値は ProfitInput 側で上書き可能。"""
    if net_profit <= 0:
        return VERDICT_MISS
    if (
        margin_rate >= data.threshold_margin_rate
        and net_profit >= data.threshold_net_profit_yen
    ):
        return VERDICT_GEM
    return VERDICT_SUSPICIOUS


def format_result_lines(result: ProfitResult) -> list:
    """CLI / ログ用に結果を整形した文字列リストを返す（表示の都合はここに閉じる）。"""
    return [
        f"判定        : {result.verdict}",
        f"純利益      : {result.net_profit:,.0f} 円",
        f"利益率      : {result.margin_rate*100:,.1f} %",
        f"ROI         : {result.roi*100:,.1f} %",
        f"損益分岐売値: {result.breakeven_price:,.0f} 円",
        "── 内訳 ──",
        f"  Amazon売値    : {result.amazon_price:,.0f} 円",
        f"  販売手数料    : -{result.referral_fee:,.0f} 円"
        f"（{result.category_label} 料率{result.referral_rate*100:.0f}%）",
        f"  FBA手数料     : -{result.fba_fee:,.0f} 円（{result.size_label}）",
        f"  仕入(税込)    : -{result.wholesale_price_incl_tax:,.0f} 円",
        f"  仕入送料      : -{result.inbound_shipping:,.0f} 円",
        f"  その他経費    : -{result.other_costs:,.0f} 円",
    ]


# =============================================================================
# 直接実行: サンプル計算のデモ（python -m calc.profit）
# =============================================================================
if __name__ == "__main__":
    samples = [
        ("黒字の代表例: 卸1,000円→Amazon2,980円(ホーム&キッチン/標準1/送料200)",
         ProfitInput(
             wholesale_price=1000, amazon_price=2980,
             category_key="home_kitchen", size_key="standard_1",
             inbound_shipping=200, other_costs=50,
         )),
        ("赤字の代表例: 卸2,500円→Amazon2,980円(同条件)",
         ProfitInput(
             wholesale_price=2500, amazon_price=2980,
             category_key="home_kitchen", size_key="standard_1",
             inbound_shipping=200, other_costs=50,
         )),
    ]
    for title, inp in samples:
        print("=" * 60)
        print(title)
        print("-" * 60)
        res = calculate(inp)
        for line in format_result_lines(res):
            print(line)
        print()
