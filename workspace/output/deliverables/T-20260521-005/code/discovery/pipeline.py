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
from adapters.multi_supplier import MultiSupplierClient
from adapters.netsea import NetseaClient
from adapters.rakuten_shopping import RakutenShoppingClient
from adapters.yahoo_shopping import YahooItem, YahooShoppingClient
from calc import profit
from discovery import name_match
from discovery.presets import DiscoveryPreset, get_finder_preset, get_preset
from discovery.quantity import parse_quantity

logger = logging.getLogger("discovery")


def default_supplier_client() -> MultiSupplierClient:
    """既定の仕入元クライアント＝Yahoo + 楽天 + NETSEA(卸) の3本を束ねた合成クライアント。

    各クライアントはキー/トークン未設定なら自前でサンプルへフォールバックするため、
    一部だけ本番でも安全に動く。仕入元が増えるほど JAN突合の母数が広がり、
    特に NETSEA は卸なので同JANで最安の仕入値になりやすく黒字判定が増える。
    """
    return MultiSupplierClient(
        [YahooShoppingClient(), RakutenShoppingClient(), NetseaClient()]
    )


def default_netsea_client() -> NetseaClient:
    """卸起点（う）専用の NETSEA クライアント。棚卸しAPI（list_suppliers / list_supplier_items）

    を使うため、合成クライアントではなく素の NetseaClient を返す（トークン未設定なら
    自前でサンプルへフォールバックする）。
    """
    return NetseaClient()


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
    maker: str = ""                  # メーカー/ブランド名（Keepa raw の brand>manufacturer）。メーカー仕入れ抽出用
    supplier_qty: Optional[int] = None   # 仕入元側の推定入数（None=不明）
    amazon_qty: Optional[int] = None     # Amazon側の推定入数（None=不明）
    qty_flag: str = ""               # 数量フラグ（一致/補正/要確認の可視化ラベル）
    qty_reliable: bool = False       # 入数が両側一致して信頼できるか（原石付与の前提）
    match_confidence: str = ""       # 突合信頼度（高/中/低）。原石は「高」のみ昇格可
    match_confidence_reason: str = ""  # 信頼度の根拠（監査/ログ用）
    supplier_price_raw: Optional[int] = None  # 数量補正前の生の仕入値（監査用）
    supplier_url: str = ""           # 仕入元リンク
    supplier_source: str = ""        # 仕入元名（"Yahoo"/"楽天"）。複数仕入れ先の可視化用
    category_label: str = ""
    is_sample: bool = False          # サンプル由来か
    # Amazon側の過去売値推移（円・古い→新しい）。最悪相場シミュレーション/折れ線表示に使う。
    price_history: Optional[list] = None
    # fees 計算に使うキー（最悪相場シミュレーションで profit を再計算する際に必要）。
    category_key: str = "default"
    size_key: str = "standard_1"
    notes: list = field(default_factory=list)


# 突合状態の定数（UI とテストで共有）
MATCH_OK = "突合OK"
MATCH_NO_JAN = "JAN無し(突合不可)"
MATCH_NO_AMAZON = "Amazonに該当無し"
MATCH_NO_PRICE = "Amazon価格取得不可"
AMAZON_ONLY = "Amazon起点(仕入元未特定)"
# 仕入元名とAmazon名がかけ離れている＝JANは一致するが別商品の疑い（JAN誤登録）。
# この行は利益数値を出さず、原石/利益ランキングから除外して別セクションに隔離する。
MATCH_SUSPECT_MISMATCH = "別商品の疑い(JAN誤登録)"

# 数量フラグの定数（UI とテストで共有）
QTY_MATCH = "数量一致"                  # 両側判明し一致 → 信頼できる
QTY_BOTH_SINGLE = "単品同士(推定)"      # 両側とも入数表記なし → 1個vs1個とみなす（信頼可・但し推定）
QTY_ADJUSTED = "数量補正"              # 両側判明し不一致 → per-unitで補正（推定・要確認）
QTY_UNKNOWN = "数量要確認"             # 片側のみ入数不明 → 1対1はリスク・要目視

# 数量フラグのうち「原石にしない（要・個数目視）」警告フラグの集合。
# UIの行ハイライト判定で使う（絵文字に依存しない明示的な集合判定）。
QTY_WARN_FLAGS = {QTY_ADJUSTED, QTY_UNKNOWN}

# 数量降格後の判定ラベル（profit.VERDICT_* とは別。数量起因の降格を明示）。
VERDICT_NEEDS_CHECK = "要確認"

# Amazon側メタ条件（ランク/出品者数/在庫切れ率）を満たさない行に立てるフラグ。
# 行自体は捨てず、verdict を「要確認」へ降格して全件表示する（捨てない設計）。
AMAZON_FILTER_FAIL = "Amazon条件外"


# =============================================================================
# (い) 仕入れ元起点 = 電脳せどり
# =============================================================================
# JAN突合で Amazon（Keepa）に問い合わせる JAN の上限。
# KeepaBackend.MAX_JANS_PER_CALL と揃える（トークン節約。残トークンが少ないため重要）。
MAX_JAN_LOOKUPS = 10


def _cheapest_per_jan(items: list[YahooItem]) -> list[YahooItem]:
    """同一JANが複数仕入元（Yahoo/楽天）から出たとき、最安の有効1件に集約する。

    最安採用＝同JANで一番安い仕入元を採る（item.source にどの仕入元かは保持済み）。
    入力順（＝検索の関連度順）を壊さないよう、各JANの初出位置を保って並べ直す。
    """
    best: dict[str, YahooItem] = {}
    order: list[str] = []
    for it in items:
        if not it.jan or it.price <= 0:
            continue
        cur = best.get(it.jan)
        if cur is None:
            best[it.jan] = it
            order.append(it.jan)
        elif it.price < cur.price:
            best[it.jan] = it  # より安い仕入元で置き換え（最安採用）
    return [best[j] for j in order]


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
    yahoo = yahoo_client or default_supplier_client()

    items = yahoo.search(query, results=max_items)

    # JAN付きだけを残す。仕入元が複数（Yahoo+楽天）だと同じJANが複数仕入元から出るため、
    # **JANごとに最安の有効仕入値1件に集約**する（最安採用＋Keepaトークンの重複問い合わせ防止）。
    jan_items_all = [it for it in items if it.jan]
    no_jan = len(items) - len(jan_items_all)
    if no_jan:
        logger.info("JAN無しで突合不可: %d件（出店者がJAN未登録）", no_jan)
    jan_items = _cheapest_per_jan(jan_items_all)
    dedup = len(jan_items_all) - len(jan_items)
    if dedup:
        logger.info("同JANを最安仕入元に集約: %d件を圧縮（複数仕入元の最安採用）", dedup)
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
        「数量補正」を立て、原石にしない（推定なので要確認に降格）。
      - 片方/両方が不明 → 1対1はリスク。「数量要確認」で原石にしない。
    """
    qy = parse_quantity(supplier_name)
    qa = parse_quantity(amazon_name)

    if qy is not None and qa is not None and qy == qa:
        return {
            "supplier_qty": qy, "amazon_qty": qa,
            "adjusted_price": supplier_price,
            "qty_flag": QTY_MATCH, "qty_reliable": True, "extra_notes": [],
        }

    # 両側とも入数表記なし＝通常の単品（1個 vs 1個）と解釈する。これが最も多いケースで、
    # ここを一律「要確認」に落とすと単品の原石が永遠に出ない（社長フィードバックの主因）。
    # 多包装の誤突合リスクは「片側だけ N個入りを名乗る」場合に限られるため、そちらだけ降格する。
    if qy is None and qa is None:
        # 両側とも入数不明＝単品同士とみなす（信頼可）。ただし「数量一致」とは表示しない。
        # 入数を確認したわけではないため、専用ラベル QTY_BOTH_SINGLE で正直に区別する
        # （社長報告: 入数?/?なのに「数量一致」と出るのは矛盾、の恒久対策 2026-06-06）。
        return {
            "supplier_qty": None, "amazon_qty": None,
            "adjusted_price": supplier_price,
            "qty_flag": QTY_BOTH_SINGLE, "qty_reliable": True,
            "extra_notes": [
                "入数表記なし＝単品(1個)同士とみなして算定。"
                "多包装の可能性が気になる場合は商品ページで内容量をご確認ください"
            ],
        }

    if qy is not None and qa is not None and qy != qa:
        # per-unit で Amazon 入数に揃える: 1個あたり仕入単価 × Amazon入数。
        unit = supplier_price / qy
        adjusted = round(unit * qa)
        note = (
            f"数量補正(推定): 仕入は{qy}個入り{supplier_price:,}円→"
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
        f"数量未確定・要目視: 仕入元={'?' if qy is None else qy}個 / "
        f"Amazon={'?' if qa is None else qa}個。"
        f"1対1比較はリスク（多包装ASINに単品が一致する誤突合の恐れ）"
    )
    return {
        "supplier_qty": qy, "amazon_qty": qa,
        "adjusted_price": supplier_price,
        "qty_flag": QTY_UNKNOWN, "qty_reliable": False, "extra_notes": [note],
    }


def _suspect_row(
    item: YahooItem, ap: AmazonProduct, conf: Optional[dict] = None
) -> DiscoveryRow:
    """別商品の疑い行を作る。利益数値は一切出さない（誤誘導防止）。

    仕入元名とAmazon名がかけ離れている／数値属性が矛盾するため、原石/利益ランキングには
    載せず、UIの「別商品の疑い」セクションへ隔離する。両名を並べて目視確認を促す。
    conf には match_confidence の結果（信頼度=低）を渡す。矛盾理由をノートに明示する。
    """
    conflict = (conf or {}).get("conflict", "")
    reason = (conf or {}).get("reason", "")
    head = (
        f"JAN一致だが数値属性が矛盾します（{conflict}）。"
        if conflict
        else "JAN一致だが仕入元名とAmazon名がかけ離れています。"
    )
    return DiscoveryRow(
        name=item.name,
        asin=ap.asin,
        supplier_price=item.price,           # 仕入元の生価格は参考表示（利益計算はしない）
        amazon_price=ap.current_price or 0.0,
        net_profit=0.0,
        margin_rate=0.0,
        roi=0.0,
        monthly_sales=ap.monthly_sales,
        sales_rank=ap.sales_rank,
        offer_count=ap.offer_count,
        oos_rate_90d=ap.oos_rate_90d,
        verdict=VERDICT_NEEDS_CHECK,
        match_status=MATCH_SUSPECT_MISMATCH,
        amazon_name=ap.title,
        maker=ap.maker,
        qty_flag="",
        qty_reliable=False,
        match_confidence=name_match.CONFIDENCE_LOW,
        match_confidence_reason=reason,
        supplier_price_raw=item.price,
        supplier_url=item.url,
        supplier_source=getattr(item, "source", ""),
        category_label="",
        is_sample=item.is_sample or ap.is_sample,
        notes=[
            head
            + "出店者のJAN誤登録（使い回し）または別規格の疑いがあるため、利益は算出していません。"
            "両リンクから現物を見比べ、同一商品か必ずご確認ください。"
        ],
    )


def _build_row(
    item: YahooItem, ap: AmazonProduct, preset: DiscoveryPreset
) -> Optional[DiscoveryRow]:
    """突合済みの (Yahoo候補, Amazon商品) から利益計算して DiscoveryRow を作る。

    Amazon価格が無い行だけは None（利益計算不能）。それ以外は **捨てずに必ず行を返す**。
    プリセットのメタ条件（ランク/出品者数/在庫切れ率）を満たさない行は、行を消さずに
    verdict を「要確認」へ降格し notes に理由を残す（社長フィードバック＝0件化をやめる）。
    入数（Yahoo個数 vs Amazon個数）を照合し、不一致/不明なら原石に昇格させない。
    """
    if ap.current_price is None:
        logger.info("除外[Amazon価格無し]: %s (ASIN=%s)", item.name, ap.asin)
        return None

    # ── 突合信頼度の多シグナル判定（JAN誤登録ガード＋数値属性矛盾ガード） ──
    # JANは一致していても、仕入元名とAmazon名がかけ離れている／容量・サイズが矛盾する
    # （例 500ml vs 1000ml、5本 vs 1本）場合は別商品の疑い。利益数値を出さず隔離する。
    # 社長＝正確性最優先のため、信頼度「低」（共通点が乏しい or 数値属性矛盾）は隔離する。
    conf = name_match.match_confidence(item.name, ap.title)
    if conf["level"] == name_match.CONFIDENCE_LOW:
        logger.info(
            "別商品の疑い[信頼度低]: 仕入元=%s ⇔ Amazon=%s (JAN=%s, %s)",
            item.name, ap.title, item.jan, conf["reason"],
        )
        return _suspect_row(item, ap, conf)

    # Amazon側メタ（ランキング/出品者数/在庫切れ率）の判定。満たさなくても行は残す。
    amazon_meta_ok = _passes_amazon_filters(ap, preset)
    if not amazon_meta_ok:
        logger.info("要確認[Amazon条件外・非除外]: %s (ASIN=%s)", item.name, ap.asin)

    # ── 入数照合（個数ミスマッチによる偽・原石を潰す） ──
    qres = _resolve_quantities(item.price, item.name, ap.title)

    result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=qres["adjusted_price"],  # 数量補正後の実質仕入値（税込扱い）
            amazon_price=ap.current_price,
            category_key=ap.category_key,
            size_key=ap.size_key,
            # 原石判定の閾値は preset の実値を渡す（profit.py のデフォ15%/500で上書きされ
            # preset緩和8%/300が効かなくなる不具合を解消）。表示の判定とプリセットが一致する。
            threshold_margin_rate=preset.min_margin_rate,
            threshold_net_profit_yen=preset.min_net_profit,
        )
    )

    # 数量が信頼できない行は原石/あやしいに昇格させず「要確認」へ降格（honesty-first）。
    verdict = result.verdict
    if not qres["qty_reliable"] and verdict != profit.VERDICT_MISS:
        verdict = VERDICT_NEEDS_CHECK
    # Amazonメタ条件外の行も原石にはしない（要確認へ降格）。ただし行は捨てない。
    if not amazon_meta_ok and verdict != profit.VERDICT_MISS:
        verdict = VERDICT_NEEDS_CHECK
    # 突合信頼度が「高」未満（＝中）の行は原石にしない（要確認へ降格）。
    # 社長＝正確性最優先：型番/ブランド未確認の弱い突合を原石として誤提示しない。
    if conf["level"] != name_match.CONFIDENCE_HIGH and verdict != profit.VERDICT_MISS:
        verdict = VERDICT_NEEDS_CHECK

    # Keepa 由来の推定ノート（月販推定・FBAサイズ推定）＋数量ノートを正直に引き継ぐ。
    notes = (
        list(result.notes)
        + list(getattr(ap, "estimate_notes", []) or [])
        + qres["extra_notes"]
    )
    if conf["level"] == name_match.CONFIDENCE_MID:
        notes = notes + [
            f"突合信頼度=中（{conf['reason']}）：仕入元名とAmazon名の一致が弱いため"
            "原石にはせず要確認。両リンクで同一商品か目視確認してください"
        ]
    if not amazon_meta_ok:
        notes = notes + [
            "Amazon条件外（ランク/出品者数/在庫切れ率がプリセット基準を外れる）："
            "原石にはせず参考表示。社長が目視で売れ行き・競合を確認してください"
        ]

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
        match_status=MATCH_OK if amazon_meta_ok else AMAZON_FILTER_FAIL,
        amazon_name=ap.title,
        maker=ap.maker,
        supplier_qty=qres["supplier_qty"],
        amazon_qty=qres["amazon_qty"],
        qty_flag=qres["qty_flag"],
        qty_reliable=qres["qty_reliable"],
        match_confidence=conf["level"],
        match_confidence_reason=conf["reason"],
        supplier_price_raw=item.price,
        supplier_url=item.url,
        supplier_source=getattr(item, "source", ""),
        category_label=result.category_label,
        is_sample=item.is_sample or ap.is_sample,
        price_history=getattr(ap, "price_history", None),
        category_key=ap.category_key,
        size_key=ap.size_key,
        notes=notes,
    )


# =============================================================================
# (う) 卸起点の自動原石探索 = NETSEA承認サプライヤーの棚卸し → Amazon突合
# =============================================================================
@dataclass
class NetseaCoverage:
    """卸起点探索の網羅状況（サイレント打ち切り禁止＝正直にどこまで見たかを返す）。"""

    total_suppliers: int = 0        # 承認サプライヤー総数（GET /suppliers）
    scanned_suppliers: int = 0      # 今回棚卸しした社数（上限 max_suppliers まで）
    fetched_items: int = 0          # 棚卸しで取得した商品数（全社合計・上限後）
    jan_items: int = 0              # うちJAN付きで突合対象になった件数（重複排除後）
    matched_jans: int = 0           # Amazon（Keepa）に当たったJAN件数
    keepa_lookups: int = 0          # Keepaへ問い合わせたJAN件数（≒消費トークンの主因）
    keepa_tokens_consumed: Optional[int] = None  # Keepa消費トークン（取得できた時のみ）
    keepa_tokens_left: Optional[int] = None      # Keepa残トークン（取得できた時のみ）
    remaining_suppliers: int = 0    # 未処理の社数（上限で見送った分）
    remaining_items_estimate: int = 0  # 上限で打ち切った商品の積み残し（判明分の合計）
    truncated: bool = False         # いずれかの上限に当たって打ち切ったか
    notes: list = field(default_factory=list)  # 4xx/429等の正直なエラーログ

    def summary_line(self) -> str:
        """UI/ログ用の1行サマリ（正直版）。"""
        tok = (
            f"・消費トークン約{self.keepa_tokens_consumed}"
            if self.keepa_tokens_consumed is not None
            else f"・Keepa問い合わせ{self.keepa_lookups}JAN"
        )
        return (
            f"承認{self.total_suppliers}社中{self.scanned_suppliers}社を棚卸し"
            f"・商品{self.fetched_items}件・JAN突合{self.matched_jans}/{self.jan_items}件"
            f"{tok}・未処理{self.remaining_suppliers}社"
            + ("（上限で打ち切り）" if self.truncated else "")
        )


def discover_from_netsea(
    *,
    preset_key: str = "hunting_beginner",
    supplier_ids: Optional[list[int]] = None,
    amazon_backend: Optional[AmazonDataBackend] = None,
    netsea_client=None,
    max_suppliers: int = 10,
    max_items_per_supplier: int = 100,
    max_jan_lookups: int = 100,
) -> tuple[list[DiscoveryRow], NetseaCoverage]:
    """卸起点（NETSEA承認サプライヤーの棚卸し）→Amazon突合→黒字候補の自動ランキング。

    キーワード不要の本命機能。流れ:
      1) GET /suppliers で承認サプライヤーを取得（supplier_ids 未指定なら承認全社）。
      2) 対象社（先頭 max_suppliers 社）について POST /items をページングして商品を棚卸し
         （各社 max_items_per_supplier 件まで・JAN付きのみ突合対象）。
      3) JANを集約・重複排除（同JANは最安卸1件）し、Keepa resolve_many（10件/コール）で突合。
         突合は max_jan_lookups 件で打ち切る（トークン上限・サイレント打ち切り禁止）。
      4) 既存の _build_row（name_match別商品ガード/数量ガード/profit）でランキング化。
         仕入値には NETSEA の卸価格（税抜・最安規格）を使う。

    上限に当たったら停止し coverage（NetseaCoverage）を返す。戻り値は (rows, coverage)。
    rows は (い)(あ) と同形式の DiscoveryRow（利益降順）。coverage で網羅状況を正直に開示する。
    """
    from adapters.netsea import NetseaClient

    preset = get_preset(preset_key)
    amazon = amazon_backend or get_backend()
    netsea = netsea_client or NetseaClient()
    cov = NetseaCoverage()

    # ── 1) 承認サプライヤー一覧 ──
    suppliers = netsea.list_suppliers()
    cov.total_suppliers = len(suppliers)
    if getattr(netsea, "last_error", None):
        cov.notes.append(f"/suppliers: {netsea.last_error}")

    # 対象社の決定（指定があればその順、無ければ承認全社の順）。
    all_ids = [s["id"] for s in suppliers]
    name_by_id = {s["id"]: s["name"] for s in suppliers}
    if supplier_ids:
        targets = [sid for sid in supplier_ids if sid in set(all_ids)] or list(supplier_ids)
    else:
        targets = all_ids

    scan_targets = targets[:max_suppliers]
    cov.scanned_suppliers = len(scan_targets)
    cov.remaining_suppliers = max(0, len(targets) - len(scan_targets))
    if cov.remaining_suppliers > 0:
        cov.truncated = True
        logger.info(
            "卸起点: 対象%d社中 先頭%d社のみ棚卸し（未処理%d社・上限max_suppliers=%d）",
            len(targets), len(scan_targets), cov.remaining_suppliers, max_suppliers,
        )

    # ── 2) 各社の棚卸し（ページング） ──
    all_items: list[YahooItem] = []
    for sid in scan_targets:
        items, item_cov = netsea.list_supplier_items(
            sid, max_items=max_items_per_supplier
        )
        all_items.extend(items)
        cov.fetched_items += item_cov.get("fetched", 0)
        if item_cov.get("truncated"):
            cov.truncated = True
            cov.remaining_items_estimate += 0  # 残数は未知（next_idはあるが件数不明＝正直に0加算）
            logger.info(
                "卸起点: supplier=%s は上限%d件で打ち切り（続きあり）",
                sid, max_items_per_supplier,
            )
        if item_cov.get("error"):
            cov.notes.append(
                f"supplier {name_by_id.get(sid, sid)}: {item_cov['error']}"
            )

    # ── 3) JAN集約・重複排除 → Keepa突合（上限あり） ──
    jan_items_all = [it for it in all_items if it.jan and it.price > 0]
    jan_items = _cheapest_per_jan(jan_items_all)
    cov.jan_items = len(jan_items)
    if len(jan_items) > max_jan_lookups:
        cov.truncated = True
        logger.info(
            "卸起点: JAN付き%d件中 先頭%d件のみKeepa突合（トークン上限max_jan_lookups=%d）",
            len(jan_items), max_jan_lookups, max_jan_lookups,
        )
    target_items = jan_items[:max_jan_lookups]

    # Keepa は 1コール最大10JAN。max_jan_lookups>10 のときは複数バッチで分割突合する。
    rows: list[DiscoveryRow] = []
    matched = 0
    batch_size = getattr(amazon, "MAX_JANS_PER_CALL", MAX_JAN_LOOKUPS) or MAX_JAN_LOOKUPS
    tokens_consumed_total = 0
    saw_token_info = False
    for i in range(0, len(target_items), batch_size):
        batch = target_items[i : i + batch_size]
        cov.keepa_lookups += len(batch)
        jan_to_product = amazon.resolve_many([it.jan for it in batch])
        tc = getattr(amazon, "last_tokens_consumed", None)
        if tc is not None:
            tokens_consumed_total += tc
            saw_token_info = True
        cov.keepa_tokens_left = getattr(amazon, "last_tokens_left", cov.keepa_tokens_left)
        for item in batch:
            ap = jan_to_product.get(item.jan)
            if ap is None:
                logger.info("除外[Amazon該当無し]: %s (JAN=%s)", item.name, item.jan)
                continue
            matched += 1
            row = _build_row(item, ap, preset)
            if row is None:
                continue
            rows.append(row)

    cov.matched_jans = matched
    if saw_token_info:
        cov.keepa_tokens_consumed = tokens_consumed_total

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)

    logger.info("卸起点カバレッジ: %s", cov.summary_line())
    return rows, cov


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
    yahoo = yahoo_client or default_supplier_client()

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

        row = _build_amazon_row(ap, yahoo, assumed_cost_rate, use_assumed_cost, preset)
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
    override_selection: Optional[dict] = None,
) -> list[DiscoveryRow]:
    """Keepa Product Finder で原石ASIN群を抽出→Yahoo突合→利益ランキング（キーワード不要）。

    Best Sellers（売れ筋トップ＝赤字）ではなく、Finder の条件抽出で
    「中位ランク × 競合薄 × 手頃価格」のニッチ原石を数千商品から自動で絞り込む。
    抽出した各ASINを JAN で Yahoo に当てて実仕入値を取り、個数安全判定を通して利益化する。

    トークン節約: Finder 1コール＋詳細最大 max_asins(≤15) 件の product 1バッチのみ。
    仕入元未発見/赤字は **でっち上げず正直に保留/除外**（_build_amazon_row と同じ honesty）。

    override_selection を渡すと、プリセットから組み立てる代わりにその selection を
    そのまま Product Finder へ流す（上級者がKeepaで作った検索条件URLの貼り付け経路）。
    利益フィルタの閾値は引き続き finder_preset_key のプリセット値を使う。
    """
    fpreset = get_finder_preset(finder_preset_key)
    amazon = amazon_backend or get_backend()
    yahoo = yahoo_client or default_supplier_client()

    # find_products を持つバックエンド（Keepa）でのみ Finder 探索。サンプル等は list_products へ。
    if hasattr(amazon, "find_products"):
        selection = override_selection or fpreset.to_selection(category_ids or [])
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
        row = _build_amazon_row(ap, yahoo, assumed_cost_rate, use_assumed_cost, preset)
        if row is not None:
            rows.append(row)

    rows = _apply_profit_filters(rows, preset)
    rows.sort(key=lambda r: r.net_profit, reverse=True)
    return rows


def _reverse_lookup_supplier(
    ap: AmazonProduct, yahoo: YahooShoppingClient
) -> Optional[YahooItem]:
    """Amazon候補のJANを Yahoo+楽天 で逆引きし、実在の最安仕入元1件を返す。

    honesty-first の肝（社長フィードバック対応）:
      - JAN が取れる ASIN のみ確実に逆引きする（JAN無しはでっち上げず None）。
      - MultiSupplierClient(jan_code=...) は各仕入元から同JANの有効候補を集め、
        **最安1件**だけ返す（_cheapest_for_jan）。その時点で「JAN一致 or JAN直指定で
        補完済み」を保証しているため、ここで再度 `it.jan == ap.jan` を厳格に課すと
        本番APIが janCode を空で返すヒットを取りこぼす（＝偽の0マッチの主因）。
      - よって「価格が有効（>0）」のみを最終条件にする。実在URLと実価格が無い候補は捨てる。
    Keepaトークンは消費しない（Yahoo/楽天は無料API）。
    """
    if not ap.jan:
        return None
    for it in yahoo.search(jan_code=ap.jan, results=5):
        # _cheapest_for_jan が JAN一致/直指定補完を担保済み。実価格が取れた1件を採る。
        if it.price and it.price > 0:
            return it
    return None


def _build_amazon_row(
    ap: AmazonProduct,
    yahoo: YahooShoppingClient,
    assumed_cost_rate: float,
    use_assumed: bool,
    preset: Optional[DiscoveryPreset] = None,
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
    supplier_source = ""
    match_status = AMAZON_ONLY
    conf = {"level": "", "reason": ""}
    hit = _reverse_lookup_supplier(ap, yahoo)
    if hit is not None:
        # 突合信頼度の多シグナル判定（JAN誤登録＋数値属性矛盾ガード）。逆引きで当たった
        # 仕入元名がAmazon名とかけ離れている／容量・サイズが矛盾すれば隔離する。
        conf = name_match.match_confidence(hit.name, ap.title)
        if conf["level"] == name_match.CONFIDENCE_LOW:
            logger.info(
                "別商品の疑い[信頼度低/逆引き]: 仕入元=%s ⇔ Amazon=%s (JAN=%s, %s)",
                hit.name, ap.title, ap.jan, conf["reason"],
            )
            return _suspect_row(hit, ap, conf)
        supplier_price = hit.price
        supplier_name = hit.name
        supplier_url = hit.url
        supplier_source = getattr(hit, "source", "")
        match_status = MATCH_OK

    # 実仕入値が取れた → 個数照合つきで利益計算（(い)と同じ honesty ロジック）。
    if supplier_price is not None:
        qres = _resolve_quantities(supplier_price, supplier_name, ap.title)
        result = profit.calculate(
            profit.ProfitInput(
                wholesale_price=qres["adjusted_price"],
                amazon_price=ap.current_price,
                category_key=ap.category_key,
                size_key=ap.size_key,
                # 原石判定の閾値は preset の実値（無ければ profit.py 既定）。preset緩和を効かせる。
                threshold_margin_rate=(
                    preset.min_margin_rate if preset else profit.THRESHOLD_MARGIN_RATE
                ),
                threshold_net_profit_yen=(
                    preset.min_net_profit if preset else profit.THRESHOLD_NET_PROFIT_YEN
                ),
            )
        )
        verdict = result.verdict
        if not qres["qty_reliable"] and verdict != profit.VERDICT_MISS:
            verdict = VERDICT_NEEDS_CHECK
        # 突合信頼度が「高」未満の行は原石にしない（要確認へ降格）。
        if conf["level"] != name_match.CONFIDENCE_HIGH and verdict != profit.VERDICT_MISS:
            verdict = VERDICT_NEEDS_CHECK
        notes = (
            list(result.notes)
            + list(getattr(ap, "estimate_notes", []) or [])
            + qres["extra_notes"]
        )
        if conf["level"] == name_match.CONFIDENCE_MID:
            notes = notes + [
                f"突合信頼度=中（{conf['reason']}）：仕入元名とAmazon名の一致が弱いため"
                "原石にはせず要確認。両リンクで同一商品か目視確認してください"
            ]
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
            maker=ap.maker,
            supplier_qty=qres["supplier_qty"],
            amazon_qty=qres["amazon_qty"],
            qty_flag=qres["qty_flag"],
            qty_reliable=qres["qty_reliable"],
            match_confidence=conf["level"],
            match_confidence_reason=conf["reason"],
            supplier_price_raw=supplier_price,
            supplier_url=supplier_url,
            supplier_source=supplier_source,
            category_label=result.category_label,
            is_sample=ap.is_sample,
            price_history=getattr(ap, "price_history", None),
            category_key=ap.category_key,
            size_key=ap.size_key,
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
            maker=ap.maker,
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
        maker=ap.maker,
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
    """利益閾値（利益率/純利益）は **原石バッジの付与条件** に留め、行は捨てない。

    社長フィードバック（2026-06-05）の恒久対策：
      「JAN突合できた行を“非表示にして0件化”しない」。
    よって突合できた行（supplier_price あり＝実利益を計算できた行、または仕入元未発見の
    候補保留行）は **全件返す**。閾値を満たさない行は verdict を下げるだけで表示は残す。

    verdict の決め方（捨てない代わりにラベルで正直に区別する）:
      - 閾値クリア & 数量信頼 & profit的に原石 → そのまま「原石」
      - 閾値割れ / 数量不確実 / Amazon条件外 → 「要確認」へ降格（行は残す）
      - 赤字（純利益<=0） → 「はずれ」（profit側の判定を尊重。行は残すが最下位に並ぶ）
    """
    out = []
    for r in rows:
        passes_threshold = (
            r.margin_rate >= preset.min_margin_rate
            and r.net_profit >= preset.min_net_profit
        )
        # 原石は「閾値クリア＋数量信頼＋突合信頼度=高＋profitエンジンが原石判定」の四拍子だけ。
        # 社長＝正確性最優先：突合信頼度が高でない行は原石に上げない（誤突合の原石化を根絶）。
        conf_high = r.match_confidence in ("", name_match.CONFIDENCE_HIGH)
        if r.supplier_price is not None and not (
            passes_threshold and r.qty_reliable and conf_high
        ):
            if r.verdict != profit.VERDICT_MISS:
                r.verdict = VERDICT_NEEDS_CHECK
        # どの行も捨てない（突合できた事実を社長に全件見せる）。
        out.append(r)
    return out


# =============================================================================
# 最悪相場シミュレーション（PoiPoi の「過去相場まで下落しても黒字か」判定）
# =============================================================================
@dataclass
class WorstCaseResult:
    """最悪相場シミュレーションの結果（行1件ぶん）。"""

    worst_price: float          # 想定した「最悪の売値」（円・過去相場の最安水準 or 手入力）
    worst_net_profit: float     # その売値での純利益（calc.profit 再計算・円）
    worst_margin_rate: float    # その売値での利益率（0〜1）
    is_profitable: bool         # 最悪ケースでも黒字か（損切り回避できるか）
    source: str                 # "history"=過去相場から / "manual"=手入力売値から
    note: str = ""


def worst_case_floor_price(price_history: Optional[list]) -> Optional[float]:
    """過去相場の系列から『最悪のケースの売値』＝過去最安水準を返す。

    PoiPoi 資料の「過去相場（元相場）まで下落しても黒字か」を判定するための床値。
    系列が無ければ None（UI は手入力売値での簡易シミュレーションに切り替える）。
    """
    if not price_history:
        return None
    vals = [float(p) for p in price_history if isinstance(p, (int, float)) and p > 0]
    return min(vals) if vals else None


def simulate_worst_case(
    row: DiscoveryRow, *, manual_price: Optional[float] = None
) -> Optional[WorstCaseResult]:
    """『最悪相場まで売値が下落しても黒字か』を calc.profit で再計算して返す。

    売値の決め方:
      - manual_price 指定時はそれ（社長が「想定下落後売値」を入力した簡易版）。
      - 未指定時は row.price_history の過去最安水準（Keepa から取れた相場）。
    仕入値は row.supplier_price（実仕入値）。calc.profit に丸投げ＝UIでは1円も計算しない。
    仕入値が無い（仕入元未特定）行は None（利益計算不能）。
    """
    if row.supplier_price is None:
        return None
    if manual_price is not None and manual_price > 0:
        worst_price = float(manual_price)
        source = "manual"
        note = "社長入力の『想定下落後売値』での再計算（実相場ではなく仮定）"
    else:
        floor = worst_case_floor_price(row.price_history)
        if floor is None:
            return None  # 相場系列も手入力も無ければシミュレーション不能
        worst_price = floor
        source = "history"
        note = "過去相場の最安水準まで売値が下落したと仮定した最悪ケース"

    result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=row.supplier_price,   # 実仕入値（税込扱い）
            amazon_price=worst_price,
            category_key=row.category_key,
            size_key=row.size_key,
        )
    )
    return WorstCaseResult(
        worst_price=worst_price,
        worst_net_profit=result.net_profit,
        worst_margin_rate=result.margin_rate,
        is_profitable=result.net_profit > 0,
        source=source,
        note=note,
    )


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
