"""原石密度の実測ハーネス v2（T-20260705-001・2周目）。

サトルのナレッジ精査で判明した「プロの逆順」で測り直す：
  Amazon側でPoiPoi標準条件を先に絞る（Keepa Product Finder）
    → 各ASINのJANで仕入れ先(Yahoo+楽天)を逆引き最安
    → 差＋流動性(Buy Box)込みで原石判定。
前回(Yahooキーワード舐め235件)との違い＝母集団が「Amazonで既に売れる棚」に選別済み。

基準は朝野式に緩和：利益率≥8%・利益額≥300円・月販≥3（分母を最大化）。
Keepaトークンは補充20/分。tokensLeftが閾値を割ったら自動でスリープ→補充待ち。
途中結果は逐次CSVへ書き出し（長時間走行でも結果が残る）。
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

CODE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260521-005/code")
DELIV_CODE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/code")
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

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260705-001")
PROG = OUT / "scan_v2_progress.log"

# カテゴリ配分（サトル設計・計2,000）
ALLOC = {
    "home_kitchen": 300, "drugstore": 250, "diy_tools": 250,
    "pet": 200, "toys": 200, "hobby": 200,
    "sports": 150, "office": 150, "baby": 150, "appliances": 150,
}
INBOUND = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
OTHER_COSTS = 150
MIN_TOKENS = 120          # これを割ったら補充待ち
DETAIL_CHUNK = 50
# 基準緩和（朝野式）
MARGIN_MIN = 0.08
NET_MIN = 300
MSALES_MIN = 3


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(PROG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_tokens(kb, need=MIN_TOKENS):
    """tokensLeftがneedを割っていたら補充を待つ。"""
    import requests
    while True:
        try:
            d = requests.get(f"https://api.keepa.com/token?key={kb.api_key}", timeout=30).json()
        except Exception:
            time.sleep(10); continue
        left = d.get("tokensLeft", 0)
        if left >= need:
            return left
        rate = d.get("refillRate") or 20
        short = need - left
        wait = min(max(short / rate * 60, 15), 300)
        log(f"  トークン補充待ち: left={left} need={need} → {wait:.0f}秒スリープ")
        time.sleep(wait)


def finder_asins(kb, preset, cat_id, target):
    """Product FinderをページングしてASINを集める。"""
    got = []
    page = 0
    while len(got) < target and page < 60:
        sel = preset.to_selection([cat_id])
        sel["page"] = page
        sel["perPage"] = 50
        try:
            asins = kb._fetch_finder_asins(sel)
        except Exception as e:
            log(f"    finder err p{page}: {e}"); break
        if not asins:
            break
        got.extend(asins)
        page += 1
        time.sleep(0.3)
    return list(dict.fromkeys(got))[:target]


def resolve_details(kb, asins):
    """ASIN群の詳細を取得。(AmazonProduct, buybox_exists) を返す。"""
    out = {}
    i = 0
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
            if ap is None:
                continue
            eans = [str(c) for c in (prod.get("eanList") or [])]
            if eans:
                ap.jan = eans[0]
            st = prod.get("stats") or {}
            bb = _keepa_price_yen(st.get("buyBoxPrice"))
            out[ap.asin] = (ap, bb)
        left = pay.get("tokensLeft")
        log(f"  詳細 {min(i,len(asins))}/{len(asins)} 取得 tokensLeft={left}")
        time.sleep(0.2)
    return out


def confirm_buybox(kb, asins):
    """原石候補だけ buybox=1&offers=20 で Buy Box 実在＋新品出品数を確認（5tok/件）。"""
    import requests
    out = {}
    i = 0
    while i < len(asins):
        wait_tokens(kb, need=150)
        chunk = asins[i:i + 20]
        i += 20
        params = {"key": kb.api_key, "domain": 5, "asin": ",".join(chunk),
                  "stats": 90, "buybox": 1, "offers": 20}
        try:
            pay = requests.get("https://api.keepa.com/product", params=params, timeout=90).json()
        except Exception as e:
            log(f"    buybox err: {e}"); time.sleep(10); continue
        for prod in pay.get("products", []):
            st = prod.get("stats") or {}
            bb = _keepa_price_yen(st.get("buyBoxPrice"))
            cur = st.get("current") or []
            cnt_new = cur[11] if len(cur) > 11 else None
            out[prod.get("asin")] = {"buybox": bb, "count_new": cnt_new}
        log(f"  BuyBox確認 {min(i,len(asins))}/{len(asins)} tokensLeft={pay.get('tokensLeft')}")
        time.sleep(0.2)
    return out


def reverse_lookup(yahoo, rakuten, jan):
    """JANで仕入れ先最安を逆引き。(price, source, ok)。okはlookupが実行できたか。"""
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
        time.sleep(0.4)
    return best, src


def main():
    if PROG.exists():
        PROG.unlink()
    preset = get_finder_preset("finder_poipoi_standard")
    kb = KeepaBackend()
    yahoo = YahooShoppingClient()
    rakuten = RakutenShoppingClient()
    log(f"起動: Yahoo={yahoo.is_live} 楽天={rakuten.is_live} Keepa={kb.is_live}")
    log(f"Finder条件: ランク{preset.sales_rank_gte}-{preset.sales_rank_lte} 出品者{preset.count_new_gte}-{preset.count_new_lte} 価格{preset.price_gte}+ 本体在庫切れ={preset.require_amazon_oos}")

    # Phase1: Amazon側で条件抽出
    all_asins = {}   # asin -> category_key
    for ckey, tgt in ALLOC.items():
        cat = AMAZON_CATEGORIES[ckey]
        got = finder_asins(kb, preset, cat.category_id, tgt)
        for a in got:
            all_asins.setdefault(a, ckey)
        log(f"[Finder] {ckey}: {len(got)}件 (累計ASIN {len(all_asins)}) tokensLeft={kb.last_tokens_left}")
    asin_list = list(all_asins.keys())
    log(f"=== Phase1完了: 条件合致ASIN {len(asin_list)}件 ===")

    # Phase2: 詳細取得
    details = resolve_details(kb, asin_list)
    log(f"=== Phase2完了: 詳細取得 {len(details)}件 ===")

    # Phase3: 逆引き＋判定（逐次CSV）
    fields = ["asin", "category", "jan", "amazon_price", "buybox", "sales_rank",
              "offer_count", "monthly_sales", "size", "buy", "buy_source",
              "net", "margin_pct", "verdict", "gem", "durable", "liquid", "name"]
    csv_path = OUT / "density_v2_results.csv"
    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader()

    n_detail = len(details)
    n_jan = 0; n_matched = 0; n_gem = 0; n_durable = 0; n_liquid = 0
    cat_stat = {}
    done = 0
    gem_rows = {}   # asin -> row（原石候補のみ。後でBuyBox確認）
    for asin, (ap, bb) in details.items():
        done += 1
        ck = all_asins.get(asin, "")
        cat_stat.setdefault(ck, {"detail": 0, "matched": 0, "gem": 0})
        cat_stat[ck]["detail"] += 1
        row = {"asin": asin, "category": ck, "jan": ap.jan or "",
               "amazon_price": ap.current_price, "buybox": bb,
               "sales_rank": ap.sales_rank, "offer_count": ap.offer_count,
               "monthly_sales": ap.monthly_sales, "size": ap.size_key,
               "buy": "", "buy_source": "", "net": "", "margin_pct": "",
               "verdict": "", "gem": False, "durable": False, "liquid": False,
               "name": (ap.title or "")[:36]}
        if ap.jan:
            n_jan += 1
            buy, src = reverse_lookup(yahoo, rakuten, ap.jan)
            if buy:
                n_matched += 1
                cat_stat[ck]["matched"] += 1
                size = ap.size_key or "standard_1"
                r = calculate(ProfitInput(
                    wholesale_price=buy, amazon_price=ap.current_price or 0,
                    category_key=ap.category_key or "default", size_key=size,
                    inbound_shipping=INBOUND.get(size, 250), other_costs=OTHER_COSTS,
                    wholesale_price_is_tax_included=True))
                offers = ap.offer_count if ap.offer_count is not None else 999
                ms = ap.monthly_sales or 0
                gem = (r.net_profit >= NET_MIN and r.margin_rate >= MARGIN_MIN)
                durable = gem and 2 <= offers <= 10 and ms >= MSALES_MIN
                liquid = durable and (bb is not None)
                row.update({"buy": buy, "buy_source": src, "net": round(r.net_profit),
                            "margin_pct": round(r.margin_rate * 100, 1),
                            "verdict": r.verdict, "gem": gem, "durable": durable,
                            "liquid": liquid})
                if gem:
                    n_gem += 1; cat_stat[ck]["gem"] += 1
                    gem_rows[asin] = row
                if durable:
                    n_durable += 1
        w.writerow(row)
        if done % 25 == 0:
            f.flush()
            log(f"  逆引き {done}/{n_detail} | JAN有{n_jan} 突合{n_matched} 原石{n_gem} 持続{n_durable}")
    f.close()

    # Phase4: 原石候補だけ Buy Box 実在を確認（流動性の正しい測定）
    log(f"=== Phase4: 原石{len(gem_rows)}件のBuyBox確認 ===")
    bbmap = confirm_buybox(kb, list(gem_rows.keys())) if gem_rows else {}
    gpath = OUT / "density_v2_gems_liquidity.csv"
    gf = open(gpath, "w", newline="", encoding="utf-8")
    gw = csv.DictWriter(gf, fieldnames=list(next(iter(gem_rows.values())).keys()) + ["bb_confirmed", "count_new_confirmed"]) if gem_rows else None
    if gw:
        gw.writeheader()
    for asin, row in gem_rows.items():
        info = bbmap.get(asin, {})
        bb = info.get("buybox")
        row["liquid"] = bool(row.get("durable")) and (bb is not None and bb > 0)
        if row["liquid"]:
            n_liquid += 1
        out_row = dict(row)
        out_row["bb_confirmed"] = bb
        out_row["count_new_confirmed"] = info.get("count_new")
        if gw:
            gw.writerow(out_row)
    gf.close()

    # サマリ
    summary = {
        "method": "Amazon-first (Keepa Product Finder PoiPoi標準) → JAN逆引き(Yahoo+楽天)",
        "finder_filter": f"rank{preset.sales_rank_gte}-{preset.sales_rank_lte}/offers{preset.count_new_gte}-{preset.count_new_lte}/price{preset.price_gte}+/AmazonOOS",
        "criteria": f"原石=率≥{MARGIN_MIN*100:.0f}%&利益≥{NET_MIN}円 / 持続=+相乗り2-10&月販≥{MSALES_MIN} / 流動性=+BuyBox実在",
        "asin_found": len(asin_list), "detailed": n_detail,
        "has_jan": n_jan, "supplier_matched": n_matched,
        "gem_tier1": n_gem, "durable_tier2": n_durable, "liquid_tier3": n_liquid,
        "match_rate_pct": round(n_matched / n_detail * 100, 1) if n_detail else 0,
        "gem_rate_of_matched_pct": round(n_gem / n_matched * 100, 1) if n_matched else 0,
        "durable_rate_of_matched_pct": round(n_durable / n_matched * 100, 1) if n_matched else 0,
        "liquid_rate_of_matched_pct": round(n_liquid / n_matched * 100, 1) if n_matched else 0,
        "by_category": cat_stat,
        "tokens_left": kb.last_tokens_left,
    }
    (OUT / "density_v2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=== 完了 ===")
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
