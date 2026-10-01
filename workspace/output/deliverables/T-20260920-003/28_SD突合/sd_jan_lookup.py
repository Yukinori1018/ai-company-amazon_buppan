#!/usr/bin/env python3
"""【レーンA・主】JAN → SD に在るか（＝どの出展企業のどの商品か）を非ログインの HTTP で引く。

CLAUDE.md §3.3-9「売れている棚を、卸で買えるか」を回すための本体。
Amazon 側で生存を確認した ASIN の JAN を投げると、SD 側の商品コード・商品名・出展企業を返す。

- **1 JAN = 1 リクエスト。**企業の全商品を舐める必要がない（一覧は約11,600ページ、こちらは JAN 数ぶん）。
- **ログイン不要。**検証済み：JAN 3件で 3/3 ヒット・無関係商品の混入なし（2026-09-30）。
- **卸価格は返らない**（非ログインでは「卸価格は会員のみ公開」）。ヒットした商品だけ
  ブラウザで価格を見る。ここで母数が2〜3桁減る。

🔴 上限（`_budget.py` の `LANE_A` で定数固定。**引数では緩められない**）
    * **1日30件**まで（日付ごとにカウンタを残す。プロセスを再起動しても戻らない）
    * **間隔10.0秒から始める**。429/503 が出たらその日は打ち切り、翌日は倍（→20→40→80→160秒）。
      429 が出なければ現状維持。連続3日出なければ1段戻す（`_backoff.py`）
    * **`--attended` 必須。**無人運転は不可
    * SD には**同時に2本走らせない**（2026-09-30、別スキャンと並走させて 429 を連発した）

🔴 間隔160秒でも1日30件なら80分。**上限に当たっても諦めない。**

使い方:
    python3 sd_jan_lookup.py --jan-file jans.txt --out out.jsonl --attended
    python3 sd_jan_lookup.py --jan 4903779138287 --attended

終了コード:
    0 正常 / 1 引数か在席の不備 / 2 Cloudflare / 4 停止中（SUSPENDED）
    5 429 でその日を打ち切った（**明日、間隔を1段上げて再開する**）
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time

BASE = "https://www.superdelivery.com"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, RateLimited, fetch               # noqa: E402
from _budget import (LANE_A, Budget, BudgetExceeded, DayCutOff,      # noqa: E402
                     NotAttended, Suspended)

ITEM_RE = re.compile(
    r'<div class="itembox-parts.*?(?=<div class="itembox-parts|<div class="dvs-loading|\Z)', re.S)


def parse_hits(page_html: str) -> list[dict]:
    """検索結果ページから (商品コード, 商品名, 出展企業ID) を取る。

    出展企業IDはブロック内の analytics 文字列 `.../registBtn/<dealer_id>` か、
    出展企業リンク `/p/do/dpsl/<dealer_id>/` から拾う。どちらも無ければ None。
    """
    hits: list[dict] = []
    seen: set[str] = set()
    for block in ITEM_RE.findall(page_html):
        m = re.search(r"/p/r/pd_p/(\d+)/", block)
        if not m:
            continue
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)
        nm = re.search(r'<div class="item-name">\s*<a[^>]*>(.*?)</a>', block, re.S)
        if nm:
            name = html.unescape(re.sub(r"<[^>]+>", "", nm.group(1))).strip()
        else:
            nm2 = re.search(r'title="([^"]+)"', block)
            name = html.unescape(nm2.group(1)).strip() if nm2 else ""
        dm = (re.search(r"registBtn/(\d+)", block)
              or re.search(r"/p/do/dpsl/(\d+)/", block))
        hits.append({
            "product_code": code,
            "name": name,
            "dealer_id": dm.group(1) if dm else None,
            "product_url": f"{BASE}/p/r/pd_p/{code}/",
        })
    return hits


def search_url(jan: str) -> str:
    """問い合わせ先。`*` 宛の robots.txt の Disallow 対象外（2026-09-30 実測）。"""
    return f"{BASE}/p/do/psl/?word={jan}"


def lookup(jan: str, fetcher=None) -> dict:
    """SD に1回だけ問い合わせる。`fetcher` はテスト用（既定はモジュールの `fetch`）。"""
    page = (fetcher or fetch)(search_url(jan))
    hits = parse_hits(page)
    return {"jan": jan, "hit_count": len(hits), "hits": hits}


def read_jans(args) -> list[str]:
    jans: list[str] = []
    if args.jan:
        jans.append(re.sub(r"\D", "", args.jan))
    if args.jan_file:
        for line in open(args.jan_file, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                jans.append(re.sub(r"\D", "", s))
    return [j for j in dict.fromkeys(jans) if 8 <= len(j) <= 13]


def main(argv: list[str] | None = None, sleep=time.sleep) -> int:
    """`sleep` はテスト用の差し替え口。**上限や間隔を緩める引数は作らない。**"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--jan")
    ap.add_argument("--jan-file", help="1行1JAN のテキスト。# で始まる行は無視")
    ap.add_argument("--out", help="JSONL の出力先。既にある JAN はスキップ（再開できる）")
    ap.add_argument("--attended", action="store_true",
                    help="人が在席していることを明示する。**付けないと動かない**（法務判定・成果物29 §5）")
    ap.add_argument("--state-dir", default=None,
                    help="回数カウンタとバックオフ状態の置き場。既定は --out と同じ場所")
    args = ap.parse_args(argv)

    # 🔴 回数・間隔・在席はレーンAの定数で縛る。引数では緩められない（_budget.py / _backoff.py）
    state_dir = args.state_dir or (os.path.dirname(os.path.abspath(args.out)) if args.out else ".")
    try:
        budget = Budget(state_dir, attended=args.attended, lane=LANE_A, sleep=sleep)
    except Suspended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 4
    except NotAttended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 1
    except DayCutOff as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 5
    print(budget.describe(), flush=True)

    jans = read_jans(args)
    if not jans:
        print("JAN がありません", file=sys.stderr)
        return 1

    done: set[str] = set()
    if args.out and os.path.exists(args.out):
        for line in open(args.out, encoding="utf-8"):
            try:
                done.add(json.loads(line)["jan"])
            except Exception:
                pass
    todo = [j for j in jans if j not in done]
    print(f"対象 {len(todo)} JAN（済 {len(done)}）", flush=True)
    if len(todo) > budget.remaining:
        print(f"■ 本日の残り {budget.remaining} 回を超えるので、先頭 {budget.remaining} 件だけ実行します",
              flush=True)
        todo = todo[: budget.remaining]

    sink = open(args.out, "a", encoding="utf-8") if args.out else None
    found = 0
    n = 0
    rate_limited = False
    try:
        for n, jan in enumerate(todo, 1):
            try:
                budget.take()
                res = lookup(jan)
            except BudgetExceeded as exc:
                print(f"■ {exc}", flush=True)
                n -= 1
                break
            except RateLimited as exc:
                # 🔴 1件の失敗として飲み込まない。その日を打ち切り、翌日は間隔を1段上げる
                nxt = budget.note_rate_limited()
                rate_limited = True
                print(f"■ {exc}\n  → 本日はここで打ち切ります。明日は間隔 {nxt:.1f} 秒で再開します。",
                      flush=True)
                n -= 1
                break
            except Blocked:
                print("■ Cloudflare に止められました。ここまでを保存して終了します。", flush=True)
                n -= 1
                break
            except Failed as exc:
                res = {"jan": jan, "hit_count": None, "hits": [], "error": str(exc)[:200]}
            if res["hit_count"]:
                found += 1
            line = json.dumps(res, ensure_ascii=False)
            if sink:
                sink.write(line + "\n")
                sink.flush()
            else:
                print(line)
            print(f"  {n}/{len(todo)} {jan}: {res['hit_count']}件"
                  f"（本日の残り {budget.remaining}）", flush=True)
    finally:
        if sink:
            sink.close()
        stepped = budget.finish()
        if stepped:
            print(f"■ 429 なしが続いたので間隔を1段戻しました → {budget.interval:.1f} 秒", flush=True)
    print(f"ヒットした JAN: {found} / 走らせた {max(n, 0)}。{budget.describe()}", flush=True)
    return 5 if rate_limited else 0


if __name__ == "__main__":
    sys.exit(main())
