#!/usr/bin/env python3
"""名簿拡張 経路① — Keepa の月販条件を緩めた商品を取得する（T-20260929-001 / 09 §3-0）。

サトル 12 §1 の方法をそのまま使う：
  月販の表示は50個が最小で、30個・20個は Keepa で切れない。代わりにカテゴリ別の売れ筋ランクで
  「月30個相当（①a）」「月20個相当（①b）」まで広げる。換算ランクは 12_calc/rank_cut.json（推測値）。

  共通条件 … T-20260930-001 の入口(a)（FBA≥1 かつ新品オファー≥2）・3,000円以上・親子は1件（singleVariation）
  ①a … ランク ≤ R30（月30個相当）
  ①b … ランク ≤ R20（月20個相当）で ①a に無いもの

  既存の取得済み ASIN（T-20260930-001 の order*.json とサトルの抜き取り300件）は取らない。
  取得順は ①a → ①b、各段の中でファッションは最後（12 §1-3 で送れる社がほぼ出なかったため。落とさず後回し）。

    python3 14a_keepa_fetch.py lists     # Finder 一覧（①a は新規 15本、①b はサトルのキャッシュを読む）
    python3 14a_keepa_fetch.py fetch     # product を 100件ずつ（1 token/ASIN・20 token/分 → 約1,200件/時）

  - 生データは agent_output/T-20260930-001/raw/ に gzip（keepa_io と同じ置き場・Keepa 規約で PUBLIC に出さない）
  - バッチ単位でキャッシュするので、止まっても同じコマンドで続きから再開する
  - 1 token も使わずに再計算したいときは 14b_build_roster.py（--from-raw 相当）
"""
from __future__ import annotations

import json
import runpy
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
T1 = HERE.parent / "T-20260930-001"
sys.path.insert(0, str(T1))
import keepa_io  # noqa: E402

WORK = keepa_io.RAW.parent.parent / "T-20260929-001"
CALC = WORK / "12_calc"
OUT = WORK / "14_roster"
FASHION = "2229202051"

F = runpy.run_path(str(T1 / "10_funnel.py"), run_name="lib")
BASE = F["selection_upto"](len(F["STEPS"]) - 1)
# サトル 12 の q1_sample.py と同じ組み立て（同じ選択式＝同じキャッシュを読む）
W = {**{k: v for k, v in BASE.items() if k not in ("offerCountFBA_gte", "monthlySold_gte", "current_SALES_lte")},
     "offerCountFBA_gte": 1, "current_COUNT_NEW_gte": 2, "singleVariation": True}
CUTS = json.loads((CALC / "rank_cut.json").read_text())


def log(*a):
    print(time.strftime("%m-%d %H:%M"), *a, flush=True)


def _list(root: str, rank_max: int, tag: str) -> list[str]:
    sel = {**W, "current_SALES_lte": rank_max, "rootCategory": [int(root)], "current_NEW_gte": 3000,
           "perPage": 10000, "page": 0}
    d = keepa_io.finder(sel, tag)
    return d.get("asinList") or []


def known() -> set[str]:
    s: set[str] = set()
    for fn in ("order.json", "order_wideA.json", "order_seller.json"):
        p = keepa_io.RAW / fn
        if p.exists():
            s |= set(json.loads(p.read_text()))
    return s


def lists() -> None:
    have = known()
    a, b = [], []
    for root, c in CUTS.items():
        t30 = _list(root, c["R30"], "r14t30")
        t20 = _list(root, c["R20"], "r12list")  # サトルの取得済み（ファッションは先頭10,000件で頭打ち）
        s30 = set(t30)
        a += [(x, root) for x in t30 if x not in have]
        b += [(x, root) for x in t20 if x not in s30 and x not in have]
        log(c["name"], "T30", len(t30), "T20", len(t20))
    # ファッションは各段の最後。段の中の順番はカテゴリの並び（rank_cut.json の順）のまま
    order_a = list(dict.fromkeys([x for x, r in a if r != FASHION] + [x for x, r in a if r == FASHION]))
    sa = set(order_a)
    order_b = list(dict.fromkeys([x for x, r in b if r != FASHION and x not in sa] +
                                 [x for x, r in b if r == FASHION and x not in sa]))
    (keepa_io.RAW / "order_r14a.json").write_text(json.dumps(order_a))
    (keepa_io.RAW / "order_r14b.json").write_text(json.dumps(order_b))
    root_of = {x: r for x, r in a + b}
    (OUT / "r14_root_of.json").write_text(json.dumps(root_of))
    log("①a 新規ASIN", len(order_a), "①b 新規ASIN", len(order_b), "既存で除いたASIN数", len(have))


def fetch() -> None:
    # サトルの抜き取り300件は取得済み（tag r12samp）。中身は 14b がキャッシュから読む
    samp = {a for a, _ in json.loads((CALC / "q1_sample_asins.json").read_text())}
    for tag in ("r14a", "r14b"):
        order = [x for x in json.loads((keepa_io.RAW / f"order_{tag}.json").read_text()) if x not in samp]
        # 抜き取り分を除いた順番を固定して保存（バッチ番号がずれないように）
        fp = keepa_io.RAW / f"order_{tag}_fetch.json"
        if fp.exists():
            order = json.loads(fp.read_text())
        else:
            fp.write_text(json.dumps(order))
        log(f"{tag} 開始 {len(order)}件")
        keepa_io.products(order, tag, log=log)
        log(f"{tag} 完了")
        (OUT / f"DONE_{tag}").write_text(time.strftime("%Y-%m-%d %H:%M"))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    {"lists": lists, "fetch": fetch}[sys.argv[1]]()
