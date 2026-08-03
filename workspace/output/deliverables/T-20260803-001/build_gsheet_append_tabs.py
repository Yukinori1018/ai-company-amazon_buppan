"""SA編集権のあるオーナー所有シート(1AAWGWaj…)へ、仕入れせどりリストを【新規タブとして非破壊追記】。
既存タブは一切触らない。追加タブ: SS4446_サマリ / SS4446_原石 / SS4446_全リスト。
"""
import csv
import json
import time
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1AAWGWaj1r6mP3Up297KxOq7F24faKYEYFlcdJlrBT_c"
OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260803-001")
CSV_PATH = OUT / "shiire_list_3000.csv"
SUMMARY_PATH = OUT / "shiire_summary.json"
URL_OUT = OUT / "sheet_url.txt"

COLS = [
    ("rank_no", "No"), ("asin", "ASIN"), ("amazon_url", "Amazonページ"),
    ("name", "商品名"), ("category", "カテゴリ"), ("jan", "JAN"),
    ("amazon_price", "Amazon価格"), ("buybox", "BuyBox価格"),
    ("sales_rank", "ランク"), ("offer_count", "出品者数"),
    ("monthly_sales", "推定月販"), ("size", "サイズ区分"),
    ("buy", "仕入値(最安)"), ("buy_source", "仕入先"),
    ("net", "純利益"), ("margin_pct", "利益率%"), ("roi_pct", "ROI%"),
    ("verdict", "判定"), ("gem", "原石"), ("durable", "持続"),
    ("supplier_hint", "仕入先メモ"),
]
HEADER = [h for _, h in COLS]
KEYS = [k for k, _ in COLS]
PREFIX = "SS4446_"


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def num(v, d=-1):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def to_row(r):
    return [r.get(k, "") for k in KEYS]


def fresh_tab(sh, title, rows, cols):
    existing = {w.title: w for w in sh.worksheets()}
    if title in existing:
        sh.del_worksheet(existing[title])
    return sh.add_worksheet(title=title, rows=max(rows, 10), cols=cols)


def chunked(sh, title, header, data_rows, chunk=1200):
    fresh_tab(sh, title, len(data_rows) + 5, len(header))
    sh.values_update(f"'{title}'!A1", params={"valueInputOption": "RAW"},
                     body={"values": [header]})
    start = 2
    for i in range(0, len(data_rows), chunk):
        block = data_rows[i:i + chunk]
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
        print(f"  {title}: {start-2}/{len(data_rows)}行", flush=True)
        time.sleep(1)


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    s = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
    gems = sorted([r for r in rows if truthy(r.get("gem"))],
                  key=lambda r: num(r.get("net")), reverse=True)

    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    print("opened:", sh.title, flush=True)

    n_jan = sum(1 for r in rows if r.get("jan"))
    n_match = sum(1 for r in rows if num(r.get("buy")) > 0)
    info = [
        ["仕入れせどり｜Amazon売れ筋 × 仕入れ先リスト（T-20260803-001）", ""],
        ["作成", s.get("finished_at", "")],
        ["手法", s.get("method", "")],
        ["Finder条件", s.get("finder_filter", "")],
        ["仕入れ条件(判定)", s.get("criteria", "")],
        ["", ""],
        ["総リスト件数", len(rows)],
        ["JAN取得済", n_jan],
        ["仕入先マッチ(価格取得)", n_match],
        ["仕入れ条件合致=原石(tier1)", len(gems)],
        ["うち持続(tier2)", sum(1 for r in rows if truthy(r.get("durable")))],
        ["", ""],
        ["※このブックの他タブ(原石密度2000件)とは別物。本リストはSS4446_タブ3枚。", ""],
        ["※実購入は社長承認必須(§4.1)。購入前にAmazon実ページ×仕入先で同一商品を目視確認。", ""],
    ]
    fresh_tab(sh, PREFIX + "サマリ", len(info) + 3, 2)
    sh.values_update(f"'{PREFIX}サマリ'!A1", params={"valueInputOption": "RAW"}, body={"values": info})
    print("wrote サマリ", flush=True)

    chunked(sh, PREFIX + "原石", HEADER, [to_row(r) for r in gems])
    print(f"wrote 原石: {len(gems)}件", flush=True)

    chunked(sh, PREFIX + "全リスト", HEADER, [to_row(r) for r in rows])
    print(f"wrote 全リスト: {len(rows)}件", flush=True)

    URL_OUT.write_text(sh.url, encoding="utf-8")
    print("URL:", sh.url, flush=True)


if __name__ == "__main__":
    main()
