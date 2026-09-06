#!/usr/bin/env python3
"""S5 を通過した 32 SKU の ASIN を取り出す。

親チケットのパイプライン（build_order_sets.py）は D の発注セット23行しか
書き出しておらず、S5 通過の32件そのものはファイルに残っていない。
本体を書き換えずに apply_velocity をラップして横取りする。
"""
import sys, json
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
PIPE = REPO / "workspace/output/deliverables/T-20260904-004"
sys.path.insert(0, str(PIPE))
sys.argv = ["build_order_sets.py", "--no-tariffs"]

import build_order_sets as B

captured = {}
_orig = B.apply_velocity
def spy(rows4, stats, min_drops=B.MIN_DROPS30):
    captured["in"] = rows4
    out = _orig(rows4, stats, min_drops)
    captured["out"] = out
    return out
B.apply_velocity = spy

try:
    B.main()
except SystemExit:
    pass
except Exception as e:
    print("pipeline error:", e, file=sys.stderr)

def asins(rows):
    return [r[0].get("ASIN") or r[0].get("asin") for r in rows]

if "out" in captured:
    passed = asins(captured["out"])
    dropped = [a for a in asins(captured["in"]) if a not in set(passed)]
    json.dump({"passed": passed, "dropped_by_S5": dropped},
              open("s5_asins.json", "w"))
    print("S5通過:", len(passed), " S5で落ちた:", len(dropped))
