#!/usr/bin/env python3
"""T-20260914-003 マサル1周目 — 案A/B/C の12ヶ月モンテカルロ × ハジメの日次計算器 00_cf_base.py

構造
- 各経路で「卸の SKU」「メーカーの成立と SKU」「せどりの原石」を月次で引く（マサル前回 T-20260912-005 の構造＋タケシ 01_calc の変数）。
- 発注は1回ずつ cf_base の Lane（利益率・回転・リード・支払い条件）にして、00_cf_base.simulate で日次に回す。
  入金（売上→口座 14〜27日）、カードの猶予、メーカー初回の前払い、税はハジメの計算器のまま。
- 判定: cum_cash（実質＝9/30 の現金−未払−200万）>0、thin_cash（日次の最低）≥25万。
- 初回ロットは「読み（期待月販）」で買い、売れるのは「実現（読み×倍率）」。読み違いは回転の延長と処分（原価の約66%回収）で現れる。
- 乱数固定・標準ライブラリのみ。 python3 01_mc.py [--quick]
すべての置き値は（推測）。根拠は 01_案Cのキャッシュ仮想PDCA.md §2-4。
"""
import importlib.util, math, random, sys, pathlib, time, json, io
import multiprocessing as mp

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cf", HERE / "00_cf_base.py")
cf = importlib.util.module_from_spec(spec); spec.loader.exec_module(cf)
D = cf.D
SEED = 20260914
FIX = 15_253            # 段階1 14,253（ハジメ）＋会計ソフト1,000。SD はフリープラン0円（サトル S-2）

# ---- 停止中の入金留保：halt_win 内の売上は入金が60日遅れる（cf_base の payout_date を窓つきに拡張）
_orig_payout = cf.State.payout_date
def _payout(self, sale):
    d = _orig_payout(self, sale)
    w = getattr(self.cfg, "halt_win", None)
    if w and w[0] <= sale <= w[1]:
        d = cf.add(d, 60)
    return d
cf.State.payout_date = _payout

# ---------------------------------------------------------------- 置き値
MASARU = dict(
    wm_sig=0.30,                                  # 需要の共通倍率（全レーン相関）
    # 卸（需要先行×卸マルチ）
    w_pool=4.0, w_pool_sig=0.9, sd_pass=0.60, w_e=30_000, w_m=0.11, w_msd=0.035, w_h=2.0, w_drift=0.003,
    # 取り分の実現（読みに対する倍率）
    real=0.85, real_sig=0.70,
    # メーカー直
    m_rate=[(0.015, 0.30), (0.03, 0.45), (0.05, 0.25)], m_gate=0.86, m_sku=2.0, m_e=30_000,
    m_m=0.12, m_msd=0.04, m_h=2.5, m_minlot=25_000, m_drift=0.002, m_consume=0.80, q300=0.6,
    send_A=[10, 30] + [40] * 22, send_B=[10, 40] + [80] * 22, q_B=0.85, send_cap=900,
    low_A=0.25, low_B=0.30, low_nofat=0.15, low_fat=0.50,       # 送信の低稼働レジーム（×0.35）。せどりの目視が止まった世界では50%
    # 相乗りの応手
    pw=0.02, pw_cut=0.03, amz=0.004, amz_share=0.30, sku_stop_m=0.08,
    # せどり（原石モデル）
    smode="gem", s_checks=216, s_h=0.025, s_h_sig=0.45, s_G=600,
    s_gate=[(0.10, 0.35), (0.25, 0.45), (0.45, 0.20)],
    s_lot=10_000, s_rg=30_000, s_rg_sig=0.6, s_surv=(0.35, 0.65), s_ek=0.15, s_emis=0.05,
    s_m=0.09, s_msd=0.03, s_drift=0.001, s_fatigue=0.40, s_fat_f=0.30,
    s_rakuten=0.20, s_rakuten_f=0.5, s_complaint=0.25, s_hz=0.12,
    trial_checks=100, trial_overrun=0.20,
    # タケシのせどり（smode="takeshi" のとき）
    s_ss=500_000, s_ss_sig=0.6, s_ramp=[0.15, 0.35, 0.60, 0.80, 1.0],
    # アカウント事故
    hz=0.05, perm=0.25,
    # 年2（24ヶ月の試算だけで使う）
    resume_share=0.9, resume_maker_loss=0.15, deferred_maker_loss=0.20, w_pool_y2=0.7,
    fixed=FIX,
)
# タケシ 01_calc の置き値を同じ構造に入れたもの（モデル差と置き値差を分けるため）
TAKESHI = dict(MASARU, w_pool=6.0, real=0.85, real_sig=0.60, smode="takeshi", s_fatigue=0.35,
               low_A=0.25, low_B=0.25, low_nofat=0.25, low_fat=0.25, q300=1.0, s_hz=0.10,
               s_rakuten=0.0, s_complaint=0.0, pw=0.0, amz=0.0, sku_stop_m=0.0, fixed=FIX + 2_200)


def lognorm(R, med, sig):
    return med * math.exp(R.gauss(0, sig))


def pick(R, table):
    u = R.random(); acc = 0.0
    for v, p in table:
        acc += p
        if u < acc:
            return v
    return table[-1][0]


def pois(R, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(R.gauss(lam, math.sqrt(lam)))))
    L = math.exp(-lam); k = 0; p = 1.0
    while True:
        p *= R.random()
        if p < L:
            return k
        k += 1


FEE = 0.25 + 0.05 + 0.01   # cf_base の三層＋外注＋返品
def cost_rate(m):
    return 1 - m - FEE


def mk(kind, margin, turn, delay=0):
    """発注1回ぶんの Lane。kind: W（卸・カード）/M1（メーカー初回・前払い）/M2（メーカー2回目以降）/S（せどり・カード）"""
    base = {"W": ("卸_カード", 15), "M1": ("メーカー直", 20), "M2": ("メーカー直", 18), "S": ("電脳せどり", 10)}[kind]
    kw = dict(name=kind, margin=margin, turnover_m=max(0.1, turn), lead_first=base[1] + delay, lead_repeat=base[1] + delay)
    if kind == "M1":
        kw.update(pay_first=[(1.0, "order", 0, "cash")], pay_repeat=[(1.0, "order", 0, "cash")])
    if kind == "M2":
        kw.update(pay_first=[(1.0, "ship", 0, "eom_next_eom")], pay_repeat=[(1.0, "ship", 0, "eom_next_eom")])
    return cf.preset(base[0], **kw)


LIQ_M = -0.35   # 処分：原価の約66%を回収（値下げ販売＋外注・手数料）


def first_lot(orders, k, kind, lot, m, e_rev, r_rev, dead_rule=True):
    """初回ロット（原価 lot）を読み e_rev で買い、実現 r_rev で売る。回転が6ヶ月を超える分・死に筋は4ヶ月目に処分"""
    c = cost_rate(m)
    S = lot / c
    T1 = S / max(r_rev, 1.0)
    dead = dead_rule and (r_rev < 0.4 * e_rev or T1 > 6)
    if not dead:
        orders[k].append((mk(kind, m, T1), lot))
        return False, T1
    frac = min(1.0, 4 * r_rev / S)
    if frac > 0.02:
        orders[k].append((mk(kind, m, 4.0), lot * frac))
    if frac < 0.999:
        orders[k].append((mk(kind, LIQ_M, 1.0, delay=122), lot * (1 - frac)))
    return True, 4.0


def gen(R, P, plan, T):
    """1経路ぶんの発注列を作る。plan: lanes('WM'|'WMS'), send('A'|'B'), rule('none'|'as_written'|'redesign'), harvest(k: この月index以降は発注しない。None=続ける), resume(k)"""
    orders = [[] for _ in range(T)]
    meta = dict(s_stop=None, s_reason="", fatigue=False, low=False, perm=False, inc=None, n_est=0, w_n=0, gems=0,
                trial_adopt=0, trial_gate=0, g=None, h=None, early_ratio=None, s_rev_plan=0.0, sends=[], complaint=None, rakuten=None)
    wm = lognorm(R, 1.0, P["wm_sig"])
    harvest, resume = plan.get("harvest"), plan.get("resume")
    def can_order(k):
        if harvest is None or k < harvest:
            return True
        return resume is not None and k >= resume
    S_on = "S" in plan["lanes"]
    # ---- 社長の時間（せどりの目視と送信は同じ時間）
    fatigue = S_on and R.random() < P["s_fatigue"]
    mf = R.randint(2, 4) if fatigue else 999
    if S_on:
        low_p = P["low_fat"] if fatigue else P["low_nofat"]
    else:
        low_p = P["low_" + plan["send"]]
    low = R.random() < low_p
    meta.update(fatigue=fatigue, low=low)

    # ---- せどり：試行（9/24〜10/9）と撤退判定
    s_active_until = -1           # この k まで（含む）せどりの発注あり
    if S_on:
        g = pick(R, P["s_gate"])
        meta["g"] = g
        if P["smode"] == "gem":
            h = lognorm(R, P["s_h"], P["s_h_sig"]); meta["h"] = h
            def h_eff(C):
                if C <= 0:
                    return 0.0
                scr = min(C, P["s_G"] * g)
                return h * (scr + max(0.0, C - scr) * g) / C
            tc = P["trial_checks"]
            trial_adopt = pois(R, tc * h_eff(tc))
        else:
            trial_adopt = 10 if R.random() < 0.9 else 5
        gate_obs = sum(1 for _ in range(50) if R.random() < g)
        overrun = R.random() < P["trial_overrun"]
        meta.update(trial_adopt=trial_adopt, trial_gate=gate_obs)
        stop = False
        if plan["rule"] == "as_written":
            if gate_obs <= 4:
                stop, why = True, "S-1"
            elif trial_adopt < 10:
                stop, why = True, "S-2 採用"
            elif overrun:
                stop, why = True, "S-2 時間"
        elif plan["rule"] == "redesign":
            if trial_adopt < plan.get("adopt_min", 3):
                stop, why = True, "採用率"
            elif overrun:
                stop, why = True, "時間"
        s_active_until = 0 if stop else T - 1
        if stop:
            meta.update(s_stop=0, s_reason=why)

    # ---- アカウント事故（月次ハザード。せどり稼働中は上乗せ）
    inc = None
    for k in range(T):
        hz = P["hz"] / 12 + (P["s_hz"] / 12 if (S_on and k <= s_active_until) else 0.0)
        if R.random() < hz:
            inc = k; break
    perm = inc is not None and R.random() < P["perm"]
    meta.update(inc=inc, perm=perm)
    def halted(k):
        return inc is not None and (k in (inc, inc + 1) or (perm and k >= inc))

    # ---- せどりの苦情（S-3）・楽天の制限
    if S_on and P["smode"] == "gem" and s_active_until > 0:
        pc = 1 - (1 - P["s_complaint"]) ** (1 / 12)
        for k in range(1, T):
            if k > s_active_until:
                break
            if R.random() < pc:
                meta["complaint"] = k
                s_active_until = k       # その月で止める（翌月から発注なし）
                meta.update(s_stop=k, s_reason="S-3 申し立て")
                break
    rak = None
    if S_on and R.random() < P["s_rakuten"]:
        rak = R.randint(2, 9); meta["rakuten"] = rak

    # ---- 送信（せどりが止まったら翌月から週20通＝案B）
    def send_plan(k):
        use_B = plan["send"] == "B" or (S_on and plan.get("fallback_B", True) and meta["s_stop"] is not None and k > meta["s_stop"])
        return (P["send_B"][k] if use_B else P["send_A"][k]), use_B

    skus = []   # dict(kind, e, r, m, st, rep_from, dead, stopped)
    def new_sku(kind, k0, e_mean, m_mean, m_sd):
        e = lognorm(R, e_mean, 0.6)
        r = e * wm * lognorm(R, P["real"], P["real_sig"])
        m = max(0.03, R.gauss(m_mean, m_sd))
        return dict(kind=kind, e=e, r=r, m=m, st=k0, rep_from=None, dead=False, stopped=False, pw=False, amz=False)

    # 卸：12ヶ月で出る SKU（月2〜8に到着）＋年2は0.7倍の速さ
    sd_ok = R.random() < P["sd_pass"]
    pool = lognorm(R, P["w_pool"], P["w_pool_sig"]) * (1.0 if sd_ok else 0.5)
    for k in range(T):
        lam = pool / 7 if 1 <= k <= 7 else (pool / 12 * P["w_pool_y2"] if k >= 12 else 0.0)
        for _ in range(pois(R, lam)):
            skus.append(new_sku("W", k, P["w_e"], P["w_m"], P["w_msd"]))
    # メーカー：送信→成立→販売開始
    rate = pick(R, P["m_rate"]) * P["m_gate"]
    sent = 0
    est_k = []
    for k in range(T):
        n_plan, use_B = send_plan(k)
        lam = n_plan * P["m_consume"] * (0.35 if low else 1.0)
        n = pois(R, lam)
        n = min(n, max(0, P["send_cap"] - sent))
        meta["sends"].append((n, n_plan))
        for _ in range(n):
            sent += 1
            q = (P["q_B"] if use_B else 1.0) * (P["q300"] if sent > 300 else 1.0)
            if R.random() < rate * q:
                lag = R.triangular(1.3, 3.0, 1.8)
                k0 = k + int(round(lag))
                if k0 >= T:
                    continue
                est_k.append(k0)
                for _ in range(max(1, int(round(lognorm(R, P["m_sku"], 0.45))))):
                    skus.append(new_sku("M", k0, P["m_e"], P["m_m"], P["m_msd"]))
    meta["n_est"] = sum(1 for k0 in est_k if k0 <= 11)
    meta["w_n"] = sum(1 for s in skus if s["kind"] == "W" and s["st"] <= 11)

    # ---- 年2の再開：停止中に成立したメーカーの一部は離れる／既存メーカーの一部も離れる
    if resume is not None:
        for s in skus:
            if s["kind"] == "M" and harvest <= s["st"] < resume and R.random() < P["deferred_maker_loss"]:
                s["stopped"] = True; s["dead"] = True
            elif s["kind"] == "M" and s["st"] < harvest and R.random() < P["resume_maker_loss"]:
                s["stopped_at"] = resume

    # ---- SKU ごとの発注
    early = []
    for s in skus:
        kind = s["kind"]
        h = P["w_h"] if kind == "W" else P["m_h"]
        drift = P["w_drift"] if kind == "W" else P["m_drift"]
        k0 = s["st"]
        if s.get("dead"):
            continue
        # 初回ロット：停止中なら再開月に回す
        while k0 < T and (not can_order(k0) or halted(k0)):
            k0 += 1
        if k0 >= T:
            continue
        e_rev = s["e"]; r_rev = s["r"]
        c = cost_rate(s["m"])
        lot = c * h * e_rev
        if kind == "M":
            lot = max(lot, P["m_minlot"])
        kind1 = "W" if kind == "W" else "M1"
        dead, T1 = first_lot(orders, k0, kind1, lot, s["m"], e_rev, r_rev)
        if k0 <= 3 and len(early) < 3:
            early.append(r_rev / e_rev)
        if dead:
            continue
        r_now = r_rev; m_now = s["m"]
        for k in range(k0 + max(1, int(math.ceil(T1 - 0.5))), T):
            age = k - k0
            if R.random() < P["pw"]:
                m_now -= P["pw_cut"]
            if R.random() < P["amz"]:
                r_now *= P["amz_share"]
            mk_ = m_now - drift * age
            if P["sku_stop_m"] and mk_ < P["sku_stop_m"]:
                break                              # 撤退条件5：実売利益率8%未満 → 補充停止
            if s.get("stopped_at") is not None and k >= s["stopped_at"]:
                break
            if not can_order(k) or halted(k):
                continue
            share = P["resume_share"] if (resume is not None and resume <= k < resume + 3) else 1.0
            amt = cost_rate(mk_) * r_now * share
            orders[k].append((mk("W" if kind == "W" else "M2", mk_, 1.5), amt))
    meta["early_ratio"] = (sum(early) / len(early)) if early else None

    # ---- せどり
    if S_on:
        if P["smode"] == "gem":
            surv = R.uniform(*P["s_surv"])
            m0 = max(0.02, R.gauss(P["s_m"], P["s_msd"]))
            live = []   # (rg, m)
            for k in range(T):
                if k > s_active_until or not can_order(k) or halted(k):
                    if k > s_active_until:
                        break
                    continue
                C = P["s_checks"] * (0.8 if k == 0 else 1.0) * (P["s_fat_f"] if k >= mf else 1.0)
                if k == 0:
                    C += P["trial_checks"]
                hits = h_eff(C) * C * (P["s_rakuten_f"] if (rak is not None and k >= rak) else 1.0)
                n_new = pois(R, hits)
                if k == 0 and meta["s_stop"] == 0:
                    n_new = meta["trial_adopt"]    # 試行で止めた場合は試行ぶんだけ買う
                meta["gems"] += n_new
                m_k = m0 - P["s_drift"] * k
                # 既存の原石の再仕入れ
                nxt = []
                for rg, gm in live:
                    if R.random() < surv:
                        amt = cost_rate(gm) * rg
                        orders[k].append((mk("S", gm, 1.2), amt))
                        meta["s_rev_plan"] += rg
                        nxt.append((rg, gm))
                live = nxt
                for _ in range(n_new):
                    rg = lognorm(R, P["s_rg"], P["s_rg_sig"]) * wm
                    gm = max(0.02, m_k + R.gauss(0, 0.02))
                    if R.random() < P["s_emis"]:           # 入数・別モデルの取り違え → 処分
                        orders[k].append((mk("S", LIQ_M, 1.0, delay=30), P["s_lot"]))
                        continue
                    kb = R.random() < P["s_ek"]            # Keepa 側の需要の誤読 → 実売は読みの2割
                    r_true = rg * (0.2 if kb else 1.0)
                    first_lot(orders, k, "S", P["s_lot"], gm, rg, r_true, dead_rule=kb)
                    meta["s_rev_plan"] += P["s_lot"] / cost_rate(gm)
                    if not kb:
                        live.append((r_true, gm))
        else:   # タケシのせどり：定常月商 s_ss × 立ち上がり
            ss = lognorm(R, P["s_ss"], P["s_ss_sig"]) * wm * g / 0.25
            m0 = max(0.02, R.gauss(P["s_m"], P["s_msd"]))
            for k in range(T):
                if k > s_active_until:
                    break
                if not can_order(k) or halted(k):
                    continue
                ramp = P["s_ramp"][min(k + 1, len(P["s_ramp"]) - 1)] * (P["s_fat_f"] if k >= mf else 1.0)
                rev = ss * ramp * lognorm(R, 1.0, 0.25)
                mm = m0 - P["s_drift"] * k
                orders[k].append((mk("S", mm, 1.3), cost_rate(mm) * rev))
                meta["s_rev_plan"] += rev
    return orders, meta


def run_one(args):
    seed, P, plan, T = args
    R = random.Random(seed)
    orders, meta = gen(R, P, plan, T)
    cfg = cf.Config(months=T, fixed_monthly=[P["fixed"]] * T)
    if meta["inc"] is not None:
        a = cf.nth_month_start(cfg.start, meta["inc"])
        cfg.halt_win = (cf.add(a, -14), cf.add(a, 61))
    def policy(st, k, d):
        req = orders[k]
        if not req:
            return []
        budget = st.cash - cfg.reserve - st.committed_outflows(d) - cfg.fixed_monthly[min(k + 1, cfg.months - 1)]
        tot = sum(a for _, a in req)
        f = 1.0 if tot <= 0 else max(0.0, min(1.0, budget / tot))
        return [(ln, a * f) for ln, a in req if a * f > 0]
    res = cf.simulate(cfg, policy)
    rows = res["rows"]
    cash = res["cum_cash"]
    if meta["perm"]:   # 恒久停止：停止時点の在庫は他販路で原価の40%回収（売上として数えた分を差し戻す）
        dinc = cf.nth_month_start(cfg.start, meta["inc"])
        cash -= 0.65 * res["state"].inventory(dinc)
    out = dict(cash=cash, thin=res["thin_cash"], profit=res["cum_profit"],
               rev=[r["売上"] for r in rows], prof=[r["利益"] for r in rows], inv=[r["在庫"] for r in rows],
               endcash=[r["月末現金"] for r in rows], ar=[r["売掛"] for r in rows], ap=[r["未払"] for r in rows],
               first_payout=str(res["first_payout"]))
    meta.pop("sends_detail", None)
    out.update(meta=meta)
    return out


_POOL = None
def run(P, plan, n, T=12, seed=SEED):
    global _POOL
    if _POOL is None:
        _POOL = mp.get_context("fork").Pool(8)
    args = [(seed * 1000 + i, P, plan, T) for i in range(n)]
    return _POOL.map(run_one, args, chunksize=max(1, n // 64))


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(p * (len(xs) - 1))))]


def man(x):
    return f"{x / 1e4:+.0f}万" if abs(x) >= 5000 else f"{x / 1e4:+.1f}万"


def summ(res):
    c = [r["cash"] for r in res]; n = len(res)
    return dict(p=sum(x > 0 for x in c) / n, p20=q(c, .2), p50=q(c, .5), p80=q(c, .8), p10=q(c, .1),
                pp=sum(r["profit"] > 0 for r in res) / n, prof50=q([r["profit"] for r in res], .5),
                thin10=q([r["thin"] for r in res], .1), breach=sum(r["thin"] < 250_000 for r in res) / n,
                rev9=q([r["rev"][8] for r in res], .5), rev12=q([r["rev"][11] for r in res], .5),
                sstop=sum(1 for r in res if r["meta"]["s_stop"] is not None) / n,
                mean=sum(c) / n)


def row(label, s):
    return (f"| {label} | {s['p']:.0%} | {man(s['p20'])}／{man(s['p50'])}／{man(s['p80'])} | {man(s['p10'])} | {s['pp']:.0%}（{man(s['prof50'])}） "
            f"| {s['thin10'] / 1e4:.0f}万 | {s['breach']:.0%} | {s['rev9'] / 1e4:.0f}万 | {s['sstop']:.0%} |")


HDR = ("| 案・条件 | P(実質現金>0) | 実質現金 P20／中央／P80 | P10 | P(累計損益>0)（中央） | 日次最低現金 P10 | 予備25万割れ | 月9の月商 中央 | せどり停止 |\n"
       "|---|---:|---|---:|---|---:|---:|---:|---:|")

H9 = 9   # k>=9（月10=2027-07 以降）は発注しない
PLANS = {
    "A": dict(lanes="WM", send="A", rule="none", harvest=H9),
    "B": dict(lanes="WM", send="B", rule="none", harvest=H9),
    "C_none": dict(lanes="WMS", send="A", rule="none", harvest=H9),
    "C_written": dict(lanes="WMS", send="A", rule="as_written", harvest=H9),
    "C_redesign": dict(lanes="WMS", send="A", rule="redesign", harvest=H9, adopt_min=3),
}


def main():
    quick = "--quick" in sys.argv
    N = 400 if quick else 3000
    NS = 300 if quick else 1500
    t0 = time.time()
    out = io.StringIO()
    def P_(*a):
        print(*a, file=out); print(*a, flush=True)
    P_(f"# 01_mc 出力（T-20260914-003・マサル）N={N}（感応度 {NS}）seed={SEED}")
    P_("実質現金＝2027-09-30 の現金−未払−200万（ハジメの cum_cash）。月10（2027-07）以降は発注しない（タケシの月10停止）を既定に。")
    P_("")
    keep = {}

    # ---- 1. 主表
    P_("## 1. 案の比較（マサルの置き値）")
    P_(HDR)
    for key, lab in (("A", "案A 週10通"), ("B", "案B 週20通"), ("C_none", "案C せどりを1年続ける（撤退条件なし）"),
                     ("C_written", "案C 撤退条件 S-1/S-2 を書面どおり"), ("C_redesign", "案C 撤退条件を採用率に一本化（2週で3件未満なら停止）")):
        r = run(MASARU, PLANS[key], N); keep[key] = r
        P_(row(lab, summ(r)))
    P_("")

    # ---- 2. タケシの置き値を同じ構造で（モデル差と置き値差の分解）
    P_("## 2. タケシの74%からの分解（1段ずつ置き換え。案C・撤退条件なし→書面どおり）")
    P_(HDR)
    steps = [
        ("0 タケシの置き値（せどり＝定常50万・続かない35%・独立）", TAKESHI, "C_none"),
        ("1 ＋SD 会費0円", dict(TAKESHI, fixed=FIX), "C_none"),
        ("2 ＋相乗りの応手（値下げ・本体参入・8%で補充停止）", dict(TAKESHI, fixed=FIX, pw=MASARU["pw"], amz=MASARU["amz"], sku_stop_m=0.08), "C_none"),
        ("3 ＋卸の母数 6→4", dict(TAKESHI, fixed=FIX, pw=MASARU["pw"], amz=MASARU["amz"], sku_stop_m=0.08, w_pool=4.0), "C_none"),
        ("4 ＋取り分のばらつき σ0.6→0.7・累計300通超の質×0.6", dict(TAKESHI, fixed=FIX, pw=MASARU["pw"], amz=MASARU["amz"], sku_stop_m=0.08, w_pool=4.0, real_sig=0.7, q300=0.6), "C_none"),
        ("5 ＋社長の時間の連動（続かない40%・その世界で送信低稼働50%）", dict(TAKESHI, fixed=FIX, pw=MASARU["pw"], amz=MASARU["amz"], sku_stop_m=0.08, w_pool=4.0, real_sig=0.7, q300=0.6,
                                                   s_fatigue=0.40, low_nofat=0.15, low_fat=0.50, s_hz=0.12), "C_none"),
        ("6 ＋せどりを原石モデルに（採用率2.5%・寿命中央2ヶ月）＝マサル・撤退条件なし", MASARU, "C_none"),
        ("7 ＋撤退条件 S-1/S-2 を書面どおり（止まったら案Bへ）", MASARU, "C_written"),
    ]
    for lab, Pp, key in steps:
        r = run(Pp, PLANS[key], NS)
        P_(row(lab, summ(r)))
    rb = run(TAKESHI, PLANS["B"], NS); P_(row("参考 案B・タケシの置き値", summ(rb)))
    ra = run(TAKESHI, PLANS["A"], NS); P_(row("参考 案A・タケシの置き値", summ(ra)))
    P_("")

    # ---- 3. せどりの寄与
    P_("## 3. せどりの寄与（pt）")
    sa, sb = summ(keep["A"]), summ(keep["B"])
    for key, lab in (("C_none", "案C 1年続ける"), ("C_written", "案C 書面どおり"), ("C_redesign", "案C 一本化")):
        s = summ(keep[key])
        P_(f"- {lab}: 案A比 {100 * (s['p'] - sa['p']):+.0f}pt（中央 {man(s['p50'] - sa['p50'])}）／案B比 {100 * (s['p'] - sb['p']):+.0f}pt（中央 {man(s['p50'] - sb['p50'])}）")
    rc = keep["C_none"]
    sr = [r["meta"]["s_rev_plan"] for r in rc]
    P_(f"- せどりの12ヶ月売上（撤退条件なし）中央 {q(sr, .5) / 1e4:.0f}万（P20 {q(sr, .2) / 1e4:.0f}〜P80 {q(sr, .8) / 1e4:.0f}万）")
    gm = [r["meta"]["gems"] for r in rc]
    P_(f"- 採用した原石の数（12ヶ月）中央 {q(gm, .5)}（P20 {q(gm, .2)}〜P80 {q(gm, .8)}）")
    w = keep["C_written"]
    reasons = {}
    for r in w:
        k = r["meta"]["s_reason"] or "続行"
        reasons[k] = reasons.get(k, 0) + 1
    P_("- 書面どおりの撤退条件で、せどりが止まる理由: " + "、".join(f"{k} {v / len(w):.0%}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])))
    P_("")

    # ---- 4. せどりの前提を1つずつ崩す（マサルの構造・撤退条件なし／タケシの構造）
    P_("## 4. せどりの前提を1つずつ崩す（案C・撤退条件なし・月10停止）")
    P_("| 前提 | タケシの構造（定常月商型） | マサルの構造（原石型） |")
    P_("|---|---:|---:|")
    base_t = dict(TAKESHI, fixed=FIX)
    tests = [
        ("置き値のまま", {}, {}),
        ("定常月商 50→25万／採用率 2.5→1.5%", dict(s_ss=250_000), dict(s_h=0.015)),
        ("ゲートなし率 10% に固定", dict(s_gate=[(0.10, 1.0)]), dict(s_gate=[(0.10, 1.0)])),
        ("利益率 9→6%", dict(s_m=0.06), dict(s_m=0.06)),
        ("目視が続かない 70%", dict(s_fatigue=0.70), dict(s_fatigue=0.70)),
        ("楽天の制限 50%", {}, dict(s_rakuten=0.5)),
        ("Keepa 側の誤読 15→35%・取り違え 5→12%", {}, dict(s_ek=0.35, s_emis=0.12)),
        ("原石の寿命が長い（再仕入れ継続 0.65〜0.8）", {}, dict(s_surv=(0.65, 0.80))),
        ("採用率 5%（生値並み）", {}, dict(s_h=0.05)),
        ("悪い側を3つ重ねる（25万/1.5%・続かない70%・利益率6%）", dict(s_ss=250_000, s_fatigue=0.70, s_m=0.06), dict(s_h=0.015, s_fatigue=0.70, s_m=0.06)),
    ]
    for lab, ot, om in tests:
        a = summ(run(dict(base_t, **ot), PLANS["C_none"], NS)) if (ot or lab == "置き値のまま") else None
        b = summ(run(dict(MASARU, **om), PLANS["C_none"], NS))
        P_(f"| {lab} | {('%d%%' % round(100 * a['p'])) + '（' + man(a['p50']) + '）' if a else '—'} | {b['p']:.0%}（{man(b['p50'])}） |")
    P_("")

    # ---- 5. マサルの感応度（案C 一本化）
    P_("## 5. 感応度（案C・撤退条件を採用率に一本化・1変数ずつ）")
    P_("| 変数 | 悲観側 | 置き値 | 楽観側 |")
    P_("|---|---|---|---|")
    b0 = summ(keep["C_redesign"])
    sens = [
        ("取り分の実現（0.85倍）", dict(real=0.5), dict(real=1.2)),
        ("メーカー成立率（混合）", dict(m_rate=[(0.015, 1.0)]), dict(m_rate=[(0.05, 1.0)])),
        ("卸の母数（4）", dict(w_pool=2.0), dict(w_pool=10.0)),
        ("せどり採用率（2.5%）", dict(s_h=0.015), dict(s_h=0.05)),
        ("目視が続かない（40%）", dict(s_fatigue=0.70), dict(s_fatigue=0.15)),
        ("メーカー直の利益率（12%）", dict(m_m=0.08), dict(m_m=0.16)),
        ("アカウント事故（年5%＋せどり12%）", dict(hz=0.15, s_hz=0.25), dict(hz=0.02, s_hz=0.03)),
        ("値下げ応酬（月2%・−3pt）", dict(pw=0.06), dict(pw=0.0)),
    ]
    for lab, lo, hi in sens:
        a = summ(run(dict(MASARU, **lo), PLANS["C_redesign"], NS)); c = summ(run(dict(MASARU, **hi), PLANS["C_redesign"], NS))
        P_(f"| {lab} | {a['p']:.0%}／{man(a['p50'])} | {b0['p']:.0%}／{man(b0['p50'])} | {c['p']:.0%}／{man(c['p50'])} |")
    P_("")

    # ---- 6. 発注停止の月
    P_("## 6. 発注停止の月（案C 一本化）と、停止しない場合")
    P_(HDR)
    for hv, lab in ((8, "月9から停止（k≥8）"), (9, "月10から停止（既定）"), (10, "月11から停止"), (None, "停止しない")):
        pl = dict(PLANS["C_redesign"], harvest=hv)
        P_(row(lab, summ(run(MASARU, pl, NS))))
    P_("")

    # ---- 7. 撤退条件の「中央で踏む確率」（案C 書面どおり／一本化）
    P_("## 7. 撤退条件を踏む確率")
    for key in ("C_written", "C_redesign", "B"):
        res = keep[key]; n = len(res)
        pr = lambda f: sum(1 for r in res if f(r)) / n
        cum = lambda r, t: sum(r["prof"][:t])
        P_(f"### {key}")
        P_(f"- 1 期間中の日次現金 <60万: {pr(lambda r: r['thin'] < 600_000):.0%}")
        P_(f"- 2 2026-12末まで売上0: {pr(lambda r: sum(r['rev'][:3]) < 1):.0%}")
        P_(f"- 3 2027-03末 累計損益 <−10万: {pr(lambda r: cum(r, 6) < -100_000):.0%}")
        P_(f"- 4 2027-06末 累計損益 <−10万: {pr(lambda r: cum(r, 9) < -100_000):.0%}")
        def low2(r):
            s = r["meta"]["sends"]
            return any(s[i][0] < 0.5 * s[i][1] and s[i + 1][0] < 0.5 * s[i + 1][1] for i in range(1, 11))
        P_(f"- 6 送信が2ヶ月続けて計画の50%未満（12ヶ月で1回以上）: {pr(low2):.0%}")
        if "S" in PLANS[key]["lanes"]:
            P_(f"- S-1 50件中ゲートなし4件以下: {pr(lambda r: r['meta']['trial_gate'] <= 4):.0%}")
            P_(f"- S-2 2週の採用10件未満: {pr(lambda r: r['meta']['trial_adopt'] < 10):.0%}")
            P_(f"- 一本化案 2週の採用3件未満: {pr(lambda r: r['meta']['trial_adopt'] < 3):.0%}")
            P_(f"- S-3 12ヶ月内に申し立て1件（せどり稼働中）: {pr(lambda r: r['meta']['complaint'] is not None):.0%}")
        P_(f"- 月9末 累計損益 ≥+10万: {pr(lambda r: cum(r, 9) >= 100_000):.0%}")
        P_(f"- アカウント事故: {pr(lambda r: r['meta']['inc'] is not None):.0%}（恒久 {pr(lambda r: r['meta']['perm']):.0%}）")
        P_(f"- W8 の取り分の実現（最初の3 SKU 平均）<0.5: {pr(lambda r: r['meta']['early_ratio'] is not None and r['meta']['early_ratio'] < 0.5):.0%}／SKU が月3までに無い: {pr(lambda r: r['meta']['early_ratio'] is None):.0%}")
        P_("")

    # ---- 8. S-1 はゲートなし10%の世界で発動するか
    P_("## 8. S-1（ゲートなし率）の判定力と、せどりの価値")
    rw = run(dict(MASARU), PLANS["C_none"], N)
    rb2 = keep["B"]
    for gv in (0.10, 0.25, 0.45):
        sub = [r for r in rw if abs(r["meta"]["g"] - gv) < 1e-9]
        if not sub:
            continue
        fire = sum(1 for r in sub if r["meta"]["trial_gate"] <= 4) / len(sub)
        s = summ(sub)
        P_(f"- ゲートなし {gv:.0%} の世界（{len(sub)}経路）: S-1 発動 {fire:.0%}／せどり継続時の P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}（案B {summ(rb2)['p']:.0%}・{man(summ(rb2)['p50'])}）")
    for lo, hi, lab in ((0, 3, "2週の採用 0〜2件"), (3, 6, "3〜5件"), (6, 10, "6〜9件"), (10, 999, "10件以上")):
        sub = [r for r in rw if lo <= r["meta"]["trial_adopt"] < hi]
        if sub:
            s = summ(sub)
            P_(f"- {lab}（{len(sub) / len(rw):.0%}）: せどり継続の P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}")
    P_("")

    # ---- 9. 早期の実測で分かれる確度（W8）
    P_("## 9. W8（11/6）の実測で確度はどう分かれるか（案C 一本化）")
    res = keep["C_redesign"]
    groups = [("最初の SKU の実現 ≥0.7", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] >= 0.7),
              ("最初の SKU の実現 0.4〜0.7", lambda r: r["meta"]["early_ratio"] is not None and 0.4 <= r["meta"]["early_ratio"] < 0.7),
              ("最初の SKU の実現 <0.4", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.4),
              ("月3までに SKU が立たない", lambda r: r["meta"]["early_ratio"] is None)]
    for lab, f in groups:
        sub = [r for r in res if f(r)]
        if sub:
            s = summ(sub)
            P_(f"- {lab}（{len(sub) / len(res):.0%}）: P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}・P10 {man(s['p10'])}")
    sub = [r for r in res if r["meta"]["n_est"] >= 3]
    P_(f"- 参考 成立3社以上（12ヶ月内）: {len(sub) / len(res):.0%}")
    P_("")

    # ---- 10. 失敗した世界の内訳（案C 一本化）
    P_("## 10. 実質現金がマイナスの世界に、何が起きていたか（案C 一本化）")
    bad = [r for r in res if r["cash"] <= 0]; good = [r for r in res if r["cash"] > 0]
    feats = [("取り分の実現（最初の SKU）<0.5", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.5),
             ("月3までに SKU が立たない", lambda r: r["meta"]["early_ratio"] is None),
             ("成立 2社以下", lambda r: r["meta"]["n_est"] <= 2),
             ("卸の SKU 2以下", lambda r: r["meta"]["w_n"] <= 2),
             ("送信の低稼働", lambda r: r["meta"]["low"]),
             ("せどりの目視が続かない", lambda r: r["meta"]["fatigue"]),
             ("せどりが試行で停止", lambda r: r["meta"]["s_stop"] == 0),
             ("せどり採用率 <2%", lambda r: (r["meta"]["h"] or 0) < 0.02),
             ("アカウント事故", lambda r: r["meta"]["inc"] is not None),
             ("楽天の制限", lambda r: r["meta"]["rakuten"] is not None),
             ("申し立て（S-3）", lambda r: r["meta"]["complaint"] is not None)]
    P_(f"| 特徴 | マイナスの世界（{len(bad)}） | プラスの世界（{len(good)}） | 倍率 |")
    P_("|---|---:|---:|---:|")
    for lab, f in feats:
        a = sum(1 for r in bad if f(r)) / max(1, len(bad)); b = sum(1 for r in good if f(r)) / max(1, len(good))
        P_(f"| {lab} | {a:.0%} | {b:.0%} | {(a / b) if b > 0 else float('nan'):.1f} |")
    P_("")

    # ---- 11. 年2（24ヶ月）: 月10停止→月13再開 vs 続ける
    P_("## 11. 発注停止の年2への損失（24ヶ月・案C 一本化／案B）")
    P_("| 案 | 運用 | 12ヶ月の実質現金 中央（P） | 年2の月商 中央（月13／月15／月18／月24） | 年2の利益 中央 | 24ヶ月の実質現金 中央 | 24ヶ月の累計損益 中央 |")
    P_("|---|---|---|---|---:|---:|---:|")
    for key in ("C_redesign", "B"):
        for hv, rs, lab in ((H9, 12, "月10〜12停止→月13再開"), (None, None, "続ける")):
            pl = dict(PLANS[key], harvest=hv, resume=rs)
            r24 = run(MASARU, pl, NS, T=24)
            # 12ヶ月時点の実質現金は 24ヶ月計算の途中値＝月12末の現金−未払−200万
            c12 = [r["endcash"][11] - r["ap"][11] - 2_000_000 for r in r24]
            y2p = [sum(r["prof"][12:]) for r in r24]
            c24 = [r["cash"] for r in r24]
            pr24 = [r["profit"] for r in r24]
            revm = lambda m: q([r["rev"][m - 1] for r in r24], .5) / 1e4
            P_(f"| {key} | {lab} | {man(q(c12, .5))}（{sum(x > 0 for x in c12) / len(c12):.0%}） | {revm(13):.0f}／{revm(15):.0f}／{revm(18):.0f}／{revm(24):.0f}万 "
               f"| {man(q(y2p, .5))} | {man(q(c24, .5))} | {man(q(pr24, .5))} |")
            keep[f"y2_{key}_{lab}"] = r24
    P_("")

    # ---- 12. 3シナリオの代表経路（日次）
    P_("## 12. 3シナリオの代表経路（案C 一本化・実質現金の P20／中央／P80 に最も近い経路を cf_base で表示）")
    res = keep["C_redesign"]
    order = sorted(range(len(res)), key=lambda i: res[i]["cash"])
    reps = {}
    for p, lab in ((0.2, "悲観（P20）"), (0.5, "中央"), (0.8, "楽観（P80）")):
        i = order[int(p * (len(order) - 1))]
        reps[lab] = i
        r = res[i]; m = r["meta"]
        P_(f"### {lab}: 実質現金 {man(r['cash'])}・累計損益 {man(r['profit'])}・日次最低 {r['thin'] / 1e4:.0f}万・初回入金 {r['first_payout']}")
        P_(f"- 経路の中身: 卸SKU {m['w_n']}・成立 {m['n_est']}社・せどり {'停止(' + m['s_reason'] + ')' if m['s_stop'] is not None else '継続'}・原石 {m['gems']}件・目視 {'途中で減る' if m['fatigue'] else '続く'}・送信 {'低稼働' if m['low'] else '通常'}・事故 {'あり' if m['inc'] is not None else 'なし'}")
        P_("| 月 | 売上 | 利益 | 月末現金 | 在庫 | 売掛 | 未払 |")
        P_("|---|---:|---:|---:|---:|---:|---:|")
        names = [f"2026-{m_:02d}" for m_ in (10, 11, 12)] + [f"2027-{m_:02d}" for m_ in range(1, 10)]
        for t in range(12):
            P_(f"| {names[t]} | {r['rev'][t] / 1e4:.1f} | {r['prof'][t] / 1e4:+.1f} | {r['endcash'][t] / 1e4:.1f} | {r['inv'][t] / 1e4:.1f} | {r['ar'][t] / 1e4:.1f} | {r['ap'][t] / 1e4:.1f} |")
        P_("")
    # 4軸×3シナリオ（分位）
    P_("### 4軸×3シナリオ（案C 一本化・各軸の P20／中央／P80）")
    rv = lambda t: [r["rev"][t] for r in res]
    P_(f"- 月商（2027-06＝発注停止前の最大月）: {q(rv(8), .2) / 1e4:.0f}／{q(rv(8), .5) / 1e4:.0f}／{q(rv(8), .8) / 1e4:.0f}万")
    P_(f"- 累計損益: {man(q([r['profit'] for r in res], .2))}／{man(q([r['profit'] for r in res], .5))}／{man(q([r['profit'] for r in res], .8))}")
    P_(f"- 実質現金: {man(q([r['cash'] for r in res], .2))}／{man(q([r['cash'] for r in res], .5))}／{man(q([r['cash'] for r in res], .8))}")
    P_(f"- 日次最低現金: {q([r['thin'] for r in res], .2) / 1e4:.0f}／{q([r['thin'] for r in res], .5) / 1e4:.0f}／{q([r['thin'] for r in res], .8) / 1e4:.0f}万")
    P_(f"- 成立社数（12ヶ月内）: {q([r['meta']['n_est'] for r in res], .2)}／{q([r['meta']['n_est'] for r in res], .5)}／{q([r['meta']['n_est'] for r in res], .8)}")
    P_("")
    P_(f"所要 {time.time() - t0:.0f}秒")
    if not quick:
        (HERE / "01_mc_出力.txt").write_text(out.getvalue())


if __name__ == "__main__":
    main()
