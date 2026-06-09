"""(う)卸起点ディスカバリーの単体テスト（NETSEA・Keepa はモック、実API不使用）。

検証ポイント:
  1. 棚卸し→JAN集約（同JAN最安）→Amazon突合→ランキング化の基本フロー。
  2. 上限（max_suppliers / max_items_per_supplier / max_jan_lookups）が効き、
     coverage に走査社数・取得商品数・突合数・未処理・打ち切りフラグが正直に乗る。
  3. NETSEAページングのエラー（4xx/通信失敗）が coverage.notes に握りつぶさず残る。
  4. 既存ガード（数量ミスマッチ／別商品の疑い）が卸起点でも適用される。
  5. NETSEAアダプタの list_supplier_items が next_direct_item_id でページングし、
     上限で打ち切ったとき truncated=True を返す。
"""

import pytest

from adapters.netsea import NetseaClient
from adapters.yahoo_shopping import YahooItem
from calc import profit
from discovery import pipeline


# ---------------------------------------------------------------------------
# テスト用フェイク
# ---------------------------------------------------------------------------
class _FakeNetsea:
    """NetseaClient の棚卸しAPI（list_suppliers / list_supplier_items）を差し替えるフェイク。"""

    def __init__(self, suppliers, items_by_supplier, *, item_cov_extra=None):
        self._suppliers = suppliers
        self._items = items_by_supplier
        self._cov_extra = item_cov_extra or {}
        self.last_error = None

    def list_suppliers(self):
        return self._suppliers

    def list_supplier_items(self, supplier_id, *, max_items=100, sleep_sec=0.0):
        items = self._items.get(supplier_id, [])
        truncated = len(items) > max_items
        cov = {
            "requested": max_items, "fetched": min(len(items), max_items),
            "pages": 1, "truncated": truncated,
            "error": self._cov_extra.get(supplier_id), "sample": False,
        }
        return items[:max_items], cov


class _FakeKeepa:
    """resolve_many をモックする Keepa バックエンド。JAN→AmazonProduct の辞書を返す。"""

    MAX_JANS_PER_CALL = 10

    def __init__(self, by_jan, *, tokens_each=12):
        self._by_jan = by_jan
        self.tokens_each = tokens_each
        self.last_tokens_consumed = None
        self.last_tokens_left = 1000

    def resolve_many(self, jans):
        self.last_tokens_consumed = self.tokens_each
        self.last_tokens_left -= self.tokens_each
        return {j: self._by_jan[j] for j in jans if j in self._by_jan}


def _ap(asin, jan, title, price):
    from adapters.amazon_data import AmazonProduct

    return AmazonProduct(
        asin=asin, title=title, current_price=price,
        category_key="default", size_key="standard_1",
        monthly_sales=120, sales_rank=30000, offer_count=3, oos_rate_90d=0.1,
        jan=jan, is_sample=False,
    )


def _ns_item(name, price, jan, supplier="NETSEA店"):
    return YahooItem(name=name, price=price, url=f"https://www.netsea.jp/@{jan}",
                     jan=jan, store=supplier, source="NETSEA")


# ---------------------------------------------------------------------------
# 1. 基本フロー: 棚卸し→突合→ランキング
# ---------------------------------------------------------------------------
def test_netsea_discovery_basic_flow_and_ranking():
    suppliers = [{"id": 1000, "name": "卸A"}, {"id": 1001, "name": "卸B"}]
    items = {
        1000: [_ns_item("ステンレス水筒 500ml", 700, "J1")],
        1001: [_ns_item("アロマディフューザー 300ml", 1200, "J2")],
    }
    fake_ns = _FakeNetsea(suppliers, items)
    fake_keepa = _FakeKeepa({
        "J1": _ap("A1", "J1", "ステンレス水筒 500ml 真空断熱", 2200),
        "J2": _ap("A2", "J2", "アロマディフューザー 300ml 木目調", 2600),
    })

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa,
        preset_key="hunting_beginner",
    )
    assert len(rows) == 2
    # 卸価格が仕入値に入っている。
    prices = {r.supplier_price for r in rows}
    assert 700 in prices
    assert all(r.supplier_source == "NETSEA" for r in rows)
    # 利益降順で並ぶ。
    assert rows[0].net_profit >= rows[1].net_profit
    # カバレッジ
    assert cov.total_suppliers == 2
    assert cov.scanned_suppliers == 2
    assert cov.fetched_items == 2
    assert cov.jan_items == 2
    assert cov.matched_jans == 2
    assert cov.remaining_suppliers == 0
    assert cov.truncated is False
    assert cov.keepa_tokens_consumed == 12  # 1バッチ=12トークン


# ---------------------------------------------------------------------------
# 2. 上限とカバレッジ
# ---------------------------------------------------------------------------
def test_max_suppliers_limits_and_reports_remaining():
    suppliers = [{"id": i, "name": f"卸{i}"} for i in range(5)]
    items = {i: [_ns_item(f"商品{i}", 500, f"J{i}")] for i in range(5)}
    fake_ns = _FakeNetsea(suppliers, items)
    fake_keepa = _FakeKeepa({
        f"J{i}": _ap(f"A{i}", f"J{i}", f"商品{i}", 1500) for i in range(5)
    })

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa, max_suppliers=2,
    )
    assert cov.total_suppliers == 5
    assert cov.scanned_suppliers == 2
    assert cov.remaining_suppliers == 3
    assert cov.truncated is True
    assert cov.fetched_items == 2  # 2社分しか棚卸ししない


def test_max_jan_lookups_caps_keepa_and_truncates():
    suppliers = [{"id": 1000, "name": "卸A"}]
    items = {1000: [_ns_item(f"商品{i}", 400, f"J{i}") for i in range(25)]}
    fake_ns = _FakeNetsea(suppliers, items)
    by_jan = {f"J{i}": _ap(f"A{i}", f"J{i}", f"商品{i}", 1200) for i in range(25)}
    fake_keepa = _FakeKeepa(by_jan)

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa,
        max_items_per_supplier=100, max_jan_lookups=10,
    )
    # JAN突合は10件で打ち切り。
    assert cov.jan_items == 25       # 棚卸しでJANは25件取れたが
    assert cov.keepa_lookups == 10   # Keepaへは10件のみ問い合わせ
    assert cov.matched_jans == 10
    assert cov.truncated is True
    assert len(rows) == 10


def test_jan_dedup_cheapest_wins_across_suppliers():
    """同一JANが複数サプライヤーから出たら最安卸1件に集約される。"""
    suppliers = [{"id": 1000, "name": "卸A"}, {"id": 1001, "name": "卸B"}]
    items = {
        1000: [_ns_item("水筒(高)", 900, "JX")],
        1001: [_ns_item("水筒(安)", 600, "JX")],  # 同JANで最安
    }
    fake_ns = _FakeNetsea(suppliers, items)
    fake_keepa = _FakeKeepa({"JX": _ap("AX", "JX", "水筒 真空断熱", 2000)})

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa,
    )
    assert cov.jan_items == 1          # 重複排除で1件
    assert len(rows) == 1
    assert rows[0].supplier_price == 600  # 最安卸が採用される


# ---------------------------------------------------------------------------
# 3. エラーは握りつぶさず coverage.notes に残す
# ---------------------------------------------------------------------------
def test_supplier_fetch_error_recorded_in_coverage():
    suppliers = [{"id": 1000, "name": "卸A"}, {"id": 1001, "name": "卸B"}]
    items = {1000: [_ns_item("商品", 500, "J1")], 1001: []}
    fake_ns = _FakeNetsea(
        suppliers, items, item_cov_extra={1001: "NETSEA API 400（権限なし）"}
    )
    fake_keepa = _FakeKeepa({"J1": _ap("A1", "J1", "商品 標準", 1500)})

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa,
    )
    assert any("400" in n for n in cov.notes)


# ---------------------------------------------------------------------------
# 4. 既存ガード（別商品の疑い）が卸起点でも効く
# ---------------------------------------------------------------------------
def test_suspect_mismatch_guard_applies():
    suppliers = [{"id": 1000, "name": "卸A"}]
    # 仕入元名とAmazon名がかけ離れる → 別商品の疑いで隔離（利益数値を出さない）。
    items = {1000: [_ns_item("シリコン調理スプーン 5本", 540, "JM")]}
    fake_ns = _FakeNetsea(suppliers, items)
    fake_keepa = _FakeKeepa({
        "JM": _ap("AM", "JM", "高級腕時計 自動巻き メンズ", 50000),
    })

    rows, cov = pipeline.discover_from_netsea(
        netsea_client=fake_ns, amazon_backend=fake_keepa,
    )
    assert len(rows) == 1
    assert rows[0].match_status == pipeline.MATCH_SUSPECT_MISMATCH
    assert rows[0].net_profit == 0.0  # でっち上げない


# ---------------------------------------------------------------------------
# 5. NETSEAアダプタの list_supplier_items ページング（requests モック）
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _install_fake_requests(monkeypatch, fake_post, fake_get=None):
    import sys

    def _default_get(url, headers=None, timeout=None):
        return _FakeResp(200, {"data": [{"id": 1000}]})

    fake = type("R", (), {
        "post": staticmethod(fake_post),
        "get": staticmethod(fake_get or _default_get),
        "RequestException": Exception,
    })
    monkeypatch.setitem(sys.modules, "requests", fake)


def test_list_supplier_items_paginates_with_next_id(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls["n"] += 1
        if "next_direct_item_id" not in data:
            # 1ページ目: 2件 + next_id
            return _FakeResp(200, {
                "data": [
                    {"product_name": "p1", "product_url": "u1", "shop_name": "s",
                     "set": [{"price": 100, "jan_code": "J1", "sold_out_flag": "N"}]},
                    {"product_name": "p2", "product_url": "u2", "shop_name": "s",
                     "set": [{"price": 200, "jan_code": "J2", "sold_out_flag": "N"}]},
                ],
                "next_direct_item_id": "999",
            })
        # 2ページ目: 1件 + next_id 無し（終端）
        return _FakeResp(200, {
            "data": [
                {"product_name": "p3", "product_url": "u3", "shop_name": "s",
                 "set": [{"price": 300, "jan_code": "J3", "sold_out_flag": "N"}]},
            ],
        })

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items, cov = c.list_supplier_items(1000, max_items=100, sleep_sec=0.0)
    assert calls["n"] == 2          # 2ページ辿った
    assert len(items) == 3
    assert cov["pages"] == 2
    assert cov["truncated"] is False
    assert cov["error"] is None


def test_list_supplier_items_truncates_at_max(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        # 常に2件 + next_id（無限に続く体）→ 上限で打ち切る。
        return _FakeResp(200, {
            "data": [
                {"product_name": "p", "product_url": "u", "shop_name": "s",
                 "set": [{"price": 100, "jan_code": "J", "sold_out_flag": "N"}]},
                {"product_name": "p", "product_url": "u", "shop_name": "s",
                 "set": [{"price": 100, "jan_code": "J", "sold_out_flag": "N"}]},
            ],
            "next_direct_item_id": "next",
        })

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items, cov = c.list_supplier_items(1000, max_items=3, sleep_sec=0.0)
    assert len(items) == 3
    assert cov["truncated"] is True   # 上限到達かつ続きあり


def test_list_supplier_items_http_error_recorded(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        return _FakeResp(400, {"error": {"code": 2, "message": "param error"}})

    _install_fake_requests(monkeypatch, fake_post)
    c = NetseaClient(token="tok")
    items, cov = c.list_supplier_items(1000, max_items=50, sleep_sec=0.0)
    assert items == []
    assert cov["error"] is not None
    assert "400" in cov["error"]


def test_list_suppliers_not_live_uses_sample(monkeypatch):
    monkeypatch.delenv("NETSEA_API_TOKEN", raising=False)
    c = NetseaClient(token=None)
    suppliers = c.list_suppliers()
    assert suppliers  # サンプル擬似一覧
    assert all("id" in s and "name" in s for s in suppliers)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
