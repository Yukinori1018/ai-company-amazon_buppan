"""原石密度の実測ハーネス（T-20260705-001）。

問い: 電脳せどりは事業になるか＝「仕入れ値とAmazon価格の差で稼げる商品(原石)」が
      母集団のうちどれだけの割合(歩留まり率)で存在するかを、実接続で測る。

仕入れ側: Yahoo!ショッピング(JAN付・税込) / NETSEA卸(一部JAN)
Amazon側: Keepa(現在価格・ランク・相乗り出品者数・月販推定)
判定    : 実働エンジン calc/profit.py

数値はでっち上げない。取れたものだけ集計し、母集団と除外理由を正直に残す。
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

# .env 読み込み
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.amazon_data import KeepaBackend       # noqa: E402
from adapters.yahoo_shopping import YahooShoppingClient  # noqa: E402
from calc.profit import ProfitInput, calculate      # noqa: E402

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260705-001")

# 電脳せどりが狙う代表カテゴリを広く舐める（母集団の偏りを避ける）
KEYWORDS = [
    "水筒 ステンレス", "タンブラー 保温", "キッチン 収納 ラック", "調理器具 セット",
    "美容 スチーマー", "ヘアアイロン", "電動歯ブラシ 替えブラシ", "制汗剤 デオドラント",
    "おもちゃ ブロック", "ボードゲーム", "文房具 ペン セット", "手帳 2026",
    "ペット 用品 猫", "犬 おやつ", "スポーツ ヨガマット", "アウトドア ランタン",
    "モバイルバッテリー", "LED ライト 卓上", "掃除 グッズ", "収納 ボックス 折りたたみ",
]

# 仕入れ→FBA納品の1個あたり送料按分（サイズ別）と共通経費
INBOUND = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
OTHER_COSTS = 150   # ラベル/資材/返品引当の按分
MAX_RESOLVE = 600   # Keepaで解決するJAN上限（トークン節約）
MIN_TOKENS = 200    # 残トークンがこれを割ったら停止
YAHOO_PER_KW = 50


def size_shipping(size_key):
    return INBOUND.get(size_key, 250)


def gather_yahoo():
    yc = YahooShoppingClient()
    assert yc.is_live, "Yahoo not live"
    by_jan = {}
    for kw in KEYWORDS:
        try:
            hits = yc.search(kw, results=YAHOO_PER_KW)
        except Exception as e:
            print(f"[warn] Yahoo '{kw}': {e}")
            continue
        for it in hits:
            if not it.jan:
                continue
            # 同一JANは最安の仕入れを採用（原石に有利＝実力を過小評価しない）
            prev = by_jan.get(it.jan)
            if prev is None or it.price < prev["price"]:
                by_jan[it.jan] = {"jan": it.jan, "price": it.price, "name": it.name,
                                  "source": "Yahoo", "url": it.url, "kw": kw,
                                  "point_rate": it.point_rate}
        print(f"[yahoo] '{kw}': {len(hits)} hits, cumulative JAN={len(by_jan)}")
        time.sleep(0.15)
    return by_jan


def main():
    print("=== 母集団収集(Yahoo) ===")
    universe = gather_yahoo()
    jans = list(universe.keys())[:MAX_RESOLVE]
    print(f"母集団(ユニークJAN)={len(universe)} / Keepa解決対象={len(jans)}")

    kb = KeepaBackend()
    assert kb.is_live, "Keepa not live"

    rows = []
    resolved = 0
    matched = 0
    i = 0
    while i < len(jans):
        chunk = jans[i:i + 10]
        i += 10
        try:
            res = kb.resolve_many(chunk)
        except Exception as e:
            print(f"[warn] Keepa chunk {i}: {e}")
            break
        resolved += len(chunk)
        for jan, ap in res.items():
            matched += 1
            src = universe[jan]
            price = src["price"]
            size = ap.size_key or "standard_1"
            inp = ProfitInput(
                wholesale_price=price, amazon_price=ap.current_price or 0,
                category_key=ap.category_key or "default", size_key=size,
                inbound_shipping=size_shipping(size), other_costs=OTHER_COSTS,
                wholesale_price_is_tax_included=True,
            )
            r = calculate(inp)
            # 値下げ耐性（Amazon価格×0.9で黒字か）
            stress = calculate(ProfitInput(
                wholesale_price=price, amazon_price=(ap.current_price or 0) * 0.9,
                category_key=ap.category_key or "default", size_key=size,
                inbound_shipping=size_shipping(size), other_costs=OTHER_COSTS,
            ))
            offers = ap.offer_count if ap.offer_count is not None else 999
            msales = ap.monthly_sales if ap.monthly_sales is not None else 0
            tier1 = r.verdict == "原石"
            tier2 = tier1 and offers <= 5 and msales >= 10
            tier3 = tier2 and stress.net_profit > 0
            rows.append({
                "jan": jan, "name": src["name"][:40], "source": src["source"],
                "buy": price, "amazon": ap.current_price, "asin": ap.asin,
                "category": ap.category_key, "size": size,
                "net_profit": round(r.net_profit), "margin_pct": round(r.margin_rate * 100, 1),
                "roi_pct": round(r.roi * 100, 1), "verdict": r.verdict,
                "offer_count": offers, "monthly_sales": msales,
                "sales_rank": ap.sales_rank, "oos90": ap.oos_rate_90d,
                "stress_net": round(stress.net_profit),
                "tier1": tier1, "tier2": tier2, "tier3": tier3, "kw": src["kw"],
            })
        if kb.last_tokens_left is not None and kb.last_tokens_left < MIN_TOKENS:
            print(f"[stop] tokensLeft={kb.last_tokens_left} < {MIN_TOKENS}")
            break
        time.sleep(0.2)

    # CSV 出力
    csv_path = OUT / "density_scan_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 集計
    n = len(rows)
    t1 = sum(1 for x in rows if x["tier1"])
    t2 = sum(1 for x in rows if x["tier2"])
    t3 = sum(1 for x in rows if x["tier3"])
    pos = sum(1 for x in rows if x["net_profit"] > 0)
    print("\n" + "=" * 60)
    print("原石密度の実測サマリ")
    print("=" * 60)
    print(f"母集団ユニークJAN(Yahoo)   : {len(universe)}")
    print(f"Keepa解決対象JAN           : {len(jans)}")
    print(f"Amazon突合成功(=分析対象N)  : {n}")
    print(f"Keepa残トークン            : {kb.last_tokens_left}")
    print("-" * 60)
    print(f"差が黒字(手数料引後 net>0) : {pos} ({pos/n*100:.1f}%)" if n else "N=0")
    print(f"Tier1 原石(率15%&利500)    : {t1} ({t1/n*100:.1f}%)" if n else "")
    print(f"Tier2 持続原石(+相乗り少回転): {t2} ({t2/n*100:.1f}%)" if n else "")
    print(f"Tier3 堅い原石(+値下げ耐性) : {t3} ({t3/n*100:.1f}%)" if n else "")
    print("-" * 60)
    if t2:
        gems = [x for x in rows if x["tier2"]]
        avg = sum(x["net_profit"] for x in gems) / len(gems)
        print(f"持続原石の平均純利益/個     : {avg:,.0f}円")
    # 上位を表示
    print("\n[Tier2以上の実物 上位10]")
    gems = sorted([x for x in rows if x["tier2"]], key=lambda x: -x["net_profit"])[:10]
    for g in gems:
        print(f"  {g['net_profit']:>6}円 率{g['margin_pct']:>4}% 相乗り{g['offer_count']:>2} 月販{g['monthly_sales']:>3} | {g['name']}")
    print(f"\nCSV: {csv_path}")
    # サマリを機械可読でも残す
    import json
    (OUT / "density_summary.json").write_text(json.dumps({
        "universe_jan": len(universe), "resolved_target": len(jans),
        "matched_N": n, "tokens_left": kb.last_tokens_left,
        "positive_gap": pos, "tier1": t1, "tier2": t2, "tier3": t3,
        "tier2_avg_profit": (sum(x["net_profit"] for x in rows if x["tier2"]) / t2) if t2 else 0,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
