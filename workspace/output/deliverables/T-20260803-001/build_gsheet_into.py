"""既存のオーナー所有Googleシート(SHEET_ID)へ、仕入れせどりリストを書き込む。
Drive複製で作った owner所有＋SA編集権のシートを対象にする（SAは新規作成不可のため）。
タブ: サマリ・前提 / 仕入れ条件合致(原石) / 全リスト。複製元の旧タブは削除する。
大きい全リストは行チャンクで投入（payload上限回避）。
"""
import csv
import json
import sys
import time
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1wiejLG9s0IMPeO46g1d7zWJl4184kgqhIpaiIvYaMuk"
OWNER_EMAIL = "satoyukinori1018@gmail.com"
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


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def num(v, d=-1):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def to_row(r):
    return [r.get(k, "") for k in KEYS]


def chunked_update(sh, tab, header, data_rows, chunk=1200):
    ncols = len(header)
    total = len(data_rows) + 1
    ws = sh.add_worksheet(title=tab, rows=max(total + 5, 10), cols=ncols)
    sh.values_update(f"'{tab}'!A1", params={"valueInputOption": "RAW"},
                     body={"values": [header]})
    start = 2
    for i in range(0, len(data_rows), chunk):
        block = data_rows[i:i + chunk]
        rng = f"'{tab}'!A{start}"
        for attempt in range(4):
            try:
                sh.values_update(rng, params={"valueInputOption": "RAW"},
                                 body={"values": block})
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  retry {tab} block@{start}: {type(e).__name__}", flush=True)
                time.sleep(5 * (attempt + 1))
        start += len(block)
        print(f"  {tab}: {start-2}/{len(data_rows)}行", flush=True)
        time.sleep(1)
    return ws


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    s = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}
    gems = sorted([r for r in rows if truthy(r.get("gem"))],
                  key=lambda r: num(r.get("net")), reverse=True)

    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    print("opened:", sh.title, flush=True)

    # 複製元の旧タブを一旦退避用に1枚残して全削除 → 新タブを作る
    tmp = sh.add_worksheet(title="_tmp", rows=1, cols=1)
    for ws in sh.worksheets():
        if ws.id != tmp.id:
            sh.del_worksheet(ws)
    print("旧タブ削除完了", flush=True)

    # 1) サマリ
    n_jan = sum(1 for r in rows if r.get("jan"))
    n_match = sum(1 for r in rows if num(r.get("buy")) > 0)
    info = [
        ["仕入れせどり｜Amazon売れ筋 × 仕入れ先リスト", ""],
        ["チケット", "T-20260803-001"],
        ["作成", s.get("finished_at", "")],
        ["", ""],
        ["【手法】", s.get("method", "")],
        ["Finder条件", s.get("finder_filter", "")],
        ["仕入れ条件(判定)", s.get("criteria", "")],
        ["", ""],
        ["総リスト件数", len(rows)],
        ["JAN取得済", n_jan],
        ["仕入先マッチ(価格取得)", n_match],
        ["仕入れ条件合致=原石(tier1)", len(gems)],
        ["うち持続(tier2)", sum(1 for r in rows if truthy(r.get("durable")))],
        ["", ""],
        ["【注意】実購入は社長承認必須(§4.1金銭)。本表は候補リストまで。", ""],
        ["各候補はAmazon実ページ×仕入先ページで同一商品かを購入前に必ず目視確認。", ""],
        ["仕入値は税込最安の自動逆引き。入数/型番差の誤突合が残り得る点に留意。", ""],
    ]
    ws1 = sh.add_worksheet(title="サマリ・前提", rows=len(info) + 3, cols=2)
    sh.values_update("'サマリ・前提'!A1", params={"valueInputOption": "RAW"}, body={"values": info})
    print("wrote サマリ・前提", flush=True)

    # 2) 原石
    chunked_update(sh, "仕入れ条件合致(原石)", HEADER, [to_row(r) for r in gems])
    print(f"wrote 原石: {len(gems)}件", flush=True)

    # 3) 全リスト
    chunked_update(sh, "全リスト", HEADER, [to_row(r) for r in rows])
    print(f"wrote 全リスト: {len(rows)}件", flush=True)

    # tmp削除・共有(念のためownerへwriter, リンク閲覧可)
    sh.del_worksheet(tmp)
    try:
        sh.share(OWNER_EMAIL, perm_type="user", role="writer", notify=False)
    except Exception as e:
        print("share owner skipped:", e)
    try:
        sh.share(None, perm_type="anyone", role="reader", with_link=True)
    except Exception as e:
        print("anyone-link skipped:", e)

    URL_OUT.write_text(sh.url, encoding="utf-8")
    print("URL:", sh.url, flush=True)


if __name__ == "__main__":
    main()
