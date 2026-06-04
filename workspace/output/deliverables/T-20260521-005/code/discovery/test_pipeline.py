"""ディスカバリー・パイプラインのテスト（サンプルデータで動くこと＝実現可能性の証明）。

実行: code/ ディレクトリで `python -m pytest discovery/`

検証する性質:
1. (い) 仕入れ元起点が利益降順のリストを返す
2. JAN無し / Amazon該当無し は除外される（突合の正直さ）
3. (あ) Amazon起点が条件フィルタ後に利益降順を返す
4. プリセットの閾値が実際に効く（緩い vs 厳しいで件数が変わる）
5. 利益計算は calc.profit に一致する（数字をでっち上げていない）
"""

from adapters.amazon_data import SampleBackend
from adapters.yahoo_shopping import YahooItem, YahooShoppingClient
from calc import profit
from discovery import pipeline
from discovery.presets import get_preset


def _clients():
    """サンプル強制のアダプタ一式（キー有無に左右されないテスト用）。"""
    return (
        SampleBackend(),
        YahooShoppingClient(force_sample=True),
    )


def test_supplier_mode_returns_descending_profit():
    amazon, yahoo = _clients()
    rows = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    assert rows, "サンプルで1件も返らないのはパイプライン破損"
    profits = [r.net_profit for r in rows]
    assert profits == sorted(profits, reverse=True), "利益降順になっていない"
    # wide_net は黒字のみ残す設定なので全行プラス
    assert all(r.net_profit > 0 for r in rows)


def test_supplier_mode_excludes_unmatched():
    """JAN無し（USBケーブル）と Amazon該当無し は結果から消えるはず。"""
    amazon, yahoo = _clients()
    rows = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    names = [r.name for r in rows]
    assert not any("JAN未登録" in n for n in names), "JAN無し商品が混入している"
    # 全行が突合OKステータス
    assert all(r.match_status == pipeline.MATCH_OK for r in rows)


def test_amazon_mode_returns_descending_profit():
    amazon, yahoo = _clients()
    rows = pipeline.discover_from_amazon(
        preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    assert rows
    profits = [r.net_profit for r in rows]
    assert profits == sorted(profits, reverse=True)


def test_preset_thresholds_actually_filter():
    """厳しいプリセットは緩いプリセット以下の件数になる。"""
    amazon, yahoo = _clients()
    wide = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    strict = pipeline.discover_from_supplier(
        "", preset_key="hunting_beginner", amazon_backend=amazon, yahoo_client=yahoo
    )
    assert len(strict) <= len(wide)
    # 堅実プリセットの「数量が信頼できる行」は全て利益率/純利益の閾値を満たす。
    # （数量不一致/不明の行は honesty-first で閾値未達でも『要確認』として残すため除外して検証）
    p = get_preset("hunting_beginner")
    for r in strict:
        if not r.qty_reliable:
            continue  # 数量要確認の行は閾値保証の対象外（黙って捨てずに残している）
        assert r.margin_rate >= p.min_margin_rate
        assert r.net_profit >= p.min_net_profit


def test_profit_numbers_match_calc_engine():
    """ランキングの数字が calc.profit の出力と一致する（数字をいじっていない）。"""
    amazon, yahoo = _clients()
    rows = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    row = rows[0]
    # 同じ入力で calc を直接回し、純利益が一致することを確認
    ap = amazon.resolve_by_jan(
        next(
            it.jan
            for it in yahoo.search("", results=50)
            if it.name == row.name
        )
    )
    recomputed = profit.calculate(
        profit.ProfitInput(
            wholesale_price=row.supplier_price,
            amazon_price=ap.current_price,
            category_key=ap.category_key,
            size_key=ap.size_key,
        )
    )
    assert abs(recomputed.net_profit - row.net_profit) < 1e-6


def _row_for(supplier_name, supplier_price, amazon_name, amazon_price):
    """個数照合の回帰テスト用に _build_row を直接叩く小道具。"""
    from adapters.amazon_data import AmazonProduct
    from discovery.presets import get_preset

    item = YahooItem(name=supplier_name, price=supplier_price, url="http://x", jan="J")
    ap = AmazonProduct(
        asin="BTEST",
        title=amazon_name,
        current_price=amazon_price,
        sales_rank=1000,
        monthly_sales=50,
        offer_count=3,
        category_key="home_kitchen",
        size_key="standard_1",
    )
    return pipeline._build_row(item, ap, get_preset("wide_net"))


def test_quantity_mismatch_20_vs_1_is_not_a_gem():
    """社長が踏んだバグの回帰: Yahoo『1個入り』× Amazon『20個入り』を原石にしない。

    1個1,650円の単品が、20個入りで売れるAmazon(7,980円)に"一応"突合された状況。
    素朴な1対1比較なら巨大な偽利益で原石になるが、個数照合で『要確認』に降格し、
    かつ仕入値が per-unit で20個分に補正されて偽の利益が消えることを検証する。
    """
    row = _row_for("リューブゼリー 1個", 1650, "リューブゼリー 20個入り", 7980)
    assert row is not None
    # 原石にしない（数量不一致 → per-unit補正で偽利益が消え、要確認 or 赤字に）
    assert row.verdict != "原石"
    assert row.verdict in (pipeline.VERDICT_NEEDS_CHECK, "はずれ")
    # 数量フラグが立ち、両側の個数が見える
    assert row.qty_flag == pipeline.QTY_ADJUSTED
    assert row.supplier_qty == 1
    assert row.amazon_qty == 20
    assert row.qty_reliable is False
    # 仕入値は20個分に per-unit 補正されている（1,650×20=33,000円）→ 偽利益が消える
    assert row.supplier_price == 1650 * 20
    assert row.supplier_price_raw == 1650
    # Amazon商品名が別途見える（社長が個数を照合できる）
    assert "20個入り" in row.amazon_name
    # 偽の巨大利益が消え赤字（販売<補正後仕入）になる
    assert row.net_profit < 0 or row.net_profit < 500


def test_quantity_match_can_be_gem():
    """両側とも入数20個で一致 → 信頼でき、利益が出れば原石になり得る。"""
    row = _row_for("お茶 ×20本", 1500, "お茶 20本入り", 3980)
    assert row is not None
    assert row.qty_flag == pipeline.QTY_MATCH
    assert row.qty_reliable is True
    assert row.supplier_qty == 20 and row.amazon_qty == 20
    # 数量一致なので降格されない（利益が出ていれば原石/あやしい、profitエンジン準拠）
    assert row.verdict in ("原石", "あやしい", "はずれ")


def test_quantity_unknown_is_downgraded():
    """両側とも入数不明 → 1対1はリスク。要確認に降格しフラグを立てる。"""
    row = _row_for("ワイヤレスイヤホン", 1200, "ワイヤレスイヤホン Bluetooth", 3980)
    assert row is not None
    assert row.qty_flag == pipeline.QTY_UNKNOWN
    assert row.qty_reliable is False
    assert row.verdict == pipeline.VERDICT_NEEDS_CHECK
    assert any("数量未確定" in n for n in row.notes)


def test_jan_search_filters_to_single_product():
    """JAN直指定の検索が該当1件に絞れる（Amazon起点の実仕入値当てに使う経路）。"""
    yahoo = YahooShoppingClient(force_sample=True)
    hits = yahoo.search(jan_code="4900000000017", results=10)
    assert len(hits) == 1
    assert hits[0].jan == "4900000000017"
