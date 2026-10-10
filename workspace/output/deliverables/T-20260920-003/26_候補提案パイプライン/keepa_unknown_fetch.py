#!/usr/bin/env python3
"""実売 UNKNOWN 行を Keepa から取り直す（2026-10-11 タカシ・T-20260920-003）。

なぜ：キーゾンが社長の Chrome に入っておらず、実売 UNKNOWN を人の目で解けない。
代わりに Keepa のランク履歴（csv[3]）とカートの持ち主（buyBoxSellerId）を取り、
`rank_velocity.py` で推定月販を出す材料にする。

取得：/product?stats=90&history=1&buybox=1（offers なし）。ASIN あたり約3トークン。
保存：agent_output/T-20260920-003/ledger20261010/keepa_unknown_20261011.jsonl（1行1商品・生）。
      既に保存済みの ASIN は叩かない（再実行はトークン0）。
使い方：python3 keepa_unknown_fetch.py [ASIN一覧.json]
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
OUT = REPO / "workspace/output/agent_output/T-20260920-003/ledger20261010"
RAW = OUT / "keepa_unknown_20261011.jsonl"
COST = 3          # stats+history 1 ＋ buybox 2（実測で確かめて表示する）
BATCH = 50


def key() -> str:
    k = os.environ.get("KEEPA_API_KEY")
    if k:
        return k
    for line in (Path.home() / ".config/ai-company-amazon-buppan/keepa.env").read_text().splitlines():
        if line.startswith("KEEPA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("KEEPA_API_KEY がありません")


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


def wait_tokens(k: str, need: int) -> None:
    while True:
        left = get(f"https://api.keepa.com/token?key={k}").get("tokensLeft", 0)
        if left >= need:
            return
        s = min(300, max(20, int((need - left) / 20 * 60) + 5))
        print(f"  トークン {left} < {need}。{s}秒待つ", flush=True)
        time.sleep(s)


def main(argv: list[str]) -> int:
    src = Path(argv[0]) if argv else OUT / "cart_queue_unknown_20261011.json"
    asins = list(dict.fromkeys(json.loads(src.read_text())))
    have = set()
    if RAW.exists():
        have = {json.loads(l)["asin"] for l in RAW.open()}
    todo = [a for a in asins if a not in have]
    print(f"対象 {len(asins)}・取得済み {len(asins) - len(todo)}・これから {len(todo)}")
    k = key()
    for i in range(0, len(todo), BATCH):
        part = todo[i:i + BATCH]
        wait_tokens(k, COST * len(part))
        q = urllib.parse.urlencode({"key": k, "domain": 5, "asin": ",".join(part),
                                    "stats": 90, "history": 1, "buybox": 1})
        d = get(f"https://api.keepa.com/product?{q}")
        now = int(time.time())
        with RAW.open("a") as f:
            for p in d.get("products") or []:
                f.write(json.dumps({"asin": p["asin"], "fetched": now, "product": p},
                                   ensure_ascii=False) + "\n")
        print(f"  {i + len(part)}/{len(todo)} 消費 {d.get('tokensConsumed')}・残 {d.get('tokensLeft')}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
