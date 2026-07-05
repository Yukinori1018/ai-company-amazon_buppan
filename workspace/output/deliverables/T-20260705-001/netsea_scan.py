"""NETSEA卸起点の原石密度＋JAN網羅率の実測（T-20260705-001 二本目）。

卸(NETSEA)は「構造的な差」が出やすいと言われる本命経路。ただし機械突合には
JANが要る。まず「卸商品のうちJANが付く割合」を測り（AI発見の可否そのもの）、
JAN付き商品をKeepaでAmazon突合して黒字差・持続の歩留まりを出す。
卸価格は税抜B2B価格として扱う（税込換算はエンジンに任せる）。
"""
import csv
import os
import sys
import time
from pathlib import Path

CODE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260521-005/code")
sys.path.insert(0, str(CODE))
ENGINE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/code")
sys.path.insert(0, str(ENGINE))
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.netsea import NetseaClient          # noqa: E402
from adapters.amazon_data import KeepaBackend      # noqa: E402
from calc.profit import ProfitInput, calculate     # noqa: E402

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260705-001")
INBOUND = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
OTHER_COSTS = 150
N_SUPPLIERS = 30          # 舐めるサプライヤー数
ITEMS_PER_SUPPLIER = 40   # 各サプライヤーの取得上限
MAX_RESOLVE = 300         # Keepa解決上限
MIN_TOKENS = 200


def main():
    nc = NetseaClient()
    assert nc.is_live
    sup = nc.list_suppliers()
    print(f"承認サプライヤー総数: {len(sup)}")
    total_items = 0
    with_jan = {}
    for s in sup[:N_SUPPLIERS]:
        try:
            items, cov = nc.list_supplier_items(s["id"], max_items=ITEMS_PER_SUPPLIER)
        except Exception as e:
            print(f"[warn] supplier {s['id']}: {e}")
            continue
        total_items += len(items)
        for it in items:
            if it.jan:
                prev = with_jan.get(it.jan)
                if prev is None or it.price < prev["price"]:
                    with_jan[it.jan] = {"jan": it.jan, "price": it.price,
                                        "name": it.name, "store": it.store}
        time.sleep(0.15)
    cov_pct = len(with_jan) / total_items * 100 if total_items else 0
    print(f"取得商品総数: {total_items} / JAN付きユニーク: {len(with_jan)} (JAN網羅率≈{cov_pct:.1f}%)")

    jans = list(with_jan.keys())[:MAX_RESOLVE]
    kb = KeepaBackend()
    rows = []
    i = 0
    while i < len(jans):
        chunk = jans[i:i + 10]
        i += 10
        try:
            res = kb.resolve_many(chunk)
        except Exception as e:
            print(f"[warn] keepa: {e}")
            break
        for jan, ap in res.items():
            src = with_jan[jan]
            size = ap.size_key or "standard_1"
            inp = ProfitInput(
                wholesale_price=src["price"], amazon_price=ap.current_price or 0,
                category_key=ap.category_key or "default", size_key=size,
                inbound_shipping=INBOUND.get(size, 250), other_costs=OTHER_COSTS,
                wholesale_price_is_tax_included=False,  # 卸は税抜
            )
            r = calculate(inp)
            offers = ap.offer_count if ap.offer_count is not None else 999
            msales = ap.monthly_sales if ap.monthly_sales is not None else 0
            t1 = r.verdict == "原石"
            t2 = t1 and offers <= 5 and msales >= 10
            rows.append({
                "jan": jan, "name": src["name"][:36], "buy_excl": src["price"],
                "amazon": ap.current_price, "asin": ap.asin,
                "net": round(r.net_profit), "margin": round(r.margin_rate * 100, 1),
                "verdict": r.verdict, "offers": offers, "msales": msales,
                "rank": ap.sales_rank, "tier1": t1, "tier2": t2,
            })
        if kb.last_tokens_left and kb.last_tokens_left < MIN_TOKENS:
            print(f"[stop] tokensLeft={kb.last_tokens_left}")
            break
        time.sleep(0.2)

    n = len(rows)
    t1 = sum(1 for x in rows if x["tier1"])
    t2 = sum(1 for x in rows if x["tier2"])
    pos = sum(1 for x in rows if x["net"] > 0)
    print("\n=== NETSEA卸起点 密度サマリ ===")
    print(f"JAN網羅率(卸)          : {cov_pct:.1f}% ({len(with_jan)}/{total_items})")
    print(f"Amazon突合成功 N       : {n}")
    print(f"Keepa残トークン        : {kb.last_tokens_left}")
    if n:
        print(f"黒字差(net>0)          : {pos} ({pos/n*100:.1f}%)")
        print(f"Tier1原石              : {t1} ({t1/n*100:.1f}%)")
        print(f"Tier2持続原石          : {t2} ({t2/n*100:.1f}%)")
    with open(OUT / "netsea_scan_results.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    print("\n[黒字だった卸商品]")
    for x in sorted([r for r in rows if r["net"] > 0], key=lambda x: -x["net"])[:12]:
        print(f"  net{x['net']:>6} 率{x['margin']:>5}% 相乗{x['offers']:>3} 月販{x['msales']:>4} buy{x['buy_excl']} amz{x['amazon']} | {x['name']}")
    import json
    (OUT / "netsea_summary.json").write_text(json.dumps({
        "supplier_sampled": min(N_SUPPLIERS, len(sup)), "total_items": total_items,
        "jan_unique": len(with_jan), "jan_coverage_pct": round(cov_pct, 1),
        "matched_N": n, "positive_gap": pos, "tier1": t1, "tier2": t2,
        "tokens_left": kb.last_tokens_left,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
