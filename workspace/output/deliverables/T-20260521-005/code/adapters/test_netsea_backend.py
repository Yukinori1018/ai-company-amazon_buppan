"""NETSEA(卸)アダプタ & 3仕入元マージのテスト（モックのみ・実API/トークン不使用）。

検証ポイント:
  1. NETSEA /items レスポンス（set[] 入れ子）の正規化（名前/卸価格/URL/JAN/店舗/source）。
  2. set[] から「在庫あり×卸価格最安」の規格を採用する。
  3. 全規格品切れの商品は price=0（突合対象外）になる。
  4. トークン未設定でサンプルへ正直にフォールバック（last_error に理由）。
  5. 本番経路: 200正常 / 401・error フォーマット時にサンプルへフォールバックし last_error を残す。
  6. JAN無しキーワードは本番でもサンプル粗集め（/items にフリーワード検索が無いため）。
  7. MultiSupplierClient が Yahoo+楽天+NETSEA の3本で同JAN最安を採用（卸が最安で勝つ）。
"""

import pytest

from adapters.multi_supplier import MultiSupplierClient
from adapters.netsea import NetseaClient
from adapters.yahoo_shopping import YahooItem


# ---------------------------------------------------------------------------
# 1〜3. 正規化（set[] の最安在庫採用・品切れ除外）
# ---------------------------------------------------------------------------
def test_netsea_normalize_picks_cheapest_in_stock_set():
    rows = [
        {
            "supplier_id": 1000,
            "product_id": "P1",
            "product_url": "https://www.netsea.jp/shop/1000/@p1",
            "product_name": "テスト卸Tシャツ",
            "shop_name": "卸ショップ",
            "jan_code": "4900000000024",
            "image_url_1": "https://img/x.jpg",
            "set": [
                {"direct_item_id": "1000-1", "jan_code": "4900000000024",
                 "reference_price": 1800, "price": 900, "sold_out_flag": "N"},
                {"direct_item_id": "1000-2", "jan_code": "4900000000024",
                 "reference_price": 1800, "price": 700, "sold_out_flag": "N"},  # 最安
                {"direct_item_id": "1000-3", "jan_code": "4900000000024",
                 "reference_price": 1800, "price": 500, "sold_out_flag": "Y"},  # 品切れ→除外
            ],
        }
    ]
    items = NetseaClient._normalize(rows, is_sample=False)
    assert len(items) == 1
    it = items[0]
    assert isinstance(it, YahooItem)
    assert it.name == "テスト卸Tシャツ"
    assert it.price == 700  # 在庫あり最安（500は品切れなので不採用）
    assert it.url == "https://www.netsea.jp/shop/1000/@p1"
    assert it.jan == "4900000000024"
    assert it.store == "卸ショップ"
    assert it.image_url == "https://img/x.jpg"
    assert it.source == "NETSEA"
    assert it.is_sample is False


def test_netsea_normalize_all_sold_out_sets_price_zero():
    rows = [{
        "product_name": "品切れ商品", "product_url": "u", "shop_name": "s",
        "jan_code": "4900000000017",
        "set": [{"direct_item_id": "1-1", "price": 800, "sold_out_flag": "Y"}],
    }]
    items = NetseaClient._normalize(rows, is_sample=False)
    assert items[0].price == 0  # 突合対象外（でっち上げない）


def test_netsea_normalize_jan_from_set_preferred():
    """set[].jan_code を優先（規格ごとに正しい）。"""
    rows = [{
        "product_name": "x", "product_url": "u", "shop_name": "s",
        "jan_code": "1111",
        "set": [{"price": 100, "jan_code": "2222", "sold_out_flag": "N"}],
    }]
    items = NetseaClient._normalize(rows, is_sample=False)
    assert items[0].jan == "2222"


# ---------------------------------------------------------------------------
# 4. トークン未設定のフォールバック & is_live
# ---------------------------------------------------------------------------
def test_not_live_without_token_falls_back_to_sample(monkeypatch):
    monkeypatch.delenv("NETSEA_API_TOKEN", raising=False)
    c = NetseaClient(token=None)
    assert c.is_live is False
    items = c.search(jan_code="4900000000024")
    assert items, "サンプルが返るはず"
    assert all(it.is_sample for it in items)
    assert all(it.source == "NETSEA" for it in items)
    assert "NETSEA_API_TOKEN" in (c.last_error or "")


def test_force_sample_overrides_token():
    c = NetseaClient(token="tok", force_sample=True)
    assert c.is_live is False


def test_sample_filter_by_jan():
    c = NetseaClient(token=None)
    items = c.search(jan_code="4900000000055")  # サンプルのプロテイン
    assert len(items) == 1
    assert items[0].jan == "4900000000055"


def test_sample_price_range_filter():
    c = NetseaClient(token=None)
    cheap = c.search(query="", price_to=600)  # 卸 <=600 のみ（サンプル: スプーン540）
    assert cheap
    assert all(it.price <= 600 for it in cheap)


# ---------------------------------------------------------------------------
# 5. 本番経路（requests をモック）
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _default_fake_get(url, headers=None, timeout=None):
    """GET /suppliers の既定スタブ（承認済みサプライヤー2社を返す）。

    /items は jan_code 単独だと 400 になるため、アダプタは先に /suppliers を引いて
    supplier_ids を埋める。本番経路テストはこの GET も必要。
    """
    assert url.endswith("/buyer/v1/suppliers")
    return _FakeResp(200, {"data": [
        {"id": 1000, "corp_name": "卸A", "trade_name": "卸A 株式会社"},
        {"id": 2000, "corp_name": "卸B", "trade_name": "卸B 株式会社"},
    ]})


def _install_fake_requests(monkeypatch, fake_post, fake_get=None):
    import sys
    fake = type("R", (), {
        "post": staticmethod(fake_post),
        "get": staticmethod(fake_get or _default_fake_get),
        "RequestException": Exception,
    })
    monkeypatch.setitem(sys.modules, "requests", fake)


def test_live_200_normalizes(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        # Bearer トークンがヘッダに乗る（NETSEA認証方式）。
        assert headers["Authorization"] == "Bearer tok123"
        assert url.endswith("/buyer/v1/items")
        assert data["jan_code"] == "4900000000024"
        # jan_code 単独は 400 になるため supplier_ids が同時指定されること。
        assert data.get("supplier_ids")
        return _FakeResp(200, {"data": [
            {"product_name": "卸水筒", "product_url": "https://www.netsea.jp/x",
             "shop_name": "卸店", "jan_code": "4900000000024",
             "set": [{"price": 650, "jan_code": "4900000000024", "sold_out_flag": "N"}]}
        ]})

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok123")
    assert c.is_live is True
    items = c.search(jan_code="4900000000024")
    assert len(items) == 1
    assert items[0].price == 650
    assert items[0].source == "NETSEA"
    assert items[0].is_sample is False
    assert c.last_error is None


def test_live_401_falls_back_with_honest_error(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        return _FakeResp(401, {"error": {"code": 1, "subcode": 401,
                                         "message": "Unauthenticated."}})

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="bad")
    items = c.search(jan_code="4900000000024")
    assert all(it.is_sample for it in items)  # 401 → サンプルへ正直に
    assert "401" in (c.last_error or "")


def test_live_error_payload_falls_back(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        return _FakeResp(200, {"error": {"code": 2, "subcode": 400,
                                         "message": "param error"}})

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items = c.search(jan_code="9999999999999")
    assert all(it.is_sample for it in items)
    assert "param error" in (c.last_error or "")


def test_live_empty_list_payload_returns_empty(monkeypatch):
    """ヒット0件の /items は素の `[]`（JSON配列）を返す実挙動。クラッシュせず空を返す。"""
    def fake_post(url, data=None, headers=None, timeout=None):
        return _FakeResp(200, [])  # dict ではなく素の配列

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items = c.search(jan_code="9999999999999")
    assert items == []          # 全バッチ正常でヒット0 → 正直に空（サンプルに逃げない）
    assert c.last_error is None


def test_suppliers_failure_falls_back_to_sample(monkeypatch):
    """GET /suppliers が落ちたら（権限/通信）サンプルへ正直にフォールバック。"""
    def fake_get(url, headers=None, timeout=None):
        return _FakeResp(401, {"error": {"code": 1, "message": "Unauthenticated."}})

    def fake_post(url, data=None, headers=None, timeout=None):
        raise AssertionError("/suppliers が落ちたら /items は呼ばない")

    _install_fake_requests(monkeypatch, fake_post, fake_get=fake_get)
    c = NetseaClient(token="tok")
    items = c.search(jan_code="4900000000024")
    assert all(it.is_sample for it in items)
    assert "401" in (c.last_error or "")


def test_live_keyword_without_jan_uses_sample(monkeypatch):
    """JAN無しキーワードは本番でも /items にフリーワード検索が無いためサンプル粗集め。"""
    called = {"post": False}

    def fake_post(url, data=None, headers=None, timeout=None):
        called["post"] = True
        return _FakeResp(200, {"data": []})

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items = c.search(query="水筒")  # JAN無し
    assert called["post"] is False  # 本番は叩かない（仕様上当てられない）
    assert all(it.is_sample for it in items)


# ---------------------------------------------------------------------------
# 6. 3仕入元マージ（NETSEA卸が最安で勝つ）
# ---------------------------------------------------------------------------
class _StubSupplier:
    def __init__(self, items, *, is_live=False):
        self._items = items
        self.is_live = is_live

    def search(self, query="", *, results=20, price_from=None, price_to=None, jan_code=None):
        if jan_code:
            return [it for it in self._items if it.jan == jan_code]
        if query:
            return [it for it in self._items if query.lower() in it.name.lower()]
        return list(self._items)


def _item(name, price, jan, source):
    return YahooItem(name=name, price=price, url=f"http://{source}/{jan}",
                     jan=jan, store=f"{source}店", source=source)


def test_multi_netsea_wholesale_cheapest_wins():
    yahoo = _StubSupplier([_item("水筒Y", 1280, "J1", "Yahoo")])
    rak = _StubSupplier([_item("水筒R", 1180, "J1", "楽天")])
    netsea = _StubSupplier([_item("水筒N(卸)", 760, "J1", "NETSEA")])
    m = MultiSupplierClient([yahoo, rak, netsea])
    got = m.search(jan_code="J1")
    assert len(got) == 1
    assert got[0].source == "NETSEA"
    assert got[0].price == 760  # 卸が最安で勝つ


def test_multi_netsea_only_jan_is_found():
    """Yahoo/楽天に無く NETSEA だけにある JAN も拾える（突合母数の拡大）。"""
    m = MultiSupplierClient([
        _StubSupplier([]), _StubSupplier([]),
        _StubSupplier([_item("卸限定品", 900, "JN", "NETSEA")]),
    ])
    got = m.search(jan_code="JN")
    assert len(got) == 1
    assert got[0].source == "NETSEA"


def test_multi_real_default_includes_netsea(monkeypatch):
    """pipeline.default_supplier_client() が NETSEA を含む3本になっている。"""
    monkeypatch.delenv("YAHOO_APP_ID", raising=False)
    monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)
    monkeypatch.delenv("NETSEA_API_TOKEN", raising=False)
    from discovery import pipeline
    supplier = pipeline.default_supplier_client()
    sources = {type(c).__name__ for c in supplier.clients}
    assert "NetseaClient" in sources
    assert len(supplier.clients) == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
