#!/usr/bin/env python3
"""秘書がブラウザで順に開く「SD 検索 URL の一覧（優先順）」を作る。**SD には1回もつながない。**

    python3 sd_lookup_list.py            # → agent_output/T-20261012-001/sd_lookup_by_partno.csv
    python3 sd_lookup_list.py --count    # 取りこぼしの規模を数えるだけ（ファイルは書かない）

各行に3本の URL を付ける：JAN で引く／メーカー品番で引く／名前（ブランド＋種類＋キャラ名）で引く。
JAN で0件だったら品番、品番で0件だったら名前、の順に開く（`sd_query_plan.py`）。
品番・名前で当たったら、商品ページの**内訳（S1〜Sn）のメーカー品番**が Amazon 側と一致するかを見る。

並び順（上から開く）
1. サンリオ照会リストの P1 → P2（T-20261012-001・社長案件）
2. **過去に JAN で引いて0件だった行**（10/01・10/09 のレーンA）＝取りこぼしの本命
3. サンリオ照会リストの P3 → P4
4. 10/12 の SD 照会キュー（`sd_queue_20261012.csv`）
5. 10/11 の SD 照会キュー（小・大）。大は元の順位どおり

🔴 出力には卸値の上限・URL が入るので **agent_output にだけ**書く（PUBLIC リポに置かない）。
🔴 上限で行を切らない（CLAUDE.md §3.3-34）。開く順番を決めるだけ。
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sd_query_plan as qp  # noqa: E402

REPO = HERE.parents[4]
AO = REPO / "workspace/output/agent_output"
T3 = AO / "T-20260920-003"
SANRIO = AO / "T-20261012-001/sanrio_sd_lookup_list_private.csv"
OUT = AO / "T-20261012-001/sd_lookup_by_partno.csv"
LANE_A = [  # (JAN リスト, 結果) ── JAN 照会の記録はこの2回分しか残っていない
    (T3 / "sd/laneA_jans_20261001.txt", T3 / "sd/laneA_jan_hits.jsonl", "2026-10-01"),
    (T3 / "sd_buylist20261009/laneA_jans_20261009.txt",
     T3 / "sd_buylist20261009/laneA_hits_20261009.jsonl", "2026-10-09"),
]
QUEUES = [
    ("10/12 SD照会キュー", T3 / "sd_buylist20261009/sd_queue_20261012.csv"),
    ("10/11 SD照会キュー(小)", T3 / "sd_lookup_queue_20261011.csv"),
    ("10/11 SD照会キュー(大)", T3 / "sd_lookup_queue_big_20261011.csv"),
]
KEEPA = T3 / "sd_queue_big/best.pkl"   # ASIN → title/brand/model（Keepa キャッシュ）

COLS = ["優先順", "群", "元の順位", "ASIN", "JAN", "商品名", "ブランド",
        "メーカー品番", "品番の出所", "過去のJAN照会",
        "① JANで引くURL", "② 品番で引くURL", "③ 名前の検索語", "③ 名前で引くURL",
        "③' 名前の検索語(広め)", "③' 名前で引くURL(広め)",
        "Amazon URL", "売価90日中央値", "B等級の卸上限", "A等級の卸上限", "上限の税区分",
        # ↓ 秘書が画面で見て埋める欄
        "当たった段", "SD品番", "内訳の品番が一致", "卸1点(税抜)", "在庫", "確認者", "確認時刻", "メモ"]


def _jans(cell: str) -> list[str]:
    return [j for j in (re.sub(r"\D", "", x) for x in re.split(r"[;／/\s,]+", cell or ""))
            if 8 <= len(j) <= 13]


def lane_a_results() -> dict[str, dict]:
    """過去の JAN 照会。{jan: {date, hit_count, asin}}"""
    out: dict[str, dict] = {}
    for jans, hits, day in LANE_A:
        asin = {}
        for line in open(jans, encoding="utf-8"):
            m = re.match(r"\s*(\d{8,13})\s*#\s*(B0[0-9A-Z]{8})?", line)
            if m:
                asin[m.group(1)] = m.group(2) or ""
        for line in open(hits, encoding="utf-8"):
            r = json.loads(line)
            out[r["jan"]] = {"date": day, "hit_count": r["hit_count"], "asin": asin.get(r["jan"], "")}
    return out


def build(keepa: dict) -> list[dict]:
    lane = lane_a_results()
    by_asin = keepa
    rows: list[dict] = []

    def add(group: str, rank: str, asin: str, jan: str, title: str, brand: str,
            sell="", b="", a="", tax=""):
        k = by_asin.get(asin, {}) if asin else {}
        title = title or k.get("title", "")
        brand = brand or k.get("brand", "")
        model = k.get("model") or ""
        parts = qp.part_numbers(title, model)
        from_model = qp.part_numbers("", model)
        src = ("Keepa の model" if parts[0] in from_model else "商品名") if parts else ""
        names = qp.name_queries(title, brand, model)
        past = lane.get(jan)
        rows.append({
            "群": group, "元の順位": rank, "ASIN": asin, "JAN": jan, "商品名": title, "ブランド": brand,
            "メーカー品番": " / ".join(parts), "品番の出所": src,
            "過去のJAN照会": (f"{past['date']} {past['hit_count']}件" if past else "未照会"),
            "① JANで引くURL": qp.search_url(jan) if jan else "",
            "② 品番で引くURL": qp.search_url(parts[0]) if parts else "",
            "③ 名前の検索語": names[0] if names else "",
            "③ 名前で引くURL": qp.search_url(names[0]) if names else "",
            "③' 名前の検索語(広め)": names[1] if len(names) > 1 else "",
            "③' 名前で引くURL(広め)": qp.search_url(names[1]) if len(names) > 1 else "",
            "Amazon URL": f"https://www.amazon.co.jp/dp/{asin}" if asin else "",
            "売価90日中央値": sell, "B等級の卸上限": b, "A等級の卸上限": a, "上限の税区分": tax,
        })

    sanrio = list(csv.DictReader(open(SANRIO, encoding="utf-8-sig")))

    def add_sanrio(levels):
        for r in sanrio:
            if r["照会の優先度"][:2] in levels:
                for j in _jans(r["JAN"]):
                    add(f"サンリオ{r['照会の優先度'][:2]}", r["順位"], r["ASIN"], j, r["商品名"],
                        r["ブランド"], r["売価90日中央値"], r["B卸上限_税込"], r["A卸上限_税込"], "税込")

    add_sanrio(("P1",))
    add_sanrio(("P2",))
    for jan, p in lane.items():
        if p["hit_count"] == 0:
            add(f"JANで0件({p['date']})", "", p["asin"], jan, "", "")
    add_sanrio(("P3", "P4"))
    for group, path in QUEUES:
        for r in csv.DictReader(open(path, encoding="utf-8-sig")):
            for j in _jans(r.get("JAN", "")):
                add(group, r.get("順位", ""), r.get("ASIN", ""), j, r.get("商品名", ""),
                    r.get("ブランド", ""), r.get("売価90日中央値", ""),
                    r.get("B等級に必要な卸1点上限(税抜)") or r.get("B等級の卸1点上限(税抜)", ""),
                    r.get("A等級に必要な卸1点上限(税抜)") or r.get("A等級の卸1点上限(税抜)", ""),
                    "税抜")

    seen: set[str] = set()
    uniq = []
    for r in rows:
        if r["JAN"] in seen:
            continue
        seen.add(r["JAN"])
        r["優先順"] = len(uniq) + 1
        uniq.append(r)
    return uniq


def count(rows: list[dict]) -> None:
    lane = lane_a_results()
    zero = [j for j, p in lane.items() if p["hit_count"] == 0]
    byj = {r["JAN"]: r for r in rows}
    zp = [j for j in zero if byj.get(j, {}).get("メーカー品番")]
    print(f"記録の残っている JAN 照会: {len(lane)} JAN（10/01・10/09 のレーンA）")
    print(f"  うち0件: {len(zero)} JAN ／ そのうち品番で引き直せる: {len(zp)} JAN")
    for j in zero:
        r = byj.get(j, {})
        print(f"    {j} {r.get('ASIN','')} 品番={r.get('メーカー品番') or '-'}  {r.get('商品名','')[:40]}")
    total = len(rows)
    withp = sum(1 for r in rows if r["メーカー品番"])
    print(f"一覧の全行: {total} JAN ／ 品番が取れる行: {withp}（{withp/total:.1%}）")
    for g in dict.fromkeys(r["群"] for r in rows):
        rs = [r for r in rows if r["群"] == g]
        print(f"  {g}: {len(rs)} 行・品番あり {sum(1 for r in rs if r['メーカー品番'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true", help="数えるだけ（書かない）")
    args = ap.parse_args(argv)
    keepa = pickle.load(open(KEEPA, "rb")) if KEEPA.exists() else {}
    rows = build(keepa)
    count(rows)
    if not args.count:
        with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"→ {OUT}（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
