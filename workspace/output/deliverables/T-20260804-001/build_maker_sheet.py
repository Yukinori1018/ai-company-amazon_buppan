"""メーカー台帳 → 社長所有の共有Googleシート(1y1e15…)へ流し込み。
タブ: サマリ・前提 / メーカー台帳 / 売れ筋商品。連絡先はPhase Bで別途更新。
既存シートは全タブ作り直し（このシートは本台帳専用に社長が用意したもの）。
"""
import csv
import json
import time
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4"
OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260804-001")
PROD_CSV = OUT / "maker_products.csv"
MAKER_CSV = OUT / "maker_ledger.csv"
SUMMARY = OUT / "maker_summary.json"

MAKER_HEAD = ["メーカー名", "ブランド", "商品数", "3基準クリア数", "月販合計",
              "カテゴリ", "代表ASIN", "代表商品リンク", "価格帯(最小)", "価格帯(最大)",
              "規模フラグ", "メーカー電話", "メーカーメール", "メーカーHP", "備考"]
MAKER_KEYS = ["maker", "brands", "n_products", "n_criteria_ok", "sum_monthly",
              "categories", "top_asin", "_top_link", "price_min", "price_max",
              "scale_flag", "maker_tel", "maker_email", "maker_url", "note"]

PROD_HEAD = ["ASIN", "商品名", "カテゴリ", "Amazon価格", "想定仕入価格(税込上限)",
             "想定純利益", "利益率%", "メーカー名", "ブランド", "月販数", "ライバル数",
             "ランク", "サイズ", "Amazon本体", "メーカー電話", "メーカーメール",
             "メーカーHP", "規模フラグ", "3基準OK", "備考", "Amazonリンク"]
PROD_KEYS = ["asin", "name", "category", "amazon_price", "buy_target_incl",
             "net_at_target", "margin_pct", "manufacturer", "brand", "monthly_sales",
             "rival_sellers", "sales_rank", "size", "amazon_oos", "maker_tel",
             "maker_email", "maker_url", "scale_flag", "criteria_ok", "note", "amazon_url"]


def chunked(sh, title, header, rows, chunk=1500):
    existing = {w.title: w for w in sh.worksheets()}
    if title in existing:
        sh.del_worksheet(existing[title])
    sh.add_worksheet(title=title, rows=max(len(rows) + 5, 10), cols=len(header))
    sh.values_update(f"'{title}'!A1", params={"valueInputOption": "RAW"}, body={"values": [header]})
    start = 2
    for i in range(0, len(rows), chunk):
        block = rows[i:i + chunk]
        for attempt in range(4):
            try:
                sh.values_update(f"'{title}'!A{start}", params={"valueInputOption": "RAW"},
                                 body={"values": block})
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  retry {title}@{start}: {type(e).__name__}", flush=True)
                time.sleep(5 * (attempt + 1))
        start += len(block)
        print(f"  {title}: {start-2}/{len(rows)}行", flush=True)
        time.sleep(1)


def main():
    makers = list(csv.DictReader(open(MAKER_CSV, encoding="utf-8")))
    prods = list(csv.DictReader(open(PROD_CSV, encoding="utf-8")))
    s = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}

    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    print("opened:", sh.title, flush=True)

    # サマリ（既存シート1を作り直し）
    info = [
        ["メーカー仕入れせどり｜Amazon売れ筋メーカー台帳（T-20260804-001）", ""],
        ["作成", s.get("finished_at", "")],
        ["手法", s.get("method", "")],
        ["選別基準", s.get("criteria", "")],
        ["", ""],
        ["売れ筋商品(母集団)", s.get("product_rows", len(prods))],
        ["3基準クリア商品", s.get("criteria_ok_rows", "")],
        ["ユニークメーカー数", s.get("unique_makers", len(makers))],
        ["中小候補メーカー", s.get("chusho_makers", "")],
        ["", ""],
        ["【想定仕入価格の意味】", "純利益率25%を確保できる税込の仕入上限。販売手数料+FBA+納品送料+梱包外注等を計上。"],
        ["", "この価格以下でメーカーと取引できれば利益率25%以上。交渉の上限目安。"],
        ["【連絡先】", "電話/メールはAmazonに無いためWeb探索(Phase B)で付与。空欄=未取得。推測記入はしない。"],
        ["【規模フラグ】", "大手/海外疑い=直取引しにくい(代理店窓口)。中小候補=メーカー直取引を狙える。"],
        ["【注意】", "メーカーへの実連絡は社長承認が必須(§4.1)。本台帳は候補提示まで。"],
        ["", "各候補は取引前にAmazon実ページとメーカー公式で商品・会社を必ず確認。"],
    ]
    first = sh.sheet1
    first.update_title("サマリ・前提")
    first.clear()
    first.resize(rows=len(info) + 3, cols=2)
    sh.values_update("'サマリ・前提'!A1", params={"valueInputOption": "RAW"}, body={"values": info})
    print("wrote サマリ・前提", flush=True)

    # メーカー台帳
    mrows = []
    for d in makers:
        d["_top_link"] = f"https://www.amazon.co.jp/dp/{d.get('top_asin','')}" if d.get("top_asin") else ""
        mrows.append([d.get(k, "") for k in MAKER_KEYS])
    chunked(sh, "メーカー台帳", MAKER_HEAD, mrows)
    print(f"wrote メーカー台帳: {len(mrows)}社", flush=True)

    # 売れ筋商品
    prows = [[p.get(k, "") for k in PROD_KEYS] for p in prods]
    chunked(sh, "売れ筋商品", PROD_HEAD, prows)
    print(f"wrote 売れ筋商品: {len(prows)}件", flush=True)

    print("URL:", sh.url, flush=True)


if __name__ == "__main__":
    main()
