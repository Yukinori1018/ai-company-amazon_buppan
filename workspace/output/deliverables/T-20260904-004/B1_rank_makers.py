#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""和名メーカーを「先に連絡先を調べる価値が高い順」に並べる。

T-20260904-004 / B-1 本走行（2026-09-04 カズヨ発注）の指示③:
    451社を頭から流さないこと。Amazon 実績で並べ替え、上位から処理すること。

**このスコアは利益予測ではありません。処理順を決めるためのヒューリスティックです。**
元データの `想定仕入れ金額の中央値` は推定値で、実測ではありません
（memory `feedback_research_accuracy_blocker`）。
「スコアが高い＝儲かる」と読まないこと。「先に調べる価値がある」だけです。

スコアの構成（すべて v14 `03_メーカー名寄せ.csv` の観測値から）:

    score = 商品数係数 × 粗利率 × 回転係数 × 予算係数 × 規模係数 × リスク係数

| 係数 | 定義 | なぜ入れるか |
|---|---|---|
| 商品数係数 | sqrt(該当商品数) | 1社から複数SKU取れる方が交渉の価値が高い。効きすぎないよう平方根 |
| 粗利率 | (Amazon価格 - 想定仕入れ) / Amazon価格 | **推定値。実測ではない** |
| 回転係数 | 1 / max(消化月数, 1) | 消化が速いほど資金が回る |
| 予算係数 | 想定仕入れが 10,000円超なら 0.3 | 総予算5万円。単価が高いと5〜10SKU組めない |
| 規模係数 | 「大手/海外疑い」なら 0.2 | 大手は初回小ロットの直取引に応じない（本丸は中小メーカー） |
| リスク係数 | 1 / (1 + リスク区分あり件数 / 該当商品数) | 出品制限・知財リスクが多い社は後回し |

使い方:
    python3 B1_rank_makers.py                 # キューを標準出力に表示
    python3 B1_rank_makers.py --write         # B1_work_queue.csv を書き出す
    python3 B1_rank_makers.py --top 50        # 上位50社だけ
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERABLES = os.path.dirname(HERE)

V14 = os.path.join(DELIVERABLES, "T-20260817-005", "v14", "03_メーカー名寄せ.csv")
CONTACTS = os.path.join(DELIVERABLES, "T-20260831-001", "contacts_v1.csv")
QUEUE = os.path.join(HERE, "B1_work_queue.csv")

TARGET_CLASS = "和名法人らしき"
CONTACT_COLS = ("公式HP", "電話", "問い合わせフォームURL", "メール")

#: 総予算5万円（チケット T-20260904-004「予算5万円から導かれる制約」）。
#: 仕入れ単価がこれを超えると 5〜10SKU の組み合わせが作れない。
UNIT_PRICE_CEILING = 10000


def _num(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def score_row(v14_row) -> float:
    """1社ぶんのスコア。**利益予測ではなく処理順のヒューリスティック。**

    >>> round(score_row({"該当商品数": "4", "想定仕入れ金額の中央値": "2000",
    ...                  "Amazon価格の中央値": "5000", "消化月数の中央値": "1",
    ...                  "規模フラグ": "中小候補", "リスク区分あり件数": "0"}), 3)
    1.2
    """
    n = _num(v14_row.get("該当商品数"), 0.0)
    if n <= 0:
        return 0.0
    buy = _num(v14_row.get("想定仕入れ金額の中央値"), 0.0)
    sell = _num(v14_row.get("Amazon価格の中央値"), 0.0)
    months = _num(v14_row.get("消化月数の中央値"), 1.0)
    risk = _num(v14_row.get("リスク区分あり件数"), 0.0)

    if sell <= 0 or buy <= 0:
        return 0.0
    margin = (sell - buy) / sell
    if margin <= 0:
        return 0.0  # 赤字は不可（チケットの制約）

    count_factor = math.sqrt(n)
    turn_factor = 1.0 / max(months, 1.0)
    budget_factor = 1.0 if buy <= UNIT_PRICE_CEILING else 0.3
    scale_factor = 0.2 if (v14_row.get("規模フラグ") or "") == "大手/海外疑い" else 1.0
    risk_factor = 1.0 / (1.0 + risk / n)

    return count_factor * margin * turn_factor * budget_factor * scale_factor * risk_factor


def build_queue():
    """未充填の和名メーカーをスコア降順で返す。"""
    with open(V14, encoding="utf-8-sig") as fp:
        v14 = {r["メーカー/ブランド"]: r for r in csv.DictReader(fp)}
    with open(CONTACTS, encoding="utf-8-sig") as fp:
        contacts = list(csv.DictReader(fp))

    out = []
    for c in contacts:
        if (c.get("分類") or "") != TARGET_CLASS:
            continue
        if any((c.get(k) or "").strip() for k in CONTACT_COLS):
            continue  # 既に埋まっている社は再取得しない（冪等）
        name = c["メーカー名"]
        v = v14.get(name)
        if v is None:
            continue
        out.append({
            "順位": 0,
            "メーカー名": name,
            "スコア": round(score_row(v), 4),
            "該当商品数": v.get("該当商品数", ""),
            "想定仕入れ金額の中央値": v.get("想定仕入れ金額の中央値", ""),
            "Amazon価格の中央値": v.get("Amazon価格の中央値", ""),
            "消化月数の中央値": v.get("消化月数の中央値", ""),
            "主なカテゴリ": v.get("主なカテゴリ", ""),
            "規模フラグ": v.get("規模フラグ", ""),
            "リスク区分あり件数": v.get("リスク区分あり件数", ""),
            "代表商品名": v.get("代表商品名", ""),
            "代表ASIN": v.get("代表ASIN", ""),
        })
    out.sort(key=lambda r: (-r["スコア"], r["メーカー名"]))
    for i, r in enumerate(out, 1):
        r["順位"] = i
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="B1_work_queue.csv に書き出す")
    ap.add_argument("--top", type=int, default=30, help="表示件数")
    args = ap.parse_args()

    rows = build_queue()
    print("和名・未充填: %d社" % len(rows), file=sys.stderr)
    if args.write:
        with open(QUEUE, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("wrote %s" % QUEUE, file=sys.stderr)
    for r in rows[: args.top]:
        print("%4d %7.3f  %-28s %2s件 %s  仕入%s→売%s  %s"
              % (r["順位"], r["スコア"], r["メーカー名"][:28], r["該当商品数"],
                 r["主なカテゴリ"][:10], r["想定仕入れ金額の中央値"],
                 r["Amazon価格の中央値"], r["代表商品名"][:34]))


if __name__ == "__main__":
    main()
