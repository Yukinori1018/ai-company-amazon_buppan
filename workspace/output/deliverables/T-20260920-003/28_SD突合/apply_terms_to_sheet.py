#!/usr/bin/env python3
"""取引条件スキャンの結果を、既存シート『仕入れ先商品リスト_Amazon物販事業』へ反映する。

🔴 このシートは**既存で共有物**（2026-09-30 時点 24,532行／NETSEA 24,451行・SD 80行）。
   **列を増減しない。NETSEA の行には触らない。**触るのは次の2つだけ。

   ① タブ `仕入れ先商品` の `ネット販売可否` 列（K列）を、**仕入れ先が SD の行に限って**上書きする
   ② タブ `SD取引条件` を作り、2,176社の企業単位の判定を置く
      （企業単位の情報は商品行に入らないので別タブにする。**列の増減ではない**）

判定の書き方（CLAUDE.md §3.3-12：不明を○に畳まない）
   ○     … ネット販売○ かつ Amazon の名指しなし
   ×     … `×（Amazon名指し不可）` または `×（ネット販売不可）` と書く。**「○」の文字を含めない**
   要確認 … `要確認（△・モール名を要確認）`
   不明   … `不明（ネット販売の記載なし）`
   → 下流が「○」で機械判定しても、× と 不明 が GO に化けない。

使い方:
    python3 apply_terms_to_sheet.py --sheet-key <id> --terms <jsonl> [--dry-run]
"""
from __future__ import annotations
import argparse, json, os, re, sys, unicodedata

CRED = os.path.expanduser("~/.config/claude-session-sheets/credentials.json")
TAB_PRODUCTS = "仕入れ先商品"
TAB_TERMS = "SD取引条件"
COL_SUPPLIER_SRC = "仕入れ先"
COL_DEALER = "出展企業・サプライヤー名"
COL_NET = "ネット販売可否"
BASE = "https://www.superdelivery.com"

LABEL = {
    "○": "○",
    "×": "×（Amazon名指し不可またはネット販売不可）",
    "要確認": "要確認（△・モール名を要確認）",
    "不明": "不明（ネット販売の記載なし）",
}


def norm(s: str) -> str:
    """社名の名寄せ。法人格語と記号・空白を落として比較する。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"(株式会社|有限会社|合同会社|合資会社|㈱|㈲|\(株\)|\(有\))", "", s)
    s = re.sub(r"[\s　・,.\-–—/（）()\[\]【】「」『』]", "", s)
    return s


def read_terms(path: str) -> list[dict]:
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-key", required=True)
    ap.add_argument("--terms", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-terms-tab", action="store_true",
                    help="SD取引条件タブを作らない（商品行の更新だけ行う）")
    args = ap.parse_args()

    if not os.path.exists(CRED):
        print(f"■ 鍵がありません: {CRED}", file=sys.stderr)
        return 1
    import gspread
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(args.sheet_key)

    terms = read_terms(args.terms)
    by_name = {}
    for t in terms:
        by_name.setdefault(norm(t["dealer_name"]), t)
    print(f"取引条件 {len(terms)}社（名寄せ後 {len(by_name)}）")

    # ---- ① 商品タブの ネット販売可否（SD 行のみ） ----
    ws = sh.worksheet(TAB_PRODUCTS)
    values = ws.get_all_values()
    head = values[0]
    try:
        i_src, i_dealer, i_net = head.index(COL_SUPPLIER_SRC), head.index(COL_DEALER), head.index(COL_NET)
    except ValueError as exc:
        print(f"■ 想定の列がありません: {exc}", file=sys.stderr)
        return 1

    updates, unmatched, untouched_netsea = [], set(), 0
    for r, row in enumerate(values[1:], start=2):
        if len(row) <= max(i_src, i_dealer, i_net):
            continue
        if (row[i_src] or "").strip() != "SD":
            untouched_netsea += 1
            continue
        t = by_name.get(norm(row[i_dealer]))
        if not t:
            unmatched.add(row[i_dealer])
            continue
        want = LABEL[t["judge"]]
        if row[i_net] != want:
            updates.append((r, want))

    col_letter = chr(ord("A") + i_net) if i_net < 26 else None
    print(f"SD 行の更新 {len(updates)}件 / NETSEA 行は {untouched_netsea}件そのまま")
    if unmatched:
        print(f"  名寄せできなかった SD 企業 {len(unmatched)}社: {sorted(unmatched)[:10]}")
    if args.dry_run:
        for r, v in updates[:20]:
            print(f"  DRY {col_letter}{r} ← {v}")
    elif updates:
        # 1セルずつではなく、行番号ごとの範囲でまとめて送る（他セッションの書き込みと衝突しにくい）
        body = [{"range": f"{col_letter}{r}", "values": [[v]]} for r, v in updates]
        ws.batch_update(body)
        print(f"  {col_letter} 列を {len(updates)}件更新しました")

    # ---- ② 企業単位のタブ ----
    if not args.skip_terms_tab:
        cols = ["dealer_id", "出展企業名", "判定", "ネット販売", "消費者への直送",
                "仕入れ前の販売", "画像転載", "代金引換", "Amazonの記載（原文）",
                "企業情報ページ", "取引条件ページ"]
        matrix = [cols]
        for t in sorted(terms, key=lambda x: ({"○": 0, "要確認": 1, "不明": 2, "×": 3}[x["judge"]], x["dealer_id"])):
            matrix.append([
                t["dealer_id"], t["dealer_name"], LABEL[t["judge"]], t["ネット販売"],
                t["消費者への直送"], t["仕入れ前の販売"], t["画像転載"], t["代金引換"],
                " || ".join(t.get("amazon_context") or []),
                f"{BASE}/p/do/dpsl/di/{t['dealer_id']}/",
                f"{BASE}/p/do/dpsl/dcc/{t['dealer_id']}/",
            ])
        if args.dry_run:
            print(f"  DRY タブ『{TAB_TERMS}』に {len(matrix) - 1}行")
        else:
            try:
                tws = sh.worksheet(TAB_TERMS)
                tws.clear()
            except Exception:
                tws = sh.add_worksheet(title=TAB_TERMS, rows=len(matrix) + 20, cols=len(cols) + 1)
            tws.resize(rows=max(len(matrix) + 20, 100), cols=len(cols) + 1)
            tws.update(values=matrix, range_name="A1")
            print(f"  タブ『{TAB_TERMS}』に {len(matrix) - 1}行")

    from collections import Counter
    c = Counter(t["judge"] for t in terms)
    n = len(terms)
    print("判定の内訳: " + " / ".join(f"{k} {v}社 ({100 * v / n:.0f}%)" for k, v in c.most_common()))
    print(f"https://docs.google.com/spreadsheets/d/{args.sheet_key}/edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
