#!/usr/bin/env python3
"""新条件①〜④を 32 SKU に当て、落ち方の内訳を出す。

Keepa の sellerId 履歴の約束事:
  "-1" = カートが誰にも付いていない / "-2" = カートが無効（資格なし）
  それ以外 = 実際にカートを取っていたセラーの ID
"""
import json, time

KEEPA_EPOCH_MIN = 21564000            # Keepa 時刻(分) → Unix 分 の差
NOW_KM = int(time.time() / 60) - KEEPA_EPOCH_MIN
DAY = 24 * 60

MIN_OBS_30 = 20        # ①-a これ未満は「判定不能」。落とすのでも通すのでもない
MIN_DROPS_30 = 10      # ①-b 実測で決めた足切り
BB_LAST_DAYS = 30      # ② 直近でカートが付いたか
BB_ABSENT_MAX = 0.30   # ③ 直近30日でカート不在の割合の上限

d = json.load(open("raw_32.json"))
target = "B0015L0RGK"


def obs30(p):
    sr = (p.get("csv") or [None] * 4)[3]
    if not sr: return 0
    ts = sr[0::2]
    return sum(1 for t in ts if t >= NOW_KM - 30 * DAY)


def bb(p):
    """カート履歴から (最後に実セラーが取った日数前, 直近30日の不在率) を返す。"""
    h = p.get("buyBoxSellerIdHistory") or []
    ts, ids = h[0::2], h[1::2]
    if not ts: return None, None
    last_real = None
    for t, sid in zip(ts, ids):
        if sid not in ("-1", "-2"):
            last_real = int(t)
    # 直近30日を1日刻みで走査し、その時点の保持者を引く
    cut = NOW_KM - 30 * DAY
    absent = total = 0
    for k in range(30):
        at = cut + k * DAY
        sid = None
        for t, s in zip(ts, ids):
            if int(t) <= at: sid = s
            else: break
        if sid is None: continue
        total += 1
        if sid in ("-1", "-2"): absent += 1
    return ((NOW_KM - last_real) / DAY if last_real else None,
            absent / total if total else None)


rows, reasons = [], {}
for p in d["products"]:
    s = p.get("stats") or {}
    n30, dr = obs30(p), s.get("salesRankDrops30")
    days, rate = bb(p)
    r = {"asin": p["asin"], "n30": n30, "d30": dr,
         "bb_last_days": days, "bb_absent": rate,
         "is_child": bool(p.get("parentAsin")) or (p.get("variationCount") or 0) > 1,
         "sold": p.get("monthlySold"), "offers": s.get("totalOfferCount")}
    fail = []
    if n30 < MIN_OBS_30:
        fail.append("①-a 観測回数不足（判定不能）")
    elif dr is None or dr < MIN_DROPS_30:
        fail.append(f"①-b ドロップ数が {MIN_DROPS_30} 未満")
    if days is None or days > BB_LAST_DAYS:
        fail.append("② カートが直近30日で一度も付いていない")
    if rate is None or rate > BB_ABSENT_MAX:
        fail.append("③ 直近30日のカート不在率が高い")
    if r["is_child"] and not r["sold"]:
        fail.append("④ バリエーションの子で、子単位の販売根拠がない")
    r["fail"] = fail
    rows.append(r)
    for f in fail:
        reasons[f] = reasons.get(f, 0) + 1

passed = [r for r in rows if not r["fail"]]
print(f"S5 通過 {len(rows)} 件 → 新条件で {len(passed)} 件が残った\n")
print("== どの条件で何件落ちたか（重複あり）==")
for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
    print(f"  {v:3d} 件  {k}")

print("\n== 単独で見た各条件の除去力 ==")
for lab, fn in [
        ("① ドロップ数の足切り（観測回数の判定込み）", lambda r: any(f.startswith("①") for f in r["fail"])),
        ("② カート最終獲得日", lambda r: any(f.startswith("②") for f in r["fail"])),
        ("③ カート不在率", lambda r: any(f.startswith("③") for f in r["fail"])),
        ("④ バリエーション子", lambda r: any(f.startswith("④") for f in r["fail"]))]:
    print(f"  {sum(1 for r in rows if fn(r)):3d} 件を落とす  {lab}")

print("\n== ①だけを当てた場合 / ②だけを当てた場合 ==")
only1 = [r for r in rows if not any(f.startswith("①") for f in r["fail"])]
only2 = [r for r in rows if not any(f.startswith("②") for f in r["fail"])]
print(f"  ①のみ → {len(only1)} 件が残る")
print(f"  ②のみ → {len(only2)} 件が残る")

t = [r for r in rows if r["asin"] == target]
print(f"\n== 失敗SKU（{target}）の判定 ==")
if not t:
    print("  32件の中にいません")
else:
    r = t[0]
    print("  落ちた" if r["fail"] else "  ★通ってしまった（条件が不十分）")
    for f in r["fail"]:
        print("   -", f)
    print(f"   参考: 観測回数30日={r['n30']} / カート最終獲得={r['bb_last_days'] and round(r['bb_last_days'])}日前 "
          f"/ 不在率={r['bb_absent'] and round(r['bb_absent'],2)} / 子ASIN={r['is_child']}")

json.dump(rows, open("backtest_result.json", "w"))
