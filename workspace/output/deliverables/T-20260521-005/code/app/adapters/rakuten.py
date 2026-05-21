"""
楽天市場 商品検索 API アダプタ
- 公式: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
- 無料、ApplicationID 必須
- Phase 1 はモック。Phase 2 で実 API 接続
"""
import os
from typing import Optional
from dataclasses import dataclass

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
USE_MOCK = not RAKUTEN_APP_ID


@dataclass
class RakutenProduct:
    """楽天市場の商品データ"""
    asin_hint: str         # 紐付け用 (Phase 2 では JAN 経由で正確に)
    price: int
    url: str
    point_rate: int = 10   # 楽天 SPU 還元率 (%)


MOCK_DATA: dict[str, RakutenProduct] = {
    "B0CABC1234": RakutenProduct("B0CABC1234", 3500, "https://item.rakuten.co.jp/example/hp-100/", 10),
    "B0CGHI9012": RakutenProduct("B0CGHI9012", 32800, "https://item.rakuten.co.jp/example/sony-headphone/", 10),
    "B0CPQR1234": RakutenProduct("B0CPQR1234", 2400, "https://item.rakuten.co.jp/example/ts-3/", 7),
    "B0CVWX9012": RakutenProduct("B0CVWX9012", 1200, "https://item.rakuten.co.jp/example/wm-1/", 8),
}


def find_by_asin(asin: str) -> Optional[RakutenProduct]:
    """ASIN ヒントから楽天市場の該当商品を検索"""
    if USE_MOCK:
        return MOCK_DATA.get(asin)
    raise NotImplementedError("Phase 2 で楽天 API 実接続を実装")
