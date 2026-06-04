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
from discovery.presets import DiscoveryPreset, get_preset

logger = logging.getLogger("discovery")


@dataclass
class DiscoveryRow:
    """ランキング1行。UI のテーブル列とほぼ1対1。"""

    name: str                    # 商品名（仕入元 or Amazon の名前）
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
    verdict: str                     # 原石/あやしい/はずれ
    match_status: str                # 突合状態（後述の定数）
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


# =============================================================================
# (い) 仕入れ元起点 = 電脳せどり
# =============================================================================
def discover_from_supplier(
    query: str = "",
    *,
    preset_key: str = "beginner_safe",
    amazon_backend: Optional[AmazonDataBackend] = None,
    yahoo_client: Optional[YahooShoppingClient] = None,
    max_items: int = 50,
) -> list[DiscoveryRow]:
    """Yahoo!ショッピングで仕入れ候補を探し、Amazon と突合して利益ランキングを返す。

    突合できなかった候補は結果に含めず、理由を logger に残す（正直に除外）。
    """
    preset = get_preset(preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or YahooShoppingClient()

    items = yahoo.search(query, results=max_items)
    rows: list[DiscoveryRow] = []

    for item in items:
        row = _match_and_calc(item, amazon, preset)
        if row is None:
            continue  # 除外理由は _match_and_calc 内でログ済み
        rows.append(row)

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


def _match_and_calc(
    item: YahooItem, amazon: AmazonDataBackend, preset: DiscoveryPreset
) -> Optional[DiscoveryRow]:
    """1つの仕入れ候補を Amazon と突合し、利益計算して DiscoveryRow にする。

    突合できなければ None を返し、理由をログに残す。
    """
    if not item.jan:
        logger.info("除外[JAN無し]: %s", item.name)
        return None

    ap: Optional[AmazonProduct] = amazon.resolve_by_jan(item.jan)
    if ap is None:
        logger.info("除外[Amazon該当無し]: %s (JAN=%s)", item.name, item.jan)
        return None
    if ap.current_price is None:
        logger.info("除外[Amazon価格無し]: %s (ASIN=%s)", item.name, ap.asin)
        return None

    # Amazon起点フィルタ（ランキング/出品者数/在庫切れ率）はここでも軽く効かせる。
    if not _passes_amazon_filters(ap, preset):
        logger.info("除外[Amazon条件外]: %s (ASIN=%s)", item.name, ap.asin)
        return None

    result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=item.price,          # Yahoo価格は税込として扱う
            amazon_price=ap.current_price,
            category_key=ap.category_key,
            size_key=ap.size_key,
        )
    )

    return DiscoveryRow(
        name=item.name,
        asin=ap.asin,
        supplier_price=item.price,
        amazon_price=ap.current_price,
        net_profit=result.net_profit,
        margin_rate=result.margin_rate,
        roi=result.roi,
        monthly_sales=ap.monthly_sales,
        sales_rank=ap.sales_rank,
        offer_count=ap.offer_count,
        oos_rate_90d=ap.oos_rate_90d,
        verdict=result.verdict,
        match_status=MATCH_OK,
        supplier_url=item.url,
        category_label=result.category_label,
        is_sample=item.is_sample or ap.is_sample,
        notes=result.notes,
    )


# =============================================================================
# (あ) Amazon起点ディスカバリー
# =============================================================================
def discover_from_amazon(
    *,
    preset_key: str = "beginner_safe",
    amazon_backend: Optional[AmazonDataBackend] = None,
    assumed_cost_rate: float = 0.5,
    yahoo_client: Optional[YahooShoppingClient] = None,
    max_items: int = 50,
) -> list[DiscoveryRow]:
    """Amazon側を条件フィルタ→利益計算→ランキング。

    仕入れ値は本来「仕入元を探して初めて」確定する。Amazon起点モードでは
    まず Yahoo に JAN で当てて実仕入値を試み、見つからなければ
    `assumed_cost_rate`（Amazon売値に対する想定原価率）で仮置きする。
    仮置きの場合 match_status=AMAZON_ONLY とし、UI/READMEで「想定値」と明示する。
    """
    preset = get_preset(preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or YahooShoppingClient()

    products = amazon.list_products()
    rows: list[DiscoveryRow] = []

    for ap in products:
        if ap.current_price is None:
            logger.info("除外[Amazon価格無し]: %s", ap.title)
            continue
        if not _passes_amazon_filters(ap, preset):
            logger.info("除外[Amazon条件外]: %s (rank=%s)", ap.title, ap.sales_rank)
            continue

        # 仕入元を JAN で当てに行く（実仕入値が取れればそれを使う）。
        supplier_price: Optional[int] = None
        supplier_url = ""
        match_status = AMAZON_ONLY
        if ap.jan:
            for it in yahoo.search(jan_code=ap.jan, results=5):
                if it.jan == ap.jan:
                    supplier_price = it.price
                    supplier_url = it.url
                    match_status = MATCH_OK
                    break

        if supplier_price is None:
            supplier_price = round(ap.current_price * assumed_cost_rate)

        result = profit.calculate(
            profit.ProfitInput(
                wholesale_price=supplier_price,
                amazon_price=ap.current_price,
                category_key=ap.category_key,
                size_key=ap.size_key,
            )
        )

        rows.append(
            DiscoveryRow(
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
                verdict=result.verdict,
                match_status=match_status,
                supplier_url=supplier_url,
                category_label=result.category_label,
                is_sample=ap.is_sample,
                notes=result.notes
                + (
                    []
                    if match_status == MATCH_OK
                    else [f"仕入値は想定原価率{assumed_cost_rate*100:.0f}%での仮置き"]
                ),
            )
        )

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


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
    """利益計算後の閾値（利益率/純利益）でフィルタ。"""
    return [
        r
        for r in rows
        if r.margin_rate >= preset.min_margin_rate
        and r.net_profit >= preset.min_net_profit
    ]


# =============================================================================
# 直接実行: サンプルでパイプラインのデモ（python -m discovery.pipeline）
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="  [log] %(message)s")
    from adapters.amazon_data import SampleBackend
    az = SampleBackend()
    yh = YahooShoppingClient(force_sample=True)
    print("=" * 70)
    print("(い) 仕入れ元起点ディスカバリー  preset=beginner_safe  ※サンプルデータ")
    print("=" * 70)
    for i, r in enumerate(
        discover_from_supplier("", preset_key="beginner_safe",
                               amazon_backend=az, yahoo_client=yh), 1
    ):
        print(
            f"{i}. {r.name[:28]:28} 仕入{r.supplier_price:>5}円 "
            f"→Amazon{int(r.amazon_price):>5}円 純利益{int(r.net_profit):>5}円 "
            f"({r.margin_rate*100:4.1f}%) [{r.verdict}]"
        )
