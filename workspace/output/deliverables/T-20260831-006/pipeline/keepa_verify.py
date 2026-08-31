"""Keepa を **検証役**として使う層（社長のご指示: 発見は NETSEA、検証は Keepa）。

やること: JAN13 → ASIN の逆引き＋Amazon 側の実績取得。
やらないこと: 商品の発見（Product Finder は一切叩きません）。

━━ トークンの実測（2026-08-31 / T-20260831-006）━━━━━━━━━━━━━━━━━━━━━━━
    課金の単位は **「返ってきた商品数」× 1トークン**。投げた JAN の数ではありません。

    | 投げた JAN | 返った商品 | tokensConsumed |
    |---|---|---|
    | 20件 | 16件 | 16 |
    | 150件 | 95件 | 95 |
    | **70件（全部ハズレ）** | **0件** | **1** |
    | **100件（メーカー中心）** | **≒190件** | **190** |

    ここから分かることが2つあります。

    1. **ヒットしなかった JAN はタダ。** 「NETSEA にあるが Amazon に無い商品」の
       仕分けは実質無料で終わります。
    2. ⚠️ **1件あたり1トークンが上限だと思ってはいけません。**
       1つの JAN が複数 ASIN を返せば、その数だけ課金されます。
       最後の行がそれで、残高が **マイナス101** まで落ちました
       （`tokenFlowReduction` は 0＝ペナルティではなく、単に読みが甘かった）。
       → `TokenBudget` は**走りながら実測レートで見積もり直します**（固定値を信じない）。

    バッチは100件（Keepa の code パラメータ上限）。「1周が5〜10分」は
    無人運転で生死が見える下限です（T-20260817-005 の教訓）。
"""

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config

KEEPA_BASE = "https://api.keepa.com"

# Keepa csv/stats のインデックス（公式 product-object より）。名前で使わず、必ず定義を見る。
IDX_AMAZON = 0
IDX_NEW = 1          # 新品最安。2026-02-23 以降は「着地価格＝出品価格＋送料」
IDX_SALES_RANK = 3
IDX_COUNT_NEW = 11   # ⚠️ 新品オファー本数。**出品者数ではない**（1社が FBA/FBM で2本出せば2）

# FBA 標準サイズの上限（mm / g）。これを超えたら大型（＝手数料が跳ねる）。
FBA_STD_DIMS_MM = (450, 350, 200)
FBA_STD_WEIGHT_G = 9000


def load_env(extra_paths: list = None) -> None:
    """KEEPA_API_KEY / NETSEA_API_TOKEN を環境変数に用意する。

    優先順位は「既に環境にある値 > .env ファイル」。**上書きはしません。**
    シークレットは Git に置かない方針なので、探すのは .gitignore 済みの場所だけです。
    """
    here = Path(__file__).resolve()
    repo = here.parents[5] if len(here.parents) > 5 else here.parent
    candidates = [
        Path.home() / ".config" / "ai-company-amazon-buppan" / ".env",
        repo / "workspace" / "output" / "agent_output" / "T-20260521-005" / "code" / ".env",
        here.parents[1] / ".env",
    ] + [Path(p) for p in (extra_paths or [])]
    for path in candidates:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        except OSError:
            continue


@dataclass
class AmazonFacts:
    """Keepa から取れた Amazon 側の事実。**取れなかった値は None のまま**にする。

    「0」と「不明」を同じ列に混ぜないための dataclass です。CSV では None は空欄になります。
    """

    jan: str
    asin: Optional[str] = None
    title: str = ""
    brand: str = ""
    # 新品最安（送料込・税込）。current が無ければ90日平均へ落とし、出所を price_source に残す。
    price_yen: Optional[int] = None
    price_source: str = ""
    sales_rank: Optional[int] = None
    # 直近30日のランク下落回数。Keepa 公式が「概算の販売個数」として使う代理指標。
    drops30: Optional[int] = None
    drops90: Optional[int] = None
    # ⚠️ 新品オファー本数。出品者数ではない（--verify-sellers で実数に差し替わる）。
    offer_count: Optional[int] = None
    real_seller_count: Optional[int] = None
    # Amazon 本体の出品有無。-1 = オファーが存在しない（current[0] では判定できない）。
    availability_amazon: Optional[int] = None
    category_names: list = field(default_factory=list)
    package_mm: tuple = ()
    package_g: Optional[int] = None
    found: bool = False
    # この JAN に紐づいた ASIN の数。2以上なら同じ商品が複数出品されている。
    asin_count: int = 0
    # この ASIN が「1注文で何個ぶんか」。まとめ売り出品なら2以上。
    # 卸値はこの数だけ掛かるので、利益計算で必ず使う。
    pack_size: int = 1

    @property
    def seller_count_source(self) -> str:
        """出品者数として出している値が「何の数字か」を必ず添えるためのラベル。

        ⚠️ **保存された属性にしてはいけません。** 以前これを普通のフィールドにしていたところ、
           値を入れ忘れた経路（テストで発見）から空欄のまま CSV に出ました。
           `COUNT_NEW` を出品者数と読み違えた事故は過去に候補top100の35%を汚染しています
           （`knowledge_keepa_count_new_is_not_seller_count`）。**由来は必ず値についてまわること。**
        """
        if self.real_seller_count is not None:
            return "実セラー数(offers検証済み)"
        if self.offer_count is not None:
            return "COUNT_NEW(新品オファー本数・出品者数ではない)"
        return ""

    @property
    def amazon_sells_it(self) -> Optional[bool]:
        if self.availability_amazon is None:
            return None
        return self.availability_amazon != -1

    @property
    def amazon_url(self) -> str:
        return f"https://www.amazon.co.jp/dp/{self.asin}" if self.asin else ""

    @property
    def keepa_url(self) -> str:
        return f"https://keepa.com/#!product/5-{self.asin}" if self.asin else ""


class TokenBudget:
    """Keepa の残トークンを見張って、429 を出す前に待つ。

    貯め込めない（上限1,200・補充20/分）ので、**待つこと自体がこのパイプラインの仕事**です。
    レスポンスの tokensLeft / refillIn をそのまま信じ、自前の推定はしません。
    """

    def __init__(self, min_before_batch: int = config.KEEPA_MIN_TOKENS_BEFORE_BATCH):
        self.min_before_batch = min_before_batch
        self.left: Optional[int] = None
        self.refill_in_ms: int = 0
        self.consumed_total = 0
        self.codes_total = 0
        self.starved_since: Optional[float] = None

    def note(self, payload: dict, codes: int = 0) -> None:
        if "tokensLeft" in payload:
            self.left = payload.get("tokensLeft")
        self.refill_in_ms = payload.get("refillIn") or 0
        self.consumed_total += payload.get("tokensConsumed") or 0
        self.codes_total += codes

    @property
    def tokens_per_code(self) -> float:
        """実測の「JAN 1件あたり何トークン掛かっているか」。

        ⚠️ **1件＝1トークン上限だと思ってはいけません。**
           課金は「**返ってきた商品数**」に対して起きるので、1つの JAN が複数 ASIN を
           返せば 1件で2も3も掛かります。実測で 100件のバッチが **190トークン**掛かり、
           残高がマイナス101まで落ちました（`tokenFlowReduction` は 0＝ペナルティではなく、
           単に実コストが読みより高かった）。
           だから固定値で見積もらず、**走りながら実測値で見積もり直します。**
        """
        if self.codes_total <= 0:
            return 1.0
        return max(self.consumed_total / self.codes_total, 0.1)

    def required_for(self, batch_size: int) -> int:
        """次のバッチを撃つ前に持っておくべき残トークン（実測レートから逆算）。"""
        need = batch_size * self.tokens_per_code * 1.3   # 3割の安全代
        return int(max(need, self.min_before_batch))

    def wait_if_needed(self, log=print, batch_size: int = 0) -> bool:
        """必要なら回復を待つ。諦めるべき状況なら False を返す（呼び出し側が止める）。"""
        threshold = self.required_for(batch_size) if batch_size else self.min_before_batch
        if self.left is None or self.left >= threshold:
            self.starved_since = None
            return True
        self.min_before_batch = threshold
        if self.starved_since is None:
            self.starved_since = time.time()
        elif time.time() - self.starved_since > config.KEEPA_STARVATION_MINUTES * 60:
            log(f"!! トークンが {config.KEEPA_STARVATION_MINUTES} 分回復しません。停止します")
            return False
        need = threshold - self.left            # 残高がマイナスならその分も足りない
        wait = max(need / 20.0 * 60.0, self.refill_in_ms / 1000.0, 15.0)
        wait = min(wait, 900.0)
        log(f"   トークン残 {self.left} → {threshold} まで {wait:.0f}秒待機"
            f"（実測 {self.tokens_per_code:.2f} トークン/件）")
        time.sleep(wait)
        return True


class KeepaVerifier:
    """JAN のリストを受け取り、AmazonFacts に変換する。"""

    def __init__(self, api_key: Optional[str] = None, *, log=print):
        load_env()
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY")
        if not self.api_key:
            raise SystemExit(
                "KEEPA_API_KEY が未設定です。.env か環境変数に設定してください。"
            )
        self.budget = TokenBudget()
        self.log = log
        self.requests_made = 0
        self.codes_sent = 0
        self.products_returned = 0

    # -- HTTP ----------------------------------------------------------------
    def _get(self, path: str, params: dict, label: str, codes: int = 0) -> dict:
        """Keepa を1回叩く。落ちない・黙らない。失敗は {} を返し、理由をログに出す。"""
        import requests

        params = dict(params, key=self.api_key, domain=config.KEEPA_DOMAIN_JP)
        for attempt in range(5):
            try:
                resp = requests.get(f"{KEEPA_BASE}/{path}", params=params, timeout=300)
            except Exception as e:  # noqa: BLE001 — 無人運転で落とさない
                self.log(f"   {label} 通信エラー: {e}")
                time.sleep(15)
                continue
            if resp.status_code == 402:
                # 契約が無効。母数の枯渇ではないので、リトライしても直らない。
                # 課金・契約は CLAUDE.md §4.1 なので、自分で判断せず止めて差し戻す。
                raise SystemExit(
                    "Keepa が HTTP 402（アクセス権なし）を返しました。契約・支払い・キーの"
                    "いずれかの問題です。課金は §4.1 なので秘書カズヨへ差し戻してください。"
                )
            if resp.status_code == 429:
                wait = min(30 * (attempt + 1), 180)
                self.log(f"   {label} 429（トークン上限）→ {wait}秒待機")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                self.log(f"   {label} HTTP {resp.status_code} {resp.text[:150]}")
                time.sleep(min(30 * (attempt + 1), 180))
                continue
            try:
                payload = resp.json()
            except ValueError as e:
                self.log(f"   {label} JSON 解釈失敗: {e}")
                time.sleep(10)
                continue
            self.budget.note(payload, codes)
            if payload.get("error"):
                self.log(f"   {label} API エラー: {payload['error']}")
                return {}
            return payload
        self.log(f"   {label} 5回試して駄目でした。このバッチは飛ばします")
        return {}

    def token_status(self) -> dict:
        payload = self._get("token", {}, "token")
        return payload or {}

    # -- 本体 ----------------------------------------------------------------
    def verify_batch(self, jans: list) -> list:
        """JAN のリスト（最大100件）→ AmazonFacts のリスト。

        Keepa は「見つかった商品」だけを返し、**どの JAN が当たったかを直接は返しません**。
        商品の `eanList` / `upcList` を見て JAN に紐付け直します。
        紐付けられなかった JAN は `found=False` で返す（＝Amazon に同一商品が無い）。
        """
        jans = [j for j in jans if j]
        if not jans:
            return []
        payload = self._get(
            "product",
            {"code": ",".join(jans), "stats": 90},
            f"product(code×{len(jans)})",
            codes=len(jans),
        )
        self.requests_made += 1
        self.codes_sent += len(jans)
        products = payload.get("products") or []
        self.products_returned += len(products)

        # ⚠️ 1つの JAN に **複数の ASIN** がぶら下がることがある（実測: 150件中15件）。
        #    同じ商品が別々に出品されている状態で、片方は死んでいて片方は売れている、が普通です。
        #    最初に見つけた1件を採るのは**ただのくじ引き**なので、全部集めてから選びます。
        by_jan: dict = {}
        for p in products:
            for code in (p.get("eanList") or []) + (p.get("upcList") or []):
                by_jan.setdefault(str(code), []).append(p)

        out = []
        for jan in jans:
            group = by_jan.get(jan) or []
            if not group:
                out.append(AmazonFacts(jan=jan, found=False))
                continue
            facts = _to_facts(jan, _pick_best(group))
            facts.asin_count = len(group)
            out.append(facts)
        return out

    def verify_all(self, jans: list, *, batch_size: int = None, on_batch=None) -> list:
        """全 JAN をバッチに割って検証する。バッチごとに on_batch(results) を呼ぶ（逐次保存用）。"""
        batch_size = batch_size or config.KEEPA_CODE_BATCH
        results = []
        for i in range(0, len(jans), batch_size):
            if not self.budget.wait_if_needed(self.log, batch_size):
                self.log("!! トークン枯渇のため打ち切ります（ここまでの結果は保存済み）")
                break
            chunk = jans[i : i + batch_size]
            before = self.products_returned
            got = self.verify_batch(chunk)
            returned = self.products_returned - before
            results.extend(got)
            if on_batch:
                on_batch(got)
            hit = sum(1 for f in got if f.found)
            self.log(
                f"   [{i + len(chunk)}/{len(jans)}] Keepa {len(chunk)}件 → "
                f"返却{returned}商品・ヒット{hit}件 "
                f"/ 累計{self.budget.consumed_total}トークン "
                f"({self.budget.tokens_per_code:.2f}/件) / 残{self.budget.left}"
            )
        return results

    def verify_sellers(self, asins: list) -> dict:
        """実セラー数（distinct sellerId）を offers 付きで確定する。**6.5トークン/件**。

        `stats.current[COUNT_NEW]` は「オファー本数」で出品者数ではありません
        （1社が FBA と FBM に出すだけで2）。この誤読で過去に候補top100の35%を汚染しています
        （`knowledge_keepa_count_new_is_not_seller_count`）。
        高いので、**利益ラインを超えた行にだけ**掛けてください。
        """
        out: dict = {}
        for i in range(0, len(asins), 20):
            if not self.budget.wait_if_needed(self.log, 20 * 7):
                break
            chunk = asins[i : i + 20]
            payload = self._get(
                "product",
                {"asin": ",".join(chunk), "offers": 20},
                f"product(offers×{len(chunk)})",
            )
            for p in payload.get("products") or []:
                live = set(p.get("liveOffersOrder") or [])
                offers = p.get("offers") or []
                sellers = {
                    o.get("sellerId")
                    for idx, o in enumerate(offers)
                    if o.get("sellerId") and (not live or idx in live)
                }
                out[p.get("asin")] = len(sellers)
        return out


# 入数の読み取りは pipeline/pack.py が唯一の実装。ここには持たない
# （同じ判定を2箇所に置くと、片方だけ直して直したつもりになる）。
from .pack import detect_pack, detect_pack_size  # noqa: E402,F401


def _pick_best(products: list) -> dict:
    """同一 JAN の複数 ASIN から「実際に売れている方」を選ぶ。

    優先順位は **売れているか → 価格が取れるか → ランクが上か**。
    「どれを選んだか」は情報として残す価値があるので、件数を `asin_count` に記録します
    （相乗り先が2つある＝どちらに出すかの判断材料。捨てない）。
    """
    def key(p):
        stats = p.get("stats") or {}
        cur = stats.get("current") or []
        drops = _num(stats.get("salesRankDrops30")) or 0
        has_price = 1 if (len(cur) > IDX_NEW and _num(cur[IDX_NEW]) is not None) else 0
        rank = _num(cur[IDX_SALES_RANK]) if len(cur) > IDX_SALES_RANK else None
        # まとめ売りより単品を好む（在庫リスクが小さく、入数の読み違えも起きない）。
        # ただし「売れているか」を最優先にするのは変えない。
        single = 1 if detect_pack_size(p.get("title") or "") == 1 else 0
        return (drops, has_price, single, -(rank if rank is not None else 10**9))

    return max(products, key=key)


def _num(value):
    """Keepa の -1 / -2 / None は「データ無し」。数値だけ返す。"""
    if isinstance(value, (int, float)) and value >= 0:
        return value
    return None


def _to_facts(jan: str, p: dict) -> AmazonFacts:
    stats = p.get("stats") or {}
    cur = stats.get("current") or []
    avg90 = stats.get("avg90") or []

    def at(seq, idx):
        return _num(seq[idx]) if len(seq) > idx else None

    price = at(cur, IDX_NEW)
    source = "現在の新品最安(送料込)"
    if price is None:
        price = at(avg90, IDX_NEW)
        source = "90日平均の新品最安(現在価格なし)" if price is not None else ""

    dims = tuple(
        d for d in (p.get("packageLength"), p.get("packageWidth"), p.get("packageHeight"))
        if isinstance(d, (int, float)) and d > 0
    )
    weight = p.get("packageWeight")
    title = p.get("title") or ""
    return AmazonFacts(
        jan=jan,
        asin=p.get("asin"),
        title=title,
        brand=p.get("brand") or p.get("manufacturer") or "",
        price_yen=int(price) if price is not None else None,
        price_source=source,
        sales_rank=at(cur, IDX_SALES_RANK),
        drops30=_num(stats.get("salesRankDrops30")),
        drops90=_num(stats.get("salesRankDrops90")),
        offer_count=at(cur, IDX_COUNT_NEW),
        availability_amazon=p.get("availabilityAmazon"),
        category_names=[
            c.get("name", "") for c in (p.get("categoryTree") or []) if isinstance(c, dict)
        ],
        package_mm=dims,
        package_g=int(weight) if isinstance(weight, (int, float)) and weight > 0 else None,
        found=True,
        pack_size=detect_pack_size(title),
    )


def fba_size_key(facts: AmazonFacts) -> tuple:
    """AmazonFacts → (fees.py の size_key, 表示ラベル)。

    寸法も重量も無い商品は "unknown"。**除外はしません**（母数を減らさない。判断は人へ）。
    手数料は standard_2 相当を仮置きして、CSV に「不明」と明記します。
    """
    dims = sorted(facts.package_mm, reverse=True)
    g = facts.package_g
    if len(dims) < 3 and g is None:
        return "unknown", "不明(寸法・重量なし)"
    if len(dims) == 3 and any(d > lim for d, lim in zip(dims, FBA_STD_DIMS_MM)):
        return "large_1", "大型"
    if g is not None and g > FBA_STD_WEIGHT_G:
        return "large_1", "大型"
    if g is None:
        return "unknown", "不明(重量なし)"
    if g <= 250 and (not dims or dims[0] <= 250):
        return "small", "小型"
    if g <= 1000:
        return "standard_1", "標準1"
    if g <= 2000:
        return "standard_2", "標準2"
    return "standard_3", "標準3"
