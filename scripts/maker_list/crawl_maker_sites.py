"""(b) メーカー自社HPを巡回して、電話番号・FAX・EC信号・主な製品を補う。

対象は「(a) で自社HPは分かったが電話番号が埋まらなかった社」だけ。
1社あたり トップ → 会社概要 → お問い合わせ の**最大3ページ**（config で変更）。

法的な位置づけ:
  T-20260831-001 Phase B（ハルオ 2026-08-31）で「メーカー公式サイトの低速クロールは可。
  robots.txt 尊重・同一ホスト3秒間隔・UA明示・会社概要/問い合わせ系ページ限定」と
  判定済み。このスクリプトはその条件をそのまま config.py に写している。
  業界団体サイト・楽天・Yahoo!・Amazon には一切アクセスしない。

途中で止めても平気:
  1社終わるごとに maker_pages.jsonl へ追記し、再実行時は済んだ社を飛ばす。

    python3 scripts/maker_list/crawl_maker_sites.py           # 全件（続きから）
    python3 scripts/maker_list/crawl_maker_sites.py --limit 50

1日の上限（config.DAILY_REQUEST_LIMIT = 1500リクエスト）に当たったら、そこで止まる。
翌日もう一度同じコマンドを打てば続きから走る（済んだ社は飛ばす）。
**プロセスを分けて速くしないこと。** 05 §2-4 が「異なるホストへの並列も1で開始」と
明記している条件で、速度のために緩めてよい数字ではない。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maker_list import config as C
from maker_list.extract import ec, phone
from maker_list.extract.htmlutil import flat_text, links, norm_name
from maker_list.fetcher import REASON, Fetcher

OUT = os.path.join(C.WORK_DIR, "maker_pages.jsonl")


def load_targets() -> list[dict]:
    """(a) の結果から「HPはあるが電話番号が無い社」を拾う。"""
    rows: list[dict] = []
    for f in sorted(glob.glob(os.path.join(C.WORK_DIR, "assoc_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            rows.append(json.loads(line))
    # 同じ社が一覧側と詳細側の両方に出る。HP と電話番号が入っている方を採る。
    best: dict[str, dict] = {}
    for r in rows:
        key = norm_name(r["社名"])
        cur = best.get(key)
        if cur is None or (not cur.get("HP起点") and r.get("HP起点")) \
                or (not cur.get("電話番号") and r.get("電話番号")):
            best[key] = r
    return [r for r in best.values() if r.get("HP起点") and not r.get("電話番号")]


def pick_company_pages(base_url: str, raw: str, limit: int) -> list[str]:
    """トップページのリンクから「会社概要/お問い合わせ」系だけを選ぶ。

    ハルオ判定の「会社概要/問い合わせ系ページ限定」を守るための関数。
    ここを緩めると判定の前提が崩れるので、語の追加は config.COMPANY_PAGE_HINTS で。
    """
    host = urlparse(base_url).netloc
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for url, label in links(raw, base_url):
        if not url.startswith("http") or urlparse(url).netloc != host:
            continue
        u = url.split("#")[0]
        if u in seen or u.rstrip("/") == base_url.rstrip("/"):
            continue
        hay = (u + " " + label).lower()
        for i, hint in enumerate(C.COMPANY_PAGE_HINTS):
            if hint.lower() in hay:
                seen.add(u)
                scored.append((i, u))
                break
    scored.sort()
    return [u for _, u in scored[:limit]]


def blank_record(name: str, top: str) -> dict:
    return {"社名": name, "HP起点": top, "取得日": C.today(), "取得時刻": C.fetched_at(),
            "到達": False, "見たページ": [], "電話番号": "", "番号の種別": "",
            "FAX番号": "", "自社EC": "未確認", "自社EC根拠": "", "モール": "未確認",
            "卸OEM記載": "未確認", "主な製品": "", "サイト説明": "",
            "問い合わせURL": "", "備考": ""}


def extract_from_pages(rec: dict, pages: list[tuple[str, str]]) -> dict:
    """取得済みのページ群から値を作る。**ネットに触らない純粋な処理**。

    fetch と extract を分けてあるので、抽出ロジックを直したあとは
    reextract.py でキャッシュから作り直せる（リクエストを1本も増やさずに）。
    """
    if not pages:
        return rec
    # リダイレクトで同じURLが2回入ることがあるので畳む
    seen_u: set[str] = set()
    pages = [(u, b) for u, b in pages if not (u in seen_u or seen_u.add(u))]
    final = pages[0][0]
    rec["到達"] = True
    rec["見たページ"] = [u for u, _ in pages]
    for u, _b in pages[1:]:
        if any(k in u.lower() for k in ("contact", "inquiry", "toiawase", "問い合わせ")):
            rec["問い合わせURL"] = rec["問い合わせURL"] or u

    all_text = "\n".join(flat_text(b) for _, b in pages)
    all_links: list[tuple[str, str]] = []
    for u, b in pages:
        all_links += links(b, u)

    tel, kind, fax = phone.pick_tel_and_fax(all_text)
    rec["電話番号"], rec["番号の種別"], rec["FAX番号"] = tel or "", kind or "", fax or ""
    rec.update(ec.detect(all_links, all_text, own_host=urlparse(final).netloc))
    # 「何を作っているか」は、①本文の事業内容/取扱品目 ②ページの title/description の順。
    # どちらも定型文しか無ければ**空のままにする**（分からないものを分かったように書かない）。
    rec["サイト説明"] = next(
        (d for d in (ec.site_description(b) for _u, b in pages) if d), "")
    rec["主な製品"] = ec.guess_products(all_text) or rec["サイト説明"]
    return rec


def crawl_one(f: Fetcher, row: dict) -> dict:
    top = row["HP起点"]
    rec = blank_record(row["社名"], top)

    status, body, final = f.get(top)
    if status != 200 or not body:
        rec["備考"] = REASON.get(status, f"HTTP {status}")
        return rec

    pages = [(final, body)]
    for u in pick_company_pages(final, body, C.MAKER_MAX_PAGES_PER_COMPANY - 1):
        st, b, fin = f.get(u)
        if st == 200 and b:
            pages.append((fin, b))
    return extract_from_pages(rec, pages)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="この件数だけ処理する（0=全件）")
    args = ap.parse_args()

    os.makedirs(C.WORK_DIR, exist_ok=True)
    # 済みの社は飛ばす（1社ごとに JSONL へ確定させているので、中断しても無駄にならない）。
    done: set[str] = set()
    for f in glob.glob(os.path.join(C.WORK_DIR, "maker_pages*.jsonl")):
        for line in open(f, encoding="utf-8"):
            try:
                done.add(json.loads(line)["社名"])
            except Exception:
                pass

    targets = [t for t in load_targets() if t["社名"] not in done]
    if args.limit:
        targets = targets[: args.limit]
    out_path = OUT
    print(f"対象 {len(targets)}社（済み {len(done)}社はスキップ）/ "
          f"間隔 {C.MAKER_MIN_INTERVAL}s / 1社最大 {C.MAKER_MAX_PAGES_PER_COMPANY}ページ")
    if not C.in_daytime():
        print("！時間帯の制限に掛かっています（config.DAYTIME_*）。中止します。")
        return 1

    f = Fetcher(C.MAKER_MIN_INTERVAL)
    ok = 0
    with open(out_path, "a", encoding="utf-8") as fh:
        for i, row in enumerate(targets, 1):
            rec = crawl_one(f, row)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()           # 1社ごとに確定させる（中断しても残す）
            ok += bool(rec["電話番号"])
            if i % 20 == 0 or i == len(targets):
                print(f"  {i}/{len(targets)}  TEL取得 {ok}  リクエスト {f.count}", flush=True)
            if f.quota.left() <= 0:
                print("1日のリクエスト上限に到達。ここで止めます。明日もう一度同じコマンドで続きから。")
                break
            if not C.in_daytime():
                print("21時を過ぎたので止めます。翌日9時以降に同じコマンドで続きから。")
                break
    if f.blocked:
        bl = os.path.join(C.WORK_DIR, "blocked_hosts.json")
        prev = json.load(open(bl, encoding="utf-8")) if os.path.exists(bl) else {}
        prev.update(f.blocked)
        json.dump(prev, open(bl, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"打ち切ったホスト {len(f.blocked)}件 → {bl}（ハルオが読むまで再開しない）")
    print(f"完了: {ok}社で電話番号を取得 / 本日のリクエスト {f.quota.used} → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
