#!/usr/bin/env python3
"""スキャン結果を Google シート『仕入れ先商品リスト_Amazon物販事業』へ投入する。

前提（2回だけの手作業。詳細は memory `reference_gsheets_service_account`）
  1. **シートは Drive MCP で作る**（サービスアカウントは Drive quota 0 で新規作成できない）。
     秘書カズヨが `create_file`（mimeType=application/vnd.google-apps.spreadsheet）で
     タイトル『仕入れ先商品リスト_Amazon物販事業』を社長所有で作成する。
  2. そのシートを `sheets-writer@claude-session-sheets.iam.gserviceaccount.com` に
     **編集者で共有**する（1回だけ）。
  以後は本スクリプトで何度でも投入できる（冪等・全置換）。

タブ構成
  `取引条件`    … sd_dealer_terms.jsonl（2,176社の Amazon 可否判定）
  `商品`        … sd_products.jsonl（企業×商品名×商品コード）
  `卸価格`      … sd_price_fill.js が返した rows を JSONL にしたもの（**会員限定情報**）
  `JAN突合`     … sd_jan_lookup.py の出力（Amazon 起点）

使い方
  python3 push_to_sheet.py --sheet-key <id> --terms <jsonl> [--products <jsonl>] \
      [--prices <jsonl>] [--jan <jsonl>]
"""
from __future__ import annotations
import argparse, json, os, sys

CRED = os.path.expanduser("~/.config/claude-session-sheets/credentials.json")

TERMS_COLS = ["dealer_id", "dealer_name", "judge", "ネット販売", "消費者への直送",
              "仕入れ前の販売", "画像転載", "代金引換", "amazon_context",
              "企業ページ", "取引条件ページ"]
PROD_COLS = ["dealer_id", "dealer_name", "product_code", "name", "商品ページ"]
PRICE_COLS = ["dealer_id", "dealer_name", "page", "product_code", "name", "price_text", "raw"]
JAN_COLS = ["jan", "hit_count", "dealer_id", "product_code", "name", "product_url"]
BASE = "https://www.superdelivery.com"


def read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def to_matrix(rows: list[dict], cols: list[str]) -> list[list]:
    out = [cols]
    for r in rows:
        out.append([("" if r.get(c) is None else
                     (" || ".join(r[c]) if isinstance(r.get(c), list) else str(r.get(c, ""))))
                    for c in cols])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-key", required=True)
    ap.add_argument("--terms")
    ap.add_argument("--products")
    ap.add_argument("--prices")
    ap.add_argument("--jan")
    args = ap.parse_args()

    if not os.path.exists(CRED):
        print(f"■ 鍵がありません: {CRED}", file=sys.stderr)
        return 1
    import gspread
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(args.sheet_key)

    tabs: list[tuple[str, list[list]]] = []
    if args.terms:
        rows = read_jsonl(args.terms)
        for r in rows:
            r["企業ページ"] = f"{BASE}/p/do/dpsl/di/{r.get('dealer_id')}/"
            r["取引条件ページ"] = f"{BASE}/p/do/dpsl/dcc/{r.get('dealer_id')}/"
        tabs.append(("取引条件", to_matrix(rows, TERMS_COLS)))
    if args.products:
        rows = read_jsonl(args.products)
        for r in rows:
            r["商品ページ"] = f"{BASE}/p/r/pd_p/{r.get('product_code')}/"
        tabs.append(("商品", to_matrix(rows, PROD_COLS)))
    if args.prices:
        tabs.append(("卸価格", to_matrix(read_jsonl(args.prices), PRICE_COLS)))
    if args.jan:
        flat = []
        for r in read_jsonl(args.jan):
            if r.get("hits"):
                for h in r["hits"]:
                    flat.append({"jan": r["jan"], "hit_count": r["hit_count"], **h})
            else:
                flat.append({"jan": r["jan"], "hit_count": r.get("hit_count")})
        tabs.append(("JAN突合", to_matrix(flat, JAN_COLS)))

    for name, matrix in tabs:
        try:
            ws = sh.worksheet(name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=max(len(matrix) + 10, 100),
                                  cols=len(matrix[0]) + 2)
        ws.resize(rows=max(len(matrix) + 10, 100), cols=len(matrix[0]) + 2)
        ws.update(values=matrix, range_name="A1")
        print(f"  {name}: {len(matrix) - 1}行")
    print(f"https://docs.google.com/spreadsheets/d/{args.sheet_key}/edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
