"""KeepaBackend の正規化ロジックのテスト（実 API は叩かず、実レスポンス断片のモックで検証）。

実行: code/ ディレクトリで `python -m pytest adapters/`

ここで使う mock JSON は 2026-06-05 にタカシが実 Keepa API（domain=5, stats=90, offers=20）で
取得した「水筒」商品レスポンスの構造をそのまま縮約したもの。価格は円そのまま、-1=データ無し。
"""

import pytest

from adapters import amazon_data
from adapters.amazon_data import (
    KeepaBackend,
    KeepaRateLimitError,
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


def test_resolve_many_no_positional_fallback(monkeypatch):
    """位置フォールバック撤去の回帰（社長報告 2026-06-06）。

    旧実装は eanList に問い合わせJANを含まない商品を、入力順×返却順の zip で別JANへ
    無理やり割り当てていた（別商品の誤突合の温床）。撤去後は eanList/upcList に
    実際に一致した商品だけが確定マッチとなり、一致しない問い合わせJANは欠落する。
    """
    backend = KeepaBackend(api_key="dummy")

    def fake_request(self, *, code):
        # 問い合わせは2件。返る商品は MOCK_PRODUCT(JAN=...072) のみ。
        # 旧バグなら 2件目の "4580502099086" が MOCK_PRODUCT に位置割り当てされてしまう。
        return {"tokensLeft": 100, "tokensConsumed": 5, "products": [MOCK_PRODUCT]}

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    result = backend.resolve_many(["4580502099086", "4562344377072"])
    # eanList に実在する 072 だけが確定マッチ。先頭の 086 は割り当てられない（欠落）。
    assert set(result.keys()) == {"4562344377072"}
    assert "4580502099086" not in result
    # jan の上書きも確定マッチに限定される（誤JANで上書きされない）。
    assert result["4562344377072"].jan == "4562344377072"


def test_resolve_many_jan_overwrite_only_on_confirmed_match(monkeypatch):
    """ap.jan の上書きは eanList 一致した確定マッチJANに限ることを保証する。"""
    backend = KeepaBackend(api_key="dummy")

    def fake_request(self, *, code):
        return {"tokensLeft": 100, "tokensConsumed": 5,
                "products": [MOCK_PRODUCT, MOCK_NO_BUYBOX]}

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    result = backend.resolve_many(["4562344377072", "4582532193901"])
    assert result["4562344377072"].jan == "4562344377072"
    assert result["4582532193901"].jan == "4582532193901"
    # 各商品が自分の eanList のJANに正しく紐づく（取り違えなし）。
    assert result["4562344377072"].asin == "B08VR99HJR"
    assert result["4582532193901"].asin == "B0BBQ3ZFCL"


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


def test_find_products_finder_flow(monkeypatch):
    """(あ)原石オートサーチ: Finder query→ASIN→詳細 の流れと ASIN上限15を検証（実APIは叩かない）。"""
    backend = KeepaBackend(api_key="dummy")

    captured = {}

    def fake_finder(self, selection):
        captured["selection"] = selection
        # Finder が条件合致 ASIN を20件返す（上限15で切られるはず）
        return [f"B{i:09d}" for i in range(20)]

    def fake_request(self, *, code=None, asin=None):
        captured["asin"] = asin
        return {
            "tokensLeft": 540,
            "tokensConsumed": 25,
            "products": [MOCK_PRODUCT, MOCK_NO_BUYBOX],
        }

    monkeypatch.setattr(KeepaBackend, "_fetch_finder_asins", fake_finder)
    monkeypatch.setattr(KeepaBackend, "_request", fake_request)

    selection = {
        "current_SALES_gte": 1000, "current_SALES_lte": 80000,
        "current_COUNT_NEW_gte": 2, "current_COUNT_NEW_lte": 10,
        "categories_include": [3828871], "perPage": 50, "page": 0,
    }
    products = backend.find_products(selection, limit=15)
    # 詳細取得は最大15 ASIN（ハードキャップ）
    assert len(captured["asin"].split(",")) == 15
    # selection がそのまま Finder に渡る
    assert captured["selection"]["current_SALES_lte"] == 80000
    assert all(p.asin for p in products)
    assert products[0].current_price == 9500
    assert backend.last_tokens_left == 540
    assert backend.last_tokens_consumed == 25


def test_find_products_empty_when_no_asins(monkeypatch):
    """Finder が0件なら詳細取得せず空リスト（でっち上げ無し）。"""
    backend = KeepaBackend(api_key="dummy")
    monkeypatch.setattr(KeepaBackend, "_fetch_finder_asins", lambda self, sel: [])
    called = {"request": False}

    def fake_request(self, *, code=None, asin=None):
        called["request"] = True
        return {"products": []}

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    assert backend.find_products({"perPage": 50}) == []
    assert called["request"] is False  # ASIN0件なら詳細コールしない＝トークン浪費しない


def test_find_products_caps_at_max_asins_per_list(monkeypatch):
    """limit 未指定でも MAX_ASINS_PER_LIST(15) を超えないこと。"""
    backend = KeepaBackend(api_key="dummy")
    monkeypatch.setattr(
        KeepaBackend, "_fetch_finder_asins",
        lambda self, sel: [f"B{i:09d}" for i in range(50)],
    )
    captured = {}

    def fake_request(self, *, code=None, asin=None):
        captured["asin"] = asin
        return {"tokensLeft": 1, "products": []}

    monkeypatch.setattr(KeepaBackend, "_request", fake_request)
    backend.find_products({"perPage": 50})  # limit 未指定
    assert len(captured["asin"].split(",")) == KeepaBackend.MAX_ASINS_PER_LIST


def test_list_products_without_category_returns_empty():
    backend = KeepaBackend(api_key="dummy")
    assert backend.list_products() == []


# ---------------------------------------------------------------------------
# 429（トークン上限）バックオフのテスト。requests と time.sleep をモックし、
# 実 API もスリープも発生させずにリトライ挙動だけを検証する。
# ---------------------------------------------------------------------------
class _FakeResp:
    """requests.Response の最小モック（status_code / json / headers / raise_for_status）。"""

    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"raise_for_status should not fire for {self.status_code}")


def _patch_request_env(monkeypatch, responses, *, no_sleep=True):
    """amazon_data 内の `import requests` / `time.sleep` を差し替えるヘルパ。

    responses は _FakeResp のリスト（呼ばれるたび先頭から順に返す）。
    """
    import sys
    import types

    calls = {"n": 0, "slept": [], "params": []}

    def fake_get(url, params=None, timeout=None):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        calls["params"].append(params or {})
        return responses[i]

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    if no_sleep:
        import time as _time
        monkeypatch.setattr(_time, "sleep", lambda s: calls["slept"].append(s))

    return calls


def test_request_retries_on_429_then_succeeds(monkeypatch):
    """429 を2回返した後に200で成功 → 例外を投げずに payload を返し、待機している。"""
    backend = KeepaBackend(api_key="dummy")
    responses = [
        _FakeResp(429, {"refillIn": 3000}),   # refillIn=3s → 4秒待つ想定
        _FakeResp(429, {}),                    # 本文無し → 指数バックオフ(10s)
        _FakeResp(200, {"tokensLeft": 50, "products": [MOCK_PRODUCT]}),
    ]
    calls = _patch_request_env(monkeypatch, responses)

    payload = backend._request(code="4562344377072")
    assert payload["tokensLeft"] == 50
    assert calls["n"] == 3            # 3回叩いた（429×2 + 成功）
    assert len(calls["slept"]) == 2   # 2回待機した
    assert calls["slept"][0] == 4     # refillIn 3000ms → +1s = 4s


def test_request_raises_rate_limit_error_after_retries_exhausted(monkeypatch):
    """429 が回復しない → リトライ尽きて KeepaRateLimitError を投げる（握りつぶさない）。"""
    backend = KeepaBackend(api_key="dummy")
    responses = [_FakeResp(429, {}, headers={"Retry-After": "7"})]  # 常に429
    calls = _patch_request_env(monkeypatch, responses)

    with pytest.raises(KeepaRateLimitError) as ei:
        backend._request(code="4562344377072")
    # 初回 + 3リトライ = 4回叩く / 待機は3回
    assert calls["n"] == len(KeepaBackend.RETRY_BACKOFFS_SEC) + 1
    assert len(calls["slept"]) == len(KeepaBackend.RETRY_BACKOFFS_SEC)
    assert ei.value.retry_after == 7  # Retry-After ヘッダを拾えている


def test_resolve_many_propagates_rate_limit_error(monkeypatch):
    """429 枯渇時、resolve_many は KeepaRateLimitError を呼び出し側へ伝播する（UI が混雑判別可能）。"""
    backend = KeepaBackend(api_key="dummy")
    responses = [_FakeResp(429, {})]
    _patch_request_env(monkeypatch, responses)
    with pytest.raises(KeepaRateLimitError):
        backend.resolve_many(["4562344377072"])


def test_offers_param_omitted_by_default(monkeypatch):
    """トークン節約 & Keepa仕様: offers は既定で **送らない**（0/1は invalidParameter で
    products が空になるバグの恒久対策）。必要値は stats=90 だけで揃う。"""
    # 既定は None（=送らない）。社長が踏んだ「(あ)が0件」の主因を回帰固定。
    assert KeepaBackend.OFFERS_PER_PRODUCT is None
    backend = KeepaBackend(api_key="dummy")
    calls = _patch_request_env(
        monkeypatch, [_FakeResp(200, {"tokensLeft": 50, "products": [MOCK_PRODUCT]})]
    )
    backend._request(asin="B0TEST")
    sent = calls["params"][0]
    assert "offers" not in sent, "offers は既定で送らない（0/1は無効）"
    assert sent["stats"] == 90  # stats は必須（buyBox/COUNT_NEW/OOS の供給源）


def test_offers_param_forwarded_when_set(monkeypatch):
    """明示的に20以上を設定した場合は offers が送られる（将来の拡張余地を担保）。"""
    backend = KeepaBackend(api_key="dummy")
    monkeypatch.setattr(backend, "OFFERS_PER_PRODUCT", 20)
    calls = _patch_request_env(
        monkeypatch, [_FakeResp(200, {"tokensLeft": 50, "products": [MOCK_PRODUCT]})]
    )
    backend._request(asin="B0TEST")
    assert calls["params"][0].get("offers") == 20


def test_retry_after_prefers_refill_in(monkeypatch):
    """_retry_after_seconds は refillIn(ms) を Retry-After より優先し、上限で頭打ちする。"""
    backend = KeepaBackend(api_key="dummy")
    # refillIn=2000ms → 3秒
    resp = _FakeResp(429, {"refillIn": 2000}, headers={"Retry-After": "99"})
    assert backend._retry_after_seconds(resp, 0) == 3
    # refillIn が巨大 → MAX_RETRY_WAIT_SEC で頭打ち
    big = _FakeResp(429, {"refillIn": 999999999})
    assert backend._retry_after_seconds(big, 0) == KeepaBackend.MAX_RETRY_WAIT_SEC


def test_resolve_by_jan_not_live_raises():
    backend = KeepaBackend(api_key=None)
    backend.api_key = None
    try:
        backend.resolve_by_jan("4562344377072")
        assert False, "キー無しは例外を投げるべき"
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# メーカー仕入れ用 brand/manufacturer マッピング（T-20260706-002（旧 T-20260706-001））。
# Keepa raw の brand/manufacturer を AmazonProduct に恒久搭載し、メーカー抽出を
# 再クエリなしで discover 出力から取れるようにした回帰テスト。
# ---------------------------------------------------------------------------
def test_product_to_amazon_maps_brand_and_manufacturer():
    prod = dict(MOCK_PRODUCT, brand="サーモス", manufacturer="THERMOS株式会社")
    ap = _product_to_amazon(prod)
    assert ap is not None
    assert ap.brand == "サーモス"
    assert ap.manufacturer == "THERMOS株式会社"
    # maker プロパティは brand を優先
    assert ap.maker == "サーモス"


def test_maker_falls_back_to_manufacturer_when_no_brand():
    prod = dict(MOCK_PRODUCT, manufacturer="THERMOS株式会社")
    prod.pop("brand", None)
    ap = _product_to_amazon(prod)
    assert ap is not None
    assert ap.brand is None
    assert ap.maker == "THERMOS株式会社"  # brand 無し → manufacturer にフォールバック


def test_maker_empty_when_both_absent():
    # 既存の MOCK_PRODUCT は brand/manufacturer を持たない（せどり用フローは未使用でも動く）。
    ap = _product_to_amazon(MOCK_PRODUCT)
    assert ap is not None
    assert ap.brand is None and ap.manufacturer is None
    assert ap.maker == ""  # 両方無ければ空文字（下流で "—" 表示）


def test_blank_brand_normalized_to_none():
    # 空白のみの brand は None に正規化して maker を素直にする。
    prod = dict(MOCK_PRODUCT, brand="   ", manufacturer="花王")
    ap = _product_to_amazon(prod)
    assert ap is not None
    assert ap.brand is None
    assert ap.maker == "花王"
