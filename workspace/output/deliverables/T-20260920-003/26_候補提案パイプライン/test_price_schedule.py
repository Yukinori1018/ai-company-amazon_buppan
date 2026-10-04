#!/usr/bin/env python3
"""price_history.py と schedule.py のテスト。`python3 test_price_schedule.py` で走ります。

縮退した入力を必ず入れます（CLAUDE.md §3.3-20「縮退した入力をテストする」）。
2026-10-01 に「全月が同じように低調だと通年低調の棚が季節物に化ける」事故を出したので、
**平らな履歴・空の履歴・1点だけの履歴**を全部通します。
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, ".")
import price_history as PH          # noqa: E402
import schedule as SC               # noqa: E402

NG = 0


def check(name, got, want):
    global NG
    ok = got == want
    if not ok:
        NG += 1
    print(f"  {'ok' if ok else 'NG  '} {name}" + ("" if ok else f": {got!r} ≠ {want!r}"))


NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def kminute(d: datetime) -> int:
    """datetime → Keepa の分。`seasonality._to_dt` の逆。"""
    return int(d.timestamp() // 60) - PH.KEEPA_EPOCH_OFFSET_MIN


def flat_csv(price: int, days: int, index: int = PH.CSV_NEW, step_days: int = 7):
    """`days` 日前から一定価格が続く履歴を作る。"""
    raw = []
    d = days
    while d >= 0:
        t = kminute(NOW - timedelta(days=d))
        raw += [t, price] + ([0] if index == PH.CSV_BUYBOX else [])
        d -= step_days
    out = [[] for _ in range(20)]
    out[index] = raw
    return out


print("1. 価格履歴の基本")
lv = PH.from_product({"csv": flat_csv(1500, 200)}, now=NOW)
check("平らな履歴の90日中央値", lv.median90, 1500)
check("  下位25%も同じ", lv.p25_90, 1500)
check("  振れ幅は0", lv.spread, 0.0)
check("  判定は使える", lv.verdict, "使える")
check("  採算に使う売価は中央値", lv.sell_for_profit, 1500)

print("\n2. 縮退した入力（ここで嘘をつかせない）")
check("履歴が空なら判定不能", PH.from_product({"csv": []}, now=NOW).verdict, "判定不能")
check("csv キーが無くても落ちない", PH.from_product({}, now=NOW).verdict, "判定不能")
one = PH.from_product({"csv": flat_csv(1000, 300, step_days=400)}, now=NOW)
check("1点しか無ければ日数が足りず判定不能", one.verdict, "判定不能")
check("  中央値を出せなくても例外にしない", one.median90 is None or one.median90 == 1000, True)

print("\n3. 🔴 持ち越しの打ち切り（2年前に消えた BuyBox を今日の中央値にしない）")
dead = [[] for _ in range(20)]
# BuyBox が 300日前に 1,400円で終わっている（以後カートが立っていない）。
dead[PH.CSV_BUYBOX] = [kminute(NOW - timedelta(days=330)), 1400, 0,
                       kminute(NOW - timedelta(days=300)), -1, -1]
dead[PH.CSV_NEW] = flat_csv(4250, 120)[PH.CSV_NEW]
lv = PH.from_product({"csv": dead}, now=NOW)
check("死んだ BuyBox は90日の母数に入らない", lv.median90, 4250)
check("  採用した系列は新品最安", lv.source, "新品最安")

print("\n4. 2本あるときは安い側（高いほうを採ると赤字を黒字と報告する）")
both = [[] for _ in range(20)]
both[PH.CSV_BUYBOX] = flat_csv(3400, 120, PH.CSV_BUYBOX)[PH.CSV_BUYBOX]
both[PH.CSV_NEW] = flat_csv(5897, 120)[PH.CSV_NEW]
lv = PH.from_product({"csv": both}, now=NOW)
check("安い側（BuyBox 3,400）を採る", lv.median90, 3400)
check("  高い側も理由文に残す", "5,897" in lv.source, True)

print("\n5. 下落トレンドは落とす／高値は中央値で見る")
down = [[] for _ in range(20)]
raw = []
for d in range(90, -1, -3):
    raw += [kminute(NOW - timedelta(days=d)), int(2000 - (90 - d) * 6)]
down[PH.CSV_NEW] = raw
lv = PH.from_product({"csv": down}, now=NOW)
check("90日で右肩下がりなら下落トレンド", lv.verdict, "下落トレンド")
check("  傾きは負", lv.slope_pct_per_30d < 0, True)

spike = [[] for _ in range(20)]
raw = [kminute(NOW - timedelta(days=d)) for d in ()]
raw = []
for d in range(90, 5, -3):
    raw += [kminute(NOW - timedelta(days=d)), 1000]
raw += [kminute(NOW - timedelta(days=2)), 2000]
spike[PH.CSV_NEW] = raw
lv = PH.from_product({"csv": spike}, now=NOW)
check("いまだけ高い行は『高値』", lv.verdict, "高値")
check("  採算は中央値 1,000円で見る", lv.sell_for_profit, 1000)

print("\n6. 人が実画面で見た値は機械より強い（§3.3-16）")
lv = PH.from_product({"csv": flat_csv(1991, 200)}, screen_price=1300, now=NOW)
check("採算の売価は実画面の値", lv.sell_for_profit, 1300)
check("  悲観も実画面以下", lv.sell_pessimistic <= 1300, True)
check("  食い違いを列に残す", "食い違" in lv.disagreement, True)

print("\n7. カレンダー")
T = date(2026, 10, 4)          # 日曜
p = SC.build(T, channel="NETSEA", months_to_sell=3.0)
check("発注日は今日", p.order_on, T)
check("着荷は発注より後", p.arrives_on > T, True)
check("FBA納品完了は着荷より後", p.fba_ready_on > p.arrives_on, True)
check("ゲート無しなら販売開始＝FBA納品完了", p.listing_starts_on, p.fba_ready_on)
g = SC.build(T, channel="NETSEA", months_to_sell=3.0, gate_needed=True)
check("ゲート申請が要ると販売開始が後ろへ", g.listing_starts_on > p.listing_starts_on, True)
check("営業日計算は土日を飛ばす", SC.add_bdays(date(2026, 10, 2), 1), date(2026, 10, 5))

print("\n8. 🔴 季節の窓（ピークを過ぎる候補は落とす）")
w = SC.build(T, channel="NETSEA", months_to_sell=3.0,
             peak_months=(11, 12, 1), season_verdict="季節")
check("11〜1月ピークはいま買えば間に合う", w.season_window, SC.IN_WINDOW)
s = SC.build(T, channel="NETSEA", months_to_sell=3.0,
             peak_months=(3, 4, 5), season_verdict="季節")
check("3〜5月ピークはいま買うと半年寝る", s.season_window, SC.MISSED)
d = SC.build(T, channel="NETSEA", months_to_sell=3.0,
             peak_months=(6,), season_verdict="通年低調")
check("通年低調は×", d.season_window, SC.MISSED)
a = SC.build(T, channel="NETSEA", months_to_sell=3.0, season_verdict="通年")
check("通年の棚は季節で落とさない", a.season_window, SC.NO_SEASON)
check("  推定で埋めた前提を列に出す", any("推定" in x for x in a.assumed), True)

print("\n全部 ok" if not NG else f"\nNG {NG}件")
raise SystemExit(1 if NG else 0)
