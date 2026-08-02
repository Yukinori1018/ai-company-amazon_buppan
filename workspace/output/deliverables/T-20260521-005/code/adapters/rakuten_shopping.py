"""楽天市場 商品検索 API ラッパー（2つ目の仕入れ先＝突合の網を広げる）。

設計方針（タカシ）:
- Yahoo と同じ正規化型 `YahooItem`（＝汎用の SupplierItem）を返す。下流（pipeline/UI）は
  仕入元が増えても一切変えずに済む。違いは item.source（"楽天" / "Yahoo"）だけ。
- シークレットはコードに書かない。環境変数 RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY から読む。
- キー未設定／参照元ドメイン未許可でも**パイプライン全体が動く**よう、サンプルJSONへ
  必ずフォールバックする（Yahoo と同じ「キー無しでもデモが回る」思想）。
- ToS 遵守: 公式の Rakuten Ichiba Item Search API（新ポータル版）だけを使う。スクレイピング禁止。

―― 楽天 新ポータル API の"実測"仕様（2026-06-05 タカシが実疎通で確認）――
- エンドポイント:
    https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401
- 認証（クエリパラメータ）:
    applicationId = RAKUTEN_APP_ID（UUID形式）
    accessKey     = RAKUTEN_ACCESS_KEY（pk_... の新方式シークレット。2026移行で必須化）
    affiliateId   = RAKUTEN_AFFILIATE_ID（任意。検索だけなら不要なので付けない）
- ⚠️ 最重要の制約（門番）:
    新APIは "ブラウザからの利用" を前提に設計され、HTTP の Referer / Origin ヘッダ必須。
    さらにその値が、楽天デベロッパー管理画面で **アプリに登録した「許可するWebサイト
    （Allowed Websites）」ドメインと一致**しないと 403 HTTP_REFERRER_NOT_ALLOWED で弾かれる。
    → 本クライアントは Referer/Origin に環境変数 RAKUTEN_REFERER（＝登録ドメイン）を送る。
      未設定 or 不一致だと 403/503 になるため、その場合は**サンプルへ正直にフォールバック**し
      `last_error` に理由を残す（でっち上げない）。社長は管理画面でドメインを1つ登録し、
      同じ値を RAKUTEN_REFERER に入れるだけで本番が通る。
- レスポンス（formatVersion=2・フラット）:
    Items[].itemName / itemPrice / itemUrl / shopName / mediumImageUrls[]
    ※ Ichiba Item Search は **JAN(janCode) を返さない**。突合キーの JAN は別途必要。
      → 本クライアントは検索キーワードに JAN を渡し（jan_code 指定時）、取れた候補の
        janCode が欠落していても「問い合わせた JAN」を補完して突合可能にする
        （仕入元起点で janCode 直指定検索した場合のみ。honesty: 推定ではなく問い合わせ値）。
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

# 仕入元をまたいで共有する正規化型（ロックイン回避・下流非依存の肝）。
from adapters.yahoo_shopping import YahooItem, _load_dotenv_if_present

_load_dotenv_if_present()


# 公式エンドポイント（新ポータル版・2026-04-01 リビジョン）
RAKUTEN_ICHIBA_ENDPOINT = (
    "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"
)

# サンプルJSONの置き場（このファイルから見た相対）
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "rakuten_items.json"

SOURCE_NAME = "楽天"


class RakutenShoppingClient:
    """楽天市場 商品検索クライアント（YahooShoppingClient と同一インターフェース）。

    使い方:
        client = RakutenShoppingClient()          # 環境変数からキー＆参照元ドメインを読む
        items = client.search("水筒", results=20)  # → list[YahooItem]（source="楽天"）

    キー未設定・参照元ドメイン未許可・通信失敗時は自動でサンプルにフォールバックし、
    `is_live`/`last_error` で本番接続状態を正直に示す（例外を投げない）。
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        access_key: Optional[str] = None,
        *,
        referer: Optional[str] = None,
        force_sample: bool = False,
    ):
        # シークレットは環境変数優先。引数はテスト差し込み用。
        self.app_id = app_id or os.environ.get("RAKUTEN_APP_ID")
        self.access_key = access_key or os.environ.get("RAKUTEN_ACCESS_KEY")
        # 管理画面で登録した「許可するWebサイト」ドメイン（Referer/Origin に送る）。
        self.referer = referer or os.environ.get("RAKUTEN_REFERER")
        self.force_sample = force_sample
        # 直近の本番呼び出しが失敗した理由（UI/ログで正直に出すため）。
        self.last_error: Optional[str] = None

    @property
    def has_keys(self) -> bool:
        """APIキー（app_id + access_key）が揃っているか。"""
        return bool(self.app_id) and bool(self.access_key)

    @property
    def is_live(self) -> bool:
        """本番APIに接続を試みられる状態か。

        新APIは Referer/Origin 必須かつ登録ドメイン一致が要るため、
        キーに加えて **RAKUTEN_REFERER（登録ドメイン）も揃って初めて** 本番扱いにする。
        揃っていなければサンプルに落ちる（403を撒き散らさないための honesty 判定）。
        """
        return self.has_keys and bool(self.referer) and not self.force_sample

    def search(
        self,
        query: str = "",
        *,
        results: int = 20,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        jan_code: Optional[str] = None,
    ) -> list[YahooItem]:
        """キーワード（またはJAN）で楽天の仕入れ候補を検索して YahooItem のリストを返す。

        Ichiba Item Search は JAN を返さないため、jan_code 指定時は JAN をキーワードとして
        検索し、ヒット候補に「問い合わせた JAN」を補完する（突合可能にする）。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            return self._search_sample(query, jan_code, results)
        return self._search_live(
            query, results=results, price_from=price_from,
            price_to=price_to, jan_code=jan_code,
        )

    def _why_not_live(self) -> str:
        """本番に行けない理由を正直に1行で返す（UI/ログ用）。"""
        if self.force_sample:
            return "force_sample=True（テスト/デモ指定）"
        if not self.has_keys:
            return "RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY 未設定"
        if not self.referer:
            return (
                "RAKUTEN_REFERER 未設定（楽天管理画面で『許可するWebサイト』ドメインを登録し、"
                "同じ値を .env の RAKUTEN_REFERER に設定してください）"
            )
        return ""

    # ---------------------------------------------------------------------
    # 本番: 実 API 呼び出し
    # ---------------------------------------------------------------------
    def _search_live(
        self, query, *, results, price_from, price_to, jan_code
    ) -> list[YahooItem]:
        """実 API を叩いて YahooItem に正規化する。失敗時はサンプルへ正直にフォールバック。"""
        import requests  # 遅延 import（サンプル経路では不要にする）

        # JAN 直指定検索: Ichiba Item Search は jan パラメータを持たないため、
        # JAN をキーワードに入れて検索する（店舗が型番/JANを商品名や説明に書いていれば当たる）。
        effective_keyword = (jan_code or query or "").strip()

        params = {
            "applicationId": self.app_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            "hits": min(max(results, 1), 30),  # Ichiba Item Search の1回上限は30件（公式）
        }
        if effective_keyword:
            params["keyword"] = effective_keyword
        if price_from is not None:
            params["minPrice"] = price_from
        if price_to is not None:
            params["maxPrice"] = price_to

        # 新APIの門番: Referer/Origin が登録ドメインと一致しないと 403。両方に同値を送る。
        headers = {
            "Referer": self._referer_url(),
            "Origin": self._origin_url(),
            "User-Agent": "Mozilla/5.0 (Sato-Scope Lite; +rakuten-ichiba-api)",
        }

        # レート配慮 + 429 を一度だけバックオフ再試行（原石オートサーチは連続で叩くため）。
        resp = None
        for attempt in range(2):
            try:
                resp = requests.get(
                    RAKUTEN_ICHIBA_ENDPOINT, params=params, headers=headers, timeout=15
                )
            except requests.RequestException as e:
                self.last_error = f"楽天API通信失敗: {e}"
                return self._search_sample(query, jan_code, results)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(1.0)
                continue
            break
        time.sleep(0.2)  # 次呼び出しまでの最小間隔（429予防）

        if resp.status_code != 200:
            # 403(ドメイン不一致)・503(認証サービスエラー)等は黙らず理由を残してサンプルへ。
            self.last_error = self._explain_http_error(resp)
            return self._search_sample(query, jan_code, results)

        try:
            payload = resp.json()
        except ValueError:
            self.last_error = "楽天APIが非JSONを返却"
            return self._search_sample(query, jan_code, results)

        self.last_error = None
        items = self._normalize(payload.get("Items", []), is_sample=False)
        # JAN 直指定検索なら、問い合わせた JAN を補完（API は janCode を返さないため）。
        if jan_code:
            for it in items:
                if not it.jan:
                    it.jan = jan_code
        return items

    @staticmethod
    def _explain_http_error(resp) -> str:
        """楽天APIのHTTPエラーを社長向けの次アクション付きで説明する。"""
        try:
            msg = resp.json().get("errors", {}).get("errorMessage", "")
        except ValueError:
            msg = (resp.text or "")[:80]
        if "REFERRER_NOT_ALLOWED" in msg or resp.status_code == 403:
            return (
                f"楽天API 403（{msg or 'HTTP_REFERRER_NOT_ALLOWED'}）: "
                "RAKUTEN_REFERER の値が、楽天管理画面で登録した『許可するWebサイト』ドメインと"
                "一致していません。両者を揃えてください。"
            )
        if resp.status_code == 503:
            return (
                "楽天API 503（Authentication service error）: 参照元ドメインが認証側で検証できません"
                "（localhost等は不可の可能性）。公開可能なドメインを登録・設定してください。"
            )
        return f"楽天API {resp.status_code}: {msg}"

    def _referer_url(self) -> str:
        """Referer ヘッダ用に末尾スラッシュ付きの URL に整える。"""
        ref = (self.referer or "").strip()
        if not ref.startswith("http"):
            ref = "https://" + ref
        return ref if ref.endswith("/") else ref + "/"

    def _origin_url(self) -> str:
        """Origin ヘッダ用に scheme+host だけ（末尾スラッシュ無し）に整える。"""
        return self._referer_url().rstrip("/")

    # ---------------------------------------------------------------------
    # フォールバック: サンプルJSON
    # ---------------------------------------------------------------------
    def _search_sample(self, query, jan_code, results) -> list[YahooItem]:
        """サンプルJSONを読み、ゆるくフィルタして返す（本番に行けない時の正直なデモ）。"""
        hits = _load_sample_hits()
        items = self._normalize(hits, is_sample=True)

        if jan_code:
            items = [it for it in items if it.jan == jan_code]
        elif query:
            q = query.lower()
            filtered = [it for it in items if q in it.name.lower()]
            items = filtered or items  # 空で寂しくならないよう全件（サンプル旨はUIで明示）
        return items[:results]

    # ---------------------------------------------------------------------
    # 共通: 生 Items → YahooItem 正規化（source="楽天" を付与）
    # ---------------------------------------------------------------------
    @staticmethod
    def _normalize(hits: list, *, is_sample: bool) -> list[YahooItem]:
        """楽天の生 Items（本番 formatVersion=2 / サンプル両対応）→ YahooItem。"""
        out: list[YahooItem] = []
        for h in hits:
            jan = (h.get("janCode") or h.get("jan") or "").strip() or None

            # 画像URL: 本番は mediumImageUrls（str配列 or {imageUrl} 配列）、サンプルは空配列。
            image_url = ""
            imgs = h.get("mediumImageUrls") or h.get("smallImageUrls") or []
            if imgs:
                first = imgs[0]
                image_url = first.get("imageUrl", "") if isinstance(first, dict) else str(first)

            # ポイント還元率: 楽天は pointRate（倍率）。1倍=1%還元相当として保持（参考値）。
            point_rate = float(h.get("pointRate", 0) or 0)

            out.append(
                YahooItem(
                    name=h.get("itemName", "") or h.get("name", ""),
                    price=int(h.get("itemPrice", h.get("price", 0)) or 0),
                    url=h.get("itemUrl", "") or h.get("url", ""),
                    jan=jan,
                    store=h.get("shopName", "") or h.get("store", ""),
                    point_rate=point_rate,
                    image_url=image_url,
                    is_sample=is_sample,
                    source=SOURCE_NAME,
                )
            )
        return out


def _load_sample_hits() -> list:
    """sample_data/rakuten_items.json を読む。無ければ空リスト。"""
    if not _SAMPLE_PATH.exists():
        return []
    with open(_SAMPLE_PATH, encoding="utf-8") as f:
        return json.load(f)
