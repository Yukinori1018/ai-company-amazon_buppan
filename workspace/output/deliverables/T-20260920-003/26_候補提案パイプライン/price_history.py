#!/usr/bin/env python3
"""価格履歴 — 「この商品は普段いくらで売れているのか」を1枚で出す（純関数）。

なぜ要るか（2026-10-04 社長指示）
---------------------------------
> 「価格が変わるのは当然です。陳腐化もするし、利益が取れなかった商品が取れるようになる。
>   当然です。そのため、**過去の履歴を見てこの商品はどれくらいで売れるのかを把握する**のが
>   大事です。」

**現在価格で採算を出すのをやめます。**現在価格は1点の観測で、薄い棚ではとくに当てになりません。

実測（2026-10-04・社長が実画面で見た5件 対 Keepa）で分かったこと
----------------------------------------------------------------
| ASIN | 台帳の売価 | 社長が実画面で見た最低価格 | Keepa 現在NEW | Keepa 30日平均 | Keepa 90日平均 |
|---|---|---|---|---|---|
| B004PXZAFI | 5,897 | **5,017** | 5,897 | **5,013** | 4,035 |
| B003181XQ8 | 12,100 | 8,318 | 12,100 | 12,100 | 10,246 |
| B00ZW7OO0I | 1,991 | 1,300 | 1,991 | 1,991 | 1,991 |

🔴 **`current[NEW]` は薄い棚で「張り付く」。**B004PXZAFI では現在値 5,897 が動かないのに
30日平均は 5,013 で、**社長が実画面で見た 5,017 とほぼ一致しました**。つまり
**平均・中央値のほうが実勢に近い**。これが「履歴で見る」の実証です。

⚠️ **ただし B00ZW7OO0I は履歴が 1,991 で完全に平らなのに、実画面は 1,300 でした。**
履歴でも当たらない棚があります。だから本モジュールは**売価を1つに決めつけません** ──
中央値・下位25%・現在値・人が見た値を**全部列に出し**、採算は
`sell_for_profit()`（＝人が見た値があればそれ、無ければ90日中央値）で計算します。
食い違いは `disagreement` に残して人に回します（CLAUDE.md §3.3-1「食い違ったら食い違いごと出す」）。

Keepa の課金
------------
価格履歴は**商品レスポンスに最初から入っています**（`csv[1]` 新品最安・`csv[18]` BuyBox）。
`history=1` は既定で、**追加トークンは0**です（ランク履歴 `csv[3]` と同じ・§3.3-20）。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Keepa の時刻の変換は `seasonality._to_dt` を**そのまま借ります**。
# あのモジュールのコメントが「ここを自分で計算し直さないこと」と書いているとおりで、
# 2026-10-04 に書き直して実際に符号を間違えました（全件 days=0 になった）。
from seasonality import KEEPA_EPOCH_OFFSET_MIN, _to_dt   # noqa: F401,E402

CSV_AMAZON = 0
CSV_NEW = 1
CSV_RANK = 3
CSV_BUYBOX = 18          # ⚠️ 3値ずつ（時刻・価格・送料）。他の系列は2値ずつ。

# 価格の振れ幅がこれを超えたら「読めない」＝ UNKNOWN。四分位範囲 ÷ 中央値。
MAX_SPREAD = 0.35

# 直近90日の傾きがこれより急な下落なら「売る頃にはもっと安い」＝落とす（%/30日）。
DOWNTREND_PCT_PER_30D = -8.0

# 現在値 ÷ 90日中央値 がこれを超えたら高値掴みの疑い＝ UNKNOWN。
MAX_CURRENT_OVER_MEDIAN = 1.25

# 中央値を出すのに最低これだけの日数が埋まっていないといけない。
MIN_DAYS_COVERED = 20

# 🔴 階段関数の値を**この日数より先には持ち越さない**。
# 2026-10-04、持ち越しに上限を置かずに書いたら、**2年前に消えた BuyBox の価格が
# 「90日中央値」として出てきました**（B01N5Q61K6 で現在 4,250円 に対し中央値 1,400円）。
# 「カートが立っていない」は「その値段で売れている」ではありません。
MAX_CARRY_DAYS = 14


@dataclass
class PriceLevel:
    """「この商品は普段いくらで売れているのか」。すべて円・税込表示価格。"""

    source: str = "なし"            # BuyBox / 新品最安 / なし
    current: int | None = None      # 現在値（Keepa の最終観測）
    median90: int | None = None     # 🔴 採算の基準
    median180: int | None = None
    p25_90: int | None = None       # 🔴 悲観シナリオの売価
    p75_90: int | None = None
    spread: float | None = None     # (p75 − p25) ÷ 中央値。大きいほど読めない
    slope_pct_per_30d: float | None = None   # 直近90日の傾き
    days_covered: int = 0
    screen_price: int | None = None          # 人が実画面で見た価格（あれば最優先）
    verdict: str = "判定不能"       # 使える / 下落トレンド / 振れ幅が大きい / 高値 / 判定不能
    note: str = ""

    # ── 採算に使う値 ────────────────────────────────────────────────
    @property
    def sell_for_profit(self) -> int | None:
        """中央ケースの売価。**人が実画面で見た値があればそれを使う**（§3.3-16）。"""
        if self.screen_price:
            return self.screen_price
        return self.median90 or self.median180 or self.current

    @property
    def sell_pessimistic(self) -> int | None:
        """悲観ケースの売価＝90日の下位25%。人が見た値がそれより低ければそちら。"""
        cands = [v for v in (self.p25_90, self.screen_price) if v]
        return min(cands) if cands else self.sell_for_profit

    @property
    def current_over_median(self) -> float | None:
        if not (self.current and self.median90):
            return None
        return round(self.current / self.median90, 3)

    @property
    def disagreement(self) -> str:
        """人が見た値と履歴の食い違い。黙って片方を採らず、列に出して人に回す。"""
        if not (self.screen_price and self.median90):
            return ""
        gap = (self.screen_price - self.median90) / self.median90
        if abs(gap) < 0.10:
            return ""
        return (f"実画面 {self.screen_price:,}円 と 90日中央値 {self.median90:,}円 が "
                f"{gap * 100:+.0f}% 食い違います（実画面を採用）")


# ── Keepa csv の読み出し ────────────────────────────────────────────────


def parse_series(csv_list, index: int) -> list[tuple[datetime, int | None]]:
    """`csv[index]` を [(時刻, 値 または None)] に開く。

    BuyBox（18）だけは **3値ずつ**（時刻・価格・送料）なので、価格＋送料を足した
    「購入者が払う額」に直します。他の系列は2値ずつ。

    🔴 **`-1` を捨てずに `None` として残します。**Keepa は「ここから値が無い」を `-1` で
    書きます。捨ててしまうと、2年前に消えた BuyBox が「最後に見えた値がずっと続いている」
    ことになり、死んだ棚の2年前の価格が今日の中央値として出てきます（2026-10-04 に実際に
    やりました）。逆に `-1` を **欠測の開始**として扱えば、
      ・値が変わらない安定した棚 → 点は少ないが `None` も来ないので**今日まで有効**
      ・カートが消えた棚         → `-1` の時点で**そこから無効**
    を正しく分けられます。この区別を落とすと、**いちばん良い（値動きの無い）棚から
    順に捨てる**ことになります。
    """
    if not csv_list or len(csv_list) <= index or not csv_list[index]:
        return []
    raw = csv_list[index]
    step = 3 if index == CSV_BUYBOX else 2
    out: list[tuple[datetime, int | None]] = []
    for i in range(0, len(raw) - step + 1, step):
        t, v = raw[i], raw[i + 1]
        if v is None or v < 0:
            out.append((_to_dt(t), None))        # ここから値が無い
            continue
        if step == 3:
            ship = raw[i + 2]
            v = v + (ship if ship and ship > 0 else 0)
        out.append((_to_dt(t), int(v)))
    return out


def daily_samples(points: list[tuple[datetime, int]], days: int,
                  now: datetime | None = None) -> list[int]:
    """階段関数を**1日1点に打ち直す**。

    Keepa の履歴は「値が変わった時だけ」点が入る階段関数なので、点をそのまま数えると
    **値動きの激しい時期だけが重く数えられます**（中央値がゆがむ）。日付のグリッドで
    サンプリングして、時間に対して平等にします。

    値は**次の点が来るまで持ち越します**（階段関数の定義どおり）。持ち越しを止めるのは
    次の2つだけです。

    1. その区間の値が `None`（Keepa の `-1`）＝ そこから値が無いと書かれている
    2. **系列の最後の点から `MAX_CARRY_DAYS` 日より先**＝ 観測が途切れている

    ⚠️ 2 を「隣り合う点の間隔」に当ててはいけません。値が変わらない棚は点が少ないだけで、
    価格はちゃんと付いています。2026-10-04 に間隔へ当ててしまい、**236件が「価格が
    読めない」で落ちました**（安定した棚ほど落ちる＝狙いと真逆）。
    """
    if not points:
        return []
    now = now or datetime.now(timezone.utc)
    pts = sorted(points, key=lambda p: p[0])
    end = pts[-1][0] + timedelta(days=MAX_CARRY_DAYS)
    out: list[int] = []
    j = 0
    cur: int | None = None
    for d in range(days, -1, -1):
        at = now - timedelta(days=d)
        while j < len(pts) and pts[j][0] <= at:
            cur = pts[j][1]
            j += 1
        if cur is None or at < pts[0][0] or at > end:
            continue
        out.append(cur)
    return out


def _pct(vals: list[int], q: float) -> int | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return int(round(s[lo] + (s[hi] - s[lo]) * (pos - lo)))


def _slope_pct_per_30d(vals: list[int]) -> float | None:
    """日次サンプルの最小二乗の傾きを「30日あたり何%」で返す。"""
    n = len(vals)
    if n < MIN_DAYS_COVERED:
        return None
    mean_y = statistics.fmean(vals)
    if mean_y <= 0:
        return None
    mean_x = (n - 1) / 2
    sxy = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(vals))
    sxx = sum((i - mean_x) ** 2 for i in range(n))
    if sxx == 0:
        return None
    return round(sxy / sxx * 30 / mean_y * 100, 1)


# ── 入口 ────────────────────────────────────────────────────────────────


def from_product(product: dict, screen_price: int | None = None,
                 now: datetime | None = None) -> PriceLevel:
    """Keepa の商品1件から価格水準を出す。

    BuyBox 履歴を優先し、点が足りなければ新品最安（`csv[1]`）に落とします。
    BuyBox は「実際にカートで売れていた価格」なので、こちらが実勢に近いです。
    """
    csvs = product.get("csv") or []
    cand: list[tuple[str, list[int], list[int]]] = []
    for name, idx in (("BuyBox", CSV_BUYBOX), ("新品最安", CSV_NEW)):
        pts = parse_series(csvs, idx)
        d90, d180 = daily_samples(pts, 90, now), daily_samples(pts, 180, now)
        if d90:
            cand.append((name, d90, d180))
    if not cand:
        return PriceLevel(screen_price=screen_price, verdict="判定不能",
                          note="価格履歴がありません（Keepa に BuyBox も新品最安も無い）。")

    # 🔴 **2本あるときは安い側を採ります。**BuyBox（買い手が実際に払った額）と
    # 新品最安（送料別）は建て付けが違うので、ずれたら**低いほうが保守側**です。
    # 2026-10-04、B004PXZAFI で BuyBox 3,400円 と 新品最安 5,897円 が食い違いました。
    # 高いほうを採ると赤字を黒字と報告するので、**迷ったら安いほう**にします。
    best = min(cand, key=lambda c: _pct(c[1], 0.5) or 10**9)
    source, d90, d180 = best
    if len(cand) == 2:
        other = [c for c in cand if c[0] != source][0]
        source = f"{source}（{other[0]} は {_pct(other[1], 0.5):,}円・安い側を採用）"
    med90, med180 = (_pct(d90, 0.5), _pct(d180, 0.5))
    p25, p75 = _pct(d90, 0.25), _pct(d90, 0.75)
    spread = round((p75 - p25) / med90, 3) if (med90 and p25 is not None and p75) else None
    slope = _slope_pct_per_30d(d90)
    cur = d90[-1] if d90 else None

    lv = PriceLevel(source=source, current=cur, median90=med90, median180=med180,
                    p25_90=p25, p75_90=p75, spread=spread, slope_pct_per_30d=slope,
                    days_covered=len(d90), screen_price=screen_price)

    # ── 判定（落とす・残す）。順番に意味があります。
    if len(d90) < MIN_DAYS_COVERED:
        lv.verdict = "判定不能"
        lv.note = (f"直近90日のうち価格が付いていたのは {len(d90)}日だけです"
                   f"（{MIN_DAYS_COVERED}日未満）。普段の値が決まりません。")
    elif slope is not None and slope <= DOWNTREND_PCT_PER_30D:
        lv.verdict = "下落トレンド"
        lv.note = (f"直近90日が 30日あたり {slope:+.1f}% の下落です。"
                   f"仕入れて納品して売る頃（2〜4週間後）にはもっと安くなります。")
    elif spread is not None and spread > MAX_SPREAD:
        lv.verdict = "振れ幅が大きい"
        lv.note = (f"90日の四分位範囲が中央値の {spread * 100:.0f}% あります"
                   f"（{MAX_SPREAD * 100:.0f}% 超）。いくらで売れるかが読めません。")
    elif (lv.current_over_median or 0) > MAX_CURRENT_OVER_MEDIAN:
        lv.verdict = "高値"
        lv.note = (f"現在 {cur:,}円 は90日中央値 {med90:,}円 の "
                   f"{lv.current_over_median:.2f}倍 です。いまの高値は長続きしません。"
                   f"**採算は中央値 {med90:,}円 で見ます。**")
    else:
        lv.verdict = "使える"
        ratio = lv.current_over_median
        if ratio and ratio < 0.9:
            lv.note = (f"現在 {cur:,}円 は90日中央値 {med90:,}円 の {ratio:.2f}倍＝"
                       f"**いま安い**（普段の値に戻れば上振れ）。")
        else:
            lv.note = (f"90日中央値 {med90:,}円・下位25% {p25:,}円 で安定しています"
                       f"（振れ幅 {(spread or 0) * 100:.0f}%・傾き {slope:+.1f}%/30日）。")
    if lv.disagreement:
        lv.note += " ⚠️ " + lv.disagreement
    return lv
