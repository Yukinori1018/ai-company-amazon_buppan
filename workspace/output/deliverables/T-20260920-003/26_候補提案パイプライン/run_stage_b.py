#!/usr/bin/env python3
"""段B — 発掘した候補に §3.3 のゲート（offers が要る①②③）を掛ける。

既存の `candidate_pipeline.py` を**波に分けて**呼ぶだけのループです。
残高が下限を割るなら投げずに待ちます（補充20/分）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
PIPE = REPO / "workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260920-003/24_カート保持者ガード"))
from keepa_client import load_api_key  # noqa: E402


def tokens_left(key: str) -> int:
    raw = urllib.request.urlopen(f"https://api.keepa.com/token?key={key}", timeout=60).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return int(json.loads(raw.decode()).get("tokensLeft") or 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--total-tokens", type=int, default=1400)
    ap.add_argument("--floor", type=int, default=240)
    ap.add_argument("--minutes", type=int, default=120)
    ap.add_argument("--min-wave", type=int, default=24, help="この量が空くまで投げない")
    a = ap.parse_args()

    key = load_api_key()
    order = json.loads((WORK / "stageb_order.json").read_text())
    # ⚠️ 順序ファイルは作った時点のもの。**台帳で判定済みの ASIN を必ず落とす。**
    # これをしないと、判定済みばかりの塊を渡して candidate_pipeline が
    # 「未判定の候補がプールに残っていません」と答え、ループが**プール全体が尽きたと誤解して止まる**
    # （2026-10-01、残り187件あるのに1波で終了した）。
    sys.path.insert(0, str(PIPE))
    import ledger_sheet                                   # noqa: E402
    done = set(ledger_sheet.read_state().asins)
    before = len(order)
    order = [a for a in order if a not in done]
    print(f"順序 {before}件 → 未判定 {len(order)}件（台帳で判定済み {before - len(order)}件を除外）",
          flush=True)
    start, spent, wave, i = time.time(), 0, 0, 0
    while spent < a.total_tokens and time.time() - start < a.minutes * 60 and i < len(order):
        left = tokens_left(key)
        room = min(left - a.floor, a.total_tokens - spent)
        # ⚠️ 2026-10-01: 他チケット（T-20260930-001 の 20_fetch.py）が同じ Keepa キーで
        # 100トークン単位の取得を回し続けているため、**300トークン貯まるのを待つと永遠に投げられない**。
        # 波を小さくして「漏れてきた分を拾う」方式にする。シート読みの往復は増えるが
        # トークンは1つも増えない（コストは件数ベース）。
        if room < a.min_wave:
            print(f"残高 {left}（波の最小 {a.min_wave}）。90秒待ちます。", flush=True)
            time.sleep(90)
            continue
        wave += 1
        # 8トークン/ASIN（商品6＋セラー名2）。予算に収まる件数だけ渡す。
        take = max(1, room // 8)
        chunk = order[i:i + take]
        i += len(chunk)
        out = WORK / f"stageb_wave{wave}.json"
        cmd = [sys.executable, "-u", str(PIPE / "candidate_pipeline.py"),
               "--max-tokens", str(room), "--no-netsea", "--go-target", "9999",
               "--asins", *chunk, "--out-json", str(out)]
        print(f"\n### 波{wave}: 予算 {room}（残高 {left}）", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PIPE))
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if "未判定の候補がプールに残っていません" in r.stdout:
            # この塊が判定済みだっただけ。**全体が尽きたとは限らない**ので次の塊へ進む。
            print("この塊は判定済みでした。次へ進みます。", flush=True)
            continue
        if r.returncode != 0:
            print(f"異常終了 rc={r.returncode}。止めます。", flush=True)
            break
        spent += room          # 実消費は標準出力に出る。ここは予算の消化量で数える
        time.sleep(5)
    print(f"\n段B 終了: 波 {wave} / 予算消化 約{spent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
