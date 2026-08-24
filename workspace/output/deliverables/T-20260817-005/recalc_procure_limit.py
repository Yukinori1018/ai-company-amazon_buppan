"""第4段: 手数料表の改定後、既存CSVの『想定仕入れ金額(上限)』を遡って一括再計算する。

設計方針:
- **Keepaを1トークンも使わない**。既存CSVの列だけで完結する（scan_v14.py本体は触らない・呼ばない）。
- **冪等**。同じ入力CSVに対して何度実行しても同じ出力になる（副作用なし・上書きは--writeを渡した時だけ）。
- 「手数料内訳」列から旧計算時の内訳（基準売価・保管料の根拠・外注費・雑費）を復元し、
  **販売手数料とFBA配送代行だけを現在の calc/fees.py で引き直す**方式（Stage3と同じ考え方）。
  保管料は「体積(L)×レート×月数」の根拠が内訳に残っていればレートだけ現行値に差し替えて再計算し、
  寸法欠落（固定額フォールバック）だった行はフォールバック額をそのまま使う。
  → 実寸法データを持たないCSVからでも、保管料の精度を落とさずに再計算できる。
- カテゴリー判定は実物ロジック（adapters.amazon_data._map_category_key）をそのまま使う。
- サイズ区分は「FBAサイズ」の表示ラベル（scan_v14.fba_size_class の出力）から復元する。
  これは料率改定の影響を受けない安定したキーなので、将来また料率が変わっても壊れない設計。

使い方:
    python3 recalc_procure_limit.py [--in v14/01_候補プール_全件.csv] [--out recalced.csv] [--write]

    --write を付けない場合は集計だけ表示して終わる（誤って上書きしない安全弁）。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters.amazon_data import _map_category_key  # noqa: E402
from calc import fees  # noqa: E402
import procure_limit as pl  # noqa: E402

DEFAULT_IN = Path(__file__).resolve().parent / "v14" / "01_候補プール_全件.csv"

# scan_v14.fba_size_class() の表示ラベル → fees.FBA_FEE_TABLE のキー。
# 「大型」「不明」は procure_limit.compute() が standard_1 にフォールバックする実挙動に合わせる
# （fees.FBA_FEE_TABLE に "large" というキーが無いため、旧スキャンでも実際にそうなっていた）。
SIZE_LABEL_TO_KEY = {
    "標準(小型)": "small", "標準1": "standard_1", "標準2": "standard_2",
    "大型": "standard_1", "不明": "standard_1", "不明(重量欠落)": "standard_1",
}

BREAKDOWN_RE = re.compile(
    r"基準売価(?P<base>\d+) − 販売手数料(?P<referral>\d+)\((?P<rate>[\d.]+)%\) "
    r"− FBA配送(?P<fba>\d+) − 保管(?P<storage>\d+)\[(?P<storage_note>.*?)\] "
    r"− 外注(?P<outsource>\d+) − 雑費(?P<other>\d+) − 目標利益(?P<target>\d+)\((?P<margin>\d+)%\)"
)
STORAGE_VOL_RE = re.compile(r"([\d.]+)L×[\d.]+円/m³×([\d.]+)ヶ月")
STORAGE_FLAT_RE = re.compile(r"固定額(\d+)円×([\d.]+)ヶ月")


def recompute_storage(storage_note: str) -> int:
    """保管料の根拠テキストから、現行レートで再計算した保管料(円)を返す。"""
    m = STORAGE_VOL_RE.search(storage_note)
    if m:
        volume_l, months = float(m.group(1)), float(m.group(2))
        fee = (volume_l / 1000.0) * pl.STORAGE_FEE_YEN_PER_M3_MONTH * months
        return round(fee)
    m = STORAGE_FLAT_RE.search(storage_note)
    if m:
        # フォールバック額は不変（pl.STORAGE_FEE_FALLBACK_YEN）なので月数だけ反映
        months = float(m.group(2))
        return round(pl.STORAGE_FEE_FALLBACK_YEN * months)
    return None  # 想定外フォーマット。呼び出し側で「再計算不能」として扱う


def recalc_row(row: dict) -> dict | None:
    m = BREAKDOWN_RE.search(row.get("手数料内訳", ""))
    if not m:
        return None
    g = m.groupdict()
    base = int(g["base"])

    cat_names = (row.get("カテゴリ") or "").split(" > ")
    category_key = _map_category_key({"categoryTree": [{"name": n} for n in cat_names if n]})

    size_label = row.get("FBAサイズ", "")
    size_key = SIZE_LABEL_TO_KEY.get(size_label, "standard_1")

    new_storage = recompute_storage(g["storage_note"])
    if new_storage is None:
        return None
    outsource = int(g["outsource"])
    other = int(g["other"])

    new_referral, new_rate = pl.referral_fee_yen(base, category_key)
    fba_key = size_key if size_key in fees.FBA_FEE_TABLE else "standard_1"
    new_fba = fees.FBA_FEE_TABLE[fba_key]["fba_fee_yen"]

    fixed = new_referral + new_fba + new_storage + outsource + other
    breakeven = base - fixed
    limit_raw = breakeven - base * pl.TARGET_NET_MARGIN

    out = dict(row)
    out["想定仕入れ金額(上限)_旧"] = row.get("想定仕入れ金額(上限)", "")
    out["想定仕入れ金額(上限)"] = int(limit_raw) if limit_raw > 0 else ""
    out["赤字ライン(これ以上は赤字)_旧"] = row.get("赤字ライン(これ以上は赤字)", "")
    out["赤字ライン(これ以上は赤字)"] = int(breakeven) if breakeven > 0 else ""
    out["販売手数料率%"] = round(new_rate * 100, 1)
    out["手数料内訳"] = (
        f"基準売価{int(base)} − 販売手数料{int(new_referral)}({new_rate * 100:.1f}%) "
        f"− FBA配送{int(new_fba)} − 保管{int(new_storage)}(現行レートで再計算) "
        f"− 外注{outsource} − 雑費{other} "
        f"− 目標利益{int(base * pl.TARGET_NET_MARGIN)}({pl.TARGET_NET_MARGIN * 100:.0f}%) "
        f"[recalc_procure_limit.py 2026-08-24 再計算]"
    )
    out["仕入れ掛け率上限%"] = (
        round(limit_raw / base * 100, 1) if limit_raw > 0 else ""
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--write", action="store_true", help="指定しない限りファイルは書かない（安全弁）")
    args = ap.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path) if args.out_path else in_path.with_name(
        in_path.stem + "_recalced" + in_path.suffix)

    with open(in_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    recalced, unparsed = [], 0
    up, down, flat = 0, 0, 0
    deltas = []
    for row in rows:
        r = recalc_row(row)
        if r is None:
            unparsed += 1
            recalced.append(row)  # 再計算できない行はそのまま残す（データを消さない）
            continue
        old_v = row.get("想定仕入れ金額(上限)", "")
        new_v = r["想定仕入れ金額(上限)"]
        if old_v not in ("", None) and new_v not in ("", None):
            d = int(new_v) - int(old_v)
            deltas.append(d)
            up += d > 0
            down += d < 0
            flat += d == 0
        recalced.append(r)

    print(f"入力: {in_path} ({len(rows)}行)")
    print(f"再計算成功: {len(rows) - unparsed}行 / 再計算不能(手数料内訳が無い等): {unparsed}行")
    if deltas:
        avg_pct = sum(deltas) / len(deltas)
        print(f"上限が増: {up} / 減: {down} / 不変: {flat}")
        print(f"平均差額: {avg_pct:+.1f}円/行")

    ext_fields = fieldnames.copy()
    for extra in ("想定仕入れ金額(上限)_旧", "赤字ライン(これ以上は赤字)_旧"):
        if extra not in ext_fields:
            ext_fields.append(extra)

    if args.write:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=ext_fields)
            w.writeheader()
            for r in recalced:
                w.writerow({k: r.get(k, "") for k in ext_fields})
        print(f"書き込み完了: {out_path}")
    else:
        print("（--write を付けていないため、ファイルへの書き込みは行っていません。集計のみ表示）")


if __name__ == "__main__":
    main()
