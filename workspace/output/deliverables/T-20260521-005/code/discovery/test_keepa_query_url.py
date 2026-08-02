"""keepa_query_url パーサのテスト（差分2・上級者向けURL貼り付け）。"""

import json

import pytest

from discovery.keepa_query_url import (
    KeepaQueryParseError,
    describe_selection,
    parse_keepa_query,
)

_SEL = {
    "current_SALES_gte": 50000,
    "current_SALES_lte": 150000,
    "current_COUNT_NEW_gte": 2,
    "current_NEW_gte": 3000,
    "categories_include": [3828871],
    "perPage": 50,
    "page": 0,
    "sort": [["current_SALES", "asc"]],
}


def test_parse_raw_json():
    sel = parse_keepa_query(json.dumps(_SEL))
    assert sel["current_SALES_gte"] == 50000
    assert sel["categories_include"] == [3828871]


def test_parse_full_keepa_url():
    from urllib.parse import quote

    url = (
        "https://api.keepa.com/query?key=ABC&domain=5&selection="
        + quote(json.dumps(_SEL))
    )
    sel = parse_keepa_query(url)
    assert sel["current_SALES_lte"] == 150000
    assert sel["current_NEW_gte"] == 3000


def test_parse_selection_fragment():
    sel = parse_keepa_query("selection=" + json.dumps(_SEL))
    assert sel["current_COUNT_NEW_gte"] == 2


def test_perpage_is_floored_to_50():
    sel = parse_keepa_query(json.dumps({"current_SALES_gte": 1, "perPage": 10}))
    assert sel["perPage"] == 50  # Keepa の最小 perPage 要件で補完
    assert sel["page"] == 0


def test_empty_input_raises():
    with pytest.raises(KeepaQueryParseError):
        parse_keepa_query("   ")


def test_url_without_selection_raises():
    with pytest.raises(KeepaQueryParseError):
        parse_keepa_query("https://api.keepa.com/query?key=ABC&domain=5")


def test_broken_json_raises():
    with pytest.raises(KeepaQueryParseError):
        parse_keepa_query("{ not valid json ")


def test_non_object_json_raises():
    with pytest.raises(KeepaQueryParseError):
        parse_keepa_query("[1, 2, 3]")


def test_parsed_selection_is_usable_by_find_products():
    """パース結果が find_products にそのまま渡せる（偽バックエンドで経路確認）。"""
    from discovery import pipeline
    from discovery.test_pipeline import _FakeFinderBackend, _amazon_product
    from adapters.yahoo_shopping import YahooShoppingClient

    sel = parse_keepa_query(json.dumps(_SEL))
    backend = _FakeFinderBackend([_amazon_product("B1", "原石 1個", 3980, jan="4900000000017")])
    products = backend.find_products(sel, limit=15)
    assert products and backend.last_selection == sel


def test_describe_selection_summarizes():
    txt = describe_selection({**_SEL, "current_AMAZON_lte": -1})
    assert "ランク" in txt and "在庫切れ" in txt
