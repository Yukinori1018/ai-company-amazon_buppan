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


class KeepaRateLimitError(RuntimeError):
    """Keepa のトークン上限（HTTP 429）にリトライ尽きても到達した時に投げる明確な例外。

    呼び出し側（resolve_many / app_discovery）がこれを捕捉して「混雑＝待てば直る」と
    UI 上で判別できるようにするための専用型。RuntimeError を継承するので、
    既存の `except RuntimeError` 経路でも握れる（ただし UI では型で分岐して親切表示する）。
    """

    def __init__(self, message: str, *, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after  # 推奨待機秒（分かれば。UI 表示に使う）

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
    # 過去の売値推移（古い→新しい順の円の系列）。最悪相場シミュレーション/折れ線表示に使う。
    # Keepa stats から取れた時のみ入る。取れない/サンプル簡易時は None または擬似系列。
    price_history: Optional[list] = None  # 例: [74000, 72000, ..., 61800]（円）
    # メーカー仕入れ（T-20260705-002）用。Keepa raw product の brand/manufacturer を保持する。
    # せどり用フロー（JAN突合→利益計算）では未使用でも支障ない任意メタ。追加トークンは消費しない
    # （brand/manufacturer は stats=90 の1バッチ応答に既に含まれる）。
    brand: Optional[str] = None           # ブランド名（Keepa raw の brand）
    manufacturer: Optional[str] = None    # 製造元（Keepa raw の manufacturer）

    @property
    def maker(self) -> str:
        """メーカー名の当たり。brand > manufacturer の優先（サトル _brand_of と同順）。両方無ければ ""。"""
        return (self.brand or self.manufacturer or "").strip()


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
            cur = r.get("current_price")
            # サンプルでも最悪相場シミュレーションを試せるよう、現在価格から擬似の過去相場を合成。
            # 過去最安=現在の82%・90日平均=92%・現在 の3点（古い→新しい）。実データではない目安。
            hist = r.get("price_history")
            if hist is None and isinstance(cur, (int, float)) and cur > 0:
                hist = [round(cur * 0.82), round(cur * 0.92), cur]
            p = AmazonProduct(
                asin=r["asin"],
                title=r.get("title", ""),
                current_price=cur,
                sales_rank=r.get("sales_rank"),
                monthly_sales=r.get("monthly_sales"),
                offer_count=r.get("offer_count"),
                oos_rate_90d=r.get("oos_rate_90d"),
                category_key=r.get("category_key", "default"),
                size_key=r.get("size_key", "standard_1"),
                jan=r.get("jan"),
                is_sample=True,
                price_history=hist,
                brand=r.get("brand"),
                manufacturer=r.get("manufacturer"),
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


def _price_at_index(arr, i) -> Optional[float]:
    """stats の固定インデックス配列から1価格を取り出す（-1/欠落は None）。"""
    if not isinstance(arr, list) or len(arr) <= i:
        return None
    return _keepa_price_yen(arr[i])


def _extract_price_history(stats: dict) -> Optional[list]:
    """Keepa stats から「過去相場の代表点」系列を軽量に組み立てる（円・古い→新しい順）。

    フル csv（history=1）は重くトークンを食うため要求しない。代わりに stats=90 で既に
    返る代表統計（min/avg90/avg30/current の Buy Box→New フォールバック）から、
    『最悪のケース＝過去相場の最安水準』を含む数点の系列を作る。
    最悪相場シミュレーション（過去最安まで下落しても黒字か）に必要十分な粒度。

    返り値: [過去最安, 90日平均, 30日平均, 現在] のうち取れた点（円, 重複/欠落除去）。
    1点も取れなければ None（UI 側でプレースホルダ＋手動入力に切り替える）。
    """
    if not isinstance(stats, dict):
        return None
    # Buy Box(18) を主、無ければ New(1) を使う（_pick_amazon_price と同じ優先順）。
    idx = (KEEPA_IDX_BUY_BOX, KEEPA_IDX_NEW)

    def from_block(block):
        if not isinstance(block, list):
            return None
        for i in idx:
            v = _price_at_index(block, i)
            if v is not None:
                return v
        return None

    points = []
    lo = from_block(stats.get("min90") or stats.get("min"))
    avg90 = from_block(stats.get("avg90"))
    avg30 = from_block(stats.get("avg30"))
    cur = _pick_amazon_price(stats)
    for v in (lo, avg90, avg30, cur):
        if v is not None and (not points or points[-1] != v):
            points.append(v)
    return points or None


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
    price_history = _extract_price_history(stats)

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
        price_history=price_history,
        # メーカー仕入れ用（追加トークン0。空文字は None に正規化して maker プロパティを素直にする）。
        brand=(product.get("brand") or "").strip() or None,
        manufacturer=(product.get("manufacturer") or "").strip() or None,
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
      ?key=...&domain=5&code=<JAN>[,JAN...]&stats=90&offers=1（offersは最小限＝節約）
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

    # offers パラメータ: 出品オファーの生配列の取得数。Keepa は offers の値だけ
    # トークンを多く消費する（offers=20 は1商品あたり高コスト）。本パイプラインが
    # 実際に使うのは stats.buyBoxPrice / stats.current[COUNT_NEW] / OOS% であり、
    # これらは stats=90 だけで埋まり、offers の生配列は一切パースしていない。
    #
    # ⚠ Keepa 仕様（実測 2026-06-05 タカシ）: offers は「0 も 1 も invalidParameter で拒否」
    #   され、要求するなら **最低20**。中途半端な値（1等）を渡すと products が空で返り、
    #   (あ)Amazon起点が「0件」になる主因だった。stats だけで必要値は揃うため、
    #   offers パラメータは **付けない**（None＝省略）のが最小トークンかつ正解。
    OFFERS_PER_PRODUCT = None  # None=offersを送らない（最小トークン）。送るなら20以上必須。

    # 429（トークン上限）時の指数バックオフ設定。残トークン枯渇時の自動回復用。
    RETRY_BACKOFFS_SEC = (5, 10, 20)  # リトライ毎の待機秒（最大3回再試行）
    MAX_RETRY_WAIT_SEC = 90           # refillIn 等から算出する待機の上限（無限待機防止）

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
        # JAN→商品 の対応は eanList/upcList の「実際の一致」のみで取る。
        # ⚠ 旧実装は eanList で取れなかった商品を入力順×返却順で zip 割り当てしていたが、
        #   これは別JAN商品を無理やり別JANへ紐付ける重大バグの温床だった（社長報告 2026-06-06）。
        #   位置フォールバックは撤去。問い合わせJANを eanList/upcList に実際に含む商品だけを
        #   確定マッチとし、含まれない商品は「該当なし」で正直に除外する。
        out: dict = {}
        by_jan: dict = {}
        for prod in products:
            jan_codes = (prod.get("eanList") or []) + (prod.get("upcList") or [])
            jan_codes = [str(c) for c in jan_codes]
            matched = next((j for j in uniq if j in jan_codes), None)
            if matched:
                # 同一JANに複数商品が返る場合は先勝ち（最初の確定マッチを採用）
                by_jan.setdefault(matched, prod)

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
    # Amazon 起点（Best Sellers）= キーワード不要の売れ筋自動収集
    # ------------------------------------------------------------------
    BESTSELLERS_ENDPOINT = "https://api.keepa.com/bestsellers"
    MAX_ASINS_PER_LIST = 15  # 詳細取得する ASIN のハードキャップ（社長制約：最大15件）

    def list_products(self, **filters) -> list[AmazonProduct]:
        """Keepa Best Sellers でカテゴリの売れ筋 ASIN を取り、先頭N件だけ詳細取得する。

        引数（filters）:
          category_id : Amazon.co.jp ブラウズノードID（presets.AMAZON_CATEGORIES から）。
                        未指定なら呼び出し側で既定カテゴリを渡す前提。
          limit       : 詳細取得する ASIN の上限（既定/上限とも MAX_ASINS_PER_LIST=10）。

        トークン節約:
          1) bestsellers で ASIN リスト取得（=軽い。1リクエスト）。
          2) 先頭 limit 件だけ product で詳細取得（1バッチ・stats/offers 込み）。
          → 1回の探索で詳細取得は最大10 ASIN にハードキャップ。
        """
        self._require_key()
        category_id = filters.get("category_id")
        limit = min(int(filters.get("limit", self.MAX_ASINS_PER_LIST)),
                    self.MAX_ASINS_PER_LIST)
        if category_id is None:
            logger.info("list_products: category_id 未指定のため空を返す")
            return []

        asins = self._fetch_bestseller_asins(category_id)
        if not asins:
            logger.info("Best Sellers: ASINを取得できませんでした（category=%s）", category_id)
            return []
        asins = asins[:limit]
        logger.info("Best Sellers: 売れ筋ASIN %d件の詳細を取得（category=%s）",
                    len(asins), category_id)

        payload = self._request(asin=",".join(asins))
        self.last_tokens_left = payload.get("tokensLeft")
        self.last_tokens_consumed = payload.get("tokensConsumed")
        logger.info("Keepa: 詳細%d件 消費tokens=%s 残tokens=%s",
                    len(asins), self.last_tokens_consumed, self.last_tokens_left)

        out: list[AmazonProduct] = []
        for prod in payload.get("products") or []:
            ap = _product_to_amazon(prod)
            if ap is None:
                continue
            # Amazon起点は JAN を eanList から拾っておく（仕入元突合のヒントに）。
            eans = [str(c) for c in (prod.get("eanList") or [])]
            if eans:
                ap.jan = eans[0]
            out.append(ap)
        return out

    # ------------------------------------------------------------------
    # Product Finder（条件抽出）= キーワード不要の「原石オートサーチ」(あ)
    # ------------------------------------------------------------------
    QUERY_ENDPOINT = "https://api.keepa.com/query"

    def find_products(self, selection: dict, *, limit: Optional[int] = None) -> list[AmazonProduct]:
        """Keepa Product Finder で条件に合う ASIN 群を引き、先頭N件だけ詳細取得する。

        引数:
          selection : Keepa Product Finder の selection(JSON)。
                      例: {"current_SALES_gte":1000, "current_SALES_lte":80000,
                           "current_COUNT_NEW_gte":2, "current_COUNT_NEW_lte":10,
                           "current_NEW_gte":1000, "current_NEW_lte":10000,
                           "categories_include":[3828871], "perPage":50, "page":0,
                           "sort":[["current_SALES","asc"]]}
          limit     : 詳細取得する ASIN の上限（既定/上限とも MAX_ASINS_PER_LIST=15）。

        トークン節約（社長制約：実走2〜3回・詳細最大15件）:
          1) query で条件に合う ASIN リストを取得（=Finderコール。10token+ASIN数/100）。
          2) 先頭 limit 件だけ product で詳細取得（1バッチ・stats/offers 込み）。
          → 1探索で詳細取得は最大 MAX_ASINS_PER_LIST=15 ASIN にハードキャップ。

        返り値: AmazonProduct のリスト（詳細取得＋正規化済み）。
        Product Finder は ASIN しか返さないため、詳細は product で別途取得する（Keepa仕様）。
        """
        self._require_key()
        cap = self.MAX_ASINS_PER_LIST
        limit = min(int(limit), cap) if limit is not None else cap

        asins = self._fetch_finder_asins(selection)
        if not asins:
            logger.info("Product Finder: 条件に合うASINが0件でした（条件を緩める/別カテゴリ）")
            return []
        asins = asins[:limit]
        logger.info("Product Finder: 条件合致ASIN %d件の詳細を取得（先頭%d件）",
                    len(asins), limit)

        payload = self._request(asin=",".join(asins))
        self.last_tokens_left = payload.get("tokensLeft")
        self.last_tokens_consumed = payload.get("tokensConsumed")
        logger.info("Keepa: 詳細%d件 消費tokens=%s 残tokens=%s",
                    len(asins), self.last_tokens_consumed, self.last_tokens_left)

        out: list[AmazonProduct] = []
        for prod in payload.get("products") or []:
            ap = _product_to_amazon(prod)
            if ap is None:
                continue
            eans = [str(c) for c in (prod.get("eanList") or [])]
            if eans:
                ap.jan = eans[0]  # 仕入元突合のヒント
            out.append(ap)
        return out

    def _fetch_finder_asins(self, selection: dict) -> list:
        """query エンドポイントで Product Finder を叩き、ASIN リストを取得する。

        Keepa 仕様: GET https://api.keepa.com/query?key=..&domain=5&selection=<JSON>。
        レスポンスは {"asinList": [...], "tokensLeft": ..., "totalResults": ...}。
        """
        import json as _json  # 遅延 import
        import requests        # 遅延 import

        params = {
            "key": self.api_key,
            "domain": self.KEEPA_DOMAIN_JP,
            "selection": _json.dumps(selection, separators=(",", ":")),
        }
        resp = requests.get(self.QUERY_ENDPOINT, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        self.last_tokens_left = payload.get("tokensLeft")
        self.last_tokens_consumed = payload.get("tokensConsumed")
        total = payload.get("totalResults")
        asins = payload.get("asinList") or []
        logger.info(
            "Product Finder: 該当%s件中 ASIN %d件取得 消費tokens=%s 残tokens=%s",
            total, len(asins), self.last_tokens_consumed, self.last_tokens_left,
        )
        return [str(a) for a in asins if a]

    def _fetch_bestseller_asins(self, category_id) -> list:
        """bestsellers エンドポイントでカテゴリの売れ筋 ASIN リストを取得する。"""
        import requests  # 遅延 import

        params = {
            "key": self.api_key,
            "domain": self.KEEPA_DOMAIN_JP,
            "category": str(category_id),
        }
        resp = requests.get(self.BESTSELLERS_ENDPOINT, params=params,
                            timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        self.last_tokens_left = payload.get("tokensLeft")
        # bestsellers のレスポンス形は { "bestSellersList": {"asinList": [...]} }。
        bsl = payload.get("bestSellersList") or {}
        asins = bsl.get("asinList") or payload.get("asinList") or []
        return [str(a) for a in asins if a]

    # ------------------------------------------------------------------
    # HTTP（生 requests・遅延 import）
    # ------------------------------------------------------------------
    def _request(self, *, code: Optional[str] = None, asin: Optional[str] = None) -> dict:
        """Keepa product を1回叩く。429（トークン上限）は指数バックオフで自動リトライ。

        トークンが枯渇していると Keepa は HTTP 429 を返す。ここで握りつぶさず、
        (1) レスポンスの refillIn（次のトークン補充までのミリ秒）が分かればそれを優先、
        (2) 分からなければ RETRY_BACKOFFS_SEC の指数バックオフ、で最大3回まで待って再試行する。
        それでも回復しなければ KeepaRateLimitError を投げ、呼び出し側が「混雑」を判別できるようにする。
        """
        import time

        import requests  # 遅延 import（サンプル経路では不要）

        params = {
            "key": self.api_key,
            "domain": self.KEEPA_DOMAIN_JP,
            "stats": 90,    # 90日統計（OOS率・平均など）を含める
        }
        # offers は None なら送らない（Keepa は 0/1 を invalidParameter で拒否し products が
        # 空になる。20以上でないと無効）。stats=90 だけで必要値（buyBox/COUNT_NEW/OOS）は揃う。
        if self.OFFERS_PER_PRODUCT:
            params["offers"] = self.OFFERS_PER_PRODUCT
        if code is not None:
            params["code"] = code   # JAN 突合（(い)経路）
        if asin is not None:
            params["asin"] = asin   # ASIN 直接取得（(あ)Best Sellers 経路）

        last_retry_after: Optional[int] = None
        # 初回 + 最大 len(RETRY_BACKOFFS_SEC) 回の再試行。
        for attempt in range(len(self.RETRY_BACKOFFS_SEC) + 1):
            resp = requests.get(self.ENDPOINT, params=params, timeout=self.timeout)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp.json()

            # --- 429: トークン上限。待機秒を算出して再試行する ---
            wait = self._retry_after_seconds(resp, attempt)
            last_retry_after = wait
            if attempt >= len(self.RETRY_BACKOFFS_SEC):
                break  # リトライ尽きた → ループ後に明確な例外を投げる
            logger.warning(
                "Keepa 429（トークン上限）。%d秒待って再試行します（%d/%d回目）",
                wait, attempt + 1, len(self.RETRY_BACKOFFS_SEC),
            )
            time.sleep(wait)

        raise KeepaRateLimitError(
            "Keepa のトークン上限に達しました（リトライ後も解消せず）。"
            "30〜60秒ほど待って再実行してください。1回の取得件数を減らすと安定します。",
            retry_after=last_retry_after,
        )

    def _retry_after_seconds(self, resp, attempt: int) -> int:
        """429 レスポンスから次の再試行までの待機秒を決める。

        優先順位: (1) JSON 本文の refillIn(ms)→秒換算、(2) Retry-After ヘッダ、
        (3) RETRY_BACKOFFS_SEC の指数バックオフ。いずれも MAX_RETRY_WAIT_SEC で頭打ち。
        Keepa は 429 でもトークン補充情報（refillIn）を本文に返すことがあるためそれを尊重する。
        """
        fallback = self.RETRY_BACKOFFS_SEC[min(attempt, len(self.RETRY_BACKOFFS_SEC) - 1)]
        wait: Optional[float] = None

        # (1) Keepa JSON 本文の refillIn（ミリ秒）。
        try:
            body = resp.json()
            refill_ms = body.get("refillIn")
            if isinstance(refill_ms, (int, float)) and refill_ms > 0:
                wait = refill_ms / 1000.0 + 1.0  # 補充直後を狙って +1s 余裕
        except Exception:  # noqa: BLE001  本文が JSON でない/壊れている場合は無視
            pass

        # (2) 標準の Retry-After ヘッダ（秒）。
        if wait is None:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    wait = float(ra)
                except (TypeError, ValueError):
                    wait = None

        # (3) 指数バックオフへフォールバック。
        if wait is None:
            wait = fallback

        return int(max(1, min(wait, self.MAX_RETRY_WAIT_SEC)))

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
