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
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger("adapters.amazon_data")

# .env を読み込む（KEEPA_API_KEY をここでも確実に拾えるように）。
# yahoo_shopping に同じ軽量ローダがあるが、get_backend() が単独で呼ばれても
# Keepa が選ばれるよう、import 時に一度流し込む（既存の環境変数は上書きしない）。
from adapters.yahoo_shopping import _load_dotenv_if_present as _load_env  # noqa: E402

_load_env()


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

    def resolve_many(self, jans: list) -> dict:
        """複数 JAN をまとめて解決し {jan: AmazonProduct} を返す（トークン節約）。"""
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

    def resolve_many(self, jans: list) -> dict:
        """複数 JAN をまとめて解決（KeepaBackend と同じ契約）。"""
        out = {}
        for j in dict.fromkeys(jans):
            p = self._by_jan.get(j)
            if p is not None:
                out[j] = p
        return out

    def list_products(self, **filters) -> list[AmazonProduct]:
        # フィルタは discovery 側で適用するので、ここは全件を返すだけ。
        return list(self._all)


# =============================================================================
# Keepa レスポンス正規化ヘルパ（実 API のスキーマに合わせた純関数群）
# =============================================================================
# Keepa の stats.current / stats.avg90 は固定インデックスの配列。
# 実 API（domain=5, stats=90, offers=20）で 2026-06-05 にタカシが実測した index 表。
# 値 -1 は「データ無し/在庫なし」を意味する。価格は **円そのまま**（×100ではない）。
KEEPA_IDX_AMAZON = 0       # Amazon本体価格（円）
KEEPA_IDX_NEW = 1          # マーケットプレイス新品最安（円）
KEEPA_IDX_SALES_RANK = 3   # 売れ筋ランキング（※参照サブカテゴリの順位が入ることがある）
KEEPA_IDX_COUNT_NEW = 11   # 新品出品オファー数
KEEPA_IDX_BUY_BOX = 18     # Buy Box 価格（円）

# packageWeight は g、寸法（packageLength/Width/Height）は mm 単位で返る（実測確認済み）。


def _keepa_price_yen(value) -> Optional[float]:
    """Keepa 価格値（円・-1=無し）を float へ。-1/None は None（在庫なし/取得不可）。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v < 0 else v


def _pick_amazon_price(stats: dict) -> Optional[float]:
    """Amazon 売値を決める。Buy Box 価格を最優先し、無ければ新品最安→Amazon本体。

    せどりの「売れる実勢価格」は Buy Box（カート取得価格）が最も近いのでこれを採用。
    Buy Box が出ていない（-1）商品は New 最安、それも無ければ Amazon 本体にフォールバック。
    """
    if not isinstance(stats, dict):
        return None
    bb = _keepa_price_yen(stats.get("buyBoxPrice"))
    if bb is not None:
        return bb
    current = stats.get("current") or []

    def at(i):
        return _keepa_price_yen(current[i]) if len(current) > i else None

    return at(KEEPA_IDX_BUY_BOX) or at(KEEPA_IDX_NEW) or at(KEEPA_IDX_AMAZON)


def _pick_sales_rank(product: dict, stats: dict) -> Optional[int]:
    """売れ筋ランキングを決める。ルートカテゴリの大分類ランクを優先採用。

    Keepa の stats.current[3] には参照サブカテゴリの小さい順位が入ることがあるため、
    salesRanks{rootCategory: [...,rank]} の大分類ランクを優先する（月販推定の整合のため）。
    """
    root = product.get("rootCategory") or product.get("salesRankReference")
    ranks = product.get("salesRanks") or {}
    if root is not None and str(root) in ranks:
        series = ranks[str(root)]
        if isinstance(series, list) and series:
            last = series[-1]
            if isinstance(last, (int, float)) and last > 0:
                return int(last)
    # フォールバック: stats.current[3]
    if isinstance(stats, dict):
        cur = stats.get("current") or []
        if len(cur) > KEEPA_IDX_SALES_RANK:
            r = cur[KEEPA_IDX_SALES_RANK]
            if isinstance(r, (int, float)) and r > 0:
                return int(r)
    ref = product.get("salesRankReferenceHistory")  # 最後の手段は無し
    _ = ref
    return None


def _pick_offer_count(stats: dict) -> Optional[int]:
    """新品出品オファー数（相乗り出品者数の代理）。stats.current[11]=COUNT_NEW。"""
    if not isinstance(stats, dict):
        return None
    cur = stats.get("current") or []
    if len(cur) > KEEPA_IDX_COUNT_NEW:
        c = cur[KEEPA_IDX_COUNT_NEW]
        if isinstance(c, (int, float)) and c >= 0:
            return int(c)
    return None


def _pick_oos_rate_90d(stats: dict) -> Optional[float]:
    """過去90日の在庫切れ率（0〜1）。Buy Box の OOS%→New の OOS% の順で採用。

    Keepa の outOfStockPercentage90 はインデックス別配列（%・-1=データ無し）。
    Buy Box(18) を優先、無ければ New(1)。値は 0〜100 → 0〜1 に正規化。
    """
    if not isinstance(stats, dict):
        return None
    oos = stats.get("outOfStockPercentage90")
    if not isinstance(oos, list):
        return None

    def at(i):
        if len(oos) > i and isinstance(oos[i], (int, float)) and oos[i] >= 0:
            return oos[i] / 100.0
        return None

    v = at(KEEPA_IDX_BUY_BOX)
    if v is None:
        v = at(KEEPA_IDX_NEW)
    return v


def _estimate_monthly_sales(product: dict, sales_rank: Optional[int]) -> tuple:
    """月販個数を返す。Keepa の monthlySold があればそれ（実測）、無ければランク粗推定。

    返り値: (月販個数 or None, 推定かどうかのフラグ, 補足ノート or None)
    monthlySold は Keepa が「過去30日の購入数（Amazon表示の "○○+ bought"）」を持つ実値。
    無い商品はランキングからの非常に粗い対数推定で埋める（必ず「推定」と明示）。
    """
    ms = product.get("monthlySold")
    if isinstance(ms, (int, float)) and ms > 0:
        return int(ms), False, None  # 実測（Keepa monthlySold）
    if sales_rank is not None and sales_rank > 0:
        # 粗い対数近似。ホーム＆キッチン大分類の体感に合わせた当たり値（精度は低い）。
        # rank 1k→~600, 10k→~120, 50k→~30, 100k→~15, 300k→~5, それ以下→~1。
        import math
        est = max(1, int(20000 / (sales_rank ** 0.55)))
        return est, True, "月販はランキングからの粗い推定（Keepa monthlySold 無し）"
    return None, True, "月販データ無し（Keepa monthlySold/ランキングとも取得不可）"


# カテゴリ正規化: Keepa categoryTree（co.jp）→ fees.REFERRAL_FEE_TABLE のキー。
# 上位カテゴリ名の部分一致で判定（ベストエフォート。不明は default）。
_CATEGORY_NAME_MAP = [
    ("ホーム", "home_kitchen"), ("キッチン", "home_kitchen"),
    ("ビューティー", "beauty"), ("コスメ", "beauty"),
    ("ドラッグストア", "drugstore"), ("ヘルス", "health"), ("医薬", "drugstore"),
    ("おもちゃ", "toys"), ("ホビー", "toys"), ("ゲーム", "toys"),
    ("家電", "electronics"), ("カメラ", "electronics"),
    ("パソコン", "pc"), ("周辺機器", "pc"),
    ("スポーツ", "sports"), ("アウトドア", "sports"),
    ("DIY", "diy"), ("工具", "diy"),
    ("服", "apparel"), ("ファッション", "apparel"), ("シューズ", "apparel"),
    ("食品", "food"), ("飲料", "food"), ("食べ物", "food"),
    ("ペット", "pet"),
    ("文房具", "office"), ("オフィス", "office"), ("文具", "office"),
    ("本", "books"), ("ブック", "books"),
]


def _map_category_key(product: dict) -> str:
    """Keepa categoryTree から fees の category_key をベストエフォートで決める。"""
    tree = product.get("categoryTree") or []
    names = [c.get("name", "") for c in tree if isinstance(c, dict)]
    # 上位（ルート）から見て最初に一致したものを採用。
    for name in names:
        for needle, key in _CATEGORY_NAME_MAP:
            if needle in name:
                return key
    return "default"  # ⚠ 不明カテゴリは default（料率15%）。手数料区分は推定誤差あり。


def _map_size_key(product: dict) -> tuple:
    """packageWeight(g)/寸法(mm) から fees の size_key をベストエフォートで決める。

    返り値: (size_key, 補足ノート or None)
    ⚠ 実 FBA 料金は寸法×重量の細区分。ここは代表区分への粗いマッピング（推定誤差あり）。
    寸法・重量が取れない場合は standard_1 をデフォルトに置く（⚠ノート付き）。
    """
    w = product.get("packageWeight")  # g
    dims = [
        product.get("packageLength"),
        product.get("packageWidth"),
        product.get("packageHeight"),
    ]
    dims_mm = [d for d in dims if isinstance(d, (int, float)) and d > 0]
    longest_cm = (max(dims_mm) / 10.0) if dims_mm else None
    sum_cm = (sum(dims_mm) / 10.0) if dims_mm else None
    weight_g = w if isinstance(w, (int, float)) and w > 0 else None

    if weight_g is None and not dims_mm:
        return "standard_1", "⚠ FBAサイズは寸法/重量不明のため standard_1 を仮定（手数料推定誤差あり）"

    # 重量・寸法から代表区分へ（保守的に大きめ＝手数料を過小評価しない方向）。
    g = weight_g or 0
    if g <= 250 and (longest_cm is None or longest_cm <= 25):
        return "small", None
    if g <= 1000:
        return "standard_1", None
    if g <= 2000:
        return "standard_2", None
    if g <= 5000 or (sum_cm is not None and sum_cm <= 60):
        return "large_1", None
    return "large_2", None


def _product_to_amazon(product: dict) -> Optional[AmazonProduct]:
    """Keepa の1商品 dict を AmazonProduct へ正規化。ASIN 無しは None（該当なし）。"""
    asin = product.get("asin")
    if not asin:
        return None

    stats = product.get("stats") or {}
    price = _pick_amazon_price(stats)
    sales_rank = _pick_sales_rank(product, stats)
    offer_count = _pick_offer_count(stats)
    oos = _pick_oos_rate_90d(stats)
    monthly, is_estimate, ms_note = _estimate_monthly_sales(product, sales_rank)
    category_key = _map_category_key(product)
    size_key, size_note = _map_size_key(product)

    p = AmazonProduct(
        asin=asin,
        title=product.get("title") or "",
        current_price=price,
        sales_rank=sales_rank,
        monthly_sales=monthly,
        offer_count=offer_count,
        oos_rate_90d=oos,
        category_key=category_key,
        size_key=size_key,
        jan=None,  # 突合キーは呼び出し側（resolve_by_jan の引数）で補完
        is_sample=False,
    )
    # 監査用メタは AmazonProduct に専用フィールドが無いため、推定フラグは
    # 呼び出し側ログ＋下流ノートで扱う。ここでは属性として一時付与しておく。
    p.monthly_sales_is_estimate = is_estimate  # type: ignore[attr-defined]
    p.estimate_notes = [n for n in (ms_note if is_estimate else None, size_note) if n]  # type: ignore[attr-defined]
    return p


# =============================================================================
# バックエンド2: Keepa（本番・要 KEEPA_API_KEY）
# =============================================================================
class KeepaBackend:
    """Keepa Product API バックエンド（本番・Amazon.co.jp = domain 5）。

    Keepa Product API を生 HTTPS で叩く（公式 python クライアントには依存しない＝YAGNI）。
    エンドポイント: GET https://api.keepa.com/product
      ?key=...&domain=5&code=<JAN>[,JAN...]&stats=90&offers=20
    - code に JAN を渡すと Keepa が JAN→ASIN を解決して商品を返す。
    - 複数 JAN はカンマ区切りで1リクエストにまとめられる（トークン節約）。
    - レスポンスは gzip。requests が自動解凍する。価格は **円そのまま**（-1=無し）。

    トークン制約（残わずか）対策:
    - 1リクエストの JAN 数を MAX_JANS_PER_CALL にハード上限。
    - レスポンスの tokensLeft をログ表示し、消費を可視化する。
    """

    KEEPA_DOMAIN_JP = 5  # co.jp
    ENDPOINT = "https://api.keepa.com/product"
    MAX_JANS_PER_CALL = 10  # 1検索で Keepa に問い合わせる JAN の上限（トークン節約・調整可）

    def __init__(self, api_key: Optional[str] = None, *, timeout: int = 60):
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY")
        self.timeout = timeout
        self.last_tokens_left: Optional[int] = None
        self.last_tokens_consumed: Optional[int] = None

    @property
    def is_live(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # 単一 JAN 解決（インターフェース契約）
    # ------------------------------------------------------------------
    def resolve_by_jan(self, jan: str) -> Optional[AmazonProduct]:
        """JAN 1件を Keepa で解決。該当なし/ASIN無しは None（呼び出し側で除外）。"""
        results = self.resolve_many([jan])
        return results.get(jan)

    # ------------------------------------------------------------------
    # 複数 JAN を1リクエストで解決（トークン節約の主役）
    # ------------------------------------------------------------------
    def resolve_many(self, jans: list) -> dict:
        """JAN リストを最大 MAX_JANS_PER_CALL 件まで1リクエストで突合。

        返り値: {jan: AmazonProduct}。Amazon に該当しなかった JAN はキーごと欠落。
        Keepa は code 順に products を返すとは限らないため、eanList/upcList で JAN を突合する。
        """
        self._require_key()
        uniq = [j for j in dict.fromkeys(jans) if j]  # 重複排除・空除外（順序維持）
        if not uniq:
            return {}
        if len(uniq) > self.MAX_JANS_PER_CALL:
            logger.info(
                "Keepa: JANを%d件→上限%d件に切り詰め（トークン節約）",
                len(uniq), self.MAX_JANS_PER_CALL,
            )
            uniq = uniq[: self.MAX_JANS_PER_CALL]

        payload = self._request(code=",".join(uniq))
        self.last_tokens_left = payload.get("tokensLeft")
        self.last_tokens_consumed = payload.get("tokensConsumed")
        logger.info(
            "Keepa: JAN%d件問い合わせ 消費tokens=%s 残tokens=%s",
            len(uniq), self.last_tokens_consumed, self.last_tokens_left,
        )

        products = payload.get("products") or []
        # JAN→商品 の対応を eanList/upcList で取る。無ければ入力順でのフォールバック対応。
        out: dict = {}
        by_jan: dict = {}
        unmatched_products = []
        for prod in products:
            jan_codes = (prod.get("eanList") or []) + (prod.get("upcList") or [])
            jan_codes = [str(c) for c in jan_codes]
            matched = next((j for j in uniq if j in jan_codes), None)
            if matched:
                by_jan[matched] = prod
            else:
                unmatched_products.append(prod)

        # eanList で取れなかった分は、入力順 × 返却順のフォールバックで割り当てる
        # （Keepa は概ね code の順序で返すため）。それでも紐付かない JAN は「該当なし」。
        leftover_jans = [j for j in uniq if j not in by_jan]
        for j, prod in zip(leftover_jans, unmatched_products):
            by_jan[j] = prod

        for jan in uniq:
            prod = by_jan.get(jan)
            if prod is None:
                logger.info("除外[Amazon該当無し]: JAN=%s（Keepaに商品なし）", jan)
                continue
            ap = _product_to_amazon(prod)
            if ap is None:
                logger.info("除外[ASIN無し]: JAN=%s", jan)
                continue
            ap.jan = jan
            out[jan] = ap
        return out

    # ------------------------------------------------------------------
    # Amazon 起点（Product Finder）—— 今回スコープ外。明示的に未実装。
    # ------------------------------------------------------------------
    def list_products(self, **filters) -> list[AmazonProduct]:
        """Amazon起点ディスカバリー（Product Finder）。本タスクのスコープ外。

        (あ)モードは別途 Product Finder API（/query?selection=...）の実装が必要。
        今回は (い)仕入れ元起点を本番化することに集中するため未実装。
        ※app 側は (あ) では Keepa を使わずサンプル/Yahoo 仮置きにフォールバックする。
        """
        raise NotImplementedError(
            "Keepa Product Finder（Amazon起点(あ)）は本タスクのスコープ外です。"
            "(い)仕入れ元起点は resolve_by_jan/resolve_many で本番稼働します。"
        )

    # ------------------------------------------------------------------
    # HTTP（生 requests・遅延 import）
    # ------------------------------------------------------------------
    def _request(self, *, code: str) -> dict:
        import requests  # 遅延 import（サンプル経路では不要）

        params = {
            "key": self.api_key,
            "domain": self.KEEPA_DOMAIN_JP,
            "code": code,
            "stats": 90,    # 90日統計（OOS率・平均など）を含める
            "offers": 20,   # 出品オファーを最大20件（Buy Box/出品者数の精度向上）
        }
        resp = requests.get(self.ENDPOINT, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _require_key(self):
        if not self.is_live:
            raise RuntimeError(
                "KEEPA_API_KEY が未設定です。.env に KEEPA_API_KEY を設定してください。"
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
