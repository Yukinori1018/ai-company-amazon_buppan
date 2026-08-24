"""T-20260817-005 / v1.3 候補100件を【クリーン版】へ差し替える（非破壊・冪等）。

2026-08-24 社長判断①「差し替えて」を受けた作業。タカシ(IT)が scan_v13.py の5欠陥
（COUNT_NEW＝オファー数の取り違え／D1〜D4）を修正した candidates_v13_top100_clean.csv を
「メーカー仕入れ台帳」へ反映する。

やること（この3つだけ。他タブには一切触らない）:
  1. 新規タブ `v13_候補100件_修正版` を作成し clean CSV を投入（No / リスク区分 / Keepaリンク を付与）
  2. 旧タブ `v13_候補100件` を `v13_候補100件_旧(欠陥あり・使用禁止)` にリネームし、
     先頭に警告行を1行挿入（赤字・太字）。データは1セルも書き換えない（1行下にずれるだけ）
  3. `v13_サマリ・前提` に差し替え記録を追記（末尾ブロック）＋ 冒頭3セルに誘導を追記

安全設計（agents/general_affairs/memory/knowledge_gsheet_nondestructive_tabs.md の型）:
  - PREFIX ガード: `v13_` で始まらないタブは削除・改名・書き込みの対象外（assert で停止）
  - 実行前に本スクリプト自身がブック全体を走査し、**数式セル / 名前付き範囲 / 保護範囲が
    1つでもあれば行挿入を行わず中止**（行挿入はセルのアドレスをずらすため）
  - 実行前後でブック全体を FORMULA レンダリングでスナップショットし、既存セルを全突合
  - 冪等: 2回目以降の実行でも同じ結果になる（タブ再作成 / リネーム済みスキップ /
    警告行の二重挿入なし / サマリ追記ブロックは同じ位置に上書き）

実行: python3 replace_sheet_v13_clean.py [--dry-run]
"""
import csv
import datetime
import json
import re
import sys
import time
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4"
OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1] / "agent_output" / "T-20260817-005"   # スナップショット置き場
CSV_PATH = OUT / "candidates_v13_top100_clean.csv"

PREFIX = "v13_"
TAB_OLD = PREFIX + "候補100件"
TAB_OLD_RENAMED = PREFIX + "候補100件_旧(欠陥あり・使用禁止)"
TAB_NEW = PREFIX + "候補100件_修正版"
TAB_INFO = PREFIX + "サマリ・前提"

WARN_TEXT = (
    "⚠️ このタブは出品者数の取り違え（COUNT_NEW＝オファー数）を含む欠陥版です。"
    "使用しないでください。正しいものは `v13_候補100件_修正版` です（2026-08-24 差し替え）"
)
INFO_MARK = "■ 2026-08-24 差し替え（クリーン版への入れ替え記録）"
RED = {"textFormat": {"bold": True, "foregroundColor": {"red": 0.8, "green": 0.0, "blue": 0.0}}}

AMAZON_TMPL = "https://www.amazon.co.jp/dp/{}"
KEEPA_TMPL = "https://keepa.com/#!product/5-{}"      # 5 = amazon.co.jp
COL_AMAZON = "Amazonページ"                            # 2026-08-23 社長裁可の統一名
COL_KEEPA = "Keepaリンク"
HEADER_ALIAS = {                                       # 旧世代CSVを食っても統一名で書く
    "Amazonページリンク": COL_AMAZON,
    "Amazonリンク": COL_AMAZON,
    "代表商品リンク": COL_AMAZON,
    "KeepaリンクURL": COL_KEEPA,
}

# --- リスク区分の機械判定（build_gsheet_v13.py と同じ規則）-----------------
LI_PSE_PAT = re.compile(
    "|".join([
        "モバイルバッテリー", "ポータブル電源", "充電器", "チャージャー", "チャージャ",
        "ACアダプタ", "ACアダプター", "電源タップ", "電源", "バッテリー", "リチウム",
        "急速充電", "充電ステーション", "充電スタンド", "蓄電",
        r"[Cc]harger", r"[Bb]attery", r"[Pp]ower ?[Bb]ank", r"[Pp]owerbank",
    ])
)
KADEN_PREFIX = "家電＆カメラ"


def risk_class(name: str, category: str) -> str:
    blob = f"{name} {category}"
    if LI_PSE_PAT.search(blob):
        return "リチウム/PSE"
    if category.startswith(KADEN_PREFIX):
        return "要確認"
    return ""


def a1_col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# --- シート操作の共通部品 ---------------------------------------------------
def retry(fn, label, tries=4):
    for a in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if a == tries - 1:
                raise
            print(f"  retry {label}: {type(e).__name__}", flush=True)
            time.sleep(5 * (a + 1))


def snapshot(sh):
    """FORMULA レンダリングでブック全体を読む（数式を見逃さないため）。"""
    snap = {}
    for ws in sh.worksheets():
        snap[ws.title] = retry(
            lambda ws=ws: ws.get_all_values(value_render_option="FORMULA"), f"read {ws.title}"
        )
        time.sleep(0.4)
    return snap


def guard_no_references(sh, snap):
    """行挿入はセルのアドレスをずらす。参照が1つでもあれば挿入しない。"""
    meta = sh.fetch_sheet_metadata(
        params={"fields": "namedRanges,sheets.properties,sheets.protectedRanges,sheets.basicFilter"}
    )
    named = meta.get("namedRanges", [])
    protected = [s["properties"]["title"] for s in meta.get("sheets", []) if s.get("protectedRanges")]
    filters = [s["properties"]["title"] for s in meta.get("sheets", []) if s.get("basicFilter")]
    formulas = [
        f"{t}!R{ri}C{ci}"
        for t, rows in snap.items()
        for ri, row in enumerate(rows, 1)
        for ci, c in enumerate(row, 1)
        if isinstance(c, str) and c.startswith("=")
    ]
    print(f"走査: 数式 {len(formulas)}件 / 名前付き範囲 {len(named)}件 / "
          f"保護範囲 {protected} / 基本フィルタ {filters}", flush=True)
    return not (formulas or named or protected or filters)


def write_block(sh, title, a1, values):
    retry(
        lambda: sh.values_update(
            f"'{title}'!{a1}", params={"valueInputOption": "RAW"}, body={"values": values}
        ),
        f"write {title}@{a1}",
    )


def fresh_tab(sh, title, rows, cols):
    """同名タブがあれば作り直す。PREFIX 以外のタブには絶対に触らない。"""
    assert title.startswith(PREFIX), f"既存タブの削除は禁止: {title}"
    existing = {w.title: w for w in sh.worksheets()}
    if title in existing:
        sh.del_worksheet(existing[title])
    return sh.add_worksheet(title=title, rows=max(rows, 10), cols=max(cols, 2))


# --- 1) クリーン版タブ ------------------------------------------------------
def build_clean_tab(sh):
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        src_cols = list(reader.fieldnames)
        rows = list(reader)

    cols = [HEADER_ALIAS.get(c, c) for c in src_cols]
    header = ["No", "リスク区分"] + cols
    if COL_AMAZON not in header:
        header.append(COL_AMAZON)
    if COL_KEEPA not in header:
        header.append(COL_KEEPA)

    counts = {"リチウム/PSE": 0, "要確認": 0, "": 0}
    data = []
    for i, r in enumerate(rows, start=1):
        rc = risk_class(r.get("商品名", ""), r.get("カテゴリ", ""))
        counts[rc] += 1
        asin = r.get("ASIN", "")
        rec = dict(zip(cols, [r.get(c, "") for c in src_cols]))
        rec.setdefault(COL_AMAZON, "")
        rec.setdefault(COL_KEEPA, "")
        if not rec[COL_AMAZON] and asin:
            rec[COL_AMAZON] = AMAZON_TMPL.format(asin)
        if not rec[COL_KEEPA] and asin:
            rec[COL_KEEPA] = KEEPA_TMPL.format(asin)
        data.append([i, rc] + [rec.get(c, "") for c in header[2:]])

    ws = fresh_tab(sh, TAB_NEW, len(data) + 5, len(header))
    write_block(sh, TAB_NEW, "A1", [header])
    write_block(sh, TAB_NEW, "A2", data)
    ws.freeze(rows=1)
    ws.format(f"A1:{a1_col(len(header))}1", {"textFormat": {"bold": True}})
    print(f"[1] {TAB_NEW}: {len(data)}行 x {len(header)}列 / リスク区分 {counts}", flush=True)
    return len(data), len(header), counts


# --- 2) 旧タブのリネーム＋警告行 -------------------------------------------
def deprecate_old_tab(sh, can_insert):
    titles = {w.title: w for w in sh.worksheets()}
    ws = titles.get(TAB_OLD) or titles.get(TAB_OLD_RENAMED)
    if ws is None:
        print(f"[2] 旧タブが見つかりません（{TAB_OLD} / {TAB_OLD_RENAMED}）。スキップ", flush=True)
        return False, False
    assert ws.title.startswith(PREFIX), f"PREFIX 外のタブは触らない: {ws.title}"

    renamed = False
    if ws.title == TAB_OLD:
        ws.update_title(TAB_OLD_RENAMED)
        renamed = True
        print(f"[2] リネーム: {TAB_OLD} → {TAB_OLD_RENAMED}", flush=True)
    else:
        print(f"[2] リネーム済み（冪等スキップ）: {ws.title}", flush=True)

    first = retry(lambda: ws.row_values(1), "read row1")
    warned = bool(first) and str(first[0]).startswith("⚠️")
    if warned:
        print("[2] 警告行は挿入済み（冪等スキップ）", flush=True)
    elif not can_insert:
        print("[2] 参照が検出されたため行挿入は行いません（リネームのみ）", flush=True)
    else:
        ws.insert_row([WARN_TEXT], index=1, value_input_option="RAW")
        ws.format(f"A1:{a1_col(ws.col_count)}1", RED)
        ws.freeze(rows=2)   # 警告行＋見出し行を固定
        warned = True
        print("[2] 警告行を1行目に挿入（赤字・太字）／固定行を2行に変更", flush=True)
    return renamed, warned


# --- 3) サマリ・前提の更新 --------------------------------------------------
def update_info_tab(sh, n_rows, n_cols, counts):
    ws = {w.title: w for w in sh.worksheets()}[TAB_INFO]
    assert TAB_INFO.startswith(PREFIX)
    cur = retry(lambda: ws.get_all_values(), "read info")

    block = [
        [INFO_MARK, ""],
        ["何が起きたか",
         "社長のご指摘（ASIN B0DWMPV656 の出品者数が実態と合わない）を起点に、タカシ(IT)が scan_v13.py の"
         "欠陥5件（COUNT_NEW の取り違え ＋ D1〜D4）を修正。クリーン版 top100 に差し替えました。"],
        ["最新の候補リスト", "v13_候補100件_修正版（本ブック内）"],
        ["旧タブの扱い", "v13_候補100件_旧(欠陥あり・使用禁止)。削除せず残していますが、判断には使わないでください。"],
        ["", ""],
        ["■ 修正した5つの欠陥", ""],
        ["COUNT_NEW", "Keepa の COUNT_NEW は『新品オファー数』であり distinct なセラー数ではない。"
                      "1セラーが複数オファーを持つと水増しされる。実セラー数を offers API で数え直し、"
                      "`実セラー数` / `セラー名一覧` / `メーカー直販フラグ` を新設。段0フィルタも追加。"],
        ["D1（過去最安値）", "stats.min は全期間の最小値だった → 期間内最安に修正。さらに 2026-02-23 の"
                            "Keepa 価格定義変更をまたぐため、**境界以降の窓で自前計算**した値を主軸化。"
                            "`参考_365日最安(価格定義混在)` / `価格定義混在` / `採用窓` / `窓差率%` を新設。"],
        ["D2（BuyBox価格）", "実体は新品最安（送料込）だったため `新品最安値(送料込)` に改名（0円案を採用）。"
                            "本物の Buy Box 価格が要る場合は +2トークン/件（3,000件で約5時間）。"],
        ["D3（Amazon本体）", "availabilityAmazon != -1 を除外条件に追加 → 20件が新たに除外。"],
        ["D4（想定月販の分母）", "分母を実セラー数に変更。未検証行と区別できるよう `分母の根拠` 列を新設。"],
        ["", ""],
        ["■ 差し替えの実績（旧 top100 → 修正版 top100）", ""],
        ["入れ替わった銘柄", "36件（旧 top100 から消え、36件が新たに入った）"],
        ["残る64件の順位変動", "中央値 15位 ／ 最大 33位（順位が動かなかったのは6件のみ）"],
        ["1位", "交代（旧 B0FPB5DSB4 → 新 B0GK7MN552）"],
        ["旧 top100 の汚染率", "35.0%（100件を実測し、実セラー数<2 が35件）"],
        ["GO母集団の推定汚染率", "38.7%（標本 n=150・95%信頼区間 およそ31〜46%）"],
        ["修正版の内訳", f"100件すべて 実セラー数2〜3 ／ 想定月販の分母は全件『実セラー数』 ／ "
                        f"消化月数 0.61〜1.00ヶ月 ／ リスク区分 リチウム/PSE {counts['リチウム/PSE']}件・"
                        f"要確認 {counts['要確認']}件"],
        ["", ""],
        ["■ 列名の対応表（旧タブ → 修正版タブ）", ""],
        ["出品者数", "新品オファー数（＋ 実セラー数 / セラー名一覧 / メーカー直販フラグ を新設）"],
        ["BuyBox価格", "新品最安値(送料込)"],
        ["過去1年最安値", "過去最安値(送料込・2026-02-23以降)（＋ 参考_365日最安(価格定義混在) / "
                        "価格定義混在 / 採用窓 / 窓差率% を新設）"],
        ["（新設）", "分母の根拠 … 想定月販の分母が実セラー数か COUNT_NEW かを示す"],
        ["", ""],
        ["■ 次に来るもの（近く母集団を作り直した新リストが出ます）", ""],
        ["D8（母集団の絞りすぎ）", "variationCount=0 の商品が 97,484件あり、母集団から丸ごと落ちていました。"
                                 "**当たり**の指摘です。母集団を作り直す必要があります。"],
        ["D11（レビュー件数フィルタ）", "レビュー件数は offers 無しでは一切返らず、現状の条件では検証不能。"
                                     "フィルタの是非を含めて見直します。"],
        ["したがって", "**本タブの修正版 top100 も『暫定』です。** D8・D11 の対応後に母集団を作り直した"
                     "新リストが出る予定です。メーカーへの実連絡は、その新リストを見てからでも遅くありません。"],
        ["", ""],
        ["■ 正直な注意（差し替え後も残る限界）", ""],
        ["実セラー数の実測範囲", "4,002行のうち実測したのは355件。top100 を確定させるには十分ですが、"
                              "**GO 2,383件のリスト全体はまだ信用できません**（全件確定に約11時間）。"],
        ["価格定義の混在", "修正版100件のうち93件が『価格定義混在=はい』。2026-02-23 以降の窓で計算した値を"
                        "採用しています（1件のみ境界後の記録が無く繰越）。"],
        ["段3（出品制限）", "従来どおり機械判定できません。発注前のワンクリック解除テストは必須のままです。"],
        ["", ""],
        ["■ 元データ（2026-08-24 時点）", ""],
        ["修正版 top100 CSV", "workspace/output/deliverables/T-20260817-005/candidates_v13_top100_clean.csv"],
        ["欠陥レポート", "workspace/output/deliverables/T-20260817-005/seller-count-defect-report.md / .html"],
        ["実セラー数モジュール", "workspace/output/deliverables/T-20260817-005/seller_count.py"],
        ["スキャナ（修正版）", "workspace/output/deliverables/T-20260817-005/scan_v13.py"],
        ["本差し替えスクリプト", "workspace/output/deliverables/T-20260817-005/replace_sheet_v13_clean.py"],
        ["差し替え実施", f"2026-08-24 マリエ(庶務) ／ 修正版タブ {n_rows}行 x {n_cols}列"],
    ]

    # 冪等: マーカー行があればそこから上書き、無ければ末尾に追記
    start = None
    for i, row in enumerate(cur, start=1):
        if row and row[0] == INFO_MARK:
            start = i
            break
    if start is None:
        start = len(cur) + 2
        print(f"[3] {TAB_INFO}: 末尾 {start}行目から追記", flush=True)
    else:
        print(f"[3] {TAB_INFO}: 既存ブロック({start}行目〜)を上書き（冪等）", flush=True)

    need_rows = start + len(block) + 2
    if ws.row_count < need_rows:
        ws.add_rows(need_rows - ws.row_count)
    write_block(sh, TAB_INFO, f"A{start}", block)
    # 旧ブロックが長かった場合の残骸を消す
    tail = start + len(block)
    if len(cur) >= tail:
        write_block(sh, TAB_INFO, f"A{tail}", [["", ""] for _ in range(len(cur) - tail + 1)])

    # 冒頭の誘導（挿入せず、既存の空行と見出しセルを使う）
    write_block(sh, TAB_INFO, "A1", [
        ["メーカー仕入れ v1.3 候補100件（T-20260817-005）【2026-08-24 修正版に差し替え済み】", ""],
    ])
    write_block(sh, TAB_INFO, "B2", [["2026-08-23（初版）／2026-08-24 クリーン版へ差し替え"]])
    write_block(sh, TAB_INFO, "A5", [[
        "⚠️ 最新の候補リストは『v13_候補100件_修正版』タブです",
        "旧『v13_候補100件_旧(欠陥あり・使用禁止)』は判断に使わないでください。経緯は本タブ末尾"
        "「2026-08-24 差し替え」を参照。",
    ]])
    ws.format("A1:B1", {"textFormat": {"bold": True}})
    ws.format("A5:B5", RED)
    ws.format(f"A{start}:B{start}", RED)
    return start, len(block)


def main():
    dry = "--dry-run" in sys.argv
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    print("opened:", sh.title, flush=True)

    before = snapshot(sh)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / f"sheet_backup_before_v13clean.{ts}.json").write_text(
        json.dumps(before, ensure_ascii=False), encoding="utf-8"
    )
    print("既存タブ(保護):", list(before), flush=True)
    can_insert = guard_no_references(sh, before)

    if dry:
        print("dry-run: 書き込みなしで終了", flush=True)
        return

    n_rows, n_cols, counts = build_clean_tab(sh)
    renamed, warned = deprecate_old_tab(sh, can_insert)
    info_start, info_len = update_info_tab(sh, n_rows, n_cols, counts)

    # --- 事後検証: 既存セルの全突合 ---------------------------------------
    time.sleep(2)
    after = snapshot(sh)
    (WORK / f"sheet_backup_after_v13clean.{ts}.json").write_text(
        json.dumps(after, ensure_ascii=False), encoding="utf-8"
    )

    problems = []
    for title, rows in before.items():
        if title == TAB_OLD:
            new_rows = after.get(TAB_OLD_RENAMED if warned or renamed else TAB_OLD)
            if new_rows is None:
                problems.append(f"{title}: 旧タブが消えた")
                continue
            shifted = new_rows[1:] if warned else new_rows
            if shifted != rows:
                problems.append(f"{title}: 警告行を除いたデータが一致しない")
            if warned and not str(new_rows[0][0]).startswith("⚠️"):
                problems.append(f"{title}: 1行目が警告行でない")
        elif title == TAB_INFO:
            allowed = {(1, 1), (2, 2), (5, 1), (5, 2)}
            new_rows = after[title]
            for ri in range(1, min(len(rows), info_start - 1) + 1):
                for ci in range(1, 3):
                    o = rows[ri - 1][ci - 1] if ci - 1 < len(rows[ri - 1]) else ""
                    n = new_rows[ri - 1][ci - 1] if ri - 1 < len(new_rows) and ci - 1 < len(new_rows[ri - 1]) else ""
                    if o != n and (ri, ci) not in allowed:
                        problems.append(f"{title}!R{ri}C{ci}: {o!r} → {n!r}")
        else:
            if after.get(title) != rows:
                problems.append(f"{title}: 既存タブの内容が変わった")

    print("\n=== 事後検証 ===", flush=True)
    print("タブ一覧(before):", list(before), flush=True)
    print("タブ一覧(after) :", list(after), flush=True)
    if problems:
        print("!! 差分あり:", flush=True)
        for p in problems:
            print("   ", p, flush=True)
        sys.exit(2)
    print("既存セルの差分: 0件（意図した変更のみ）", flush=True)
    print("URL:", sh.url, flush=True)


if __name__ == "__main__":
    main()
