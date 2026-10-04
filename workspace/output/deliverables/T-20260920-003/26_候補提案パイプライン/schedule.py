#!/usr/bin/env python3
"""いつ買って、いつ売るか — 発注日から販売開始日・売り切り目標月までを引く（純関数）。

なぜ要るか（2026-10-04 社長指示）
---------------------------------
> 「**いつ買って、いつ売るかも考えてリストを作ってね。**」

単価と利益率だけの表では決められません。**いま10月4日で、仕入れて納品して売れるまでに
2〜4週間かかります。**だから「3〜5月がピークの商品をいま買うと半年寝る」（§3.3-20）。

🔴 **リードタイムの数字は推定です。**NETSEA / スーパーデリバリーの商品ページには
出荷目安（「翌営業日」「5営業日以内」等）が出ますが、**当社の JAN 索引はそれを取って
いません**（索引の項目は jan / 卸値 / 最小ロット / 在庫 / 店名 / URL だけ）。
ですので本モジュールは**チャネル別の既定値**を置き、`lead_days` を渡せば上書きできる形に
してあります。**発注直前に商品ページで実際の出荷目安を見て上書きしてください。**
推定であることは `assumed` に出ます（列に「推定」と出して、確定値と混ぜないため）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# ── リードタイムの既定値（営業日）。すべて**推定**。確定値が取れたら引数で上書きする。
#    根拠：NETSEA / SD は「発送までの目安」を店ごとに出しており、当社が見た店は
#    「即日〜5営業日」の幅だった（2026-09-30 の実画面）。中央の3営業日を置く。
DEFAULT_SUPPLIER_SHIP_BDAYS = {"NETSEA": 3, "スーパーデリバリー": 5}
DEFAULT_SUPPLIER_SHIP_BDAYS_FALLBACK = 5

# 卸の発送 → 社長宅に着くまでの配送日数（暦日・宅配便）。
DELIVERY_DAYS = 2

# 🔴 社長宅での検品・ラベル貼り・梱包（営業日）。**納品代行は未契約**なので当面は自宅。
#    CLAUDE.md §3.4「初回仕入れは自宅検品、2回目からFBA外注」。
HOME_PREP_BDAYS = 2

# 発送 → FBA 倉庫が受領して販売可能になるまで（営業日）。ヤマト FBAパートナーキャリア。
FBA_RECEIVING_BDAYS = 5

# 出品許可（ゲート）の申請が要る場合の上乗せ（営業日）。中央5・最悪10。
# 根拠：CLAUDE.md §3.3-25 の「＋3〜7営業日（最長2週間）」。
GATE_BDAYS_MID = 5
GATE_BDAYS_WORST = 10

# 季節の窓の判定
IN_WINDOW = "○"        # 販売開始から売り切り目標までにピーク月が入る
EDGE = "△"             # 肩だけかかる／ピークが窓の端
MISSED = "×"           # ピークを過ぎている or 窓に入らない
NO_SEASON = "○（通年）"


def add_bdays(start: date, n: int) -> date:
    """営業日を足す（土日を飛ばす）。

    ⚠️ **祝日は見ていません。**年末年始とゴールデンウィークは実際より楽観に出ます。
    10〜12月に当てる用途なので、11/3・11/23・12/29〜1/3 ぶん **数日は遅れる**と
    思ってください（列に出すのは営業日ベースの最短です）。
    """
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def month_span(start: date, months: float) -> date:
    """`start` から `months` ヶ月後の日付（暦の概算・30日/月）。"""
    return start + timedelta(days=int(round(months * 30)))


def _months_between(a: date, b: date) -> list[int]:
    """`a` から `b` までに触れる月（1〜12）を順に並べる。"""
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@dataclass
class Plan:
    """1 SKU のカレンダー。日付はすべて「最短でこの日」。"""

    order_on: date                    # 発注日
    arrives_on: date                  # 着荷の見込み（社長宅）
    fba_ready_on: date                # FBA 納品完了（販売可能になる日）の見込み
    listing_starts_on: date           # 販売開始日（ゲート申請ぶんを含む）
    sellout_target: date | None       # 売り切り目標（販売開始 ＋ 捌ける月数）
    season_window: str = NO_SEASON    # ○ / △ / × / ○（通年）
    season_note: str = ""
    weeks_to_listing: int = 0         # 発注から販売開始までの週数
    assumed: list[str] = field(default_factory=list)   # 推定で埋めた前提

    @property
    def sellout_month(self) -> str:
        return self.sellout_target.strftime("%Y-%m") if self.sellout_target else "未確定"

    def as_row(self) -> dict:
        f = "%m/%d"
        return {
            "発注日": self.order_on.strftime(f),
            "着荷の見込み": self.arrives_on.strftime(f),
            "FBA納品完了の見込み": self.fba_ready_on.strftime(f),
            "販売開始日": self.listing_starts_on.strftime(f),
            "売り切り目標月": self.sellout_month,
            "季節の窓": self.season_window,
            "発注→販売開始": f"{self.weeks_to_listing}週",
            "カレンダーの前提": " / ".join(self.assumed) or "既定値",
        }


def build(today: date, *, channel: str | None = None,
          lead_bdays: int | None = None,
          gate_needed: bool = False, gate_worst: bool = False,
          months_to_sell: float | None = None,
          peak_months: tuple[int, ...] = (), season_verdict: str = "") -> Plan:
    """1 SKU ぶんのカレンダーを引く。

    `lead_bdays` を渡せばチャネル既定値を上書きします（商品ページの出荷目安を見た値）。
    `peak_months` / `season_verdict` は `seasonality.Season` からそのまま渡します。
    """
    assumed: list[str] = []
    if lead_bdays is None:
        lead_bdays = DEFAULT_SUPPLIER_SHIP_BDAYS.get(
            channel or "", DEFAULT_SUPPLIER_SHIP_BDAYS_FALLBACK)
        assumed.append(f"卸の出荷 {lead_bdays}営業日（推定・商品ページ未確認）")

    order_on = today
    ship_on = add_bdays(order_on, lead_bdays)
    arrives_on = ship_on + timedelta(days=DELIVERY_DAYS)
    prep_done = add_bdays(arrives_on, HOME_PREP_BDAYS)
    assumed.append(f"自宅で検品・ラベル {HOME_PREP_BDAYS}営業日（納品代行は未契約）")
    fba_ready = add_bdays(prep_done, FBA_RECEIVING_BDAYS)

    listing = fba_ready
    if gate_needed:
        extra = GATE_BDAYS_WORST if gate_worst else GATE_BDAYS_MID
        listing = add_bdays(fba_ready, extra)
        assumed.append(f"ゲート申請 +{extra}営業日")

    sellout = month_span(listing, months_to_sell) if months_to_sell else None
    weeks = max(1, round((listing - order_on).days / 7))

    p = Plan(order_on, arrives_on, fba_ready, listing, sellout,
             weeks_to_listing=weeks, assumed=assumed)
    p.season_window, p.season_note = _season_window(listing, sellout, peak_months,
                                                    season_verdict)
    return p


def _season_window(listing: date, sellout: date | None,
                   peak_months: tuple[int, ...], verdict: str) -> tuple[str, str]:
    """🔴 **販売開始日が季節のピークを過ぎる候補は落とす**ための判定。

    窓＝販売開始月 〜 売り切り目標月。この窓にピーク月が1つでも入れば ○。
    入らなければ ×（＝いま買うとピークを外して在庫を抱える）。
    """
    if verdict == "通年低調":
        return MISSED, "ランク履歴が通年で低調です（ピークがありません）。"
    if not peak_months or verdict in ("通年", "判定不能", ""):
        return NO_SEASON, ("季節性が出ていません（通年の棚）。"
                           "いつ売り始めても条件は同じです。")

    end = sellout or month_span(listing, 3)
    window = _months_between(listing, end)
    hit = [m for m in window if m in peak_months]
    peaks = "・".join(f"{m}月" for m in sorted(peak_months))

    if hit:
        got = "・".join(f"{m}月" for m in hit)
        # 窓の最後の月だけがピークなら、間に合うかどうかが紙一重。
        if len(hit) == 1 and hit[0] == window[-1]:
            return EDGE, (f"ピークは {peaks} で、販売期間（{window[0]}月〜{window[-1]}月）の"
                          f"**最後の月にようやく {got} が入ります**。1週遅れると外します。")
        return IN_WINDOW, (f"ピークは {peaks} で、販売期間（{window[0]}月〜{window[-1]}月）に "
                           f"{got} が入ります。**いま買えば間に合います。**")
    return MISSED, (f"ピークは {peaks} ですが、販売期間は {window[0]}月〜{window[-1]}月 で"
                    f"重なりません。**いま仕入れると次のピークまで寝かせます。**")
