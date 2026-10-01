#!/usr/bin/env python3
"""季節判定のテスト（**ネットワーク0・シート0**）。

固定したいのは3つ。
1. 「年間を通して低調（死）」と「今が季節外」を**ランク履歴で区別する**
2. ピークが **11〜1月**なら NO-GO にしない（UNKNOWN に残す）。春夏ピークは NO-GO でよい
3. **キーワードはゲートを動かさない**（並べ替え専用）

実例は 2026-10-01 に SD レーンAで当てたナガクラ 栽培キット（B001LOOR4E・春物・3か月0個・
レビュー153件）と、社長が持っている鍋（11〜1月の棚）。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "24_カート保持者ガード"))

import candidate_pipeline as CP   # noqa: E402
import seasonality as S           # noqa: E402

ok = fail = 0


def check(c, label):
    global ok, fail
    if c:
        ok += 1
        print(f"  ok {label}")
    else:
        fail += 1
        print(f"  NG {label}")


def eq(got, want, label):
    check(got == want, f"{label}（got={got!r} want={want!r}）")


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def to_keepa_min(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - S.KEEPA_EPOCH_OFFSET_MIN


def history(month_ranks: dict[int, int], years: int = 2) -> list[int]:
    """`{月: ランク}` から Keepa の csv[3] 形式を作る。月ごとに4点ずつ、2年ぶん。"""
    out: list[int] = []
    for y in range(years):
        for m, rank in month_ranks.items():
            for d in (3, 10, 17, 24):
                # NOW から過去へさかのぼって、その月の日付を作る
                year = NOW.year - 1 - y if m > NOW.month else NOW.year - y
                t = datetime(year, m, d, tzinfo=timezone.utc)
                if t >= NOW:
                    continue
                out += [to_keepa_min(t), rank]
    return out


print("1. 時刻の変換（Keepa の分 → 日付）")
t = S._to_dt(to_keepa_min(datetime(2026, 3, 15, tzinfo=timezone.utc)))
eq((t.year, t.month, t.day), (2026, 3, 15), "往復して同じ日付に戻る")
eq(S.parse_rank_history([to_keepa_min(NOW - timedelta(days=10)), -1], now=NOW), [],
   "値 -1（欠測）は捨てる")
eq(len(S.parse_rank_history(
    [to_keepa_min(NOW - timedelta(days=2000)), 100,
     to_keepa_min(NOW - timedelta(days=10)), 200], days=730, now=NOW)), 1,
   "2年より古い点は捨てる")

print("\n2. 通年低調（＝本当に死んでいる）")
dead = S.classify(history({m: 1_400_000 for m in range(1, 13)}), now=NOW)
eq(dead.verdict, S.DEAD, "どの月も圏外なら通年低調")
check(not dead.peaks_in_target(), "通年低調は『いま狙う月』に当てない")
check("最良月でも" in dead.label(), "ラベルに最良月を出す（最悪月だと読み違える）")

print("\n3. 🔴 春物（栽培キット B001LOOR4E 型）— 今が季節外でも『死』ではない")
spring = S.classify(history({1: 60_000, 2: 40_000, 3: 8_000, 4: 5_000, 5: 9_000,
                             6: 30_000, 7: 200_000, 8: 260_000, 9: 240_000,
                             10: 150_000, 11: 90_000, 12: 70_000}), now=NOW)
eq(spring.verdict, S.SEASONAL, "振れ幅が大きければ季節商品と判る")
eq(spring.peak_months, (3, 4, 5), "ピークは3〜5月（春物・肩の月まで含める）")
check(not spring.peaks_in_target(), "ピークが春なので『いま狙う月』ではない")
st, sr = CP.liveness_status(None, 240_000, 600_000, spring)
eq(st, CP.FAIL, "春ピークは NO-GO でよい（いま仕入れると半年寝かせる）")
check("3月・4月・5月" in sr, "理由にピーク月を書く")
eq(S.order_key(spring, "リトルガーデン・プロ ミニトマト 栽培キット"), 5,
   "春物は並べ替えで最後")

print("\n4. 🔴 冬物（社長の鍋 型）— 3か月0個でも UNKNOWN に残す")
winter = S.classify(history({1: 9_000, 2: 40_000, 3: 120_000, 4: 300_000, 5: 400_000,
                             6: 450_000, 7: 480_000, 8: 420_000, 9: 200_000,
                             10: 60_000, 11: 12_000, 12: 7_000}), now=NOW)
eq(winter.verdict, S.SEASONAL, "冬物も季節商品と判る")
eq(winter.peak_months, (1, 11, 12), "ピークは11・12・1月")
check(winter.peaks_in_target(), "『いま狙う月』に当たる")
st, sr = CP.liveness_status(None, 60_000, 600_000, winter)
eq(st, CP.UNKNOWN, "🔴 冬ピークは NO-GO にしない（UNKNOWN に残す）")
check("今が季節外だから" in sr, "理由に『今が季節外』と書く")
check("11〜1月" in sr, "理由に『いま仕入れて売る月』と書く")
eq(S.order_key(winter, "燕三 よせしゃぶ鍋"), 0, "履歴で裏の取れた冬物は最優先")

print("\n5. 履歴が足りないときは『通年』とも『季節』とも書かない")
thin = S.classify(history({10: 5_000, 11: 6_000}), now=NOW)
eq(thin.verdict, S.UNKNOWN_SEASON, "月が6本埋まらなければ判定不能")
st, _ = CP.liveness_status(None, 600_000, 600_000, thin)
eq(st, CP.FAIL, "判定不能では救済しない（UNKNOWN を GO 方向に畳まない）")
eq(S.from_product({}).verdict, S.UNKNOWN_SEASON, "csv が無ければ判定不能")
check("history=1" in S.from_product({}).reason, "取り直し方を理由に書く")

print("\n6. 通年商品")
allyear = S.classify(history({m: 20_000 + m * 500 for m in range(1, 13)}), now=NOW)
eq(allyear.verdict, S.ALL_YEAR, "振れ幅が小さければ通年")
eq(S.order_key(allyear, "ステンレスタンブラー"), 2, "通年＋通年名は中位")
eq(S.order_key(allyear, "電気毛布 あったか"), 1, "通年＋冬物名は上位")

print("\n7. 🔴 キーワードはゲートを動かさない（並べ替え専用）")
st_kw, _ = CP.liveness_status(None, 600_000, 600_000, None)
eq(st_kw, CP.FAIL, "季節が None（未判定）なら従来どおり NO-GO")
eq(S.season_hint("鍋 土鍋 おでん"), "冬", "冬物の語")
eq(S.season_hint("栽培キット プランター"), "春", "春物の語")
eq(S.season_hint("冷感 ひざ掛け 電気毛布"), "不明",
   "夏と冬の両方に当たったら『不明』（片方を黙って採らない）")
eq(S.season_hint("ただのボールペン"), "不明", "当たらなければ不明")
eq(S.order_key(None, None), 3, "材料が何も無ければ中位より下（春夏より前）")

print("\n8. 生存ゲートの既存の挙動は壊していない")
eq(CP.liveness_status(50, None, None, None)[0], CP.PASS, "月販があれば PASS")
eq(CP.liveness_status(None, 20_000, 24_150, None)[0], CP.PASS, "10万位以内は PASS")
eq(CP.liveness_status(None, None, 300_000, None)[0], CP.UNKNOWN, "10万〜50万は UNKNOWN")
eq(CP.liveness_status(None, None, None, None)[0], CP.UNKNOWN, "ランクが無ければ UNKNOWN")

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
