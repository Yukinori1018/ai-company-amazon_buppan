"""入口を広げたときの件数だけを測る（取得はしない）— T-20260930-001 / 2026-10-01。

base = 10_funnel.py の全条件（段2b まで＝9,756 ASIN）。そこから1条件ずつ緩めた Finder の totalResults を取る。
月販≥50（積極条件）は絶対に外さない。1本 ≈ 11 token。キャッシュ済みは0 token。

    python3 15_widen.py    → agent_output/T-20260930-001/widen.json
"""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import keepa_io

HERE = Path(__file__).resolve().parent
F = runpy.run_path(str(HERE / "10_funnel.py"), run_name="lib")
BASE = F["selection_upto"](len(F["STEPS"]) - 1)


def without(sel: dict, *keys: str) -> dict:
    return {k: v for k, v in sel.items() if k not in keys}


A = {**without(BASE, "offerCountFBA_gte"), "offerCountFBA_gte": 1, "current_COUNT_NEW_gte": 2}
B = {**BASE, "current_NEW_gte": 1500}
C = without(BASE, "current_SALES_gte", "current_SALES_lte")
VARIANTS = [
    ("base（現行・段2b まで）", BASE),
    ("(a) FBA≥2 → 新品オファー≥2 かつ FBA≥1", A),
    ("(b) 売価≥2,200 → ≥1,500", B),
    ("(c) ランク≤5万を外す（月販≥50は維持）", C),
    ("(a)+(b)+(c) 全部", {**without(A, "current_SALES_gte", "current_SALES_lte"), "current_NEW_gte": 1500}),
    ("check: current_COUNT_NEW_gte=999999 で0件になるか（綴りの効き）", {**A, "current_COUNT_NEW_gte": 999999}),
]

if __name__ == "__main__":
    out = []
    for label, sel in VARIANTS:
        assert sel.get("monthlySold_gte") == 50, label
        d = keepa_io.finder({**sel, "perPage": 50, "page": 0}, "widen")
        out.append({"label": label, "total": d.get("totalResults"), "tokens": d.get("tokensConsumed")})
        print(f"{label:60} {d.get('totalResults'):>10,} (token {d.get('tokensConsumed')})", flush=True)
    (keepa_io.RAW.parent / "widen.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
