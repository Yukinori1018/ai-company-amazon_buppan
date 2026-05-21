"""
Keepa API アダプタ
- 公式 API: https://keepa.com/#!api
- 課金: Power-User Plan €49/月（§4.1 承認後）
- Phase 1 ではモック実装。Phase 2 で実 API 接続
"""
import os
from typing import Optional
from dataclasses import dataclass

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "")
USE_MOCK = not KEEPA_API_KEY


@dataclass
class KeepaProduct:
    """Keepa から取得する商品データの正規化形式"""
    asin: str
    title: str
    image_emoji: str       # Phase 2 では実画像 URL に置き換え
    price_amazon: int      # 現在の Amazon売値 (円)
    monthly_sales: int     # 月販
    drop_30: int           # 30日間ドロップ回数


# Phase 1 モックデータ (8件 — モック HTML と同じセット)
MOCK_DATA: dict[str, KeepaProduct] = {
    "B0CABC1234": KeepaProduct("B0CABC1234", "山田電機 ホットプレート HP-100", "🍳", 6980, 45, 28),
    "B0CDEF5678": KeepaProduct("B0CDEF5678", "ABC社 マッサージガン MG-Pro", "💆", 12800, 18, 11),
    "B0CGHI9012": KeepaProduct("B0CGHI9012", "Sony WH-1000XM5 ヘッドホン", "🎧", 41800, 24, 18),
    "B0CJKL3456": KeepaProduct("B0CJKL3456", "AA社 ハイブリッド加湿器 HM-20", "💧", 4200, 3, 2),
    "B0CMNO7890": KeepaProduct("B0CMNO7890", "ZZ コスメ シートマスク 30枚入", "💄", 2800, 80, 45),
    "B0CPQR1234": KeepaProduct("B0CPQR1234", "AAA社 ポップアップトースター TS-3", "🍞", 3480, 8, 5),
    "B0CSTU5678": KeepaProduct("B0CSTU5678", "BBB プロテイン 1kg バニラ", "💪", 6800, 55, 32),
    "B0CVWX9012": KeepaProduct("B0CVWX9012", "CCC ワイヤレスマウス WM-1", "🖱", 1890, 15, 9),
}


def get_by_asin(asin: str) -> Optional[KeepaProduct]:
    """ASIN から商品を取得"""
    if USE_MOCK:
        return MOCK_DATA.get(asin)
    raise NotImplementedError("Phase 2 で Keepa 実 API 接続を実装")


def find_profitable_products(
    min_monthly_sales: int = 5,
    min_drop_30: int = 5,
) -> list[KeepaProduct]:
    """
    Keepa Product Finder 相当: 売れ筋商品を抽出。
    Phase 1 はモック。Phase 2 で Keepa Product Finder API を実装。
    """
    if USE_MOCK:
        return [
            p for p in MOCK_DATA.values()
            if p.monthly_sales >= min_monthly_sales and p.drop_30 >= min_drop_30
        ]
    raise NotImplementedError("Phase 2 で Keepa Product Finder API を実装")
