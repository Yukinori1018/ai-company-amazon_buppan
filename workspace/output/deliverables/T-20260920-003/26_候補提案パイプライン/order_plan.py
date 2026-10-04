#!/usr/bin/env python3
"""発注案 — 残枠の中で買う3SKUの組み合わせを作る（純関数）。

社長の要求（2026-10-04）
> 残枠 約8万円で買う3SKU の組み合わせを3案。各案に：合計発注額／想定手残り合計／
> 捌ける月数／分散（同じ購入元に偏らない）／最悪ケース（半値処分時の損失）。
> それぞれ「この3SKUで何月にいくらの手残りになるか」。

**発注はしません。**ここが作るのは「人が見て押すだけ」の一歩手前までです（§4.1）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

BUDGET_YEN = 80_000
SKU_PER_PLAN = 3


@dataclass
class Pick:
    """1 SKU ぶんの発注内容。`score_20261004` の1行から作ります。"""

    asin: str
    title: str
    supplier: str
    grade: str
    qty: int
    order_total: int
    net_per_unit: int
    worst_net_per_unit: int
    half_disposal_loss: int
    months_to_sell: float
    listing_starts_on: date
    sellout_month: str
    season_window: str

    @property
    def net_total(self) -> int:
        return self.net_per_unit * self.qty

    @property
    def worst_total(self) -> int:
        return (self.worst_net_per_unit or 0) * self.qty


@dataclass
class Plan:
    name: str
    picks: list[Pick]
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def order_total(self) -> int:
        return sum(p.order_total for p in self.picks)

    @property
    def net_total(self) -> int:
        return sum(p.net_total for p in self.picks)

    @property
    def worst_total(self) -> int:
        return sum(p.worst_total for p in self.picks)

    @property
    def half_loss(self) -> int:
        """**全部売れ残って半値処分したとき**の損失合計。最悪ケースの下限。"""
        return sum(p.half_disposal_loss for p in self.picks)

    @property
    def suppliers(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.picks:
            out[p.supplier] = out.get(p.supplier, 0) + p.order_total
        return out

    @property
    def concentration(self) -> float:
        """1社に寄っている割合（0〜1）。**0.6 を超えたら分散できていない。**"""
        s = self.suppliers
        return max(s.values()) / self.order_total if self.order_total else 1.0

    @property
    def months_to_clear(self) -> float:
        """全部捌けるまでの月数＝いちばん遅い SKU に引っぱられる。"""
        return max((p.months_to_sell for p in self.picks), default=0.0)

    def cash_by_month(self) -> list[tuple[str, int]]:
        """🔴 **何月にいくらの手残りになるか。**

        各 SKU の手残りを、販売開始月から売り切り月まで**均等に割って**積み上げます
        （実際は立ち上がりが遅いので、前倒しに出ていると思ってください＝楽観側）。
        """
        acc: dict[str, int] = {}
        for p in self.picks:
            months = _month_keys(p.listing_starts_on, p.months_to_sell)
            if not months:
                continue
            per = p.net_total // len(months)
            for m in months:
                acc[m] = acc.get(m, 0) + per
        return sorted(acc.items())

    def as_dict(self) -> dict:
        return {
            "案": self.name, "狙い": self.reason,
            "合計発注額": self.order_total, "想定手残り合計": self.net_total,
            "悲観の手残り合計": self.worst_total,
            "捌ける月数": self.months_to_clear,
            "購入元の内訳": self.suppliers,
            "1社への偏り(%)": round(self.concentration * 100, 1),
            "最悪ケース(全量半値処分の損失)": -self.half_loss,
            "月別の手残り": dict(self.cash_by_month()),
            "注意": self.warnings,
            "SKU": [{"ASIN": p.asin, "商品名": p.title, "購入元": p.supplier,
                     "等級": p.grade, "発注数": p.qty, "発注額": p.order_total,
                     "1個手残り": p.net_per_unit, "手残り合計": p.net_total,
                     "販売開始": p.listing_starts_on.strftime("%m/%d"),
                     "売り切り目標": p.sellout_month, "季節の窓": p.season_window}
                    for p in self.picks],
        }


def _month_keys(start: date, months: float) -> list[str]:
    n = max(1, int(round(months)))
    out, y, m = [], start.year, start.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build_plans(picks: list[Pick], budget: int = BUDGET_YEN,
                sku_per_plan: int = SKU_PER_PLAN) -> list[Plan]:
    """3つの案を作る。**狙いが違う3案**にします（同じ案の並べ替えでは判断材料になりません）。

    ① 手残り最大     … 予算内で想定手残りが最も大きい組み合わせ
    ② 分散重視       … 購入元が3社に割れていて、1社への偏りが最小
    ③ 下振れ耐性重視 … 悲観シナリオの手残りが最も大きい（等級Aを優先）
    """
    valid = [c for c in combinations(picks, sku_per_plan)
             if sum(p.order_total for p in c) <= budget]
    if not valid:
        return []

    def mk(name: str, combo, reason: str) -> Plan:
        p = Plan(name, list(combo), reason)
        if p.concentration > 0.6:
            s = max(p.suppliers, key=p.suppliers.get)
            p.warnings.append(
                f"購入元が『{s}』に {p.concentration * 100:.0f}% 寄っています。"
                f"**1社が品切れ・取引不可になると案が丸ごと倒れます。**")
        if any(x.season_window == "△" for x in p.picks):
            p.warnings.append("季節の窓が△の SKU が入っています（1週遅れると外します）。")
        if any(x.grade == "B" for x in p.picks):
            p.warnings.append("等級Bの SKU は**最小ロットで1回だけ**実測してください。")
        if p.months_to_clear > 6:
            p.warnings.append(
                f"捌けるまで {p.months_to_clear:.1f}ヶ月＝回転上限6ヶ月を超えます。")
        return p

    best_net = max(valid, key=lambda c: sum(p.net_total for p in c))
    best_div = min(valid, key=lambda c: (
        -len({p.supplier for p in c}),
        max(sum(p.order_total for p in c if p.supplier == s)
            for s in {p.supplier for p in c}) / max(1, sum(p.order_total for p in c)),
        -sum(p.net_total for p in c)))
    best_worst = max(valid, key=lambda c: (sum(p.worst_total for p in c),
                                           sum(1 for p in c if p.grade == "A")))
    return [
        mk("① 手残り最大", best_net, "予算内で想定手残りがいちばん大きい組み合わせ。"),
        mk("② 分散重視", best_div,
           "購入元をできるだけ割った組み合わせ。1社が倒れても残りが生きます。"),
        mk("③ 下振れ耐性重視", best_worst,
           "悲観シナリオ（売価が90日の下位25%・区分1段上・保管2倍）でも"
           "手残りがいちばん残る組み合わせ。"),
    ]


def pick_from_row(s: dict) -> Pick | None:
    """`score_20261004.build()` の戻り値から `Pick` を作る。"""
    e, pl, r = s.get("econ"), s.get("plan"), s["row"]
    if not (e and pl):
        return None
    return Pick(
        asin=s["asin"], title=r["商品名"][:40],
        supplier=r.get("購入元の名前") or "不明", grade=s["等級"],
        qty=e.qty, order_total=e.order_total, net_per_unit=e.net_per_unit,
        worst_net_per_unit=e.worst_net_per_unit or 0,
        half_disposal_loss=e.half_disposal_loss,
        months_to_sell=e.months_to_sell or 3.0,
        listing_starts_on=pl.listing_starts_on,
        sellout_month=pl.sellout_month, season_window=pl.season_window)
