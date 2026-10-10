"""カートが消えている棚（「一般的な価格より高い」でカート非表示など）の基準売価を出す。

2026-10-11 タカシ（T-20260920-003）。

なぜ：カートが無い棚は、いま並んでいる出品が相場より高いだけのことがある。
その場合、相場で出品すればカートを取れる見込みがある。ただし「いまの新品最安」は
吊り上がった価格なので、採算の基準にすると黒字を過大に見る。

基準売価＝**カートが立っていた最後の期間の BuyBox 価格の中央値**（Keepa csv[18]）。
  - 直近365日のうちカートが立っていた日だけを使う（日次サンプル）
  - その中で「最後に立っていた日」から遡って90日ぶん（§3.3-28 の90日中央値と同じ考え方）
  - 悲観値は同じ区間の下位25%
カートが365日一度も立っていなければ None（基準が無い＝推測で埋めない）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

KEEPA_T0 = 21564000
CSV_BUYBOX = 18


@dataclass
class PastBuyBox:
    median: int
    p25: int
    last_day: str          # カートが最後に立っていた日
    first_day: str         # 使った区間の始まり
    days: int              # 使った日数
    gap_days: int          # 最後に立っていた日から今日まで

    def text(self) -> str:
        return (f"カートが立っていた最後の90日（{self.first_day}〜{self.last_day}・{self.days}日）の"
                f"BuyBox 中央値 {self.median:,}円・下位25% {self.p25:,}円"
                f"（カート消失から {self.gap_days}日）")


def _day(kmin: int) -> str:
    return datetime.fromtimestamp((kmin + KEEPA_T0) * 60, tz=timezone.utc).strftime("%Y-%m-%d")


def daily_buybox(product: dict, now_unix: int, days: int = 365) -> list[tuple[int, int]]:
    """[(Keepa分の日の頭, 価格)]。BuyBox 履歴は [t, 価格, 送料, ...] の3つ組。"""
    c = product.get("csv") or []
    h = c[CSV_BUYBOX] if len(c) > CSV_BUYBOX else None
    if not h:
        return []
    now_min = now_unix // 60 - KEEPA_T0
    lo = now_min - days * 1440
    pts = [(h[i], h[i + 1] + max(h[i + 2], 0) if h[i + 1] > 0 else -1)
           for i in range(0, len(h) - 2, 3)]
    out = []
    for d0 in range(lo - lo % 1440, now_min, 1440):
        v = None
        for t, p in pts:          # その日の頭の時点で効いていた値
            if t <= d0:
                v = p
            else:
                break
        if v and v > 0:
            out.append((d0, v))
    return out


def past_buybox(product: dict, now_unix: int) -> PastBuyBox | None:
    ds = daily_buybox(product, now_unix)
    if not ds:
        return None
    last = ds[-1][0]
    win = [p for t, p in ds if t > last - 90 * 1440]
    win.sort()
    med = win[len(win) // 2]
    p25 = win[len(win) // 4]
    now_min = now_unix // 60 - KEEPA_T0
    first = min(t for t, _ in ds if t > last - 90 * 1440)
    return PastBuyBox(med, p25, _day(last), _day(first), len(win), (now_min - last) // 1440)
