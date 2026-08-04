"""メーカー仕入れせどり｜Amazon売れ筋メーカー抽出ハーネス（Phase A・T-20260804-001）。

ナレッジ3基準（EC STARs/中西）:
  ①Amazon本体が出品していない（Keepa current_AMAZON=-1）
  ②FBAライバルセラー2人以上（current_COUNT_NEW>=2）
  ③ランキング 50,000〜150,000位（社長修正）
中小メーカー狙い・規制カテゴリ除外（医薬品/化粧品/食品）。

流れ: Keepa Product Finder(多カテゴリ) → 詳細取得 → raw から brand/manufacturer 直読み
      → 利益から想定仕入価格を逆算 → 商品行CSV + メーカー名寄せCSV。
連絡先(電話/メール)は Phase B(Web) で付与するため本スクリプトでは空欄。
"""
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
sys.path.insert(0, str(CODE))
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.amazon_data import KeepaBackend, _product_to_amazon  # noqa: E402
from calc.profit import ProfitInput, calculate  # noqa: E402
from calc import fees  # noqa: E402

OUT = ROOT / "workspace/output/deliverables/T-20260804-001"
OUT.mkdir(parents=True, exist_ok=True)
PROD_CSV = OUT / "maker_products.csv"
MAKER_CSV = OUT / "maker_ledger.csv"
SUMMARY = OUT / "maker_summary.json"
PROG = OUT / "maker_scan_progress.log"

# 規制カテゴリ(医薬品/化粧品/食品)を除いた対象カテゴリ。各fee_categoryも指定。
CATS = {
    "home_kitchen": (3828871, "home_kitchen"), "office": (86731051, "office"),
    "pet": (2127212051, "pet"), "toys": (13299531, "toys"),
    "sports": (14304371, "sports"), "diy_tools": (2016929051, "diy"),
    "appliances": (3210981, "electronics"), "pc": (2127209051, "pc"),
    "baby": (344845011, "default"), "car": (2017304051, "default"),
    "hobby": (2277721051, "toys"), "instruments": (2123629051, "default"),
    "industrial": (3445393051, "default"),
}
TARGET_PER_CAT = 400          # カテゴリ毎ASIN目標
FINDER_PAGES_MAX = 16
DETAIL_CHUNK = 90
MIN_TOKENS = 120
RANK_LO, RANK_HI = 50000, 150000
PRICE_LO, PRICE_HI = 1500, 30000
INBOUND = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
OTHER_COSTS = 100             # 梱包外注(WAM NET 5-10円)+ラベル+資材+返品引当のざっくり
TARGET_MARGIN = 0.25          # 想定仕入価格＝この純利益率になる税込上限

# 大手/海外の可能性フラグ用（除外はせず注記）。
BIG_HINTS = re.compile(r"(SONY|ソニー|Panasonic|パナソニック|東芝|TOSHIBA|日立|SHARP|シャープ|"
                       r"Nike|ナイキ|adidas|アディダス|Apple|Anker|アンカー|Logicool|Logitech|"
                       r"Canon|Nikon|Bandai|バンダイ|TAKARA|タカラトミー|Coca|サントリー|"
                       r"任天堂|Nintendo|BUFFALO|バッファロー|ELECOM|エレコム|Philips|フィリップス)", re.I)
NG_TITLE = re.compile(r"(DVD|Blu-?ray|ブルーレイ|CD|アダルト|18禁|成人)", re.I)

PROD_FIELDS = ["asin", "name", "category", "amazon_price", "buy_target_incl",
               "net_at_target", "margin_pct", "manufacturer", "brand",
               "monthly_sales", "rival_sellers", "sales_rank", "size",
               "amazon_oos", "maker_tel", "maker_email", "maker_url",
               "scale_flag", "criteria_ok", "note", "amazon_url"]


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


def selection(cat_id, page):
    return {
        "current_SALES_gte": RANK_LO, "current_SALES_lte": RANK_HI,
        "current_COUNT_NEW_gte": 2,
        "current_AMAZON_gte": -1, "current_AMAZON_lte": -1,   # 本体不在に限定
        "current_NEW_gte": PRICE_LO, "current_NEW_lte": PRICE_HI,
        "categories_include": [cat_id],
        "perPage": 50, "page": page,
        "sort": [["current_SALES", "asc"]],
    }


def finder_asins(kb, cat_id, target):
    got = []
    for page in range(FINDER_PAGES_MAX):
        if len(got) >= target:
            break
        wait_tokens(kb, need=60)
        try:
            asins = kb._fetch_finder_asins(selection(cat_id, page))
        except Exception as e:
            log(f"    finder err p{page}: {e}"); time.sleep(5); continue
        if not asins:
            break
        got.extend(asins)
        time.sleep(0.25)
    return list(dict.fromkeys(got))[:target]


def reverse_buy(amazon_price, fee_cat, size):
    """純利益率がTARGET_MARGINになる税込仕入上限と、その時の純利益。"""
    if not amazon_price or amazon_price <= 0:
        return None, None, None
    cfg = fees.get_referral_rate(fee_cat)
    referral = max(amazon_price * cfg["rate"], cfg.get("min_fee_yen", 0))
    fba = fees.get_fba_fee(size).get("fba_fee_yen", 0)
    inbound = INBOUND.get(size, 250)
    target_net = TARGET_MARGIN * amazon_price
    buy_incl = amazon_price - referral - fba - inbound - OTHER_COSTS - target_net
    if buy_incl <= 0:
        return 0, round(target_net), round(TARGET_MARGIN * 100, 1)
    # 検算（calc.profitで純利益率を確認）
    try:
        r = calculate(ProfitInput(wholesale_price=buy_incl, amazon_price=amazon_price,
                                   category_key=fee_cat, size_key=size,
                                   inbound_shipping=inbound, other_costs=OTHER_COSTS,
                                   wholesale_price_is_tax_included=True))
        return round(buy_incl), round(r.net_profit), round(r.margin_rate * 100, 1)
    except Exception:
        return round(buy_incl), round(target_net), round(TARGET_MARGIN * 100, 1)


def write_prod(rows):
    tmp = PROD_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PROD_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in PROD_FIELDS})
    tmp.replace(PROD_CSV)


def main():
    if PROG.exists():
        PROG.unlink()
    kb = KeepaBackend()
    log(f"起動: Keepa={kb.is_live} ランク{RANK_LO}-{RANK_HI} 価格{PRICE_LO}-{PRICE_HI} "
        f"目標ASIN計={len(CATS)*TARGET_PER_CAT} 目標利益率{TARGET_MARGIN*100:.0f}%")

    # Phase1: Finder
    cat_map = {}
    fee_map = {}
    for ckey, (cid, feecat) in CATS.items():
        got = finder_asins(kb, cid, TARGET_PER_CAT)
        for a in got:
            cat_map.setdefault(a, ckey)
            fee_map.setdefault(a, feecat)
        log(f"[Finder] {ckey}: {len(got)}件 (累計{len(cat_map)}) tokensLeft={kb.last_tokens_left}")
    asins = list(cat_map.keys())
    log(f"=== Phase1完了: 本体不在×競合2+×ランク帯 ASIN {len(asins)}件 ===")

    # Phase2: 詳細取得 → メーカー抽出 → 想定仕入価格
    rows = []
    seen = set()
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
            if ap is None or ap.asin in seen:
                continue
            seen.add(ap.asin)
            manufacturer = (prod.get("manufacturer") or "").strip()
            brand = (prod.get("brand") or "").strip()
            maker = manufacturer or brand
            title = (ap.title or "")
            if not maker:
                continue                      # メーカー不明は台帳に使えない
            if NG_TITLE.search(title):
                continue                      # 規制/成人系を除外
            ck = cat_map.get(ap.asin, "")
            feecat = fee_map.get(ap.asin, "default")
            size = ap.size_key or "standard_1"
            buy, net, mpct = reverse_buy(ap.current_price, feecat, size)
            offers = ap.offer_count if ap.offer_count is not None else None
            rank = ap.sales_rank
            oos = (prod.get("availabilityAmazon", -1) == -1)
            # ランクはFinderが権威フィールド(current_SALES)で5万-15万を担保済み。
            # 表示rankは別軸で差が出るため再判定に使わず、本体不在×競合2+×利益成立で判定。
            crit = (oos and (offers is not None and offers >= 2)
                    and bool(buy) and buy > 0)
            scale = "大手/海外疑い" if BIG_HINTS.search(maker + " " + title) else "中小候補"
            rows.append({
                "asin": ap.asin, "name": title[:60], "category": ck,
                "amazon_price": ap.current_price, "buy_target_incl": buy,
                "net_at_target": net, "margin_pct": mpct,
                "manufacturer": manufacturer, "brand": brand,
                "monthly_sales": ap.monthly_sales, "rival_sellers": offers,
                "sales_rank": rank, "size": size,
                "amazon_oos": "本体なし" if oos else "本体あり",
                "maker_tel": "", "maker_email": "", "maker_url": "",
                "scale_flag": scale, "criteria_ok": crit,
                "note": ("要連絡先確認" if scale == "中小候補" else "大手/海外の可能性→代理店窓口"),
                "amazon_url": f"https://www.amazon.co.jp/dp/{ap.asin}",
            })
        log(f"  詳細 {min(i,len(asins))}/{len(asins)} メーカー付与行={len(rows)} tokensLeft={pay.get('tokensLeft')}")
        write_prod(rows)
        time.sleep(0.2)
    write_prod(rows)

    # Phase3: メーカー名寄せ台帳
    led = {}
    for r in rows:
        key = r["manufacturer"] or r["brand"]
        d = led.setdefault(key, {"maker": key, "brands": set(), "n_products": 0,
                                 "n_criteria_ok": 0, "sum_monthly": 0,
                                 "categories": set(), "top_asin": "", "top_ms": -1,
                                 "price_min": None, "price_max": None,
                                 "scale_flag": r["scale_flag"]})
        d["brands"].add(r["brand"])
        d["n_products"] += 1
        if r["criteria_ok"]:
            d["n_criteria_ok"] += 1
        ms = r["monthly_sales"] or 0
        d["sum_monthly"] += ms
        d["categories"].add(r["category"])
        if ms > d["top_ms"]:
            d["top_ms"] = ms; d["top_asin"] = r["asin"]
        p = r["amazon_price"] or 0
        if p:
            d["price_min"] = p if d["price_min"] is None else min(d["price_min"], p)
            d["price_max"] = p if d["price_max"] is None else max(d["price_max"], p)
    ledger = sorted(led.values(), key=lambda d: (d["n_criteria_ok"], d["sum_monthly"]), reverse=True)
    mfields = ["maker", "brands", "n_products", "n_criteria_ok", "sum_monthly",
               "categories", "top_asin", "price_min", "price_max", "scale_flag",
               "maker_tel", "maker_email", "maker_url", "note"]
    with open(MAKER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=mfields); w.writeheader()
        for d in ledger:
            w.writerow({
                "maker": d["maker"], "brands": " / ".join(sorted(x for x in d["brands"] if x)),
                "n_products": d["n_products"], "n_criteria_ok": d["n_criteria_ok"],
                "sum_monthly": d["sum_monthly"], "categories": " / ".join(sorted(d["categories"])),
                "top_asin": d["top_asin"], "price_min": d["price_min"], "price_max": d["price_max"],
                "scale_flag": d["scale_flag"], "maker_tel": "", "maker_email": "", "maker_url": "",
                "note": "要連絡先確認(Phase B)",
            })

    summary = {
        "ticket": "T-20260804-001",
        "method": "Keepa Finder(本体不在×競合2+×ランク5万-15万・13カテゴリ) → brand/manufacturer直読み → 想定仕入価格逆算 → メーカー名寄せ",
        "criteria": f"①Amazon本体不在 ②FBAライバル≥2 ③ランク{RANK_LO}-{RANK_HI} / 想定仕入価格=純利益率{TARGET_MARGIN*100:.0f}%の税込上限(手数料+FBA+納品送料+外注{OTHER_COSTS}円計上)",
        "asin_found": len(asins), "product_rows": len(rows),
        "criteria_ok_rows": sum(1 for r in rows if r["criteria_ok"]),
        "unique_makers": len(ledger),
        "makers_criteria_ok": sum(1 for d in ledger if d["n_criteria_ok"] > 0),
        "chusho_makers": sum(1 for d in ledger if d["scale_flag"] == "中小候補"),
        "tokens_left": kb.last_tokens_left,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=== Phase A 完了 ===")
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
