"""PoiPoi 寄せ改修のテスト（差分1: PoiPoi標準プリセット / 差分4: 最悪相場シミュレーション）。"""

from adapters.amazon_data import AmazonProduct
from calc import profit
from discovery import pipeline
from discovery.presets import get_finder_preset


# ---------------------------------------------------------------------------
# 差分1: PoiPoi標準 FinderPreset と to_selection
# ---------------------------------------------------------------------------
def test_poipoi_preset_exists_and_matches_video_criteria():
    fp = get_finder_preset("finder_poipoi_standard")
    # 資料の Phase1 基準: 出品者≥2 / 価格≥3,000円 / ランク50,000〜150,000位 / Amazon本体在庫切れ
    assert fp.count_new_gte == 2
    assert fp.price_gte == 3000
    assert fp.sales_rank_gte == 50000
    assert fp.sales_rank_lte == 150000
    assert fp.require_amazon_oos is True
    # Phase3 利益基準（利益額≥3,000円）
    assert fp.min_net_profit == 3000


def test_poipoi_to_selection_includes_amazon_oos():
    fp = get_finder_preset("finder_poipoi_standard")
    sel = fp.to_selection([3828871])
    assert sel["current_SALES_gte"] == 50000
    assert sel["current_SALES_lte"] == 150000
    assert sel["current_COUNT_NEW_gte"] == 2
    assert sel["current_NEW_gte"] == 3000
    # Amazon本体在庫=アウトオブストックを current_AMAZON_gte/lte=-1 で表現する
    assert sel["current_AMAZON_gte"] == -1
    assert sel["current_AMAZON_lte"] == -1
    assert sel["categories_include"] == [3828871]


def test_non_oos_preset_does_not_add_amazon_filter():
    """既存プリセット（在庫切れ不要）は selection に current_AMAZON を足さない（後方互換）。"""
    fp = get_finder_preset("finder_genseki_beginner")
    sel = fp.to_selection([3828871])
    assert "current_AMAZON_gte" not in sel
    assert "current_AMAZON_lte" not in sel


def test_existing_presets_preserved():
    """既存 Finder プリセットを壊していない。"""
    for k in ("finder_genseki_beginner", "finder_genseki_standard"):
        assert get_finder_preset(k).key == k


# ---------------------------------------------------------------------------
# 差分4: 最悪相場シミュレーション（過去相場まで下落しても黒字か）
# ---------------------------------------------------------------------------
def _row_with_history(supplier_price, amazon_price, history):
    item_ap = AmazonProduct(
        asin="BSIM", title="加湿器 1個", current_price=amazon_price,
        sales_rank=80000, monthly_sales=15, offer_count=3,
        category_key="home_kitchen", size_key="standard_1", jan="J",
        price_history=history,
    )
    from adapters.yahoo_shopping import YahooItem
    from discovery.presets import get_preset

    item = YahooItem(name="加湿器 1個", price=supplier_price, url="u", jan="J")
    return pipeline._build_row(item, item_ap, get_preset("wide_net"))


def test_price_history_flows_into_row():
    row = _row_with_history(40000, 74000, [61800, 70000, 74000])
    assert row is not None
    assert row.price_history == [61800, 70000, 74000]
    assert row.category_key == "home_kitchen"


def test_worst_case_uses_floor_and_calc_engine():
    """ダイニチ加湿器の例: 現在74,000円・過去最安61,800円。最悪=61,800円で再計算し黒字。"""
    row = _row_with_history(40000, 74000, [61800, 70000, 74000])
    sim = pipeline.simulate_worst_case(row)
    assert sim is not None
    assert sim.worst_price == 61800  # 過去最安水準を床値に採用
    assert sim.source == "history"
    # calc.profit と完全一致（UIで1円も計算しない＝委譲の担保）
    expected = profit.calculate(
        profit.ProfitInput(
            wholesale_price=40000, amazon_price=61800,
            category_key="home_kitchen", size_key="standard_1",
        )
    )
    assert abs(sim.worst_net_profit - expected.net_profit) < 1e-6
    assert sim.is_profitable == (expected.net_profit > 0)


def test_worst_case_manual_price_overrides_history():
    row = _row_with_history(40000, 74000, [61800, 70000, 74000])
    sim = pipeline.simulate_worst_case(row, manual_price=50000)
    assert sim is not None
    assert sim.worst_price == 50000
    assert sim.source == "manual"


def test_worst_case_detects_loss():
    """仕入値が高く、過去最安まで落ちると赤字になるケースを赤として検出する。"""
    row = _row_with_history(60000, 74000, [61800, 70000, 74000])
    sim = pipeline.simulate_worst_case(row)
    assert sim is not None
    assert sim.is_profitable is False  # 61,800円では手数料込みで赤字


def test_worst_case_none_without_supplier_price():
    """仕入元未特定（supplier_price=None）はシミュレーション不能で None。"""
    ap = AmazonProduct(
        asin="BX", title="原石X", current_price=5000, sales_rank=80000,
        monthly_sales=10, offer_count=3, category_key="home_kitchen",
        size_key="standard_1", jan=None, price_history=[4000, 4500, 5000],
    )

    class _Stub:
        def search(self, query="", *, results=20, price_from=None, price_to=None, jan_code=None):
            return []

    row = pipeline._build_amazon_row(ap, _Stub(), assumed_cost_rate=0.5, use_assumed=False)
    assert row.supplier_price is None
    assert pipeline.simulate_worst_case(row) is None


def test_worst_case_none_without_history_or_manual():
    """相場系列も手入力も無ければ None（簡易版は UI 側で手入力を促す）。"""
    row = _row_with_history(40000, 74000, None)
    assert row is not None
    assert pipeline.simulate_worst_case(row) is None
