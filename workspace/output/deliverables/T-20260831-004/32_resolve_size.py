"""連絡候補メーカーに gBizINFO の規模情報を付ける（T-20260831-004 / タカシ）.

    python3 32_resolve_size.py [--input 10_連絡候補メーカー.csv] [--limit N]

やること:
  1. メーカー名（Amazon のブランド表記）から法人番号を特定する
  2. 従業員数・資本金・所在地・事業概要を取る
  3. 規模を**列として付与し、並べ替えと目印に使う**
  4. **どの会社も落とさない。** 262社は262社のまま出す

やらないこと（意図的に）:
  * **規模で足切りすること**
    社長の訂正（2026-08-31）:
      「従業員300人以下はあくまで目安（私の感想）です。参考数字としていいですが、
        絶対的な数字としないでください。仕入れサイトからだともしかしたら
        大企業でも仕入れられるかもしれません。」
    → 規模は「**直接交渉での通りやすさの目安**」であって「仕入れ可能性そのもの」
      ではない。卸サイト（NETSEA 等）経由なら大企業からでも仕入れられうる。
      **経路が変われば答えが変わるので、経路を決める前に落としてはいけない。**
  * 同名企業が複数ヒットしたときに1社へ推測で決めること
    → `U2` として保留し、候補を全部書き出す
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

#: 社長の**目安**。中小企業基本法（製造業）の従業員基準と同じ数字。
#: 足切りには使わない（社長の訂正・2026-08-31）。区分の境界としてだけ使う。
EMPLOYEE_MAX = 300

#: 区分の上側の境界。「301〜1000人」と「1000人超」を分けるためだけの線。
EMPLOYEE_MID = 1000

#: 資本金の境界（円）。中小企業基本法（製造業）の資本金基準。
#: **併用する理由は実測にある。** 従業員数だけでは上場企業に印が付かなかった：
#:   株式会社ブシロード  従業員 259人 / 資本金 57.8億円（東証上場）
#:   Ｈａｍｅｅ株式会社    従業員 176人 / 資本金  6.3億円（東証プライム）
#: どちらも「従業員300人以下」に入る。資本金を見て初めて規模の大きさが分かる。
CAPITAL_MAX = 300_000_000

#: 資本金は gBizINFO 側でほとんど欠測する（実測: 262社中6社）。しかも
#: 取れた会社が大企業に偏る。＝**欠測は「小さい」の証拠にならない。**

REASONS = {
    "M1": "中小の目安（従業員300人以下・資本金3億円以下の両方を確認）",
    "M2": "中小の目安（従業員300人以下。資本金は gBizINFO に未登録）",
    "M3": "中小の目安（資本金3億円以下。従業員数は gBizINFO に未登録）",
    "L1": "規模大の目安：従業員301人以上",
    "L2": "規模大の目安：資本金3億円超（従業員数は300人以下）",
    "U1": "規模不明：法人は特定できたが従業員数も資本金も未登録",
    "U2": "規模不明：同名の現存法人が複数あり1社に決められない",
    "U3": "規模不明：商号が完全一致する現存法人を特定できず",
}

#: 表示順。**どれも落とさない。** 中小の目安 → 規模不明 → 規模大 の順に並べる。
#: 社長が上から見るとき、直接交渉が通りやすい順になっている、というだけの意味。
CODE_ORDER = ["M1", "M2", "M3", "U1", "U2", "U3", "L2", "L1"]

#: 直接交渉の目安。**仕入れ可能性そのものではない。**
#: 卸サイト（NETSEA 等）経由なら規模が大きくても仕入れられうるので、
#: 列名にも「直接交渉の」と入れて誤読を防ぐ。
HINT_EASY = "◎ 中小の目安（直接交渉が通りやすい）"
HINT_HARD = "△ 規模が大きい（直接は不利。卸サイト経由なら可能性あり）"
HINT_NA = "— 規模を確認できず（落としていない）"

OUT_COLS = [
    "直接交渉の目安", "規模区分", "資本金区分", "理由コード", "理由",
    "従業員数", "資本金", "法人番号", "gBiz商号", "代表者名",
    "所在地", "郵便番号", "事業概要", "企業URL", "設立年月日",
    "照合の注意", "候補件数", "候補一覧",
    "参考_前方一致の未検証候補", "照合に使ったクエリ", "検索打ち切り",
]


def size_band(emp) -> str:
    """従業員数の区分。社長が自分で線を引き直せるように幅で持つ。"""
    if emp is None:
        return "不明"
    if emp <= EMPLOYEE_MAX:
        return "〜300人"
    if emp <= EMPLOYEE_MID:
        return "301〜1000人"
    return "1000人超"


def capital_band(cap) -> str:
    if cap is None:
        return "不明"
    return "3億円以下" if cap <= CAPITAL_MAX else "3億円超"

#: 前方一致ヒントを出す最小のキー長。短すぎると総当たりのノイズになる。
HINT_MIN_KEY = 3
HINT_MAX = 5


def prefix_hints(all_hits: list[dict], variants: list[str]) -> str:
    """商号が「ブランド名 + α」の会社を **参考として** 挙げる。

    `デビフ` の実体は `デビフペット株式会社` のように、ブランド名が商号の
    先頭にだけ入っている会社が実在する。完全一致では拾えない。
    ただし前方一致は同名の別会社を拾う（`ピープル` → `ピープルソフトウエア`）ので
    **判定には一切使わず、社長が目視で潰すための手がかりとしてだけ出す。**
    追加の API アクセスは発生しない（検索済みの結果を読み直すだけ）。
    """
    keys = [nm.match_key(v) for v in variants]
    keys = [k for k in keys if len(k) >= HINT_MIN_KEY]
    if not keys:
        return ""
    seen: set[str] = set()
    out: list[str] = []
    for h in all_hits:
        if h.get("status") == "閉鎖":
            continue
        hk = nm.match_key(h.get("name", ""))
        cn = h.get("corporate_number", "")
        if cn in seen or hk in keys:
            continue
        if any(hk.startswith(k) for k in keys):
            seen.add(cn)
            out.append(f"{h['name']}({cn}・{h.get('location','')[:12]})")
        if len(out) >= HINT_MAX:
            break
    return " / ".join(out)


def judge(emp, cap) -> str:
    """従業員数・資本金から理由コードを決める。取れない値は None で渡す。

    **これは足切りの判定ではなく、目印と並び順を決めるための分類。**
    """
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


def hint(code: str) -> str:
    if code.startswith("M"):
        return HINT_EASY
    if code.startswith("L"):
        return HINT_HARD
    return HINT_NA


def resolve(client, raw_name: str) -> dict:
    """1社ぶんの照合。ネットワークアクセスはここだけ。"""
    rec = {c: "" for c in OUT_COLS}
    variants = nm.query_variants(raw_name)
    truncated = False
    all_hits: list[dict] = []

    for q in variants:
        hits = client.search_by_name(q)
        all_hits.extend(hits)
        if len(hits) >= gb.SEARCH_LIMIT:
            truncated = True
        exact = nm.pick_exact(hits, q)
        if not exact:
            continue

        rec["照合に使ったクエリ"] = q
        rec["候補件数"] = len(exact)
        if len(exact) > 1:
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
        rec["理由コード"] = judge(emp, cap)
        rec["規模区分"] = size_band(emp)
        rec["資本金区分"] = capital_band(cap)
        break
    else:
        rec["理由コード"] = "U3"
        rec["照合に使ったクエリ"] = " | ".join(variants)

    rec["理由"] = REASONS[rec["理由コード"]]
    rec["直接交渉の目安"] = hint(rec["理由コード"])
    rec["規模区分"] = rec["規模区分"] or "不明"
    rec["資本金区分"] = rec["資本金区分"] or "不明"
    rec["検索打ち切り"] = "あり" if truncated else ""
    if rec["理由コード"] in ("U2", "U3"):
        rec["参考_前方一致の未検証候補"] = prefix_hints(all_hits, variants)
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

    # **落とさない。** 並べ替えるだけ。中小の目安 → 規模不明 → 規模大 の順。
    order = {c: i for i, c in enumerate(CODE_ORDER)}
    ranked = sorted(
        enriched,
        key=lambda e: (order[e["理由コード"]], -int(e["該当商品数"] or 0)),
    )
    large = [e for e in ranked if e["理由コード"].startswith("L")]

    p = args.out_prefix
    write(HERE / f"{p}_連絡候補_規模情報つき.csv", ranked)
    write(HERE / f"{p}b_規模が大きいと分かった社.csv", large)

    c = Counter(e["理由コード"] for e in enriched)
    emps = sorted(int(e["従業員数"]) for e in enriched if e["従業員数"] != "")
    identified = sum(c[k] for k in ["M1", "M2", "M3", "L1", "L2", "U1"])
    stats = {
        "入力": src.name,
        "方針": "規模は足切りに使わない（社長の訂正 2026-08-31）。列と並び順にだけ使う",
        "段階別内訳": {
            "1_入力社数": len(rows),
            "2_法人番号を特定できた": identified,
            "3a_従業員数を取得できた": sum(c[k] for k in ["M1", "M2", "L1", "L2"]),
            "3b_資本金を取得できた": sum(
                1 for e in enriched if e["資本金"] != ""
            ),
            "4_中小の目安に入った": sum(c[k] for k in ["M1", "M2", "M3"]),
            "5_規模が大きいと分かった（落としていない）": c["L1"] + c["L2"],
            "6_規模を確認できなかった": sum(c[k] for k in ["U1", "U2", "U3"]),
            "7_出力社数": len(ranked),
        },
        "理由コード別": {k: c[k] for k in CODE_ORDER},
        "規模区分別": dict(Counter(e["規模区分"] for e in enriched)),
        "資本金区分別": dict(Counter(e["資本金区分"] for e in enriched)),
        "直接交渉の目安別": dict(Counter(e["直接交渉の目安"] for e in enriched)),
        "従業員数の中央値": emps[len(emps) // 2] if emps else None,
        "従業員数の範囲": [emps[0], emps[-1]] if emps else None,
        "設立年月日を取得できた社数": sum(
            1 for e in enriched if e["設立年月日"] != ""
        ),
        "短名一致で要目視": sum(1 for e in enriched if e["照合の注意"]),
        "参考の前方一致候補が付いた社数": sum(
            1 for e in enriched if e["参考_前方一致の未検証候補"]
        ),
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
