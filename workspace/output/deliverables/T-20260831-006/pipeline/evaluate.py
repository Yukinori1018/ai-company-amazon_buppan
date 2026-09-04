"""利益計算 — NETSEA の卸値（実額）× Keepa の Amazon 実績（実額）→ 1行の CSV。

**この層の存在意義は「1円もごまかさない」こと。**
料率も手数料も一切ここには書きません。すべて `calc/fees.py`（T-20260521-005 / 2026-08 料率）
から取ります。数字を直したくなったら、直す先はあちらです。

推定が混じるのは次の3つだけで、CSV に内訳列として明示します:
    1. FBA 納品送料（1個あたり）      … 社長の実績が出たら置き換える
    2. FBA 在庫保管手数料              … 保管月数の仮定が入る
    3. 雑費（梱包資材・ラベル・返品）  … 売値に対する率
卸価格と Amazon 売値は**推定ではありません**。ここが NETSEA 起点の最大の値打ちです。
"""

from dataclasses import dataclass
from typing import Optional

from . import config, keepa_verify, pack, paths, screen
from .screen import Candidate

paths.ensure()

from calc import fees, profit  # noqa: E402
from adapters.amazon_data import _CATEGORY_NAME_MAP  # noqa: E402


def map_category_key(category_names: list) -> str:
    """Keepa の categoryTree 名 → fees の category_key。不明は default（15.4%＝辛い側）。"""
    for name in category_names:
        for needle, key in _CATEGORY_NAME_MAP:
            if needle in name:
                return key
    return "default"


@dataclass
class Evaluation:
    """1候補の最終評価。CSV 1行にほぼそのまま落ちる。"""

    candidate: Candidate
    facts: keepa_verify.AmazonFacts
    result: Optional[object] = None       # profit.ProfitResult（Amazon未出品なら None）
    category_key: str = "default"
    size_key: str = "unknown"
    size_label: str = ""
    storage_fee: float = 0.0
    # 旧「雑費（売価の3%）」を置換。売価には連動させない（経理ハジメ 2026-09-04）。
    return_provision: float = 0.0
    # 小口プランの基本成約料。売れた1点ごとに必ず乗る（売価に関係しない）。
    closing_fee: float = 0.0
    # FBA納品送料 ＋ 納品代行の作業費 ＋ NETSEA送料の按分。
    inbound_shipping: float = 0.0
    # NETSEA 1単位に対して Amazon 1出品が何単位ぶんか。卸値をこの数だけ掛ける。
    pack_size: int = 1
    # 入数をどう判断したかの説明（CSV にそのまま出す。根拠を値と一緒に運ぶ）。
    pack_reason: str = ""
    # 自動判定を信用してはいけない行の理由。空でなければ利益判定を出さない。
    review_reason: str = ""
    status: str = ""                       # 利益判定できたか／できなかった理由

    @property
    def is_profitable(self) -> bool:
        return self.result is not None and self.result.net_profit > 0


STATUS_NOT_ON_AMAZON = "Amazon未出品(同一JANのASINなし)"
STATUS_NO_PRICE = "Amazon価格が取得できず(出品はあるが在庫なし等)"
STATUS_OK = "計算済み"
STATUS_NEEDS_REVIEW = "要確認"

# 「回転」の判定に使う直近30日のランク下落回数。
# Keepa 公式が概算の販売個数として使う代理指標で、**販売数そのものではありません**。
DROPS_DECENT = 3      # 月3個以上動いていれば、少なくとも「死に筋ではない」
DROPS_SLOW = 1        # 1〜2 は「月に数個」。試し仕入れの数量を絞る帯

# 利益率の区分。社長のご指示（2026-08-31）で **5% から候補に含める**ことになりました。
# 会社 KPI は利益率20%ですが、**捨てるのではなく段階で見せて社長が線を引けるように**します。
# 上限を書かない（20%以上を1つにまとめる）のは、そこから先は率より回転が効くからです。
MARGIN_BANDS = [(0.05, "5%未満"), (0.10, "5〜10%"), (0.20, "10〜20%"), (None, "20%以上")]


def margin_band(margin_rate: Optional[float]) -> str:
    """利益率 → 区分ラベル。赤字は赤字とはっきり書く（0%台に紛れさせない）。"""
    if margin_rate is None:
        return ""
    if margin_rate < 0:
        return "赤字"
    for upper, label in MARGIN_BANDS:
        if upper is None or margin_rate < upper:
            return label
    return MARGIN_BANDS[-1][1]


def overall_verdict(ev: "Evaluation") -> str:
    """利益と**回転**の両方を見た総合判定。

    ⚠️ **これがこのファイルで一番大事な関数です。**
       利益率だけを見ると、「利益率55.9%・純利益7,230円」なのに
       **直近30日で1個も売れていない**商品が最上位に来ます（初回実走で実際に起きた）。
       在庫は現金です。売れない在庫は利益率が何%だろうと現金を潰します。
       利益の判定（calc/profit.py）は回転を知らないので、ここで必ず重ねます。
    """
    if ev.result is None:
        return ev.status
    # ⚠️ 要確認は赤字判定より先。**「儲かる」と言い切れない行を儲かる側に見せない。**
    if ev.review_reason:
        return f"要確認（{ev.review_reason}）"
    if ev.result.net_profit <= 0:
        return "はずれ(赤字)"
    drops = ev.facts.drops30
    if drops is None:
        return "利益は出るが販売実績が不明"
    if drops == 0:
        return "利益は出るが直近30日に売れた形跡なし"
    if drops < DROPS_DECENT:
        return f"利益は出るが回転が遅い(30日で約{drops}個)"
    return ev.result.verdict  # 原石 / あやしい


def evaluate(
    candidate: Candidate,
    facts: keepa_verify.AmazonFacts,
    cfg: config.ScanConfig,
) -> Evaluation:
    """1候補を評価する。**利益が出ない場合も必ず Evaluation を返す**（黙って捨てない）。"""
    ev = Evaluation(candidate=candidate, facts=facts)

    if not facts.found or not facts.asin:
        # ⚠️ ここが正直に書かなければならない一番大事なところ。
        # 「Amazon に同一 JAN の商品が無い」は
        #     (a) 誰も出していない＝競合ゼロの好機
        #     (b) そもそも需要が無い
        # のどちらでも同じ結果になります。**この観測だけでは区別できません。**
        ev.status = STATUS_NOT_ON_AMAZON
        return ev

    ev.category_key = map_category_key(facts.category_names)
    ev.size_key, ev.size_label = keepa_verify.fba_size_key(facts)

    if facts.price_yen is None or facts.price_yen <= 0:
        ev.status = STATUS_NO_PRICE
        return ev

    costs = cfg.costs
    # NETSEA 側の送料は「1回の発注」に対して掛かる。想定発注数で按分する（推定）。
    netsea_ship_per_unit = (
        candidate.ship_fee / max(costs.netsea_ship_amortize_qty, 1)
        if candidate.ship_fee
        else 0.0
    )
    # 納品代行の作業費は「物理作業は外注」という社長方針の実費。
    # 2026-09-04 まで1円も入っていませんでした（owner_pc_complete_outsourcing に反する）。
    ev.inbound_shipping = (
        costs.fba_inbound_yen + costs.prep_service_yen + netsea_ship_per_unit)
    ev.closing_fee = costs.closing_fee_yen

    # 保管手数料は体積が要る。寸法不明なら 0 にせず、標準1の代表体積で仮置きすると
    # 嘘になるので **0 のまま「不明」を status に残す**方針にした（過小評価は明示する）。
    volume_cm3 = 0.0
    if len(facts.package_mm) == 3:
        volume_cm3 = (facts.package_mm[0] / 10) * (facts.package_mm[1] / 10) * (
            facts.package_mm[2] / 10
        )
        ev.storage_fee = fees.get_storage_fee_yen(
            volume_cm3,
            costs.storage_months,
            size_class="large" if ev.size_key.startswith("large") else "standard",
            peak_season=costs.storage_peak_season,
        )

    # ⚠️ まとめ売り出品への対応。**ここを忘れると利益が数倍に膨らんで出ます。**
    # 入数は **Amazon 側の商品名にしか書かれていないことが多い**（NETSEA 側は単品名）。
    # 事故2回とも、Amazon のタイトルを読まなかったこと（読めなかったこと）が原因でした。
    # NETSEA 側も複数個入りのことがあるので、**両側を読んで倍率を出す**。
    ev.pack_size, ev.pack_reason, needs_review = pack.resolve_multiplier(
        candidate.product_name, facts.title)
    if needs_review:
        ev.review_reason = ev.pack_reason
    wholesale_for_listing = candidate.wholesale_ex_tax * ev.pack_size

    size_key_for_fee = "standard_2" if ev.size_key == "unknown" else ev.size_key

    def run(other_costs: float):
        return profit.calculate(
            profit.ProfitInput(
                wholesale_price=wholesale_for_listing,
                wholesale_price_is_tax_included=costs.wholesale_is_tax_included,
                amazon_price=facts.price_yen,
                category_key=ev.category_key,
                size_key=size_key_for_fee,
                inbound_shipping=ev.inbound_shipping,
                other_costs=other_costs,
                # 販売手数料は税抜表示。請求は×1.1（経理ハジメ実測 2026-09-04）。
                referral_fee_tax_rate=costs.referral_fee_tax_rate,
                threshold_margin_rate=cfg.min_margin_rate,
                threshold_net_profit_yen=cfg.min_net_profit,
            )
        )

    # 返品引当は「FBA配送料と販売手数料と仕入原価」から決まるので、
    # 手数料が確定してからでないと出せません。calculate は純関数なので2回呼びます
    # （返品引当を売価×3%で済ませていた旧実装の、経理的な根拠の無さを直すため）。
    first = run(ev.storage_fee + ev.closing_fee)
    ev.return_provision = costs.return_provision(
        first.fba_fee, first.referral_fee, first.wholesale_price_incl_tax)
    ev.result = run(ev.storage_fee + ev.closing_fee + ev.return_provision)
    # 機械的な異常値ガード。人の注意力に頼らず、ここで捕まえる。
    ratio = facts.price_yen / max(wholesale_for_listing * (1 + fees.CONSUMPTION_TAX_RATE), 1)
    if ratio >= config.SUSPICIOUS_PRICE_RATIO and not ev.review_reason:
        ev.review_reason = (
            f"売価が仕入の{ratio:.1f}倍。入数の読み落としの疑い"
            f"（Amazon商品名を確認してください）")

    ev.status = STATUS_NEEDS_REVIEW if ev.review_reason else STATUS_OK
    if ev.pack_size > 1:
        ev.status += f"（Amazonはケース売り{ev.pack_size}倍。卸値を{ev.pack_size}倍で計上）"
    if ev.size_key == "unknown":
        ev.status += "（FBAサイズ不明のため標準2で仮置き・保管料は未計上）"
    elif volume_cm3 == 0:
        ev.status += "（寸法不明のため保管料は未計上）"
    return ev


# =============================================================================
# CSV 出力
# =============================================================================

COLUMNS = [
    "商品名", "Amazon商品名", "JAN", "ASIN", "サプライヤー名", "業態", "NETSEA卸値(税抜)", "NETSEA卸値(税込)",
    "Amazon価格", "価格の出所", "純利益", "利益率%", "利益率区分", "ROI%",
    "月間販売数(30日ランク下落数)", "月間販売数(90日ドロップ÷3)",
    "出品者数", "出品者数の出所", "Amazon本体の有無", "ランキング",
    "FBAサイズ", "手数料内訳", "販売手数料(消費税込)", "FBA配送料", "保管料", "納品送料(FBA+納品代行)", "基本成約料", "返品引当",
    "出品の入数", "入数の根拠", "要確認理由", "最小発注数", "最小発注額(税込)", "他サプライヤー数", "同一JANのASIN数", "ネット販売可否",
    "総合判定", "利益判定", "法令要確認", "発注前に必ず確認",
    "状態", "Amazonページ", "Keepaリンク", "NETSEA商品ページ", "備考",
]

# サプライヤーの「販売条件」は自由記述で、**API のスキーマに存在しません**（ハルオ判定 §第3層）。
# 「Amazon不可」「モール不可」「売価厳守」がここに書かれうるため、自動判定は不可能です。
# 全行に固定文言で出して、確認導線（NETSEA商品ページ列）と必ずセットで社長へ渡します。
PRE_ORDER_CHECK = (
    "商品ページの「販売条件」タブを人が読むこと"
    "（Amazon不可・モール不可・売価厳守の記載が API では取得できません）"
)


def to_row(ev: Evaluation) -> dict:
    """Evaluation → CSV 1行の dict。**取れない値は空欄**。推測で埋めない。"""
    c, f, r = ev.candidate, ev.facts, ev.result
    tax = 1 + fees.CONSUMPTION_TAX_RATE
    row = {
        "商品名": c.product_name,
        "Amazon商品名": f.title,
        "JAN": c.jan,
        "ASIN": f.asin or "",
        "サプライヤー名": c.supplier_name,
        "業態": c.business_type,
        "NETSEA卸値(税抜)": c.wholesale_ex_tax,
        "NETSEA卸値(税込)": round(c.wholesale_ex_tax * tax * (ev.pack_size or 1)),
        "Amazon価格": f.price_yen if f.price_yen is not None else "",
        "価格の出所": f.price_source,
        "純利益": "", "利益率%": "", "利益率区分": "", "ROI%": "",
        "月間販売数(30日ランク下落数)": f.drops30 if f.drops30 is not None else "",
        "月間販売数(90日ドロップ÷3)": round(f.drops90 / 3) if f.drops90 is not None else "",
        "出品者数": (
            f.real_seller_count if f.real_seller_count is not None
            else (f.offer_count if f.offer_count is not None else "")
        ),
        "出品者数の出所": f.seller_count_source,
        "Amazon本体の有無": (
            "" if f.amazon_sells_it is None else ("あり" if f.amazon_sells_it else "なし")
        ),
        "ランキング": f.sales_rank if f.sales_rank is not None else "",
        "FBAサイズ": ev.size_label,
        "手数料内訳": "", "販売手数料(消費税込)": "", "FBA配送料": "",
        "保管料": round(ev.storage_fee) if ev.storage_fee else "",
        "納品送料(FBA+納品代行)": round(ev.inbound_shipping) if ev.inbound_shipping else "",
        "基本成約料": round(ev.closing_fee) if ev.closing_fee else "",
        "返品引当": round(ev.return_provision) if ev.return_provision else "",
        "出品の入数": ev.pack_size,
        "入数の根拠": ev.pack_reason,
        "要確認理由": ev.review_reason,
        "最小発注数": c.set_num,
        "最小発注額(税込)": c.set_price_incl_tax or "",
        "他サプライヤー数": c.alt_supplier_count,
        "同一JANのASIN数": f.asin_count or "",
        "ネット販売可否": "可" if c.deal_net_shop_flag == "Y" else c.deal_net_shop_flag,
        "総合判定": overall_verdict(ev),
        "利益判定": "",
        "法令要確認": " / ".join(screen.law_check_flags(c.product_name)),
        "発注前に必ず確認": PRE_ORDER_CHECK,
        "状態": ev.status,
        "Amazonページ": f.amazon_url,
        "Keepaリンク": f.keepa_url,
        "NETSEA商品ページ": c.product_url,
        "備考": " / ".join(c.notes),
    }
    if r is not None:
        row.update({
            "純利益": round(r.net_profit),
            "利益率%": round(r.margin_rate * 100, 1),
            "利益率区分": margin_band(r.margin_rate),
            "ROI%": round(r.roi * 100, 1),
            "販売手数料(消費税込)": round(r.referral_fee),
            "FBA配送料": round(r.fba_fee),
            "利益判定": r.verdict,
            "手数料内訳": (
                f"販売{round(r.referral_fee)}({r.referral_rate*100:.1f}%・消費税込)"
                f"+FBA{round(r.fba_fee)}"
                f"+成約料{round(ev.closing_fee)}"
                f"+保管{round(ev.storage_fee)}"
                f"+納品{round(ev.inbound_shipping)}"
                f"+返品引当{round(ev.return_provision)}"
            ),
        })
    return row


# =============================================================================
# サプライヤー単位の集計（秘書カズヨの「3階層リスト」の第1階層用）
# =============================================================================

SUPPLIER_COLUMNS = [
    "サプライヤー名", "supplier_id", "業態", "取引状態", "取扱商品数", "規格数",
    "JAN保有率%", "候補数(前段通過)", "Keepa検証済み", "Amazonに存在",
    "利益プラス", "利益率5%以上", "利益率10%以上", "利益率20%以上",
    "回転もある候補", "最良の純利益", "最良商品のASIN", "NETSEA店舗ページ",
]

# API が返すのは「取引申請が承認済み」のサプライヤーだけ（NETSEA 公式ヘルプ）。
# したがってこのファイルに出てくる社は **全社が第1階層＝今すぐ発注できる相手**です。
TRADE_STATUS_APPROVED = "承認済み(今すぐ発注できる)"


def supplier_summary(evaluations: list, all_candidates: list) -> list:
    """サプライヤーごとに「この取引先は使えるのか」を1行にまとめる。

    社長が見たいのは商品の前に**取引先**です（「取引できるメーカー」）。
    商品行だけ渡すと225社ぶんが混ざって、どの相手が有望なのか読めません。
    """
    agg: dict = {}

    def slot(sid, name, url=""):
        row = agg.setdefault(sid, {
            "サプライヤー名": name, "supplier_id": sid, "業態": "",
            "取引状態": TRADE_STATUS_APPROVED,
            "取扱商品数": 0, "規格数": 0, "_jan": 0,
            "候補数(前段通過)": 0, "Keepa検証済み": 0, "Amazonに存在": 0,
            "利益プラス": 0, "利益率5%以上": 0, "利益率10%以上": 0, "利益率20%以上": 0,
            "回転もある候補": 0, "最良の純利益": "", "最良商品のASIN": "",
            "NETSEA店舗ページ": f"https://www.netsea.jp/shop/{sid}" if sid else "",
        })
        if name and not row["サプライヤー名"]:
            row["サプライヤー名"] = name
        return row

    products: dict = {}
    for c in all_candidates:
        row = slot(c.supplier_id, c.supplier_name)
        if c.business_type and not row["業態"]:
            row["業態"] = c.business_type
        row["規格数"] += 1
        if c.jan:
            row["_jan"] += 1
        if c.verdict == screen.PASS:
            row["候補数(前段通過)"] += 1
        products.setdefault(c.supplier_id, set()).add(c.product_url)

    for sid, urls in products.items():
        slot(sid, "")["取扱商品数"] = len(urls)

    for ev in evaluations:
        row = slot(ev.candidate.supplier_id, ev.candidate.supplier_name)
        row["Keepa検証済み"] += 1
        if ev.facts.found:
            row["Amazonに存在"] += 1
        if not ev.is_profitable:
            continue
        row["利益プラス"] += 1
        m = ev.result.margin_rate
        for threshold, key in ((0.05, "利益率5%以上"), (0.10, "利益率10%以上"),
                               (0.20, "利益率20%以上")):
            if m >= threshold:
                row[key] += 1
        if (ev.facts.drops30 or 0) >= DROPS_DECENT:
            row["回転もある候補"] += 1
        best = row["最良の純利益"]
        if best == "" or ev.result.net_profit > best:
            row["最良の純利益"] = round(ev.result.net_profit)
            row["最良商品のASIN"] = ev.facts.asin or ""

    out = []
    for row in agg.values():
        n = row.pop("_jan")
        row["JAN保有率%"] = round(n / row["規格数"] * 100, 1) if row["規格数"] else 0
        out.append(row)
    # 「使える取引先」が上に来る順。利益が出た数 → 回転もある数 → 候補数。
    maker_rank = {"メーカー": 0, "卸専業": 1, "卸および小売業": 2, "その他": 3}
    out.sort(key=lambda r: (
        -r["利益プラス"], -r["回転もある候補"],
        maker_rank.get(str(r["業態"]).split("（")[0], 9),   # 社長の狙いはメーカー仕入れ
        -r["候補数(前段通過)"],
    ))
    return out
