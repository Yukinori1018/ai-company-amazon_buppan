#!/usr/bin/env python3
"""入口の並び順 — Keepa に回す前に「実効卸率の見込み」で順番を決める（純関数・通信0）。

2026-10-14 タカシ（T-20261014-001 ハジメ成果物01 §5「入口フィルタ」を順番として実装）。

    実効卸率の見込み ＝ 定価比卸率 ÷（Amazon 90日中央値 ÷ 定価税込）
                     ＝ 卸1点（税抜）÷ Amazon 1点あたりの売価（税抜）

- **55%以下を先に回す**（卸サイトで B 等級に届く線。小型2,000円の B 線が55.6%・ハジメ §5）
- 🔴 **これは捨てるフィルタではなく順番です**（CLAUDE.md §3.3-34：上限・足切りを置かない）。
  55%超も、定価が無い行も、**後ろの順番で必ず残す**。誰も打ち切らない
- Amazon の90日中央値が Keepa を引く前に分かっていない JAN（ほとんど）は、
  「Amazon 実売 ÷ 定価」の中央値 **0.86**（ハジメ 母集団B・1,119 ASIN）で置く。**推定**なので
  並べ替えにしか使わない。採算の結論は後段（`fba_cost.grade`）が実売価で出す

グループ（小さいほど先）
  0 … 見込み55%以下
  1 … 定価が無くて計算できない（中身が分からないので真ん中）
  2 … 見込み55%超
"""
from __future__ import annotations

TAX = 1.1
#: 先に回す線（仮置き・§3.1。実績で直す）
EFFECTIVE_RATE_FIRST = 0.55
#: Amazon 実売（1点・税抜）÷ 定価（税抜）の中央値。ハジメ T-20261014-001 §3 母集団B（推定）
AMAZON_TO_LIST_DEFAULT = 0.86

GROUP_FIRST, GROUP_UNKNOWN, GROUP_LATER = 0, 1, 2


def _f(x) -> float | None:
    try:
        v = float(str(x).replace(",", "").replace("円", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def effective_rate(wholesale_excl, list_price_excl, amazon_median_incl=None,
                   set_n: float = 1.0) -> float | None:
    """実効卸率の見込み（0〜）。定価か卸値が無ければ None。

    `amazon_median_incl` … Amazon の90日中央値（税込・その ASIN の1個＝卸 `set_n` 点ぶん）。
                          分かっていなければ None → 定価 × 0.86 を Amazon の1点売価とみなす
    """
    w, lp = _f(wholesale_excl), _f(list_price_excl)
    if not w or not lp:
        return None
    med = _f(amazon_median_incl)
    n = _f(set_n) or 1.0
    if med:
        amazon_to_list = (med / n) / (lp * TAX)      # Amazon 90日中央値 ÷ 定価税込（1点あたり）
    else:
        amazon_to_list = AMAZON_TO_LIST_DEFAULT
    return (w / lp) / amazon_to_list


def group_of(rate: float | None) -> int:
    if rate is None:
        return GROUP_UNKNOWN
    return GROUP_FIRST if rate <= EFFECTIVE_RATE_FIRST + 1e-9 else GROUP_LATER


def sort_key(rate: float | None) -> tuple[int, float]:
    """`sorted(..., key=...)` 用。グループ → 見込みの低い順。定価なしは同点（元の順を保つ）。"""
    return (group_of(rate), rate if rate is not None else 0.0)


def label(rate: float | None) -> str:
    g = group_of(rate)
    return {GROUP_FIRST: f"先（実効卸率見込み≦{EFFECTIVE_RATE_FIRST:.0%}）",
            GROUP_UNKNOWN: "中（定価なし）",
            GROUP_LATER: f"後（{EFFECTIVE_RATE_FIRST:.0%}超・捨てない）"}[g]
