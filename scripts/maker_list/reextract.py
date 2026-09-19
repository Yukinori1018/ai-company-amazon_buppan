"""キャッシュ済みHTMLから maker_pages.jsonl を作り直す。**ネットには出ない。**

抽出ロジック（phone.py / ec.py）を直したあと、取得済みの社に新しいロジックを
当て直すためのもの。リクエストを1本も増やさずに全件を作り直せる。

    python3 scripts/maker_list/reextract.py

元ファイルは maker_pages.jsonl.bak に退避する。
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maker_list import config as C
from maker_list.crawl_maker_sites import OUT, blank_record, extract_from_pages
from maker_list.fetcher import Fetcher


def main() -> int:
    f = Fetcher(C.MAKER_MIN_INTERVAL)
    records: list[dict] = []
    for path in sorted(glob.glob(os.path.join(C.WORK_DIR, "maker_pages*.jsonl"))):
        if path.endswith(".bak"):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # 同じ社が複数回出てきたら、ページを多く見た方を残す
    best: dict[str, dict] = {}
    for r in records:
        cur = best.get(r["社名"])
        if not cur or len(r.get("見たページ", [])) > len(cur.get("見たページ", [])):
            best[r["社名"]] = r

    out, hit, miss = [], 0, 0
    for name, old in best.items():
        rec = blank_record(name, old.get("HP起点", ""))
        rec["取得日"] = old.get("取得日", rec["取得日"])
        rec["取得時刻"] = old.get("取得時刻", rec.get("取得時刻", ""))
        pages = []
        for u in old.get("見たページ", []):
            p = f._path(u)
            if os.path.exists(p):
                pages.append((u, open(p, encoding="utf-8", errors="ignore").read()))
        if pages:
            rec = extract_from_pages(rec, pages)
            hit += 1
        else:
            rec["備考"] = old.get("備考", "") or "キャッシュなし"
            miss += 1
        out.append(rec)

    if os.path.exists(OUT):
        shutil.copy(OUT, OUT + ".bak")
    for extra in glob.glob(os.path.join(C.WORK_DIR, "maker_pages_s*.jsonl")):
        os.rename(extra, extra + ".merged")
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{len(out)}社を作り直しました（キャッシュあり {hit} / なし {miss}）→ {OUT}")
    print(f"  電話番号 {sum(1 for r in out if r['電話番号'])} / "
          f"EC信号 {sum(1 for r in out if r['自社EC'] != '未確認')} / "
          f"モール {sum(1 for r in out if r['モール'] != '未確認')} / "
          f"何を作っているか {sum(1 for r in out if r['主な製品'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
