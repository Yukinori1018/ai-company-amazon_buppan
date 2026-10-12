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

🔴 **JAN で0件＝SD に無い、ではない**（2026-10-12 追加・T-20261012-001）
    サンリオ おせわセット クロミ（JAN 4550624199285）は JAN で0件だったが、SD の1ページに
    キティ／シナモロール／クロミを S1〜S3 の内訳にした1ページで出ていた（内訳にメーカー品番
    199281 はあるが JAN は無い）。だから `--queue-csv` で商品名・ブランドを渡すと、
    **JAN → メーカー品番 → 商品名の主要語** の3段で引く（`sd_query_plan.py`）。
    * 段を進めるたびに1リクエスト＝**回数枠を1つ使う**（枠・間隔・在席の縛りは同じ）
    * ②③で当たった行は `needs_page_check: true`。**商品ページの内訳の品番を人が見るまで候補扱い**
    * 3段とも0件でも `verdict` は「SD に無い」とは書かない
    * `--jan-file`（JAN だけ）で渡した行は商品名が無いので①だけ。`verdict` に「品番・名前は未照会」と残す

使い方:
    python3 sd_jan_lookup.py --jan-file jans.txt --out out.jsonl --attended
    python3 sd_jan_lookup.py --jan 4903779138287 --attended
    python3 sd_jan_lookup.py --queue-csv queue.csv --out out.jsonl --attended   # 3段で引く
        （queue.csv は列 JAN・商品名・ブランド、任意で メーカー品番。sd_lookup_list.py の出力をそのまま渡せる）

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
import sd_query_plan                                                  # noqa: E402

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


def search_url(word: str) -> str:
    """問い合わせ先。`*` 宛の robots.txt の Disallow 対象外（2026-09-30 実測）。

    JAN でも品番でも名前でも同じ口。日本語・空白は URL エンコードする。
    """
    return sd_query_plan.search_url(word)


def lookup(jan: str, fetcher=None) -> dict:
    """SD に1回だけ問い合わせる。`fetcher` はテスト用（既定はモジュールの `fetch`）。"""
    page = (fetcher or fetch)(search_url(jan))
    hits = parse_hits(page)
    return {"jan": jan, "hit_count": len(hits), "hits": hits}


def lookup_tiered(jan: str, title: str = "", brand: str = "", model: str = "",
                  fetcher=None, take=lambda: None) -> dict:
    """JAN → メーカー品番 → 商品名の主要語 の順に、**当たった段で止める**。

    `take` は1リクエストごとに呼ぶ（回数枠の消費。上限なら BudgetExceeded が飛ぶ）。
    429・上限は**呼び出し側へそのまま投げる**（途中の段の結果は捨てる＝0件に化けさせない）。
    """
    tried: list[dict] = []
    for tier, word in sd_query_plan.plan(jan, title, brand, model):
        take()
        hits = parse_hits((fetcher or fetch)(search_url(word)))
        tried.append({"tier": tier, "word": word, "hit_count": len(hits)})
        if hits:
            return {"jan": jan, "hit_count": len(hits), "hits": hits, "matched_by": tier,
                    "needs_page_check": tier != "jan", "queries": tried,
                    "verdict": ("JAN で一致" if tier == "jan" else
                                f"{'品番' if tier == 'partno' else '名前'}で候補あり（JAN 未確認。"
                                "商品ページの内訳の品番を見て確定する）")}
    has_more = bool(title or model)
    return {"jan": jan, "hit_count": 0, "hits": [], "matched_by": None,
            "needs_page_check": False, "queries": tried,
            "verdict": ("3段とも0件（SD に無いとは限らない：表記揺れ・出展企業の非公開ページ）"
                        if has_more else "JAN で0件・品番と名前は未照会（SD に無いとは言えない）")}


def read_queue_csv(path: str) -> list[dict]:
    """列 JAN・商品名・ブランド（任意で メーカー品番）の CSV を読む。1セルに複数 JAN なら分ける。"""
    import csv
    rows: list[dict] = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        for j in re.split(r"[;／/\s,]+", r.get("JAN", "") or ""):
            j = re.sub(r"\D", "", j)
            if 8 <= len(j) <= 13:
                rows.append({"jan": j, "title": r.get("商品名", ""), "brand": r.get("ブランド", ""),
                             "model": r.get("メーカー品番", "")})
    return rows


def read_jans(args) -> list[str]:
    jans: list[str] = []
    if args.jan:
        jans.append(re.sub(r"\D", "", args.jan))
    if args.jan_file:
        for line in open(args.jan_file, encoding="utf-8"):
            # 行は `JAN` か `JAN<TAB># メモ`。**行末のメモの数字を JAN に混ぜない**
            head = re.split(r"[\s,#]", line.strip(), maxsplit=1)[0]
            if head and not line.lstrip().startswith("#"):
                jans.append(re.sub(r"\D", "", head))
    return [j for j in dict.fromkeys(jans) if 8 <= len(j) <= 13]


def main(argv: list[str] | None = None, sleep=time.sleep) -> int:
    """`sleep` はテスト用の差し替え口。**上限や間隔を緩める引数は作らない。**"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--jan")
    ap.add_argument("--jan-file", help="1行1JAN のテキスト。# で始まる行は無視")
    ap.add_argument("--queue-csv", help="列 JAN・商品名・ブランド の CSV。JAN→品番→名前の3段で引く")
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

    meta: dict[str, dict] = {}
    if args.queue_csv:
        for r in read_queue_csv(args.queue_csv):
            meta.setdefault(r["jan"], r)
    jans = list(dict.fromkeys(read_jans(args) + list(meta)))
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
                m = meta.get(jan, {})
                res = lookup_tiered(jan, m.get("title", ""), m.get("brand", ""),
                                    m.get("model", ""), take=budget.take)
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
                  f"（{res.get('matched_by') or '一致なし'}・{len(res.get('queries', []))}回）"
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
