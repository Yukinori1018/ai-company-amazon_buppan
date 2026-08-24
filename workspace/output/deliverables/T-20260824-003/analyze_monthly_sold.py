#!/usr/bin/env python3
"""Keepa `monthlySold` の値の分布を、保存済み raw JSON だけで実測する（Keepa API は叩かない＝0トークン）。

背景（T-20260824-003）
--------------------
memory `agents/it_engineer/memory/knowledge_keepa_product_finder_fields.md` に
「monthlySold は月50個以上の商品にしか出ない」という実測観察がある。これを
T-20260824-001 で確定した公式定義（"10+"/"100+" のような階級値・大半のASINで欠測・
推定値ではない・バリエーション単位）と、保存済み実データで突合するためのスクリプト。

入力
----
workspace/output/deliverables/T-20260817-005/raw/*.json.gz        （Product API のレスポンス生データ）
workspace/output/deliverables/T-20260817-005/raw_offers/*.json.gz （offers 付き取得分・参考）

出力
----
標準出力に Markdown。結果は monthly-sold-distribution.md に保存済み。

使い方
------
    python3 analyze_monthly_sold.py --repo-root "/path/to/ai-company-amazon_buppan"
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

RAW_DIRS = [
    "workspace/output/deliverables/T-20260817-005/raw",
    "workspace/output/deliverables/T-20260817-005/raw_offers",
]

# Keepa 時刻（分）→ UTC datetime。Keepa 分 = int(unixtime/60) - 21564000
KEEPA_EPOCH_OFFSET_MIN = 21_564_000


def keepa_minutes_to_dt(minutes: int) -> dt.datetime:
    return dt.datetime.utcfromtimestamp((minutes + KEEPA_EPOCH_OFFSET_MIN) * 60)


def load_products(source_dir: Path) -> dict[str, dict]:
    """gzip された Keepa レスポンス群を ASIN 単位に畳んで返す（同一 ASIN は後勝ち）。"""
    products: dict[str, dict] = {}
    for path in sorted(source_dir.glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        for product in (payload.get("products") if isinstance(payload, dict) else payload) or []:
            asin = product.get("asin")
            if asin:
                products[asin] = product
    return products


def report_current_values(label: str, products: dict[str, dict]) -> None:
    """現在値 `monthlySold` の欠測率と値の分布。"""
    total = len(products)
    # 「キーが無い」と「キーはあるが None」を区別する
    absent = sum(1 for p in products.values() if "monthlySold" not in p)
    null = sum(1 for p in products.values() if p.get("monthlySold", "x") is None)
    values = [p["monthlySold"] for p in products.values() if isinstance(p.get("monthlySold"), int)]
    positive = [v for v in values if v > 0]

    print(f"\n### {label}\n")
    print(f"- ユニーク ASIN 数: **{total}**")
    print(f"- `monthlySold` キーなし（＝欠測）: **{absent}（{absent / total:.1%}）**")
    print(f"- キーはあるが null: {null} ／ 値 0: {sum(1 for v in values if v == 0)} ／ "
          f"負値: {sorted({v for v in values if v < 0}) or 'なし'}")
    print(f"- 値を持つ ASIN: **{len(positive)}（{len(positive) / total:.1%}）**")
    if not positive:
        return
    print(f"- **最小値 {min(positive)} ／ 最大値 {max(positive)}**")
    counts = Counter(positive)
    print("\n| `monthlySold` | 件数 | 値ありのうち |")
    print("|---:|---:|---:|")
    for value, count in sorted(counts.items()):
        print(f"| {value} | {count} | {count / len(positive):.1%} |")
    print(f"\n- 出現ユニーク値: `{sorted(counts)}`")
    print(f"- 50 未満の値: **{sorted(v for v in counts if v < 50) or 'なし'}**")


def report_history(products: dict[str, dict]) -> None:
    """`monthlySoldHistory` を掘る。現在値のスナップショットだけでは見えない階級が出る。"""
    value_counts: Counter[int] = Counter()
    month_bands: dict[str, Counter[str]] = defaultdict(Counter)
    tail_pairs: Counter[tuple] = Counter()
    asins_with_small = 0
    last_small_ts: list[int] = []
    n_hist = 0

    for product in products.values():
        history = product.get("monthlySoldHistory")
        if not history:
            continue
        n_hist += 1
        # history は [keepaTime, value, keepaTime, value, ...] のフラット配列
        times, values = history[0::2], history[1::2]
        for ts, value in zip(times, values):
            value_counts[value] += 1
            band = "missing(-1)" if value == -1 else ("1-49" if value < 50 else ">=50")
            month_bands[keepa_minutes_to_dt(ts).strftime("%Y-%m")][band] += 1
        small = [ts for ts, v in zip(times, values) if 0 < v < 50]
        if small:
            asins_with_small += 1
            last_small_ts.append(max(small))
        current = product.get("monthlySold")
        tail_pairs[(values[-1], current if current is not None else "ABSENT")] += 1

    print(f"\n### `monthlySoldHistory`（履歴）\n")
    print(f"- 履歴を持つ ASIN: **{n_hist}**")
    print(f"- 履歴に出現したユニーク値: `{sorted(value_counts)}`")
    print(f"- 履歴のどこかに 1〜49 を持つ ASIN: **{asins_with_small}**")
    if last_small_ts:
        print(f"- 1〜49 が最後に観測された時刻: **{keepa_minutes_to_dt(max(last_small_ts))} UTC**")

    print("\n#### 履歴の末尾値と現在値の対応（整合チェック）\n")
    print("| 履歴の末尾値 | `monthlySold` | 件数 |")
    print("|---:|---:|---:|")
    for (tail, current), count in tail_pairs.most_common(15):
        print(f"| {tail} | {current} | {count} |")

    print("\n#### 月別：1〜49 の値が出た時期\n")
    print("| 年月 | 1-49 | >=50 | -1（欠測） |")
    print("|---|---:|---:|---:|")
    for month in sorted(month_bands):
        band = month_bands[month]
        print(f"| {month} | {band['1-49']} | {band['>=50']} | {band['missing(-1)']} |")


def report_by_drops(products: dict[str, dict]) -> None:
    """salesRankDrops30 の帯ごとに欠測率を見る。「回転が速いほど値が出る」の裏取り。"""
    bands = [(0, 10), (10, 20), (20, 32), (32, 50), (50, 100), (100, 10**9)]
    print("\n#### `salesRankDrops30` 帯別の出現率\n")
    print("| ドロップ数 | ASIN数 | 値あり | 出現率 | 値ありの最小値 |")
    print("|---|---:|---:|---:|---:|")
    for low, high in bands:
        subset = [p for p in products.values()
                  if isinstance((p.get("stats") or {}).get("salesRankDrops30"), int)
                  and low <= p["stats"]["salesRankDrops30"] < high]
        if not subset:
            continue
        have = [p["monthlySold"] for p in subset if isinstance(p.get("monthlySold"), int)]
        label = f"{low}–{high}" if high < 10**9 else f"{low}+"
        print(f"| {label} | {len(subset)} | {len(have)} | {len(have) / len(subset):.1%} | "
              f"{min(have) if have else '-'} |")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()
    root = Path(args.repo_root)

    primary: dict[str, dict] = {}
    for source_rel in RAW_DIRS:
        source_dir = root / source_rel
        if not source_dir.is_dir():
            print(f"<!-- skip (not found): {source_rel} -->")
            continue
        products = load_products(source_dir)
        report_current_values(source_rel, products)
        if not primary:
            primary = products  # 主データ = raw/

    if primary:
        report_history(primary)
        report_by_drops(primary)


if __name__ == "__main__":
    main()
