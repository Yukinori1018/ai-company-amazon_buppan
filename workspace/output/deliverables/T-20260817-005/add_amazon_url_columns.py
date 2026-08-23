#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「メーカー仕入れ台帳」の既存タブに Amazon商品ページURL列を非破壊で追加する。

初出: 2026-08-23 / T-20260817-005（社長指示：ASIN列はあるがURL列が無くて不便）
担当: 庶務マリエ

■ 設計方針（事故防止）
  1. 実行前にブック全体のスナップショットを JSON 保存する。
     初回の原本は上書きせず、再実行時は時刻つき別名に退避する。
  2. 追加は「既存列の右端に1列 append」のみ。列の挿入・削除・並べ替えは一切しない。
     → 既存セルのアドレスが1つも動かないので、値が壊れる余地が構造的に無い。
  3. 冪等。ヘッダー行に既に URL 列があれば、列を増やさず値だけ更新する。
  4. 実行後にブックを読み直し、**既存列の全セルを事前スナップショットと機械突合**する。
     1セルでも不一致なら異常終了扱いで報告する。
  5. リンク列が既にあるタブ（⭐︎売れ筋商品／メーカー台帳／v13_候補100件）には触れない。

■ 使い方
    python3 add_amazon_url_columns.py            # 実行
    python3 add_amazon_url_columns.py --dry-run  # 何をするかだけ表示
"""
import json
import os
import sys
import time

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
BACKUP = os.path.join(
    REPO, "workspace/output/agent_output/T-20260817-005/sheet_backup_before_urlcol.json")

NEW_HEADER = "Amazonページ"
URL_TMPL = "https://www.amazon.co.jp/dp/{}"

# 対象タブ: {タブ名: ASINが入っている列のヘッダー名}
TARGETS = {
    "⭐月販実測あり(60商品)": "ASIN",
    "連絡先取得済(優先)": "代表ASIN",
}
# 触らないタブ（既にURL列がある／URLの概念が無い）
SKIP_NOTE = {
    "⭐︎売れ筋商品": "既に『Amazonリンク』列あり(全行充足)",
    "メーカー台帳": "既に『代表商品リンク』列あり(全行充足)",
    "v13_候補100件": "既に『Amazonページリンク』列あり・社長指示で触らない",
    "サマリ・前提": "ASIN列なし",
    "v13_サマリ・前提": "ASIN列なし",
}

# 既にURL列とみなすヘッダー名（別名でも二重追加しないため）
URLISH = {NEW_HEADER, "Amazonリンク", "Amazonページリンク", "代表商品リンク", "商品リンク"}


def col_a1(n):
    """1始まりの列番号 -> A1記法の列名"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def dump_book(sh):
    return {
        "sheet_id": SHEET_ID,
        "title": sh.title,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tabs": [
            {
                "title": ws.title, "id": ws.id,
                "rows": ws.row_count, "cols": ws.col_count,
                "values": ws.get_all_values(),
            }
            for ws in sh.worksheets()
        ],
    }


def main():
    dry = "--dry-run" in sys.argv
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)

    # ---- 1. 事前スナップショット ----
    before = dump_book(sh)
    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    # 初回の「変更前」原本は上書きしない。2回目以降は時刻つきの別名に保存する。
    path = BACKUP
    if os.path.exists(BACKUP):
        path = BACKUP.replace(".json", "." + time.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(before, f, ensure_ascii=False, indent=1)
    print(f"[snapshot] {path}")
    before_tabs = {t["title"]: t for t in before["tabs"]}
    print(f"[snapshot] タブ {len(before_tabs)}枚: {list(before_tabs)}")

    report = []

    # ---- 2. 追加処理 ----
    for ws in sh.worksheets():
        title = ws.title
        if title not in TARGETS:
            print(f"[skip] {title} … {SKIP_NOTE.get(title, '対象外')}")
            continue

        vals = before_tabs[title]["values"]
        if not vals:
            print(f"[skip] {title} … 空タブ")
            continue
        header = vals[0]
        asin_name = TARGETS[title]
        if asin_name not in header:
            print(f"[skip] {title} … ASIN列『{asin_name}』が見つからない")
            continue
        ai = header.index(asin_name)

        # --- 冪等判定: 既にURL列があるか ---
        existing = [i for i, h in enumerate(header) if h.strip() in URLISH]
        if existing:
            ci = existing[0]
            mode = f"既存列『{header[ci]}』({col_a1(ci+1)}列)の値のみ更新"
            new_col = False
        else:
            ci = len(header)          # 右端に append
            mode = f"新規列 {col_a1(ci+1)} として追加"
            new_col = True

        # --- 値を組み立て（ASINが空の行は空欄のまま） ---
        cells, filled, blank = [], 0, 0
        for row in vals[1:]:
            asin = row[ai].strip() if ai < len(row) else ""
            if asin:
                cells.append([URL_TMPL.format(asin)])
                filled += 1
            else:
                cells.append([""])
                blank += 1

        print(f"[plan] {title}: {mode} / 埋める {filled}行 / 空欄 {blank}行")
        if dry:
            report.append((title, col_a1(ci + 1), filled, blank, "dry-run"))
            continue

        # --- グリッド幅の確保（列を増やすだけ。既存セルは動かない） ---
        need = ci + 1
        if ws.col_count < need:
            ws.add_cols(need - ws.col_count)
            time.sleep(1)

        rng = f"{col_a1(need)}1:{col_a1(need)}{len(vals)}"
        ws.update(rng, [[NEW_HEADER]] + cells, value_input_option="RAW")
        time.sleep(1)
        ws.format(f"{col_a1(need)}1", {"textFormat": {"bold": True}})
        time.sleep(1)
        print(f"[done] {title}: {rng} 書き込み完了")
        report.append((title, col_a1(need), filled, blank,
                       "新規追加" if new_col else "値更新"))

    if dry:
        return

    # ---- 3. 事後検証: 既存列が1セルも変わっていないことを突合 ----
    print("\n[verify] 既存列の突合を開始")
    after = dump_book(sh)
    after_tabs = {t["title"]: t for t in after["tabs"]}
    ng = 0

    lost = set(before_tabs) - set(after_tabs)
    if lost:
        print(f"  NG: タブが消えた -> {lost}")
        ng += 1

    for title, b in before_tabs.items():
        if title not in after_tabs:
            continue
        a = after_tabs[title]
        bw = max((len(r) for r in b["values"]), default=0)   # 変更前の実データ幅
        if len(a["values"]) < len(b["values"]):
            print(f"  NG: {title} 行数が減った {len(b['values'])} -> {len(a['values'])}")
            ng += 1
        diff = 0
        for r, brow in enumerate(b["values"]):
            arow = a["values"][r] if r < len(a["values"]) else []
            for c in range(bw):
                bv = brow[c] if c < len(brow) else ""
                av = arow[c] if c < len(arow) else ""
                if bv != av:
                    diff += 1
                    if diff <= 3:
                        print(f"  NG: {title} {col_a1(c+1)}{r+1}: '{bv}' -> '{av}'")
        if diff:
            print(f"  NG: {title} 既存セル差分 {diff}件")
            ng += 1
        else:
            print(f"  OK: {title} 既存 {len(b['values'])}行 x {bw}列 … 全セル一致")

    print("\n=== 結果 ===")
    for t, col, f_, bl, m in report:
        print(f"  {t}: {col}列 ({m}) / 埋 {f_} / 空 {bl}")
    if ng:
        print(f"\n*** 検証 NG {ng}件。バックアップ {BACKUP} から復元を検討してください ***")
        sys.exit(1)
    print("\n検証OK: 既存データは1セルも変わっていません。")


if __name__ == "__main__":
    main()
