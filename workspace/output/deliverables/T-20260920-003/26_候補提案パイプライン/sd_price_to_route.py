#!/usr/bin/env python3
"""SD 実画面の卸値（JAN キー）を、台帳の SD 経路（sd_route_override_*.csv・ASIN キー）に変換する。

2026-10-16 タカシ（T-20260920-003）。10/15 のカネイシ10 JAN は手で変換していたので、型を1本にした。

    python3 sd_price_to_route.py <価格CSV> --supplier カネイシ --tag 20261016_kaneishi_unimat \
        [--tokens 300] [--buybox-tokens 600]

流れ
----
1. 価格CSV（列：sd_product_id, jan, 卸単価_通常_税抜, 出どころ, 取得日）を読む
2. JAN → ASIN を Keepa で逆引き（キャッシュ優先・足りない JAN だけ `code`。**セット品 ASIN も全部**＝§3.3-19）
3. 対象 ASIN だけ buybox=1 で取り直す（#5 カートの販売元・メーカー公式カートの検査用。3トークン/商品）
4. 書き出し
   - `sd_buylist20261009/sd_route_override_<tag>.csv`（ledger_refresh が glob で読む）
   - `unknown_queue/keepa_stage_<tag>.jsonl`（ledger_refresh の台帳外採点が読む商品データ）

在庫は価格CSVに無いので「未確認」＝#17 は UNKNOWN のまま（route_to_sd の規定）。
🔴 卸値は agent_output にだけ書く（PUBLIC リポ）。このスクリプトは値を持たない。SD へは一切アクセスしない。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import supplier_screen as SS   # noqa: E402

WORK = SS.WORK
SDB = WORK / "sd_buylist20261009"
STAGE = WORK / "unknown_queue"
COLS = ["ASIN", "JAN", "SD品番", "購入先URL", "卸価格_税抜_1点", "卸の最小ロット(点)", "在庫", "確認時刻",
        "確認者", "メモ", "卸サイト", "仕入れ先", "JAN照合", "購入元の名前"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("price_csv", type=Path)
    ap.add_argument("--supplier", required=True, help="SD 出展企業の通称（例：カネイシ）")
    ap.add_argument("--buyer-name", default="", help="購入元の名前（台帳の列）。省略時は --supplier")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tokens", type=int, default=0)
    ap.add_argument("--buybox-tokens", type=int, default=0)
    ap.add_argument("--floor", type=int, default=200)
    a = ap.parse_args(argv)

    rows = list(csv.DictReader(a.price_csv.open(encoding="utf-8-sig")))
    by_jan = {r["jan"].strip(): r for r in rows if r.get("jan")}
    store = SS.KeepaStore(set(by_jan))
    need = [j for j in by_jan if j not in store.complete]
    print(f"JAN {len(by_jan)}・逆引き済み {len(by_jan) - len(need)}・未取得 {len(need)}")
    if need and a.tokens:
        store.resolve_jans(need, a.tokens, a.floor, wait=False)
    asins = sorted({x for j in by_jan for x in store.by_jan.get(j, ())})
    print(f"ASIN {len(asins)}（セット品含む）")
    if a.buybox_tokens and asins:
        store.refresh_buybox(asins, a.buybox_tokens, a.floor, wait=False)

    out = SDB / f"sd_route_override_{a.tag}.csv"
    nohit = []
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for j, r in by_jan.items():
            hits = sorted(store.by_jan.get(j, ()))
            if not hits:
                nohit.append(j)
            pid = r["sd_product_id"].strip()
            for asin in hits:
                w.writerow({"ASIN": asin, "JAN": j, "SD品番": pid,
                            "購入先URL": f"https://www.superdelivery.com/p/r/pd_p/{pid}/",
                            "卸価格_税抜_1点": r["卸単価_通常_税抜"].strip(), "卸の最小ロット(点)": "1",
                            "在庫": "未確認", "確認時刻": r.get("取得日", "").strip(),
                            "確認者": "カズヨ(Chrome実画面・SD JAN照合済み)",
                            "メモ": "通常単価（初回限定割引は使わない）",
                            "卸サイト": "スーパーデリバリー", "仕入れ先": a.supplier, "JAN照合": "済",
                            "購入元の名前": a.buyer_name or a.supplier})
    stage = STAGE / f"keepa_stage_{a.tag}.jsonl"
    with stage.open("w") as f:
        for asin in asins:
            p, fetched, _, _ = store.product(asin)
            f.write(json.dumps({"asin": asin, "fetched": fetched, "product": p}, ensure_ascii=False) + "\n")
    print(f"書き出し {out.name}・{stage.name}（{len(asins)} ASIN）")
    print(f"Amazon に無い JAN {len(nohit)}: {' '.join(nohit)}")
    print(f"Keepa 消費 {store.tokens_spent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
