#!/usr/bin/env python3
"""SD 企業 → 商品（商品名・商品コード）の索引を、非ログインの HTTP だけで作る。

- 1社ごとに JSONL へ追記し、進捗を別ファイルに保存する。**中断したら同じコマンドで再開する。**
- Cloudflare チャレンジ（"Just a moment"）を検知したらその場で保存して終了コード 2 で抜ける。
  www は連続取得で落ちる（2026-09-20 実測：190件で失敗・2秒間隔でも復帰せず）。日を分ける前提。
- **JAN は取らない。**一覧ページの HTML に JAN は1件も無い（2026-09-30 実測）。JAN が要るなら
  sd_jan_lookup.py（Amazon 起点）を使う。
- 卸価格も取らない（非ログインでは「卸価格は会員のみ公開」）。卸価格は sd_price_fill.js が上書きする。

使い方:
    python3 sd_dealer_index.py --dealers <TSV> --out <dir> [--limit 50] [--sleep 2.2]

TSV は `dealer_id<TAB>name` のヘッダ付き（カズヨ取得の sd_trading_partners_*.tsv）。
--limit は「今回処理する企業数」。優先順位は priority.py が付けた順（--order で渡す）。
"""
from __future__ import annotations
import argparse, gzip, html, io, json, os, re, sys, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
BASE = "https://www.superdelivery.com"
PER_PAGE = 120


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, fetch  # noqa: E402

UA = ""  # 実際の User-Agent は _fetch.py が持つ


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


def dealer_pages(dealer_id: str, sleep: float) -> tuple[list[dict], int | None]:
    """1社の全商品を返す。1ページ目で総件数を読み、必要なページ数だけ回す。"""
    first = fetch(f"{BASE}/p/do/dpsl/{dealer_id}/")
    total = parse_total(first)
    items = parse_items(first)
    if total is None:
        return items, None
    pages = (total + PER_PAGE - 1) // PER_PAGE
    seen = {i["product_code"] for i in items}
    for pg in range(2, pages + 1):
        time.sleep(sleep)
        page = fetch(f"{BASE}/p/do/dpsl/{dealer_id}/all/{pg}/")
        new = [i for i in parse_items(page) if i["product_code"] not in seen]
        if not new:
            break          # ページ構造が変わった／末尾に達した
        seen.update(i["product_code"] for i in new)
        items.extend(new)
    return items, total


def load_dealers(tsv: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(tsv, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2 or parts[0] in ("dealer_id", ""):
                continue
            rows.append((parts[0].strip(), parts[1].strip()))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dealers", required=True, help="dealer_id<TAB>name の TSV")
    ap.add_argument("--out", required=True, help="出力ディレクトリ（agent_output/.../sd/）")
    ap.add_argument("--order", help="優先順（dealer_id を1行1件・priority.py の出力）")
    ap.add_argument("--limit", type=int, default=0, help="今回処理する企業数（0=全部）")
    ap.add_argument("--sleep", type=float, default=4.0,
                    help="リクエスト間隔（秒）。2.0 では 429 を踏んだ（2026-09-30 実測）")
    ap.add_argument("--approved-by-secretary", action="store_true",
                    help="秘書の判断で全件スキャンを再開する場合にだけ付ける（既定では起動しない）")
    args = ap.parse_args()

    # 🔴 2026-09-30 使用停止（法務判定・成果物29）
    #   このスクリプトは /p/do/dpsl/ を企業数ぶん連続で叩く＝母数の全件スキャン。
    #   法務の推奨Aに従い「発注候補に挙がった社だけを、発注の手前で読む」方針に切り替えたため、
    #   既定では起動しない。再開には秘書（と必要なら社長）の判断が要る。
    if not getattr(args, "approved_by_secretary", False):
        print("■ このスクリプトは 2026-09-30 に使用停止しました（法務判定・成果物29）。\n"
              "  理由: /p/do/dpsl/ を企業数ぶん連続取得する＝母数の全件スキャン。\n"
              "        名指しクローラ向けの robots.txt が同パスを全面 Disallow しており、\n"
              "        会員規約 第10条(2)(5) で予告なし即時の利用停止・登録抹消が可能・\n"
              "        第11条1項で賠償責任も否定されている（争う足場がない）。\n"
              "  代わりに: 発注候補に挙がった社だけを発注の手前で読む／Amazon 起点の\n"
              "        sd_jan_lookup.py（1日30回・間隔10秒・在席下）を使う。\n"
              "  それでも必要なら --approved-by-secretary を付けて、判断した人と根拠をチケットに残すこと。",
              file=sys.stderr)
        return 3

    os.makedirs(args.out, exist_ok=True)
    items_path = os.path.join(args.out, "sd_products.jsonl")
    prog_path = os.path.join(args.out, "sd_index_progress.json")
    progress = json.load(open(prog_path)) if os.path.exists(prog_path) else {"done": {}, "failed": {}}

    dealers = load_dealers(args.dealers)
    names = dict(dealers)
    if args.order and os.path.exists(args.order):
        order = [l.strip() for l in open(args.order, encoding="utf-8") if l.strip()]
        rank = {d: i for i, d in enumerate(order)}
        dealers.sort(key=lambda d: rank.get(d[0], 10 ** 9))

    todo = [d for d in dealers if d[0] not in progress["done"]]
    if args.limit:
        todo = todo[: args.limit]
    print(f"対象 {len(todo)}社（済 {len(progress['done'])}社 / 全 {len(dealers)}社）", flush=True)

    with open(items_path, "a", encoding="utf-8") as sink:
        for n, (did, name) in enumerate(todo, 1):
            try:
                items, total = dealer_pages(did, args.sleep)
            except Blocked as exc:
                print(f"\n■ Cloudflare に止められました（{exc}）。ここまでを保存して終了します。", flush=True)
                json.dump(progress, open(prog_path, "w"), ensure_ascii=False, indent=1)
                return 2
            except Failed as exc:
                progress["failed"][did] = str(exc)[:200]
                print(f"  × {did} {name}: {exc}", flush=True)
                json.dump(progress, open(prog_path, "w"), ensure_ascii=False, indent=1)
                time.sleep(args.sleep)
                continue
            for it in items:
                sink.write(json.dumps(
                    {"dealer_id": did, "dealer_name": names.get(did, name),
                     "product_code": it["product_code"], "name": it["name"]},
                    ensure_ascii=False) + "\n")
            sink.flush()
            progress["done"][did] = {"items": len(items), "total": total,
                                     "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            json.dump(progress, open(prog_path, "w"), ensure_ascii=False, indent=1)
            print(f"  {n}/{len(todo)} {did} {name}: {len(items)}件"
                  f"{'' if total in (None, len(items)) else f'（公称{total}件）'}", flush=True)
            time.sleep(args.sleep)
    print("完了", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
