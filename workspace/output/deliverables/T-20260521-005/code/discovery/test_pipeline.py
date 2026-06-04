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
from adapters.yahoo_shopping import YahooShoppingClient
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
    # 堅実プリセットの結果は全て利益率15%以上・純利益500円以上
    p = get_preset("hunting_beginner")
    for r in strict:
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


def test_jan_search_filters_to_single_product():
    """JAN直指定の検索が該当1件に絞れる（Amazon起点の実仕入値当てに使う経路）。"""
    yahoo = YahooShoppingClient(force_sample=True)
    hits = yahoo.search(jan_code="4900000000017", results=10)
    assert len(hits) == 1
    assert hits[0].jan == "4900000000017"
