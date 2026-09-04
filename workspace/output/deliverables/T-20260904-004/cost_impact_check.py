#!/usr/bin/env python3
"""経理ハジメの実測コストを入れると、既存の黒字判定がどう動くかを数える（T-20260904-004）。

走行中のスキャンには触りません（読むだけ・CSV も書き換えません）。
`out/keepa_facts.jsonl` に既に取れている JAN だけを対象に、
**旧前提と実測版で同じ行を計算し直して**、利益率の帯がどう動くかを出します。

なぜ 911MB の netsea_items.jsonl を全部展開しないか:
    段2 の全展開（1,714,571件）はメモリを食い、走行中のジョブと競合します。
    検証済みの JAN だけを拾う1パスなら軽く済みます。

使い方:
    python3 cost_impact_check.py
    python3 cost_impact_check.py --netsea-ship-per-order 1500   # 悲観シナリオ
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCAN_DIR = REPO / "workspace" / "output" / "deliverables" / "T-20260831-006"
for p in (str(SCAN_DIR),
          str(REPO / "workspace" / "output" / "deliverables" / "T-20260521-005" / "code")):
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline import config, evaluate, keepa_verify, screen, store  # noqa: E402
from calc import profit  # noqa: E402

FACTS = SCAN_DIR / "out" / "keepa_facts.jsonl"
ITEMS = SCAN_DIR / "out" / "netsea_items.jsonl"


def old_costs() -> config.CostAssumptions:
    """2026-09-04 より前の前提。**費目3つが抜けていた状態**を再現する。"""
    return config.CostAssumptions(
        closing_fee_yen=0.0,          # 小口プラン基本成約料が入っていなかった
        referral_fee_tax_rate=0.0,    # 販売手数料の消費税が入っていなかった
        prep_service_yen=0.0,         # 納品代行の作業費が入っていなかった
        fba_inbound_yen=100.0,        # 根拠のない概算
        storage_months=2.0,           # 二重に保守的だった
        return_rate=0.0,              # 旧モデルは「雑費 売価の3%」（下で足す）
    )


LEGACY_MISC_RATE = 0.03   # 旧「雑費」。売価連動にする経理的な根拠が無く廃止された


def evaluate_old(cand, facts, cfg) -> object:
    """旧モデルでの利益。evaluate() で骨格を作り、雑費3%だけ手で足し直す。"""
    ev = evaluate.evaluate(cand, facts, cfg)
    if ev.result is None:
        return ev
    misc = facts.price_yen * LEGACY_MISC_RATE
    ev.result = profit.calculate(
        profit.ProfitInput(
            wholesale_price=cand.wholesale_ex_tax * ev.pack_size,
            wholesale_price_is_tax_included=False,
            amazon_price=facts.price_yen,
            category_key=ev.category_key,
            size_key="standard_2" if ev.size_key == "unknown" else ev.size_key,
            inbound_shipping=ev.inbound_shipping,
            other_costs=ev.storage_fee + misc,
            referral_fee_tax_rate=0.0,
            threshold_margin_rate=cfg.min_margin_rate,
            threshold_net_profit_yen=cfg.min_net_profit,
        )
    )
    return ev


def load_candidates_for(jans: set) -> dict:
    """検証済み JAN に対応する Candidate を netsea_items.jsonl から1パスで拾う。

    同一 JAN を複数サプライヤーが扱う場合は**卸値の安い方**を採る
    （段2 の dedupe_by_jan と同じ考え方。ここで高い方を採ると赤字側に寄る）。
    """
    best = {}
    with open(ITEMS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue          # 電源断で途中まで書かれた行は読み飛ばす
            for c in screen.to_candidates(item):
                if c.jan in jans and c.wholesale_ex_tax > 0:
                    cur = best.get(c.jan)
                    if cur is None or c.wholesale_ex_tax < cur.wholesale_ex_tax:
                        best[c.jan] = c
    return best


def bands(evs: list) -> dict:
    out = {}
    for ev in evs:
        if ev.result is None:
            continue
        b = evaluate.margin_band(ev.result.margin_rate)
        out[b] = out.get(b, 0) + 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netsea-ship-per-order", type=int, default=0,
                    help="NETSEA送料を1発注あたりいくらで見るか（悲観シナリオは1500）")
    args = ap.parse_args()

    facts_rows = store.JsonlStore(FACTS, key="jan").load()
    print(f"検証済み JAN: {len(facts_rows)}件")

    cands = load_candidates_for(set(facts_rows))
    print(f"NETSEA 側の卸値と突合できたもの: {len(cands)}件")

    new_cfg = config.ScanConfig()
    old_cfg = config.ScanConfig(costs=old_costs())
    if args.netsea_ship_per_order:
        # 送料は注文単位。1発注10個の想定で按分する（推定であることを明示）。
        per_unit = args.netsea_ship_per_order / new_cfg.costs.netsea_ship_amortize_qty
        print(f"NETSEA送料を実費計上: {args.netsea_ship_per_order}円/発注 "
              f"→ {per_unit:.0f}円/点（{new_cfg.costs.netsea_ship_amortize_qty}個按分・推定）")

    new_evs, old_evs = [], []
    for jan, cand in cands.items():
        if args.netsea_ship_per_order:
            cand.ship_fee = args.netsea_ship_per_order
        f = keepa_verify.AmazonFacts(**{
            k: v for k, v in dict(facts_rows[jan],
                                  package_mm=tuple(facts_rows[jan].get("package_mm") or ()))
            .items() if k in keepa_verify.AmazonFacts.__dataclass_fields__})
        f.pack_size = keepa_verify.detect_pack_size(f.title)
        new_evs.append(evaluate.evaluate(cand, f, new_cfg))
        old_evs.append(evaluate_old(cand, f, old_cfg))

    ob, nb = bands(old_evs), bands(new_evs)
    keys = ["20%以上", "10〜20%", "5〜10%", "5%未満", "赤字"]
    print("\n利益率の帯（同じ行を、旧前提と実測版で計算し直したもの）")
    print(f"{'帯':<10}{'旧前提':>8}{'実測版':>8}{'差':>8}")
    for k in keys:
        o, n = ob.get(k, 0), nb.get(k, 0)
        print(f"{k:<10}{o:>8}{n:>8}{n - o:>+8}")

    op = sum(1 for e in old_evs if e.is_profitable)
    np_ = sum(1 for e in new_evs if e.is_profitable)
    print(f"\n黒字（純利益>0）  旧 {op}件 → 実測版 {np_}件（{np_ - op:+d}）")

    # 帯をまたいで落ちた行を数える。「何件が候補から外れたか」が社長の関心事。
    fell = sum(1 for o, n in zip(old_evs, new_evs)
               if o.is_profitable and not n.is_profitable)
    print(f"黒字から赤字に落ちた行: {fell}件")

    surv = [n for o, n in zip(old_evs, new_evs)
            if o.result and o.result.margin_rate >= 0.20]
    kept20 = sum(1 for n in surv if n.result and n.result.margin_rate >= 0.20)
    print(f"旧前提で「20%以上」だった {len(surv)}件のうち、実測版でも20%以上: {kept20}件")


if __name__ == "__main__":
    main()
