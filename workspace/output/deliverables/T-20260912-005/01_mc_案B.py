"""T-20260912-005 案B「鍵を積み、独占へ渡す」の12ヶ月モンテカルロ（マサル 1周目）

段の所要日数（送信→返信→見積→口座/確約→出荷→FBA→初回販売→入金）は
T-20260912-001/07_mc_最終版.py と同じ三角分布。そこに次を足した。
  ・月次の売上/SKU/利益率（2026-09=月0 … 2027-09=月12）
  ・資本キャップ（月商 ≤ 使える資本。在庫1.5ヶ月・原価率0.65 → ほぼ1倍）
  ・社長の §4.1 の滞留（月ごとに「送信0」になる月がある）と消化率
  ・アカウント事故（2〜3ヶ月の全停止）
  ・卸レーン（アミノのゲート → SD → 卸請求書での解除）
  ・限定/独占の提案（取引3ヶ月後）、簡易OEM（2027-02〜、商標44,900円、ロット3〜10万円、3割は不発）
  ・相乗りの価格下落と競合参入（6ヶ月で取り分×0.8）
タケシ §6-1 の11変数を C(中央)/O(楽観)/P(悲観) で持ち、感応度は1変数ずつ振る（OAT）。
乱数固定。python3 01_mc_案B.py [--fast] で実行。
"""
import random as R, math, sys, statistics as st

SEED = 20260913
N_MAIN = 20000
N_SENS = 10000
if "--fast" in sys.argv:
    N_MAIN, N_SENS = 4000, 2000

DAY_M = 30.4          # 1ヶ月の日数
MONTHS = 13           # 月0〜12
tri = lambda a, m, b: R.triangular(a, b, m)
logn = lambda med, sig: med * math.exp(R.gauss(0, sig))

# ---- タケシ §6-1 の11変数（中央／楽観／悲観） ----
V_C = dict(reply=.25, est=.03, sku_per=2.0, share=1.0, excl=.25, gate=.60, oem=.15, oem_rev=5e4,
           cap2=3e5, cap3=1e6, consume=.90, acc=.15)
V_O = dict(reply=.35, est=.05, sku_per=4.0, share=1.5, excl=.40, gate=.80, oem=.30, oem_rev=1e5,
           cap2=5e5, cap3=2e6, consume=1.0, acc=.05)
V_P = dict(reply=.12, est=.015, sku_per=1.0, share=0.3, excl=.10, gate=.40, oem=.05, oem_rev=1e4,
           cap2=1e5, cap3=3e5, consume=.60, acc=.30)
# 資本は「cap2→cap3」で1変数扱い（タケシの表と同じ）

# ---- マサルが足した前提（変数表に無いもの。推測） ----
X = dict(
    stall=.20,        # 社長の手が止まり、その月の送信が0になる確率
    low_regime=.30,   # 12ヶ月を通して低稼働（消化率×0.35・滞留50%）になる確率。4ヶ月で送信0通の前科から（推測）
    wave_mult=1.0,    # 波の社数の倍率（逆算用）
    amino_slip=.20,   # アミノの出品が10月末を越えてずれる確率
    fallback_quick=.40,# ゲート却下時、緩和②のフォールバック出品が10/30に間に合う確率
    relax1=True,      # 緩和①（4社案を9月に送る）が承認される
    gated=.70,        # 本丸メーカーのブランドにゲートがある割合
    confirm=.80,      # ゲートあり社が請求書記載を書面で確約する
    quote=.35,        # 前向き返信のうち見積まで行く割合（25%×35%≈8.75%。EC STARs 8〜10%）
    ainori_rev=3e4,   # 本丸相乗り 1 SKU の月商中央値（タケシ 3万）
    excl_rev=7e4,     # 限定/独占 1 SKU の月商中央値（タケシ 10万を広告費と立ち上がりで割引）
    price_drift=-.004,# 相乗りの月次価格変化（年−5%）
    entry6=.80,       # 6ヶ月後に相乗り+1で取り分×0.8
    sd_pass=.50,      # スーパーデリバリー通過
    oem_dud=.30,      # OEM が月0〜1個で終わる割合
    trademark=True,   # 商標を12月に出願する（44,900円）
    sprite=True,      # セラースプライトを1月から契約（13,998円/月）
)
# 波（月, 社数）。緩和①非承認なら月0の4社は月4へ
WAVES = [(0, 4), (1, 10), (3, 15), (4, 10), (5, 10), (6, 10), (7, 10), (8, 10), (9, 10), (10, 10), (11, 10)]
FIXED = 14000        # 大口5,390 + Keepa API 約8,500
MARGIN = dict(amino=.08, oroshi=.06, ainori=.12, excl=.25, oem=.30, fallback=.00)


def one_trial(v, x):
    """1試行。戻り値: dict(rev[13], sku[13], margin[13], cash[13], events)"""
    rev = [0.0] * MONTHS; sku = [0] * MONTHS; prof = [0.0] * MONTHS
    lane = [dict(oroshi=0.0, ainori=0.0, excl=0.0, oem=0.0) for _ in range(MONTHS)]
    # 共通倍率（成立率・返信率の相関）
    u = R.random(); m = 2.0 if u < .2 else (1.0 if u < .8 else .4)
    # アカウント事故
    halt = set()
    if R.random() < v["acc"]:
        t = R.randrange(0, 12); halt.update([t, t + 1])
        if R.random() < .3: halt.add(t + 2)
    # 社長の手の滞留（低稼働レジームなら12ヶ月を通して重い）
    low = R.random() < x["low_regime"]
    stall_p = .5 if low else x["stall"]; consume = v["consume"] * (.35 if low else 1.0)
    stalled = [R.random() < stall_p for _ in range(MONTHS)]
    # ---- 本丸の送信 ----
    pending = 0.0; sends = []   # (day)
    waves = dict()
    for mo, n in WAVES:
        if mo == 0 and not x["relax1"]: mo = 4
        waves[mo] = waves.get(mo, 0) + n * x["wave_mult"]
    for mo in range(MONTHS):
        pending += waves.get(mo, 0)
        if stalled[mo] or mo in halt: continue
        k = int(round(pending * consume))
        k = min(k, int(pending))
        for _ in range(k):
            sends.append(mo * DAY_M + R.uniform(3, 25))
        pending -= k
    # ---- 各社の結果 ----
    firms = []   # dict(fs=初回販売日, pay=初回入金日, k=SKU数, gated)
    n_pos = n_quote = n_est = 0
    pos_by_1215 = quote_by_1215 = 0; sent_by_1215 = 0
    for s in sends:
        if s <= 92: sent_by_1215 += 1
        pos = R.random() < min(1, v["reply"] * m)
        if pos:
            n_pos += 1
            q = R.random() < x["quote"]
            if q: n_quote += 1
            if s + tri(3, 7, 21) <= 92:
                pos_by_1215 += 1
                if q: quote_by_1215 += 1
        if R.random() >= min(1, v["est"] * m): continue
        gated = R.random() < x["gated"]
        if gated and R.random() >= x["confirm"]:
            continue   # 成立しても Amazon で売れない → 0円撤退
        n_est += 1
        r = s + tri(3, 7, 21) + (5 if s < 9 else 0)
        o = r + tri(7, 14, 30); d = o + tri(5, 10, 30)
        if R.random() < .5: d += tri(3, 7, 14)
        d += tri(7, 12, 21); fs = d + tri(1, 5, 20); pay = fs + tri(7, 14, 21)
        if R.random() < .08: fs += tri(30, 45, 90); pay += tri(30, 45, 90)
        # 事故中に販売開始が重なれば後ろへ
        while int(fs // DAY_M) in halt: fs += DAY_M; pay += DAY_M
        k = max(1, int(round(logn(v["sku_per"], .45))))
        firms.append(dict(fs=fs, pay=pay, k=k, gated=gated,
                          unit=[logn(x["ainori_rev"], .5) * v["share"] for _ in range(k)],
                          excl=None, oem=None))
    # 限定/独占・OEM の分岐
    for f in firms:
        fm = f["fs"] / DAY_M
        if fm + 4 <= 12 and R.random() < v["excl"]:
            f["excl"] = fm + 4   # 取引3ヶ月で提案→1ヶ月で切替
        # 簡易OEM：2027-02（月5）以降、取引1ヶ月経過の社に1回だけ打診
        pm = max(5.0, fm + 1)
        if pm < 11 and R.random() < v["oem"]:
            lead = tri(60, 90, 150) / DAY_M
            f["oem"] = dict(start=pm + lead, lot=tri(3e4, 6e4, 1e5),
                            rev=(logn(v["oem_rev"], .8) * (0.1 if R.random() < x["oem_dud"] else 1.0)))
    # ---- 卸レーン ----
    amino_ok = R.random() < v["gate"]
    amino_start = (1.3 + (0.7 if R.random() < x["amino_slip"] else 0)) if amino_ok else None   # 10月中旬（2割は11月へ）
    fallback_start = None if amino_ok else (1.5 if R.random() < x["fallback_quick"] else 2.5)
    sd_ok = R.random() < x["sd_pass"]
    sd_n = (R.random() < .7) + (R.random() < .4) + (R.random() < .2) if sd_ok else 0   # 0〜3
    oroshi = []  # (start_month, unit_rev, margin)
    if amino_ok: oroshi.append((amino_start, 2.1e4 * logn(1, .3) * v["share"], MARGIN["amino"]))
    if fallback_start: oroshi.append((fallback_start, 0.6e4 * logn(1, .3), MARGIN["fallback"]))
    for i in range(sd_n): oroshi.append((3 + i * .7, 1.5e4 * logn(1, .5) * v["share"], MARGIN["oroshi"]))
    if amino_ok:  # 卸請求書でゲートが開く → 2ヶ月に1ブランド、各1〜3 SKU（上限20）
        mo = 3.5
        while mo < 12 and len(oroshi) < 20:
            for _ in range(1 + (R.random() < .5) + (R.random() < .25)):
                oroshi.append((mo, 1.5e4 * logn(1, .5) * v["share"], MARGIN["oroshi"]))
            mo += 2 + R.uniform(-.5, 1.0)
    # ---- 月次集計 ----
    cap_inj = [1e5] * MONTHS
    for mo in range(MONTHS):
        if mo >= 3: cap_inj[mo] += v["cap2"]
        if mo >= 8: cap_inj[mo] += v["cap3"]
    cum_prof = 0.0; cum_lane = 0.0; oneoff_paid = 0.0; cash = [0.0] * MONTHS
    first_list = None; first_pay = None
    for mo in range(MONTHS):
        fixed = FIXED + (13998 if (x["sprite"] and mo >= 4) else 0)
        oneoff = 0.0
        if x["trademark"] and mo == 3: oneoff += 44900
        lanes_rev = 0.0; lanes_prof = 0.0; n_sku = 0
        if mo not in halt:
            for (s0, unit, mg) in oroshi:
                if mo >= s0:
                    ramp = 0.5 if mo < s0 + 1 else 1.0
                    drift = (1 + x["price_drift"]) ** max(0, mo - s0)
                    ent = x["entry6"] if mo >= s0 + 6 else 1.0
                    rv = unit * ramp * drift * ent
                    lanes_rev += rv; lanes_prof += rv * mg; n_sku += 1; lane[mo]["oroshi"] += rv
                    if first_list is None: first_list = s0 - .3
            for f in firms:
                fm = f["fs"] / DAY_M
                if mo >= fm:
                    if first_list is None or fm - .3 < first_list: first_list = fm - .3
                    if first_pay is None or f["pay"] < first_pay: first_pay = f["pay"]
                    excl_on = f["excl"] is not None and mo >= f["excl"]
                    for unit in f["unit"]:
                        if excl_on:
                            rv = logn(x["excl_rev"], .15) * (unit / x["ainori_rev"]) ** .3
                            lanes_rev += rv; lanes_prof += rv * MARGIN["excl"]; lane[mo]["excl"] += rv
                        else:
                            ramp = 0.5 if mo < fm + 1 else 1.0
                            drift = (1 + x["price_drift"]) ** max(0, mo - fm)
                            ent = x["entry6"] if mo >= fm + 6 else 1.0
                            rv = unit * ramp * drift * ent
                            lanes_rev += rv; lanes_prof += rv * MARGIN["ainori"]; lane[mo]["ainori"] += rv
                        n_sku += 1
                if f["oem"] is not None:
                    o = f["oem"]
                    if o["start"] - 1 <= mo < o["start"] and not o.get("paid"):
                        oneoff += o["lot"]; o["paid"] = True
                    if mo >= o["start"]:
                        rv = o["rev"] * (0.5 if mo < o["start"] + 1 else 1.0)
                        lanes_rev += rv; lanes_prof += rv * MARGIN["oem"]; n_sku += 1; lane[mo]["oem"] += rv
        # 資本キャップ（固定費は別枠。月商 ≤ 在庫に回せる資本 × 1.2）
        avail = cap_inj[mo] + cum_lane - oneoff_paid - oneoff
        cap = max(0.0, avail) * 1.2
        if lanes_rev > cap and lanes_rev > 0:
            scale = cap / lanes_rev; lanes_rev *= scale; lanes_prof *= scale
            for kk in lane[mo]: lane[mo][kk] *= scale
        p = lanes_prof - fixed
        cum_prof += p; cum_lane += lanes_prof; oneoff_paid += oneoff
        rev[mo] = lanes_rev; sku[mo] = n_sku; prof[mo] = p
        cash[mo] = cap_inj[mo] + cum_prof - oneoff_paid
    margin = [(prof[i] / rev[i]) if rev[i] > 0 else (-1.0 if prof[i] < 0 else 0.0) for i in range(MONTHS)]
    ev = dict(first_list=first_list, first_pay=first_pay, n_pos=n_pos, n_quote=n_quote, n_est=n_est,
              sent_by_1215=sent_by_1215, pos_by_1215=pos_by_1215, quote_by_1215=quote_by_1215,
              n_sent=len(sends), amino_ok=amino_ok, halt=bool(halt),
              n_excl=sum(1 for f in firms if f["excl"] is not None and f["excl"] <= 12),
              n_oem=sum(1 for f in firms if f["oem"] is not None and f["oem"]["start"] <= 12),
              est_by_0315=sum(1 for f in firms if (f["fs"] - 60) <= 182),  # 成立≒初回販売の60日前
              est_by_m5=sum(1 for f in firms if (f["fs"] - 60) <= 5 * DAY_M),
              n_pos_total=n_pos, low=low)
    return dict(rev=rev, sku=sku, margin=margin, cash=cash, ev=ev, lane=lane)


def pct(a, q):
    a = sorted(a); i = max(0, min(len(a) - 1, int(q * len(a)) - (1 if q == 1 else 0)))
    return a[i]


def run(v, x, n, seed=SEED):
    R.seed(seed)
    T = [one_trial(v, x) for _ in range(n)]
    def col(key, mo): return [t[key][mo] for t in T]
    out = {}
    for mo in (3, 6, 12):
        r = col("rev", mo); s = col("sku", mo); g = col("margin", mo)
        out[f"rev{mo}"] = dict(p10=pct(r, .1), p20=pct(r, .2), p50=pct(r, .5), p80=pct(r, .8), p90=pct(r, .9),
                               mean=st.mean(r))
        out[f"sku{mo}"] = dict(p20=pct(s, .2), p50=pct(s, .5), p80=pct(s, .8))
        out[f"mg{mo}"] = dict(p20=pct(g, .2), p50=pct(g, .5), p80=pct(g, .8))
    r12 = col("rev", 12); r11 = col("rev", 11); g12 = col("margin", 12); g11 = col("margin", 11)
    out["P(rev12>=120万)"] = sum(1 for r in r12 if r >= 1.2e6) / n
    out["P(rev12>=250万)"] = sum(1 for r in r12 if r >= 2.5e6) / n
    out["P(rev12<30万)"] = sum(1 for r in r12 if r < 3e5) / n
    out["P(rev12>=800万)"] = sum(1 for r in r12 if r >= 8e6) / n
    out["cash12_p50"] = pct(col("cash", 12), .5); out["cash12_p10"] = pct(col("cash", 10), .1)
    out["cash_min_p10"] = pct([min(t["cash"]) for t in T], .1)
    out["cash_min_p50"] = pct([min(t["cash"]) for t in T], .5)
    E = [t["ev"] for t in T]
    fl = [e["first_list"] for e in E]; fp = [e["first_pay"] for e in E]
    out["P(出品0 at 10/30)"] = sum(1 for a in fl if a is None or a * DAY_M > 46) / n
    out["P(出品0 at 12/31)"] = sum(1 for a in fl if a is None or a * DAY_M > 108) / n
    out["P(入金0 at 1/15)"] = sum(1 for a in fp if a is None or a > 123) / n
    out["P(入金0 at 3/15)"] = sum(1 for a in fp if a is None or a > 182) / n
    out["P(本丸成立0 at 3/15)"] = sum(1 for e in E if e["est_by_0315"] == 0) / n
    out["P(成立0 & SKU<3 at 3/15)"] = sum(1 for e, t in zip(E, T) if e["est_by_0315"] == 0 and t["sku"][6] < 3) / n
    out["P(12/15 見積0 of sent)"] = sum(1 for e in E if e["quote_by_1215"] == 0) / n
    out["P(12/15 見積0 & 送信>=14)"] = sum(1 for e in E if e["quote_by_1215"] == 0 and e["sent_by_1215"] >= 14) / n
    out["P(12/15までに送信<14)"] = sum(1 for e in E if e["sent_by_1215"] < 14) / n
    out["P(9/12 月商<30万 2ヶ月連続)"] = sum(1 for a, b in zip(r11, r12) if a < 3e5 and b < 3e5) / n
    out["P(9/12 利益率<5% 2ヶ月連続)"] = sum(1 for a, b in zip(g11, g12) if a < .05 and b < .05) / n
    out["P(9/12 撤退条件)"] = sum(1 for a, b, c, d in zip(r11, r12, g11, g12) if (a < 3e5 and b < 3e5) or (c < .05 and d < .05)) / n
    out["sent12_p50"] = pct([e["n_sent"] for e in E], .5)
    out["est12_p50"] = pct([e["n_est"] for e in E], .5); out["est12_mean"] = st.mean([e["n_est"] for e in E])
    out["P(成立>=1 by 12M)"] = sum(1 for e in E if e["n_est"] >= 1) / n
    out["P(成立>=1 by 12/31)"] = sum(1 for e in E if e["first_pay"] is not None and e["first_pay"] - 74 <= 108) / n  # 成立≒入金の74日前
    out["excl12_mean"] = st.mean([e["n_excl"] for e in E]); out["P(独占>=1)"] = sum(1 for e in E if e["n_excl"] >= 1) / n
    out["oem12_mean"] = st.mean([e["n_oem"] for e in E]); out["P(OEM>=1)"] = sum(1 for e in E if e["n_oem"] >= 1) / n
    out["P(事故)"] = sum(1 for e in E if e["halt"]) / n
    out["lane12_mean"] = {k: st.mean([t["lane"][12][k] for t in T]) for k in ("oroshi", "ainori", "excl", "oem")}
    out["est_m5_mean"] = st.mean([e["est_by_m5"] for e in E]); out["P(月5までに成立>=2)"] = sum(1 for e in E if e["est_by_m5"] >= 2) / n
    out["pos12_p50"] = pct([e["n_pos_total"] for e in E], .5)
    out["P(低稼働)"] = sum(1 for e in E if e["low"]) / n
    return out


def fmt_money(y): return f"{y/1e4:.0f}万"


def show(label, o):
    print(f"\n=== {label}")
    for mo in (3, 6, 12):
        r = o[f"rev{mo}"]; s = o[f"sku{mo}"]; g = o[f"mg{mo}"]
        print(f"月{mo:2d}: 月商 P10 {fmt_money(r['p10'])} / P20 {fmt_money(r['p20'])} / P50 {fmt_money(r['p50'])} / P80 {fmt_money(r['p80'])} / P90 {fmt_money(r['p90'])} (mean {fmt_money(r['mean'])})"
              f" | SKU {s['p20']}/{s['p50']}/{s['p80']} | 利益率 {g['p20']:.0%}/{g['p50']:.0%}/{g['p80']:.0%}")
    for k in ("P(rev12>=120万)", "P(rev12>=250万)", "P(rev12<30万)", "P(rev12>=800万)", "P(出品0 at 10/30)", "P(出品0 at 12/31)",
              "P(入金0 at 1/15)", "P(入金0 at 3/15)", "P(本丸成立0 at 3/15)", "P(成立0 & SKU<3 at 3/15)",
              "P(12/15 見積0 of sent)", "P(12/15 見積0 & 送信>=14)", "P(12/15までに送信<14)",
              "P(9/12 月商<30万 2ヶ月連続)", "P(9/12 利益率<5% 2ヶ月連続)", "P(9/12 撤退条件)",
              "P(成立>=1 by 12M)", "P(独占>=1)", "P(OEM>=1)", "P(事故)"):
        print(f"  {k}: {o[k]:.0%}")
    print(f"  送信数(12M) 中央 {o['sent12_p50']} / 成立社数 中央 {o['est12_p50']} 平均 {o['est12_mean']:.2f} / 独占 平均 {o['excl12_mean']:.2f} / OEM 平均 {o['oem12_mean']:.2f}")
    print(f"  現金 12M 中央 {fmt_money(o['cash12_p50'])} / 期間最小 P10 {fmt_money(o['cash_min_p10'])} P50 {fmt_money(o['cash_min_p50'])}")
    L = o["lane12_mean"]; print(f"  月12 月商の内訳(平均): 卸 {fmt_money(L['oroshi'])} / 本丸相乗り {fmt_money(L['ainori'])} / 独占 {fmt_money(L['excl'])} / OEM {fmt_money(L['oem'])}")
    print(f"  前向き返信 社数 中央 {o['pos12_p50']} / 月5(2027-02)までの成立社数 平均 {o['est_m5_mean']:.2f} / P(>=2) {o['P(月5までに成立>=2)']:.0%}")


if __name__ == "__main__":
    import time; t0 = time.time()
    C = run(V_C, X, N_MAIN); show("中央（タケシ置き値そのまま＋マサル前提）", C)
    O = run(V_O, X, N_SENS); show("楽観（11変数すべて楽観）", O)
    P = run(V_P, X, N_SENS); show("悲観（11変数すべて悲観）", P)
    # 混合（楽観20/中央60/悲観20 を試行比率で）
    print("\n=== 感応度（OAT: 1変数だけ楽観/悲観に振る。12ヶ月 月商の中央値と P(>=120万)）")
    base = C["rev12"]["p50"]; rows = []
    for k in V_C:
        if k == "cap3": continue
        vo = dict(V_C); vp = dict(V_C)
        if k == "cap2": vo["cap2"], vo["cap3"] = V_O["cap2"], V_O["cap3"]; vp["cap2"], vp["cap3"] = V_P["cap2"], V_P["cap3"]
        else: vo[k] = V_O[k]; vp[k] = V_P[k]
        ro = run(vo, X, N_SENS); rp = run(vp, X, N_SENS)
        rows.append((k, ro["rev12"]["p50"], rp["rev12"]["p50"], ro["P(rev12>=120万)"], rp["P(rev12>=120万)"], ro["P(rev12<30万)"], rp["P(rev12<30万)"]))
    rows.sort(key=lambda r: -(r[1] - r[2]))
    print("変数 | 楽観に振った中央 | 悲観に振った中央 | 幅 | P(>=120万) 楽/悲 | P(<30万) 楽/悲")
    for k, a, b, pa, pb, qa, qb in rows:
        print(f"{k} | {fmt_money(a)} | {fmt_money(b)} | {fmt_money(a-b)} | {pa:.0%}/{pb:.0%} | {qa:.0%}/{qb:.0%}")
    print("\n=== マサルが足した前提の感応度")
    for label, xx in (("低稼働レジーム0%（社長の手が止まらない）", dict(X, low_regime=0.0, stall=0.0)), ("低稼働レジーム50%", dict(X, low_regime=.50)),
                      ("緩和①非承認（本丸の送信は1月から）", dict(X, relax1=False)),
                      ("確約50%", dict(X, confirm=.5)), ("独占1SKU=10万（タケシ値）", dict(X, excl_rev=1e5)),
                      ("商標・スプライトを買わない", dict(X, trademark=False, sprite=False)),
                      ("SD不通過", dict(X, sd_pass=0.0))):
        r = run(V_C, xx, N_SENS)
        print(f"{label}: 月商12 中央 {fmt_money(r['rev12']['p50'])} / P(>=120万) {r['P(rev12>=120万)']:.0%} / P(<30万) {r['P(rev12<30万)']:.0%} / 出品0@10/30 {r['P(出品0 at 10/30)']:.0%} / 入金0@1/15 {r['P(入金0 at 1/15)']:.0%} / 9/12撤退 {r['P(9/12 撤退条件)']:.0%}")
    print("\n=== 逆算：120万に何が要るか")
    for label, vv, xx in (("送信2倍（20社/月）", V_C, dict(X, wave_mult=2.0)), ("送信3倍", V_C, dict(X, wave_mult=3.0)),
                          ("成立率5%＋送信2倍", dict(V_C, est=.05), dict(X, wave_mult=2.0)),
                          ("成立率5%＋送信2倍＋低稼働0", dict(V_C, est=.05), dict(X, wave_mult=2.0, low_regime=0.0, stall=0.0)),
                          ("楽観11変数＋送信2倍＋低稼働0", V_O, dict(X, wave_mult=2.0, low_regime=0.0, stall=0.0))):
        r = run(vv, xx, N_SENS)
        print(f"{label}: 月商12 中央 {fmt_money(r['rev12']['p50'])} P80 {fmt_money(r['rev12']['p80'])} / P(>=120万) {r['P(rev12>=120万)']:.0%} / SKU {r['sku12']['p50']} / 利益率 {r['mg12']['p50']:.0%} / 送信 {r['sent12_p50']} / 成立 {r['est12_mean']:.1f} / 9/12撤退 {r['P(9/12 撤退条件)']:.0%}")
    print("\n=== 資本を足さない（10万のまま）＋成立率1%")
    r = run(dict(V_C, cap2=0, cap3=0), X, N_SENS); print(f"資本10万のまま: 月商12 中央 {fmt_money(r['rev12']['p50'])} / SKU {r['sku12']['p50']} / 利益率 {r['mg12']['p50']:.0%} / 9/12撤退 {r['P(9/12 撤退条件)']:.0%}")
    r = run(dict(V_C, est=.01), X, N_SENS); print(f"成立率1%: 月商12 中央 {fmt_money(r['rev12']['p50'])} / 成立>=1 {r['P(成立>=1 by 12M)']:.0%} / 3/15 成立0 {r['P(本丸成立0 at 3/15)']:.0%} / 9/12撤退 {r['P(9/12 撤退条件)']:.0%}")
    r = run(dict(V_C, est=.01, share=.3), X, N_SENS); print(f"成立率1%×取り分0.3: 月商12 中央 {fmt_money(r['rev12']['p50'])} / 9/12撤退 {r['P(9/12 撤退条件)']:.0%} / 現金最小P10 {fmt_money(r['cash_min_p10'])}")
    print(f"\n所要 {time.time()-t0:.0f}s  N_MAIN={N_MAIN} N_SENS={N_SENS}")
