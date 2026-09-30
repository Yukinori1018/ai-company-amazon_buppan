#!/usr/bin/env python3
"""仕入れ先商品リスト（Googleシート）— **仕入れ先側の商品台帳**。

| 項目 | 値 |
|---|---|
| タイトル | 仕入れ先商品リスト_Amazon物販事業 |
| Drive file id | 14VnMuvVDYNFlP0uer5y9E2atXnKbNWEHsGMrKk_xl68 |
| タブ | 仕入れ先商品（1枚。増やさない） |

判定台帳（`1ppyXCnp2S…`）とは**別物です。混ぜないこと。**

| | 判定台帳 | 仕入れ先商品リスト（これ） |
|---|---|---|
| 1行の意味 | **Amazon の ASIN 1つについての判定** | **仕入れ先で買える商品1つ** |
| 主キー | ASIN | 仕入れ先 ＋ JAN |
| 増え方 | 人の確認が進むと GO/NO-GO が確定する | 仕入れ先を回るほど積み上がる（消えない資産） |
| 使い道 | 発注の可否 | **Amazon 起点で出た JAN を「買えるか」で引く索引** |

これが何のためにあるか（2026-09-30 社長指示）
------------------------------------------
> 「進めて下さい。感覚的にはスーパーデリバリーで探す方が得策と感じています。
>  **仕入れ先起点のリストを積み上げて下さい。**」

Amazon 起点（CLAUDE.md §3.3-9）で候補を出す流れとは**別の資産**です。
Amazon 起点の歩留まりがどうであれ、**「当社が買える商品の一覧」は減りません**。
ここが埋まっていれば、Amazon 側で出た JAN を1行引くだけで「買えるか」が分かります。

冪等の鍵は「仕入れ先 ＋ JAN」
--------------------------
同じ JAN を同じ仕入れ先で二重登録しません。**ただし仕入れ先が違えば別行にします** ──
同じ商品を NETSEA と SD の両方で買えるなら、それは安い方を選べるという情報そのものです。
同一の仕入れ先で入り数の違う口（SD の S1/S2）が複数あるときは、
**入り数の小さい口を採り、残りは備考に書きます**（試し買いの下限が判断に効くため）。

⚠️ 卸価格はこのシートにだけ入れます。**リポ内の成果物には書きません**（PUBLIC リポ）。
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path

SHEET_ID = "14VnMuvVDYNFlP0uer5y9E2atXnKbNWEHsGMrKk_xl68"
TAB = "仕入れ先商品"
CREDENTIALS = Path("~/.config/claude-session-sheets/credentials.json").expanduser()
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive")

# 17列。この順・この名前（2026-09-30 カズヨ指定）。増やさない・並べ替えない。
COLUMNS = [
    "登録日", "仕入れ先", "出展企業・サプライヤー名", "商品名", "品番", "JAN",
    "卸価格(1点・税込)", "入り数(1セット◯点)", "最小ロット", "在庫状況",
    "ネット販売可否", "消費者直送可否", "商品URL", "卸価格の承認状態",
    "Amazonで該当ASINがあるか", "該当ASIN", "備考",
]

I_SOURCE = COLUMNS.index("仕入れ先")
I_JAN = COLUMNS.index("JAN")
I_ASIN = COLUMNS.index("該当ASIN")
I_HAS_ASIN = COLUMNS.index("Amazonで該当ASINがあるか")

UNKNOWN = "未確認"

# 卸価格の承認状態に入れてよい値。**「無し」「不可」は入れません**（申請すれば見えるので）。
APPROVAL_OK = "承認済み"
APPROVAL_PENDING = "卸価格未承認"       # 申請すれば見える。**NO-GO ではない**
APPROVAL_UNKNOWN = UNKNOWN


@dataclass
class Row:
    """1行。**空欄を作りません**（§3.2）。分からないものは「未確認」と書きます。"""

    source: str                       # NETSEA / SD
    supplier: str = UNKNOWN
    name: str = UNKNOWN
    code: str = UNKNOWN               # 品番（SD品番 or メーカー品番 or NETSEA の商品ID）
    jan: str = ""
    wholesale_incl: int | None = None  # 1点・税込。**None は「不明」。0 に畳まない**
    units_per_set: int | None = None
    min_lot: int | None = None
    stock: str = UNKNOWN
    net_sales_ok: str = UNKNOWN
    direct_ship_ok: str = UNKNOWN
    url: str = UNKNOWN
    approval: str = APPROVAL_UNKNOWN
    asin: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.jan)

    def to_cells(self, today: str | None = None) -> list:
        today = today or dt.date.today().isoformat()
        return [
            today, self.source, self.supplier or UNKNOWN, self.name or UNKNOWN,
            self.code or UNKNOWN, self.jan,
            self.wholesale_incl if self.wholesale_incl else UNKNOWN,
            self.units_per_set if self.units_per_set else UNKNOWN,
            self.min_lot if self.min_lot else UNKNOWN,
            self.stock or UNKNOWN, self.net_sales_ok or UNKNOWN,
            self.direct_ship_ok or UNKNOWN, self.url or UNKNOWN,
            self.approval or APPROVAL_UNKNOWN,
            "あり" if self.asin else UNKNOWN, self.asin or UNKNOWN,
            " / ".join(self.notes) if self.notes else "",
        ]


# ── 仕入れ先ごとの変換（純関数。テストできます）────────────────────────────


def from_netsea_index(jans: dict, tax_rate: float = 1.10) -> list[Row]:
    """`discover.build_netsea_index()` の JAN 索引 → 行。

    索引の `unit_price_excl` は **1点の税抜**（T-20260831-006 の実測解釈）。
    シートは税込で持つので `×1.10` します。軽減税率の品は 1.08 ですが、
    索引に税区分が入っていないので**一律 1.10（保守側）**にし、備考に書きます。

    `deal_net_shop_flag == 'Y'` のものしか索引に入っていないので、ネット販売可否は「○」。
    **消費者直送可否は NETSEA の API に無いので「未確認」**（推測で埋めない）。
    """
    out: list[Row] = []
    for jan, w in (jans or {}).items():
        price = w.get("unit_price_excl")
        notes = ["卸価格は税抜×1.10で税込化"]
        tax = w.get("tax_class")
        if tax not in (None, "", 0, "0"):
            # 0/1/99 の意味が公式スキーマに書かれていないので**推測で 1.08 にしません**。
            # 高め（1.10）に出しておいて、番号を備考に残します。
            notes.append(f"税区分 {tax}（軽減税率なら税込は過大）")
        out.append(Row(
            source="NETSEA",
            supplier=w.get("supplier_name") or UNKNOWN,
            name=w.get("title") or UNKNOWN,
            code=str(w.get("shop_id") or UNKNOWN),
            jan=str(jan),
            wholesale_incl=int(round(price * tax_rate)) if price else None,
            units_per_set=1,                       # NETSEA の price は1点の値段
            min_lot=w.get("min_lot_units") or 1,
            stock=w.get("stock") or UNKNOWN,
            net_sales_ok="○",                      # 索引に入る条件そのもの
            direct_ship_ok=UNKNOWN,                # API に項目が無い
            url=w.get("supplier_url") or UNKNOWN,
            approval=APPROVAL_OK,                  # 承認済みサプライヤーしか API に出ない
            notes=notes,
        ))
    return out


def from_sd_sets(sets: list, asin_by_jan: dict | None = None) -> list[Row]:
    """`superdelivery.parse_product()` の結果 → 行。

    SD は **卸価格だけが会員＋承認待ち**なので、値が無い行は `未確認` / `卸価格未承認` で
    積みます。**捨てません。**JAN・入り数・販売規制という、判定に直接効く情報が載っています。
    """
    asin_by_jan = asin_by_jan or {}
    out: list[Row] = []
    for s in sets or []:
        notes = list(getattr(s, "notes", []) or [])
        if s.retail_excl:
            notes.append(f"上代(税抜) {s.retail_excl}")
        out.append(Row(
            source="SD",
            supplier=(s.supplier.name if s.supplier else UNKNOWN),
            name=s.name or UNKNOWN,
            code=s.sd_code or (s.maker_code or UNKNOWN),
            jan=s.jan or "",
            wholesale_incl=(int(round(s.wholesale_price_excl * 1.10))
                            if s.wholesale_price_excl else None),
            units_per_set=s.units_per_set,
            min_lot=1,                             # SD は1セット単位。実額は要ログイン
            stock=s.stock or UNKNOWN,
            net_sales_ok=s.net_sales_ok or UNKNOWN,
            direct_ship_ok=s.direct_ship_ok or UNKNOWN,
            url=s.url or UNKNOWN,
            approval=s.approval or APPROVAL_UNKNOWN,
            asin=asin_by_jan.get(s.jan, ""),
            notes=notes,
        ))
    return out


def dedupe(rows: list[Row]) -> list[Row]:
    """同じ (仕入れ先, JAN) は1行に畳む。**入り数の小さい口を残す。**

    残した口の情報だけを書いて残りを黙って捨てると、「1セット3点しか無い」を
    「1点で買える」と読み違えます。だから落とした口は備考に書きます。
    """
    best: dict[tuple[str, str], Row] = {}
    for r in rows:
        if not r.jan:
            continue
        cur = best.get(r.key)
        if cur is None:
            best[r.key] = r
            continue
        a = r.units_per_set or 10 ** 6
        b = cur.units_per_set or 10 ** 6
        keep, drop = (r, cur) if a < b else (cur, r)
        if drop.units_per_set:
            keep.notes.append(f"他の口: 1セット{drop.units_per_set}点")
        best[r.key] = keep
    return list(best.values())


# ── シート ────────────────────────────────────────────────────────────────


def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS") or str(CREDENTIALS)
    if not Path(path).exists():
        raise SystemExit(f"サービスアカウントの鍵が見つかりません: {path}")
    return gspread.authorize(Credentials.from_service_account_file(path, scopes=list(SCOPES)))


def open_tab(create: bool = False):
    sh = _client().open_by_key(SHEET_ID)
    try:
        return sh.worksheet(TAB)
    except Exception:                              # noqa: BLE001 - gspread の例外型に依存しない
        if not create:
            raise
        ws = sh.sheet1
        ws.update_title(TAB)
        return ws


def ensure_header(ws=None) -> None:
    """ヘッダ17列を保証する。既にあれば触りません（列の並びは固定）。"""
    ws = ws or open_tab(create=True)
    values = ws.get_all_values()
    if values and values[0][:len(COLUMNS)] == COLUMNS:
        return
    if values and any(any(c for c in r) for r in values[1:]):
        raise SystemExit(
            "データが入っているのにヘッダが想定と違います。人が確認してください。\n"
            f"想定: {COLUMNS}\n実際: {values[0] if values else '(空)'}")
    ws.resize(rows=max(1000, ws.row_count), cols=len(COLUMNS))
    ws.update(values=[COLUMNS], range_name="A1", value_input_option="USER_ENTERED")
    sh = ws.spreadsheet
    sh.batch_update({"requests": [
        {"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"setBasicFilter": {"filter": {"range": {
            "sheetId": ws.id, "startRowIndex": 0, "endColumnIndex": len(COLUMNS)}}}},
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": .92, "green": .92, "blue": .92}}},
            "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        # 🔴 JAN 列は必ず TEXT。**数値として入ると先頭の0が消えます。**
        # 2026-09-30、`USER_ENTERED` で 088381753180 が 88381753180 になり、
        # 冪等の鍵が一致せず**同じ商品を二重登録しました**（59件が桁落ち・12件が重複）。
        # 「JAN は数字だから数値でいい」は間違いで、**JAN は数字の並びであって数ではありません**。
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startColumnIndex": I_JAN,
                      "endColumnIndex": I_JAN + 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
            "fields": "userEnteredFormat.numberFormat"}},
    ]})


def read_keys(ws=None) -> dict[tuple[str, str], int]:
    """既にある (仕入れ先, JAN) → 行番号。冪等のための現況読み。"""
    ws = ws or open_tab(create=True)
    values = ws.get_all_values()
    if not values:
        return {}
    header = values[0]
    if header[:len(COLUMNS)] != COLUMNS:
        raise SystemExit(f"列が想定と違います。\n想定: {COLUMNS}\n実際: {header}")
    keys: dict[tuple[str, str], int] = {}
    malformed: list[str] = []
    for i, row in enumerate(values[1:], start=2):
        src = (row[I_SOURCE] if len(row) > I_SOURCE else "").strip()
        jan = (row[I_JAN] if len(row) > I_JAN else "").strip()
        if src and jan:
            keys.setdefault((src, jan), i)
            if len(jan) not in (12, 13) or not jan.isdigit():
                malformed.append(jan)
    if malformed:
        # **黙って通さない。**桁落ちした JAN は冪等の鍵として使えず、二重登録になります。
        print(f"⚠️ JAN の形が壊れている行が {len(malformed)}件あります（例 {malformed[:3]}）。"
              "JAN 列が TEXT になっているか確認してください（数値化で先頭の0が消えます）")
    return keys


def append(rows: list[Row], ws=None, chunk: int = 2000, log=print) -> int:
    """未登録の行だけ追記する。**既にある (仕入れ先, JAN) は触りません。**

    人が卸価格を手で埋めた行を機械が上書きしないための、いちばん簡単な担保です
    （上書きの経路を作らない）。
    """
    ws = ws or open_tab(create=True)
    ensure_header(ws)
    have = read_keys(ws)
    fresh = [r for r in dedupe(rows) if r.key not in have]
    log(f"仕入れ先商品リスト: 既存 {len(have):,}行 / 今回 {len(rows):,}件 → 新規 {len(fresh):,}行")
    today = dt.date.today().isoformat()
    for i in range(0, len(fresh), chunk):
        batch = [r.to_cells(today) for r in fresh[i:i + chunk]]
        ws.append_rows(batch, value_input_option="USER_ENTERED",
                       insert_data_option="INSERT_ROWS", table_range="A1")
        log(f"  {i + len(batch):,}/{len(fresh):,} 行 書き込み")
    return len(fresh)


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
