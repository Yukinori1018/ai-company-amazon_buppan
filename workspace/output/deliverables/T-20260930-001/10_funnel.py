"""段1の漏斗：Finder に条件を1本ずつ足して totalResults を記録する（T-20260930-001）。

目的は2つ。
1. **条件ごとの残件数**（社長に見せる漏斗）
2. **フィールドが本当に効いているかの確認**（Keepa Finder は未知のフィールドを黙って無視する。
   件数が動かなければ、そのフィールドは効いていない＝memory knowledge_keepa_product_finder_fields）

1ステップ = perPage 50 = 約11 token。結果は raw/ にキャッシュされ、再実行は0 token。

    python3 10_funnel.py            # 実行（キャッシュがあれば0 token）
    python3 10_funnel.py --offline  # キャッシュだけで表示
"""
from __future__ import annotations

import json
import sys

import keepa_io
from maker_rules import EXCLUDE_ROOTS

# (ラベル, 足すフィールド)。上から順に累積で足す。
STEPS: list[tuple[str, dict]] = [
    ("0 母集団（通常商品・アダルト除外）", {"productType": [0], "isAdultProduct": False}),
    ("7 本/CD/DVD/ソフト/ゲーム/デジタル等のルート除外", {"categories_exclude": EXCLUDE_ROOTS}),
    ("1 monthlySold ≥ 50", {"monthlySold_gte": 50}),
    ("4 大カテゴリーランク ≤ 50,000", {"current_SALES_gte": 1, "current_SALES_lte": 50000}),
    ("3 FBA出品者 ≥ 2", {"offerCountFBA_gte": 2}),
    ("5a カートが FBA", {"buyBoxIsFBA": True}),
    ("5b カートが資格なしでない", {"buyBoxIsUnqualified": False}),
    ("6 売価（新品最安）≥ 2,200円", {"current_NEW_gte": 2200}),
    ("2a カートが今 Amazon でない", {"buyBoxIsAmazon": False}),
    ("2b 365日で Amazon のカート保持率 ≤ 10%（本体365日在庫切れ≥90%の必要条件・前段）",
     {"buyBoxStatsAmazon365_lte": 10}),
]


def selection_upto(n: int) -> dict:
    sel: dict = {}
    for _, add in STEPS[: n + 1]:
        sel.update(add)
    return sel


def run(offline: bool = False) -> list[dict]:
    rows = []
    for i, (label, _) in enumerate(STEPS):
        sel = {**selection_upto(i), "perPage": 50, "page": 0}
        d = keepa_io.finder(sel, f"funnel{i:02d}", offline=offline)
        rows.append({"step": label, "total": d.get("totalResults"), "tokens": d.get("tokensConsumed")})
        print(f"{label:70} {d.get('totalResults'):>12,}  (token {d.get('tokensConsumed')})", flush=True)
    return rows


# 効きの確認用：Boolean の逆側で件数が出るか（False 側で動かなくても、True 側で動けば効いている）
CHECKS: list[tuple[str, dict]] = [
    ("check buyBoxIsUnqualified=True", {"buyBoxIsUnqualified": True}),
    ("check ゲーム(637394)だけ", {"rootCategory": [637394]}),
]


def checks(offline: bool = False) -> None:
    base = {**selection_upto(4), "perPage": 50, "page": 0}  # 段3まで（FBA≥2）の母集団
    for label, add in CHECKS:
        sel = {**base, **add}
        if "rootCategory" in add:
            sel.pop("categories_exclude", None)
        d = keepa_io.finder(sel, "check", offline=offline)
        print(f"{label:70} {d.get('totalResults'):>12,}")


if __name__ == "__main__":
    off = "--offline" in sys.argv
    rows = run(off)
    checks(off)
    (keepa_io.RAW.parent / "funnel.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
