"""Yahoo!ショッピング 商品検索 API ラッパー（仕入れ元起点 = 電脳せどりの入口）。

設計方針（タカシ）:
- ロックインを避けるため、戻り値は Yahoo 固有の生 JSON ではなく自前 dataclass に正規化する。
- シークレット（APIキー）はコードに書かない。環境変数 YAHOO_APP_ID から読む。
- **キー未設定でもパイプライン全体が動く**よう、ローカルのサンプルJSONを返す
  フォールバックを必ず持つ。これが「キー無しでもデモが回る」ための肝。
- ToS 遵守: 公式の商品検索 API（v3 ItemSearch）だけを使う。HTMLスクレイピングは絶対にしない。

公式仕様（2026年時点の代表値・要再確認）:
- エンドポイント: https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch
- 認証: クエリパラメータ appid に「Client ID（アプリケーションID）」を渡す
- 料金: 無料。レート上限はアプリ単位（おおむね数万req/日。公式要確認）
- 主なパラメータ: query（キーワード）, jan_code（JAN直指定）, results（最大件数）,
  price_from / price_to, condition（new/used）, in_stock 等
- JAN コードはレスポンスの item.janCode に入る（出店者が登録していれば。未登録だと空）

⚠️ 正直な制約:
- 出店者が JAN を登録していない商品が一定数あり、その場合 jan が空 → Amazon 突合不能。
- 商品名・価格は取れるが「Amazon売値」は Yahoo 側からは取れない（amazon_data 側の責務）。
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _load_dotenv_if_present() -> None:
    """同階層〜2つ上までの .env を探して os.environ に流し込む（軽量自前ローダ）。

    python-dotenv に依存しないのは YAGNI（KEY=VALUE しか無いため）。
    既に環境変数があればそちらを優先（上書きしない）。シークレットは Git 対象外の .env のみ。
    """
    here = Path(__file__).resolve()
    for base in [here.parent, here.parent.parent, here.parent.parent.parent]:
        env_path = base / ".env"
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
        except OSError:
            pass
        break


_load_dotenv_if_present()


# 公式エンドポイント（実呼び出し時に使用）
YAHOO_ITEMSEARCH_ENDPOINT = (
    "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
)

# サンプルJSONの置き場（このファイルから見た相対）
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "yahoo_items.json"


@dataclass
class YahooItem:
    """Yahoo!ショッピングの仕入れ候補1件（自前正規化形式）。

    Yahoo 固有形式から切り離してあるので、別 EC（楽天等）の実装を足すときも
    この dataclass に正規化すれば下流（discovery）は一切変えずに済む。
    """

    name: str                      # 商品名
    price: int                     # 仕入価格（税込・円）
    url: str                       # 仕入元の商品ページURL
    jan: Optional[str] = None      # JANコード（突合キー。未登録なら None）
    store: str = ""                # 出店ストア名
    point_rate: float = 0.0        # PayPayポイント還元率（%）。実質原価の参考用
    image_url: str = ""            # 商品画像URL（UI表示用）
    is_sample: bool = False        # サンプル由来かどうか（UI/READMEで明示するため）


class YahooShoppingClient:
    """Yahoo!ショッピング商品検索クライアント。

    使い方:
        client = YahooShoppingClient()        # 環境変数 YAHOO_APP_ID を読む
        items = client.search("ワイヤレスイヤホン", results=20, price_to=5000)

    APIキーが無ければ自動でサンプルデータにフォールバックする（例外を投げない）。
    """

    def __init__(self, app_id: Optional[str] = None, *, force_sample: bool = False):
        # シークレットは環境変数優先。引数はテスト差し込み用。
        self.app_id = app_id or os.environ.get("YAHOO_APP_ID")
        self.force_sample = force_sample

    @property
    def is_live(self) -> bool:
        """本番APIに接続できる状態か。UIの「サンプル/本番」表示判定に使う。"""
        return bool(self.app_id) and not self.force_sample

    def search(
        self,
        query: str = "",
        *,
        results: int = 20,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        jan_code: Optional[str] = None,
    ) -> list[YahooItem]:
        """キーワード（またはJAN）で仕入れ候補を検索して YahooItem のリストを返す。

        キー未設定時はサンプルJSONをそのまま返す（キーワードでの粗いフィルタ付き）。
        """
        if not self.is_live:
            return self._search_sample(query, jan_code, results)
        return self._search_live(
            query, results=results, price_from=price_from,
            price_to=price_to, jan_code=jan_code,
        )

    # ---------------------------------------------------------------------
    # 本番: 実 API 呼び出し（キーを入れればここが動く）
    # ---------------------------------------------------------------------
    def _search_live(
        self, query, *, results, price_from, price_to, jan_code
    ) -> list[YahooItem]:
        """実 API を叩いて YahooItem に正規化する。

        requests に依存。キーが入った瞬間にこの経路に切り替わる（コメント明示）。
        """
        import requests  # 遅延 import（サンプル経路では不要にする）

        params = {
            "appid": self.app_id,
            "results": min(results, 20),  # Yahoo V3 itemSearch の1回上限は20件（公式）
        }
        if query:
            params["query"] = query
        if jan_code:
            params["jan_code"] = jan_code
        if price_from is not None:
            params["price_from"] = price_from
        if price_to is not None:
            params["price_to"] = price_to

        # 短時間に多数のJAN検索を連投すると Yahoo が 429 を返すため、軽くペーシングし、
        # 429 を一度だけバックオフ再試行する（原石オートサーチは最大15回連続で叩くため）。
        import time

        for attempt in range(2):
            resp = requests.get(YAHOO_ITEMSEARCH_ENDPOINT, params=params, timeout=15)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(1.0)  # レート制限 → 1秒待って一度だけ再試行
                continue
            resp.raise_for_status()
            break
        time.sleep(0.15)  # 次の呼び出しまでの最小間隔（429 予防）
        payload = resp.json()
        return self._normalize(payload.get("hits", []), is_sample=False)

    # ---------------------------------------------------------------------
    # フォールバック: サンプルJSON
    # ---------------------------------------------------------------------
    def _search_sample(self, query, jan_code, results) -> list[YahooItem]:
        """サンプルJSONを読み、ゆるくフィルタして返す（キー無しデモ用）。"""
        hits = _load_sample_hits()
        items = self._normalize(hits, is_sample=True)

        if jan_code:
            items = [it for it in items if it.jan == jan_code]
        elif query:
            # 商品名にキーワードを含むものだけ（部分一致・大文字小文字無視）。
            q = query.lower()
            filtered = [it for it in items if q in it.name.lower()]
            # ヒット0なら「デモが空で寂しい」を避け全件返す（サンプルである旨はUIで明示）。
            items = filtered or items
        return items[:results]

    # ---------------------------------------------------------------------
    # 共通: 生 hits → YahooItem 正規化
    # ---------------------------------------------------------------------
    @staticmethod
    def _normalize(hits: list, *, is_sample: bool) -> list[YahooItem]:
        """生 hits（本番 v3 / サンプル両対応）→ YahooItem。

        本番 v3 ItemSearch のレスポンスは入れ子（seller/image/point が dict）。
        サンプルJSONはフラット（store/image_url/pointRate）。両方を吸収する。
        本番で実測したフィールド構造（2026-06-04 タカシ）に合わせてある。
        """
        out: list[YahooItem] = []
        for h in hits:
            jan = (h.get("janCode") or h.get("jan") or "").strip() or None

            # 出店ストア名: 本番は seller.name（dict）、サンプルは store（str）
            store = ""
            seller = h.get("seller")
            if isinstance(seller, dict):
                store = seller.get("name", "")
            else:
                store = h.get("store") or (seller or "")

            # 画像URL: 本番は image.medium（dict）、サンプルは image_url/image（str）
            image_url = ""
            image = h.get("image")
            if isinstance(image, dict):
                image_url = image.get("medium") or image.get("small") or ""
            else:
                image_url = h.get("image_url") or (image or "")

            # ポイント還元率: 本番 v3 は point(dict) で「率(%)」を直接返さず付与額のみ。
            # 率に換算（付与額/価格*100）。サンプルは pointRate(%) を直接持つ。
            point_rate = 0.0
            point = h.get("point")
            price = int(h.get("price", 0) or 0)
            if isinstance(point, dict) and price > 0:
                # 通常付与 + ボーナス付与を実質還元として概算（LYP限定は変動するため除外＝保守的）
                amount = (point.get("amount", 0) or 0) + (point.get("bonusAmount", 0) or 0)
                point_rate = round(amount / price * 100, 1)
            elif point is None:
                point_rate = float(h.get("pointRate", h.get("point_rate", 0)) or 0)

            out.append(
                YahooItem(
                    name=h.get("name", ""),
                    price=price,
                    url=h.get("url", ""),
                    jan=jan,
                    store=store,
                    point_rate=point_rate,
                    image_url=image_url,
                    is_sample=is_sample,
                )
            )
        return out


def _load_sample_hits() -> list:
    """sample_data/yahoo_items.json を読む。無ければ空リスト。"""
    if not _SAMPLE_PATH.exists():
        return []
    with open(_SAMPLE_PATH, encoding="utf-8") as f:
        return json.load(f)
