"""YahooShoppingClient のページング/正規化テスト（実 API は叩かず requests をモック）。

検証する性質:
1. results が20を超えると start オフセットで複数ページを取りに行く（突合母数を広げる肝）。
2. JAN直指定検索は1ページで止める（最安1件の入力に十分・無駄打ちしない）。
3. ページが尽きたら早期終了する（空ページで止まる）。
"""

from adapters.yahoo_shopping import YahooShoppingClient


class _FakeResp:
    status_code = 200

    def __init__(self, hits):
        self._hits = hits

    def raise_for_status(self):
        pass

    def json(self):
        return {"hits": self._hits}


def _make_hits(n, *, with_jan=True, base=0):
    """Yahoo v3 ItemSearch 形式の生 hits を n 件作る。"""
    out = []
    for i in range(n):
        idx = base + i
        out.append({
            "name": f"商品{idx}",
            "price": 1000 + idx,
            "url": f"https://store.example/{idx}",
            "janCode": f"49000000{idx:05d}" if with_jan else "",
        })
    return out


def test_pagination_fetches_multiple_pages(monkeypatch):
    """results=50 → 20件ページを start で複数回取りに行き、上限ページまで連結する。"""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params.get("start", 1))
        return _FakeResp(_make_hits(20, base=(params.get("start", 1) - 1)))

    monkeypatch.setitem(__import__("sys").modules, "requests", _fake_requests(fake_get))
    # time.sleep を無効化（テスト高速化）
    monkeypatch.setattr("time.sleep", lambda *_: None)

    client = YahooShoppingClient(app_id="DUMMY")
    items = client.search("水筒", results=50)
    # MAX_PAGES=3 までに制限され、20*3=60 を超えない範囲で 50 件返る。
    assert len(items) == 50
    # start は 1, 21, 41 と進んでいる（ページング発火の証拠）。
    assert calls == [1, 21, 41]


def test_jan_search_single_page(monkeypatch):
    """JAN直指定は1ページのみ（無駄打ちしない）。"""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params.get("start", 1))
        return _FakeResp(_make_hits(20, base=0))

    monkeypatch.setitem(__import__("sys").modules, "requests", _fake_requests(fake_get))
    monkeypatch.setattr("time.sleep", lambda *_: None)

    client = YahooShoppingClient(app_id="DUMMY")
    client.search(jan_code="4900000000017", results=50)
    assert calls == [1]  # 1ページで止まる


def test_pagination_stops_on_short_page(monkeypatch):
    """ページが20件未満で返ったら、それ以上ページを取りに行かない（早期終了）。"""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params.get("start", 1))
        # 1ページ目で5件しか返らない（在庫がそれだけ）。
        return _FakeResp(_make_hits(5, base=0))

    monkeypatch.setitem(__import__("sys").modules, "requests", _fake_requests(fake_get))
    monkeypatch.setattr("time.sleep", lambda *_: None)

    client = YahooShoppingClient(app_id="DUMMY")
    items = client.search("ニッチ商品", results=50)
    assert len(items) == 5
    assert calls == [1]  # 短いページで打ち切り


class _FakeRequestsModule:
    def __init__(self, getter):
        self.get = getter


def _fake_requests(getter):
    return _FakeRequestsModule(getter)
