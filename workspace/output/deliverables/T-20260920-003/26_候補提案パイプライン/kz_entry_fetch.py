#!/usr/bin/env python3
"""kz 入口の段2：Keepa を取り直す（再実行はトークン0＝取得済み ASIN は叩かない）。

2026-10-11 タカシ（T-20260920-003）。
  python3 kz_entry_fetch.py hist <ASIN一覧.json>   # stats=90&history=1        … 1トークン/ASIN
  python3 kz_entry_fetch.py full <ASIN一覧.json>   # stats=90&history=1&buybox=1 … 3トークン/ASIN

二段にする理由：kz（ランク履歴からの3か月販売数）の足切りは history だけで出せる（1トークン）。
カート保持者（buybox）は足切りを通った ASIN にだけ払う（+2トークン）。
保存：agent_output/T-20260920-003/kz_entry/keepa_<mode>.jsonl（1行1商品・生・PUBLIC に出さない）
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keepa_unknown_fetch import get, key, wait_tokens   # noqa: E402  同じ取り方を使い回す

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003/kz_entry")
COST = {"hist": 1, "full": 3}
BATCH = 30      # 他のジョブと Keepa を分け合うとき 100（300トークン）だと残高が貯まらず止まる


def main(argv: list[str]) -> int:
    mode, src = argv[0], Path(argv[1])
    raw = OUT / f"keepa_{mode}.jsonl"
    asins = list(dict.fromkeys(json.loads(src.read_text())))
    have = {json.loads(l)["asin"] for l in raw.open()} if raw.exists() else set()
    todo = [a for a in asins if a not in have]
    print(f"[{mode}] 対象 {len(asins)}・取得済み {len(asins) - len(todo)}・これから {len(todo)}", flush=True)
    k = key()
    for i in range(0, len(todo), BATCH):
        part = todo[i:i + BATCH]
        wait_tokens(k, COST[mode] * len(part))
        prm = {"key": k, "domain": 5, "asin": ",".join(part), "stats": 90, "history": 1}
        if mode == "full":
            prm["buybox"] = 1
        d = get("https://api.keepa.com/product?" + urllib.parse.urlencode(prm))
        now = int(time.time())
        got = d.get("products") or []
        with raw.open("a") as f:
            for p in got:
                f.write(json.dumps({"asin": p["asin"], "fetched": now, "product": p},
                                   ensure_ascii=False) + "\n")
        print(f"  {i + len(part)}/{len(todo)} 取得 {len(got)}・消費 {d.get('tokensConsumed')}・残 {d.get('tokensLeft')}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
