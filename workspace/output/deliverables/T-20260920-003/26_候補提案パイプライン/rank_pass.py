#!/usr/bin/env python3
"""安い段（1トークン/ASIN）でランクと月販を取り、段B（6.6トークン/ASIN）の順番を決める。

なぜ要るか（2026-10-01 の反省）
------------------------------
段A で `stats=90` を取っていたのにランクを保存しておらず、生存ゲート（ランク10万位以内で PASS）を
掛ける順番が決められなかった。結果、段Bの最初の7件のうち**生存 PASS は1件**で、
6.6トークン/ASIN を「どう転んでも UNKNOWN になる行」に払っていた。

二段構えの原則（memory: knowledge_keepa_token_ceiling_and_unattended_scan §2）
  1段でまとめて stats+offers = 6.5/件
  二段なら 1 + 通過率×6.5
**払って得た数字は捨てない。**discover.py は保存するよう直したが、既に払ったぶんはここで取り直す。
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
PIPE = REPO / "workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
GUARD = REPO / "workspace/output/deliverables/T-20260920-003/24_カート保持者ガード"
WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(GUARD))
import ledger_sheet                               # noqa: E402
import profit                                      # noqa: E402
import set_count                                   # noqa: E402
from candidate_pipeline import ALIVE_RANK, DEAD_RANK  # noqa: E402
from keepa_client import KEEPA_DOMAIN_JP, load_api_key  # noqa: E402

CACHE = WORK / "discovered.json"
ORDER = WORK / "stageb_order.json"


def get(url: str) -> dict:
    raw = urllib.request.urlopen(url, timeout=300).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def tokens_left(key: str) -> int:
    return int(get(f"https://api.keepa.com/token?key={key}").get("tokensLeft") or 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=60)
    a = ap.parse_args()

    key = load_api_key()
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    cands = data["candidates"]
    state = ledger_sheet.read_state()
    want = [asin for asin, c in cands.items()
            if asin not in state.asins and "rank_avg90" not in (c.get("extra") or {})]
    print(f"候補 {len(cands)}件 / 未判定でランク未取得 {len(want)}件")

    start, i = time.time(), 0
    while i < len(want) and time.time() - start < a.minutes * 60:
        left = tokens_left(key)
        # ⚠️ 同じ API キーで T-20260930-001 の取得（100件/105トークン単位）が同時に走っている。
        # **向こうは105貯まるまで待つので、こちらは40で取りに行けば先に拾える。**
        # これは設計ではなく小細工です。本来はどちらを先に通すかを人が決めるべき（報告に書いた）。
        if left < 40:
            time.sleep(20)
            continue
        chunk = want[i:i + max(1, min(100, left - 10))]
        i += len(chunk)
        d = get("https://api.keepa.com/product?" + urllib.parse.urlencode(
            {"key": key, "domain": KEEPA_DOMAIN_JP, "asin": ",".join(chunk), "stats": 90}))
        if d.get("error"):
            print(f"Keepa エラー: {d['error']}")
            break
        for p in d.get("products") or []:
            c = cands.get(p.get("asin"))
            if not c:
                continue
            st = p.get("stats") or {}
            cur, avg = st.get("current") or [], st.get("avg90") or []
            def at(seq, n):
                v = seq[n] if isinstance(seq, list) and len(seq) > n else None
                return None if v in (None, -1) else v
            ms = p.get("monthlySold")
            c["monthly_sold"] = None if ms in (None, -1) else ms
            c.setdefault("extra", {}).update(
                {"rank_now": at(cur, 3), "rank_avg90": at(avg, 3)})
        print(f"  {i}/{len(want)} 消費 {d.get('tokensConsumed')} 残 {d.get('tokensLeft')}",
              flush=True)
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1)

    # 段Bの順番を引き直す: 生存 PASS → 手残りが大きい順。社ごとのラウンドロビンは維持。
    import collections
    scored = []
    for asin, c in cands.items():
        if asin in state.asins:
            continue
        ex = c.get("extra") or {}
        r = ex.get("rank_avg90") or ex.get("rank_now")
        alive = 0 if (c.get("monthly_sold") or (r and r <= ALIVE_RANK)) else (
            2 if (r and r > DEAD_RANK) or not r else 1)
        mult, _ = set_count.cost_multiplier(c.get("title"))
        net = -10 ** 6
        if mult and all(c.get(k) for k in ("sell", "fee_pct", "fba_yen", "unit_cost_incl")):
            e = profit.compute(c["sell"], c["fee_pct"], c["fba_yen"],
                               c["unit_cost_incl"] * mult, qty=1)
            net = e.net_per_unit - (int(round(e.sell * 0.07)) + 200)
        scored.append((alive, -net, asin, c.get("supplier") or "?"))
    scored.sort()
    q = collections.OrderedDict()
    for row in scored:
        q.setdefault(row[3], []).append(row[2])
    order = []
    while any(q.values()):
        for k in list(q):
            if q[k]:
                order.append(q[k].pop(0))
    ORDER.write_text(json.dumps(order), encoding="utf-8")
    alive_n = sum(1 for s in scored if s[0] == 0)
    print(f"\n段Bの順番を引き直しました: {len(order)}件（生存 PASS 見込み {alive_n}件・"
          f"灰色 {sum(1 for s in scored if s[0] == 1)}件・死 {sum(1 for s in scored if s[0] == 2)}件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
