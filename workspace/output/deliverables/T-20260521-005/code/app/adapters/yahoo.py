"""
Yahoo!ショッピング Web API アダプタ
- 公式: https://developer.yahoo.co.jp/webapi/shopping/
- 無料、ClientID 必須（50,000req/日）
- Phase 1 はモック。Phase 2 で実 API 接続
"""
import os
from typing import Optional
from dataclasses import dataclass

YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")
USE_MOCK = not YAHOO_APP_ID


@dataclass
class YahooProduct:
    """Yahoo!ショッピングの商品データ"""
    asin_hint: str
    price: int
    url: str
    point_rate: int = 8  # PayPay 還元率 (%)


MOCK_DATA: dict[str, YahooProduct] = {
    "B0CDEF5678": YahooProduct("B0CDEF5678", 9200, "https://store.shopping.yahoo.co.jp/example/mg-pro.html", 8),
    "B0CJKL3456": YahooProduct("B0CJKL3456", 3800, "https://store.shopping.yahoo.co.jp/example/hm-20.html", 5),
    "B0CMNO7890": YahooProduct("B0CMNO7890", 1500, "https://store.shopping.yahoo.co.jp/example/mask-30.html", 12),
    "B0CSTU5678": YahooProduct("B0CSTU5678", 4200, "https://store.shopping.yahoo.co.jp/example/protein-1kg.html", 10),
}


def find_by_asin(asin: str) -> Optional[YahooProduct]:
    """ASIN ヒントから Yahoo!ショッピングの該当商品を検索"""
    if USE_MOCK:
        return MOCK_DATA.get(asin)
    raise NotImplementedError("Phase 2 で Yahoo! API 実接続を実装")
