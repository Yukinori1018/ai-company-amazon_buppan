"""procure_limit の性質テスト。

実行: このディレクトリで `python3 -m pytest test_procure_limit.py -q`

利益計算は「1円もごまかさない」と決めている箇所なので、
式そのものより **性質**（保守側に倒れているか・出せない時に0を返さないか）を固定する。
"""
import procure_limit as pl


BASE = dict(category_key="home_kitchen", size_key="standard_1",
            dims_mm=(300, 200, 100), turnover_months=1.0)


def test_uses_the_lower_of_current_and_floor():
    """基準売価は「現在価格」と「過去最安値」の小さい方＝保守側。"""
    hi = pl.compute(current_price=5000, floor_price=None, **BASE)
    lo = pl.compute(current_price=5000, floor_price=4000, **BASE)
    assert hi["base_price"] == 5000 and hi["basis"] == "現在の新品最安値"
    assert lo["base_price"] == 4000 and lo["basis"] == "過去最安値(2026-02-23以降)"
    assert lo["limit"] < hi["limit"]


def test_floor_above_current_is_ignored():
    """過去最安値が現在価格より高いなら、当然そちらは使わない。"""
    r = pl.compute(current_price=4000, floor_price=5000, **BASE)
    assert r["base_price"] == 4000


def test_limit_is_below_breakeven_by_the_target_profit():
    """上限 = 赤字ライン − 目標利益。目標利益率ぶんきっちり下にある。"""
    r = pl.compute(current_price=5000, floor_price=None, **BASE)
    assert r["breakeven"] - r["limit"] == int(5000 * pl.TARGET_NET_MARGIN)
    assert r["net_at_limit"] == int(5000 * pl.TARGET_NET_MARGIN)


def test_returns_none_not_zero_when_unprofitable():
    """黒字にできない商品は None。0 を返すと『0円なら仕入れられる』と誤読される。"""
    r = pl.compute(current_price=600, floor_price=None, **BASE)
    assert r["limit"] is None


def test_returns_none_when_no_price_at_all():
    r = pl.compute(current_price=None, floor_price=None, **BASE)
    assert r["limit"] is None and r["base_price"] is None


def test_fee_buffer_makes_the_limit_stricter():
    """料率バッファは必ず上限を下げる方向にしか効かない（甘い方にはズレない）。

    2026-08-24: fees.py を現行値へ更新したため、既定の FEE_RATE_BUFFER_PT は 0.0 になった
    （二重の安全マージンが不要になったため）。この性質テストは「バッファという仕組み自体」を
    検証するものなので、明示的に正の値と 0 を比較する形に直す。
    """
    saved = pl.FEE_RATE_BUFFER_PT
    try:
        pl.FEE_RATE_BUFFER_PT = 0.010
        r_with = pl.compute(current_price=5000, floor_price=None, **BASE)
        pl.FEE_RATE_BUFFER_PT = 0.0
        r_without = pl.compute(current_price=5000, floor_price=None, **BASE)
    finally:
        pl.FEE_RATE_BUFFER_PT = saved
    assert r_with["limit"] < r_without["limit"]


def test_default_buffer_is_zero_after_2026_08_fee_update():
    """既定値そのものが 0.0 であること（更新のし忘れ防止のガード）。"""
    assert pl.FEE_RATE_BUFFER_PT == 0.0


def test_storage_fee_scales_with_volume_and_months():
    small, _ = pl.storage_fee_yen((100, 100, 100), 1.0)
    big, _ = pl.storage_fee_yen((300, 300, 300), 1.0)
    longer, _ = pl.storage_fee_yen((100, 100, 100), 3.0)
    assert big > small and longer > small


def test_storage_months_are_capped():
    """消化に何年かかる商品でも保管料は上限で頭打ち（撤退判断の領域なので積み増さない）。"""
    a, _ = pl.storage_fee_yen((200, 200, 200), pl.STORAGE_MONTHS_CAP)
    b, _ = pl.storage_fee_yen((200, 200, 200), 999.0)
    assert a == b


def test_breakdown_string_shows_every_deduction():
    """社長・経理が『何を引いたか』を追えること。監査可能性は仕様の一部。"""
    r = pl.compute(current_price=5000, floor_price=None, **BASE)
    for word in ("基準売価", "販売手数料", "FBA配送", "保管", "外注", "雑費", "目標利益"):
        assert word in r["cost_breakdown"]
