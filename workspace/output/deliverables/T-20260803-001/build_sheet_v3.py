"""shiire_list_3000.csv → 新規Googleスプレッドシート（社長閲覧用）。

タブ構成:
  1) サマリ・前提       … 手法/仕入れ条件/件数サマリ
  2) 仕入れ条件合致(原石) … gem=True を純利益降順で（=すぐ精査すべき棚）
  3) 全リスト           … 3000件超の全行（Amazonリンク付）

サービスアカウント(claude-session-sheets)で作成し、社長アカウントへ共有。
実行: python3 build_sheet_v3.py
"""
import csv
import json
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
OWNER_EMAIL = "satoyukinori1018@gmail.com"
TITLE = "仕入れせどり_売れ筋×仕入れ先リスト_Amazon物販事業"
OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260803-001")
CSV_PATH = OUT / "shiire_list_3000.csv"
SUMMARY_PATH = OUT / "shiire_summary.json"
URL_OUT = OUT / "sheet_url.txt"

# 表示ヘッダ（日本語）とCSVキーの対応
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


def load_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_row(r):
    return [r.get(k, "") for k in KEYS]


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def num(v, default=-1):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_summary_tab(rows):
    s = {}
    if SUMMARY_PATH.exists():
        s = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    n = len(rows)
    n_jan = sum(1 for r in rows if r.get("jan"))
    n_matched = sum(1 for r in rows if num(r.get("buy")) > 0)
    n_gem = sum(1 for r in rows if truthy(r.get("gem")))
    n_durable = sum(1 for r in rows if truthy(r.get("durable")))
    lines = [
        ["仕入れせどり｜Amazon売れ筋 × 仕入れ先リスト", ""],
        ["チケット", "T-20260803-001"],
        ["作成", s.get("finished_at", "（走行中スナップショット）")],
        ["", ""],
        ["【手法】", s.get("method", "Amazon起点(Keepa Product Finder) → JAN逆引き(Yahoo+楽天) → 利益判定")],
        ["Finder条件", s.get("finder_filter", "rank3000-80000/offers2-10/price1000-10000")],
        ["仕入れ条件(判定)", s.get("criteria", "原石=利益率≥8%&純利益≥300円 / 持続=+相乗り2-10&月販≥3")],
        ["", ""],
        ["【件数】", ""],
        ["総リスト件数", n],
        ["JAN取得済", n_jan],
        ["仕入先マッチ(価格取得)", n_matched],
        ["仕入れ条件合致=原石(tier1)", n_gem],
        ["うち持続(tier2)", n_durable],
        ["", ""],
        ["【注意】", "実購入は社長承認必須(§4.1金銭)。本シートは候補リストまで。"],
        ["", "各候補はAmazon実ページ×仕入先ページで同一商品かを購入前に必ず目視確認。"],
        ["", "仕入値は税込最安の自動逆引き。入数/型番差の誤突合が残り得る点に留意。"],
    ]
    return lines


def main():
    rows = load_rows()
    # 原石タブ: gem=True を純利益降順
    gems = [r for r in rows if truthy(r.get("gem"))]
    gems.sort(key=lambda r: num(r.get("net")), reverse=True)

    gc = gspread.service_account(filename=CRED)
    sh = gc.create(TITLE)
    sh.share(OWNER_EMAIL, perm_type="user", role="writer", notify=False)
    try:
        sh.share(None, perm_type="anyone", role="reader", with_link=True)
    except Exception as e:
        print("anyone-link share skipped:", e)

    # Tab1 サマリ
    ws = sh.sheet1
    ws.update_title("サマリ・前提")
    summary_rows = build_summary_tab(rows)
    ws.resize(rows=max(len(summary_rows), 1), cols=2)
    sh.values_update("'サマリ・前提'!A1", params={"valueInputOption": "RAW"},
                     body={"values": summary_rows})
    print("wrote サマリ・前提")

    # Tab2 原石
    gem_data = [HEADER] + [to_row(r) for r in gems]
    ws2 = sh.add_worksheet(title="仕入れ条件合致(原石)", rows=max(len(gem_data), 1), cols=len(HEADER))
    sh.values_update("'仕入れ条件合致(原石)'!A1", params={"valueInputOption": "RAW"},
                     body={"values": gem_data})
    print(f"wrote 仕入れ条件合致(原石): {len(gems)}件")

    # Tab3 全リスト
    all_data = [HEADER] + [to_row(r) for r in rows]
    ws3 = sh.add_worksheet(title="全リスト", rows=max(len(all_data), 1), cols=len(HEADER))
    # gspread values_update は一括投入。大きいので分割せず一発（数千行は許容範囲）。
    sh.values_update("'全リスト'!A1", params={"valueInputOption": "RAW"},
                     body={"values": all_data})
    print(f"wrote 全リスト: {len(rows)}件")

    URL_OUT.write_text(sh.url, encoding="utf-8")
    print("URL:", sh.url)


if __name__ == "__main__":
    main()
