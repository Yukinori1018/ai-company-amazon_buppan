"""NETSEA（卸）バイヤーAPI ラッパー（第3の仕入れ先＝卸で最安を狙う）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ 用途制限 — このモジュールは【NETSEA 内で完結する仕入れ実務】専用です。
   【メーカー／サプライヤーの「発見」用途で使ってはいけません。】
   （法務ハルオ判定 2026-08-31 / T-20260831-005。読まずに使わないこと）

当社は Buyer API のアクセストークンを発行済み ＝ NETSEA バイヤー会員 ＝
下記の条文に「現に」拘束されています。将来の話ではありません。

✗ 禁止1: NETSEA で見つけたサプライヤーに、NETSEA の外で連絡する
        バイヤー会員規約 第7条2項5号
        「当社が定めた方法又は当社が提供する機能以外の方法を利用して、
          サプライヤーと直接又は間接問わず連絡を取ること」

✗ 禁止2: NETSEA で見つけたサプライヤーと、NETSEA の外で売買契約を結ぶ
        第19条3項
        「バイヤー会員は、NETSEA を利用することなく、サプライヤー会員との間で
          商品等に係る売買契約等を締結してはならないものとします」
        ── 違反したときの制裁（第27条4項）──
             ① 当社の事業者名を公表される
             ② 売買契約を解除される
             ③ 損害賠償とは別に【違約金 200万円 ＋ 売買代金の 50%】を請求される
           月商800万円の事業にとって、これは一発で吹き飛ぶ金額です。

✗ 禁止3: サプライヤー会員の情報を「集めること自体を目的に」API を叩く
        第7条1項3号「本サービスを利用する他の者の情報の収集を目的とする行為」
        ※ この号には「当社の事前承諾があれば可」という逃げ道がありません（絶対禁止）

✗ 禁止4: 取得したサプライヤー名・企業名を、メーカー発見リストへ合流させる
        第7条2項3号「利用者の権利の行使の範囲を超えて、本サービスの情報を利用すること」
        具体的には v14 候補リスト（T-20260817-005）や展示会出展社リストなど、
        「後で直接アプローチするための名簿」へ NETSEA 由来の社名を混ぜないこと。

○ 許可: NETSEA 内で買う商品を選ぶ（JAN 突合・卸価格取得・在庫確認・送料計算）
○ 許可: NETSEA 内で発注・決済する
       → discovery/pipeline.py の discover_from_netsea() もこちら側です。
         あれは「NETSEA 内で買う商品」を探す関数であって、
         「外で口説くメーカー」を探す関数ではありません。出力の使い道に注意。

⚠ 会員規約 第24条1項により、バイヤー会員の氏名・住所・電話番号は NETSEA サイト上で
  公開されます（個人事業主＝自宅住所）。利用継続の可否は社長判断です。

判定書 : workspace/output/deliverables/T-20260831-005/04_出展社リストとNETSEAの適法性判定.md
規約原文: https://www.netsea.jp/agreement/statement
          （2026-08-31 取得のスナップショット:
            workspace/output/agent_output/T-20260831-005/legal/netsea_buyer_agreement_20260831.txt）
注記    : API 利用規約（第8条2＝取得データの加工には書面承諾が必要）は会員規約とは別文書です。
          取得データの加工・外部提供を検討するときは、そちらを別途確認すること。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

設計方針（タカシ）:
- Yahoo / 楽天と同じ正規化型 `YahooItem`（＝汎用 SupplierItem）を返す。下流（pipeline/UI）は
  仕入元が増えても一切変えずに済む。違いは item.source（"NETSEA"）と price が卸価格である点。
- シークレットはコードに書かない。環境変数 NETSEA_API_TOKEN から読む。
- トークン未設定／未取得・通信失敗時は**サンプルJSONへ必ずフォールバック**する
  （Yahoo / 楽天と同じ「キー無しでもデモが回る」思想）。
- ToS 遵守: 公式の NETSEA Buyer API（トークン認証）だけを使う。スクレイピング禁止。

―― NETSEA Buyer API の確定仕様（2026-06-06 タカシが OpenAPI 仕様を直接取得して確認）――
出典: https://api.netsea.jp/docs/buyer/openapi.json
      （Redoc が描画する spec 本体。paths は paths/index.json、各スキーマは schemas/*.json を $ref 参照）
運営: 株式会社SynaBiz（NETSEA = https://www.netsea.jp）

- ベースURL: https://api.netsea.jp/buyer/v1/
- 認証: リクエストヘッダ `Authorization: Bearer <アクセストークン>`
    トークンは https://www.netsea.jp/account/ のAPI設定画面で発行（有効期限180日）。
- エンドポイント:
    POST /items         商品一覧（1回100件・ソート=ダイレクト商品ID昇順）
    GET  /items/stock   在庫情報（1件・direct_item_id 指定）
    GET  /categories    商品カテゴリ一覧
    GET  /suppliers     取引可能サプライヤー一覧
    GET  /tariffs       送料一覧（サプライヤー別・都道府県別）
- /items の主なリクエスト（application/x-www-form-urlencoded）:
    direct_item_ids もしくは supplier_ids の **いずれか必須**（カンマ区切り・各最大10件）
    jan_code（JAN直指定・integer）, category_id, product_id,
    price_range_from / price_range_to（卸価格税抜の範囲）,
    sold_out_flag（Y=品切れ / N=在庫有）, deal_net_shop_flag（ネット販売可否）,
    next_direct_item_id（ページング: 100件超過時のみレスポンスに付き、次回リクエストに渡す）
    ※ キーワード（フリーテキスト）検索パラメータは仕様に存在しない（不明＝無い）。
      検索の起点は JAN / カテゴリ / サプライヤー / 商品ID。
- /items レスポンスの商品フィールド（最重要）:
    トップレベル: supplier_id, product_id, product_url, product_name, shop_name,
      jan_code, category_id, reference_price_type(O/M/C/H), description, spec_size,
      ship_fee_type(Y/N), ship_fee, image_url_1..10, deal_net_shop_flag ほか
    set[]（規格/枝番ごと。価格・在庫はここに入る）:
      direct_item_id, jan_code, reference_price（上代＝希望小売 税抜）,
      price（卸価格単価 税抜）, set_num, set_price（セット卸額 税込）,
      set_price_without_tax（セット卸額 税抜）, consumption_tax_class（0/1/99）,
      sold_out_flag（Y=品切れ / N=在庫あり）
    → ✅ JANコード あり（top + set 両方） / ✅ 卸価格 あり（set[].price 税抜・set_price 税込）
      / ✅ 希望小売価格 あり（set[].reference_price 上代税抜・種別 reference_price_type）
      / ✅ 在庫 あり（set[].sold_out_flag） / ✅ 送料 あり（ship_fee + /tariffs）
      / ✅ 商品名・画像・商品URL あり
- エラー: 異常時は {"error": {"code", "subcode", "message"}}。code 1=認証, 2=パラメータ, 4=アクセス。
    HTTP 400/401 等。承認済みサプライヤーの商品しか取得できない。
- ⚠️ 実機確認で判明した重要な実挙動（2026-06-06 タカシ 本番接続で確認）:
    1) /items は jan_code 単独だと 400（code=2 subcode=101
       "direct_item_ids or supplier_ids is not specified."）になる。
       → JAN突合時も supplier_ids（承認済みサプライヤーID・10件ずつ）の同時指定が必須。
    2) /items のヒット0件レスポンスは **{"data":[]} ではなく素の `[]`（JSON配列）** を返す。
       ヒット有り時は {"data":[...]}（dict）。両方を受ける必要がある。
    3) トークンの scopes が空配列 `[]` でも GET /suppliers / POST /items は 200 で通る
       （scope 制御は実運用されていない模様。権限はサプライヤー承認で制御）。
- レート制限: **不明**（OpenAPI 仕様に明記なし。規約第3条で当社がアクセス回数等を制約しうると規定）。
    → 保守的に呼び出し間隔を置き、429/4xx は黙らず last_error に残す（でっち上げない）。

⚠️ 正直な制約 / honesty:
- トークンは社長が未取得（2026-06-06 時点）。実HTTP経路は実装済みだが**今は叩かない**。
  トークンが .env(NETSEA_API_TOKEN) に入った瞬間に本番に切り替わる設計。
- /items は「キーワード検索」を持たない。Sato-Scope の JAN直指定突合（mode い）には
  jan_code 指定で直接当てる。フリーワードの粗集めは Yahoo/楽天が担う（役割分担）。
- 卸価格は **税抜**（set[].price）。税込が要る場面では set_price を使う（消費税率は商品で変動）。
- 価格・在庫は承認済みサプライヤー限定。未承認サプライヤーの商品は取得不能（仕様）。
"""

import json
import os
from pathlib import Path
from typing import Optional

# 仕入元をまたいで共有する正規化型（ロックイン回避・下流非依存の肝）。
from adapters.yahoo_shopping import YahooItem, _load_dotenv_if_present

_load_dotenv_if_present()


# 公式ベースURL（確定・OpenAPI servers より）
NETSEA_BASE_URL = "https://api.netsea.jp/buyer/v1"
NETSEA_ITEMS_ENDPOINT = NETSEA_BASE_URL + "/items"
NETSEA_STOCK_ENDPOINT = NETSEA_BASE_URL + "/items/stock"
NETSEA_SUPPLIERS_ENDPOINT = NETSEA_BASE_URL + "/suppliers"
NETSEA_TARIFFS_ENDPOINT = NETSEA_BASE_URL + "/tariffs"

# /items は supplier_ids をカンマ区切りで最大10件まで受け付ける（仕様）。
_MAX_SUPPLIER_IDS_PER_REQUEST = 10

# GET /suppliers の1ページ取得件数。既定は100件で打ち切られる（OpenAPI 仕様に記載なし）。
# 実機確認（2026-08-31）で `limit` と `next_supplier_id` が効くことを確認した。
_SUPPLIERS_PAGE_LIMIT = 200

# サンプルJSONの置き場（このファイルから見た相対）
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "netsea_items.json"

SOURCE_NAME = "NETSEA"

# 用途ラベル。NETSEA 由来データを書き出すときは、この値を出所として必ず一緒に残す。
# （出所カード SOURCE.md ／ CSV の出所列 ／ ログの1行目、どれでもよいが省略しないこと）
NETSEA_DATA_PROVENANCE = "NETSEA Buyer API"

# 許される用途はこの1つだけ。文字列で持つのは、呼び出し側に用途を書かせるため。
PURPOSE_PROCUREMENT = "procurement"        # NETSEA 内で完結する仕入れ実務 → OK
PURPOSE_DISCOVERY = "discovery"            # メーカー/サプライヤーの発掘 → 規約違反

NETSEA_USE_POLICY = (
    "NETSEA 由来データは『NETSEA 内で完結する仕入れ実務』にのみ使用可。"
    "サプライヤーの発見・外部での連絡・外部での売買契約は会員規約 第7条2項5号／第19条3項違反。"
    "制裁は第27条4項＝事業者名の公表・契約解除・違約金200万円＋代金の50%。"
)


class NetseaUsageError(RuntimeError):
    """NETSEA 会員規約で禁じられた用途に使おうとしたときに投げる。

    握りつぶさないこと。ここで落ちるのは、落ちた方が安いからです。
    """


def assert_procurement_use(purpose: str) -> None:
    """用途が『仕入れ実務』であることを確認する。発見用途なら即座に落とす。

    NETSEA 由来データを新しい出力先へ流す処理を書くときは、その入口でこれを呼ぶ。
    半年後の自分や別の AI が、うっかり発見パイプラインへ配線するのを止めるための関門です。

    >>> assert_procurement_use(PURPOSE_PROCUREMENT)   # 何も起きない
    >>> assert_procurement_use(PURPOSE_DISCOVERY)     # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    NetseaUsageError: ...
    """
    if purpose == PURPOSE_PROCUREMENT:
        return
    raise NetseaUsageError(
        f"NETSEA データを purpose={purpose!r} で使おうとしています。{NETSEA_USE_POLICY} "
        "詳細は workspace/output/deliverables/T-20260831-005/"
        "04_出展社リストとNETSEAの適法性判定.md"
    )


class NetseaClient:
    """NETSEA Buyer API クライアント（Yahoo/楽天と同一の .search() インターフェース）。

    使い方:
        client = NetseaClient()                      # 環境変数 NETSEA_API_TOKEN を読む
        items = client.search(jan_code="4900000000024")  # → list[YahooItem]（source="NETSEA"）

    トークン未設定・未取得・通信失敗時は自動でサンプルにフォールバックし、
    `is_live`/`last_error` で本番接続状態を正直に示す（例外を投げない）。
    """

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        force_sample: bool = False,
    ):
        # シークレットは環境変数優先。引数はテスト差し込み用。
        self.token = token or os.environ.get("NETSEA_API_TOKEN")
        self.force_sample = force_sample
        # 直近の本番呼び出しが失敗した理由（UI/ログで正直に出すため）。
        self.last_error: Optional[str] = None
        # 承認済みサプライヤーIDのキャッシュ（GET /suppliers の結果）。
        # /items は jan_code 単独だと 400（direct_item_ids か supplier_ids 必須）になるため、
        # JAN突合時はこのIDで supplier_ids を埋める。プロセス内で1回だけ取得する。
        self._supplier_ids_cache: Optional[list[int]] = None

    @property
    def has_token(self) -> bool:
        """アクセストークンが設定されているか。"""
        return bool(self.token)

    @property
    def is_live(self) -> bool:
        """本番APIに接続を試みられる状態か（トークンが揃っているか）。"""
        return self.has_token and not self.force_sample

    def search(
        self,
        query: str = "",
        *,
        results: int = 20,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        jan_code: Optional[str] = None,
    ) -> list[YahooItem]:
        """JAN（またはカテゴリ／キーワードでの粗フィルタ）で卸の仕入れ候補を検索する。

        NETSEA /items は**フリーワード検索を持たない**ため:
          - jan_code 指定時 → 本番では jan_code パラメータで直接取得（mode(い) の本丸）。
          - query のみ（JAN無し）→ 本番でも当てにいけないので**サンプルを商品名で粗フィルタ**して返す
            （フリーワードの粗集めは Yahoo/楽天の役割。NETSEA はJAN突合の最安卸として効く）。
        戻り値は YahooItem（source="NETSEA"・price=卸価格 税抜）。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            return self._search_sample(query, jan_code, results, price_from, price_to)
        # 本番でもフリーワード（JAN/カテゴリ無し）は仕様上当てられない → サンプルで正直に粗集め。
        if not jan_code:
            return self._search_sample(query, jan_code, results, price_from, price_to)
        return self._search_live(
            jan_code=jan_code, results=results,
            price_from=price_from, price_to=price_to,
        )

    def _why_not_live(self) -> str:
        """本番に行けない理由を正直に1行で返す（UI/ログ用）。"""
        if self.force_sample:
            return "force_sample=True（テスト/デモ指定）"
        if not self.has_token:
            return (
                "NETSEA_API_TOKEN 未設定（NETSEAマイページ https://www.netsea.jp/account/ の"
                "API設定画面でアクセストークンを発行し、.env の NETSEA_API_TOKEN に設定してください）"
            )
        return ""

    # ---------------------------------------------------------------------
    # 本番: 実 API 呼び出し（トークンが入ればここが動く。社長未取得のため今は呼ばれない）
    # ---------------------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "Sato-Scope Lite (+netsea-buyer-api)",
        }

    def _approved_supplier_ids(self) -> list[int]:
        """承認済みサプライヤーID一覧を GET /suppliers から取得（プロセス内1回キャッシュ）。

        /items の JAN突合は jan_code 単独だと 400（direct_item_ids か supplier_ids 必須）に
        なるため、ここで取得したIDで supplier_ids を埋める。失敗時は空リスト（呼び出し側で
        サンプルへフォールバック）。
        """
        if self._supplier_ids_cache is not None:
            return self._supplier_ids_cache

        import requests  # 遅延 import

        try:
            resp = requests.get(
                NETSEA_SUPPLIERS_ENDPOINT, headers=self._headers(), timeout=15
            )
        except requests.RequestException as e:
            self.last_error = f"NETSEA /suppliers 通信失敗: {e}"
            self._supplier_ids_cache = []
            return []
        if resp.status_code != 200:
            self.last_error = self._explain_http_error(resp)
            self._supplier_ids_cache = []
            return []
        try:
            data = resp.json().get("data", [])
        except ValueError:
            self.last_error = "NETSEA /suppliers が非JSONを返却"
            self._supplier_ids_cache = []
            return []
        ids = [int(s["id"]) for s in data if s.get("id") is not None]
        # ⚠️ ここも1ページ(100件)しか見ていない。JAN突合の網が狭くなるだけで壊れはしないが、
        #    全承認サプライヤーを当てたい場合は list_suppliers() の結果を使うこと
        #    （T-20260831-006 でページング済み）。
        self._supplier_ids_cache = ids
        return ids

    def _search_live(
        self, *, jan_code, results, price_from, price_to
    ) -> list[YahooItem]:
        """実 API（POST /items）を叩いて YahooItem に正規化する。失敗時はサンプルへ正直に。

        NETSEA /items は jan_code 単独では 400 になる（direct_item_ids か supplier_ids 必須）。
        そのため承認済みサプライヤーIDを取得し、10件ずつ supplier_ids に詰めて jan_code と
        一緒に投げ、ヒットを集約する。
        """
        import time

        import requests  # 遅延 import（サンプル経路では不要にする）

        supplier_ids = self._approved_supplier_ids()
        if not supplier_ids:
            # 承認済みサプライヤーが取れない（401/権限/通信失敗）→ サンプルへ正直に。
            # last_error は _approved_supplier_ids が既に設定済み。
            return self._search_sample("", jan_code, results, price_from, price_to)

        headers = self._headers()
        collected: list = []
        last_resp = None
        # 10件ずつバッチで supplier_ids を当てる（仕様上1リクエスト最大10件）。
        batches = [
            supplier_ids[i : i + _MAX_SUPPLIER_IDS_PER_REQUEST]
            for i in range(0, len(supplier_ids), _MAX_SUPPLIER_IDS_PER_REQUEST)
        ]
        for batch in batches:
            data = {
                "jan_code": jan_code,
                "supplier_ids": ",".join(str(s) for s in batch),
            }
            if price_from is not None:
                data["price_range_from"] = price_from
            if price_to is not None:
                data["price_range_to"] = price_to

            resp = None
            for attempt in range(2):
                try:
                    resp = requests.post(
                        NETSEA_ITEMS_ENDPOINT, data=data, headers=headers, timeout=15
                    )
                except requests.RequestException as e:
                    self.last_error = f"NETSEA API通信失敗: {e}"
                    # 通信失敗時、ここまでに集めた分があればそれを返す。なければサンプル。
                    if collected:
                        break
                    return self._search_sample(
                        "", jan_code, results, price_from, price_to
                    )
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(1.0)  # レート制限 → 1秒待って一度だけ再試行
                    continue
                break
            time.sleep(0.2)  # 次バッチまでの最小間隔（保守的レート配慮）

            if resp is None:
                continue
            last_resp = resp
            if resp.status_code != 200:
                self.last_error = self._explain_http_error(resp)
                continue
            try:
                payload = resp.json()
            except ValueError:
                self.last_error = "NETSEA APIが非JSONを返却"
                continue
            if isinstance(payload, dict) and payload.get("error"):
                err = payload["error"]
                self.last_error = (
                    f"NETSEA API error code={err.get('code')} "
                    f"subcode={err.get('subcode')} {err.get('message','')}"
                )
                continue
            # /items は通常 {"data": [...]} だが、稀に data 配列を直接返す場合に備える。
            if isinstance(payload, dict):
                collected.extend(payload.get("data", []) or [])
            elif isinstance(payload, list):
                collected.extend(payload)
            # 最安1件を取りたい用途のため、十分集まったら早期終了して呼び出し回数を抑える。
            if results and len(collected) >= results * 3:
                break

        if not collected:
            # 1件も取れなかった（全バッチ空 or 全バッチエラー）。
            # 全バッチがエラーだった場合は last_error が立っているのでサンプルへ。
            # 全バッチ正常で単にヒット0なら、それは正直に空（でっち上げない）。
            if last_resp is not None and last_resp.status_code == 200 and not self.last_error:
                return []
            return self._search_sample("", jan_code, results, price_from, price_to)

        self.last_error = None
        items = self._normalize(collected, is_sample=False)
        return items[:results] if results else items

    # ---------------------------------------------------------------------
    # 卸起点（う）: 承認サプライヤーの棚卸し（一覧→ページング取得）
    # ---------------------------------------------------------------------
    def list_suppliers(self) -> list[dict]:
        """承認済みサプライヤーを {id, name} の dict 一覧で返す（UI選択肢／棚卸し対象用）。

        ⛔ この戻り値には社名が入ります。**NETSEA 内で買う相手を選ぶためだけ**に使うこと。
           社名を名簿化して外部で連絡・契約すれば、第7条2項5号／第19条3項違反となり
           違約金200万円＋代金の50%＋事業者名の公表（第27条4項）の対象です。
           メーカー発見リストへ合流させないこと（モジュール冒頭の用途制限を参照）。

        本番では GET /suppliers をそのまま使う（id と社名）。本番に行けない／失敗時は
        サンプル商品から supplier_id を抽出して擬似サプライヤー一覧を作る（デモが回る）。

        ⚠️ 2026-08-31 修正（T-20260831-006）:
           このメソッドは以前 **先頭100件しか返していませんでした**。
           `/suppliers` は1レスポンス100件で打ち切り、続きがあると `next_supplier_id` を
           付けて返します（**OpenAPI 仕様には記載が無く、実機で発見**）。
           当社の承認済みサプライヤーは実測 **225社** なので、旧実装は 125社を静かに
           取りこぼしていました。「仕入れられる相手が誰か」を数え違える＝母数の欠落なので、
           ページングを実装しました。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            return self._sample_suppliers()

        import time

        import requests  # 遅延 import

        data = []
        next_id = None
        for _ in range(50):  # 保険の上限（225社なら2周で終わる）
            params = {"limit": _SUPPLIERS_PAGE_LIMIT}
            if next_id is not None:
                params["next_supplier_id"] = next_id
            try:
                resp = requests.get(
                    NETSEA_SUPPLIERS_ENDPOINT,
                    headers=self._headers(),
                    params=params,
                    timeout=30,
                )
            except requests.RequestException as e:
                self.last_error = f"NETSEA /suppliers 通信失敗: {e}"
                if data:
                    break  # 途中まで取れているなら、それは正直な部分結果として返す
                return self._sample_suppliers()
            if resp.status_code != 200:
                self.last_error = self._explain_http_error(resp)
                if data:
                    break
                return self._sample_suppliers()
            try:
                payload = resp.json()
            except ValueError:
                self.last_error = "NETSEA /suppliers が非JSONを返却"
                if data:
                    break
                return self._sample_suppliers()
            page = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
            data.extend(page)
            next_id = payload.get("next_supplier_id") if isinstance(payload, dict) else None
            if not next_id:
                break
            time.sleep(0.3)

        out = []
        for s in data:
            sid = s.get("id")
            if sid is None:
                continue
            name = (
                s.get("trade_name") or s.get("corp_name") or s.get("name") or f"supplier {sid}"
            )
            out.append({"id": int(sid), "name": str(name)})
        self.last_error = None
        return out

    def list_tariffs(self, supplier_ids: list) -> dict:
        """GET /tariffs — サプライヤーの送料設定を取る。**送料無料ラインの唯一の一次情報**。

        なぜ要るか:
            卸は「◯円以上で送料無料」が標準です。5社に分けて買うと送料が5回掛かり、
            初回5万円のような小さな枠では利益が丸ごと消えます。
            どこまで積めば送料が変わるかは、**商品側の ship_fee には出てきません**。

        公式スキーマ（2026-09-04 タカシが openapi 実取得で確認）:
            supplier_id          … サプライヤーID
            description          … 説明文（自由記述）
            apply_type           … higher / lower（送料の違う商品を混ぜたときどちらを適用するか）
            gradual_flag         … 段階設定を使うか（true/false）
            gradual_border_price … 段階の切り替え金額。**未満なら price1・以上なら price2**
                                   段階設定を使わない場合は null
            prices[]             … 都道府県別 {prefecture, price1, price2}
                                   price2 は段階設定を使わない場合 null

        ⚠️ **「gradual_border_price = 送料無料ライン」ではありません。**
           price2 が 0 のときだけ「その金額以上で送料無料」です。
           price2 が正の値なら「その金額以上で送料が安くなる」であって無料ではありません。
           この読み違えは初回仕入れの採算を直接壊すので、判定は呼び出し側で
           price2 を見て行うこと。ここは**取ってきた値をそのまま返します**。

        戻り値: {supplier_id: tariff_dict}。取れなかった社は**入りません**（空欄にするため）。
        1リクエスト最大10社（公式仕様）。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            return {}

        import time

        import requests  # 遅延 import

        out: dict = {}
        ids = [int(i) for i in supplier_ids if i]
        for i in range(0, len(ids), _MAX_SUPPLIER_IDS_PER_REQUEST):
            chunk = ids[i : i + _MAX_SUPPLIER_IDS_PER_REQUEST]
            try:
                resp = requests.get(
                    NETSEA_TARIFFS_ENDPOINT,
                    headers=self._headers(),
                    params={"supplier_id": ",".join(str(c) for c in chunk)},
                    timeout=30,
                )
            except requests.RequestException as e:
                self.last_error = f"NETSEA /tariffs 通信失敗: {e}"
                continue
            if resp.status_code != 200:
                self.last_error = self._explain_http_error(resp)
                continue
            try:
                payload = resp.json()
            except ValueError:
                self.last_error = "NETSEA /tariffs が非JSONを返却"
                continue
            # ヒット0件が素の [] で返るのは NETSEA 共通の癖（/items で実測済み）。
            rows = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
            for row in rows:
                sid = row.get("supplier_id")
                if sid is not None:
                    out[int(sid)] = row
            time.sleep(0.3)
        return out

    def list_supplier_items(
        self,
        supplier_id: int,
        *,
        max_items: int = 100,
        sleep_sec: float = 0.2,
    ) -> tuple[list[YahooItem], dict]:
        """1サプライヤーの商品を POST /items でページング取得し棚卸しする（卸起点の心臓）。

        next_direct_item_id でページを辿り、max_items 件に達したら停止する（サイレント打ち
        切り禁止＝coverage に未処理を残す）。戻り値は (正規化済みYahooItem列, coverage dict)。
        coverage = {requested, fetched, pages, truncated, error}。
          requested = max_items（上限）
          fetched   = 実際に取得した商品数
          pages     = 投げた /items リクエスト数
          truncated = 上限で打ち切ったか（True なら未処理が残っている可能性）
          error     = 4xx/429/通信失敗の正直な理由（無ければ None）
        本番に行けない場合はサンプルの当該supplier_idの商品で代替する。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            items = self._sample_items_for_supplier(supplier_id, max_items)
            return items, {
                "requested": max_items, "fetched": len(items), "pages": 0,
                "truncated": False, "error": self._why_not_live(), "sample": True,
            }
        return self._list_supplier_items_live(supplier_id, max_items, sleep_sec)

    def list_supplier_items_raw(
        self,
        supplier_id: int,
        *,
        max_items: int = 100_000,
        sleep_sec: float = 0.2,
    ) -> tuple[list[dict], dict]:
        """1サプライヤーの商品を **生の dict のまま** ページング取得する。

        `list_supplier_items()` は共通型 `YahooItem` に正規化して返しますが、
        その過程で **利益計算に要る情報が落ちます**（上代 reference_price / セット入数 set_num /
        ネット販売可否 deal_net_shop_flag / 送料 ship_fee / 規格ごとの税区分）。
        NETSEA 起点の利益スキャン（T-20260831-006）はそれらを全部使うため、
        生データを触れる入口を1つ用意しました。

        ⛔ 用途はモジュール冒頭の制限どおり **NETSEA 内で完結する仕入れ実務のみ**。
           戻り値には `shop_name`（社名）が入ります。名簿化しないこと。

        戻り値: (生 data の行リスト, coverage dict)
        coverage は list_supplier_items() と同じ形（requested/fetched/pages/truncated/error）。
        """
        if not self.is_live:
            self.last_error = self._why_not_live()
            return [], {
                "requested": max_items, "fetched": 0, "pages": 0,
                "truncated": False, "error": self._why_not_live(), "sample": True,
            }
        return self._fetch_supplier_items_raw(supplier_id, max_items, sleep_sec)

    def _list_supplier_items_live(
        self, supplier_id: int, max_items: int, sleep_sec: float
    ) -> tuple[list[YahooItem], dict]:
        rows, coverage = self._fetch_supplier_items_raw(supplier_id, max_items, sleep_sec)
        return self._normalize(rows, is_sample=False), coverage

    def _fetch_supplier_items_raw(
        self, supplier_id: int, max_items: int, sleep_sec: float
    ) -> tuple[list[dict], dict]:
        import time

        import requests  # 遅延 import

        headers = self._headers()
        collected: list = []
        pages = 0
        next_id = None
        error = None
        truncated = False

        while len(collected) < max_items:
            data = {"supplier_ids": str(supplier_id)}
            if next_id is not None:
                data["next_direct_item_id"] = next_id

            resp = None
            for attempt in range(2):
                try:
                    resp = requests.post(
                        NETSEA_ITEMS_ENDPOINT, data=data, headers=headers, timeout=20
                    )
                except requests.RequestException as e:
                    error = f"NETSEA /items 通信失敗(supplier={supplier_id}): {e}"
                    resp = None
                    break
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(1.0)  # レート制限 → 1秒待って一度だけ再試行
                    continue
                break
            pages += 1

            if resp is None:
                self.last_error = error
                break
            if resp.status_code != 200:
                error = self._explain_http_error(resp)
                self.last_error = error
                break
            try:
                payload = resp.json()
            except ValueError:
                error = "NETSEA /items が非JSONを返却"
                self.last_error = error
                break
            if isinstance(payload, dict) and payload.get("error"):
                err = payload["error"]
                error = (
                    f"NETSEA API error code={err.get('code')} "
                    f"subcode={err.get('subcode')} {err.get('message','')}"
                )
                self.last_error = error
                break

            # ヒット有り={"data":[...]} / ヒット0=素の[]（実挙動）。両方受ける。
            if isinstance(payload, dict):
                rows = payload.get("data", []) or []
                next_id = payload.get("next_direct_item_id")
            elif isinstance(payload, list):
                rows = payload
                next_id = None
            else:
                rows = []
                next_id = None

            collected.extend(rows)
            time.sleep(sleep_sec)  # 各リクエスト間に短いsleep（保守的レート配慮）

            if not next_id:
                break  # ページ終端（これ以上の在庫なし）

        if len(collected) >= max_items and next_id:
            truncated = True  # 上限で打ち切り、まだ続きがある

        rows = collected[:max_items]
        return rows, {
            "requested": max_items,
            "fetched": len(rows),
            "pages": pages,
            "truncated": truncated,
            "error": error,
            "sample": False,
        }

    def _sample_suppliers(self) -> list[dict]:
        """サンプル商品から擬似サプライヤー一覧（id＋仮名）を作る（デモ用）。"""
        raw = _load_sample_hits()
        seen: dict = {}
        for r in raw:
            sid = r.get("supplier_id")
            if sid is None or sid in seen:
                continue
            seen[int(sid)] = r.get("shop_name") or f"supplier {sid}"
        return [{"id": sid, "name": name} for sid, name in seen.items()]

    def _sample_items_for_supplier(self, supplier_id: int, max_items: int) -> list[YahooItem]:
        """サンプル商品から当該supplier_idの行だけ正規化して返す（デモの棚卸し）。"""
        raw = [r for r in _load_sample_hits() if r.get("supplier_id") == supplier_id]
        return self._normalize(raw[:max_items], is_sample=True)

    @staticmethod
    def _explain_http_error(resp) -> str:
        """NETSEA APIのHTTPエラーを社長向けの次アクション付きで説明する。"""
        try:
            err = resp.json().get("error", {})
            msg = err.get("message", "")
        except ValueError:
            msg = (resp.text or "")[:80]
        if resp.status_code == 401:
            return (
                f"NETSEA API 401（{msg or 'Unauthenticated'}）: "
                "NETSEA_API_TOKEN が無効か期限切れ（有効期限180日）です。"
                "マイページのAPI設定画面でトークンを再発行してください。"
            )
        if resp.status_code == 400:
            return (
                f"NETSEA API 400（{msg or 'Bad Request'}）: "
                "パラメータ不正、またはアクセス許可の無いデータ（未承認サプライヤー等）です。"
            )
        return f"NETSEA API {resp.status_code}: {msg}"

    # ---------------------------------------------------------------------
    # フォールバック: サンプルJSON
    # ---------------------------------------------------------------------
    def _search_sample(
        self, query, jan_code, results, price_from=None, price_to=None
    ) -> list[YahooItem]:
        """サンプルJSONを読み、ゆるくフィルタして返す（本番に行けない時の正直なデモ）。"""
        raw = _load_sample_hits()
        items = self._normalize(raw, is_sample=True)

        if jan_code:
            items = [it for it in items if it.jan == jan_code]
        elif query:
            q = query.lower()
            filtered = [it for it in items if q in it.name.lower()]
            items = filtered or items  # 空で寂しくならないよう全件（サンプル旨はUIで明示）

        # 卸価格の範囲フィルタ（本番の price_range_* と挙動を揃える）。
        if price_from is not None:
            items = [it for it in items if it.price >= price_from]
        if price_to is not None:
            items = [it for it in items if it.price <= price_to]
        return items[:results]

    # ---------------------------------------------------------------------
    # 共通: 生 data → YahooItem 正規化（source="NETSEA"・price=卸価格税抜）
    # ---------------------------------------------------------------------
    @staticmethod
    def _normalize(rows: list, *, is_sample: bool) -> list[YahooItem]:
        """NETSEA の生 data（/items レスポンス）→ YahooItem。

        1商品に複数規格（set[]）がある。突合の最安を狙うため、在庫あり(set[].sold_out_flag=='N')
        の中で **卸価格(price 税抜)が最も安い規格** を採用して1件にまとめる。
        全規格が品切れなら、価格情報のため先頭規格を採用しつつ price は卸価格を入れる。
        """
        out: list[YahooItem] = []
        for r in rows:
            sets = r.get("set") or []
            chosen = _pick_cheapest_in_stock(sets)

            # 卸価格（税抜）。set が無い／壊れている場合は 0（突合対象外になる）。
            price = int((chosen or {}).get("price", 0) or 0)

            # JAN: set 側を優先（規格ごとに正しい）、無ければトップレベル。
            jan = ((chosen or {}).get("jan_code") or r.get("jan_code") or "")
            jan = str(jan).strip() or None

            # 在庫: 採用した規格の sold_out_flag。'N'=在庫あり。
            sold_out = (chosen or {}).get("sold_out_flag", "")
            in_stock = sold_out == "N"

            # 画像: image_url_1 を代表に。
            image_url = r.get("image_url_1", "") or ""

            out.append(
                YahooItem(
                    name=r.get("product_name", "") or r.get("name", ""),
                    price=price,                       # 卸価格（税抜）。最安採用の入力。
                    url=r.get("product_url", "") or r.get("url", ""),
                    jan=jan,
                    store=r.get("shop_name", "") or r.get("store", ""),
                    point_rate=0.0,                    # 卸にポイント還元の概念は無い。
                    image_url=image_url,
                    is_sample=is_sample,
                    source=SOURCE_NAME,
                )
            )
            # 品切れ規格しか無い場合でも候補としては残すが、価格0なら下流で弾かれる。
            # （honesty: in_stock を別フィールドで持たないのは共通型を汚さないため。
            #   品切れは price を 0 にして突合対象外にする方が安全。）
            if not in_stock:
                out[-1].price = 0
        return out


def _pick_cheapest_in_stock(sets: list) -> Optional[dict]:
    """規格一覧から「在庫あり×卸価格最安」の1規格を選ぶ。無ければ先頭、空なら None。"""
    if not sets:
        return None
    in_stock = [s for s in sets if s.get("sold_out_flag") == "N" and int(s.get("price", 0) or 0) > 0]
    if in_stock:
        return min(in_stock, key=lambda s: int(s.get("price", 0) or 0))
    return sets[0]


def _load_sample_hits() -> list:
    """sample_data/netsea_items.json を読む。無ければ空リスト。"""
    if not _SAMPLE_PATH.exists():
        return []
    with open(_SAMPLE_PATH, encoding="utf-8") as f:
        return json.load(f)
