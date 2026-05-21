"""
利益計算ロジックのユニットテスト
- 物販ナレッジ１ Part3 の例を再現
- MSS で大型商品が黒字化するパターンを検証
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.calc.profit import calc_profit, calc_all, best_mode, ProfitInput
from app.calc.score import calc_score, judge


def test_fba_basic():
    """物販ナレッジ１ Part3 の例: 売値5,000 / 仕入3,000 / 販売手数料10% / FBA手数料1,000 → 利益500"""
    p = ProfitInput(sell_price=5000, cost=3000, category_fee_rate=0.10, fba_fee=1000)
    r = calc_profit(p, "fba")
    assert r.profit == 500
    assert r.rate == 10.0


def test_self_mss_better_than_fba_for_large_item():
    """大型商品では MSS の方が FBA より得になる(朝野コンサルの核心)"""
    p = ProfitInput(sell_price=6980, cost=3500, fba_fee=462, mss_ship_cost=132)
    r_fba = calc_profit(p, "fba")
    r_mss = calc_profit(p, "self_mss")
    assert r_mss.profit > r_fba.profit, "MSS の方が FBA より利益が大きいはず"


def test_all_three_modes_present():
    """3パターン全部計算される"""
    p = ProfitInput(sell_price=6980, cost=3500)
    results = calc_all(p)
    assert "fba" in results
    assert "self" in results
    assert "self_mss" in results


def test_best_mode_picks_max():
    """best_mode は利益最大のモードを返す"""
    p = ProfitInput(sell_price=6980, cost=3500)
    best = best_mode(p)
    assert best.mode == "self_mss"  # 通常 MSS が最大


def test_score_range():
    """スコアは 0〜100 の範囲"""
    s = calc_score(profit=2000, rate=20.0, monthly_sales=50, drop_30=25)
    assert 0 <= s <= 100


def test_judge_green():
    """🟢原石の判定条件"""
    j = judge(profit=2000, rate=20.0, monthly_sales=10, drop_30=15)
    assert j == "green"


def test_judge_yellow():
    """🟡要検討の判定条件"""
    j = judge(profit=500, rate=8.0, monthly_sales=3, drop_30=5)
    assert j == "yellow"


def test_judge_red():
    """🔴除外の判定条件"""
    j = judge(profit=-100, rate=-2.0, monthly_sales=2, drop_30=1)
    assert j == "red"
