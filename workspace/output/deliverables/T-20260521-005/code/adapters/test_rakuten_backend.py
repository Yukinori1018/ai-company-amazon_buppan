"""楽天アダプタ & 複数仕入元マージのテスト（モックのみ・実API/トークン不使用）。

検証ポイント:
  1. 楽天レスポンス（formatVersion=2）の正規化（名前/価格/URL/JAN/店舗/source）。
  2. JAN直指定検索で janCode 欠落を「問い合わせた JAN」で補完する。
  3. 本番に行けない条件（キー無し / RAKUTEN_REFERER 無し）でサンプルへ正直にフォールバック。
  4. 403/503 のHTTPエラー時にサンプルへフォールバックし last_error に理由を残す。
  5. MultiSupplierClient が同JANで「最も安い有効仕入値」を採用し source を保持する。
"""

import pytest

from adapters.multi_supplier import MultiSupplierClient
from adapters.rakuten_shopping import RakutenShoppingClient
from adapters.yahoo_shopping import YahooItem


# ---------------------------------------------------------------------------
# テスト用ダミー: 任意の YahooItem を返す仕入元クライアント（最安採用の検証用）。
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


# ---------------------------------------------------------------------------
# 1. 正規化
# ---------------------------------------------------------------------------
def test_rakuten_normalize_format_version_2():
    hits = [
        {
            "itemName": "テスト水筒 500ml",
            "itemPrice": 1180,
            "itemUrl": "https://item.rakuten.co.jp/x/y/",
            "shopName": "テスト店",
            "janCode": "4900000000024",
            "pointRate": 1,
            "mediumImageUrls": [{"imageUrl": "https://img/x.jpg"}],
        }
    ]
    items = RakutenShoppingClient._normalize(hits, is_sample=False)
    assert len(items) == 1
    it = items[0]
    assert isinstance(it, YahooItem)
    assert it.name == "テスト水筒 500ml"
    assert it.price == 1180
    assert it.url == "https://item.rakuten.co.jp/x/y/"
    assert it.store == "テスト店"
    assert it.jan == "4900000000024"
    assert it.image_url == "https://img/x.jpg"
    assert it.source == "楽天"  # 仕入元ラベルが付く（マージ時の識別に必須）
    assert it.is_sample is False


def test_rakuten_normalize_handles_string_image_array():
    """mediumImageUrls が文字列配列でも壊れない。"""
    hits = [{"itemName": "x", "itemPrice": 100, "itemUrl": "u",
             "shopName": "s", "mediumImageUrls": ["https://img/a.jpg"]}]
    items = RakutenShoppingClient._normalize(hits, is_sample=False)
    assert items[0].image_url == "https://img/a.jpg"


# ---------------------------------------------------------------------------
# 2. サンプル・フォールバックと is_live 判定
# ---------------------------------------------------------------------------
def test_not_live_without_keys_falls_back_to_sample(monkeypatch):
    monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("RAKUTEN_REFERER", raising=False)
    c = RakutenShoppingClient(app_id=None, access_key=None, referer=None)
    assert c.is_live is False
    items = c.search("水筒")
    assert items, "サンプルが返るはず"
    assert all(it.is_sample for it in items)
    assert "未設定" in (c.last_error or "")


def test_not_live_without_referer_even_with_keys():
    """キーが揃っても RAKUTEN_REFERER（登録ドメイン）が無ければ本番に行かない。"""
    c = RakutenShoppingClient(app_id="uuid", access_key="pk_x", referer=None)
    assert c.has_keys is True
    assert c.is_live is False  # 403を撒かないための honesty 判定
    c.search("水筒")
    assert "RAKUTEN_REFERER" in (c.last_error or "")


def test_force_sample_overrides_keys():
    c = RakutenShoppingClient(app_id="uuid", access_key="pk_x",
                              referer="https://example.test/", force_sample=True)
    assert c.is_live is False


# ---------------------------------------------------------------------------
# 3. 本番経路のエラーハンドリング（requests をモック）
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


def _make_live_client():
    return RakutenShoppingClient(app_id="uuid", access_key="pk_x",
                                 referer="https://shop.example/")


def _install_fake_requests(monkeypatch, fake_get):
    """関数内 `import requests` が拾うよう sys.modules に偽 requests を差し込む。"""
    import sys
    fake = type("R", (), {
        "get": staticmethod(fake_get),
        "RequestException": Exception,
    })
    monkeypatch.setitem(sys.modules, "requests", fake)


def test_live_403_referrer_falls_back_with_honest_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        # Referer/Origin が送られていることを確認（門番対応の肝）。
        assert headers["Referer"].startswith("https://shop.example")
        assert headers["Origin"] == "https://shop.example"
        return _FakeResp(403, {"errors": {"errorCode": 403,
                                          "errorMessage": "HTTP_REFERRER_NOT_ALLOWED"}})

    _install_fake_requests(monkeypatch, fake_get)
    c = _make_live_client()
    assert c.is_live is True
    items = c.search("水筒")  # 403 → サンプルへ正直にフォールバック
    assert all(it.is_sample for it in items)
    assert "REFERRER_NOT_ALLOWED" in c.last_error


def test_live_200_normalizes_and_backfills_jan(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        # JAN直指定検索では JAN がキーワードに入る（Ichiba Item Search に jan param が無いため）。
        assert params["keyword"] == "4900000000024"
        return _FakeResp(200, {"Items": [
            {"itemName": "水筒", "itemPrice": 1180,
             "itemUrl": "https://item.rakuten.co.jp/x/", "shopName": "s"}
            # janCode は返らない（API仕様）
        ]})

    _install_fake_requests(monkeypatch, fake_get)
    c = _make_live_client()
    items = c.search(jan_code="4900000000024")
    assert len(items) == 1
    assert items[0].jan == "4900000000024"  # 問い合わせたJANで補完される
    assert items[0].source == "楽天"
    assert c.last_error is None


# ---------------------------------------------------------------------------
# 4. 複数仕入元マージ（最安採用）
# ---------------------------------------------------------------------------
def _item(name, price, jan, source):
    return YahooItem(name=name, price=price, url=f"http://{source}/{jan}",
                     jan=jan, store=f"{source}店", source=source)


def test_multi_cheapest_wins_rakuten():
    yahoo = _StubSupplier([_item("水筒Y", 1280, "J1", "Yahoo")])
    rak = _StubSupplier([_item("水筒R", 1180, "J1", "楽天")])
    m = MultiSupplierClient([yahoo, rak])
    got = m.search(jan_code="J1")
    assert len(got) == 1
    assert got[0].source == "楽天"
    assert got[0].price == 1180  # 安い方を採用


def test_multi_cheapest_wins_yahoo():
    yahoo = _StubSupplier([_item("スプーンY", 880, "J2", "Yahoo")])
    rak = _StubSupplier([_item("スプーンR", 980, "J2", "楽天")])
    m = MultiSupplierClient([yahoo, rak])
    got = m.search(jan_code="J2")
    assert got[0].source == "Yahoo"
    assert got[0].price == 880


def test_multi_rakuten_only_jan_is_found():
    """Yahoo に無く楽天だけにある JAN も拾える（＝突合母数が広がる本丸）。"""
    yahoo = _StubSupplier([])  # Yahoo はこのJANを持たない
    rak = _StubSupplier([_item("ライトR", 1450, "J3", "楽天")])
    m = MultiSupplierClient([yahoo, rak])
    got = m.search(jan_code="J3")
    assert len(got) == 1
    assert got[0].source == "楽天"


def test_multi_no_match_returns_empty_not_fabricated():
    yahoo = _StubSupplier([])
    rak = _StubSupplier([])
    m = MultiSupplierClient([yahoo, rak])
    assert m.search(jan_code="JX") == []  # でっち上げず空


def test_multi_keyword_concat_sorted_by_price():
    yahoo = _StubSupplier([_item("水筒Y", 1280, "J1", "Yahoo")])
    rak = _StubSupplier([_item("水筒R", 1180, "J1b", "楽天")])
    m = MultiSupplierClient([yahoo, rak])
    got = m.search("水筒", results=10)
    assert len(got) == 2
    assert got[0].price <= got[1].price  # 安い順


def test_multi_one_supplier_failure_does_not_kill_search():
    class _Boom:
        is_live = True
        def search(self, *a, **k):
            raise RuntimeError("仕入元ダウン")
    good = _StubSupplier([_item("水筒", 1000, "J9", "Yahoo")])
    m = MultiSupplierClient([_Boom(), good])
    got = m.search(jan_code="J9")
    assert got and got[0].price == 1000  # 片方落ちても生き残る


def test_multi_live_sources_reports_only_live():
    live = _StubSupplier([], is_live=True)
    sample = _StubSupplier([], is_live=False)
    m = MultiSupplierClient([live, sample])
    assert m.is_live is True
    assert len(m.live_sources()) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
