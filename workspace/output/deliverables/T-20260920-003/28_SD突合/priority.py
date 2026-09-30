#!/usr/bin/env python3
"""取引企業 2,176社に「どのジャンルを持つか」を貼り、スキャンの優先順を出す。

材料は `/p/do/psl/<genre_id>/?pg=<n>`（25社/ページ・**サーバー描画なので curl で取れる**）。
出力:
  - `sd_dealer_priority.csv` … dealer_id, name, priority, genres
  - `sd_dealer_order.txt`    … dealer_id を優先順に1行1件（sd_dealer_index.py --order に渡す）

優先順（2026-09-30 カズヨ指示）
  1 … 丸進(102452) と 和平フレイズ(21321)。取引実績・承認あり
  2 … 生活雑貨／家具・インテリア／電化製品／什器・店舗資材
  3 … 食品・菓子・飲料・酒／本
  4 … ジャンル不明（どの一覧にも出てこなかった社）
  5 … ファッションのみ。**後回し**（2026-09-30 に検証したバッグ4件はいずれも実売ゼロ）
"""
from __future__ import annotations
import argparse, csv, json, os

FIRST = ["102452", "21321"]
TIER2 = {"5134", "5012", "1399", "1409"}
TIER3 = {"2900", "6022"}
FASHION = "1052"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dealers", required=True, help="dealer_id<TAB>name の TSV")
    ap.add_argument("--genre-progress", required=True,
                    help="ジャンル別企業一覧のスキャン結果 JSON（_progress.json）")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    names: dict[str, str] = {}
    for line in open(args.dealers, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0] not in ("dealer_id", ""):
            names[p[0].strip()] = p[1].strip()

    gp = json.load(open(args.genre_progress, encoding="utf-8"))
    by_dealer: dict[str, set[str]] = {}
    gname = {gid: v.get("name", gid) for gid, v in gp.items()}
    for gid, v in gp.items():
        for did in v.get("dealers", []):
            by_dealer.setdefault(str(did), set()).add(gid)

    rows = []
    for did, name in names.items():
        gs = by_dealer.get(did, set())
        if did in FIRST:
            pri = 1
        elif gs & TIER2:
            pri = 2
        elif gs & TIER3:
            pri = 3
        elif not gs:
            pri = 4
        elif gs == {FASHION}:
            pri = 5
        else:
            pri = 4
        rows.append({"dealer_id": did, "name": name, "priority": pri,
                     "genres": "|".join(sorted(gname.get(g, g) for g in gs))})
    rows.sort(key=lambda r: (r["priority"], r["dealer_id"]))

    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, "sd_dealer_priority.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["dealer_id", "name", "priority", "genres"])
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(args.out_dir, "sd_dealer_order.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(r["dealer_id"] for r in rows) + "\n")

    from collections import Counter
    c = Counter(r["priority"] for r in rows)
    print(f"{len(rows)}社 → " + " / ".join(f"優先{k}:{c[k]}社" for k in sorted(c)))
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
