"""T-20260912-005 仮想 PDCA 2周目 — 案B（送信ブロック A/B/C）の12ヶ月モンテカルロ（マサル）

1周目 `01_mc_案B.py` の段モデル（送信→返信→見積→成立→ゲート確約→販売開始→入金）を土台に、次を差し替えた。
  ・波: タケシ 2周目 `02_calc_2周目.py` の A 週5通／B 週10通／C 週20通（母数上限 470・楽観600・悲観300）
  ・資本: 成立3社以上で発動（12月〜30万・5月〜100万）。セラースプライト・商標: 成立2社以上で発動
  ・取り分: A 1.0倍固定（1周目）／B ファミリー別の経験分布（サトル05・n=68）／C 実測層のみ（n=24）
  ・成立率: 中央3%・悲観1.5%・楽観5%。「独立根拠2本では決められない」ので混合（1.5/3/5%）も回す
  ・ブランド登録: タケシ40% → サトル S-d（登録済み1・不明6・未登録9）で15%（推測）。未登録は A5 先行の分岐
  ・週20通の歩留まり低下: 累計300通超は成立率×0.6、週20通の下書き品質で×0.85（推測）
  ・撤退条件13本（タケシ §6）を中央／悲観／成立率1.5%で「踏む確率」と「発動時期」に翻訳
乱数固定。python3 02_mc_2周目.py [--fast]
"""
import random as R, math, sys, csv, os, statistics as st, time

SEED = 20260913
N_MAIN = 6000
N_SENS = 3000
if "--fast" in sys.argv:
    N_MAIN, N_SENS = 1500, 800
DAY_M = 30.4
MONTHS = 13
tri = lambda a, m, b: R.triangular(a, b, m)
logn = lambda med, sig: med * math.exp(R.gauss(0, sig))
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- サトル05 の実測倍率（対 3万円/SKU）を経験分布として読む ----
def load_multipliers():
    rows = list(csv.DictReader(open(os.path.join(HERE, "05_sa_asin別.csv"), encoding="utf-8-sig")))
    fam = {}
    meas = []; passed = []
    for r in rows:
        try: mult = float(r["倍率_対3万"])
        except (ValueError, KeyError): continue
        try: rank = float(r["ランク本体_現在"])
        except ValueError: rank = 9e9
        key = r["親ASIN"].strip() or r["ASIN"].strip()
        if key not in fam or rank < fam[key][0]: fam[key] = (rank, mult, r)
        if r["月販の層"].startswith("実測"): meas.append(mult)
    family = [v[1] for v in fam.values()]
    offers = [v[1] for v in fam.values() if v[2]["新品オファー数_COUNT_NEW"].strip() not in ("", "0", "0.0")]
    return family, meas, offers

FAMILY, MEASURED, OFFERS = load_multipliers()

# ---- 置き値（中央／楽観／悲観）: タケシ 2周目 §2-2 ----
V_C = dict(est=.03, sku_per=2.0, share=1.0, excl=.25, gate=.60, consume=.80, oem=.15, oem_rev=5e4, acc=.15, reply=.25)
V_O = dict(est=.05, sku_per=3.0, share=1.5, excl=.40, gate=.80, consume=1.0, oem=.30, oem_rev=1e5, acc=.05, reply=.35)
V_P = dict(est=.015, sku_per=1.0, share=0.3, excl=.10, gate=.40, consume=.50, oem=.05, oem_rev=1e4, acc=.30, reply=.12)

X0 = dict(
    stall=.20, low_regime=.30,      # マサル: 低稼働レジームは前科ベースで30%を据え置く（タケシ20%は感応度で示す）
    gated=.70, confirm=.80, quote=.35,
    amino_slip=.20, fallback_quick=.40, auto_fallback=True, sd_pass=.50,
    ainori_rev=3e4, excl_rev=7e4, price_drift=-.004, entry6=.80, oem_dud=.30,
    share_mode="fixed",             # fixed / family / measured / offers（ファミリー別・現在オファーあり）
    brand_reg=.15,                  # 成立社のブランド登録あり（S-d 反映・推測）
    a5_first=True,                  # 未登録社は A5（代理運用）を先に提案 → 独占は+3ヶ月遅れ・崩れ40%→15%（推測）
    cap_conditional=True, tools_conditional=True,
    oroshi_expand=True,             # 卸請求書でゲートが開いた後のブランド追加（1周目のまま）
    relax1=True,                    # 論点③ 4社案の並走（9/17〜）
    decay=False,                    # 週20通の歩留まり低下
    est_mix=None,                   # [(p, est), ...] 成立率の混合
    pool_idx=0,
)
PLANS = {
    "A": dict(waves=[4, 10, 15, 15, 15, 18, 18, 18, 18, 18, 18, 18], pool=(470, 600, 300)),
    "B": dict(waves=[4, 20, 30, 30, 30, 35, 35, 35, 35, 35, 35, 35], pool=(470, 600, 300)),
    "C": dict(waves=[4, 20, 40, 60, 60, 70, 70, 70, 70, 70, 70, 70], pool=(470, 600, 300)),
    "M": dict(waves=[4, 10, 0, 15, 10, 10, 10, 10, 10, 10, 10, 10], pool=(9999, 9999, 9999)),  # マサル1周目の波
}
FIXED = 14000
SPRITE = 13998
TRADEMARK = 44900
MARGIN = dict(amino=.08, oroshi=.06, ainori=.12, excl=.25, oem=.30, fallback=.00)


def draw_unit(v, x):
    """相乗り1 SKU の月商（円）"""
    m = x["share_mode"]
    if m == "fixed": return logn(x["ainori_rev"], .5) * v["share"]
    pool = FAMILY if m == "family" else (MEASURED if m == "measured" else OFFERS)
    return x["ainori_rev"] * R.choice(pool) * logn(1, .2) * (v["share"] if v["share"] != 1.0 else 1.0)


def one_trial(plan, v, x):
    waves = list(plan["waves"])
    if not x["relax1"]: waves[0], waves[4] = 0, waves[4] + 4
    pool = plan["pool"][x["pool_idx"]]
    est = v["est"]
    if x["est_mix"]:
        u = R.random(); acc = 0
        for p, e in x["est_mix"]:
            acc += p
            if u < acc: est = e; break
    u = R.random(); m = 2.0 if u < .2 else (1.0 if u < .8 else .4)
    halt = set()
    if R.random() < v["acc"]:
        t = R.randrange(0, 12); halt.update([t, t + 1])
        if R.random() < .3: halt.add(t + 2)
    low = R.random() < x["low_regime"]
    stall_p = .5 if low else x["stall"]; consume = v["consume"] * (.35 if low else 1.0)
    # ---- 送信 ----
    pending = 0.0; sends = []; sent_m = [0] * MONTHS
    for mo in range(12):
        pending += waves[mo]
        if R.random() < stall_p or mo in halt: continue
        k = min(int(round(pending * consume)), int(pending), pool - len(sends))
        if k <= 0: continue
        for _ in range(k): sends.append(mo * DAY_M + R.uniform(3, 25))
        pending -= k; sent_m[mo] = k
    sends.sort()
    cum_sent = [sum(sent_m[:mo + 1]) for mo in range(MONTHS)]
    # ---- 各社 ----
    firms = []; n_quote = 0; quote_by_1215 = 0; sent_by_1215 = sum(1 for s in sends if s <= 92)
    for idx, s in enumerate(sends):
        e = est
        if x["decay"]:
            if idx >= 300: e *= .6
            if max(waves) >= 60: e *= .85
        pos = R.random() < min(1, v["reply"] * m)
        q = pos and R.random() < x["quote"]
        if q:
            n_quote += 1
            if s + tri(3, 7, 21) <= 92: quote_by_1215 += 1
        if R.random() >= min(1, e * m): continue
        gated = R.random() < x["gated"]
        if gated and R.random() >= x["confirm"]: continue
        r = s + tri(3, 7, 21) + (5 if s < 9 else 0)
        o = r + tri(7, 14, 30); d = o + tri(5, 10, 30)
        if R.random() < .5: d += tri(3, 7, 14)
        est_day = d
        d += tri(7, 12, 21); fs = d + tri(1, 5, 20); pay = fs + tri(7, 14, 21)
        if R.random() < .08: fs += tri(30, 45, 90); pay += tri(30, 45, 90)
        while int(fs // DAY_M) in halt: fs += DAY_M; pay += DAY_M
        k = max(1, int(round(logn(v["sku_per"], .45))))
        f = dict(fs=fs, pay=pay, k=k, est_day=est_day, unit=[draw_unit(v, x) for _ in range(k)], excl=None, oem=None,
                 reg=R.random() < x["brand_reg"])
        fm = fs / DAY_M
        if R.random() < v["excl"]:
            em = fm + 4
            if not f["reg"]:
                if x["a5_first"]:
                    em += 3; collapse = .15
                else:
                    collapse = .40
                if R.random() < collapse: em = None
            if em is not None and em <= 12: f["excl"] = em
        pm = max(5.0, fm + 1)
        if pm < 11 and R.random() < v["oem"]:
            f["oem"] = dict(start=pm + tri(60, 90, 150) / DAY_M, lot=tri(3e4, 6e4, 1e5),
                            rev=logn(v["oem_rev"], .8) * (0.1 if R.random() < x["oem_dud"] else 1.0))
        firms.append(f)
    firms.sort(key=lambda f: f["est_day"])
    est_by = lambda day: sum(1 for f in firms if f["est_day"] <= day)
    # ---- 卸レーン ----
    amino_ok = R.random() < v["gate"]
    amino_start = (1.3 + (0.7 if R.random() < x["amino_slip"] else 0)) if amino_ok else None
    if amino_ok: fallback_start = None
    else:
        fq = x["fallback_quick"] if x["auto_fallback"] else x["fallback_quick"] * .4
        fallback_start = 1.5 if R.random() < fq else 2.5
    sd_n = ((R.random() < .7) + (R.random() < .4) + (R.random() < .2)) if R.random() < x["sd_pass"] else 0
    oroshi = []
    if amino_ok: oroshi.append((amino_start, 2.1e4 * logn(1, .3), MARGIN["amino"]))
    if fallback_start: oroshi.append((fallback_start, 0.6e4 * logn(1, .3), MARGIN["fallback"]))
    for i in range(sd_n): oroshi.append((3 + i * .7, 1.5e4 * logn(1, .5), MARGIN["oroshi"]))
    if amino_ok and x["oroshi_expand"]:
        mo = 3.5
        while mo < 12 and len(oroshi) < 20:
            for _ in range(1 + (R.random() < .5) + (R.random() < .25)):
                oroshi.append((mo, 1.5e4 * logn(1, .5), MARGIN["oroshi"]))
            mo += 2 + R.uniform(-.5, 1.0)
    # ---- 月次 ----
    rev = [0.0] * MONTHS; sku = [0] * MONTHS; prof = [0.0] * MONTHS; lane_pr = [0.0] * MONTHS
    cum_prof = 0.0; cum_lane = 0.0; oneoff_paid = 0.0; cash = [0.0] * MONTHS
    first_list = None; first_pay = None; sprite_on = False; tm_paid = False
    for mo in range(MONTHS):
        n_est = est_by((mo + 1) * DAY_M)
        if x["tools_conditional"]:
            if n_est >= 2: sprite_on = True
        else:
            sprite_on = mo >= 4
        fixed = FIXED + (SPRITE if sprite_on else 0)
        oneoff = 0.0
        if (x["tools_conditional"] and n_est >= 2 and not tm_paid) or (not x["tools_conditional"] and mo == 3 and not tm_paid):
            oneoff += TRADEMARK; tm_paid = True
        lanes_rev = 0.0; lanes_prof = 0.0; n_sku = 0
        if mo not in halt:
            for (s0, unit, mg) in oroshi:
                if mo >= s0:
                    rv = unit * (0.5 if mo < s0 + 1 else 1.0) * (1 + x["price_drift"]) ** max(0, mo - s0) * (x["entry6"] if mo >= s0 + 6 else 1.0)
                    lanes_rev += rv; lanes_prof += rv * mg; n_sku += 1
                    if first_list is None or s0 - .3 < first_list: first_list = s0 - .3
            for f in firms:
                fm = f["fs"] / DAY_M
                if mo >= fm:
                    if first_list is None or fm - .3 < first_list: first_list = fm - .3
                    if first_pay is None or f["pay"] < first_pay: first_pay = f["pay"]
                    ex = f["excl"] is not None and mo >= f["excl"]
                    for unit in f["unit"]:
                        if ex:
                            rv = logn(x["excl_rev"], .15) * (unit / x["ainori_rev"]) ** .3; mg = MARGIN["excl"]
                        else:
                            rv = unit * (0.5 if mo < fm + 1 else 1.0) * (1 + x["price_drift"]) ** max(0, mo - fm) * (x["entry6"] if mo >= fm + 6 else 1.0); mg = MARGIN["ainori"]
                        lanes_rev += rv; lanes_prof += rv * mg; n_sku += 1
                o = f["oem"]
                if o is not None:
                    if o["start"] - 1 <= mo < o["start"] and not o.get("paid"): oneoff += o["lot"]; o["paid"] = True
                    if mo >= o["start"]:
                        rv = o["rev"] * (0.5 if mo < o["start"] + 1 else 1.0); lanes_rev += rv; lanes_prof += rv * MARGIN["oem"]; n_sku += 1
        cap_inj = 1e5
        if x["cap_conditional"]:
            if n_est >= 3 and mo >= 3: cap_inj += 3e5
            if n_est >= 3 and mo >= 8: cap_inj += 1e6
        else:
            if mo >= 3: cap_inj += 3e5
            if mo >= 8: cap_inj += 1e6
        cap = max(0.0, cap_inj + cum_lane - oneoff_paid - oneoff) * 1.2
        if lanes_rev > cap and lanes_rev > 0:
            sc = cap / lanes_rev; lanes_rev *= sc; lanes_prof *= sc
        p = lanes_prof - fixed
        cum_prof += p; cum_lane += lanes_prof; oneoff_paid += oneoff
        rev[mo] = lanes_rev; sku[mo] = n_sku; prof[mo] = p; cash[mo] = cap_inj + cum_prof - oneoff_paid
        lane_pr[mo] = (lanes_prof / lanes_rev) if lanes_rev > 0 else 0.0
    # 最初の3 SKU の実測倍率（本丸のみ）
    first3 = []
    for f in sorted(firms, key=lambda f: f["fs"]):
        for u in f["unit"]:
            if len(first3) < 3: first3.append(u / x["ainori_rev"])
    # 送信計画比 50%未満が2ヶ月連続
    low2 = any(sent_m[i] < .5 * waves[i] and sent_m[i + 1] < .5 * waves[i + 1] for i in range(1, 11) if waves[i] > 0 and waves[i + 1] > 0)
    ev = dict(first_list=first_list, first_pay=first_pay, n_sent=len(sends), sent_by_1215=sent_by_1215, quote_by_1215=quote_by_1215,
              n_quote=n_quote, n_est=len(firms), est_m5=est_by(6 * DAY_M), est_m8=est_by(9 * DAY_M), est_m6_0315=est_by(182),
              cum_sent=cum_sent, halt=bool(halt), low=low, low2=low2, first3=first3, amino_ok=amino_ok,
              n_excl=sum(1 for f in firms if f["excl"] is not None), n_oem=sum(1 for f in firms if f["oem"] is not None and f["oem"]["start"] <= 12),
              n_reg=sum(1 for f in firms if f["reg"]), n_sold30=sum(f["k"] for f in firms if f["fs"] / DAY_M <= 11),
              est_days=[f["est_day"] for f in firms])
    return dict(rev=rev, sku=sku, prof=prof, cash=cash, lane_pr=lane_pr, ev=ev)


def pct(a, q):
    a = sorted(a); return a[max(0, min(len(a) - 1, int(q * len(a))))]


def run(plan, v, x, n, seed=SEED):
    R.seed(seed)
    T = [one_trial(plan, v, x) for _ in range(n)]
    E = [t["ev"] for t in T]
    r12 = [t["rev"][12] for t in T]; r11 = [t["rev"][11] for t in T]
    o = dict(n=n)
    for mo in (3, 6, 12):
        r = [t["rev"][mo] for t in T]
        o[f"rev{mo}"] = (pct(r, .1), pct(r, .5), pct(r, .9))
        o[f"sku{mo}"] = pct([t["sku"][mo] for t in T], .5)
    o["mg12"] = pct([(t["prof"][12] / t["rev"][12]) if t["rev"][12] > 0 else -1 for t in T], .5)
    o["lane12"] = pct([t["lane_pr"][12] for t in T], .5)
    o["cum"] = pct([sum(t["prof"]) for t in T], .5)
    o["cum_p10"] = pct([sum(t["prof"]) for t in T], .1)
    o["cash_min_p10"] = pct([min(t["cash"]) for t in T], .1)
    o["P30"] = st.mean(r >= 3e5 for r in r12); o["P60"] = st.mean(r >= 6e5 for r in r12); o["P120"] = st.mean(r >= 1.2e6 for r in r12)
    o["sent"] = (pct([e["n_sent"] for e in E], .1), pct([e["n_sent"] for e in E], .5), pct([e["n_sent"] for e in E], .9))
    o["est"] = (pct([e["n_est"] for e in E], .1), pct([e["n_est"] for e in E], .5), pct([e["n_est"] for e in E], .9), st.mean(e["n_est"] for e in E))
    o["P_sent300"] = st.mean(e["n_sent"] >= 300 for e in E); o["P_sent240"] = st.mean(e["n_sent"] >= 240 for e in E)
    o["P_est1_m5"] = st.mean(e["est_m5"] >= 1 for e in E)
    o["P_est3"] = st.mean(e["n_est"] >= 3 for e in E); o["P_est6"] = st.mean(e["n_est"] >= 6 for e in E)
    o["P_sold3"] = st.mean(e["n_sold30"] >= 3 for e in E)
    o["P_northstar"] = st.mean(e["n_sent"] >= 300 and e["n_est"] >= 6 and e["n_sold30"] >= 3 for e in E)
    o["P_excl1"] = st.mean(e["n_excl"] >= 1 for e in E); o["P_oem1"] = st.mean(e["n_oem"] >= 1 for e in E)
    o["P_low"] = st.mean(e["low"] for e in E)
    # ---- 撤退条件13本（タケシ §6） ----
    fl = [e["first_list"] for e in E]; fp = [e["first_pay"] for e in E]
    W = {}
    W["1 10/2 アミノ却下"] = st.mean(not e["amino_ok"] for e in E)
    W["2 10/30 出品0"] = st.mean(a is None or a * DAY_M > 46 for a in fl)
    W["3 12/15 送信<14"] = st.mean(e["sent_by_1215"] < 14 for e in E)
    W["4 12/15 送信≥20かつ見積0"] = st.mean(e["sent_by_1215"] >= 20 and e["quote_by_1215"] == 0 for e in E)
    W["5 1/15 初回入金0"] = st.mean(a is None or a > 123 for a in fp)
    W["6 2027-02 送信≥60かつ成立0"] = st.mean(e["cum_sent"][5] >= 60 and e["est_m5"] == 0 for e in E)
    W["6' 2027-02 送信<60（評価不能）"] = st.mean(e["cum_sent"][5] < 60 for e in E)
    W["7 3/15 送信≥50かつ成立0かつSKU<3"] = st.mean(e["cum_sent"][5] >= 50 and e["est_m6_0315"] == 0 and t["sku"][6] < 3 for e, t in zip(E, T))
    W["8 2027-05 送信≥120かつ成立≤1"] = st.mean(e["cum_sent"][8] >= 120 and e["est_m8"] <= 1 for e in E)
    W["8' 2027-05 送信<120（評価不能）"] = st.mean(e["cum_sent"][8] < 120 for e in E)
    W["9 送信が計画の50%未満×2ヶ月連続（12M内に1回以上）"] = st.mean(e["low2"] for e in E)
    W["10 最初の3SKUの実売が読みの1/3未満"] = st.mean(len(e["first3"]) >= 3 and st.mean(e["first3"]) < 1 / 3 for e in E)
    W["10' 12Mで3SKUの30日実売が出ない"] = st.mean(len(e["first3"]) < 3 for e in E)
    W["12 9/12 成立<3かつ月商<15万"] = st.mean(e["n_est"] < 3 and t["rev"][12] < 1.5e5 for e, t in zip(E, T))
    W["13 9/12 レーン利益率<5%×2ヶ月連続"] = st.mean(t["lane_pr"][11] < .05 and t["lane_pr"][12] < .05 for t in T)
    o["W"] = W
    # 成立の時期（1社目・3社目・6社目の中央月）
    def kth(k):
        d = [sorted(e["est_days"])[k - 1] / DAY_M for e in E if len(e["est_days"]) >= k]
        return (pct(d, .5) if d else None, len(d) / n)
    o["est_k"] = {k: kth(k) for k in (1, 3, 6)}
    return o


def show(label, o, full=True):
    r3, r6, r12 = o["rev3"], o["rev6"], o["rev12"]
    print(f"\n=== {label}  (n={o['n']})")
    print(f"  月商 3M {r3[1]/1e4:.0f}万 / 6M {r6[1]/1e4:.0f}万 / 12M 中央 {r12[1]/1e4:.0f}万 (P10 {r12[0]/1e4:.0f}〜P90 {r12[2]/1e4:.0f})  P(≥30万) {o['P30']:.0%} P(≥60万) {o['P60']:.0%} P(≥120万) {o['P120']:.0%}")
    print(f"  送信 中央 {o['sent'][1]} ({o['sent'][0]}〜{o['sent'][2]}) P(≥300) {o['P_sent300']:.0%} P(≥240) {o['P_sent240']:.0%} | 2027-02 成立≥1 {o['P_est1_m5']:.0%} | 成立 中央 {o['est'][1]} ({o['est'][0]}〜{o['est'][2]}, 平均 {o['est'][3]:.1f}) P(≥3) {o['P_est3']:.0%} P(≥6) {o['P_est6']:.0%} | 取り分実測3件 {o['P_sold3']:.0%} | 北極星3つ同時 {o['P_northstar']:.0%}")
    print(f"  SKU 12M {o['sku12']} | 利益率12M(固定費込) {o['mg12']:+.0%} レーン {o['lane12']:+.0%} | 累計損益 中央 {o['cum']/1e4:+.0f}万 (P10 {o['cum_p10']/1e4:+.0f}万) | 現金最小P10 {o['cash_min_p10']/1e4:.0f}万 | 独占≥1 {o['P_excl1']:.0%} OEM≥1 {o['P_oem1']:.0%} | 低稼働 {o['P_low']:.0%}")
    k = o["est_k"]
    print(f"  成立の時期（中央月, 到達率）: 1社目 {k[1][0] and round(k[1][0],1)} ({k[1][1]:.0%}) / 3社目 {k[3][0] and round(k[3][0],1)} ({k[3][1]:.0%}) / 6社目 {k[6][0] and round(k[6][0],1)} ({k[6][1]:.0%})")
    if full:
        for key, val in o["W"].items(): print(f"    撤退 {key}: {val:.0%}")


if __name__ == "__main__":
    t0 = time.time()
    print(f"実測倍率: ファミリー n={len(FAMILY)} 中央 {st.median(FAMILY):.2f} 平均 {st.mean(FAMILY):.2f} (P10 {pct(FAMILY,.1):.2f}〜P90 {pct(FAMILY,.9):.2f}) / 実測層 n={len(MEASURED)} 中央 {st.median(MEASURED):.2f} 平均 {st.mean(MEASURED):.2f} ({pct(MEASURED,.1):.2f}〜{pct(MEASURED,.9):.2f}) / ファミリー・現在オファーあり n={len(OFFERS)} 中央 {st.median(OFFERS):.2f} 平均 {st.mean(OFFERS):.2f} ({pct(OFFERS,.1):.2f}〜{pct(OFFERS,.9):.2f})")
    X = dict(X0)

    print("\n##### 1. 検証① B（週10通）の分布: マサル1周目 → タケシ2周目B への橋渡し（1変数ずつ）")
    steps = [
        ("0 マサル1周目そのまま（波105・低稼働30%・消化90%・資本/ツール無条件・卸拡張あり）", "M", dict(V_C, consume=.9), dict(X, cap_conditional=False, tools_conditional=False, brand_reg=1.0, a5_first=False)),
        ("1 +波をB（343）に", "B", dict(V_C, consume=.9), dict(X, cap_conditional=False, tools_conditional=False, brand_reg=1.0, a5_first=False)),
        ("2 +消化率 90→80%", "B", V_C, dict(X, cap_conditional=False, tools_conditional=False, brand_reg=1.0, a5_first=False)),
        ("3 +資本を成立3社条件に", "B", V_C, dict(X, tools_conditional=False, brand_reg=1.0, a5_first=False)),
        ("4 +スプライト/商標を成立2社条件に", "B", V_C, dict(X, brand_reg=1.0, a5_first=False)),
        ("5 +ブランド登録40%・崩れ40%（タケシ）", "B", V_C, dict(X, brand_reg=.40, a5_first=False)),
        ("6 +ブランド登録15%・A5先行（サトルS-d反映）", "B", V_C, dict(X)),
        ("7 +低稼働 30→20%（タケシの置き値）", "B", V_C, dict(X, low_regime=.20)),
        ("8 +卸のブランド拡張を外す（タケシ calc に近い）", "B", V_C, dict(X, low_regime=.20, oroshi_expand=False)),
    ]
    for label, pl, v, x in steps:
        o = run(PLANS[pl], v, x, N_SENS); show(label, o, full=False)

    print("\n##### 2. 中央（B・取り分固定1.0・低稼働30%）= 本書の基準ケース")
    BASE = run(PLANS["B"], V_C, X, N_MAIN); show("B 中央（基準）", BASE)
    print("\n##### 3. 検証②④ 悲観・成立率1.5%の世界（撤退条件13本）")
    PESS = run(PLANS["B"], V_P, dict(X, pool_idx=2), N_SENS); show("B 悲観（全変数悲観）", PESS)
    EST15 = run(PLANS["B"], dict(V_C, est=.015), X, N_MAIN); show("B 成立率1.5%のみ悲観", EST15)
    EST5 = run(PLANS["B"], dict(V_C, est=.05), X, N_SENS); show("B 成立率5%のみ楽観", EST5)
    OPT = run(PLANS["B"], V_O, dict(X, pool_idx=1), N_SENS); show("B 楽観（全変数楽観）", OPT)

    print("\n##### 4. サトル05 の実測を投入: 取り分 A 固定1.0 / B ファミリー別 / C 実測層のみ × 成立率 1.5/3/5%")
    for sm, sl in (("fixed", "A 固定1.0"), ("family", "B ファミリー別(n=68)"), ("offers", "B'' 現在オファーあり(n=62)"), ("measured", "C 実測層のみ(n=24)")):
        for e, el in ((.015, "1.5%"), (.03, "3%"), (.05, "5%")):
            o = run(PLANS["B"], dict(V_C, est=e), dict(X, share_mode=sm), N_SENS)
            print(f"  取り分{sl:22s} × 成立率{el:4s}: 12M 中央 {o['rev12'][1]/1e4:4.0f}万 (P10 {o['rev12'][0]/1e4:3.0f}〜P90 {o['rev12'][2]/1e4:4.0f}) P(≥30万) {o['P30']:.0%} P(≥60万) {o['P60']:.0%} | 成立 {o['est'][1]} P(≥6) {o['P_est6']:.0%} | SKU {o['sku12']} | 累計損益 {o['cum']/1e4:+.0f}万 | 北極星 {o['P_northstar']:.0%} | 撤退10 {o['W']['10 最初の3SKUの実売が読みの1/3未満']:.0%} | 撤退12 {o['W']['12 9/12 成立<3かつ月商<15万']:.0%} | 撤退13 {o['W']['13 9/12 レーン利益率<5%×2ヶ月連続']:.0%}")
    MIX = run(PLANS["B"], V_C, dict(X, share_mode="family", est_mix=[(.30, .015), (.45, .03), (.25, .05)]), N_MAIN)
    show("B 混合（成立率 1.5%:30% / 3%:45% / 5%:25%・取り分ファミリー別）= 私の本命の分布", MIX)

    print("\n##### 5. 検証③ 週20通（C）の歩留まり低下込み")
    for label, x in (("C 歩留まり低下なし（タケシ）", dict(X)), ("C 低下あり（300通超×0.6・週20通の下書き×0.85）", dict(X, decay=True)),
                     ("C 低下あり・母数300（第3陣が来ない）", dict(X, decay=True, pool_idx=2)), ("A 週5通", dict(X))):
        pl = "A" if label.startswith("A") else "C"
        o = run(PLANS[pl], V_C, x, N_SENS); show(label, o, full=False)

    print("\n##### 6. ブランド登録の実測（S-d）を応手に反映")
    for label, x in (("登録40%・A5なし（タケシ）", dict(X, brand_reg=.40, a5_first=False)), ("登録15%・A5なし", dict(X, brand_reg=.15, a5_first=False)),
                     ("登録15%・A5先行（本書）", dict(X)), ("登録6%・A5先行（不明6社が全部未登録）", dict(X, brand_reg=.06))):
        o = run(PLANS["B"], V_C, x, N_SENS)
        print(f"  {label:36s}: 12M 中央 {o['rev12'][1]/1e4:.0f}万 | 独占≥1 {o['P_excl1']:.0%} | 成立中央 {o['est'][1]}")

    print("\n##### 7. 社長論点③④ と 低稼働の感応度")
    for label, x in (("③ 4社案を並走しない（波1を1月へ）", dict(X, relax1=False)), ("④ フォールバックを社長判断待ちに", dict(X, auto_fallback=False)),
                     ("低稼働 20%", dict(X, low_regime=.20)), ("低稼働 50%", dict(X, low_regime=.50)), ("低稼働 0%・滞留0（社長の手が止まらない）", dict(X, low_regime=0, stall=0))):
        o = run(PLANS["B"], V_C, x, N_SENS)
        print(f"  {label:40s}: 12M 中央 {o['rev12'][1]/1e4:.0f}万 | 送信中央 {o['sent'][1]} P(≥300) {o['P_sent300']:.0%} | 成立中央 {o['est'][1]} P(≥6) {o['P_est6']:.0%} | 出品0@10/30 {o['W']['2 10/30 出品0']:.0%} | 12/15送信<14 {o['W']['3 12/15 送信<14']:.0%} | 1社目 {o['est_k'][1][0] and round(o['est_k'][1][0],1)}")
    print(f"\n所要 {time.time()-t0:.0f}s  N_MAIN={N_MAIN} N_SENS={N_SENS}")
