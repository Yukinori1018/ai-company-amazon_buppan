#!/usr/bin/env python3
"""判定台帳シートのタブ『買う候補_20261004』を更新する。

    python3 push_buy_candidates.py --dry-run    # 書き込まずに内容を確認
    python3 push_buy_candidates.py              # 実際に書く

🔴 **古い行は消しません。新しい候補をヘッダの直下に差し込みます。**
既存16行はカズヨが実画面で確認して `実画面確認` / `ゲートの根拠(実画面)` を埋めた行で、
**機械が上書きしてはいけません**（CLAUDE.md §3.3-16）。`insert_rows` で上に積むので、
既存行は下にずれるだけで中身は触りません。

列は既存の30列をそのまま使い、価格履歴とカレンダーの6列だけ**右端に足します**
（足すのは安全側。既存列の順を動かすと条件付き書式が意味を失います）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ledger_sheet                     # noqa: E402
import score_20261004 as SC             # noqa: E402

TAB = "買う候補_20261004"

# 既存30列（2026-10-04 に実シートから読んだ順。**並べ替えない**）。
EXISTING = ["順位", "ASIN", "商品名", "Amazon URL", "売価(円)", "過去1ヶ月の販売数",
            "売れ筋ランク(90日平均)", "セラー数", "Amazon本体の有無", "カートの販売元",
            "季節", "等級", "1個手残り(円)", "利益率(%)", "悲観利益率(%)",
            "Amazon側のセット数", "卸の1点あたり原価(税込)", "買う卸の口",
            "発注点数(Amazon何個)", "発注する卸の点数", "発注額(円・税込)", "卸率(売価比)",
            "売り切る月数", "ゲート種別", "購入元の名前", "購入先URL", "実画面確認",
            "判定理由(新)", "最低価格(10/4実測)", "ゲートの根拠(実画面)"]

# 2026-10-04 に右端へ足す6列（価格履歴とカレンダー）。
ADDED = ["販売価格(90日中央値)", "保守値(90日の下位25%)", "価格の傾き(%/30日)",
         "販売開始日", "売り切り目標月", "季節の窓"]

HEADER = EXISTING + ADDED


def to_row(rank: int, s: dict) -> list:
    r, lv, e, pl = s["row"], s.get("price"), s.get("econ"), s.get("plan")
    row = {
        "順位": rank, "ASIN": s["asin"], "商品名": r["商品名"][:70],
        "Amazon URL": r.get("AmazonURL"),
        "売価(円)": (lv.sell_for_profit if lv else ""),
        "過去1ヶ月の販売数": (f"{s['monthlySold']}個" if s.get("monthlySold")
                              else "表示なし（月50個未満）"),
        "売れ筋ランク(90日平均)": (f"{s['rank']:,}位（現在）" if s.get("rank") else "未取得"),
        "セラー数": r.get("セラー数"), "Amazon本体の有無": r.get("Amazon本体の有無"),
        "カートの販売元": s.get("カート保持者"),
        "季節": (s["season"].verdict if s.get("season") else ""),
        "等級": s["等級"],
        "Amazon側のセット数": (int(s["n_set"]) if s.get("n_set") else ""),
        "卸の1点あたり原価(税込)": r.get("卸の1点あたり原価(税込)"),
        "買う卸の口": r.get("買う卸の口"),
        "発注する卸の点数": r.get("発注する卸の点数"),
        "卸率(売価比)": (f"{e.cost_ratio_pct}%" if e else ""),
        "ゲート種別": r.get("ゲート種別"), "購入元の名前": r.get("購入元の名前"),
        "購入先URL": r.get("購入先URL"),
        # 🔴 機械が埋めてよいのは「機械判定のみ」。人の確認結果は人が書きます。
        # 🔴 機械が埋めてよいのは「機械判定のみ」。そこに**次に人が何を見ればよいか**を
        #    添える。人の確認結果（ゲートの根拠・キーゾンの実数）は人が書く欄のまま。
        "実画面確認": (ledger_sheet.MACHINE_ONLY if s["判定"] == "GO"
                       else f"{ledger_sheet.MACHINE_ONLY}／🔴実売をキーゾンで確認"),
        "判定理由(新)": " ／ ".join(f"{n}. {why}" for n, st, why in s["gates"]
                                   if st != "PASS")[:900] or "全ゲート PASS",
        "最低価格(10/4実測)": SC.SCREEN_PRICES.get(s["asin"], ""),
        "ゲートの根拠(実画面)": "",     # ← カズヨが書く欄。機械は空のまま
    }
    if e:
        row.update({"1個手残り(円)": e.net_per_unit, "利益率(%)": e.net_margin_pct,
                    "悲観利益率(%)": e.worst_margin_pct,
                    "発注点数(Amazon何個)": e.qty, "発注額(円・税込)": e.order_total,
                    "売り切る月数": (f"{e.months_to_sell}ヶ月" if e.months_to_sell
                                     else "未確定（月販非表示）")})
    if lv:
        row.update({"販売価格(90日中央値)": lv.median90,
                    "保守値(90日の下位25%)": lv.p25_90,
                    "価格の傾き(%/30日)": lv.slope_pct_per_30d})
    if pl:
        row.update({"販売開始日": pl.listing_starts_on.strftime("%Y-%m-%d"),
                    "売り切り目標月": pl.sellout_month,
                    "季節の窓": pl.season_window})
    return [row.get(c, "") if row.get(c) is not None else "" for c in HEADER]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args(argv)

    scored = SC.score_all()
    go, pend, _over = SC.candidates(scored)
    cands = go + pend
    top = cands[:a.top]
    print(f"機械判定 GO {len(go)}件 ／ 実売だけ人の確認待ち {len(pend)}件")
    rows = [to_row(i + 1, s) for i, s in enumerate(top)]
    print(f"候補 {len(cands)}件 → 上に差し込むのは {len(rows)}行")

    if a.dry_run:
        for r in rows[:5]:
            print(r[:14])
        return 0
    if not rows:
        print("差し込む行がありません（候補0件）。シートは触りません。")
        return 0

    ws = ledger_sheet._client().open_by_key(ledger_sheet.SHEET_ID).worksheet(TAB)
    cur = ws.row_values(1)
    if cur[:len(EXISTING)] != EXISTING:
        print("⚠️ 既存のヘッダが想定と違います。**書き込みません。**")
        print(f"  シート: {cur}")
        return 1
    if len(cur) < len(HEADER):                     # 右端の6列を足す
        ws.update(values=[HEADER], range_name="A1")
        print(f"ヘッダに {len(HEADER) - len(cur)}列 足しました: {ADDED}")
    # ヘッダ直下に差し込む（既存行は下にずれるだけ・中身は触らない）。
    ws.insert_rows(rows, row=2, value_input_option="USER_ENTERED")
    print(f"タブ『{TAB}』の2行目に {len(rows)}行 差し込みました"
          f"（既存行は {len(rows)}行ぶん下へ。消していません）")
    print(f"https://docs.google.com/spreadsheets/d/{ledger_sheet.SHEET_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
