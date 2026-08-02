"""Keepa API ラッパー —— 第2層用スタブ（実装は TODO）。

⚠️ このファイルは「インターフェース定義のみ」です。実際の API 呼び出しはしません。
   Keepa は有料（€49/月）で、課金は CLAUDE.md §4.1（社長承認必須）に該当します。
   承認が下りたら fetch_product の TODO を埋めてください。

設計方針（タカシ）:
- ロックインを避けるため、profit.py（第1層）は Keepa を一切知らない。
- 第2層は「Keepa からデータを取る → profit.ProfitInput に詰める」だけを担当。
- 差し替え可能性のため、戻り値は Keepa 固有形式ではなく自前の dataclass に正規化する。
- シークレット（APIキー）はコードに書かない。環境変数 KEEPA_API_KEY から読む。
"""

import os
from dataclasses import dataclass
from typing import Optional


# Amazon.co.jp の Keepa ドメインID（参考: 5 = co.jp）。実呼び出し時に使う。
KEEPA_DOMAIN_JP = 5


@dataclass
class KeepaProduct:
    """Keepa から取得したデータを自前形式に正規化したもの。

    第1層の profit.ProfitInput とは別物。to_profit_inputs() で橋渡しする。
    """

    asin: str
    title: str
    current_price: Optional[float]      # 現在のAmazon価格（円・税込）
    avg_price_90d: Optional[float]      # 90日平均価格（円）
    sales_rank: Optional[int]           # 現在の売れ筋ランキング
    monthly_sales_estimate: Optional[int]  # 推定月間販売数
    category_key: str = "default"       # fees.py のカテゴリキーに正規化済み
    size_key: str = "standard_1"        # fees.py のサイズキーに正規化済み


class KeepaClient:
    """Keepa API クライアント（スタブ）。

    使い方（実装後）:
        client = KeepaClient()              # 環境変数 KEEPA_API_KEY を読む
        product = client.fetch_product("B0XXXXXXX")
        inp = product_to_profit_input(product, wholesale_price=1000)
        result = profit.calculate(inp)
    """

    def __init__(self, api_key: Optional[str] = None):
        # シークレットは環境変数優先。引数は主にテスト差し込み用。
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY")

    @property
    def is_configured(self) -> bool:
        """APIキーが設定済みかどうか。UI側で「未接続」表示の判定に使う。"""
        return bool(self.api_key)

    def fetch_product(self, asin: str) -> KeepaProduct:
        """ASIN から商品データを取得する（第2層の中核）。

        TODO（Keepa課金 §4.1 承認後に実装）:
          1. `pip install keepa` を requirements.txt に追加。
          2. `import keepa; api = keepa.Keepa(self.api_key)` でクライアント生成。
          3. `products = api.query(asin, domain='JP', stats=90)` で取得。
          4. Keepa のレスポンス（CSV配列・価格は「×100の整数」表現）を
             円単位の float へ復元する。価格 -1 は「在庫なし/データなし」=None。
          5. categoryTree / packageWeight / packageDimensions を見て
             fees.py の category_key / size_key に正規化するマッピングを書く。
          6. KeepaProduct を組んで返す。
          7. レート制限（トークン制）対策: 残トークンが尽きたら待機 or 例外。

        実装するまでは明示的に未実装エラーを投げる（黙ってモックを返さない）。
        """
        if not self.is_configured:
            raise RuntimeError(
                "Keepa APIキーが未設定です。環境変数 KEEPA_API_KEY を設定してください。"
                "（Keepa課金は社長承認 §4.1 が必要です）"
            )
        raise NotImplementedError(
            "Keepa連携は第2層で実装予定です。adapters/keepa.py の TODO を参照。"
        )


def product_to_profit_input(product: KeepaProduct, wholesale_price: float, **overrides):
    """KeepaProduct と卸価格から profit.ProfitInput を組み立てる橋渡し関数。

    第1層への依存方向を「第2層 → 第1層」に固定するため、import はここで遅延。
    Amazon売値は current_price を優先し、無ければ 90日平均にフォールバック。
    """
    from calc.profit import ProfitInput  # 遅延 import（循環回避＆第1層を汚さない）

    amazon_price = product.current_price or product.avg_price_90d
    if amazon_price is None:
        raise ValueError(f"{product.asin}: Amazon価格が取得できませんでした")

    params = dict(
        wholesale_price=wholesale_price,
        amazon_price=amazon_price,
        category_key=product.category_key,
        size_key=product.size_key,
    )
    params.update(overrides)
    return ProfitInput(**params)
