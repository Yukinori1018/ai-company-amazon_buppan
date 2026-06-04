"""Amazon側データ取得の抽象インターフェース。

「Amazon側で何を知りたいか」を1つの interface に固定し、その裏に
複数のバックエンド（Keepa / SP-API / サンプル）を差し替え可能に置く。
discovery パイプラインは AmazonDataBackend だけを見て、Keepa も SP-API も知らない。

取得したい項目（電脳せどりに必要な最小集合）:
- 売値（current_price）          : Amazon の現在価格（税込）
- ランキング（sales_rank）        : カテゴリ内の売れ筋順位（小さいほど売れる）
- 月販推定（monthly_sales）       : 推定月間販売数
- 出品者数（offer_count）         : 相乗り出品者の数（多いと価格競争）
- 在庫切れ率（oos_rate_90d）      : 過去90日で「在庫切れ」だった割合（0〜1）
- JAN→ASIN 解決（resolve_by_jan） : 仕入れ元のJANから Amazon 商品を引く

設計方針（タカシ）:
- 戻り値は自前 dataclass AmazonProduct に正規化（Keepa/SP-API 固有形式を漏らさない）。
- fees.py の category_key / size_key へ正規化済みの値を持たせる（profit にそのまま渡せる）。
- キー未設定なら SampleBackend を使う（キー無しでもパイプラインが動く）。
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "amazon_products.json"


@dataclass
class AmazonProduct:
    """Amazon側の1商品（自前正規化形式）。profit.ProfitInput へそのまま橋渡しできる。"""

    asin: str
    title: str
    current_price: Optional[float]        # 現在価格（円・税込）。None=在庫なし/取得不可
    sales_rank: Optional[int] = None      # カテゴリ内ランキング
    monthly_sales: Optional[int] = None   # 推定月間販売数
    offer_count: Optional[int] = None     # 出品者数
    oos_rate_90d: Optional[float] = None  # 90日在庫切れ率（0〜1）
    category_key: str = "default"         # fees.py のカテゴリキー
    size_key: str = "standard_1"          # fees.py のサイズキー
    jan: Optional[str] = None             # 紐づくJAN（突合監査用）
    is_sample: bool = False               # サンプル由来か（UI/READMEで明示）


class AmazonDataBackend(Protocol):
    """Amazon側データソースが満たすべき契約（Keepa でも SP-API でも実装可能）。"""

    @property
    def is_live(self) -> bool: ...

    def resolve_by_jan(self, jan: str) -> Optional[AmazonProduct]:
        """JAN から Amazon 商品を1件解決する。見つからなければ None。"""
        ...

    def list_products(self, **filters) -> list[AmazonProduct]:
        """条件に合う Amazon 商品を列挙する（Amazon起点ディスカバリー用）。"""
        ...


# =============================================================================
# バックエンド1: サンプル（キー不要・デモ用）
# =============================================================================
class SampleBackend:
    """sample_data/amazon_products.json を読むだけのバックエンド。

    APIキーが要らないので「キー無しでパイプラインが動く」ことを担保する主役。
    """

    def __init__(self):
        self._by_jan: dict[str, AmazonProduct] = {}
        self._all: list[AmazonProduct] = []
        self._load()

    @property
    def is_live(self) -> bool:
        return False  # サンプルは常に「本番ではない」

    def _load(self):
        if not _SAMPLE_PATH.exists():
            return
        with open(_SAMPLE_PATH, encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            p = AmazonProduct(
                asin=r["asin"],
                title=r.get("title", ""),
                current_price=r.get("current_price"),
                sales_rank=r.get("sales_rank"),
                monthly_sales=r.get("monthly_sales"),
                offer_count=r.get("offer_count"),
                oos_rate_90d=r.get("oos_rate_90d"),
                category_key=r.get("category_key", "default"),
                size_key=r.get("size_key", "standard_1"),
                jan=r.get("jan"),
                is_sample=True,
            )
            self._all.append(p)
            if p.jan:
                self._by_jan[p.jan] = p

    def resolve_by_jan(self, jan: str) -> Optional[AmazonProduct]:
        return self._by_jan.get(jan)

    def list_products(self, **filters) -> list[AmazonProduct]:
        # フィルタは discovery 側で適用するので、ここは全件を返すだけ。
        return list(self._all)


# =============================================================================
# バックエンド2: Keepa（要 KEEPA_API_KEY・§4.1 課金承認後に実装）
# =============================================================================
class KeepaBackend:
    """Keepa API バックエンド（TODO スタブ）。

    ⚠️ Keepa は有料（€49/月）。課金は CLAUDE.md §4.1（社長承認必須）に該当。
       承認が下りたら下記 TODO を埋める。それまでは明示的にエラーを投げ、
       黙ってサンプルを返さない（データを偽らないため）。
    """

    KEEPA_DOMAIN_JP = 5  # co.jp

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY")

    @property
    def is_live(self) -> bool:
        return bool(self.api_key)

    def resolve_by_jan(self, jan: str) -> Optional[AmazonProduct]:
        """JAN→ASIN→商品。

        TODO（§4.1 承認後）:
          1. requirements に `keepa` を追加、`import keepa`。
          2. api = keepa.Keepa(self.api_key)
          3. asins = api.product_finder({"productType":0, "code": jan}) 等でJAN→ASIN。
          4. products = api.query(asin, domain='JP', stats=90, offers=20)
          5. 価格(-1=在庫なし→None) / salesRank / offerCount /
             stats の outOfStockPercentage90 を AmazonProduct へ正規化。
          6. categoryTree → fees.category_key, packageDimensions/Weight → fees.size_key。
        """
        self._require_key()
        raise NotImplementedError("Keepa JAN解決は §4.1 承認後に実装（adapters/amazon_data.py 参照）")

    def list_products(self, **filters) -> list[AmazonProduct]:
        """Amazon起点ディスカバリー（Product Finder）。

        TODO（§4.1 承認後）:
          api.product_finder({...salesRank/offerCount/categoryなどの条件...}) で
          ASIN集合を取得 → api.query で詳細 → AmazonProduct に正規化。
        """
        self._require_key()
        raise NotImplementedError("Keepa Product Finder は §4.1 承認後に実装")

    def _require_key(self):
        if not self.is_live:
            raise RuntimeError(
                "KEEPA_API_KEY が未設定です。Keepa課金は社長承認 §4.1 が必要です。"
            )


# =============================================================================
# ファクトリ: キーの有無で自動選択（呼び出し側はこれだけ使えばよい）
# =============================================================================
def get_backend(prefer: str = "auto") -> AmazonDataBackend:
    """環境に応じて適切なバックエンドを返す。

    prefer="auto"（既定）: KEEPA_API_KEY があれば Keepa、無ければ Sample。
    prefer="sample"       : 強制サンプル（テスト・デモ用）。
    prefer="keepa"        : 強制 Keepa（キー無しなら後で例外）。

    ★ここが「キーを入れれば本番データに切り替わる」設計の切替点。
    """
    if prefer == "sample":
        return SampleBackend()
    if prefer == "keepa":
        return KeepaBackend()
    # auto
    if os.environ.get("KEEPA_API_KEY"):
        return KeepaBackend()
    return SampleBackend()
