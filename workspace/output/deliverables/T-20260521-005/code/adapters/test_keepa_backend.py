"""KeepaBackend の正規化ロジックのテスト（実 API は叩かず、実レスポンス断片のモックで検証）。

実行: code/ ディレクトリで `python -m pytest adapters/`

ここで使う mock JSON は 2026-06-05 にタカシが実 Keepa API（domain=5, stats=90, offers=20）で
取得した「水筒」商品レスポンスの構造をそのまま縮約したもの。価格は円そのまま、-1=データ無し。
"""

from adapters import amazon_data
from adapters.amazon_data import (
    KeepaBackend,
    _map_category_key,
    _map_size_key,
    _pick_amazon_price,
    _pick_oos_rate_90d,
    _product_to_amazon,
)


# ---- 実レスポンスを縮約したモック商品（サーモス2L 水筒・実データ由来）------------
MOCK_PRODUCT = {
    "asin": "B08VR99HJR",
    "title": "サーモス 水筒 真空断熱スポーツジャグ 2.0L",
    "eanList": ["4562344377072"],
    "monthlySold": 28,
    "rootCategory": 3828871,
    "salesRankReference": 3828871,
    "salesRanks": {"3828871": [123, 152233], "2421559051": [10, 800]},
    "categoryTree": [
        {"catId": 3828871, "name": "ホーム＆キッチン"},
        {"catId": 2962360051, "name": "弁当箱・水筒"},
    ],
    "packageWeight": 1200,        # g → standard_2 帯
    "packageLength": 300, "packageWidth": 120, "packageHeight": 120,  # mm
    "stats": {
        "current": [-1, 9500, -1, 27, -1, -1, -1, -1, -1, -1, 9500, 2,
                    -1, -1, -1, -1, -1, -1, 9500, -1, -1, -1, -1, -1,
                    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        "buyBoxPrice": 9500,
        "outOfStockPercentage90": [-1, 5, -1, -1] + [-1] * 14 + [3] + [-1] * 17,
    },
}

# Buy Box が出ていない（-1）商品: New 最安にフォールバックするケース
MOCK_NO_BUYBOX = {
    "asin": "B0BBQ3ZFCL",
    "title": "アトラス 水筒 1リットル",
    "eanList": ["4582532193901"],
    "monthlySold": 0,            # → ランク推定にフォールバック（is_estimate=True）
    "rootCategory": 3828871,
    "salesRanks": {"3828871": [1, 9000]},
    "categoryTree": [{"catId": 3828871, "name": "ホーム＆キッチン"}],
    "packageWeight": 400,
    "stats": {
        "current": [-1, 1980, -1, 9000] + [-1] * 32,
        "buyBoxPrice": -1,       # Buy Box 無し
        "outOfStockPercentage90": [-1] * 36,
    },
}


def test_amazon_price_prefers_buybox():
    assert _pick_amazon_price(MOCK_PRODUCT["stats"]) == 9500


def test_amazon_price_falls_back_to_new_when_no_buybox():
    # buyBoxPrice=-1 → current[18](BB)=-1 → current[1](NEW)=1980 を採用
    assert _pick_amazon_price(MOCK_NO_BUYBOX["stats"]) == 1980


def test_amazon_price_minus_one_is_none():
    assert _pick_amazon_price({"buyBoxPrice": -1, "current": [-1] * 36}) is None


def test_oos_rate_normalized_0_to_1():
    # Buy Box OOS(index18)=3% → 0.03
    assert abs(_pick_oos_rate_90d(MOCK_PRODUCT["stats"]) - 0.03) < 1e-9


def test_category_mapping_home_kitchen():
    assert _map_category_key(MOCK_PRODUCT) == "home_kitchen"


def test_category_mapping_default_for_unknown():
    assert _map_category_key({"categoryTree": [{"name": "謎カテゴリ"}]}) == "default"


def test_size_mapping_by_weight():
    # 1200g → standard_2
    assert _map_size_key(MOCK_PRODUCT)[0] == "standard_2"
    # 400g → standard_1
    assert _map_size_key(MOCK_NO_BUYBOX)[0] == "standard_1"


def test_size_mapping_unknown_defaults_with_note():
    size_key, note = _map_size_key({"asin": "X"})
    assert size_key == "standard_1"
    assert note is not None  # ⚠ノート付きで「仮定」と明示される


def test_product_to_amazon_full_mapping():
    ap = _product_to_amazon(MOCK_PRODUCT)
    assert ap is not None
    assert ap.asin == "B08VR99HJR"
    assert ap.current_price == 9500
    assert ap.sales_rank == 152233       # salesRanks のルート大分類ランク
    assert ap.offer_count == 2           # current[11]=COUNT_NEW
    assert ap.monthly_sales == 28        # 実測 monthlySold
    assert ap.category_key == "home_kitchen"
    assert getattr(ap, "monthly_sales_is_estimate") is False


def test_monthly_sales_estimate_flag_when_no_data():
    ap = _product_to_amazon(MOCK_NO_BUYBOX)
    assert ap is not None
    # monthlySold=0 → ランク推定にフォールバック → is_estimate True ＆ ノート付き
    assert getattr(ap, "monthly_sales_is_estimate") is True
    assert any("推定" in n for n in getattr(ap, "estimate_notes"))


def test_product_without_asin_returns_none():
    assert _product_to_amazon({"title": "no asin", "stats": {}}) is None


def test_resolve_many_matches_by_eanlist(monkeypatch):
    """resolve_many が eanList で JAN を正しく突合し、該当無し JAN を除外することを検証。"""
    backend = KeepaBackend(api_key="dummy")  # is_live=True にする

    def fake_request(self, *, code):
        # 2件問い合わせ → 1件だけ Amazon に存在する想定
        return {
            "tokensLeft": 1000,
            "tokensConsumed": 5,
            "products": [MOCK_PRODUCT],  # JAN 4562344377072 のみ返る
        }

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    result = backend.resolve_many(["4562344377072", "9999999999999"])
    assert set(result.keys()) == {"4562344377072"}   # 該当無し JAN は除外
    assert result["4562344377072"].jan == "4562344377072"
    assert result["4562344377072"].asin == "B08VR99HJR"
    assert backend.last_tokens_left == 1000


def test_resolve_many_caps_jan_count(monkeypatch):
    """MAX_JANS_PER_CALL を超える JAN は切り詰められること（トークン節約）。"""
    backend = KeepaBackend(api_key="dummy")
    captured = {}

    def fake_request(self, *, code):
        captured["code"] = code
        return {"tokensLeft": 1, "tokensConsumed": 1, "products": []}

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    many = [str(1000000000000 + i) for i in range(25)]
    backend.resolve_many(many)
    assert len(captured["code"].split(",")) == KeepaBackend.MAX_JANS_PER_CALL


def test_list_products_bestsellers_flow(monkeypatch):
    """(あ)Amazon起点: bestsellers→ASIN→詳細 の流れと ASIN上限が効くことを検証（実APIは叩かない）。"""
    backend = KeepaBackend(api_key="dummy")

    def fake_bestsellers(self, category_id):
        # カテゴリから売れ筋 ASIN を15件返す（上限10で切られるはず）
        return [f"B{ i:09d}" for i in range(15)]

    captured = {}

    def fake_request(self, *, code=None, asin=None):
        captured["asin"] = asin
        return {
            "tokensLeft": 900,
            "tokensConsumed": 10,
            "products": [MOCK_PRODUCT, MOCK_NO_BUYBOX],
        }

    monkeypatch.setattr(KeepaBackend, "_fetch_bestseller_asins", fake_bestsellers)
    monkeypatch.setattr(KeepaBackend, "_request", fake_request)

    products = backend.list_products(category_id=3828871, limit=10)
    # 詳細取得は最大10 ASIN（ハードキャップ）
    assert len(captured["asin"].split(",")) == 10
    # 返ってきた商品が AmazonProduct に正規化される
    assert all(p.asin for p in products)
    assert products[0].current_price == 9500
    assert backend.last_tokens_left == 900


def test_list_products_without_category_returns_empty():
    backend = KeepaBackend(api_key="dummy")
    assert backend.list_products() == []


def test_resolve_by_jan_not_live_raises():
    backend = KeepaBackend(api_key=None)
    backend.api_key = None
    try:
        backend.resolve_by_jan("4562344377072")
        assert False, "キー無しは例外を投げるべき"
    except RuntimeError:
        pass
