#!/usr/bin/env python3
"""T-20260912-004 2周目 — 12ヶ月分布を「成立社数」から引き直す（送信ブロック A/B/C）。
マサル 01_mc_案B.py の段（波→返信→見積→成立→ゲート確約→販売開始→取り分）を簡略に踏襲。
乱数固定。金額は円。月0=2026-09（後半）、月12=2027-09。
"""
import math, random, statistics as st

SEED = 20260913
N = 12000
DAY_M = 30.4
MONTHS = 13

# ---- 共通の置き値（中央／楽観／悲観） ----
V = dict(
    C=dict(est=.03, sku_per=2.0, share=1.0, excl=.25, gate=.60, consume=.80, oem=.15, oem_rev=5e4),
    O=dict(est=.05, sku_per=3.0, share=1.5, excl=.40, gate=.80, consume=1.0, oem=.30, oem_rev=1e5),
    P=dict(est=.015, sku_per=1.0, share=0.3, excl=.10, gate=.40, consume=.50, oem=.05, oem_rev=1e4),
)
X = dict(
    reply=.25, quote=.35,          # 前向き返信・見積到達（成立は est で直接引く。返信は情報のみ）
    gated=.70, confirm=.80,        # ゲートあり×確約 → 0.86
    low_regime=.20,                # 低稼働（消化率×0.35・滞留50%）。マサル30%→社長の意思表明で20%（推測）
    stall=.20,
    ainori_rev=3e4, excl_rev=7e4, price_drift=-.004, entry6=.8,
    amino_slip=.20, fallback_quick=.40, sd_pass=.50, oem_dud=.30,
    brand_reg=.40,                 # 成立社のうちブランド登録あり（S-d 未反映・推測）。無い社は独占が3手目で崩れる40%
    accident=.15,
)
FIXED = 14000
MARGIN = dict(amino=.08, oroshi=.06, ainori=.12, excl=.25, oem=.30, fallback=.00)

# 送信ブロック（週あたり）→ 月別の波（社数）。母数上限（中央/楽観/悲観）
PLANS = {
    "A 週5通":  dict(waves=[4, 10, 15, 15, 15, 18, 18, 18, 18, 18, 18, 18], pool=(470, 600, 300)),
    "B 週10通": dict(waves=[4, 20, 30, 30, 30, 35, 35, 35, 35, 35, 35, 35], pool=(470, 600, 300)),
    "C 週20通": dict(waves=[4, 20, 40, 60, 60, 70, 70, 70, 70, 70, 70, 70], pool=(470, 600, 300)),
    "M マサル1周目": dict(waves=[4, 10, 0, 15, 10, 10, 10, 10, 10, 10, 10, 10], pool=(470, 600, 300)),
}

def run(plan, v, R, pool_idx):
    tri = lambda a, m, b: R.triangular(a, b, m)
    logn = lambda med, sig: med * math.exp(R.gauss(0, sig))
    u = R.random(); m = 2.0 if u < .2 else (1.0 if u < .8 else .4)   # 成立率の共通倍率
    halt = set()
    if R.random() < X["accident"]:
        t = R.randrange(0, 12); halt.update([t, t + 1])
    low = R.random() < X["low_regime"]
    stall_p = .5 if low else X["stall"]; consume = v["consume"] * (.35 if low else 1.0)
    pool = plan["pool"][pool_idx] * (1.0 if not low else 1.0)
    # 送信
    pending = 0.0; sends = []; sent_total = 0
    for mo in range(12):
        pending += plan["waves"][mo]
        if R.random() < stall_p or mo in halt:
            continue
        k = min(int(round(pending * consume)), int(pending), int(pool) - sent_total)
        if k <= 0: continue
        for _ in range(k): sends.append(mo * DAY_M + R.uniform(0, DAY_M))
        pending -= k; sent_total += k
    firms = []; n_quote = 0
    for s in sends:
        if R.random() < X["reply"] and R.random() < X["quote"]: n_quote += 1
        if R.random() >= min(1, v["est"] * m): continue
        if R.random() < X["gated"] and R.random() >= X["confirm"]: continue
        r = s + tri(3, 7, 21) + (5 if s < 9 else 0)
        o = r + tri(7, 14, 30); d = o + tri(5, 10, 30)
        fs = d + tri(7, 14, 21)
        fm = fs / DAY_M
        while int(fm) in halt: fm += 1.0
        k = max(1, int(round(logn(v["sku_per"], .45))))
        units = [logn(X["ainori_rev"], .5) * v["share"] for _ in range(k)]
        # 独占：取引3ヶ月後に提案。ブランド登録なしは40%で崩れる
        excl = None
        if R.random() < v["excl"]:
            em = fm + 3 + tri(1, 2, 4)
            if R.random() < X["brand_reg"] or R.random() >= .40: excl = em
        oem = None
        pm = max(5.0, fm + 1)
        if pm < 11 and R.random() < v["oem"]:
            oem = dict(start=pm + tri(60, 90, 150) / DAY_M,
                       rev=logn(v["oem_rev"], .8) * (0.1 if R.random() < X["oem_dud"] else 1.0))
        firms.append(dict(fm=fm, units=units, excl=excl, oem=oem, est_day=d))
    # 卸レーン
    amino_ok = R.random() < v["gate"]
    amino_start = (1.3 + (0.7 if R.random() < X["amino_slip"] else 0)) if amino_ok else None
    fallback_start = None if amino_ok else (1.5 if R.random() < X["fallback_quick"] else 2.5)
    sd_n = ((R.random() < .7) + (R.random() < .4) + (R.random() < .2)) if R.random() < X["sd_pass"] else 0
    oroshi = []
    if amino_start is not None: oroshi.append((amino_start, logn(5e3, .4), MARGIN["amino"]))
    if fallback_start is not None: oroshi.append((fallback_start, logn(4e3, .4), MARGIN["fallback"]))
    for _ in range(sd_n): oroshi.append((3.5 + tri(0, 1, 3), logn(1.5e4, .5), MARGIN["oroshi"]))
    # 月次
    rev = [0.0] * MONTHS; sku = [0] * MONTHS; prof = [0.0] * MONTHS; est_cum = [0] * MONTHS
    cash = 1e5; cum = 0.0; first_list = None
    n_est_by = lambda mo: sum(1 for f in firms if f["est_day"] <= (mo + 1) * DAY_M)
    sprite_on = False
    for mo in range(MONTHS):
        est_cum[mo] = n_est_by(mo)
        if est_cum[mo] >= 2: sprite_on = True
        fixed = FIXED + (13998 if sprite_on else 0)
        lr = 0.0; lp = 0.0; n = 0
        if mo not in halt:
            for s0, unit, mg in oroshi:
                if mo >= s0:
                    n += 1; rv = unit * (0.5 if mo < s0 + 1 else 1.0); lr += rv; lp += rv * mg
                    if first_list is None: first_list = s0
            for f in firms:
                fm = f["fm"]
                if mo < fm: continue
                if first_list is None or fm < first_list: first_list = fm
                exon = f["excl"] is not None and mo >= f["excl"]
                for unit in f["units"]:
                    n += 1
                    if exon:
                        rv = logn(X["excl_rev"], .15) * (unit / X["ainori_rev"]) ** .3; mg = MARGIN["excl"]
                    else:
                        rv = unit * (0.5 if mo < fm + 1 else 1.0) * (1 + X["price_drift"]) ** max(0, mo - fm) \
                             * (X["entry6"] if mo >= fm + 6 else 1.0); mg = MARGIN["ainori"]
                    lr += rv; lp += rv * mg
                o = f["oem"]
                if o and mo >= o["start"]:
                    n += 1; rv = o["rev"] * (0.5 if mo < o["start"] + 1 else 1.0); lr += rv; lp += rv * MARGIN["oem"]
        # 資本キャップ：成立3社以上で2周目30万・3周目100万（条件付き）
        cap_inj = 1e5 + (3e5 if (est_cum[mo] >= 3 and mo >= 3) else 0) + (1e6 if (est_cum[mo] >= 3 and mo >= 8) else 0)
        cap = max(0.0, cap_inj + cum) * 1.2
        if lr > cap and lr > 0:
            sc = cap / lr; lr *= sc; lp *= sc
        p = lp - fixed
        rev[mo] = lr; sku[mo] = n; prof[mo] = p; cum += lp
    return dict(rev12=rev[12], sku12=sku[12], est12=est_cum[12], est5=est_cum[5], est8=est_cum[8],
                sent=sent_total, quote=n_quote, first_list=first_list,
                pr12=(prof[12] / rev[12] if rev[12] > 0 else -1.0),
                lane_pr=(sum(prof[m] + FIXED for m in range(10, 13)) / max(1, sum(rev[10:13]))),
                cumprof=sum(prof), rev6=rev[6], rev3=rev[3], sku6=sku[6],
                low=low)

def q(xs, p): xs = sorted(xs); return xs[int(p * (len(xs) - 1))]

def summarize(name, res):
    r12 = [x["rev12"] for x in res]
    print(f"\n=== {name} ===")
    print(f"送信 累計 中央 {q([x['sent'] for x in res], .5):.0f} (P10 {q([x['sent'] for x in res], .1):.0f}〜P90 {q([x['sent'] for x in res], .9):.0f})")
    print(f"成立社数 12M 中央 {q([x['est12'] for x in res], .5):.0f} 平均 {st.mean(x['est12'] for x in res):.1f} P10 {q([x['est12'] for x in res], .1):.0f} P90 {q([x['est12'] for x in res], .9):.0f}")
    print(f"成立 月5(2027-02)≥2: {st.mean(x['est5'] >= 2 for x in res):.0%}  月8(2027-05)≥3: {st.mean(x['est8'] >= 3 for x in res):.0%}  12M≥3: {st.mean(x['est12'] >= 3 for x in res):.0%}  12M≥6: {st.mean(x['est12'] >= 6 for x in res):.0%}")
    print(f"月商 3M {q([x['rev3'] for x in res], .5)/1e4:.0f}万  6M {q([x['rev6'] for x in res], .5)/1e4:.0f}万  12M 中央 {q(r12, .5)/1e4:.0f}万 (P10 {q(r12,.1)/1e4:.0f}〜P90 {q(r12,.9)/1e4:.0f})  P(≥30万) {st.mean(x>=3e5 for x in r12):.0%} P(≥60万) {st.mean(x>=6e5 for x in r12):.0%} P(≥120万) {st.mean(x>=1.2e6 for x in r12):.0%}")
    print(f"SKU 6M {q([x['sku6'] for x in res], .5):.0f} 12M 中央 {q([x['sku12'] for x in res], .5):.0f} (P10 {q([x['sku12'] for x in res], .1):.0f}〜P90 {q([x['sku12'] for x in res], .9):.0f})")
    print(f"利益率 12M(固定費込み) 中央 {q([x['pr12'] for x in res], .5):+.0%}  レーン利益率(10〜12M) 中央 {q([x['lane_pr'] for x in res], .5):+.0%}  累計損益 中央 {q([x['cumprof'] for x in res], .5)/1e4:+.0f}万")
    fl = [x["first_list"] for x in res if x["first_list"] is not None]
    print(f"出品1件 ≤10/30: {st.mean((x['first_list'] is not None and x['first_list'] <= 1.55) for x in res):.0%}  見積 12/15までに≥2: —")

def main():
    for name, plan in PLANS.items():
        R = random.Random(SEED)
        res = [run(plan, V["C"], R, 0) for _ in range(N)]
        summarize(name + "（中央の置き値）", res)
    # 楽観・悲観（全変数を振る）
    for name in ["A 週5通", "B 週10通"]:
        for tag, key, pi in [("楽観", "O", 1), ("悲観", "P", 2)]:
            R = random.Random(SEED)
            res = [run(PLANS[name], V[key], R, pi) for _ in range(N // 2)]
            summarize(f"{name} {tag}", res)
    # 感応度（B・中央を1変数ずつ振る）
    print("\n=== 感応度（B 週10通・中央、1変数ずつ楽観／悲観）12M 月商 中央 ===")
    for var in ["est", "sku_per", "share", "consume", "excl", "gate"]:
        out = []
        for key in ["O", "P"]:
            v = dict(V["C"]); v[var] = V[key][var]
            R = random.Random(SEED)
            res = [run(PLANS["B 週10通"], v, R, 0) for _ in range(N // 2)]
            out.append(q([x["rev12"] for x in res], .5) / 1e4)
        print(f"{var:10s} 楽観 {out[0]:.0f}万 / 悲観 {out[1]:.0f}万  幅 {out[0]-out[1]:.0f}万")
    for lr in [.30, .10]:
        X["low_regime"] = lr
        R = random.Random(SEED)
        res = [run(PLANS["B 週10通"], V["C"], R, 0) for _ in range(N // 2)]
        print(f"low_regime={lr:.0%}  12M 月商 中央 {q([x['rev12'] for x in res], .5)/1e4:.0f}万  成立 中央 {q([x['est12'] for x in res], .5):.0f}")
    X["low_regime"] = .20
    for br in [.80, .20]:
        X["brand_reg"] = br
        R = random.Random(SEED)
        res = [run(PLANS["B 週10通"], V["C"], R, 0) for _ in range(N // 2)]
        print(f"brand_reg={br:.0%}  12M 月商 中央 {q([x['rev12'] for x in res], .5)/1e4:.0f}万")
    X["brand_reg"] = .40
    for pool in [(300, 600, 300), (700, 900, 400)]:
        PLANS["B 週10通"]["pool"] = pool
        R = random.Random(SEED)
        res = [run(PLANS["B 週10通"], V["C"], R, 0) for _ in range(N // 2)]
        print(f"pool={pool[0]}  12M 月商 中央 {q([x['rev12'] for x in res], .5)/1e4:.0f}万  送信 中央 {q([x['sent'] for x in res], .5):.0f}")

if __name__ == "__main__":
    main()
