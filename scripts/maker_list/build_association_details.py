"""(a-2) 一覧に社名しか無い2団体の、各社の詳細ページを取る。

  NAPAC（161社）  /cms/ja/members/10-jp/member-list/<id>-<slug>
  日本金属ハウスウェア工業組合＝燕（67社）  /company/<id>/

法的な条件（05_リスト拡充の法務判定 §2-1 / §2-4）:
  - NAPAC は**明示の不許諾宣言**がある（/cms/ja/copyright）。判定は「条件付きOK（最狭）」。
    → 抽出は **社名・所在地・電話番号・FAX番号・自社HP の5項目のみ**。
      紹介文などの**本文は1文字も保存しない**。詳細ページは**1社1回・再訪しない**。
      抽出結果の**再公開は一切不可**（PUBLIC リポに出さない）。
  - 燕は共通条件のみ。詳細67ページも同条件。
  - 同一ホスト3.0秒以上・09〜21時・robots.txt 尊重・業界団体分は1日400リクエストまで。
  - 403 / 429 / 5xx が1回でも出たら、そのホストは即時・永久に打ち切る。

    python3 scripts/maker_list/build_association_details.py
    python3 scripts/maker_list/build_association_details.py --only napac --limit 5
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maker_list import config as C
from maker_list.extract import phone
from maker_list.extract.htmlutil import clean_url, flat_text, links, text_lines
from maker_list.fetcher import REASON, Fetcher
from maker_list.parsers import associations as A

LIST_HTML = {"napac": "napac.html", "houseware": "houseware.html"}
LINK_PATTERN = {
    "napac": r"member-list/\d+",
    "houseware": r"/company/\d+",
}


def detail_links(aid: str) -> list[tuple[str, str]]:
    """一覧ページ（保存済みHTML）から (詳細URL, 社名) を拾う。"""
    base = A.ASSOCIATIONS[aid][1]
    raw = open(os.path.join(C.SOURCES_HTML, LIST_HTML[aid]),
               encoding="utf-8", errors="ignore").read()
    out, seen = [], set()
    for href, inner in re.findall(
            r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S | re.I):
        if not re.search(LINK_PATTERN[aid], href):
            continue
        url = urljoin(base, _html.unescape(href))
        name = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", inner))).strip()
        if url in seen or not name:
            continue
        seen.add(url)
        out.append((url, name))
    return out


def parse_detail(aid: str, url: str, raw: str, name: str) -> dict:
    """詳細ページから5項目だけ取る。**本文は保存しない**（NAPAC 条件）。"""
    rec = {"社名": name, "電話番号": "", "FAX番号": "", "自社HP": "",
           "取扱品目": "", "所在地": "", "会員種別": "",
           "出典URL": url, "取得日": C.today(), "取得時刻": C.fetched_at()}
    text = flat_text(raw)

    tel, _kind, fax = phone.pick_tel_and_fax(text)
    rec["電話番号"], rec["FAX番号"] = tel or "", fax or ""

    m = re.search(r"〒?\s*\d{3}-?\d{4}[^\n]{4,60}", text)
    if m:
        rec["所在地"] = m.group(0).strip()[:60]

    host = url.split("/")[2]
    for u, _label in links(raw, url):
        if u.startswith("http") and host.split(".")[-2] not in u:
            if not any(s in u for s in ("facebook", "twitter", "instagram", "youtube",
                                        "google", "line.me", "x.com")):
                rec["自社HP"] = clean_url(u)
                break

    # 燕は「主な業務内容 / 主な製品」という定型の項目があり、これは事実データなので取る。
    # NAPAC は §2-1 の条件で本文を取らないため、品目は空のまま。
    if aid == "houseware":
        for key in ("主な製品", "主な業務内容"):
            m = re.search(re.escape(key) + r"[\s:：]*([^\n]{2,60})", text)
            if m:
                rec["取扱品目"] = m.group(1).strip()
                break
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(LIST_HTML), help="この団体だけ")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not C.in_daytime():
        print("！取得してよい時間帯は 09:00〜21:00 JST です（05 §2-4）。中止します。")
        return 1

    f = Fetcher(C.ASSOCIATION_MIN_INTERVAL,
                daily_limit=C.ASSOCIATION_DAILY_LIMIT, quota_name="association")
    for aid in ([args.only] if args.only else list(LIST_HTML)):
        name, base, cat, _files = A.ASSOCIATIONS[aid]
        rule = C.ASSOCIATION_RULES[aid]
        # 一覧から作った assoc_<aid>.jsonl は上書きしない。詳細は別ファイルに出し、
        # merge 側で「後から読んだ方が勝つ」ことで詳細が優先される。
        out_path = os.path.join(C.WORK_DIR, f"assoc_{aid}_detail.jsonl")
        # 既に詳細を取った社は再訪しない（NAPAC の「1社1回」条件）
        done = {}
        if os.path.exists(out_path):
            for line in open(out_path, encoding="utf-8"):
                r = json.loads(line)
                done[r["社名"]] = r

        targets = detail_links(aid)
        if args.limit:
            targets = targets[: args.limit]
        print(f"[{aid}] {name} / 判定={rule['judgment']} / 詳細 {len(targets)}件 "
              f"/ 間隔 {C.ASSOCIATION_MIN_INTERVAL}s / 本日の団体枠の残り {f.quota.left()}")

        rows = dict(done)
        got = 0
        for i, (url, cname) in enumerate(targets, 1):
            prev = done.get(cname)
            if prev and prev.get("出典URL", "").startswith("http") and prev.get("電話番号"):
                continue                      # 取得済み。再訪しない
            status, body, _ = f.get(url)
            if status != 200 or not body:
                reason = REASON.get(status, f"HTTP {status}")
                print(f"  {cname}: {reason}")
                if status in (-2, -3, -5):     # 上限・時間帯・打ち切り → 以降も無駄
                    break
                continue
            rec = parse_detail(aid, url, body, cname)
            rec.update({"カテゴリ": cat, "名簿": name, "名簿URL": base,
                        "会員種別": (prev or {}).get("会員種別", ""),
                        "取得元": f"業界団体名簿の会社詳細ページ（{name}）"})
            from maker_list.build_associations import origin
            rec["HP起点"] = origin(rec["自社HP"])
            rows[cname] = rec
            got += bool(rec["電話番号"])
            if i % 20 == 0:
                print(f"  {i}/{len(targets)} TEL {got} / リクエスト {f.quota.used}", flush=True)
            # 1社ごとに書き切る（中断しても部分成果が残る）
            with open(out_path, "w", encoding="utf-8") as fh:
                for r in rows.values():
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{aid}] 電話番号 {sum(1 for r in rows.values() if r.get('電話番号'))}"
              f" / HP {sum(1 for r in rows.values() if r.get('自社HP'))} / {len(rows)}社")

    if f.blocked:
        bl = os.path.join(C.WORK_DIR, "blocked_hosts.json")
        prev = json.load(open(bl, encoding="utf-8")) if os.path.exists(bl) else {}
        prev.update(f.blocked)
        json.dump(prev, open(bl, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"打ち切ったホスト {len(f.blocked)}件 → {bl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
