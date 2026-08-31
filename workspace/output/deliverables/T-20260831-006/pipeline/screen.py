"""前段フィルタ — **Keepa に1トークンも払う前に**、機械的に落とせるものを落とす。

なぜこの層が要るか（設計の背骨）:
    Keepa のトークンは上限1,200・補充20/分で**貯め込めません**（実測 / T-20260817-005）。
    NETSEA の承認済みサプライヤーは225社あり、全商品を検証するのは非現実的です。
    ここで落とせた1件が、そのまま本命1件ぶんのトークンになります。

このファイルの約束:
    - **純関数だけ。** ネットワークにも時計にも触らない → テストできる
    - **不明を「駄目」にしない。** 上代が空欄、寸法が無い、といった欠測は通す。
      落とすのは「値が分かっていて、それが基準を満たさない」ものだけ
    - 落とした理由を必ず1件ずつ残す（歩留まりを社長に説明できるようにするため）
"""

from dataclasses import dataclass, field
from typing import Optional

from . import config

# 除外理由のラベル。CSV / 統計の集計キーとしてそのまま使う。
REASON_NO_JAN = "JANなし"
REASON_BAD_JAN = "JAN形式不正"
REASON_SOLD_OUT = "在庫なし"
REASON_NO_PRICE = "卸価格なし"
REASON_NET_SHOP_NG = "ネット販売不可(deal_net_shop_flag≠Y)"
REASON_PRICE_BAND = "卸価格が採用レンジ外"
REASON_REGULATED = "規制品・危険物の疑い"
REASON_USED = "中古品の疑い(古物商許可が未取得)"
REASON_HOPELESS = "上代でも利益が出ない"
REASON_DUP_JAN = "同一JANの重複(他サプライヤーが安い)"

PASS = "通過"


@dataclass
class Candidate:
    """NETSEA の1商品×1規格。**これがパイプラインを流れる唯一の単位**。

    NETSEA の1商品(`product`)は複数の規格(`set[]`)を持ち、規格ごとに JAN も価格も違います。
    Amazon 側は JAN 単位で別 ASIN になるので、**規格を1件として扱う**のが正しい粒度です。
    """

    jan: str
    product_name: str
    supplier_id: int
    supplier_name: str
    product_url: str
    # 卸価格（税抜・1個あたり単価）。NETSEA set[].price。
    wholesale_ex_tax: int
    # 上代（希望小売・税抜）。空欄の商品が多い。0 は「不明」を意味する。
    reference_price_ex_tax: int = 0
    # 最小発注のまとまり。set_num=10 なら「10個単位でしか買えない」。
    set_num: int = 1
    # まとめ買い1口ぶんの税込金額（＝実質の最小発注額）。
    set_price_incl_tax: int = 0
    direct_item_id: str = ""
    category_id: Optional[int] = None
    # NETSEA 側の送料設定（実発注時に /tariffs で確定させる必要あり）。
    ship_fee: int = 0
    # ネットショップでの販売可否。'Y' 以外は Amazon 出品の前提が崩れる。
    deal_net_shop_flag: str = ""
    consumption_tax_class: Optional[int] = None
    spec_size: str = ""
    # 判定結果（screen が埋める）
    verdict: str = ""
    reason: str = ""
    # 同一 JAN を扱う他サプライヤー数（重複排除で潰した数）。
    alt_supplier_count: int = 0
    notes: list = field(default_factory=list)


def _valid_jan13(value) -> bool:
    """JAN13（EAN13）として Keepa の `code` に投げられる形か。

    チェックデジットまでは見ません。Keepa 側が弾いても **0トークン**（ヒット0は課金されない
    ＝実測）なので、ここで厳密にやる実益がありません。桁と数字だけ見ます。
    """
    s = str(value or "").strip()
    return len(s) == 13 and s.isdigit()


def to_candidates(raw_item: dict) -> list[Candidate]:
    """NETSEA /items の生 dict 1件 → 規格ごとの Candidate リストに展開する。

    JAN は set[].jan_code を優先し、空ならトップレベルの jan_code で補う
    （単一規格の商品は set 側が空のことがある）。
    """
    sets = raw_item.get("set") or []
    top_jan = str(raw_item.get("jan_code") or "").strip()
    out: list[Candidate] = []
    for s in sets:
        jan = str(s.get("jan_code") or "").strip() or top_jan
        out.append(
            Candidate(
                jan=jan,
                product_name=str(raw_item.get("product_name") or ""),
                supplier_id=int(raw_item.get("supplier_id") or 0),
                supplier_name=str(raw_item.get("shop_name") or ""),
                product_url=str(raw_item.get("product_url") or ""),
                wholesale_ex_tax=_int(s.get("price")),
                reference_price_ex_tax=_int(s.get("reference_price")),
                set_num=_int(s.get("set_num")) or 1,
                set_price_incl_tax=_int(s.get("set_price")),
                direct_item_id=str(s.get("direct_item_id") or ""),
                category_id=raw_item.get("category_id"),
                ship_fee=_int(raw_item.get("ship_fee")),
                deal_net_shop_flag=str(raw_item.get("deal_net_shop_flag") or ""),
                consumption_tax_class=s.get("consumption_tax_class"),
                spec_size=str(raw_item.get("spec_size") or ""),
                notes=["品切れ"] if s.get("sold_out_flag") == "Y" else [],
            )
        )
        # 在庫フラグは Candidate に列を増やさず notes で持つ（共通型を太らせない）。
        out[-1].__dict__["_sold_out"] = s.get("sold_out_flag") == "Y"
    return out


def _int(value) -> int:
    """NETSEA は空文字・None・数字文字列が混在する。落ちない変換を1箇所に。"""
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def looks_regulated(name: str, keywords=None) -> Optional[str]:
    """商品名に規制品・危険物の語が入っていれば、その語を返す。無ければ None。

    ⚠️ 商品名だけの判定です。取りこぼしも誤検知もあります。
       ここは「トークンを節約するための粗い網」であって、**出品可否の判定ではありません**。
       実発注前には必ず Amazon の出品制限（ゲート）を実機で確認してください。
    """
    keywords = config.REGULATED_KEYWORDS if keywords is None else keywords
    for kw in keywords:
        if kw in name:
            return kw
    return None


def looks_used(name: str, keywords=None) -> Optional[str]:
    """中古品を示す語が入っていれば、その語を返す。無ければ None。

    社長は**古物商許可を未取得**です。中古・ヴィンテージ・リユース品を1点でも扱えば
    古物営業法違反（無許可営業）になります。NETSEA が卸サイトであることは免罪符になりません
    （実測: 「中古」で212件ヒット／ハルオ判定 §3-3）。
    """
    keywords = config.USED_KEYWORDS if keywords is None else keywords
    for kw in keywords:
        if kw in name:
            return kw
    return None


def law_check_flags(name: str) -> list:
    """発注前に人が確認すべき法令の一覧を返す（**除外はしない**）。

    電安法27条の PSE 表示義務などは**転売者にも及びます**。
    「輸入者ではないから関係ない」は誤りです（ハルオ判定 §3）。
    ここで落とすと家電がまるごと消えて母数が死ぬので、目印だけ立てて人へ渡します。
    """
    hits = []
    for label, words in config.LAW_CHECK_KEYWORDS.items():
        if any(w in name for w in words):
            hits.append(label)
    return hits


def best_case_net_profit(candidate: Candidate, cfg: config.ScanConfig) -> Optional[float]:
    """「この商品が最高にうまくいった場合」の純利益。**上代が不明なら None**（＝判定しない）。

    最高の場合とは:
        売値   = 上代 × ceiling_multiple（既定1.3倍）
        販売手数料 = 全カテゴリで最も安い料率
        FBA手数料  = 最も小さいサイズ区分
        送料・保管・雑費 = ゼロ
    ここまで甘くしても利益が基準に届かないなら、**Keepa を引いても結論は変わりません。**
    これが「トークンを本命に集中させる」の実体です。
    """
    if candidate.reference_price_ex_tax <= 0:
        return None  # 上代不明 → 判定しない（不明を駄目にしない）

    from calc import fees

    ceiling = candidate.reference_price_ex_tax * (1 + fees.CONSUMPTION_TAX_RATE)
    ceiling *= cfg.ceiling_multiple

    best_rate = min(v["rate"] for v in fees.REFERRAL_FEE_TABLE.values())
    best_fba = min(
        v["fba_fee_yen"] for k, v in fees.FBA_FEE_TABLE.items() if k != "self_ship"
    )
    wholesale_incl = candidate.wholesale_ex_tax * (1 + fees.CONSUMPTION_TAX_RATE)
    return ceiling - ceiling * best_rate - best_fba - wholesale_incl


def screen_one(candidate: Candidate, cfg: config.ScanConfig) -> Candidate:
    """1件を判定して verdict / reason を埋めて返す（破壊的に同じオブジェクトを更新）。

    判定順は **安い順・落ちる率が高い順**。JAN 判定が最初なのは、
    JAN が無ければそもそも Keepa の1トークン検証に載せられないからです。
    """
    name = candidate.product_name

    if not candidate.jan:
        return _reject(candidate, REASON_NO_JAN)
    if not _valid_jan13(candidate.jan):
        return _reject(candidate, REASON_BAD_JAN)
    if candidate.__dict__.get("_sold_out"):
        return _reject(candidate, REASON_SOLD_OUT)
    if candidate.wholesale_ex_tax <= 0:
        return _reject(candidate, REASON_NO_PRICE)
    if cfg.require_net_shop_ok and candidate.deal_net_shop_flag != "Y":
        return _reject(candidate, REASON_NET_SHOP_NG)
    if not (cfg.wholesale_min <= candidate.wholesale_ex_tax <= cfg.wholesale_max):
        return _reject(
            candidate,
            f"{REASON_PRICE_BAND}({candidate.wholesale_ex_tax}円)",
        )
    if cfg.drop_used:
        hit = looks_used(name)
        if hit:
            return _reject(candidate, f"{REASON_USED}: 「{hit}」")
    if cfg.drop_regulated:
        hit = looks_regulated(name)
        if hit:
            return _reject(candidate, f"{REASON_REGULATED}: 「{hit}」")

    best = best_case_net_profit(candidate, cfg)
    if best is not None and best < cfg.min_net_profit:
        return _reject(candidate, f"{REASON_HOPELESS}(最良でも{best:.0f}円)")

    candidate.verdict = PASS
    candidate.reason = ""
    if best is None:
        candidate.notes.append("上代不明のため前段の利益判定はスキップ")
    return candidate


def _reject(candidate: Candidate, reason: str) -> Candidate:
    candidate.verdict = "除外"
    candidate.reason = reason
    return candidate


def dedupe_by_jan(candidates: list[Candidate]) -> tuple[list[Candidate], int]:
    """同じ JAN を複数サプライヤーが扱っている場合、**最も安い1件だけ**を残す。

    同じ JAN を2回 Keepa に投げるのはトークンの丸損です。
    残した1件には「他に何社が扱っているか」を `alt_supplier_count` で記録します
    （＝相見積もりの余地。将来まとめて叩ける情報なので捨てない）。

    戻り値: (残した候補, 潰した件数)
    """
    best: dict[str, Candidate] = {}
    counts: dict[str, int] = {}
    for c in candidates:
        counts[c.jan] = counts.get(c.jan, 0) + 1
        cur = best.get(c.jan)
        if cur is None or c.wholesale_ex_tax < cur.wholesale_ex_tax:
            best[c.jan] = c
    for jan, c in best.items():
        c.alt_supplier_count = counts[jan] - 1
    dropped = len(candidates) - len(best)
    return list(best.values()), dropped


def summarize(candidates: list[Candidate]) -> dict:
    """除外理由ごとの件数。README と完了報告に載せる「歩留まり」の素。"""
    out: dict[str, int] = {}
    for c in candidates:
        # 括弧つきの理由（金額入り）はラベル部分だけで集計する。
        key = c.reason.split("(")[0].split(":")[0].strip() if c.reason else PASS
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
