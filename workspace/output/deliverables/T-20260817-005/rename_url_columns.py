#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「メーカー仕入れ台帳」の Amazon 商品ページ URL 列のヘッダー名を `Amazonページ` に統一する。

初出: 2026-08-23 / T-20260817-005（社長指示「Amazonページで統一して下さい。」）
担当: 庶務マリエ

■ 背景
  同じ「Amazon 商品ページの URL」列が、タブごとに4種類の名前で存在していた。
    ⭐月販実測あり(60商品) … Amazonページ      （既に統一名）
    連絡先取得済(優先)      … Amazonページ      （既に統一名）
    ⭐︎売れ筋商品            … Amazonリンク      → Amazonページ
    メーカー台帳            … 代表商品リンク    → Amazonページ
    v13_候補100件           … Amazonページリンク → Amazonページ
  社長が「列が無い」と誤認する原因になっていたため、名前だけを揃える。

■ 事前確認（2026-08-23 実施済み・このスクリプトを流す前提条件）
  1. ブック全7タブ・全セルを valueRenderOption=FORMULA で走査 → **数式セル 0件**。
     名前付き範囲 0件。よってヘッダー文字列を参照する QUERY / VLOOKUP 等は存在しない。
  2. リポジトリ側も走査 → シートを**列名で読む**スクリプトは無い（書き出し側のみ）。
  → 改名で壊れるものが無いことを確認した上で実行している。

■ 設計方針（add_amazon_url_columns.py / add_keepa_link_columns.py の型を踏襲）
  1. 実行前にブック全体を **時刻つき別名**で JSON スナップショット保存（既存バックアップは上書きしない）。
  2. 触るのは **1行目のヘッダーセル1個だけ**。データ行・列の位置・並び順・タブ名は一切変えない。
  3. 冪等。既に `Amazonページ` なら何もしない。
  4. 同一タブに `Amazonページ` が2つできる状況を検知したら中止（安全弁）。
  5. 実行後にブックを読み直し、**変更した3セル以外の全セルを事前スナップショットと機械突合**。
     1セルでも不一致なら異常終了扱い。

■ 使い方
    python3 rename_url_columns.py            # 実行
    python3 rename_url_columns.py --dry-run  # 何をするかだけ表示
"""
import datetime
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
BACKUP_DIR = os.path.join(REPO, "workspace/output/agent_output/T-20260817-005")

CANON = "Amazonページ"

# 改名対象: {タブ名: (旧ヘッダー名の候補,)}
# 値は「Amazon 商品ページの URL が入っている列」だけ。Keepaリンク は対象外。
TARGETS = {
    "⭐月販実測あり(60商品)": ("Amazonページ",),          # 既に統一名 → 変更なし
    "連絡先取得済(優先)":     ("Amazonページ",),          # 既に統一名 → 変更なし
    "⭐︎売れ筋商品":           ("Amazonリンク", "Amazonページ"),
    "メーカー台帳":           ("代表商品リンク", "Amazonページ"),
    "v13_候補100件":          ("Amazonページリンク", "Amazonページ"),
}
# 触らないタブ（URL 列が無い）
SKIP_NOTE = {
    "サマリ・前提": "URL列なし（対象外）",
    "v13_サマリ・前提": "URL列なし（対象外）",
}
# 絶対に触らない列名（明示しておく）
NEVER_TOUCH = {"Keepaリンク", "ASIN", "代表ASIN"}


def col_a1(n):
    """1始まりの列番号 -> A1記法の列名"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def dump_book(sh):
    """全タブの全セルを FORMULA レンダリングで吸い出す（数式があれば数式のまま残る）。"""
    tabs = {}
    for ws in sh.worksheets():
        tabs[ws.title] = ws.get_all_values(value_render_option="FORMULA")
    return tabs


def main():
    dry = "--dry-run" in sys.argv
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    print(f"opened: {sh.title}", flush=True)

    before = dump_book(sh)
    print(f"タブ数: {len(before)}", flush=True)

    # ---- 安全弁1: 数式セルが1つでもあれば中止 ----
    n_formula = sum(
        1 for rows in before.values() for row in rows for v in row
        if isinstance(v, str) and v.startswith("=")
    )
    if n_formula:
        print(f"[ABORT] 数式セルを {n_formula} 件検出しました。列名参照の恐れがあるため中止します。")
        sys.exit(2)
    print("数式セル: 0件（安全）", flush=True)

    # ---- 計画づくり ----
    plan = []   # (tab, col_index_1based, old, new)
    for title, rows in before.items():
        if title in SKIP_NOTE:
            print(f"  - {title}: SKIP（{SKIP_NOTE[title]}）")
            continue
        if title not in TARGETS:
            print(f"  - {title}: SKIP（対象外タブ）")
            continue
        header = rows[0] if rows else []
        olds = TARGETS[title]
        hits = [i for i, h in enumerate(header, 1) if h in olds]
        if not hits:
            print(f"  ! {title}: 対象列が見つかりません（header={header}）")
            continue
        if len(hits) > 1:
            print(f"[ABORT] {title}: 対象列が {len(hits)} 個あります（{hits}）。手動確認が必要です。")
            sys.exit(2)
        idx = hits[0]
        old = header[idx - 1]
        if old == CANON:
            print(f"  = {title}: {col_a1(idx)}列 は既に『{CANON}』（変更なし）")
            continue
        # 安全弁2: 同じタブに既に CANON がある場合は重複になるので中止
        if CANON in header:
            print(f"[ABORT] {title}: 既に『{CANON}』列が存在します。改名すると重複します。")
            sys.exit(2)
        # 安全弁3: 触ってはいけない列名でないこと
        if old in NEVER_TOUCH:
            print(f"[ABORT] {title}: 『{old}』は変更禁止列です。")
            sys.exit(2)
        plan.append((title, idx, old, CANON))
        print(f"  → {title}: {col_a1(idx)}1  『{old}』 → 『{CANON}』")

    if not plan:
        print("\n変更するものはありません（冪等・既に統一済み）。")
        return

    # ---- スナップショット保存 ----
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bpath = os.path.join(BACKUP_DIR, f"sheet_backup_before_rename.{ts}.json")
    if os.path.exists(bpath):
        print(f"[ABORT] バックアップ {bpath} が既に存在します（上書きしません）。")
        sys.exit(2)
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(before, f, ensure_ascii=False)
    print(f"\nスナップショット保存: {bpath} ({os.path.getsize(bpath):,} bytes)", flush=True)

    if dry:
        print("\n--dry-run のためここで終了します。書き込みはしていません。")
        return

    # ---- 実行（ヘッダーセル1個ずつ）----
    for title, idx, old, new in plan:
        a1 = f"'{title}'!{col_a1(idx)}1"
        sh.values_update(a1, params={"valueInputOption": "RAW"}, body={"values": [[new]]})
        print(f"  wrote {a1}: 『{old}』 → 『{new}』", flush=True)

    # ---- 事後突合 ----
    after = dump_book(sh)
    changed = {(t, 1, i) for t, i, _, _ in plan}
    diff = 0
    if set(before) != set(after):
        print(f"[NG] タブ構成が変わりました: {set(before) ^ set(after)}")
        sys.exit(1)
    for title in before:
        b, a = before[title], after[title]
        if len(b) != len(a):
            print(f"[NG] {title}: 行数 {len(b)} → {len(a)}")
            diff += 1
            continue
        for r in range(len(b)):
            if len(b[r]) != len(a[r]):
                print(f"[NG] {title}: {r+1}行目の列数 {len(b[r])} → {len(a[r])}")
                diff += 1
                continue
            for c in range(len(b[r])):
                if (title, r + 1, c + 1) in changed:
                    continue
                if b[r][c] != a[r][c]:
                    diff += 1
                    if diff <= 10:
                        print(f"[NG] {title} [{r+1},{c+1}]: {b[r][c]!r} → {a[r][c]!r}")
    # 変更セルが意図どおりになっているか
    for title, idx, old, new in plan:
        got = after[title][0][idx - 1]
        mark = "OK" if got == new else "NG"
        print(f"  [{mark}] {title} {col_a1(idx)}1 = {got!r}")
        if got != new:
            diff += 1

    if diff:
        print(f"\n[NG] ヘッダー以外に差分 {diff} 件。バックアップ: {bpath}")
        sys.exit(1)
    print(f"\n[OK] 変更した {len(plan)} セル以外は全タブ・全セル差分0で一致しました。")


if __name__ == "__main__":
    main()
