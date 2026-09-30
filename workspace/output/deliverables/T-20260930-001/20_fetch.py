"""段1の取得：Finder の一覧 → product（1 token/ASIN）を A 優先・monthlySold 降順で取る（T-20260930-001）。

- 一覧は 10_funnel.py の全条件（段2b まで）＋ sort=monthlySold desc。
- 取得順 = A 条件（monthlySold≥100 かつ 新品最安≥3,900円）の ASIN → それ以外。順序は raw/order.json に固定し、
  バッチ番号がずれないようにする（途中で止めても、再実行で続きから取る）。
- product は stats=365・history=0・offers なし（1 token/ASIN）。buybox=1 は 3 token/ASIN なので
  代表 ASIN だけ 30_build.py の --bb で取り直す。

    nohup python3 20_fetch.py --max 9756 > ../../agent_output/T-20260930-001/fetch.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

import keepa_io

HERE = Path(__file__).resolve().parent
F = runpy.run_path(str(HERE / "10_funnel.py"), run_name="lib")
BASE = F["selection_upto"](len(F["STEPS"]) - 1)
ORDER = keepa_io.RAW / "order.json"


def build_order() -> list[str]:
    if ORDER.exists():
        return json.loads(ORDER.read_text())
    full = keepa_io.finder({**BASE, "perPage": 10000, "page": 0, "sort": [["monthlySold", "desc"]]}, "list")
    a = keepa_io.finder({**BASE, "monthlySold_gte": 100, "current_NEW_gte": 3900,
                         "perPage": 10000, "page": 0, "sort": [["monthlySold", "desc"]]}, "listA")
    alist = a.get("asinList") or []
    aset = set(alist)
    order = alist + [x for x in (full.get("asinList") or []) if x not in aset]
    ORDER.write_text(json.dumps(order))
    print(f"order: A {len(alist)} + 他 {len(order) - len(alist)} = {len(order)}")
    return order


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3000, help="取得する ASIN 数の上限（先頭から）")
    a = ap.parse_args()
    order = build_order()
    ps = keepa_io.products(order[: a.max], "all", log=lambda s: print(s, flush=True))
    print(f"DONE products {len(ps)}", flush=True)
