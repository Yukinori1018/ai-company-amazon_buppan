"""
Keepa API アダプタ
- 公式 API: https://keepa.com/#!api
- 課金: Power-User Plan €49/月（社長が既に契約済み・PCローカルで使用中）
- KEEPA_API_KEY が未設定なら自動的にモックモード（USE_MOCK=True）
- KEEPA_API_KEY があれば実 API に接続

【重要】このクラウド/携帯セッションのコンテナは api.keepa.com への通信が
ネットワークポリシーで遮断されている（403）。実 API モードを携帯から動かすには、
環境のネットワーク許可リストに api.keepa.com を追加する必要がある（B案）。
PC ローカル実行では自宅回線が無制限のためそのまま動作する。

【要検証】実 API のレスポンス項目（価格の桁・monthlySold/salesRankDrops30 の
有無）は Keepa の仕様で揺れることがある。初回は必ず PC で live レスポンスを見て
_parse_product() / _yen() のマッピングを確認すること。
"""
import os
import json
from typing import Optional
from dataclasses import dataclass

import httpx

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "")
USE_MOCK = not KEEPA_API_KEY

# Amazon.co.jp の Keepa ドメイン ID は 5
KEEPA_DOMAIN_JP = 5
KEEPA_BASE = "https://api.keepa.com"
_HTTP_TIMEOUT = 30.0


@dataclass
class KeepaProduct:
    """Keepa から取得する商品データの正規化形式"""
    asin: str
    title: str
    image_emoji: str       # 実 API では絵文字の代わりに汎用アイコン（実画像URLは別途）
    price_amazon: int      # 現在の Amazon売値 (円)
    monthly_sales: int     # 月販（推定含む）
    drop_30: int           # 30日間の売れランクドロップ回数（販売の代理指標）


class KeepaError(RuntimeError):
    """Keepa API 呼び出し失敗"""


# ---------------------------------------------------------------------------
# モックデータ (KEEPA_API_KEY 未設定時のフォールバック)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 実 API 用ヘルパ
# ---------------------------------------------------------------------------
def _yen(raw: Optional[int]) -> int:
    """
    Keepa の価格整数を円に正規化。Keepa は「値なし」を -1 で返す。
    JPY は補助単位が無いため実運用では等倍（円）で返る。要検証: PC の live で
    桁を確認し、もし 100 倍で返るなら // 100 に切り替える。
    """
    if raw is None or raw < 0:
        return 0
    return int(raw)


def _parse_product(p: dict) -> KeepaProduct:
    """Keepa /product のレスポンス1件を KeepaProduct に変換"""
    asin = p.get("asin", "")
    title = p.get("title") or asin
    stats = p.get("stats") or {}

    # 価格: buyBoxPrice を優先、無ければ current[0]=AMAZON, current[1]=NEW
    price = stats.get("buyBoxPrice")
    if price is None or price < 0:
        current = stats.get("current") or []
        if len(current) > 0 and current[0] and current[0] > 0:
            price = current[0]
        elif len(current) > 1 and current[1] and current[1] > 0:
            price = current[1]
        else:
            price = -1
    price_amazon = _yen(price)

    # 月販: monthlySold（Amazon「過去1か月に購入」）
    monthly = stats.get("monthlySold")
    if monthly is None or monthly < 0:
        monthly = 0

    # ドロップ: salesRankDrops30（30日の売れランク下落回数＝販売の代理指標）
    drops = stats.get("salesRankDrops30")
    if drops is None or drops < 0:
        drops = 0

    return KeepaProduct(
        asin=asin,
        title=title,
        image_emoji="📦",   # 実 API は実画像を持つが、既存 UI は絵文字前提のため暫定
        price_amazon=price_amazon,
        monthly_sales=int(monthly),
        drop_30=int(drops),
    )


def _get(path: str, params: dict) -> dict:
    """Keepa API への GET。key/domain を自動付与。"""
    full = {"key": KEEPA_API_KEY, "domain": KEEPA_DOMAIN_JP, **params}
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(f"{KEEPA_BASE}/{path}", params=full)
    except httpx.HTTPError as e:
        # 携帯/クラウドから叩くと 403(ポリシー遮断) がここに来る
        raise KeepaError(f"Keepa への接続に失敗（回線遮断の可能性）: {e}") from e
    if resp.status_code != 200:
        raise KeepaError(f"Keepa API エラー {resp.status_code}: {resp.text[:200]}")
    return resp.json()


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------
def get_by_asin(asin: str) -> Optional[KeepaProduct]:
    """ASIN から商品を取得"""
    if USE_MOCK:
        return MOCK_DATA.get(asin)
    data = _get("product", {"asin": asin, "stats": 180, "buybox": 1})
    products = data.get("products") or []
    if not products:
        return None
    return _parse_product(products[0])


def find_profitable_products(
    min_monthly_sales: int = 5,
    min_drop_30: int = 5,
    per_page: int = 50,
) -> list[KeepaProduct]:
    """
    Keepa Product Finder 相当: 売れ筋商品を抽出。
    - モック時: 固定 8 件をフィルタ
    - 実 API 時: /query(Product Finder) で ASIN 一覧 → /product で詳細取得
    """
    if USE_MOCK:
        return [
            p for p in MOCK_DATA.values()
            if p.monthly_sales >= min_monthly_sales and p.drop_30 >= min_drop_30
        ]

    # Product Finder の抽出条件。フィールド名は Keepa 仕様準拠だが、初回は
    # PC の live で必ず結果件数を確認すること（要検証）。
    selection = {
        "monthlySold_gte": min_monthly_sales,
        "salesRankDrops30_gte": min_drop_30,
        "productType": [0, 1],
        "sort": [["salesRankDrops30", "desc"]],
        "page": 0,
        "perPage": per_page,
    }
    finder = _get("query", {"selection": json.dumps(selection, separators=(",", ":"))})
    asin_list = finder.get("asinList") or []
    if not asin_list:
        return []

    # 詳細をまとめて取得（Keepa は複数 ASIN をカンマ区切りで受け付ける）
    results: list[KeepaProduct] = []
    CHUNK = 20
    for i in range(0, len(asin_list), CHUNK):
        chunk = asin_list[i:i + CHUNK]
        data = _get("product", {"asin": ",".join(chunk), "stats": 180, "buybox": 1})
        for p in (data.get("products") or []):
            kp = _parse_product(p)
            if kp.monthly_sales >= min_monthly_sales and kp.drop_30 >= min_drop_30:
                results.append(kp)
    return results
