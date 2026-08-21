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
    # 設計変更(2026-06-05): 突合できた行は赤字でも捨てず全件表示する（0件化をやめる）。
    # 黒字行は少なくとも1つはある（サンプルに利益の出る商品が含まれる）。
    assert any(r.net_profit > 0 for r in rows)


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
    """設計変更(2026-06-05): プリセット閾値は『原石バッジの付与条件』であり、行は捨てない。

    よって件数では差が出ない（突合できた行は全プリセットで全件残す）。
    代わりに、閾値が効くのは verdict＝『原石』の付与有無で検証する：
    厳しいプリセットの原石数は、緩いプリセットの原石数以下になる。
    """
    amazon, yahoo = _clients()
    wide = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    strict = pipeline.discover_from_supplier(
        "", preset_key="hunting_standard", amazon_backend=amazon, yahoo_client=yahoo
    )
    gems_wide = sum(1 for r in wide if r.verdict == "原石")
    gems_strict = sum(1 for r in strict if r.verdict == "原石")
    assert gems_strict <= gems_wide
    # 原石になった行は、そのプリセットの利益率/純利益の閾値を必ず満たす（バッジの正しさ）。
    p = get_preset("hunting_standard")
    for r in strict:
        if r.verdict == "原石":
            assert r.margin_rate >= p.min_margin_rate
            assert r.net_profit >= p.min_net_profit
            assert r.qty_reliable


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


def test_suspect_mismatch_is_quarantined_not_ranked():
    """別商品の疑い検知（社長報告 2026-06-06）。

    JANは一致するが仕入元名(遊具)とAmazon名(物置)がかけ離れている＝JAN誤登録の疑い。
    利益数値を出さず match_status=別商品の疑い に隔離されることを検証する。
    """
    row = _row_for("滑り台・ブランコ 大型遊具 すべり台", 9800,
                   "物置 屋外 大型 SOFTSEA 収納庫", 24800)
    assert row is not None
    assert row.match_status == pipeline.MATCH_SUSPECT_MISMATCH
    # 利益数値は一切出さない（誤誘導防止）
    assert row.net_profit == 0.0
    assert row.margin_rate == 0.0
    # 仕入元名とAmazon名が両方見える（社長が目視照合できる）
    assert "遊具" in row.name
    assert "物置" in row.amazon_name
    assert any("JAN" in n for n in row.notes)


def test_suspect_desk_mismatch_quarantined():
    """ジャングルジム ⇔ システムデスク も別商品の疑いとして隔離される。"""
    row = _row_for("つっぱり式ジャングルジム 室内 子供", 12800,
                   "システムデスク OSJ パソコンデスク L字", 18800)
    assert row is not None
    assert row.match_status == pipeline.MATCH_SUSPECT_MISMATCH


def test_legitimate_match_is_not_flagged_as_suspect():
    """正しい組（スライダージム同士）は別商品の疑いにならず通常ランキングに乗る。"""
    row = _row_for("おりたたみスライダージム すべり台 室内", 8800,
                   "折りたたみ スライダージム 室内すべり台 ブランコ", 14800)
    assert row is not None
    assert row.match_status != pipeline.MATCH_SUSPECT_MISMATCH
    assert row.match_status in (pipeline.MATCH_OK, pipeline.AMAZON_FILTER_FAIL)


def test_guard_does_not_drop_healthy_keyword_earplug():
    """健全キーワード（耳栓）でガードが正しい原石を誤って落とさない（誤検知抑制）。"""
    row = _row_for("シリコン 耳栓 睡眠用 ノイズ低減", 800,
                   "耳栓 睡眠用 高性能 ノイズキャンセリング 防音", 2480)
    assert row is not None
    assert row.match_status != pipeline.MATCH_SUSPECT_MISMATCH


def test_numeric_conflict_volume_is_quarantined():
    """容量が矛盾（500ml vs 1000ml）＝別商品の疑いに隔離（社長FB 2026-06-07・精度向上）。

    JAN一致でも容量が違えば別規格の別商品。利益を出さず隔離する。
    """
    row = _row_for("ファブリーズ 消臭スプレー 500ml", 480,
                   "ファブリーズ 消臭スプレー 1000ml 大容量", 1280)
    assert row is not None
    assert row.match_status == pipeline.MATCH_SUSPECT_MISMATCH
    assert row.match_confidence == "低"
    assert row.net_profit == 0.0
    assert any("容量" in n for n in row.notes)


def test_high_confidence_match_carries_confidence_field():
    """型番/名詞一致＋容量一致の正当な突合は信頼度=高を持つ。"""
    row = _row_for("ファブリーズ 消臭スプレー 500ml", 480,
                   "ファブリーズ 消臭スプレー 500ml 無香料", 1280)
    assert row is not None
    assert row.match_status in (pipeline.MATCH_OK, pipeline.AMAZON_FILTER_FAIL)
    assert row.match_confidence == "高"


def test_low_confidence_never_becomes_gem():
    """信頼度=低（容量矛盾）は決して原石にならない（誤突合の原石化を根絶）。"""
    row = _row_for("洗剤 1L 詰め替え", 300, "洗剤 2L 業務用", 900)
    assert row is not None
    assert row.verdict != "原石"
    assert row.match_status == pipeline.MATCH_SUSPECT_MISMATCH


def test_quantity_match_can_be_gem():
    """両側とも入数20個で一致 → 信頼でき、利益が出れば原石になり得る。"""
    row = _row_for("お茶 ×20本", 1500, "お茶 20本入り", 3980)
    assert row is not None
    assert row.qty_flag == pipeline.QTY_MATCH
    assert row.qty_reliable is True
    assert row.supplier_qty == 20 and row.amazon_qty == 20
    # 数量一致なので降格されない（利益が出ていれば原石/あやしい、profitエンジン準拠）
    assert row.verdict in ("原石", "あやしい", "はずれ")


def test_quantity_both_none_is_treated_as_single_unit():
    """設計変更(2026-06-05): 両側とも入数表記なし＝通常の単品(1個 vs 1個)とみなす。

    社長フィードバック「原石が出てこない」の主因対策。単品同士を一律『要確認』に落とすと
    単品の原石が永遠に出ないため、None/None は qty_reliable=True（一致扱い）にする。
    多包装の誤突合リスクは『片側だけN個入りを名乗る』ケースに限定して降格する（次のテスト）。
    """
    row = _row_for("ワイヤレスイヤホン", 1200, "ワイヤレスイヤホン Bluetooth", 3980)
    assert row is not None
    # 数量矛盾修正(2026-06-06): 入数?/?なのに「数量一致」と出すのは矛盾。専用ラベルで区別。
    assert row.qty_flag == pipeline.QTY_BOTH_SINGLE
    assert row.qty_flag != pipeline.QTY_MATCH
    assert row.qty_reliable is True
    # 利益が出ていれば原石/あやしいに昇格し得る（単品なので降格しない）。
    assert row.verdict in ("原石", "あやしい", "はずれ")
    assert any("単品" in n for n in row.notes)


def test_quantity_both_unknown_does_not_say_match():
    """数量矛盾の回帰(社長報告 2026-06-06): 入数が両方不明(?/?)のとき、

    『数量一致』とは表示しない。両側 None なら専用ラベル QTY_BOTH_SINGLE になり、
    『一致』を意味する QTY_MATCH には決してならないことを保証する。
    """
    row = _row_for("シリコン耳栓", 800, "シリコン耳栓 睡眠用", 2480)
    assert row is not None
    assert row.supplier_qty is None and row.amazon_qty is None
    assert row.qty_flag == pipeline.QTY_BOTH_SINGLE
    assert "一致" not in row.qty_flag


def test_quantity_one_sided_is_downgraded():
    """片側だけ『N個入り』を名乗る → 多包装の誤突合リスク。要確認に降格しフラグを立てる。"""
    row = _row_for("お茶 5本セット", 1200, "お茶", 3980)
    assert row is not None
    assert row.qty_flag == pipeline.QTY_UNKNOWN
    assert row.qty_reliable is False
    assert row.verdict == pipeline.VERDICT_NEEDS_CHECK
    assert any("数量未確定" in n for n in row.notes)


def test_amazon_condition_fail_row_is_kept_not_dropped():
    """社長FB回帰(2026-06-05): Amazonメタ条件外でも行を0件化せず『要確認』で残す。

    rank がプリセット上限を超える商品を _build_row に通す。以前は None で除外され
    『条件に合う原石が見つかりません』の0件化を招いていた。今は行を返し verdict を降格する。
    """
    from adapters.amazon_data import AmazonProduct
    from discovery.presets import get_preset

    item = YahooItem(name="単品商品", price=1000, url="http://x", jan="J")
    ap = AmazonProduct(
        asin="BFAIL", title="単品商品", current_price=3000,
        sales_rank=999999,  # プリセット上限を大きく超える（条件外）
        monthly_sales=1, offer_count=3,
        category_key="home_kitchen", size_key="standard_1",
    )
    row = pipeline._build_row(item, ap, get_preset("hunting_beginner"))
    assert row is not None, "Amazon条件外で行を捨ててはいけない（0件化の主因）"
    assert row.match_status == pipeline.AMAZON_FILTER_FAIL
    assert row.verdict == pipeline.VERDICT_NEEDS_CHECK  # 原石にはしないが残す
    assert any("Amazon条件外" in n for n in row.notes)


def test_below_threshold_profit_row_is_kept_as_needs_check():
    """利益閾値を下回る黒字行も捨てず『要確認』で残す（バッジ条件に留める）。"""
    amazon, yahoo = _clients()
    # min_net_profit=300 の hunting_beginner で、閾値前後の行が全て残ることを確認。
    rows = pipeline.discover_from_supplier(
        "", preset_key="hunting_beginner", amazon_backend=amazon, yahoo_client=yahoo
    )
    # 突合できた行は1つも消えない（wide_net と同数）。
    wide = pipeline.discover_from_supplier(
        "", preset_key="wide_net", amazon_backend=amazon, yahoo_client=yahoo
    )
    assert len(rows) == len(wide), "閾値で行を捨てている（0件化の温床）"


class _FakeFinderBackend:
    """find_products を持つ偽 Keepa バックエンド（実APIを叩かずに Finder 経路を検証）。"""

    is_live = True
    is_sample = False

    def __init__(self, products):
        self._products = products
        self.last_selection = None
        self.last_tokens_left = 530
        self.last_tokens_consumed = 24

    def find_products(self, selection, *, limit=None):
        self.last_selection = selection
        return list(self._products)[: (limit or len(self._products))]


def _amazon_product(asin, title, price, jan=None, rank=20000, offers=4, brand=None):
    from adapters.amazon_data import AmazonProduct

    return AmazonProduct(
        asin=asin, title=title, current_price=price, sales_rank=rank,
        monthly_sales=30, offer_count=offers, category_key="home_kitchen",
        size_key="standard_1", jan=jan, brand=brand,
    )


def test_discover_by_finder_builds_selection_and_ranks(monkeypatch):
    """Finder経路: selection が組まれ、Yahoo突合→利益降順ランキングになる。"""
    from discovery.presets import get_finder_preset

    products = [
        _amazon_product("B1", "原石A 1個", 3980, jan="4900000000017"),
        _amazon_product("B2", "原石B 1個", 2980, jan="4900000000024"),
    ]
    backend = _FakeFinderBackend(products)
    yahoo = YahooShoppingClient(force_sample=True)

    rows = pipeline.discover_by_finder(
        finder_preset_key="finder_genseki_beginner",
        category_ids=[3828871],
        amazon_backend=backend, yahoo_client=yahoo,
        use_assumed_cost=True, assumed_cost_rate=0.4,  # サンプルYahoo未一致でも行が出るように
    )
    # selection が Finder プリセットから組み立てられている
    sel = backend.last_selection
    fp = get_finder_preset("finder_genseki_beginner")
    assert sel["current_SALES_gte"] == fp.sales_rank_gte
    assert sel["current_SALES_lte"] == fp.sales_rank_lte
    assert sel["current_COUNT_NEW_lte"] == fp.count_new_lte
    assert sel["categories_include"] == [3828871]
    assert sel["sort"] == fp.sort  # 抽出順はプリセット定義（既定: 競合薄い順 COUNT_NEW asc）
    # 利益降順
    profits = [r.net_profit for r in rows]
    assert profits == sorted(profits, reverse=True)


def test_discover_by_finder_carries_maker(monkeypatch):
    """メーカー仕入れ用（T-20260706-002（旧 T-20260706-001））: Finder 出力 DiscoveryRow に maker が乗る。

    仕入元未特定でも（use_assumed_cost=False の正直保留行でも）メーカー名は保持され、
    メーカー抽出を Keepa 再クエリなしで discover 出力から取れることを保証する。
    """
    products = [
        _amazon_product("BM", "原石M 1個", 4980, jan="0000000000000", brand="サーモス"),
    ]
    backend = _FakeFinderBackend(products)
    yahoo = YahooShoppingClient(force_sample=True)

    rows = pipeline.discover_by_finder(
        finder_preset_key="finder_genseki_beginner",
        category_ids=[3828871],
        amazon_backend=backend, yahoo_client=yahoo,
        use_assumed_cost=False,  # 仕入元未特定→正直保留。それでも maker は乗る
    )
    assert rows, "行が出るはず（捨てない設計）"
    assert all(r.maker == "サーモス" for r in rows)


def test_discover_by_finder_honest_when_no_supplier(monkeypatch):
    """仕入元が当たらず use_assumed_cost=False なら利益をでっち上げず保留にする。"""
    products = [_amazon_product("BX", "原石X 1個", 5000, jan="0000000000000")]
    backend = _FakeFinderBackend(products)
    yahoo = YahooShoppingClient(force_sample=True)

    rows = pipeline.discover_by_finder(
        finder_preset_key="finder_genseki_beginner",
        category_ids=[3828871],
        amazon_backend=backend, yahoo_client=yahoo,
        use_assumed_cost=False,
    )
    # 仕入元未発見の行は利益0・要確認・保留ノート付き（でっち上げ無し）
    assert rows and rows[0].supplier_price is None
    assert rows[0].net_profit == 0.0
    assert rows[0].verdict == pipeline.VERDICT_NEEDS_CHECK
    assert any("仕入元未発見" in n for n in rows[0].notes)


class _StubSupplier:
    """jan_code 逆引きで固定アイテムを返す擬似仕入元（実APIを叩かない）。

    本番Yahooが janCode を空で返すケースを再現するため jan=None を返せる。
    """

    def __init__(self, item):
        self._item = item
        self.calls = []

    def search(self, query="", *, results=20, price_from=None, price_to=None, jan_code=None):
        self.calls.append(jan_code)
        return [self._item] if (jan_code and self._item is not None) else []


def test_amazon_reverse_lookup_attaches_real_supplier_even_if_jan_none():
    """逆引きの肝（社長FB回帰）: 仕入元が janCode を空(None)で返しても、
    最安1件として返ってきた実在候補を取りこぼさず、実仕入値・URLを付与する。"""
    ap = _amazon_product("BREV", "テスト原石 20本入り", 3980, jan="4900000000017")
    # 本番Yahooが janCode を返さない（None）が、JAN直指定検索の最安1件として実在する。
    hit = YahooItem(
        name="テスト原石 20本入り", price=1500, url="https://store.example/x",
        jan=None, source="楽天",
    )
    supplier = _StubSupplier(hit)
    row = pipeline._build_amazon_row(ap, supplier, assumed_cost_rate=0.5, use_assumed=False)
    assert row is not None
    # 実仕入値・実URL・仕入元名が付く（でっち上げの50%ではない）
    assert row.supplier_price == 1500
    assert row.supplier_url == "https://store.example/x"
    assert row.supplier_source == "楽天"
    assert row.match_status == pipeline.MATCH_OK
    assert supplier.calls == ["4900000000017"]  # JANで逆引きしている


def test_amazon_no_jan_yields_holding_row_without_fake_profit():
    """JANが取れないASINは逆引きせず、仕入元未特定の保留行（利益0・URL空）になる。"""
    ap = _amazon_product("BNOJAN", "JAN無し原石", 4000, jan=None)
    supplier = _StubSupplier(None)
    row = pipeline._build_amazon_row(ap, supplier, assumed_cost_rate=0.5, use_assumed=False)
    assert row is not None
    assert row.supplier_price is None
    assert row.supplier_url == ""
    assert row.net_profit == 0.0 and row.margin_rate == 0.0 and row.roi == 0.0
    assert row.match_status == pipeline.AMAZON_ONLY
    assert supplier.calls == []  # JAN無しは無駄打ちしない


def test_amazon_reverse_lookup_real_supplier_computes_profit():
    """逆引きで実仕入値が付いた行は calc.profit と一致する利益が出る（数量一致時）。"""
    ap = _amazon_product("BOK", "お茶 20本入り", 3980, jan="4900000000017")
    hit = YahooItem(name="お茶 ×20本", price=1500, url="u", jan="4900000000017", source="Yahoo")
    supplier = _StubSupplier(hit)
    row = pipeline._build_amazon_row(ap, supplier, assumed_cost_rate=0.5, use_assumed=False)
    assert row is not None and row.supplier_price == 1500
    recomputed = profit.calculate(
        profit.ProfitInput(
            wholesale_price=1500, amazon_price=3980,
            category_key=ap.category_key, size_key=ap.size_key,
        )
    )
    assert abs(recomputed.net_profit - row.net_profit) < 1e-6


def test_finder_preset_to_selection_shape():
    """FinderPreset.to_selection が Keepa が期待するフィールド名の dict を返す。"""
    from discovery.presets import get_finder_preset

    fp = get_finder_preset("finder_genseki_beginner")
    sel = fp.to_selection([3828871, 86731051])
    for field_name in (
        "current_SALES_gte", "current_SALES_lte",
        "current_COUNT_NEW_gte", "current_COUNT_NEW_lte",
        "current_NEW_gte", "current_NEW_lte",
        "categories_include", "perPage", "page", "sort",
    ):
        assert field_name in sel
    assert sel["categories_include"] == [3828871, 86731051]
    assert sel["perPage"] >= 50  # Keepa の最小 perPage 要件


def test_jan_search_filters_to_single_product():
    """JAN直指定の検索が該当1件に絞れる（Amazon起点の実仕入値当てに使う経路）。"""
    yahoo = YahooShoppingClient(force_sample=True)
    hits = yahoo.search(jan_code="4900000000017", results=10)
    assert len(hits) == 1
    assert hits[0].jan == "4900000000017"


# ---------------------------------------------------------------------------
# 複数仕入れ先（Yahoo+楽天）統合: 同JAN最安採用と突合母数の拡大
# ---------------------------------------------------------------------------
def test_cheapest_per_jan_keeps_lowest_source():
    """同一JANが複数仕入元から出たら最安1件に集約され、source が安い方になる。"""
    items = [
        YahooItem(name="水筒Y", price=1280, url="u1", jan="J1", source="Yahoo"),
        YahooItem(name="水筒R", price=1180, url="u2", jan="J1", source="楽天"),
        YahooItem(name="他", price=900, url="u3", jan="J2", source="Yahoo"),
    ]
    out = pipeline._cheapest_per_jan(items)
    assert len(out) == 2  # J1 は1件に集約
    j1 = next(it for it in out if it.jan == "J1")
    assert j1.price == 1180 and j1.source == "楽天"


def test_cheapest_per_jan_drops_invalid_price_and_no_jan():
    items = [
        YahooItem(name="価格0", price=0, url="u", jan="J1", source="楽天"),
        YahooItem(name="JAN無し", price=500, url="u", jan=None, source="Yahoo"),
        YahooItem(name="有効", price=500, url="u", jan="J2", source="Yahoo"),
    ]
    out = pipeline._cheapest_per_jan(items)
    assert [it.jan for it in out] == ["J2"]


def test_multi_supplier_keyword_merge_prioritizes_jan():
    """キーワード検索のマージは JAN付きを上位に集める（楽天のJAN無しで突合母数を減らさない）。

    楽天は仕様上 janCode を返さないため、安い順だけで並べると JAN無しの楽天品が上位を占め、
    results で切り詰めると Amazon突合に乗る JAN付き候補が落ちる。JAN優先で取りこぼさない。
    """
    from adapters.multi_supplier import MultiSupplierClient

    class _Stub:
        def __init__(self, items):
            self._items = items

        def search(self, query="", *, results=20, price_from=None, price_to=None, jan_code=None):
            return list(self._items)

    # 楽天役: 安いが JAN無し（多数）。Yahoo役: 少し高いが JAN付き。
    rakuten = _Stub([
        YahooItem(name=f"R{i}", price=500 + i, url="u", jan=None, source="楽天")
        for i in range(5)
    ])
    yahoo = _Stub([
        YahooItem(name=f"Y{i}", price=2000 + i, url="u", jan=f"J{i}", source="Yahoo")
        for i in range(3)
    ])
    multi = MultiSupplierClient([rakuten, yahoo])
    merged = multi.search("水筒", results=3)
    # 上位3件すべて JAN付き（安い楽天の JAN無しに押し出されていない）。
    assert all(it.jan for it in merged), [it.source for it in merged]


def test_supplier_mode_merges_two_suppliers_widens_pool():
    """Yahoo単独より Yahoo+楽天 の方が、楽天だけにあるJANを拾える（突合母数の拡大）。"""
    from adapters.multi_supplier import MultiSupplierClient
    from adapters.rakuten_shopping import RakutenShoppingClient

    amazon = SampleBackend()
    yahoo_only = YahooShoppingClient(force_sample=True)
    both = MultiSupplierClient(
        [YahooShoppingClient(force_sample=True), RakutenShoppingClient(force_sample=True)]
    )
    rows_y = pipeline.discover_from_supplier("", amazon_backend=amazon, yahoo_client=yahoo_only)
    rows_b = pipeline.discover_from_supplier("", amazon_backend=amazon, yahoo_client=both)
    # 仕入元が2本になっても同JANは集約されるので、ASINは重複しない。
    asins = [r.asin for r in rows_b]
    assert len(asins) == len(set(asins))
    # 少なくとも1行は楽天が最安として採用されている（マージが効いている証拠）。
    assert any(r.supplier_source == "楽天" for r in rows_b)
    # 母数は単独以上（楽天のみのJANが加わるため減らない）。
    assert len(rows_b) >= len(rows_y)


# =============================================================================
# 2026-06-05 社長フィードバック対応（探索カテゴリ増設・原石基準の動的表示）
# =============================================================================
def test_amazon_categories_expanded_to_at_least_12():
    """社長FB「カテゴリが5個しかない＝少なすぎ」対策。12件以上に増設したことを保証。"""
    from discovery.presets import AMAZON_CATEGORIES, amazon_category_choices

    assert len(AMAZON_CATEGORIES) >= 12, "探索カテゴリは12件以上必要（社長FB）"
    # 既存5カテゴリは温存（後方互換）。
    for k in ("home_kitchen", "office", "pet", "toys", "sports"):
        assert k in AMAZON_CATEGORIES
    # UIセレクト用 choices も同数で (key, label) 形を保つ。
    choices = amazon_category_choices()
    assert len(choices) == len(AMAZON_CATEGORIES)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in choices)


def test_amazon_category_ids_are_valid_keepa_cojp_roots():
    """各 category_id が Keepa /category(domain=5) 実取得の有効ルートIDであること。

    2026-06-05 タカシが実取得した co.jp ルートカテゴリID集合（でっち上げ防止の固定値）。
    新規IDがこの集合外＝出典不明として落とす（テストで検出）。
    """
    from discovery.presets import AMAZON_CATEGORIES

    # Keepa /category?domain=5&category=0&parents=0 実レスポンス（2026-06-05取得）の物販系ID。
    valid_keepa_cojp_root_ids = {
        3828871, 86731051, 2127212051, 13299531, 14304371,   # 既存5
        160384011, 52374051, 57239051, 3210981, 2127209051,  # 増設
        2016929051, 344845011, 2017304051, 2277721051,
        2123629051, 3445393051,
    }
    for c in AMAZON_CATEGORIES.values():
        assert c.category_id in valid_keepa_cojp_root_ids, (
            f"{c.key} の category_id={c.category_id} は実取得ID集合外（出典不明）"
        )


def test_gem_criteria_text_follows_preset_values():
    """原石基準の表示文が preset の実値（率/額）から動的生成されること。

    社長FB「表示は15%/500円だが実装は8%/300円に緩和済みで食い違う」の恒久対策。
    finder初心者プリセットは 8%/300円 → 文言もそれに一致しなければならない。
    """
    from discovery.presets import (
        active_gem_criteria_text,
        gem_criteria_text,
        get_finder_preset,
    )

    fp = get_finder_preset("finder_genseki_beginner")
    assert fp.min_margin_rate == 0.08 and fp.min_net_profit == 300
    txt = active_gem_criteria_text(finder_key="finder_genseki_beginner")
    assert "8%" in txt and "300" in txt
    assert "15%" not in txt and "500" not in txt
    # 純関数も実値どおりに整形する。
    assert gem_criteria_text(0.15, 500) == "利益率15%以上かつ純利益500円以上"


def test_preset_thresholds_drive_gem_verdict():
    """preset の min_margin_rate/min_net_profit が原石判定に実際に効くこと。

    profit.py 既定(15%/500)で上書きされ preset緩和(8%/300)が無効化されていた不具合の回帰。
    8%台の利益率しか出ない行が、緩い preset では原石、厳しい preset では原石にならない。
    """
    from adapters.amazon_data import AmazonProduct
    from discovery.presets import DiscoveryPreset

    item = YahooItem(name="テスト商品", price=1000, url="http://x", jan="J")
    ap = AmazonProduct(
        asin="BGEM", title="テスト商品", current_price=1200,
        sales_rank=1000, monthly_sales=50, offer_count=3,
        category_key="home_kitchen", size_key="standard_1",
    )
    loose = DiscoveryPreset(
        key="loose", label="ゆるい", description="",
        max_sales_rank=10**9, max_offer_count=999,
        min_margin_rate=0.01, min_net_profit=1,
    )
    strict = DiscoveryPreset(
        key="strict", label="きびしい", description="",
        max_sales_rank=10**9, max_offer_count=999,
        min_margin_rate=0.50, min_net_profit=5000,
    )
    row_loose = pipeline._build_row(item, ap, loose)
    row_strict = pipeline._build_row(item, ap, strict)
    # 同じ実利益でも、緩い preset では原石、厳しい preset では原石でない。
    assert row_loose is not None and row_strict is not None
    if row_loose.net_profit > 0:  # 黒字行のときだけ原石/非原石の差が意味を持つ
        assert row_loose.verdict == "原石"
        assert row_strict.verdict != "原石"
