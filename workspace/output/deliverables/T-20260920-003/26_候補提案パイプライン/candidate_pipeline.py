#!/usr/bin/env python3
"""候補提案パイプライン — 1コマンドで「候補を出す → §3.3 で判定する → 台帳に積む」。

    python3 candidate_pipeline.py                # 既定（トークン上限200・GO 30件で停止）
    python3 candidate_pipeline.py --dry-run      # ネットワーク0・トークン0で計画だけ見る
    python3 candidate_pipeline.py --max-tokens 60 --limit 5
    python3 candidate_pipeline.py --no-sheet     # シートに書かず標準出力だけ

社長指示（2026-09-30）
    「提案商品は2つだけでなく、出し続けて下さい。……ある程度提案が溜まってきたら、
      リサーチを止めて良いです。」

なので **止まる条件**を持たせています。台帳に「判定=GO かつ 確認方法=機械判定のみ」の行が
`GO_TARGET`（既定30）件たまったら、それ以上は探しません。人（カズヨ）の実画面確認が
追いついていないのに候補だけ積み上げても、社長の判断は1件も進みません。

判定は GO / NO-GO / **UNKNOWN** の3値。**UNKNOWN を GO に畳みません**（fail-closed）。
`確認方法` は必ず「機械判定のみ・実画面未確認」と書きます。§3.3 の実画面確認（Chrome＋
キーゾンでカート保持者を見る）は人の仕事で、このスクリプトはそこまでやりません。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD = HERE.parent / "24_カート保持者ガード"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(GUARD))

import candidate_sources as sources          # noqa: E402
import ledger_sheet                          # noqa: E402
import maker_direct                           # noqa: E402
import profit                                 # noqa: E402
import set_count                              # noqa: E402
from keepa_client import KeepaClient, KeepaError  # noqa: E402
from keepa_sellers import SellerNames         # noqa: E402
from verdict import (AMAZON_JP_SELLER_ID, FAIL, GO, NO_GO, PASS,  # noqa: E402
                     UNKNOWN, _live_new_offers, judge, judge_missing)

TICKET = "T-20260920-003"
COL_CART = ledger_sheet.COLUMNS.index("カートの販売元")

# ── 定数（README に説明あり。変えるのはここ1箇所）──────────────────────────
# 台帳にこの件数の「GO（機械判定のみ）」がたまったら、リサーチを止める。
GO_TARGET = 30

# 1回の実行で使ってよい Keepa トークンの上限。
# Keepa は毎分トークンが回復する契約（API €49）で、残高を使い切ると他の作業が止まります。
# 実測: product+offers=20 で **6トークン/ASIN**、セラー名が **1トークン/セラー**。
MAX_KEEPA_TOKENS_PER_RUN = 200

# 1 ASIN あたりの見積り（商品6 + セラー名 最大2社ぶん）。
TOKENS_PER_ASIN = 8

# オファー取得数の上限。ここを下げると §3.3 のチェック3が UNKNOWN になるので下げない。
OFFERS = 20
# ──────────────────────────────────────────────────────────────────────────

# 作業ファイル（Git 追跡外）。卸値・卸URL を含むのでここ以外に書かない。
WORK_DIR = (sources.REPO / "workspace/output/agent_output" / TICKET / "pipeline")
SELLER_CACHE = WORK_DIR / "seller_names.json"


def _n(v, suffix: str = "") -> str:
    """セルの値。無ければ「未確認」（空欄にしない＝§3.2）。"""
    if v is None or v == "":
        return ledger_sheet.UNKNOWN_CELL
    return f"{v}{suffix}"


def extract_facts(product: dict, cand: sources.Candidate) -> dict:
    """Keepa の product から、判定と採算に使う値だけ取り出す。

    列名から意味を推測せず、Keepa の公式フィールド名で取る
    （memory: knowledge_verify_field_semantics_not_names）。
    """
    st = product.get("stats") or {}
    cur = st.get("current") or []

    def at(i):
        v = cur[i] if isinstance(cur, list) and i < len(cur) else None
        return None if v in (None, -1) else v

    buybox = st.get("buyBoxPrice")
    sell = None
    for v in (buybox, at(1), at(0), cand.sell):     # BuyBox → 新品 → 本体 → プール
        if v and v > 0:
            sell = int(v)
            break

    fee_pct = product.get("referralFeePercent")
    if fee_pct in (None, -1):
        fee_pct = product.get("referralFeePercentage")
    if fee_pct in (None, -1):
        fee_pct = cand.fee_pct

    fba = (product.get("fbaFees") or {}).get("pickAndPackFee")
    if fba in (None, -1, 0):
        fba = cand.fba_yen

    ms = product.get("monthlySold")
    if ms in (None, -1):
        ms = cand.monthly_sold

    live = _live_new_offers(product) or []
    seller_ids = [str(o.get("sellerId")) for o in live if o.get("sellerId")]

    return {
        "title": (product.get("title") or cand.title or "")[:120],
        "brand": product.get("brand") or cand.brand or "",
        "manufacturer": product.get("manufacturer") or "",
        "sell": sell,
        "fee_pct": fee_pct,
        "fba_yen": fba,
        "monthly_sold": ms,
        "cart_seller_id": st.get("buyBoxSellerId"),
        "live_offer_count": len(live),
        "seller_ids": seller_ids,
        "rank": at(3),
    }


# 回転の上限。これを超える在庫は社長既定で「生成も提示もしない」（6ヶ月）。
MAX_MONTHS_TO_SELL = 6.0


def economics_status(econ, monthly_sold, set_note: str = "") -> tuple[str, str]:
    """採算のゲート。(status, reason) を返す。

    カートが第三者でも、**赤字**や**捌けない在庫**は提案してはいけません。
    月販が取れないものは「売れる根拠がない」ので GO にせず UNKNOWN に置きます
    （キーゾンの列は人が埋めます）。
    """
    if econ is None:
        return (UNKNOWN,
                "売価・手数料・FBA・原価のどれかが揃わず、採算を計算できません。"
                + (f" {set_note}" if set_note else ""))
    if econ.gross_per_unit <= 0:
        return (FAIL, f"1個粗利が {econ.gross_per_unit:,}円（赤字）です。")
    if econ.net_per_unit <= 0:
        # 販売手数料と FBA 配送代行だけでは黒字に見えても、保管料・納品送料・梱包資材
        # （実測206円/個）を引くと沈む棚。**社長は「利益が少なくても量で」と言っていますが、
        # マイナスは量を増やすほど損が増えます。**
        return (FAIL,
                f"1個粗利 {econ.gross_per_unit:,}円から保管料・納品送料・梱包資材 "
                f"{econ.other_unit_costs}円を引くと手残り {econ.net_per_unit:,}円（実質赤字）です。")
    if not monthly_sold:
        # ⚠️ **月販が取れないことを理由に落とさない。**（2026-09-30 カズヨ訂正 / CLAUDE.md §3.1）
        # 社長は「最初は入口を多く持ちたい。利益が少なくても、量を増やせば何とかなる可能性が
        # あるかもしれない。やった後で評価し、継続判断を行う」と条件を緩めています。
        # `monthlySold` は月50個未満だと Amazon が表示しないだけで、「売れていない」ではありません
        # （社長が発注を決めた B0DJNX12KZ はキーゾン実測で月10個）。
        # 列には出す。しかしそれだけでは GO を止めない。
        return (PASS,
                f"1個粗利 {econ.gross_per_unit:,}円・利益率 {econ.margin_pct}%"
                f"（保管/納品/梱包 {econ.other_unit_costs}円を引いた手残り "
                f"{econ.net_per_unit:,}円・{econ.net_margin_pct}%）。"
                "月販は Keepa 非表示（月50個未満）で回転は未確認ですが、"
                "これだけでは落としません（キーゾンで実数を確認してください）。")
    if econ.months_to_sell and econ.months_to_sell > MAX_MONTHS_TO_SELL:
        # 月販が判っていて、なお最小ロットが大きすぎて捌けない場合だけ落とす。
        # これは「売れていない」ではなく「ロットが合わない」＝事実として動かせない制約です。
        return (FAIL,
                f"売り切るのに約{econ.months_to_sell}ヶ月かかります"
                f"（上限{MAX_MONTHS_TO_SELL:.0f}ヶ月・最小ロットが大きすぎる）。")
    return (PASS,
            f"1個粗利 {econ.gross_per_unit:,}円・利益率 {econ.margin_pct}%"
            f"（保管/納品/梱包 {econ.other_unit_costs}円を引いた手残り "
            f"{econ.net_per_unit:,}円・{econ.net_margin_pct}%）・"
            f"約{econ.months_to_sell}ヶ月で売り切る見込み。")


def combine(base_verdict: str, maker_status: str, econ_status: str = PASS) -> str:
    """§3.3 の3点チェック・5番目（メーカー直販）・採算ゲートを合成する。

    FAIL が1つでもあれば NO-GO、UNKNOWN が残れば UNKNOWN、全部 PASS で初めて GO。
    **UNKNOWN を GO に畳まない**のがこのパイプラインの芯です。
    """
    if base_verdict == NO_GO or maker_status == FAIL or econ_status == FAIL:
        return NO_GO
    if base_verdict == UNKNOWN or maker_status == UNKNOWN or econ_status == UNKNOWN:
        return UNKNOWN
    return GO


def prioritize(candidates: list) -> list:
    """判定する順番を決める。**月販が大きいものから**。

    社長の基準は「月100個以上売れている商品とその類似品」です
    （memory: feedback_volume_sellers_only）。月販が取れない棚は、このパイプラインでは
    どう転んでも UNKNOWN にしかならないので、後回しにします。
    トークンは有限なので、**同じ200トークンで GO が出やすい順**に使います。
    """
    def key(c):
        # 原価が判らない候補は、どう転んでも GO にならない（採算が計算できない）。
        # だから「月販も原価も判っているもの」を最優先にする。
        if c.monthly_sold and c.unit_cost_incl:
            tier = 0
        elif c.unit_cost_incl:
            tier = 1
        elif c.monthly_sold:
            tier = 2
        else:
            tier = 3
        return (tier, -(c.monthly_sold or 0))
    return sorted(candidates, key=key)


def build_row(cand: sources.Candidate, facts: dict, judgment, maker: tuple,
              econ, cart_seller_name: str | None, today: str,
              set_note: str = "") -> list:
    """32列ぶんのセルを作る。列の並びは ledger_sheet.COLUMNS のとおり。"""
    maker_status, maker_reason, _maker_ev = maker
    econ_status, econ_reason = economics_status(econ, facts.get("monthly_sold"), set_note)
    verdict = combine(judgment.verdict, maker_status, econ_status)

    check2 = next((c for c in judgment.checks if c.number == 2), None)
    instock = (check2.evidence.get("amazon_instock_365_pct") if check2 else None)
    check3 = next((c for c in judgment.checks if c.number == 3), None)
    sellers = (check3.evidence.get("distinct_sellers") if check3 else None)
    amazon_in = (check3.evidence.get("amazon_among_sellers") if check3 else None)

    amazon_presence = ledger_sheet.UNKNOWN_CELL
    if amazon_in is True:
        amazon_presence = "あり"
    elif amazon_in is False and instock is not None:
        amazon_presence = "あり" if instock > 0 else "なし"

    cart = judgment.cart_holder
    if cart_seller_name:
        cart = f"{cart_seller_name}（{facts.get('cart_seller_id')}）"
    if maker_status == FAIL:
        cart += "＝メーカー本人/ブランド公式の疑い"

    reasons = [f"{c.number}. {c.reason}" for c in judgment.checks if c.status != PASS]
    if maker_status != PASS:
        reasons.append(f"5. {maker_reason}")
    if econ_status != PASS:
        reasons.append(f"採算. {econ_reason}")
    if set_note and "単品" not in set_note:
        reasons.append(f"単位. {set_note}")
    if not reasons:
        reasons = ([f"{c.number}. {c.reason}" for c in judgment.checks]
                   + [f"5. {maker_reason}", f"採算. {econ_reason}"])

    ms = facts.get("monthly_sold")
    return [
        today, TICKET, cand.asin, facts["title"], facts["brand"] or cand.brand,
        f"https://www.amazon.co.jp/dp/{cand.asin}",
        _n(facts.get("sell")),
        (f"{ms}（Keepa monthlySold・キーゾン未確認）" if ms
         else "未確認（Keepa 非表示＝月50個未満）"),
        ledger_sheet.UNKNOWN_CELL, ledger_sheet.UNKNOWN_CELL, ledger_sheet.UNKNOWN_CELL,
        (f"{sellers}社（Keepa offers の実数・画面未確認）" if sellers is not None
         else ledger_sheet.UNKNOWN_CELL),
        amazon_presence,
        cart,
        # 「本体365日在庫率」= 本体が在庫を持っていた期間の割合。0% なら1年間ずっと不在。
        f"{instock}%" if instock is not None else ledger_sheet.UNKNOWN_CELL,
        ledger_sheet.UNKNOWN_CELL,                 # ゲート種別（実機確認は人）
        ledger_sheet.UNKNOWN_CELL,                 # ゲート可否
        cand.supplier or ledger_sheet.UNKNOWN_CELL,
        "NETSEA" if cand.supplier_url else ledger_sheet.UNKNOWN_CELL,
        cand.supplier_url or ledger_sheet.UNKNOWN_CELL,      # ※シート限定
        f"{econ.cost_ratio_pct}%" if econ else ledger_sheet.UNKNOWN_CELL,
        _n(econ.qty if econ else None),
        _n(econ.order_total if econ else None),
        _n(econ.gross_per_unit if econ else None),
        _n(econ.margin_pct if econ else None),
        _n(econ.months_to_sell if econ else None),
        _n(econ.half_disposal_loss if econ else None),
        verdict,
        " ／ ".join(reasons)[:1000],
        ledger_sheet.MACHINE_ONLY,
        "タカシ（candidate_pipeline.py）",
        "未発注（提案のみ・社長判断前）",
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="候補提案パイプライン（CLAUDE.md §3.2・§3.3）")
    ap.add_argument("--max-tokens", type=int, default=MAX_KEEPA_TOKENS_PER_RUN,
                    help=f"1回の実行で使う Keepa トークンの上限（既定 {MAX_KEEPA_TOKENS_PER_RUN}）")
    ap.add_argument("--go-target", type=int, default=GO_TARGET,
                    help=f"台帳の GO（機械判定のみ）がこの件数に達したら停止（既定 {GO_TARGET}）")
    ap.add_argument("--limit", type=int, help="判定する ASIN 数の上限（トークン上限より優先）")
    ap.add_argument("--asins", nargs="*", default=[], help="ASIN を直接指定（プールを使わない）")
    ap.add_argument("--order", choices=("volume", "pool"), default="volume",
                    help="判定する順番。volume=月販が大きいものから（既定）／pool=プールの並び順")
    ap.add_argument("--dry-run", action="store_true", help="ネットワークに触らず計画だけ出す")
    ap.add_argument("--no-sheet", action="store_true", help="シートに書かない")
    ap.add_argument("--no-netsea", action="store_true", help="NETSEA の卸値引き直しをしない")
    ap.add_argument("--update-existing", action="store_true",
                    help="台帳に既にある ASIN も再判定して行を上書きする")
    ap.add_argument("--out-json", type=Path, help="判定の根拠を JSON で保存（agent_output 限定）")
    args = ap.parse_args(argv)

    today = date.today().isoformat()
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 台帳の現況を読む（＝停止条件と冪等性の土台）
    state = None
    if not args.no_sheet:
        state = ledger_sheet.read_state()
        print(f"台帳: {state.total_rows}行 / GO（機械判定のみ）{state.machine_go_count}件 "
              f"/ 目標 {args.go_target}件", file=sys.stderr)
        if state.machine_go_count >= args.go_target:
            print(f"目標到達: GO（機械判定のみ）が {state.machine_go_count}件 "
                  f"≧ {args.go_target}件。リサーチを止めます。"
                  f"実画面確認（Chrome＋キーゾン）へ引き継いでください。 {ledger_sheet.sheet_url()}")
            return 0

    # 2. 候補を集めて、まだ判定していないものに絞る
    pool = sources.load_pool()
    if args.asins:
        # ⚠️ ASIN を直接指定しても **プールの卸値・手数料は引き継ぐ**。
        # 引き継がないと採算が計算できず、GO だった行を UNKNOWN に落として上書きします
        # （2026-09-30 に一度やって、GO 20件を消しました）。
        by_asin = {c.asin: c for c in pool}
        pool = [by_asin.get(a) or sources.Candidate(asin=a, source="--asins")
                for a in args.asins]
    known = set(state.asins) if state and not args.update_existing else set()
    remaining = [c for c in pool if c.asin not in known]
    if args.order == "volume":
        remaining = prioritize(remaining)
    have_ms = sum(1 for c in remaining if c.monthly_sold)
    print(f"プール {len(pool)}件 → 未判定 {len(remaining)}件"
          f"（うち月販が判っているもの {have_ms}件・この順に判定します）", file=sys.stderr)
    if not remaining:
        print("未判定の候補がプールに残っていません。"
              "NETSEA からの新規 ASIN 発掘（README §次にやること）が必要です。")
        return 0

    # 3. トークン上限で今回の件数を決める
    by_budget = max(0, args.max_tokens) // TOKENS_PER_ASIN
    take = min(len(remaining), by_budget, args.limit or 10**9)
    batch = remaining[:take]
    est = len(batch) * TOKENS_PER_ASIN
    print(f"今回判定: {len(batch)}件 / トークン見積り 約{est}"
          f"（上限 {args.max_tokens}・{TOKENS_PER_ASIN}/ASIN）", file=sys.stderr)
    if args.dry_run or not batch:
        for c in batch:
            print(f"  {c.asin}  {c.title[:48]}  [{c.source}]")
        return 0

    # 4. NETSEA で卸値を今の値に引き直す（Keepa トークン0）
    fresh = {}
    if not args.no_netsea:
        fresh = sources.refresh_wholesale_from_netsea(batch)
        if fresh.get("_error"):
            print(f"NETSEA: {fresh['_error']}（プールの卸値を使います）", file=sys.stderr)

    # 5. Keepa で §3.3 に必要な項目を取る
    try:
        res = KeepaClient().fetch_for_cart_check([c.asin for c in batch], offers=OFFERS)
    except KeepaError as e:
        print(f"Keepa エラー: {e}", file=sys.stderr)
        return 2
    by_asin = {p.get("asin"): p for p in res.products}
    (WORK_DIR / "last_raw.json").write_text(
        json.dumps({"products": res.products, "_offers_requested": res.offers_requested},
                   ensure_ascii=False), encoding="utf-8")

    # 6. セラー名を解決（メーカー直販の検出に必要）
    names = SellerNames(SELLER_CACHE)
    want: list[str] = []
    for c in batch:
        p = by_asin.get(c.asin)
        if not p:
            continue
        f = extract_facts(p, c)
        cart_id = str(f["cart_seller_id"] or "")
        if cart_id and not cart_id.startswith("-") and cart_id != AMAZON_JP_SELLER_ID:
            want.append(cart_id)
        if f["live_offer_count"] == 1:
            want += f["seller_ids"]
    seller_budget = max(0, args.max_tokens - res.tokens_consumed)
    try:
        resolved = names.resolve(want, budget=seller_budget)
    except KeepaError as e:
        print(f"セラー名の取得に失敗（メーカー直販判定は UNKNOWN になります）: {e}",
              file=sys.stderr)
        resolved = {}

    # 7. 判定して行を作る
    rows, details = [], []
    tally = {GO: 0, NO_GO: 0, UNKNOWN: 0}
    for c in batch:
        p = by_asin.get(c.asin)
        if not p:
            j = judge_missing(c.asin)
            facts = {"title": c.title, "brand": c.brand, "manufacturer": "", "sell": c.sell,
                     "fee_pct": c.fee_pct, "fba_yen": c.fba_yen,
                     "monthly_sold": c.monthly_sold, "cart_seller_id": None,
                     "live_offer_count": None, "seller_ids": [], "rank": None}
            maker = (UNKNOWN, "Keepa が商品を返さず、セラー名も取れませんでした。", {})
            cart_name = None
        else:
            j = judge(p, res.offers_requested)
            facts = extract_facts(p, c)
            cart_id = str(facts["cart_seller_id"] or "")
            cart_name = ("Amazon.co.jp" if cart_id == AMAZON_JP_SELLER_ID
                         else resolved.get(cart_id))
            others = [resolved[s] for s in facts["seller_ids"] if s in resolved]
            maker = maker_direct.detect_maker_direct(
                facts["brand"], facts["manufacturer"], cart_name,
                facts["live_offer_count"], others)

        # 卸値: NETSEA の今の値 → プールの値
        unit_cost, pack = c.unit_cost_incl, c.pack
        fj = fresh.get(c.jan) if isinstance(fresh, dict) else None
        if isinstance(fj, dict) and fj.get("unit_price_excl"):
            unit_cost = profit.unit_cost_incl_tax(fj["unit_price_excl"])
            pack = fj.get("min_lot_units") or pack     # 卸はこの倍数でしか売らない

        # ⚠️ **単位を揃える。** 卸は「1点あたり」、Amazon は「N点セット」で売っている。
        # Amazon の1個が卸のN点なら原価はN倍（2026-09-30 カズヨが B0DJNX12KZ で発見）。
        multiplier, set_note = set_count.cost_multiplier(facts.get("title") or c.title)
        if multiplier is None:
            unit_cost = None                           # → 採算 UNKNOWN（人が見る）
        elif unit_cost:
            unit_cost = unit_cost * multiplier
            pack = set_count.order_lot_in_amazon_units(pack, multiplier)

        econ = None
        if unit_cost and facts.get("sell") and facts.get("fee_pct") and facts.get("fba_yen"):
            qty = profit.order_qty(facts.get("monthly_sold"), pack)
            econ = profit.compute(facts["sell"], facts["fee_pct"], facts["fba_yen"],
                                  unit_cost, qty, facts.get("monthly_sold"))

        row = build_row(c, facts, j, maker, econ, cart_name, today, set_note)
        rows.append(row)
        tally[row[ledger_sheet.COL_VERDICT]] += 1
        details.append({
            "asin": c.asin, "verdict": row[ledger_sheet.COL_VERDICT],
            "cart_holder": row[COL_CART],
            "base_verdict": j.verdict, "maker_direct": maker[0], "maker_reason": maker[1],
            "checks": [{"n": ch.number, "status": ch.status, "reason": ch.reason}
                       for ch in j.checks],
            "economics": econ.as_dict() if econ else None,
        })
        mark = {GO: "✅", NO_GO: "⛔", UNKNOWN: "❓"}[row[ledger_sheet.COL_VERDICT]]
        print(f"{mark} {c.asin} {facts['title'][:40]}")
        print(f"    カート保持者: {row[COL_CART]}")
        for ch in j.checks:
            print(f"    {ch.status[:1]} {ch.number}. {ch.reason}")
        print(f"    {maker[0][:1]} 5. {maker[1]}")
        es, er = economics_status(econ, facts.get("monthly_sold"), set_note)
        print(f"    {es[:1]} 採算. {er}")
        if "単品" not in set_note:
            print(f"    ! 単位. {set_note}")

    # 8. 台帳へ（冪等）
    written = 0
    if not args.no_sheet:
        ws = ledger_sheet.open_tab()
        new_rows = []
        for row in rows:
            asin = row[ledger_sheet.COL_ASIN]
            existing = state.asins.get(asin) if state else None
            if existing and args.update_existing:
                try:
                    ledger_sheet.update_row(existing, row, ws, state)
                    written += 1
                except ledger_sheet.HumanRowProtected as e:
                    print(f"上書きせず: {e}", file=sys.stderr)
            elif not existing:
                new_rows.append(row)
        written += ledger_sheet.append_rows(new_rows, ws)
        state = ledger_sheet.read_state(ws)

    if args.out_json:
        if "agent_output" not in str(args.out_json.resolve()):
            raise SystemExit("--out-json は agent_output 配下にしてください（PUBLIC リポ）。")
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(details, ensure_ascii=False, indent=2),
                                 encoding="utf-8")

    total_tokens = res.tokens_consumed + names.tokens_consumed
    go_now = state.machine_go_count if state else tally[GO]
    print(f"\n新規判定 {len(rows)}件・GO {tally[GO]}件・NO-GO {tally[NO_GO]}件・"
          f"UNKNOWN {tally[UNKNOWN]}件／台帳書き込み {written}行／"
          f"累計GO {go_now}件／{args.go_target}／消費トークン {total_tokens}"
          f"（商品 {res.tokens_consumed}＋セラー名 {names.tokens_consumed}、残 {res.tokens_left}）")
    if state and state.machine_go_count >= args.go_target:
        print(f"目標到達: これ以上リサーチしません。{ledger_sheet.sheet_url()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
