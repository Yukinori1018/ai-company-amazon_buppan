#!/usr/bin/env python3
"""【レーンB・併用】**発注候補に挙がった社だけ**の商品一覧（商品名・商品コード）を取る。

🔴 2026-10-01、**全件スキャン（レーンC）の経路を削除した。**
    以前は `--dealers <TSV>` に 2,176社を渡して舐める作りだった。それはもう無い。
    **`--dealer-ids` で明示した社だけ**が対象（CLAUDE.md §3.3-18）。

🔴 上限（`_budget.py` の `LANE_B` で定数固定。**引数では緩められない**）
    * **間隔3.0秒から**（429 が出たら翌日は 6→12→24→48 秒）
    * **1セッション20リクエスト・1日50リクエスト**
      上限の単位は **リクエスト**。1社でページ送りが複数枚あれば複数回ぶん消費する
      （安全側。`--max-pages` で1社あたりの枚数を縛る）
    * **`--attended` 必須。**無人運転は不可

- 1社ごとに JSONL へ追記し、進捗を別ファイルに保存する。**中断したら同じコマンドで再開する。**
- **JAN は取らない。**一覧ページの HTML に JAN は1件も無い（2026-09-30 実測）。
  JAN が要るなら `sd_jan_lookup.py`（レーンA・Amazon 起点）を使う。
- 卸価格も取らない（非ログインでは「卸価格は会員のみ公開」）。

使い方:
    python3 sd_dealer_index.py --dealer-ids 12345,67890 --out <dir> --attended
    python3 sd_dealer_index.py --dealer-ids @candidates.txt --out <dir> --attended --max-pages 2

終了コード:
    0 正常 / 1 引数か在席の不備 / 2 Cloudflare / 4 停止中 / 5 429 でその日を打ち切った
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
PER_PAGE = 120

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, RateLimited, fetch               # noqa: E402
from _budget import (LANE_B, Budget, BudgetExceeded, DayCutOff,      # noqa: E402
                     NotAttended, SessionLimitReached, Suspended)
from sd_dealer_terms import read_dealer_ids, read_names             # noqa: E402


def parse_total(page_html: str) -> int | None:
    """「1 ～ 120件（全1339件）」から総件数を取る。"""
    m = re.search(r"全([0-9,]+)件", page_html)
    return int(m.group(1).replace(",", "")) if m else None


def parse_items(page_html: str) -> list[dict]:
    """一覧ページから (商品コード, 商品名) を重複なく取る。

    item-name ブロックの <a href="/p/r/pd_p/<code>/" ...>商品名</a> を拾う。
    画像 alt からも拾えるが、同一商品で2回出るので item-name を正とする。
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<div class="item-name">\s*<a href="/p/r/pd_p/(\d+)/"[^>]*>(.*?)</a>',
        page_html, re.S,
    ):
        code, name = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        name = html.unescape(name).strip()
        if code in seen:
            continue
        seen.add(code)
        out.append({"product_code": code, "name": name})
    if out:
        return out
    # フォールバック: item-name の構造が変わった場合は img title から拾う
    for m in re.finditer(r'<a href="/p/r/pd_p/(\d+)/"[^>]*>.*?title="([^"]*)"', page_html, re.S):
        code, name = m.group(1), html.unescape(m.group(2)).strip()
        if code in seen or not name:
            continue
        seen.add(code)
        out.append({"product_code": code, "name": name})
    return out


def dealer_pages(dealer_id: str, budget, max_pages: int) -> tuple[list[dict], int | None]:
    """1社の商品を返す。**ページ送りの1枚ごとに budget を消費する。**

    例外（`RateLimited` / `BudgetExceeded` / `Blocked` / `Failed`）はそのまま呼び出し側へ上げる。
    **ここで握って部分結果を「全部」として返さない**（0件に化けるのが一番危ない）。
    """
    budget.take()
    first = fetch(f"{BASE}/p/do/dpsl/{dealer_id}/")
    total = parse_total(first)
    items = parse_items(first)
    if total is None:
        return items, None
    pages = min((total + PER_PAGE - 1) // PER_PAGE, max_pages)
    seen = {i["product_code"] for i in items}
    for pg in range(2, pages + 1):
        budget.take()
        page = fetch(f"{BASE}/p/do/dpsl/{dealer_id}/all/{pg}/")
        new = [i for i in parse_items(page) if i["product_code"] not in seen]
        if not new:
            break          # ページ構造が変わった／末尾に達した
        seen.update(i["product_code"] for i in new)
        items.extend(new)
    return items, total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dealer-ids", required=True,
                    help="発注候補に挙がった社の dealer_id。`12345,67890` か `@file`。"
                         "**明示した社だけが対象**（全件スキャンの経路は無い）")
    ap.add_argument("--out", required=True, help="出力ディレクトリ（agent_output/.../sd/）")
    ap.add_argument("--names-tsv", help="dealer_id<TAB>name の TSV（表示名の補完にだけ使う）")
    ap.add_argument("--max-pages", type=int, default=3,
                    help="1社あたりに開く一覧ページの枚数（既定3）。上限は回数で縛られる")
    ap.add_argument("--attended", action="store_true",
                    help="人が在席していることを明示する。**付けないと動かない**")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    try:
        budget = Budget(args.out, attended=args.attended, lane=LANE_B)
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

    items_path = os.path.join(args.out, "sd_products.jsonl")
    prog_path = os.path.join(args.out, "sd_index_progress.json")
    progress = (json.load(open(prog_path, encoding="utf-8")) if os.path.exists(prog_path)
                else {"done": {}, "failed": {}})
    progress.setdefault("done", {})
    progress.setdefault("failed", {})

    names = read_names(args.names_tsv)
    wanted = read_dealer_ids(args.dealer_ids)
    todo = [d for d in wanted if d not in progress["done"]]
    print(f"指定 {len(wanted)}社・未取得 {len(todo)}社（済 {len(progress['done'])}）", flush=True)
    if not todo:
        budget.finish()
        print("取るものがありません", flush=True)
        return 0

    rate_limited = False
    try:
        with open(items_path, "a", encoding="utf-8") as sink:
            for n, did in enumerate(todo, 1):
                name = names.get(did, "")
                try:
                    items, total = dealer_pages(did, budget, args.max_pages)
                except SessionLimitReached as exc:
                    print(f"■ {exc}", flush=True)
                    break
                except BudgetExceeded as exc:
                    print(f"■ {exc}", flush=True)
                    break
                except RateLimited as exc:
                    nxt = budget.note_rate_limited()
                    rate_limited = True
                    print(f"■ {exc}\n  → 本日はここで打ち切ります。明日は間隔 {nxt:.1f} 秒で再開します。",
                          flush=True)
                    break
                except Blocked as exc:
                    print(f"\n■ Cloudflare に止められました（{exc}）。保存して終了します。", flush=True)
                    break
                except Failed as exc:
                    progress["failed"][did] = str(exc)[:200]
                    print(f"  × {did} {name}: {exc}", flush=True)
                    continue
                for it in items:
                    sink.write(json.dumps(
                        {"dealer_id": did, "dealer_name": name,
                         "product_code": it["product_code"], "name": it["name"]},
                        ensure_ascii=False) + "\n")
                sink.flush()
                progress["done"][did] = {"items": len(items), "total": total,
                                         "pages_cap": args.max_pages,
                                         "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                more = "" if total in (None, len(items)) else f"（公称{total}件・先頭だけ取得）"
                print(f"  {n}/{len(todo)} {did} {name}: {len(items)}件{more}", flush=True)
    finally:
        with open(prog_path, "w", encoding="utf-8") as fh:
            json.dump(progress, fh, ensure_ascii=False, indent=1)
        if budget.finish():
            print(f"■ 429 なしが続いたので間隔を1段戻しました → {budget.interval:.1f} 秒", flush=True)
    print(f"完了。{budget.describe()}", flush=True)
    return 5 if rate_limited else 0


if __name__ == "__main__":
    sys.exit(main())
