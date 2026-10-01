"""救済用：区分で落ちた社の名前を gBizINFO で引き、商号が完全一致する現存法人を記録する（T-20260930-001 / 2026-10-01）。

    python3 30_build.py --from-raw   # suspect_names.json を作る
    python3 35_gbiz_rescue.py        # gBiz を引く（1.15秒/件・キャッシュ済みは0回）
    python3 30_build.py --from-raw   # 救済を反映

- 照合は T-20260831-004 の 31_name_match.py（query_variants / pick_exact）をそのまま使う。
- **完全一致が1社のときだけ救済に使う**（maker_rules._jp_gbiz）。2社以上は同名別会社がありうるので使わない。
- 英字ブランドと商号の偶然一致（BOS 型）はありうる。救済の根拠列に商号を書くので、人が見て戻せる。
- 出力 agent_output/T-20260930-001/gbiz/exact_by_name.json（法人番号を含むので Git に入れない）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
T4 = REPO / "workspace/output/deliverables/T-20260831-004"
WORK = REPO / "workspace/output/agent_output/T-20260930-001"
OUT = WORK / "gbiz"


def _mod(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, T4 / file)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


G = _mod("gbiz", "30_gbizinfo.py")
M = _mod("name_match", "31_name_match.py")

if __name__ == "__main__":
    names = json.loads((WORK / "suspect_names.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    outp = OUT / "exact_by_name.json"
    res = json.loads(outp.read_text()) if outp.exists() else {}
    cli = G.GBizInfo(OUT)
    for i, n in enumerate(names):
        if n in res:
            continue
        hits: dict[str, dict] = {}
        for q in M.query_variants(n):
            for c in M.pick_exact(cli.search_by_name(q), q):
                hits[c["corporate_number"]] = {"name": c.get("name"), "no": c["corporate_number"],
                                               "loc": (c.get("location") or "")[:20]}
        res[n] = list(hits.values())
        if i % 25 == 0:
            cli.flush(); outp.write_text(json.dumps(res, ensure_ascii=False))
            print(f"{i}/{len(names)} live={cli.live_calls}", flush=True)
    cli.flush(); outp.write_text(json.dumps(res, ensure_ascii=False))
    one = sum(1 for v in res.values() if len(v) == 1)
    print(f"done names={len(res)} exact1={one} multi={sum(1 for v in res.values() if len(v) > 1)} live={cli.live_calls}")
