#!/usr/bin/env python3
"""母数を取りに行くレーン — 「売れている棚」から入って NETSEA 索引に当てる。

    python3 lane_selling_first.py --budget 400      # 使ってよいトークン数

なぜこの向きか（2026-10-04）
---------------------------
既存プール648件は **NETSEA 索引（卸）から入って** Amazon に当てたものです。だから
「仕入れは実在するが Amazon で売れていない」棚ばかりになりました。実測：

- `monthlySold` が取れている行は **460件中9件（2%）**
- ランクで代用しようとすると、**262件が family 共有ランク**で ASIN 単位の根拠にならない

つまり**入口が逆**です。`monthlySold_gte` で「売れている棚」から入れば、実売の根拠は
最初から付いています。あとは**仕入れが実在するか**だけを当てればよい。

⚠️ **2026-09-30 に同じ向きを SD で試して一致0/10件**でした（`product_finder` の
`SD_FRIENDLY_ROOT_CATEGORIES` のコメント）。理由は品揃えのズレです。今回は
**NETSEA 索引（67,667 JAN・SD より桁が大きい）**に当てるので、当たる率は別です。
**だから「やってみて率を測る」**のが本スクリプトの目的で、当たらなければ当たらないと
報告します（推測で母数を語らない）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import product_finder                                  # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
NETSEA_IDX = WORK / "pipeline/netsea_jan_index.json"
OUT = WORK / "lane_selling20261004"
KEY = os.environ.get("KEEPA_API_KEY") or ""

BATCH = 20
COST_PER_PRODUCT = 3


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
        enc = r.headers.get("Content-Encoding")
    if enc == "gzip":
        body = gzip.decompress(body)
    return json.loads(body)


def tokens_left() -> int:
    try:
        return int(get(f"https://api.keepa.com/token?key={KEY}").get("tokensLeft", 0))
    except Exception:
        return 0


def wait_for(need: int) -> None:
    while True:
        left = tokens_left()
        if left >= need:
            return
        wait = min(300, max(30, int((need - left) / 20 * 60) + 10))
        print(f"  残 {left} < 必要 {need} → {wait}秒待機", flush=True)
        time.sleep(wait)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=400, help="使ってよいトークン数")
    ap.add_argument("--monthly-sold-min", type=int, default=50)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    jans = json.loads(NETSEA_IDX.read_text())["jans"]
    print(f"NETSEA 索引 {len(jans):,} JAN に当てます")

    # ── 1. 売れている棚の ASIN を引く（Finder 1本 ≒ 10トークン）
    sel = product_finder.selling_shelves(monthly_sold_min=a.monthly_sold_min,
                                         price_min=500, price_max=20_000)
    sel["perPage"] = 10_000
    wait_for(20)
    url = ("https://api.keepa.com/query?" + urllib.parse.urlencode(
        {"key": KEY, "domain": 5, "selection": json.dumps(sel)}))
    d = get(url)
    asins = d.get("asinList") or []
    spent = d.get("tokensConsumed", 10)
    print(f"Finder: 該当 {d.get('totalResults')}件・取得 {len(asins)}件"
          f"（消費 {spent}・残 {d.get('tokensLeft')}）")
    (OUT / "finder_asins.json").write_text(json.dumps(
        {"selection": sel, "totalResults": d.get("totalResults"),
         "asins": asins}, ensure_ascii=False))

    # ── 2. 商品を取って JAN を索引に当てる（1件3トークン）
    hits, checked = [], 0
    for i in range(0, len(asins), BATCH):
        if spent + BATCH * COST_PER_PRODUCT > a.budget:
            print(f"予算 {a.budget} トークンに到達（消費 {spent}）。ここで止めます。")
            break
        chunk = asins[i:i + BATCH]
        wait_for(BATCH * COST_PER_PRODUCT + 30)
        try:
            r = get(f"https://api.keepa.com/product?key={KEY}&domain=5"
                    f"&asin={','.join(chunk)}&buybox=1&stats=180&days=400")
        except Exception as e:
            print(f"  取得失敗 {e}"); time.sleep(30); continue
        spent += r.get("tokensConsumed", 0)
        for p in r.get("products", []):
            checked += 1
            for code in (p.get("eanList") or []) + (p.get("upcList") or []):
                ent = jans.get(str(code))
                if ent:
                    hits.append({"asin": p.get("asin"), "jan": str(code),
                                 "title": (p.get("title") or "")[:70],
                                 "monthlySold": p.get("monthlySold"),
                                 "netsea": ent, "product": p})
                    break
        print(f"  {checked}件照合 / 一致 {len(hits)}件（消費 {spent}）", flush=True)

    rate = (len(hits) / checked * 100) if checked else 0.0
    print(f"\n照合 {checked}件 → NETSEA 一致 {len(hits)}件（{rate:.1f}%）")
    print(f"消費トークン {spent}")
    if checked:
        need = int(round(100 / max(rate, 0.01) * COST_PER_PRODUCT))
        print(f"一致1件あたり約 {need} トークン ＝ 20件増やすのに約 {need * 20:,} トークン"
              f"（20/分なので約 {need * 20 / 20 / 60:.1f}時間）")
    json.dump({"照合": checked, "一致": len(hits), "一致率(%)": round(rate, 1),
               "消費トークン": spent,
               "hits": [{k: v for k, v in h.items() if k != "product"} for h in hits]},
              (OUT / "summary.json").open("w"), ensure_ascii=False, indent=1)
    with (OUT / "raw.jsonl").open("w") as f:
        for h in hits:
            f.write(json.dumps({"asin": h["asin"], "product": h["product"]},
                               ensure_ascii=False) + "\n")
    print(f"書き出し: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
