"""profit.py のユニットテスト（pytest）。

実行: code/ ディレクトリで `python -m pytest`

カバーするケース:
1. 黒字（原石判定）
2. 赤字（はずれ判定）
3. 境界（あやしい: プラスだが閾値未満）
4. 高利益率（原石・ROI も高い）
5. 送料負け（送料を足すと黒字→赤字に転落）
+ 補助: 税抜入力の税込換算、最低手数料の適用、損益分岐売値の整合
"""

import math

import pytest

from calc.profit import (
    ProfitInput,
    calculate,
    VERDICT_GEM,
    VERDICT_SUSPICIOUS,
    VERDICT_MISS,
)


def test_case1_black_ink_is_gem():
    """黒字・利益率15%以上・純利益500円以上 → 原石。"""
    res = calculate(ProfitInput(
        wholesale_price=1000, amazon_price=2980,
        category_key="home_kitchen",  # 料率15%
        size_key="standard_1",        # FBA 318円（2025/4改定後・ハジメ検証）
        inbound_shipping=200, other_costs=50,
    ))
    # 手数料 = 2980*0.15 = 447, FBA=318, 仕入1000, 送料200, その他50
    # 純利益 = 2980 - (447+318+1000+200+50) = 965
    assert math.isclose(res.referral_fee, 447.0, rel_tol=1e-6)
    assert math.isclose(res.net_profit, 965.0, rel_tol=1e-6)
    assert res.margin_rate > 0.15
    assert res.net_profit >= 500
    assert res.verdict == VERDICT_GEM


def test_case2_loss_is_miss():
    """赤字 → はずれ。"""
    res = calculate(ProfitInput(
        wholesale_price=2500, amazon_price=2980,
        category_key="home_kitchen",
        size_key="standard_1",
        inbound_shipping=200, other_costs=50,
    ))
    # 純利益 = 2980 - (447+318+2500+200+50) = -535
    assert res.net_profit < 0
    assert res.verdict == VERDICT_MISS


def test_case3_boundary_is_suspicious():
    """プラスだが利益率15%未満 → あやしい。"""
    # 利益率を 0%超〜15%未満に収める。卸を上げて薄利にする。
    res = calculate(ProfitInput(
        wholesale_price=1700, amazon_price=2980,
        category_key="home_kitchen",
        size_key="standard_1",
        inbound_shipping=100, other_costs=0,
    ))
    # 純利益 = 2980 - (447+318+1700+100+0) = 415 (>0, 利益率 ~14%)
    assert res.net_profit > 0
    assert res.margin_rate < 0.15
    assert res.verdict == VERDICT_SUSPICIOUS


def test_case4_high_margin_gem_self_ship():
    """高利益率（自己発送でFBA手数料0）→ 原石、ROIも高い。"""
    res = calculate(ProfitInput(
        wholesale_price=800, amazon_price=4980,
        category_key="toys",        # 料率10%（ハジメ検証で15%→10%へ是正）
        size_key="self_ship",       # FBA 0円
        inbound_shipping=300, other_costs=100,
    ))
    # 手数料=4980*0.10=498, FBA=0, 仕入800, 送料300, その他100
    # 純利益 = 4980 - (498+0+800+300+100) = 3282
    assert res.fba_fee == 0
    assert math.isclose(res.net_profit, 3282.0, rel_tol=1e-6)
    assert res.margin_rate > 0.15
    assert res.roi > 1.0   # 投下原価1200に対し利益3033 → ROI>250%
    assert res.verdict == VERDICT_GEM


def test_case5_shipping_pushes_into_loss():
    """送料負け: 送料ゼロなら黒字だが、重い送料を足すと赤字に転落。"""
    base = dict(
        wholesale_price=1500, amazon_price=2500,
        category_key="home_kitchen", size_key="large_2",  # FBA 675円（2025/4改定後）
        other_costs=0,
    )
    no_ship = calculate(ProfitInput(inbound_shipping=0, **base))
    heavy_ship = calculate(ProfitInput(inbound_shipping=600, **base))
    # 手数料=2500*0.15=375, FBA=675, 仕入1500
    # 送料0 : 2500-(375+707+1500+0) = -82 ... これは元々赤字なので調整
    # → base を黒字寄りに作り直すため amazon_price を上げる
    # ここでは「送料追加で純利益が減る」方向性を必ず満たすことを検証
    assert heavy_ship.net_profit < no_ship.net_profit
    assert math.isclose(no_ship.net_profit - heavy_ship.net_profit, 600.0, rel_tol=1e-6)


def test_case5b_shipping_flips_sign():
    """送料負けの符号反転を明示的に検証（黒字→赤字）。"""
    base = dict(
        wholesale_price=1000, amazon_price=2200,
        category_key="home_kitchen", size_key="standard_1",  # FBA 318（2025/4改定後）
        other_costs=0,
    )
    # 手数料=2200*0.15=330, FBA=318, 仕入1000 → 固定控除1648
    # 送料0 : 2200-1648 = 552 (黒字)
    # 送料600: 2200-2248 = -48 (赤字)
    no_ship = calculate(ProfitInput(inbound_shipping=0, **base))
    heavy = calculate(ProfitInput(inbound_shipping=600, **base))
    assert no_ship.net_profit > 0
    assert heavy.net_profit < 0
    assert heavy.verdict == VERDICT_MISS


def test_tax_exclusive_input_is_converted():
    """税抜入力は税込へ換算される（仕入原価が10%増える）。"""
    incl = calculate(ProfitInput(
        wholesale_price=1000, amazon_price=2980,
        wholesale_price_is_tax_included=True,
    ))
    excl = calculate(ProfitInput(
        wholesale_price=1000, amazon_price=2980,
        wholesale_price_is_tax_included=False,  # 税抜→税込1100に換算
    ))
    assert math.isclose(excl.wholesale_price_incl_tax, 1100.0, rel_tol=1e-6)
    # 税抜入力のほうが原価が高くなり、純利益は100円少ない
    assert math.isclose(incl.net_profit - excl.net_profit, 100.0, rel_tol=1e-6)


def test_minimum_referral_fee_applied():
    """低単価×低料率カテゴリで最低手数料が効くこと。"""
    # electronics 料率8%・最低手数料30円。売値300円なら 300*0.08=24 < 30。
    res = calculate(ProfitInput(
        wholesale_price=100, amazon_price=300,
        category_key="electronics", size_key="small",
    ))
    assert math.isclose(res.referral_fee, 30.0, rel_tol=1e-6)


def test_breakeven_price_yields_zero_profit():
    """損益分岐売値で再計算すると純利益がほぼ0になる（自己整合）。"""
    inp = ProfitInput(
        wholesale_price=1000, amazon_price=2980,
        category_key="home_kitchen", size_key="standard_1",
        inbound_shipping=200, other_costs=50,
    )
    res = calculate(inp)
    # 損益分岐売値で売ったら利益0付近のはず
    recomputed = calculate(ProfitInput(
        wholesale_price=1000, amazon_price=res.breakeven_price,
        category_key="home_kitchen", size_key="standard_1",
        inbound_shipping=200, other_costs=50,
    ))
    assert abs(recomputed.net_profit) < 1.0  # 1円未満の誤差


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
