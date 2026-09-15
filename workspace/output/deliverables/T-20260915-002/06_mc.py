"""T-20260915-002 / 06 真似する計画 — 12ヶ月の簡易モンテカルロ（タケシ）

置き値は実践者の公開数字（01・03・05）から取る。当社の実測は母数の上限にだけ使う。
マサルの本検証の前の、桁と順位を見るための道具。乱数シード 20260915。

月 t=0..11 は 2026-10 .. 2027-09。単位は万円。
"""
import numpy as np

SEED = 20260915
N = 20000
T = 12
RESERVE = 25.0          # 予備（割らない）
CAPITAL = 200.0         # 運転資金
FIXED_A = 1.51          # 大口 0.539 + Keepa API 0.87 + ネットFAX 0.1（推測）
RAIJIN_M = 0.98         # 雷神 月額（03 S30）
RAIJIN_INIT = 2.5       # 雷神 初期（03 S30・中央）
TEST_COST = 2.0         # 1社目の初回ロット（5個×1〜2SKU・01 §3.4）
TEST_FAIL = 0.30        # 初回で売れず取引が続かない割合（推測）
TEST_LOSS = 0.6         # 失敗時の損失（売り切りで原価の3割）
ATTR = 0.04             # 取引が続かなくなる月率（値崩れ等・推測）
RAMP = [0.3, 0.65]      # 取引開始後1・2ヶ月目の立ち上がり（初回5個→リピート）
F_INV = 0.74            # 運転資金のうち在庫の比率（在庫1.35×原価0.54 : 売掛0.26）
MARGIN = 0.10           # 型A の利益率（01: 10〜12%。納品代行費で−1〜2pt）


def lognorm(median, p80_ratio, size, rng):
    sigma = np.log(p80_ratio) / 0.8416
    return median * np.exp(sigma * rng.standard_normal(size))


def simulate(plan, stop_month=None, rng=None):
    """plan: 'A' 月300通 / 'B' 型A 月150通＋電脳リピート / 'C' 月130通（既定の週30通）"""
    rng = rng or np.random.default_rng(SEED)
    # 世界ごとの共通の置き値
    p = np.clip(lognorm(0.02, 1.75, N, rng), 0.003, 0.08)      # 成約率/通（中央2%・P80 3.5%・P20 1.1%）
    g = lognorm(0.70, 1.45, N, rng)                             # 1社の定常月利（01: 0.7〜1万・S11）
    r = lognorm(7.5, 1.33, N, rng)                              # 運転資金÷月利（01 社内記録: 5〜7.5＋売掛）
    pool = lognorm(2000, 2.0, N, rng)                           # 3基準を満たす中小メーカーの母数（推測・未計測）
    stall = rng.random(N) < 0.20                                # 送信が続かない世界（前科：4ヶ月で0通）
    if plan == 'A':
        base = np.array([150] + [300] * (T - 1), float)
        stall_mult, fixed, acc_year = 0.4, FIXED_A, 0.05
    elif plan == 'C':
        base = np.array([60] + [130] * (T - 1), float)
        stall_mult, fixed, acc_year = 0.5, FIXED_A, 0.05
    elif plan == 'B':
        base = np.array([80] + [150] * (T - 1), float)
        stall_mult, fixed, acc_year = 0.5, FIXED_A + RAIJIN_M, 0.12
    else:
        raise ValueError(plan)
    # 電脳リピート（案B のみ）：定常月利 中央3万（05 S1: 1年以内 月1〜3万が最多帯）
    d = lognorm(3.0, 2.1, N, rng) if plan == 'B' else np.zeros(N)
    r_e = 6.7                                                   # せどり：回転1ヶ月＋売掛0.5ヶ月（03 §2-3）
    # アカウント事故（2ヶ月止まる）
    acc = rng.random(N) < acc_year
    acc_m = rng.integers(0, T - 1, N)

    cash = np.full(N, CAPITAL)
    cum_profit = np.zeros(N); cum_fixed = np.zeros(N); cum_loss = np.zeros(N)
    wc = np.zeros(N)
    used = np.zeros(N)
    cohorts = []            # (開始月, 社数)
    active_hist = np.zeros((T, N)); new_hist = np.zeros((T, N)); profit_hist = np.zeros((T, N))
    min_cash = np.full(N, CAPITAL)
    prev_sends = np.zeros(N)
    fails_due = np.zeros((T + 3, N))
    for t in range(T):
        sends = base[t] * np.where(stall & (t >= 1), stall_mult, 1.0)
        if stop_month is not None and t >= stop_month:
            sends = np.zeros(N)
        sends = np.minimum(sends, np.maximum(pool - used, 0))
        # 成約：前月の送信から（1ヶ月の遅れ）。良い先から送るので母数を使うほど率が落ちる
        p_eff = p * (1 - 0.5 * np.minimum(used / pool, 1))
        new = rng.binomial(prev_sends.astype(int), np.clip(p_eff, 0, 1))
        if stop_month is not None and t >= stop_month:
            new = np.zeros(N, int)
        used += sends
        prev_sends = sends
        fail = rng.binomial(new, TEST_FAIL)
        fails_due[t + 2] += fail
        cohorts.append((t, new - fail))
        new_hist[t] = new
        # 需要（利益ベース）
        demand = np.zeros(N)
        active = np.zeros(N)
        for (t0, n0) in cohorts:
            age = t - t0 - 1            # 翌月から売れ始める
            if age < 0:
                continue
            surv = n0 * (1 - ATTR) ** age
            ramp = RAMP[age] if age < len(RAMP) else 1.0
            demand += surv * g * ramp
            active += surv
        if plan == 'B':
            e = np.where(t < 2, -1.0, np.where(t == 2, 0.3 * d, d))
        else:
            e = np.zeros(N)
        # 発注停止後：在庫で売れるのは 1.35ヶ月分
        if stop_month is not None and t >= stop_month:
            cover = 1.0 if t == stop_month else 0.35 if t == stop_month + 1 else 0.0
            demand = demand * cover
            e = np.where(e > 0, e * cover, e)
        # 運転資金の上限（予備を割らない）
        wc_req = r * demand + TEST_COST * new + r_e * np.maximum(e, 0)
        if stop_month is not None and t >= stop_month:
            wc_req = (1 - F_INV) * (r * demand + r_e * np.maximum(e, 0))   # 売掛だけ残る
        avail = CAPITAL + cum_profit - cum_fixed - cum_loss - RESERVE
        scale = np.where(wc_req > avail, np.maximum(avail, 0) / np.maximum(wc_req, 1e-9), 1.0)
        profit = scale * demand + np.where(e > 0, scale * e, e)
        wc_new = np.minimum(wc_req, np.maximum(avail, 0))
        # 事故：2ヶ月売上0（在庫は残る）
        hit = acc & ((t == acc_m) | (t == acc_m + 1))
        profit = np.where(hit, 0.0, profit)
        wc_new = np.where(hit, wc, wc_new)
        fx = fixed + (RAIJIN_INIT if (plan == 'B' and t == 0) else 0)
        loss = fails_due[t] * TEST_LOSS
        cum_profit += profit; cum_fixed += fx; cum_loss += loss
        cash = cash + profit - fx - loss - (wc_new - wc)
        wc = wc_new
        min_cash = np.minimum(min_cash, cash)
        active_hist[t] = active; profit_hist[t] = profit
    pl = cum_profit - cum_fixed - cum_loss                      # 累計損益（在庫は原価で資産）
    real = cash - CAPITAL                                       # 実質現金（在庫・未入金を数えない）
    liq = real + wc * (F_INV * 0.8 + (1 - F_INV))               # 清算価値（在庫を原価の80%で回収）
    assert np.allclose(real, pl - wc, atol=1e-6), '恒等式 現金−開始＝累計損益−運転資金 が崩れた'
    return dict(pl=pl, real=real, liq=liq, min_cash=min_cash,
                m12=profit_hist[T - 1] - fixed, m6=profit_hist[5] - fixed,
                m3=profit_hist[2] - fixed, active12=active_hist[T - 1],
                cum_new=new_hist.sum(0), sales12=profit_hist[T - 1] / MARGIN,
                new_w8=new_hist[:2].sum(0) + 0.0, wc12=wc,
                new_m3=new_hist[:3].sum(0) + 0.0, p=p, pool=pool, g=g, stall=stall)


def q(x):
    return np.percentile(x, [20, 50, 80])


def report():
    rows = []
    for plan in ['A', 'B', 'C']:
        s = simulate(plan, rng=np.random.default_rng(SEED))
        st = simulate(plan, stop_month=10, rng=np.random.default_rng(SEED))
        rows.append((plan, s, st))
    print('案 | P(清算価値>0) | 清算価値 P20/中央/P80 | P(累計損益>0) | P(実質現金>0) 継続 | P(実質現金>0) 月10停止 | 実質(停止) 中央 | 最薄の現金 P10')
    for plan, s, st in rows:
        print(plan, f"{(s['liq']>0).mean():.0%}", np.round(q(s['liq']), 1), f"{(s['pl']>0).mean():.0%}",
              f"{(s['real']>0).mean():.0%}", f"{(st['real']>0).mean():.0%}", round(float(np.median(st['real'])), 1),
              round(float(np.percentile(s['min_cash'], 10)), 1))
    print('\n案 | 月利(固定費後) 3ヶ月 / 6ヶ月 / 12ヶ月 [P20,中央,P80] | 12ヶ月 月商 | 累計成約 | 12ヶ月 取引中 | 運転資金12')
    for plan, s, st in rows:
        print(plan, np.round(q(s['m3']), 1), np.round(q(s['m6']), 1), np.round(q(s['m12']), 1),
              np.round(q(s['sales12']), 0), np.round(q(s['cum_new']), 0), np.round(q(s['active12']), 0),
              np.round(q(s['wc12']), 0))
    # 資本上限：天井に当たった世界の比率
    s = rows[0][1]
    print('\n案A 12ヶ月の運転資金が上限（175万）の95%以上の世界:', f"{(s['wc12'] >= 0.95*(175+s['pl'])).mean():.0%}")


if __name__ == '__main__':
    report()
