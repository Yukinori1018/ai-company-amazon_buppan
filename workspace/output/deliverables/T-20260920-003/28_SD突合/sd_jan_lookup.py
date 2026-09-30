#!/usr/bin/env python3
"""JAN → SD に在るか（＝どの出展企業のどの商品か）を、非ログインの HTTP で引く。

CLAUDE.md §3.3-9「売れている棚を、卸で買えるか」を回すための本体。
Amazon 側で生存を確認した ASIN の JAN を投げると、SD 側の商品コード・商品名・出展企業を返す。

- **1 JAN = 1 リクエスト。**企業の全商品を舐める必要がない（一覧は約11,600ページ、こちらは JAN 数ぶん）。
- **ログイン不要。**検証済み：JAN 3件で 3/3 ヒット・無関係商品の混入なし（2026-09-30）。
- **卸価格は返らない**（非ログインでは「卸価格は会員のみ公開」）。ヒットした商品だけ
  sd_price_fill.js またはブラウザで価格を見る。ここで母数が2〜3桁減る。
- 429 は指数バックオフ。**SD には同時に2本走らせないこと**（2026-09-30、別スキャンと並走させて 429 を連発した）。

使い方:
    python3 sd_jan_lookup.py --jan-file jans.txt --out out.jsonl [--sleep 4.0]
    python3 sd_jan_lookup.py --jan 4903779138287
"""
from __future__ import annotations
import argparse, gzip, html, json, os, re, sys, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
BASE = "https://www.superdelivery.com"


class Blocked(RuntimeError):
    pass


def fetch(url: str, timeout: int = 40, retries: int = 4) -> str:
    wait = 8.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
        try:
            raw = urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < retries:
                time.sleep(wait)
                wait *= 2
                continue
            raise
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", "replace")
        if "Just a moment" in text or "cf-challenge" in text:
            raise Blocked(url)
        return text
    raise urllib.error.URLError("429 が続いたため中断")


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
    ap.add_argument("--sleep", type=float, default=4.0)
    args = ap.parse_args()

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
    for n, jan in enumerate(todo, 1):
        try:
            res = lookup(jan)
        except Blocked:
            print("■ Cloudflare に止められました。ここまでを保存して終了します。", flush=True)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            res = {"jan": jan, "hit_count": None, "hits": [], "error": str(exc)[:200]}
        if res["hit_count"]:
            found += 1
        line = json.dumps(res, ensure_ascii=False)
        if sink:
            sink.write(line + "\n")
            sink.flush()
        else:
            print(line)
        print(f"  {n}/{len(todo)} {jan}: {res['hit_count']}件", flush=True)
        time.sleep(args.sleep)
    if sink:
        sink.close()
    print(f"ヒットした JAN: {found} / 走らせた {min(n if todo else 0, len(todo))}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
