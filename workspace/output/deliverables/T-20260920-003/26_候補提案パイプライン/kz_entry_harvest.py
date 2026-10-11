#!/usr/bin/env python3
"""kz 入口（monthlySold を問わない Amazon 起点）の段1：キャッシュ総ざらい（トークン0）。

2026-10-11 タカシ（T-20260920-003）。社長「GO 2件では事業にならない」への新しい手。
これまでの Amazon 起点の入口は monthlySold≥50 で、月3〜49個の棚を最初から捨てていた。
キーゾンの3か月販売数は Keepa ランク履歴（csv[3]）で再現できる（kz_estimate.py・
キーゾン実画面75点中69点一致）ので、その式で入口を作り直す。

やること
  agent_output 配下の全 Keepa キャッシュ（json/jsonl/json.gz）から商品レコードを集め、ASIN ごとに
  - 最新の lastUpdate のレコード（カート・本体在庫用）
  - ランク履歴（csv[3]）を持つ最新のレコード（kz 推定用）
  を残す。kz 推定の「now」はそのレコードの lastUpdate（Keepa 分）。古いレコードの kz は
  「その時点から見た過去3か月」なので、出力に kz の基準日を必ず持たせる。
出力: agent_output/T-20260920-003/kz_entry/harvest.pkl（PUBLIC リポに出さない）
"""
from __future__ import annotations

import gzip
import json
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
ROOT = REPO / "workspace/output/agent_output"
OUT = ROOT / "T-20260920-003/kz_entry"
T0 = 21564000          # Keepa 分 → Unix 分 のオフセット
THR = 0.03             # kz_estimate.py と同じ（直前観測より3%超の改善を1個と数える）


def kz_months(csv3: list, now: int) -> tuple[list[int], list[int]]:
    """kz_estimate.months() と同じ式（入力を csv[3] に直接取る版）。"""
    ps = [(csv3[i], csv3[i + 1]) for i in range(0, len(csv3) - 1, 2)]
    out, obs = [], []
    for k in (1, 2, 3):
        lo, hi = now - 30 * k * 1440, now - 30 * (k - 1) * 1440
        n = o = 0
        prev = None
        for t, r in ps:
            if r <= 0:
                prev = None
                continue
            if lo <= t < hi:
                o += 1
                if prev is not None and (prev - r) / prev > THR:
                    n += 1
            prev = r
        out.append(n)
        obs.append(o)
    return out, obs


def kday(m: int | None) -> str:
    if not m:
        return ""
    return datetime.fromtimestamp((m + T0) * 60, tz=timezone.utc).strftime("%Y-%m-%d")


BEST: dict[str, dict] = {}     # 最新レコード（カート判定用）
HIST: dict[str, dict] = {}     # ランク履歴つきの最新レコード（kz 用）


def take(p: dict, src: str, fetched: int | None) -> None:
    a = p.get("asin")
    if not a or not isinstance(a, str):
        return
    lu = p.get("lastUpdate") or 0
    if fetched:                       # 取り直し jsonl は fetched（Unix 秒）を持つ
        lu = max(lu, fetched // 60 - T0)
    st = p.get("stats") or {}
    o = st.get("outOfStockPercentage365")
    rec = dict(asin=a, lu=lu, src=src, title=p.get("title"), brand=p.get("brand"),
               ean=list(p.get("eanList") or []), parent=p.get("parentAsin"),
               ms=p.get("monthlySold"), bbs=st.get("buyBoxSellerId"),
               bbamz=st.get("buyBoxIsAmazon"),
               oos365=o[0] if isinstance(o, list) and o else None,
               amzcur=(st.get("current") or [None])[0],
               has_bb="buyBoxSellerId" in st)
    cur = BEST.get(a)
    if cur is None or lu > cur["lu"]:
        # 古いレコードの JAN は捨てない（新しい方に eanList が無いことがある）
        if cur and not rec["ean"]:
            rec["ean"] = cur["ean"]
        # buybox を引いていない新しいレコードで、引いた古いレコードのカート情報を消さない
        if cur and not rec["has_bb"] and cur["has_bb"]:
            for k in ("bbs", "bbamz", "has_bb"):
                rec[k] = cur[k]
            rec["bb_lu"] = cur.get("bb_lu", cur["lu"])
        BEST[a] = rec
    elif rec["ean"] and not cur["ean"]:
        cur["ean"] = rec["ean"]
    c = p.get("csv") or []
    c3 = c[3] if len(c) > 3 else None
    if c3:
        h = HIST.get(a)
        if h is None or lu > h["lu"]:
            m, obs = kz_months(c3, lu)
            HIST[a] = dict(lu=lu, m=m, obs=obs, src=src)


def walk(x, src: str, fetched: int | None = None) -> None:
    if isinstance(x, dict):
        if "asin" in x and isinstance(x.get("asin"), str) and (
                "csv" in x or "eanList" in x or "monthlySold" in x or "stats" in x):
            take(x, src, fetched)
            return
        f = x.get("fetched") if isinstance(x.get("fetched"), int) else fetched
        for v in x.values():
            walk(v, src, f)
    elif isinstance(x, list):
        for v in x:
            walk(v, src, fetched)


def files() -> list[Path]:
    out = subprocess.run(["grep", "-rl", "--include=*.json", "--include=*.jsonl",
                          '"eanList"', str(ROOT)], capture_output=True, text=True).stdout
    fs = [Path(l) for l in out.splitlines() if l and "/kz_entry/" not in l]
    fs += list(ROOT.rglob("*.json.gz"))
    return fs


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fs = files()
    print(f"キャッシュ {len(fs)} ファイル", flush=True)
    for i, f in enumerate(fs):
        src = str(f.relative_to(ROOT))
        try:
            if f.suffix == ".jsonl":
                for line in f.open():
                    line = line.strip()
                    if line:
                        try:
                            walk(json.loads(line), src)
                        except Exception:
                            pass
            elif f.suffix == ".gz":
                walk(json.load(gzip.open(f)), src)
            else:
                walk(json.load(f.open()), src)
        except Exception as e:  # 壊れたキャッシュは飛ばすが黙らない
            print("ERR", src, e, file=sys.stderr)
        if i % 200 == 0:
            print(f"  {i}/{len(fs)}  ASIN {len(BEST)}  履歴つき {len(HIST)}", flush=True)
    pickle.dump({"best": BEST, "hist": HIST}, (OUT / "harvest.pkl").open("wb"))
    print(f"ASIN {len(BEST)}・ランク履歴つき {len(HIST)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
