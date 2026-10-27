#!/usr/bin/env python3
"""unknown_stages.run の冪等性（§3.3-17「2回目で0行」）を、Keepa もシートも触らずに確かめる。

2026-10-25 タカシ（T-20260920-003）。10/24 夜、run を2回続けると 1回目で UNKNOWN 295→300、
2回目で 300→295 と同じ5行が往復した。原因は「引き直しで新しく UNKNOWN になった行」を
同じ回で回していなかったこと（キューは引き直し前の台帳で作っていた）。

再現は 10/24 夜の実スナップショット（agent_output・Git 除外）を台帳の代わりに読む。
  before_20261024_stages_020425.json … 1回目の前の台帳
  after_20261024_stages_020425.json  … 1回目の引き直し結果（5行が NO-GO→UNKNOWN）
  after_20261024_stages_021050.json  … その5行を Keepa で取り直した後の引き直し結果
ファイルが無い環境ではスキップする。値（卸値など）は表示しない。

  python3 test_unknown_stages_fixpoint.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import unknown_stages as U  # noqa: E402

SNAP = U.LEDGER
FLIP = {"B0CLJ8GS2Z", "B00XTYOM12", "B01NBDCW2T", "B09JFKH3WS", "B01N0H1A76"}


def rows_of(name: str) -> list[dict]:
    h, *body = json.loads((SNAP / name).read_text())
    return [dict(zip(h, r + [""] * (len(h) - len(r)))) for r in body]


def n_unknown(rows):
    return sum(1 for r in rows if r["判定"] == "UNKNOWN")


class Fake:
    """台帳（シート）と ledger_refresh を差し替える。refresh は与えた結果を順に返し、尽きたら最後を返す。"""

    def __init__(self, sheet: list[dict], refreshes: list[list[dict]]):
        self.sheet, self.refreshes, self.calls, self.stage_calls = sheet, refreshes, 0, []

    def read_sheet(self):
        return list(self.sheet[0].keys()), self.sheet

    def refresh_ledger(self, write: bool) -> dict:
        rows = self.refreshes[min(self.calls, len(self.refreshes) - 1)]
        self.calls += 1
        self.sheet = rows
        from collections import Counter
        return {"前": [{}], "後": [dict(Counter(r["判定"] for r in rows))]}

    def run_stage(self, stage, batch, prods, reserve, dry):
        self.stage_calls.append((stage, [x["ASIN"] for x in batch]))
        return {"stage": stage, "batch": len(batch), "fetched": 0, "to_browser": [], "stop": ""}


def run_once(fake: Fake, tmp: Path) -> dict:
    U.read_sheet, U.refresh_ledger, U.run_stage = fake.read_sheet, fake.refresh_ledger, fake.run_stage
    U.load_products = lambda: {}
    U.QDIR, U.STATE = tmp, tmp / "state.json"
    a = type("A", (), {"batch": 100000, "rotations": 1, "reserve": 300, "no_write": False,
                       "no_fetch": True})()
    U.cmd_run.__globals__["print"] = lambda *x, **k: None   # run_log の出力を黙らせる
    U.cmd_run(a)
    return json.loads(U.STATE.read_text())["history"][-1]


def main() -> int:
    need = ["before_20261024_stages_020425.json", "after_20261024_stages_020425.json",
            "after_20261024_stages_021050.json"]
    if not all((SNAP / n).exists() for n in need):
        print("SKIP: 10/24 のスナップショットが無い")
        return 0
    b0, a1, a2 = (rows_of(n) for n in need)
    assert (n_unknown(b0), n_unknown(a1), n_unknown(a2)) == (295, 300, 295)
    flipped = {r["ASIN"] for r, s in zip(a1, b0) if r["判定"] != s["判定"]}
    assert flipped == FLIP, flipped

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        # 1回目：引き直しで5行が UNKNOWN に落ちる → 同じ回で5行を回す → 取り直し後の結果で終わる
        f = Fake(b0, [a1, a2])
        log1 = run_once(f, tmp)
        pass2 = {x for s, xs in f.stage_calls[3:] for x in xs}
        assert log1["passes"] == 2, log1["passes"]
        assert pass2 == FLIP, pass2
        assert n_unknown(f.sheet) == 295
        print(f"1回目: pass {log1['passes']}・2周目に回した行 {sorted(pass2)}・UNKNOWN {n_unknown(f.sheet)}")

        # 2回目：同じ入力（1回目の結果の台帳）でもう一度。段は何も回らず、判定は1行も変わらない
        before = {r["ASIN"]: r["判定"] for r in f.sheet}
        f2 = Fake(f.sheet, [f.sheet])
        log2 = run_once(f2, tmp)
        worked = [x for _, xs in f2.stage_calls for x in xs]
        changed = [a for a, v in ((r["ASIN"], r["判定"]) for r in f2.sheet) if before[a] != v]
        assert log2["passes"] == 1 and not worked and not changed, (log2["passes"], worked[:5], changed[:5])
        print(f"2回目: pass {log2['passes']}・段で回した行 {len(worked)}・判定が変わった行 {len(changed)}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
