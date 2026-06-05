"""ディスカバリー・パイプライン（このプロトの心臓部）。

2モードを提供する:
  (い) discover_from_supplier : 仕入れ元起点（電脳せどり）
         Yahoo検索 → 各商品のJAN → Amazon突合 → 利益計算 → 利益降順ランキング
  (あ) discover_from_amazon   : Amazon起点
         Amazon商品を条件フィルタ → 利益計算 → 利益降順ランキング

設計方針（タカシ）:
- 利益計算は必ず calc.profit に委譲する（1円もここで計算しない）。
- アダプタ（yahoo / amazon_data）越しにデータを取り、生APIを直接触らない。
- 突合失敗・データ欠損は「除外＋ログ」。黙って捨てない／でっち上げない。
- 戻り値は表示にもテストにも使える dataclass のリスト（利益降順済み）。
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from adapters.amazon_data import AmazonDataBackend, AmazonProduct, get_backend
from adapters.yahoo_shopping import YahooItem, YahooShoppingClient
from calc import profit
from discovery.presets import DiscoveryPreset, get_finder_preset, get_preset
from discovery.quantity import parse_quantity

logger = logging.getLogger("discovery")


@dataclass
class DiscoveryRow:
    """ランキング1行。UI のテーブル列とほぼ1対1。"""

    name: str                    # 仕入元(Yahoo)側の商品名
    asin: str
    supplier_price: Optional[int]    # 仕入値（円・税込）。Amazon起点で仕入元未特定なら None
    amazon_price: float              # Amazon売値（円・税込）
    net_profit: float                # 純利益（円）
    margin_rate: float               # 利益率（0〜1）
    roi: float                       # ROI（0〜1）
    monthly_sales: Optional[int]
    sales_rank: Optional[int]
    offer_count: Optional[int]
    oos_rate_90d: Optional[float]
    verdict: str                     # 原石/要確認/あやしい/はずれ
    match_status: str                # 突合状態（後述の定数）
    amazon_name: str = ""            # Amazon(Keepa)側の商品名。Yahoo名と別保持（個数照合用）
    supplier_qty: Optional[int] = None   # 仕入元側の推定入数（None=不明）
    amazon_qty: Optional[int] = None     # Amazon側の推定入数（None=不明）
    qty_flag: str = ""               # 数量フラグ（一致/補正/要確認の可視化ラベル）
    qty_reliable: bool = False       # 入数が両側一致して信頼できるか（原石付与の前提）
    supplier_price_raw: Optional[int] = None  # 数量補正前の生の仕入値（監査用）
    supplier_url: str = ""           # 仕入元リンク
    category_label: str = ""
    is_sample: bool = False          # サンプル由来か
    notes: list = field(default_factory=list)


# 突合状態の定数（UI とテストで共有）
MATCH_OK = "突合OK"
MATCH_NO_JAN = "JAN無し(突合不可)"
MATCH_NO_AMAZON = "Amazonに該当無し"
MATCH_NO_PRICE = "Amazon価格取得不可"
AMAZON_ONLY = "Amazon起点(仕入元未特定)"

# 数量フラグの定数（UI とテストで共有）
QTY_MATCH = "数量一致"                  # 両側判明し一致 → 信頼できる
QTY_ADJUSTED = "⚠️数量補正"            # 両側判明し不一致 → per-unitで補正（推定・要確認）
QTY_UNKNOWN = "⚠️数量要確認"           # 片側/両側が入数不明 → 1対1はリスク・要目視

# 数量降格後の判定ラベル（profit.VERDICT_* とは別。数量起因の降格を明示）。
VERDICT_NEEDS_CHECK = "要確認"


# =============================================================================
# (い) 仕入れ元起点 = 電脳せどり
# =============================================================================
# JAN突合で Amazon（Keepa）に問い合わせる JAN の上限。
# KeepaBackend.MAX_JANS_PER_CALL と揃える（トークン節約。残トークンが少ないため重要）。
MAX_JAN_LOOKUPS = 10


def discover_from_supplier(
    query: str = "",
    *,
    preset_key: str = "hunting_beginner",
    amazon_backend: Optional[AmazonDataBackend] = None,
    yahoo_client: Optional[YahooShoppingClient] = None,
    max_items: int = 50,
    max_jan_lookups: int = MAX_JAN_LOOKUPS,
) -> list[DiscoveryRow]:
    """Yahoo!ショッピングで仕入れ候補を探し、Amazon と突合して利益ランキングを返す。

    トークン節約のため、Yahoo 結果のうち **JAN付きの先頭 max_jan_lookups 件のみ**を
    1リクエストにまとめて Amazon（Keepa）へ突合する（resolve_many）。
    突合できなかった候補は結果に含めず、理由を logger に残す（正直に除外）。
    """
    preset = get_preset(preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or YahooShoppingClient()

    items = yahoo.search(query, results=max_items)

    # JAN付きの先頭 N 件だけ Amazon に問い合わせる（トークン上限のハードキャップ）。
    jan_items = [it for it in items if it.jan]
    no_jan = len(items) - len(jan_items)
    if no_jan:
        logger.info("JAN無しで突合不可: %d件（Yahoo出店者がJAN未登録）", no_jan)
    target_items = jan_items[:max_jan_lookups]
    if len(jan_items) > max_jan_lookups:
        logger.info(
            "トークン節約: JAN付き%d件中 先頭%d件のみAmazon突合",
            len(jan_items), max_jan_lookups,
        )

    # 1リクエストでまとめて突合（Keepaならカンマ区切り1コールでトークン節約）。
    jan_to_product = amazon.resolve_many([it.jan for it in target_items])

    rows: list[DiscoveryRow] = []
    for item in target_items:
        ap = jan_to_product.get(item.jan)
        if ap is None:
            logger.info("除外[Amazon該当無し]: %s (JAN=%s)", item.name, item.jan)
            continue
        row = _build_row(item, ap, preset)
        if row is None:
            continue  # 除外理由は _build_row 内でログ済み
        rows.append(row)

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


def _resolve_quantities(
    supplier_price: int, supplier_name: str, amazon_name: str
) -> dict:
    """仕入元名・Amazon名の入数を推定し、安全な突合方針を決める（honesty-first）。

    返り値 dict:
      supplier_qty / amazon_qty : 推定入数（None=不明）
      adjusted_price            : 入数を揃えた実質仕入値（補正不要ならそのまま）
      qty_flag                  : QTY_MATCH / QTY_ADJUSTED / QTY_UNKNOWN
      qty_reliable              : 入数一致で利益が信頼できるか（原石付与の前提）
      extra_notes               : 行に積む補足ノート（推定である旨を明示）

    方針（社長が踏んだ「20個入り vs 1個」バグの恒久対策）:
      - 両方判明 & qy==qa → そのまま（信頼できる）。
      - 両方判明 & qy!=qa → 仕入値を per-unit で Amazon 入数に揃えて再計算し、
        「⚠️数量補正」を立て、原石にしない（推定なので要確認に降格）。
      - 片方/両方が不明 → 1対1はリスク。「⚠️数量要確認」で原石にしない。
    """
    qy = parse_quantity(supplier_name)
    qa = parse_quantity(amazon_name)

    if qy is not None and qa is not None and qy == qa:
        return {
            "supplier_qty": qy, "amazon_qty": qa,
            "adjusted_price": supplier_price,
            "qty_flag": QTY_MATCH, "qty_reliable": True, "extra_notes": [],
        }

    if qy is not None and qa is not None and qy != qa:
        # per-unit で Amazon 入数に揃える: 1個あたり仕入単価 × Amazon入数。
        unit = supplier_price / qy
        adjusted = round(unit * qa)
        note = (
            f"⚠️数量補正(推定): 仕入は{qy}個入り{supplier_price:,}円→"
            f"1個{unit:,.0f}円×Amazon{qa}個={adjusted:,}円で再計算。"
            f"人間確認前提（原石にはしない）"
        )
        return {
            "supplier_qty": qy, "amazon_qty": qa,
            "adjusted_price": adjusted,
            "qty_flag": QTY_ADJUSTED, "qty_reliable": False, "extra_notes": [note],
        }

    # 片方/両方が不明
    note = (
        f"⚠️数量未確定・要目視: 仕入元={'?' if qy is None else qy}個 / "
        f"Amazon={'?' if qa is None else qa}個。"
        f"1対1比較はリスク（多包装ASINに単品が一致する誤突合の恐れ）"
    )
    return {
        "supplier_qty": qy, "amazon_qty": qa,
        "adjusted_price": supplier_price,
        "qty_flag": QTY_UNKNOWN, "qty_reliable": False, "extra_notes": [note],
    }


def _build_row(
    item: YahooItem, ap: AmazonProduct, preset: DiscoveryPreset
) -> Optional[DiscoveryRow]:
    """突合済みの (Yahoo候補, Amazon商品) から利益計算して DiscoveryRow を作る。

    Amazon価格欠損・プリセット条件外は None を返し理由をログに残す。
    入数（Yahoo個数 vs Amazon個数）を照合し、不一致/不明なら原石に昇格させない。
    """
    if ap.current_price is None:
        logger.info("除外[Amazon価格無し]: %s (ASIN=%s)", item.name, ap.asin)
        return None

    # Amazon側メタ（ランキング/出品者数/在庫切れ率）でプリセット条件を軽く効かせる。
    if not _passes_amazon_filters(ap, preset):
        logger.info("除外[Amazon条件外]: %s (ASIN=%s)", item.name, ap.asin)
        return None

    # ── 入数照合（個数ミスマッチによる偽・原石を潰す） ──
    qres = _resolve_quantities(item.price, item.name, ap.title)

    result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=qres["adjusted_price"],  # 数量補正後の実質仕入値（税込扱い）
            amazon_price=ap.current_price,
            category_key=ap.category_key,
            size_key=ap.size_key,
        )
    )

    # 数量が信頼できない行は原石/あやしいに昇格させず「要確認」へ降格（honesty-first）。
    verdict = result.verdict
    if not qres["qty_reliable"] and verdict != profit.VERDICT_MISS:
        verdict = VERDICT_NEEDS_CHECK

    # Keepa 由来の推定ノート（月販推定・FBAサイズ推定）＋数量ノートを正直に引き継ぐ。
    notes = (
        list(result.notes)
        + list(getattr(ap, "estimate_notes", []) or [])
        + qres["extra_notes"]
    )

    return DiscoveryRow(
        name=item.name,
        asin=ap.asin,
        supplier_price=qres["adjusted_price"],
        amazon_price=ap.current_price,
        net_profit=result.net_profit,
        margin_rate=result.margin_rate,
        roi=result.roi,
        monthly_sales=ap.monthly_sales,
        sales_rank=ap.sales_rank,
        offer_count=ap.offer_count,
        oos_rate_90d=ap.oos_rate_90d,
        verdict=verdict,
        match_status=MATCH_OK,
        amazon_name=ap.title,
        supplier_qty=qres["supplier_qty"],
        amazon_qty=qres["amazon_qty"],
        qty_flag=qres["qty_flag"],
        qty_reliable=qres["qty_reliable"],
        supplier_price_raw=item.price,
        supplier_url=item.url,
        category_label=result.category_label,
        is_sample=item.is_sample or ap.is_sample,
        notes=notes,
    )


# =============================================================================
# (あ) Amazon起点ディスカバリー
# =============================================================================
def discover_from_amazon(
    *,
    preset_key: str = "hunting_beginner",
    amazon_backend: Optional[AmazonDataBackend] = None,
    assumed_cost_rate: float = 0.5,
    use_assumed_cost: bool = False,
    yahoo_client: Optional[YahooShoppingClient] = None,
    max_items: int = 50,
    category_id: Optional[int] = None,
    max_asins: int = 10,
) -> list[DiscoveryRow]:
    """Amazon側を条件フィルタ→利益計算→ランキング（キーワード不要の売れ筋探索）。

    仕入れ値は本来「仕入元を探して初めて」確定する。Amazon起点モードでは
    まず Yahoo に JAN で当てて実仕入値を試み、見つかればそれで利益計算する。
    見つからない場合の方針:
      - use_assumed_cost=False（本番・既定）: 仮の利益をでっち上げず「候補保留」にする。
      - use_assumed_cost=True（学習/デモ）  : assumed_cost_rate で仮置き（要確認に降格）。

    category_id を渡すと Keepa Best Sellers から売れ筋 ASIN を集める（list_products 経由）。
    トークン節約のため詳細取得 ASIN は max_asins 件にハードキャップ。
    """
    preset = get_preset(preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or YahooShoppingClient()

    list_kwargs = {}
    if category_id is not None:
        list_kwargs["category_id"] = category_id
    list_kwargs["limit"] = max_asins
    products = amazon.list_products(**list_kwargs)
    rows: list[DiscoveryRow] = []

    for ap in products:
        if ap.current_price is None:
            logger.info("除外[Amazon価格無し]: %s", ap.title)
            continue
        if not _passes_amazon_filters(ap, preset):
            logger.info("除外[Amazon条件外]: %s (rank=%s)", ap.title, ap.sales_rank)
            continue

        row = _build_amazon_row(ap, yahoo, assumed_cost_rate, use_assumed_cost)
        if row is not None:
            rows.append(row)

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


# =============================================================================
# (あ) 原石オートサーチ = Keepa Product Finder（キーワード不要・条件抽出）
# =============================================================================
def discover_by_finder(
    *,
    finder_preset_key: str = "finder_genseki_beginner",
    category_ids: Optional[list[int]] = None,
    amazon_backend: Optional[AmazonDataBackend] = None,
    yahoo_client: Optional[YahooShoppingClient] = None,
    use_assumed_cost: bool = False,
    assumed_cost_rate: float = 0.5,
    max_asins: int = 15,
) -> list[DiscoveryRow]:
    """Keepa Product Finder で原石ASIN群を抽出→Yahoo突合→利益ランキング（キーワード不要）。

    Best Sellers（売れ筋トップ＝赤字）ではなく、Finder の条件抽出で
    「中位ランク × 競合薄 × 手頃価格」のニッチ原石を数千商品から自動で絞り込む。
    抽出した各ASINを JAN で Yahoo に当てて実仕入値を取り、個数安全判定を通して利益化する。

    トークン節約: Finder 1コール＋詳細最大 max_asins(≤15) 件の product 1バッチのみ。
    仕入元未発見/赤字は **でっち上げず正直に保留/除外**（_build_amazon_row と同じ honesty）。
    """
    fpreset = get_finder_preset(finder_preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or YahooShoppingClient()

    # find_products を持つバックエンド（Keepa）でのみ Finder 探索。サンプル等は list_products へ。
    if hasattr(amazon, "find_products"):
        selection = fpreset.to_selection(category_ids or [])
        logger.info("Product Finder selection=%s（詳細上限%d件）", selection, max_asins)
        products = amazon.find_products(selection, limit=max_asins)
    else:
        logger.info("find_products 非対応バックエンド→list_productsにフォールバック")
        products = amazon.list_products(limit=max_asins)

    # 利益フィルタは Finder プリセットを DiscoveryPreset に写像して再利用。
    preset = fpreset.as_discovery_preset()

    rows: list[DiscoveryRow] = []
    for ap in products:
        if ap.current_price is None:
            logger.info("除外[Amazon価格無し]: %s", ap.title)
            continue
        # Finder 側で既にランク/出品者数/価格を絞っているが、念のため軽く再確認。
        if not _passes_amazon_filters(ap, preset):
            logger.info("除外[Amazon条件外]: %s (rank=%s)", ap.title, ap.sales_rank)
            continue
        row = _build_amazon_row(ap, yahoo, assumed_cost_rate, use_assumed_cost)
        if row is not None:
            rows.append(row)

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


def _build_amazon_row(
    ap: AmazonProduct,
    yahoo: YahooShoppingClient,
    assumed_cost_rate: float,
    use_assumed: bool,
) -> Optional[DiscoveryRow]:
    """(あ)Amazon起点の1商品から DiscoveryRow を作る。

    仕入元を JAN で当てに行き、実仕入値が取れたら個数照合のうえ利益計算する。
    仕入元が取れない場合:
      - use_assumed=True  : 想定原価率で仮置き（学習/デモ用。要確認に降格）
      - use_assumed=False : 仕入値をでっち上げず None で保留（本番の正直モード）
    """
    supplier_name = ""
    supplier_price: Optional[int] = None
    supplier_url = ""
    match_status = AMAZON_ONLY
    if ap.jan:
        for it in yahoo.search(jan_code=ap.jan, results=5):
            if it.jan == ap.jan:
                supplier_price = it.price
                supplier_name = it.name
                supplier_url = it.url
                match_status = MATCH_OK
                break

    # 実仕入値が取れた → 個数照合つきで利益計算（(い)と同じ honesty ロジック）。
    if supplier_price is not None:
        qres = _resolve_quantities(supplier_price, supplier_name, ap.title)
        result = profit.calculate(
            profit.ProfitInput(
                wholesale_price=qres["adjusted_price"],
                amazon_price=ap.current_price,
                category_key=ap.category_key,
                size_key=ap.size_key,
            )
        )
        verdict = result.verdict
        if not qres["qty_reliable"] and verdict != profit.VERDICT_MISS:
            verdict = VERDICT_NEEDS_CHECK
        notes = (
            list(result.notes)
            + list(getattr(ap, "estimate_notes", []) or [])
            + qres["extra_notes"]
        )
        return DiscoveryRow(
            name=supplier_name or ap.title,
            asin=ap.asin,
            supplier_price=qres["adjusted_price"],
            amazon_price=ap.current_price,
            net_profit=result.net_profit,
            margin_rate=result.margin_rate,
            roi=result.roi,
            monthly_sales=ap.monthly_sales,
            sales_rank=ap.sales_rank,
            offer_count=ap.offer_count,
            oos_rate_90d=ap.oos_rate_90d,
            verdict=verdict,
            match_status=match_status,
            amazon_name=ap.title,
            supplier_qty=qres["supplier_qty"],
            amazon_qty=qres["amazon_qty"],
            qty_flag=qres["qty_flag"],
            qty_reliable=qres["qty_reliable"],
            supplier_price_raw=supplier_price,
            supplier_url=supplier_url,
            category_label=result.category_label,
            is_sample=ap.is_sample,
            notes=notes,
        )

    # 仕入元が見つからない。本番の正直モードでは仮の利益を出さず保留（行は出すが利益なし）。
    if not use_assumed:
        return DiscoveryRow(
            name=ap.title,
            asin=ap.asin,
            supplier_price=None,
            amazon_price=ap.current_price,
            net_profit=0.0,
            margin_rate=0.0,
            roi=0.0,
            monthly_sales=ap.monthly_sales,
            sales_rank=ap.sales_rank,
            offer_count=ap.offer_count,
            oos_rate_90d=ap.oos_rate_90d,
            verdict=VERDICT_NEEDS_CHECK,
            match_status=AMAZON_ONLY,
            amazon_name=ap.title,
            qty_flag=QTY_UNKNOWN,
            qty_reliable=False,
            supplier_url="",
            category_label="",
            is_sample=ap.is_sample,
            notes=list(getattr(ap, "estimate_notes", []) or [])
            + ["仕入元未発見：実仕入値が無いため利益は算出していません（候補保留・要リサーチ）"],
        )

    # 学習/デモ用フォールバック: 想定原価率で仮置き（要確認に降格・明示ノート）。
    supplier_price = round(ap.current_price * assumed_cost_rate)
    result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=supplier_price,
            amazon_price=ap.current_price,
            category_key=ap.category_key,
            size_key=ap.size_key,
        )
    )
    verdict = (
        VERDICT_NEEDS_CHECK
        if result.verdict != profit.VERDICT_MISS
        else result.verdict
    )
    return DiscoveryRow(
        name=ap.title,
        asin=ap.asin,
        supplier_price=supplier_price,
        amazon_price=ap.current_price,
        net_profit=result.net_profit,
        margin_rate=result.margin_rate,
        roi=result.roi,
        monthly_sales=ap.monthly_sales,
        sales_rank=ap.sales_rank,
        offer_count=ap.offer_count,
        oos_rate_90d=ap.oos_rate_90d,
        verdict=verdict,
        match_status=AMAZON_ONLY,
        amazon_name=ap.title,
        qty_flag=QTY_UNKNOWN,
        qty_reliable=False,
        supplier_url="",
        category_label=result.category_label,
        is_sample=ap.is_sample,
        notes=list(result.notes)
        + [f"仕入値は想定原価率{assumed_cost_rate*100:.0f}%での仮置き（実仕入値ではない・要確認）"],
    )


# =============================================================================
# 共通フィルタ
# =============================================================================
def _passes_amazon_filters(ap: AmazonProduct, preset: DiscoveryPreset) -> bool:
    """Amazon側メタ（ランキング/月販/出品者数/在庫切れ率）でプリセット条件を判定。"""
    if ap.sales_rank is not None and ap.sales_rank > preset.max_sales_rank:
        return False
    if ap.monthly_sales is not None and ap.monthly_sales < preset.min_monthly_sales:
        return False
    if ap.offer_count is not None and ap.offer_count > preset.max_offer_count:
        return False
    if preset.min_oos_rate_90d > 0:
        if ap.oos_rate_90d is None or ap.oos_rate_90d < preset.min_oos_rate_90d:
            return False
    return True


def _apply_profit_filters(
    rows: list[DiscoveryRow], preset: DiscoveryPreset
) -> list[DiscoveryRow]:
    """利益計算後の閾値（利益率/純利益）でフィルタ。

    ただし数量が信頼できない行（補正/要確認）は **黙って捨てない**。閾値を満たさなくても
    「⚠️数量要確認」として残し、社長が目視照合できるようにする（honesty-first）。
    黒字（純利益>0）であることだけは最低条件として課す（赤字は表示価値が薄い）。
    """
    out = []
    for r in rows:
        passes_threshold = (
            r.margin_rate >= preset.min_margin_rate
            and r.net_profit >= preset.min_net_profit
        )
        if passes_threshold:
            out.append(r)
        elif not r.qty_reliable and r.net_profit > 0:
            # 数量補正/不明の黒字行は、閾値未達でも「要確認」として残す。
            out.append(r)
        elif r.supplier_price is None and r.match_status == AMAZON_ONLY:
            # 仕入元未発見の「候補保留」行（利益0）は黙って捨てず残す（honesty-first）。
            # Amazon起点/Finderで原石候補として社長がリサーチできるようにする。
            out.append(r)
    return out


# =============================================================================
# 直接実行: サンプルでパイプラインのデモ（python -m discovery.pipeline）
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="  [log] %(message)s")
    from adapters.amazon_data import SampleBackend
    az = SampleBackend()
    yh = YahooShoppingClient(force_sample=True)
    print("=" * 70)
    print("(い) 仕入れ元起点ディスカバリー  preset=hunting_beginner  ※サンプルデータ")
    print("=" * 70)
    for i, r in enumerate(
        discover_from_supplier("", preset_key="hunting_beginner",
                               amazon_backend=az, yahoo_client=yh), 1
    ):
        print(
            f"{i}. {r.name[:28]:28} 仕入{r.supplier_price:>5}円 "
            f"→Amazon{int(r.amazon_price):>5}円 純利益{int(r.net_profit):>5}円 "
            f"({r.margin_rate*100:4.1f}%) [{r.verdict}]"
        )
