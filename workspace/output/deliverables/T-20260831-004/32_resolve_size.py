"""連絡候補メーカーに gBizINFO の規模情報を付ける（T-20260831-004 / タカシ）.

    python3 32_resolve_size.py [--input 10_連絡候補メーカー.csv] [--limit N]

やること:
  1. メーカー名（Amazon のブランド表記）から法人番号を特定する
  2. 従業員数・所在地・事業概要を取る
  3. 社長確定の「従業員300人以下」で絞る
  4. **落ちた会社も、引けなかった会社も、理由コード付きで台帳に残す**

やらないこと（意図的に）:
  * 同名企業が複数ヒットしたときに1社へ推測で決めること
    → `U2_候補複数_特定保留` として保留し、候補を全部書き出す
  * 法人番号や従業員数が取れなかった会社を落とすこと
    → gBizINFO は小規模事業者ほど欠測する。落とすと社長が最も取引しやすい
      相手を優先的に捨てることになる（タケシの §6 と同じ判断）
  * 推測で欄を埋めること → 取れなければ空欄

出力は行データを含むため **Git 追跡外**（社長判断 P2: PUBLIC リポに載せない）。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gb = _load("gbizinfo", "30_gbizinfo.py")
nm = _load("name_match", "31_name_match.py")

#: 社長確定のしきい値。中小企業基本法（製造業）の従業員基準と同じ。
EMPLOYEE_MAX = 300

#: 資本金の上限（円）。中小企業基本法（製造業）の資本金基準。
#: **併用する理由は実測にある。** 従業員数だけでは上場企業を落とせなかった：
#:   株式会社ブシロード  従業員 259人 / 資本金 57.8億円（東証上場）
#:   Ｈａｍｅｅ株式会社    従業員 176人 / 資本金  6.3億円（東証プライム）
#: どちらも「従業員300人以下」を通過する。資本金を見て初めて落ちる。
#: 法律上の中小企業者は「資本金 OR 従業員」のどちらかを満たせば該当だが、
#: 本件の目的は「個人事業主の初回小ロットを受けてくれる相手か」なので
#: **AND（両方満たすものだけ中小）** で判定する。
CAPITAL_MAX = 300_000_000

#: 資本金は gBizINFO 側でほとんど欠測する（実測: 12社中2社）。しかも
#: 取れた2社が両方とも上場企業だった。＝**欠測は「小さい」の証拠にならず、
#: 取得できたときだけ落とす方向に使う**。中小判定の必須条件にはしない。

REASONS = {
    "M1": "中小（従業員300人以下・資本金3億円以下の両方を確認）",
    "M2": "中小（従業員300人以下。資本金は gBizINFO に未登録）",
    "M3": "中小（資本金3億円以下。従業員数は gBizINFO に未登録）",
    "L1": "除外：従業員301人以上",
    "L2": "除外：資本金3億円超（従業員数は300人以下だが大企業）",
    "U1": "保留：法人は特定できたが従業員数も資本金も未登録",
    "U2": "保留：同名の現存法人が複数あり1社に決められない",
    "U3": "保留：商号が完全一致する現存法人を特定できず",
}

#: 残す理由コード。落とすのは L1 / L2 だけ。
KEEP_CODES = ["M1", "M2", "M3", "U1", "U2", "U3"]

OUT_COLS = [
    "規模判定", "理由コード", "理由",
    "従業員数", "資本金", "法人番号", "gBiz商号", "代表者名",
    "所在地", "郵便番号", "事業概要", "企業URL", "設立年月日",
    "照合の注意", "候補件数", "候補一覧", "照合に使ったクエリ", "検索打ち切り",
]


def judge(emp, cap) -> str:
    """従業員数・資本金から理由コードを決める。取れない値は None で渡す。"""
    if emp is not None and emp > EMPLOYEE_MAX:
        return "L1"
    if cap is not None and cap > CAPITAL_MAX:
        return "L2"
    if emp is not None and cap is not None:
        return "M1"
    if emp is not None:
        return "M2"
    if cap is not None:
        return "M3"
    return "U1"


def resolve(client, raw_name: str) -> dict:
    """1社ぶんの照合。ネットワークアクセスはここだけ。"""
    rec = {c: "" for c in OUT_COLS}
    variants = nm.query_variants(raw_name)
    truncated = False

    for q in variants:
        hits = client.search_by_name(q)
        if len(hits) >= gb.SEARCH_LIMIT:
            truncated = True
        exact = nm.pick_exact(hits, q)
        if not exact:
            continue

        rec["照合に使ったクエリ"] = q
        rec["候補件数"] = len(exact)
        if len(exact) > 1:
            rec["規模判定"] = "保留"
            rec["理由コード"] = "U2"
            rec["候補一覧"] = " / ".join(
                f"{c['name']}({c['corporate_number']}・{c.get('location','')[:12]})"
                for c in exact[:8]
            )
            break

        detail = client.fetch_by_number(exact[0]["corporate_number"]) or exact[0]
        rec["法人番号"] = detail.get("corporate_number", "")
        rec["gBiz商号"] = detail.get("name", "")
        rec["代表者名"] = detail.get("representative_name", "") or ""
        rec["所在地"] = detail.get("location", "")
        rec["郵便番号"] = detail.get("postal_code", "")
        rec["事業概要"] = detail.get("business_summary", "") or ""
        rec["企業URL"] = detail.get("company_url", "") or ""
        # gBizINFO は持っていれば返す。実測では大半が欠測。推測で埋めない。
        rec["設立年月日"] = detail.get("date_of_establishment", "") or ""

        emp = detail.get("employee_number")
        cap = detail.get("capital_stock")
        rec["従業員数"] = "" if emp is None else emp
        rec["資本金"] = "" if cap is None else cap
        code = judge(emp, cap)
        rec["理由コード"] = code
        rec["規模判定"] = {"M": "中小", "L": "大企業", "U": "保留"}[code[0]]
        break
    else:
        rec["規模判定"] = "保留"
        rec["理由コード"] = "U3"
        rec["照合に使ったクエリ"] = " | ".join(variants)

    rec["理由"] = REASONS[rec["理由コード"]]
    rec["検索打ち切り"] = "あり" if truncated else ""
    # 3文字以下の商号は偶然の一致がありうる（"CIO" → ＣＩＯ株式会社 が本当に
    # そのブランドの会社かは名前だけでは決まらない）。目視の対象として印を付ける。
    if rec["法人番号"] and len(nm.match_key(rec["照合に使ったクエリ"])) <= 3:
        rec["照合の注意"] = "商号が短く偶然一致の可能性あり（要目視）"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="10_連絡候補メーカー.csv")
    ap.add_argument("--out-prefix", default="33")
    ap.add_argument("--limit", type=int, default=0, help="先頭N社だけ（動作確認用）")
    args = ap.parse_args()

    src = HERE / args.input
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    if args.limit:
        rows = rows[: args.limit]

    cache_dir = (
        HERE.parents[1] / "agent_output" / "T-20260831-004" / "gbiz_cache"
    )
    client = gb.GBizInfo(cache_dir)

    enriched = []
    for i, r in enumerate(rows, 1):
        rec = resolve(client, r["メーカー"])
        enriched.append({**r, **rec})
        if i % 20 == 0:
            client.flush()
            print(
                f"  {i}/{len(rows)}  live_calls={client.live_calls}",
                file=sys.stderr, flush=True,
            )
    client.flush()

    src_cols = list(rows[0].keys())
    cols = ["メーカー"] + OUT_COLS + [c for c in src_cols if c != "メーカー"]

    def write(path: Path, data: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    # 残すのは中小3種 + 保留3種。落とすのは L1 / L2（大企業）だけ。
    order = {c: i for i, c in enumerate(KEEP_CODES)}
    keep = sorted(
        (e for e in enriched if e["理由コード"] in order),
        key=lambda e: (order[e["理由コード"]], -int(e["該当商品数"] or 0)),
    )
    dropped = [e for e in enriched if e["理由コード"] in ("L1", "L2")]

    p = args.out_prefix
    write(HERE / f"{p}_連絡候補_規模判定済み.csv", keep)
    write(HERE / f"{p}b_除外_大企業.csv", dropped)
    write(HERE / f"{p}c_規模判定_全件台帳.csv", enriched)

    c = Counter(e["理由コード"] for e in enriched)
    emps = sorted(int(e["従業員数"]) for e in enriched if e["従業員数"] != "")
    identified = c["M1"] + c["M2"] + c["M3"] + c["L1"] + c["L2"] + c["U1"]
    confirmed_small = c["M1"] + c["M2"] + c["M3"]
    stats = {
        "入力": src.name,
        "段階別内訳": {
            "1_入力社数": len(rows),
            "2_法人番号を特定できた": identified,
            "3a_従業員数を取得できた": c["M1"] + c["M2"] + c["L1"] + c["L2"],
            "3b_資本金を取得できた": c["M1"] + c["M3"] + c["L2"]
            + sum(1 for e in enriched if e["理由コード"] == "L1" and e["資本金"] != ""),
            "4_中小と確認できた": confirmed_small,
            "5_大企業として除外": c["L1"] + c["L2"],
            "6_保留（落とさない）": c["U1"] + c["U2"] + c["U3"],
        },
        "理由コード別": {k: c[k] for k in ["M1", "M2", "M3", "L1", "L2", "U1", "U2", "U3"]},
        "最終リスト社数（保留を残す＝推奨）": len(keep),
        "最終リスト社数（保留を落とす）": confirmed_small,
        "保留を落とした場合に失う社数": len(keep) - confirmed_small,
        "従業員数の中央値": emps[len(emps) // 2] if emps else None,
        "従業員数の分布": {
            "1-20人": sum(1 for x in emps if x <= 20),
            "21-50人": sum(1 for x in emps if 20 < x <= 50),
            "51-100人": sum(1 for x in emps if 50 < x <= 100),
            "101-300人": sum(1 for x in emps if 100 < x <= 300),
            "301人以上": sum(1 for x in emps if x > 300),
        },
        "設立年月日を取得できた社数": sum(
            1 for e in enriched if e["設立年月日"] != ""
        ),
        "短名一致で要目視": sum(1 for e in enriched if e["照合の注意"]),
        "検索が100件で打ち切られた社数": sum(
            1 for e in enriched if e["検索打ち切り"]
        ),
        "gBizINFOへの実アクセス回数": client.live_calls,
        "理由コード定義": REASONS,
    }
    (HERE / f"{p}d_集計_規模判定.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
