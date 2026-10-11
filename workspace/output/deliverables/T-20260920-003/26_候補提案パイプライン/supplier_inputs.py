#!/usr/bin/env python3
"""仕入れ先の商品一覧を `supplier_screen.py` の入力 CSV（標準形）に直す口。通信0。

2026-10-11 タカシ（T-20260920-003）。

標準形（1行＝卸の1商品・1点あたり）
------------------------------------
| 列 | 必須 | 中身 |
|---|---|---|
| JAN | ○ | 13桁/12桁。**文字列のまま**扱う（先頭0を落とさない） |
| 卸単価(税抜) | ○ | **卸の1点あたり**の値段。ロット価格を点数で割った値ではなく、卸サイトの「1点の単価」 |
| 入数 | | 卸の1点に入っている数（「12個入」なら12）。空なら不明 |
| 最小ロット | | 何点から買えるか（点）。空なら1 |
| 卸の商品名 | | セット数の判定（Amazon の1個＝卸の何点か）に使う。**空だと UNKNOWN が増える** |
| 仕入れ先 / 卸サイト / 購入先URL / 在庫 / 上代(税抜) / 卸値の確認日 / 備考 | | そのまま台帳へ |

🔴 卸単価・購入先URL は会員限定の取引条件。**この CSV は agent_output にだけ置く**（PUBLIC リポ）。

サブコマンド
------------
    python3 supplier_inputs.py sd-screen   # カズヨの SD 実画面価格（sd_price_screen_*.csv）→ 標準形
    python3 supplier_inputs.py netsea      # NETSEA の JAN 索引（卸値つき）→ 標準形
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
OUT_DIR = WORK / "supplier_screen"

COLUMNS = ["JAN", "卸単価(税抜)", "入数", "最小ロット", "卸の商品名", "仕入れ先", "卸サイト",
           "購入先URL", "在庫", "上代(税抜)", "卸値の確認日", "備考"]

# 別名（仕入れ先ごとに列名が違っても読めるように）
ALIASES = {
    "JAN": ("JAN", "jan", "JANコード", "janコード"),
    "卸単価(税抜)": ("卸単価(税抜)", "卸単価", "unit_price_excl", "卸価格_税抜_1点", "最安の卸1点(税抜)"),
    "入数": ("入数", "入り数"),
    "最小ロット": ("最小ロット", "min_lot_units", "最小点数"),
    "卸の商品名": ("卸の商品名", "商品名", "title"),
    "仕入れ先": ("仕入れ先", "supplier_name", "購入元の名前"),
    "卸サイト": ("卸サイト",),
    "購入先URL": ("購入先URL", "supplier_url"),
    "在庫": ("在庫", "stock"),
    "上代(税抜)": ("上代(税抜)", "reference_price"),
    "卸値の確認日": ("卸値の確認日", "確認日", "確認時刻"),
    "備考": ("備考", "メモ"),
}

JAN_RE = re.compile(r"^\d{12,13}$")


def normalize_row(r: dict) -> dict:
    """任意の列名の1行を標準形へ。見つからない列は空文字。"""
    out = {}
    for col, names in ALIASES.items():
        v = ""
        for n in names:
            if n in r and str(r[n]).strip() != "":
                v = str(r[n]).strip()
                break
        out[col] = v
    out["JAN"] = re.sub(r"\D", "", out["JAN"])
    return out


def read_input(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return [normalize_row(r) for r in csv.DictReader(f)]


def write(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ── SD：カズヨの実画面価格 ＋ 手元の SD 行（JAN）────────────────────────────

_TIER = re.compile(r"(\d+)\s*[xX×]\s*(\d+)")


def parse_tiers(s: str) -> list[tuple[int, int]]:
    """'300x1/290x10/280x200' → [(300,1),(290,10),(280,200)]（単価, 最小点数）。点数の昇順。"""
    return sorted(((int(p), int(q)) for p, q in _TIER.findall(s or "")), key=lambda t: t[1])


def sd_screen(screen: Path, sd_rows: Path, manual: Path | None = None) -> list[dict]:
    """SD は非ログインで卸値が取れないので、人が実画面で見た価格だけを使う。

    単価は**最小ロットの段**（一番少ない点数で買える段）を採る＝テスト仕入れの実態に合わせた
    保守側。まとめ買いの安い段は備考に残す。
    """
    rows = json.loads(sd_rows.read_text())
    by_pid: dict[str, list[dict]] = {}
    for r in rows:
        by_pid.setdefault(str(r.get("product_id")), []).append(r)
    notes: dict[str, str] = {}
    if manual and manual.exists():
        with manual.open(encoding="utf-8-sig") as fh:
            manual_rows = list(csv.DictReader(fh))
        for m in manual_rows:
            if m.get("メモ"):
                notes[m["SD品番"]] = m["メモ"]
    out = []
    with screen.open(encoding="utf-8-sig") as fh:
        screen_rows = list(csv.DictReader(fh))
    for s in screen_rows:
        pid = s["SD品番"].strip()
        tiers = parse_tiers(s.get("卸単価(税抜)x最小点数", ""))
        cands = by_pid.get(pid) or []
        if not tiers or not cands:
            print(f"  ⚠️ SD {pid}: 価格の段か JAN が取れないので入力に入れません", file=sys.stderr)
            continue
        price, lot = tiers[0]
        base = min(cands, key=lambda r: r.get("units_per_set") or 10 ** 9)
        sup = (base.get("supplier") or {}).get("name") or ""
        stock = (s.get("在庫") or "").strip()
        stock_n = {"あり": "在庫あり", "なし": "品切れ", "SOLD OUT": "品切れ"}.get(stock, stock)
        if stock == "品切れあり":
            stock_n = "一部品切れ"
        out.append({
            "JAN": base["jan"], "卸単価(税抜)": price, "入数": "",
            "最小ロット": lot, "卸の商品名": base.get("name") or "",
            "仕入れ先": sup, "卸サイト": "スーパーデリバリー",
            "購入先URL": s.get("購入先URL") or base.get("url") or "",
            "在庫": stock_n, "上代(税抜)": base.get("retail_excl") or "",
            "卸値の確認日": (s.get("確認時刻") or "")[:10],
            "備考": "；".join(x for x in (
                "段：" + "/".join(f"{p}円×{q}点〜" for p, q in tiers),
                f"確認者 {s.get('確認者', '')}", notes.get(pid, "")) if x),
        })
    return out


# ── NETSEA：JAN 索引 ─────────────────────────────────────────────────────


def netsea(index_path: Path) -> list[dict]:
    idx = json.loads(index_path.read_text())["jans"]
    day = datetime.fromtimestamp(os.path.getmtime(index_path)).strftime("%Y-%m-%d")
    out = []
    for jan, r in idx.items():
        if not JAN_RE.match(jan) or not r.get("unit_price_excl"):
            continue
        out.append({
            "JAN": jan, "卸単価(税抜)": r["unit_price_excl"], "入数": "",
            "最小ロット": r.get("min_lot_units") or 1, "卸の商品名": r.get("title") or "",
            "仕入れ先": r.get("supplier_name") or "", "卸サイト": "NETSEA",
            "購入先URL": r.get("supplier_url") or "", "在庫": r.get("stock") or "",
            "上代(税抜)": r.get("reference_price") or "", "卸値の確認日": day, "備考": "",
        })
    return out


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "sd-screen":
        src = Path(argv[2]) if len(argv) > 2 else WORK / "sd_buylist20261009/sd_price_screen_20261011.csv"
        rows = sd_screen(src, WORK / "pipeline/sd_rows.json",
                         WORK / "sd_buylist20261009/sd_price_manual_20261010.csv")
        dst = OUT_DIR / f"input_sd_{src.stem.split('_')[-1]}.csv"
    elif cmd == "netsea":
        rows = netsea(WORK / "pipeline/netsea_jan_index.json")
        dst = OUT_DIR / "input_netsea_index.csv"
    else:
        print(__doc__)
        return 2
    write(rows, dst)
    print(f"{len(rows):,}行 → {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
