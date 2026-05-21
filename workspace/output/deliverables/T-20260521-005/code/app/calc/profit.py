"""
Sato-Scope 真の利益計算ロジック
- FBA、自己発送（通常宅配）、自己発送（マーケットプレイス配送サービス = MSS）の3パターン
- 物販ナレッジ１ Part3「FBA vs 自己発送 — 送料負けの真実」を実装
"""
from dataclasses import dataclass, asdict
from typing import Literal

ShipMode = Literal["fba", "self", "self_mss"]


@dataclass
class ProfitInput:
    """利益計算の入力"""
    sell_price: int                    # Amazon売値 (円)
    cost: int                          # 仕入れ値 (円・ポイント考慮前)
    category_fee_rate: float = 0.10    # Amazon販売手数料率 (カテゴリ別、デフォルト10%)
    fba_fee: int = 462                 # FBA配送代行手数料 (A4サイズ目安)
    self_ship_cost: int = 600          # 自己発送・通常宅配便送料
    mss_ship_cost: int = 132           # MSS マケプレ配送サービス特別運賃 (ヤマト提携)
    other_costs: int = 0               # 梱包材・人件費等


@dataclass
class ProfitResult:
    """利益計算の出力"""
    mode: ShipMode
    profit: int                        # 利益額 (円)
    rate: float                        # 利益率 (%)
    breakdown: dict                    # 計算明細


def calc_profit(p: ProfitInput, mode: ShipMode) -> ProfitResult:
    """指定モードで利益計算"""
    sell = p.sell_price
    cat_fee = round(sell * p.category_fee_rate)

    if mode == "fba":
        ship = p.fba_fee
    elif mode == "self":
        ship = p.self_ship_cost
    elif mode == "self_mss":
        ship = p.mss_ship_cost
    else:
        raise ValueError(f"unknown ship mode: {mode}")

    profit = sell - p.cost - cat_fee - ship - p.other_costs
    rate = round(profit / sell * 100, 1) if sell > 0 else 0.0

    return ProfitResult(
        mode=mode,
        profit=profit,
        rate=rate,
        breakdown={
            "sell_price": sell,
            "cost": -p.cost,
            "category_fee": -cat_fee,
            "ship": -ship,
            "other_costs": -p.other_costs,
        },
    )


def calc_all(p: ProfitInput) -> dict[str, ProfitResult]:
    """3パターン全部計算"""
    return {
        "fba": calc_profit(p, "fba"),
        "self": calc_profit(p, "self"),
        "self_mss": calc_profit(p, "self_mss"),
    }


def best_mode(p: ProfitInput) -> ProfitResult:
    """利益が最大になるモードを返す"""
    results = calc_all(p)
    return max(results.values(), key=lambda r: r.profit)
