#!/usr/bin/env python3
"""JAN → SD に在るか（＝どの出展企業のどの商品か）を、非ログインの HTTP で引く。

CLAUDE.md §3.3-9「売れている棚を、卸で買えるか」を回すための本体。
Amazon 側で生存を確認した ASIN の JAN を投げると、SD 側の商品コード・商品名・出展企業を返す。

- **1 JAN = 1 リクエスト。**企業の全商品を舐める必要がない（一覧は約11,600ページ、こちらは JAN 数ぶん）。
- **ログイン不要。**検証済み：JAN 3件で 3/3 ヒット・無関係商品の混入なし（2026-09-30）。
- **卸価格は返らない**（非ログインでは「卸価格は会員のみ公開」）。ヒットした商品だけ
  sd_price_fill.js またはブラウザで価格を見る。ここで母数が2〜3桁減る。
- 🔴 **法務判定（成果物29 §5）により、実行は次の枠内に限る。**この3つは `_budget.py` の定数で
  機械的に縛られており、引数では緩められない。超えたら例外で止まる。
    * **1日30回**まで（日付ごとにカウンタを残す。プロセスを再起動しても戻らない）
    * **間隔10.0秒**（robots.txt の Crawl-delay は `*` グループには無いが、名指しクローラ向けに
      10 が示されているのでその値に合わせる）
    * **人（秘書カズヨ）の在席下のみ。`--attended` を明示しないと起動しない。無人運転は不可**
- SD には**同時に2本走らせない**（2026-09-30、別スキャンと並走させて 429 を連発した）。

使い方:
    python3 sd_jan_lookup.py --jan-file jans.txt --out out.jsonl --attended
    python3 sd_jan_lookup.py --jan 4903779138287 --attended
"""
from __future__ import annotations
import argparse, gzip, html, json, os, re, sys, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
BASE = "https://www.superdelivery.com"


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, fetch  # noqa: E402
from _budget import (Budget, BudgetExceeded, NotAttended, Suspended,  # noqa: E402
                     MAX_PER_DAY, MIN_INTERVAL)

UA = ""  # 実際の User-Agent は _fetch.py が持つ


ITEM_RE = re.compile(r'<div class="itembox-parts.*?(?=<div class="itembox-parts|<div class="dvs-loading|\Z)', re.S)


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


def lookup(jan: str) -> dict:
    page = fetch(f"{BASE}/p/do/psl/?word={jan}")
    hits = parse_hits(page)
    return {"jan": jan, "hit_count": len(hits), "hits": hits}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jan")
    ap.add_argument("--jan-file", help="1行1JAN のテキスト。# で始まる行は無視")
    ap.add_argument("--out", help="JSONL の出力先。既にある JAN はスキップ（再開できる）")
    ap.add_argument("--attended", action="store_true",
                    help="秘書が在席していることを明示する。**付けないと動かない**（法務判定・成果物29 §5）")
    ap.add_argument("--state-dir", default=None,
                    help="1日の回数カウンタの置き場。既定は --out と同じ場所")
    args = ap.parse_args()

    # 🔴 回数・間隔・在席は定数で縛る。引数で緩められない（_budget.py）
    state_dir = args.state_dir or (os.path.dirname(os.path.abspath(args.out)) if args.out else ".")
    try:
        budget = Budget(state_dir, attended=args.attended, label="sd_jan")
    except Suspended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 4
    except NotAttended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 1
    print(f"本日の残り {budget.remaining} / {MAX_PER_DAY} 回・間隔 {MIN_INTERVAL:.1f} 秒", flush=True)

    jans: list[str] = []
    if args.jan:
        jans.append(args.jan.strip())
    if args.jan_file:
        for line in open(args.jan_file, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                jans.append(re.sub(r"\D", "", s))
    jans = [j for j in dict.fromkeys(jans) if 8 <= len(j) <= 13]
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

    sink = open(args.out, "a", encoding="utf-8") if args.out else None
    found = 0
    if len(todo) > budget.remaining:
        print(f"■ 本日の残り {budget.remaining} 回を超えるので、先頭 {budget.remaining} 件だけ実行します",
              flush=True)
        todo = todo[: budget.remaining]
    n = 0
    for n, jan in enumerate(todo, 1):
        try:
            budget.take()
            res = lookup(jan)
        except BudgetExceeded as exc:
            print(f"■ {exc}", flush=True)
            break
        except Blocked:
            print("■ Cloudflare に止められました。ここまでを保存して終了します。", flush=True)
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
        print(f"  {n}/{len(todo)} {jan}: {res['hit_count']}件（本日の残り {budget.remaining}）", flush=True)
    if sink:
        sink.close()
    print(f"ヒットした JAN: {found} / 走らせた {n}。本日の残り {budget.remaining} 回", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
