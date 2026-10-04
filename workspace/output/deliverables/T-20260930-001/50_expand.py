"""母数の追加：入口(a) と セラーリサーチ（本書 Ch.5-04）で ASIN を足す（T-20260930-001 / 2026-10-04）。

    python3 50_expand.py lists --sellers 30   # Finder で一覧だけ作る（a: 約220 token／セラー: 約15 token×人数）
    python3 50_expand.py fetch                # 一覧の product を取る（1 token/ASIN・中断点から再開）
    python3 30_build.py --from-raw            # 3つの入口をまとめて集約・除外

入口(a)  = 10_funnel.py の全条件のうち「FBA≥2」を「新品オファー≥2 かつ FBA≥1」に替えた Finder 一覧 − 基本の一覧
セラー   = 台帳の接触候補・今回残した社の代表 ASIN でカートを持つ第三者セラー（Amazon 本体・本人カート疑いを除く）を
           カート保持の回数が多い順に並べ、Finder の sellerIds で「そのセラーが出品している商品」を入口条件つきで引く。
           ランク≤5万・カートFBA・カートが今 Amazon でない（スナップショット）は掛けない＝基本の一覧から漏れた分が拾える。
           月販≥50（積極条件）・FBA≥2・売価≥2,200・365日 BB 本体≤10% は掛ける。本体の判定は 30_build.py の oos365 で再判定。
出力: raw/order_wideA.json / raw/order_seller.json（＋seller_rank.json：どのセラーから何件来たか）
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import runpy
from collections import Counter
from pathlib import Path

import keepa_io
from maker_rules import EXCLUDE_ROOTS

HERE = Path(__file__).resolve().parent
WORK = keepa_io.RAW.parent
F = runpy.run_path(str(HERE / "10_funnel.py"), run_name="lib")
BASE = F["selection_upto"](len(F["STEPS"]) - 1)
AMAZON_SELLER = "AN1VRQENFRJN5"
WIDE_A = {**{k: v for k, v in BASE.items() if k != "offerCountFBA_gte"}, "offerCountFBA_gte": 1, "current_COUNT_NEW_gte": 2}
SELLER_ENTRY = {"productType": [0], "isAdultProduct": False, "categories_exclude": EXCLUDE_ROOTS,
                "monthlySold_gte": 50, "offerCountFBA_gte": 2, "current_NEW_gte": 2200, "buyBoxStatsAmazon365_lte": 10}


def _known() -> set[str]:
    out: set[str] = set()
    for fn in ("order.json", "order_wideA.json", "order_seller.json"):
        p = keepa_io.RAW / fn
        if p.exists():
            out |= set(json.loads(p.read_text()))
    return out


def _list(sel: dict, tag: str) -> list[str]:
    """Finder の一覧を全件取る。**Keepa の Finder は先頭 10,000 件までしか返さない**（page=1 は 400 Bad Request・
    2026-10-04 実測）。10,000 件を超えるときは monthlySold の降順と昇順で1本ずつ取り、和集合にする（20,000 件まで）。"""
    d = keepa_io.finder({**sel, "perPage": 10000, "page": 0, "sort": [["monthlySold", "desc"]]}, f"{tag}p0")
    asins = list(d.get("asinList") or [])
    total = d.get("totalResults") or 0
    if total > 10000:
        d2 = keepa_io.finder({**sel, "perPage": 10000, "page": 0, "sort": [["monthlySold", "asc"]]}, f"{tag}asc")
        seen = set(asins)
        asins += [a for a in (d2.get("asinList") or []) if a not in seen]
        if total > 20000:
            print(f"  警告: {tag} は {total} 件。20,000 件を超えた分は取れていない", flush=True)
    return asins


def seller_rank() -> list[tuple[str, int, str]]:
    """カート保持の回数が多い第三者セラー（id, 回数, 名前）。台帳の接触候補と今回残した社の代表 ASIN を合算。"""
    names = json.loads((keepa_io.RAW / "seller_names.json").read_text())
    rev: dict[str, str] = {}
    for sid, n in names.items():
        rev.setdefault(n.strip(), sid)
    c: Counter = Counter()
    led = WORK / "sheet_backup_before_profitcols_20261004.csv"
    if led.exists():
        for r in csv.DictReader(led.open(encoding="utf-8-sig")):
            if r["判定"].startswith("接触候補"):
                n = re.sub(r"（.*?）", "", r["カート保持者(実画面9/30)"]).strip()
                if n in rev:
                    c[rev[n]] += 1
    full = WORK / "10_メーカー候補_完全版.csv"
    for r in csv.DictReader(full.open(encoding="utf-8-sig")):
        if r["優先度"] and not r["要確認"] and r["カート保持セラー(代表)"]:
            sid = rev.get(r["カート保持セラー(代表)"].strip())
            if sid and sid != AMAZON_SELLER:
                c[sid] += 1
    return [(sid, k, names.get(sid, "")) for sid, k in c.most_common()]


def lists(n_sellers: int) -> None:
    known = set(json.loads((keepa_io.RAW / "order.json").read_text()))
    wa = [a for a in _list(WIDE_A, "wideA") if a not in known]
    (keepa_io.RAW / "order_wideA.json").write_text(json.dumps(wa))
    print(f"入口(a) 新規 {len(wa)} ASIN", flush=True)
    known |= set(wa)
    ranked = seller_rank()[:n_sellers]
    out, log = [], []
    for sid, k, name in ranked:
        got = _list({**SELLER_ENTRY, "sellerIds": [sid]}, f"seller_{sid}")
        new = [a for a in got if a not in known]
        known |= set(new); out += new
        log.append({"seller": name, "id": sid, "カート保持回数": k, "入口条件の該当": len(got), "新規": len(new)})
        print(f"  {name[:20]:20} 保持{k:3} 該当{len(got):5} 新規{len(new):5}", flush=True)
    (keepa_io.RAW / "order_seller.json").write_text(json.dumps(out))
    (WORK / "seller_rank.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(f"セラー 新規 {len(out)} ASIN（{len(ranked)} セラー）", flush=True)


def fetch() -> None:
    for fn, tag in (("order_seller.json", "seller"), ("order_wideA.json", "wideA")):
        order = json.loads((keepa_io.RAW / fn).read_text())
        ps = keepa_io.products(order, tag, log=lambda s: print(s, flush=True))
        print(f"DONE {tag} {len(ps)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["lists", "fetch", "rank"])
    ap.add_argument("--sellers", type=int, default=30)
    a = ap.parse_args()
    if a.cmd == "lists":
        lists(a.sellers)
    elif a.cmd == "rank":
        for x in seller_rank()[:40]:
            print(x)
    else:
        fetch()
