"""仕入れせどり用｜Amazon売れ筋 × 仕入れ先 3000件リスト生成ハーネス v3。

T-20260803-001（社長: 電脳せどり→仕入れせどりへスイッチ／明日11時までに3000件超）。
実証済み density_scan_v2.py（T-20260705-001）を 3000件超へスケール。

パイプライン（プロの逆順＝Amazon起点）:
  1) Keepa Product Finder を16カテゴリ横断でページング → 売れ筋ニッチASINを大量抽出（目標4,500）
  2) 各ASINの詳細（価格/ランク/出品者数/月販/サイズ/JAN）を取得 →【まず全行をCSVへ】(=3000件の"リスト"を早期確定)
  3) JANで仕入れ先を逆引き最安（Yahoo!ショッピング + 楽天）
  4) calc.profit で純利益/利益率を算出 → 仕入れ条件合致フラグ（原石/持続/流動性）を付与
  5) CSVは逐次全書き換え（長時間走行でも結果が残る／途中で落ちても3000行は残る設計）

ナレッジ準拠の仕入れ条件:
  Finder = 中位ランク3,000〜80,000 / 出品者2〜10 / 価格1,000〜10,000円（PoiPoi標準の逆張りニッチ）
  原石 = 利益率≥8% かつ 純利益≥300円（朝野式緩和）
  持続 = 原石 + 相乗り2〜10 + 月販≥3
  流動性 = 持続 + Buy Box実在

Keepaトークンは20/分補充。MIN_TOKENS を割ったら自動スリープ→補充待ち。
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
DELIV_CODE = ROOT / "workspace/output/deliverables/T-20260521-005/code"
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(DELIV_CODE))
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.amazon_data import (KeepaBackend, _product_to_amazon,  # noqa: E402
                                  _keepa_price_yen)
from adapters.yahoo_shopping import YahooShoppingClient   # noqa: E402
from adapters.rakuten_shopping import RakutenShoppingClient  # noqa: E402
from discovery.presets import AMAZON_CATEGORIES, get_finder_preset  # noqa: E402
from calc.profit import ProfitInput, calculate  # noqa: E402

OUT = ROOT / "workspace/output/deliverables/T-20260803-001"
OUT.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT / "shiire_list_3000.csv"
SUMMARY_PATH = OUT / "shiire_summary.json"
PROG = OUT / "scan_v3_progress.log"

# ---- カテゴリ配分（16カテゴリ・目標ASIN合計 ~4,500）----
# 大きい棚を厚めに。詳細取得・JAN欠落での目減りを見込んで3,000行を安全に超える母集団を確保。
ALLOC = {
    "home_kitchen": 450, "drugstore": 400, "beauty": 350, "food": 300,
    "diy_tools": 350, "pet": 300, "toys": 300, "hobby": 300,
    "sports": 250, "office": 250, "baby": 250, "appliances": 250,
    "pc": 200, "car": 200, "instruments": 150, "industrial": 150,
}
FINDER_PAGES_MAX = 20        # 1カテゴリあたり最大ページ数（50件/ページ）
INBOUND = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
OTHER_COSTS = 150
MIN_TOKENS = 120            # これを割ったら補充待ち
DETAIL_CHUNK = 90          # 詳細取得のバッチサイズ
# 仕入れ条件（朝野式緩和・ナレッジ準拠）
MARGIN_MIN = 0.08
NET_MIN = 300
MSALES_MIN = 3

FIELDS = ["rank_no", "asin", "category", "jan", "name",
          "amazon_price", "buybox", "sales_rank", "offer_count", "monthly_sales",
          "size", "buy", "buy_source", "net", "margin_pct", "roi_pct",
          "verdict", "gem", "durable", "amazon_url", "supplier_hint"]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(PROG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_tokens(kb, need=MIN_TOKENS):
    import requests
    while True:
        try:
            d = requests.get(f"https://api.keepa.com/token?key={kb.api_key}&domain=5", timeout=30).json()
        except Exception:
            time.sleep(10); continue
        left = d.get("tokensLeft", 0)
        if left >= need:
            return left
        rate = d.get("refillRate") or 20
        wait = min(max((need - left) / rate * 60, 15), 300)
        log(f"  トークン補充待ち: left={left} need={need} → {wait:.0f}秒")
        time.sleep(wait)


def finder_asins(kb, preset, cat_id, target):
    got = []
    for page in range(FINDER_PAGES_MAX):
        if len(got) >= target:
            break
        wait_tokens(kb, need=60)
        sel = preset.to_selection([cat_id])
        sel["page"] = page
        sel["perPage"] = 50
        try:
            asins = kb._fetch_finder_asins(sel)
        except Exception as e:
            log(f"    finder err p{page}: {e}"); time.sleep(5); continue
        if not asins:
            break
        got.extend(asins)
        time.sleep(0.25)
    return list(dict.fromkeys(got))[:target]


def resolve_details(kb, asins, rows, cat_map, write_cb):
    """ASIN群の詳細を取得し rows(list) を埋める。DETAIL_CHUNKごとに write_cb で全書き出し。"""
    i = 0
    seen = set()
    while i < len(asins):
        wait_tokens(kb)
        chunk = asins[i:i + DETAIL_CHUNK]
        i += DETAIL_CHUNK
        try:
            pay = kb._request(asin=",".join(chunk))
        except Exception as e:
            log(f"    detail err: {e}"); time.sleep(10); continue
        for prod in pay.get("products", []):
            ap = _product_to_amazon(prod)
            if ap is None or ap.asin in seen:
                continue
            seen.add(ap.asin)
            eans = [str(c) for c in (prod.get("eanList") or [])]
            if eans:
                ap.jan = eans[0]
            st = prod.get("stats") or {}
            bb = _keepa_price_yen(st.get("buyBoxPrice"))
            rows.append({
                "rank_no": len(rows) + 1,
                "asin": ap.asin, "category": cat_map.get(ap.asin, ""),
                "jan": ap.jan or "", "name": (ap.title or "")[:60],
                "amazon_price": ap.current_price, "buybox": bb,
                "sales_rank": ap.sales_rank, "offer_count": ap.offer_count,
                "monthly_sales": ap.monthly_sales, "size": ap.size_key,
                "buy": "", "buy_source": "", "net": "", "margin_pct": "",
                "roi_pct": "", "verdict": "", "gem": False, "durable": False,
                "amazon_url": f"https://www.amazon.co.jp/dp/{ap.asin}",
                "supplier_hint": "",
            })
        log(f"  詳細 {min(i,len(asins))}/{len(asins)} 取得 累計行={len(rows)} tokensLeft={pay.get('tokensLeft')}")
        write_cb(rows)
        time.sleep(0.2)


def reverse_lookup(yahoo, rakuten, jan):
    best = None; src = ""
    for cli, name in ((yahoo, "Yahoo"), (rakuten, "楽天")):
        for attempt in range(3):
            try:
                hits = cli.search(jan_code=jan, results=5)
                for it in hits:
                    if it.price and it.price > 0:
                        if best is None or it.price < best:
                            best = it.price; src = name
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep(6 * (attempt + 1)); continue
                break
        time.sleep(0.35)
    return best, src


def write_csv(rows):
    tmp = CSV_PATH.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(CSV_PATH)


def main():
    if PROG.exists():
        PROG.unlink()
    preset = get_finder_preset("finder_genseki_beginner")
    kb = KeepaBackend()
    yahoo = YahooShoppingClient()
    rakuten = RakutenShoppingClient()
    log(f"起動 v3: Yahoo={yahoo.is_live} 楽天={rakuten.is_live} Keepa={kb.is_live}")
    log(f"Finder条件: ランク{preset.sales_rank_gte}-{preset.sales_rank_lte} "
        f"出品者{preset.count_new_gte}-{preset.count_new_lte} "
        f"価格{preset.price_gte}-{preset.price_lte}円 目標ASIN計={sum(ALLOC.values())}")

    # Phase1: Finderで条件合致ASINを大量抽出
    cat_map = {}
    for ckey, tgt in ALLOC.items():
        cat = AMAZON_CATEGORIES.get(ckey)
        if not cat:
            continue
        got = finder_asins(kb, preset, cat.category_id, tgt)
        for a in got:
            cat_map.setdefault(a, ckey)
        log(f"[Finder] {ckey}: {len(got)}件 (累計ASIN {len(cat_map)}) tokensLeft={kb.last_tokens_left}")
    asin_list = list(cat_map.keys())
    log(f"=== Phase1完了: 条件合致ASIN {len(asin_list)}件 ===")

    # Phase2: 詳細取得 → 全行を早期にCSVへ（3000件のリストを先に確定）
    rows = []
    resolve_details(kb, asin_list, rows, cat_map, write_csv)
    write_csv(rows)
    log(f"=== Phase2完了: リスト {len(rows)}行を確定・CSV出力済 ===")

    # Phase3: 仕入れ先逆引き＋利益判定（逐次CSV更新）
    n_jan = n_matched = n_gem = n_durable = 0
    cat_stat = {}
    for idx, row in enumerate(rows, 1):
        ck = row["category"]
        cat_stat.setdefault(ck, {"rows": 0, "matched": 0, "gem": 0})
        cat_stat[ck]["rows"] += 1
        jan = row["jan"]
        if jan:
            n_jan += 1
            buy, src = reverse_lookup(yahoo, rakuten, jan)
            if buy:
                n_matched += 1
                cat_stat[ck]["matched"] += 1
                size = row["size"] or "standard_1"
                ap_price = row["amazon_price"] or 0
                try:
                    r = calculate(ProfitInput(
                        wholesale_price=buy, amazon_price=ap_price,
                        category_key="default", size_key=size,
                        inbound_shipping=INBOUND.get(size, 250), other_costs=OTHER_COSTS,
                        wholesale_price_is_tax_included=True))
                except Exception:
                    r = None
                if r is not None:
                    offers = row["offer_count"] if row["offer_count"] is not None else 999
                    ms = row["monthly_sales"] or 0
                    gem = (r.net_profit >= NET_MIN and r.margin_rate >= MARGIN_MIN)
                    durable = gem and (2 <= offers <= 10) and ms >= MSALES_MIN
                    row.update({
                        "buy": buy, "buy_source": src, "net": round(r.net_profit),
                        "margin_pct": round(r.margin_rate * 100, 1),
                        "roi_pct": round(getattr(r, "roi", 0) * 100, 1),
                        "verdict": r.verdict, "gem": gem, "durable": durable,
                        "supplier_hint": f"{src}最安 JAN={jan}",
                    })
                    if gem:
                        n_gem += 1; cat_stat[ck]["gem"] += 1
                    if durable:
                        n_durable += 1
        if idx % 50 == 0:
            write_csv(rows)
            log(f"  逆引き {idx}/{len(rows)} | JAN有{n_jan} 突合{n_matched} 原石{n_gem} 持続{n_durable}")
    write_csv(rows)

    summary = {
        "ticket": "T-20260803-001",
        "method": "Amazon起点(Keepa Product Finder 16cat) → JAN逆引き(Yahoo+楽天) → 利益判定",
        "finder_filter": f"rank{preset.sales_rank_gte}-{preset.sales_rank_lte}/"
                         f"offers{preset.count_new_gte}-{preset.count_new_lte}/"
                         f"price{preset.price_gte}-{preset.price_lte}",
        "criteria": f"原石=率≥{MARGIN_MIN*100:.0f}%&利益≥{NET_MIN}円 / 持続=+相乗り2-10&月販≥{MSALES_MIN}",
        "asin_found": len(asin_list),
        "list_rows": len(rows),
        "has_jan": n_jan,
        "supplier_matched": n_matched,
        "gem_tier1": n_gem,
        "durable_tier2": n_durable,
        "match_rate_pct": round(n_matched / len(rows) * 100, 1) if rows else 0,
        "by_category": cat_stat,
        "tokens_left": kb.last_tokens_left,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=== 完了 ===")
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
