#!/usr/bin/env python3
"""まとめ売り突合のテスト（**ネットワーク0・シート0**）。

固定したいのは次の4つです。
1. JAN 1本に対して**セット品 ASIN を全部拾う**（`_pick_best` に戻らない）
2. セット数は**商品名 × packageQuantity の2本**で決め、食い違ったら UNKNOWN（大きい方で計算）
3. 必要売価は **区分別の実費だけ**で解く（2026-10-04 に「固定費821円」を撤去）
4. 取引条件の表が**読めない**ことを「載っていない」と混ぜない

実データは 2026-10-01 に Keepa から取った旭化成 ズビズバ あみたわし（JAN 4901670106107）の
10 ASIN をそのまま使います。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import set_family as sf          # noqa: E402
import trading_terms as tt       # noqa: E402

ok = fail = 0


def check(cond, label):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok {label}")
    else:
        fail += 1
        print(f"  NG {label}")


def eq(got, want, label):
    check(got == want, f"{label}（got={got!r} want={want!r}）")


# ── 実データ（2026-10-01 Keepa `code=4901670106107`・10 ASIN）────────────────
# 卸側は SD で「1点」「×10点」「×200点」が**すべて同じ JAN**。
FAMILY = [
    {"asin": "B00SB63MCI", "packageQuantity": 200, "numberOfItems": -1,
     "title": "旭化成　ズビズバサラッシュ 立体タイプ 隅々まで洗えるあみたわし ×２００個セット",
     "stats": {"current": [43000, 43000, -1, -1], "avg90": [0, 0, 0, -1]},
     "referralFeePercent": 10.0, "fbaFees": {"pickAndPackFee": 781}},
    {"asin": "B06Y5JXM87", "packageQuantity": 10, "numberOfItems": -1,
     "title": "ズビズバ　サラッシュ　立体タイプ　隅々まで洗えるあみたわし × 10個セット",
     "stats": {"current": [2576, 2576, -1, 150000], "avg90": [0, 0, 0, 213252]},
     "referralFeePercent": 10.0, "fbaFees": {"pickAndPackFee": 425}},
    {"asin": "B01MCR1XMK", "packageQuantity": 3, "numberOfItems": 1,
     "title": "ズビズバ　サラッシュ　立体タイプ　隅々まで洗えるあみたわし × 3個セット",
     "stats": {"current": [980, 980, -1, 147161], "avg90": [0, 0, 0, 147161]},
     "referralFeePercent": 8.0, "fbaFees": {"pickAndPackFee": 318}},
    {"asin": "B00H2E0JLW", "packageQuantity": 1, "numberOfItems": 2,
     "title": "ズビズバ サラッシュ立体タイプ 2個セット", "monthlySold": 50,
     "stats": {"current": [700, 700, -1, 42290], "avg90": [0, 0, 0, 42290]},
     "referralFeePercent": 5.0, "fbaFees": {"pickAndPackFee": 252}},
    {"asin": "B0052T0CE8", "packageQuantity": 1, "numberOfItems": 1,
     "title": "旭化成ホームプロダクツ ズビズバ サラッシュ立体タイプ 隅々まで洗えるあみたわし",
     "monthlySold": 100, "parentAsin": "B0GV1Y3C38",
     "variations": [{"asin": "B0VARIATION1"}, {"asin": "B0052T0CE8"}],
     "stats": {"current": [330, 330, -1, 17944], "avg90": [0, 0, 0, 17944]},
     "referralFeePercent": 9.0, "fbaFees": {"pickAndPackFee": 222}},
    {"asin": "B01LWLJY84", "packageQuantity": 1, "numberOfItems": 1,
     "title": "ズビズバ サラッシュ立体タイプ 隅々まで洗えるあみたわし",
     "stats": {"current": [-1, -1, -1, 650407], "avg90": [0, 0, 0, 650407]},
     "referralFeePercent": 6.0, "fbaFees": {"pickAndPackFee": 252}},
]


print("1. JAN 1本からセット品 ASIN を全部拾う")
members = sf.family_members(FAMILY)
eq(len(members), 6, "6口すべてを Member にする（1件に絞らない）")
eq([m.set_count.n for m in members], [200, 10, 3, 2, 1, 1], "大きい口から並べる")
eq(sf.extra_asins(FAMILY), ["B0GV1Y3C38", "B0VARIATION1"],
   "parentAsin と variations も同じレスポンスから拾える（追加トークン0）")

print("\n2. セット数は商品名 × packageQuantity の2本で決める")
eq(sf.resolve("あみたわし × 10個セット", 10, -1).confidence, sf.CONFIRMED, "2本一致で確定")
eq(sf.resolve("あみたわし × 10個セット", 10, -1).n, 10, "確定したら倍率を返す")
c = sf.resolve("ズビズバ 2個セット", 1, 2)
eq(c.confidence, sf.CONFLICT, "商品名2・pq1 は不一致")
eq(c.n, 2, "不一致なら**大きい方**で計算する（原価を安く見積もらない）")
check(not c.is_decided(), "不一致は GO に進めない（人が両方の画面を見る）")
eq(sf.resolve("あみたわし × 3個セット", 3, 1).confidence, sf.CONFIRMED,
   "numberOfItems=1 は多数決に使わない（1 が既定値として入る実例がある）")
c = sf.resolve("あみたわし", 0, -1)
eq(c.n, 1, "pq=0/-1 は『データなし』。商品名だけで単品と読む")
eq(c.confidence, sf.SINGLE, "情報源が1本なら単独")
check(c.is_decided(), "単独でも n=1（単品）は進めてよい")
c = sf.resolve("お得セット まとめ買い", -1, -1)
eq(c.n, None, "セットらしいが個数が読めない → None")
check(not c.is_decided(), "読めなければ UNKNOWN（1 とも N とも決め打たない）")
c = sf.resolve("カップ麺 110g、18食入り", 18, -1)
eq(c.n, 18, "pq が 18 なら『18食入り』の曖昧さが解ける")
eq(c.confidence, sf.SINGLE, "商品名側は曖昧で読めないので情報源は1本")
check(not c.is_decided(), "n>1 の単独は GO にしない（10/01 の ▲778円/個 の型）")
eq(sf.resolve("×200個セット", 200, -1).n, 200,
   "pq は 1000 まで受ける（商品名側の上限60で大口を切り落とさない）")
eq(sf.resolve("あみたわし", 99999, -1).confidence, sf.SINGLE,
   "pq が上限超なら読まない（商品名だけが残る）")

print("\n3. 必要売価（区分別の実費だけ。誤差幅は入れない）")
# 🔴 旧テストは「卸178円の単品は売価1,214円ないと駄目」を固定していました。
# **その1,214円が間違い**でした（固定費821円の内訳のうち470円が架空・成果物33）。
# 正しい損益分岐は約514円です。**単品でも成立します。**
eq(round(sf.required_sell(178, 1)), 514, "卸178円の単品の損益分岐は約514円（旧1,214円）")
t = dict((n, (s, per)) for n, s, per in sf.required_sell_table(178))
check(t[1][1] > t[2][1] > t[5][1] > t[10][1] > t[20][1],
      "n を増やすと1点あたりは下がる（ただし下がるのは FBA配送代行と外注費のぶんだけ）")
check(t[10][0] < 1214 * 10,
      "まとめ売りの必要売価も旧モデルより安い（固定費821円が誤りだったので全体が下がる）")
eq(sf.min_profitable_set_count(178, 300), 12, "1点300円で売れる棚なら12点セットから黒字")
eq(sf.min_profitable_set_count(178, 50), None, "1点50円では何点まとめても黒字にならない")
# 実額を渡す口は「カテゴリー」と「Keepa の実測率」に変わりました（FBA は区分から引く）。
eq(sf.required_sell(178, 1, category="エレクトロニクス"),
   sf.required_sell(178, 1, category="エレクトロニクス"), "カテゴリーを渡せる（既定に固定しない）")
check(sf.required_sell(178, 1, category="ホーム&キッチン")
      >= sf.required_sell(178, 1, category="エレクトロニクス"),
      "料率が高いカテゴリーほど必要売価が高い（15.4% ≥ 8.4%）")
check(sf.required_sell(178, 1, tier="標準7") > sf.required_sell(178, 1, tier="小型"),
      "大きい区分ほど必要売価が高い（固定費は区分で決まる）")

print("\n4. 卸の口を選ぶ")
mouths = [sf.Mouth("S1", 1, 178, "1点"), sf.Mouth("S2", 10, 160, "×10点"),
          sf.Mouth("S3", 100, 150, "×100点"), sf.Mouth("S4", None, 120, "入り数不明")]
ch = sf.pick_mouth(mouths, needed_points=10, amazon_set_count=10)
eq(ch.mouth.code, "S3", "1点あたりが最も安い口を選ぶ")
eq(ch.points_to_buy, 100, "1口100点なので100点買う")
eq(ch.amazon_units, 10, "Amazon の1個が卸10点なので10個ぶん")
ch = sf.pick_mouth([sf.Mouth("S4", None, 120, "?")], 10, 1)
check(ch.mouth is None, "入り数が読めない口しか無ければ選ばない（1 と決め打たない）")
ch = sf.pick_mouth([sf.Mouth("S1", 10, 160, "×10点")], needed_points=15, amazon_set_count=1)
eq(ch.sets_to_order, 2, "15点なら1口10点を2セット")
eq(ch.leftover_points, 5, "余り5点を正直に出す")

print("\n5. 取引条件の表（『読めない』を『載っていない』と混ぜない）")
table = {"by_id": {"1000196": {"dealer_id": "1000196", "name": "オクムラ",
                              "verdict_raw": "○", "verdict": tt.OK}},
         "by_name": {tt.normalize("オクムラ"): {"name": "オクムラ", "verdict_raw": "○",
                                              "verdict": tt.OK}},
         "counts": {}, "total": 1}
eq(tt.gate("sd_lookup", "株式会社オクムラ", table=table)[0], "PASS", "○ なら PASS（法人格は無視）")
eq(tt.gate("sd_lookup", "知らない会社", table=table)[0], "UNKNOWN",
   "SD 由来で表に無ければ UNKNOWN（○ に畳まない）")
eq(tt.gate("discover/netsea", "知らない会社", table=table)[0], "PASS",
   "NETSEA 由来はこの表の対象外（載っていないことを × と読まない）")
bad = {"by_id": {}, "by_name": {}, "counts": {}, "total": 0, "unavailable": "読めません"}
eq(tt.gate("sd_lookup", "オクムラ", table=bad)[0], "UNKNOWN",
   "表が読めない晩に全件 ○ 扱いで走らない")
eq(tt.classify("×（Amazon名指し不可またはネット販売不可）"), tt.NG, "× は NG")
eq(tt.classify("要確認（△・モール名を要確認）"), tt.NEEDS_CHECK, "△ は要確認")
eq(tt.classify("不明（ネット販売の記載なし）"), tt.NEEDS_CHECK, "記載なしを ○ に畳まない")
eq(tt.classify(""), tt.NEEDS_CHECK, "空欄を ○ に畳まない")
eq(tt.classify("○"), tt.OK, "○ は OK")

print("\n6. SD の卸価格は「1点あたり / 1セットあたり」を書かないと取り込まない")
import superdelivery as sd      # noqa: E402


def _row(code, units=None):
    return sd.SDSet(sd_code=code, product_id="13681795", units_per_set=units)


rows = [_row("A1", 1), _row("A2", 10), _row("A3", 10), _row("A4"), _row("A5", 3)]
sd.merge_wholesale(rows, {
    "A1": {"卸価格": 178, "価格の単位": "1点あたり"},
    "A2": {"卸価格": 1600, "価格の単位": "1セットあたり", "入り数": 10},
    "A3": {"卸価格": 1600},                                   # 単位なし
    "A4": {"卸価格": 1600, "価格の単位": "1セットあたり"},      # 入り数なし
    "A5": {"卸価格": 1000, "価格の単位": "1セットあたり", "入り数": 3},
})
got = {r.sd_code: r.wholesale_price_excl for r in rows}
eq(got["A1"], 178, "1点あたりはそのまま")
eq(got["A2"], 160, "1セット10点1,600円 → 1点160円")
eq(got["A3"], None, "`価格の単位` が無い行は取り込まない（推測しない）")
eq(got["A4"], None, "1セットあたりなのに入り数が無ければ取り込まない")
eq(got["A5"], 334, "割り切れないときは**切り上げ**（原価を安く見積もらない）")
check(any("価格の単位" in n for n in next(r for r in rows if r.sd_code == "A3").notes),
      "取り込まなかった理由が notes に残る（黙って空にしない）")

print("\n7. この家族の各口が必要売価に届くかを確かめる")
# 卸178円/点（税抜）と仮定。実在する口の売価と必要売価を突き合わせる。
# 🔴 旧テストの見出しは「単品では黒字にならないことを確かめる」でした。
# **その前提は取り下げました。**単品の損益分岐は514円で、売価330円の口が届かないのは
# 「単品だから」ではなく「330円では固定費（FBA222円＋その他63円）を割れないから」です。
for m in members:
    if not m.sell or m.set_count.n is None:
        continue
    need = sf.required_sell(178, m.set_count.n, keepa_pct=m.fee_pct)
    print(f"  {m.asin} n={m.set_count.n:>3} 売価{m.sell:>6,}円 / 必要{int(need):>6,}円 "
          f"→ {'黒字' if m.sell >= need else '届かない'}")
single = next(m for m in members if m.asin == "B0052T0CE8")
need1 = sf.required_sell(178, 1, keepa_pct=single.fee_pct)
check(single.sell < need1, "売価330円の単品は必要売価（約514円）に届かない")
check(need1 < 1214, "ただし必要売価は旧モデルの1,214円ではない（470円が架空だった）")

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
