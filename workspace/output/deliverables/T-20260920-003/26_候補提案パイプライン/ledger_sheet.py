#!/usr/bin/env python3
"""商品判定台帳スプレッドシートへの追記（冪等）。

| 項目 | 値 |
|---|---|
| タイトル | 商品判定台帳_Amazon物販事業 |
| Drive file id | 1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I |
| タブ | 判定台帳（1枚。増やさない） |
| 書き込み | SA `sheets-writer@claude-session-sheets.iam.gserviceaccount.com`（編集者共有済み） |

**列は32列で固定です。増やさない・減らさない・並べ替えない。**
条件付き書式（AB列＝判定を 緑／赤／黄）はシート側に保存されているので、
列がずれると色が意味を失います。

**シートが正**です。リポ内にミラーCSVは作りません（二重管理の事故源）。
卸率・購入先URL などの会員限定の取引条件は**シートにだけ**入れます。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SHEET_ID = "1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I"
TAB = "判定台帳"
CREDENTIALS = Path("~/.config/claude-session-sheets/credentials.json").expanduser()
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive")

# 32列。この順・この名前（memory: reference_product_judgment_ledger_sheet）。
COLUMNS = [
    "判定日", "チケットID", "ASIN", "商品名", "ブランド", "Amazon URL", "Amazon価格",
    "キーゾン 平均月販", "キーゾン 過去1ヶ月", "キーゾン 過去2ヶ月", "キーゾン 過去3ヶ月",
    "新品出品者数(画面実数)", "Amazon本体の有無", "カートの販売元", "本体365日在庫率",
    "ゲート種別", "ゲート可否", "購入元の名前", "卸サイト", "購入先URL", "卸率(売価比)",
    "発注点数", "発注額(円・税込)", "1個粗利(円)", "利益率(%)", "売り切る月数",
    "半値処分時の損失(円)", "判定", "判定理由", "確認方法", "確認者", "発注状況",
]

COL_ASIN = COLUMNS.index("ASIN")
COL_VERDICT = COLUMNS.index("判定")
COL_METHOD = COLUMNS.index("確認方法")

# §3.3 の実画面確認（Chrome＋キーゾン）は人がやります。機械判定をこう名乗ります。
MACHINE_ONLY = "機械判定のみ・実画面未確認"

UNKNOWN_CELL = "未確認"


@dataclass
class LedgerState:
    """シートの現況。停止条件の判定に使う。"""

    asins: dict[str, int]          # ASIN → 行番号（1始まり・ヘッダは1行目）
    machine_go_count: int          # 判定=GO かつ 確認方法=機械判定のみ の件数
    total_rows: int
    # 人（カズヨ）が実画面で確認した行の ASIN。**機械が上書きしてはいけない。**
    human_verified: set = None

    def is_human_verified(self, asin: str) -> bool:
        return bool(self.human_verified) and asin in self.human_verified


def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS") or str(CREDENTIALS)
    if not Path(path).exists():
        raise SystemExit(
            f"サービスアカウントの鍵が見つかりません: {path}\n"
            "（環境変数 GOOGLE_SHEETS_CREDENTIALS で場所を指定できます）")
    return gspread.authorize(Credentials.from_service_account_file(path, scopes=list(SCOPES)))


def open_tab():
    return _client().open_by_key(SHEET_ID).worksheet(TAB)


def read_state(ws=None) -> LedgerState:
    ws = ws or open_tab()
    values = ws.get_all_values()
    if not values:
        raise SystemExit("シートが空です。ヘッダ32列が消えていないか確認してください。")
    header = values[0]
    if len(header) < len(COLUMNS) or header[:len(COLUMNS)] != COLUMNS:
        raise SystemExit(
            "シートの列が想定と違います。列を勝手に増減しない運用です。\n"
            f"想定: {COLUMNS}\n実際: {header}")

    asins: dict[str, int] = {}
    machine_go = 0
    human: set[str] = set()
    for i, row in enumerate(values[1:], start=2):
        asin = (row[COL_ASIN] if len(row) > COL_ASIN else "").strip()
        if asin:
            asins.setdefault(asin, i)
        verdict = (row[COL_VERDICT] if len(row) > COL_VERDICT else "").strip()
        method = (row[COL_METHOD] if len(row) > COL_METHOD else "").strip()
        machine = MACHINE_ONLY.split("・")[0] in method
        if verdict == "GO" and machine:
            machine_go += 1
        if asin and method and not machine:
            human.add(asin)
    return LedgerState(asins=asins, machine_go_count=machine_go,
                       total_rows=len(values) - 1, human_verified=human)


def append_rows(rows: list[list], ws=None) -> int:
    """末尾に追記する。1件ずつ API を叩かず1回でまとめる。"""
    if not rows:
        return 0
    ws = ws or open_tab()
    ws.append_rows(rows, value_input_option="USER_ENTERED",
                   insert_data_option="INSERT_ROWS", table_range="A1")
    return len(rows)


class HumanRowProtected(RuntimeError):
    """人が実画面で確認した行を機械が上書きしようとした。"""


def update_row(row_number: int, row: list, ws=None, state: "LedgerState | None" = None) -> None:
    """既にある ASIN の行を上書きする（再判定したとき）。

    ⚠️ **人が実画面で確認した行は上書きしません。**
    2026-09-30、`--update-existing` でカズヨの実画面確認の結果（B0DJNX12KZ・B0FN3NWKYZ）を
    機械判定で潰しました。機械が人の確認を消すのは、消した事実さえ残らないので最悪です。
    """
    asin = row[COL_ASIN] if len(row) > COL_ASIN else ""
    if state is not None and state.is_human_verified(asin):
        raise HumanRowProtected(
            f"{asin} は人が実画面で確認した行です（確認方法が機械判定のみではない）。"
            "機械判定で上書きしません。直す必要があれば人が直してください。")
    ws = ws or open_tab()
    ws.update(f"A{row_number}:AF{row_number}", [row], value_input_option="USER_ENTERED")


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
