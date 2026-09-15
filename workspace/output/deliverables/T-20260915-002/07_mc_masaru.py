"""T-20260915-002 / 07 マサル仮想実行 — 独立モデル（06_mc.py とは別の作り）

06_mc.py との構造の違い（切り替えフラグで1つずつ戻せる）:
  lag     : 成約の遅れ。06 は送信の翌月に100%。ここは翌月50%・2ヶ月後35%・3ヶ月後15%（見積→テスト発注の往復・推測）
  wc      : 運転資金。06 は月利×r（中央7.5）。ここは在庫1.35ヶ月×原価率0.55＋入金待ち0.5ヶ月×入金率0.65＝月商×1.07＝月利×10.7
  erosion : 相乗りの値崩れ。06 は取引の離脱4%/月のみ。ここは加えて1社の利益が年0〜40%目減り（世界ごと一様・中央20%・推測。
            利益率10%なら売価−2%で利益−20%）
  regime  : 送信が続かない世界。06 は20%・送信×0.4。ここは30%・×0.35（simulator memory の既定・前科=4ヶ月0通）
  pool    : メーカーの母数。06 は対数正規 中央2,000。ここは固定値で世界を分ける（T-20260915-003 の実測を受けて）
  after   : 母数が尽きた後。none=止まる／second=一巡した先に3ヶ月以上あけて2通目（成約率×0.3・推測）／replen=名簿の補充 月R社

単位は万円。月 t=0..11 は 2026-10..2027-09。乱数シード 20260916。
"""
import sys
import numpy as np

SEED = 20260916
N = 20000
T = 12
CAPITAL, RESERVE = 200.0, 25.0
FIXED = 1.51
TEST_COST, TEST_FAIL, TEST_LOSS = 2.0, 0.30, 0.6
ATTR = 0.04
RAMP = [0.3, 0.65]
MARGIN = 0.10
INV_SHARE_MINE = 0.7425 / 1.0675      # 運転資金のうち在庫（清算で80%回収）
INV_SHARE_TAKESHI = 0.74


def lognorm(median, p80_ratio, size, rng):
    sigma = np.log(p80_ratio) / 0.8416
    return median * np.exp(sigma * rng.standard_normal(size))


def simulate(plan='A', lag=True, wc='mine', erosion=True, regime='mine', pool=None,
             after='none', replen=100, p_fixed=None, g_fixed=None, stop_month=None,
             seed=SEED, n=N):
    rng = np.random.default_rng(seed)
    p = np.clip(lognorm(0.02, 1.75, n, rng), 0.003, 0.08) if p_fixed is None else np.full(n, p_fixed)
    g = lognorm(0.70, 1.45, n, rng) if g_fixed is None else np.full(n, g_fixed)
    if wc == 'takeshi':
        k = lognorm(7.5, 1.33, n, rng); inv_share = INV_SHARE_TAKESHI
    else:
        k = np.full(n, (1.35 * 0.55 + 0.5 * 0.65) / MARGIN); inv_share = INV_SHARE_MINE
    pl_ = lognorm(2000, 2.0, n, rng) if pool is None else np.full(n, float(pool))
    if regime == 'takeshi':
        stall = rng.random(n) < 0.20; smult = 0.4
    else:
        stall = rng.random(n) < 0.30; smult = 0.35
    ero = rng.uniform(0, 0.4, n) if erosion else np.zeros(n)
    acc = rng.random(n) < 0.05
    acc_m = rng.integers(0, T - 1, n)
    base = {'A': [150] + [300] * (T - 1), 'C': [60] + [130] * (T - 1)}[plan]
    lagw = [0.50, 0.35, 0.15] if lag else [1.0]

    cash = np.full(n, CAPITAL); wcur = np.zeros(n)
    cum_pl = np.zeros(n)
    used1 = np.zeros(n); used2 = np.zeros(n); pool_now = pl_.copy()
    closed_total = np.zeros(n)
    sched = np.zeros((T + 4, n))            # 成約の予定
    fails_due = np.zeros((T + 4, n))
    cohorts = []
    exhaust_m = np.full(n, 99)
    min_cash = np.full(n, CAPITAL)
    hist = {k_: np.zeros((T, n)) for k_ in ['profit', 'new', 'active', 'sends']}
    first_round_done_m = np.full(n, 99)
    for t in range(T):
        if after == 'replen' and t >= 3:
            pool_now = pool_now + replen
        want = base[t] * np.where(stall & (t >= 1), smult, 1.0)
        if stop_month is not None and t >= stop_month:
            want = np.zeros(n)
        s1 = np.minimum(want, np.maximum(pool_now - used1, 0))
        s2 = np.zeros(n)
        if after == 'second':
            rest = want - s1
            ok = (first_round_done_m <= t - 3)
            avail2 = np.maximum(used1 - closed_total - used2, 0) * ok
            s2 = np.minimum(rest, avail2)
        p1 = p * (1 - 0.5 * np.minimum(used1 / pool_now, 1))
        c1 = rng.binomial(s1.astype(int), np.clip(p1, 0, 1))
        c2 = rng.binomial(s2.astype(int), np.clip(p * 0.3 * (1 - 0.5 * np.minimum(used2 / pl_, 1)), 0, 1))
        c = c1 + c2
        used1 += s1; used2 += s2
        newly = (used1 >= pool_now - 0.5) & (first_round_done_m == 99)
        first_round_done_m = np.where(newly, t, first_round_done_m)
        exhaust_m = np.where((s1 + s2 < want - 0.5) & (exhaust_m == 99) & (want > 0), t, exhaust_m)
        if len(lagw) == 1:
            sched[t + 1] += c
        else:
            parts = rng.multinomial(c, lagw) if False else None
            a = rng.binomial(c, lagw[0]); rest_ = c - a
            b = rng.binomial(rest_, lagw[1] / (lagw[1] + lagw[2]))
            sched[t + 1] += a; sched[t + 2] += b; sched[t + 3] += rest_ - b
        hist['sends'][t] = s1 + s2
        new = sched[t].astype(int)
        if stop_month is not None and t >= stop_month:
            new = np.zeros(n, int)
        closed_total += new
        fail = rng.binomial(new, TEST_FAIL)
        fails_due[t + 2] += fail
        cohorts.append((t, new - fail))
        demand = np.zeros(n); active = np.zeros(n)
        for (t0, n0) in cohorts:
            age = t - t0 - 1
            if age < 0:
                continue
            surv = n0 * (1 - ATTR) ** age
            ramp = RAMP[age] if age < len(RAMP) else 1.0
            demand += surv * g * ramp * (1 - ero * age / 12)
            active += surv
        if stop_month is not None and t >= stop_month:
            cover = 1.0 if t == stop_month else (0.35 if t == stop_month + 1 else 0.0)
            demand = demand * cover
        req = k * demand + TEST_COST * new
        if stop_month is not None and t >= stop_month:
            req = (1 - inv_share) * k * demand
        avail = cash + wcur - RESERVE
        scale = np.where(req > avail, np.maximum(avail, 0) / np.maximum(req, 1e-9), 1.0)
        profit = scale * demand
        wnew = np.minimum(req, np.maximum(avail, 0))
        hit = acc & ((t == acc_m) | (t == acc_m + 1))
        profit = np.where(hit, 0.0, profit); wnew = np.where(hit, wcur, wnew)
        loss = fails_due[t] * TEST_LOSS
        cum_pl += profit - FIXED - loss
        cash = cash + profit - FIXED - loss - (wnew - wcur)
        wcur = wnew
        min_cash = np.minimum(min_cash, cash)
        hist['profit'][t] = profit; hist['new'][t] = new; hist['active'][t] = active
    real = cash - CAPITAL
    liq = real + wcur * (inv_share * 0.8 + (1 - inv_share))
    assert np.allclose(real, cum_pl - wcur, atol=1e-6)
    return dict(liq=liq, real=real, pl=cum_pl, min_cash=min_cash, m12=hist['profit'][T - 1] - FIXED,
                m6=hist['profit'][5] - FIXED, sales12=hist['profit'][T - 1] / MARGIN,
                cum_new=hist['new'].sum(0), new_by_dec=hist['new'][:3].sum(0), active12=hist['active'][T - 1],
                sends=hist['sends'].sum(0), exhaust_m=exhaust_m, stall=stall, p=p, wc12=wcur,
                new_hist=hist['new'], profit_hist=hist['profit'])


def summ(r):
    q = lambda x: np.percentile(x, [20, 50, 80])
    return (f"P(清算>0) {np.mean(r['liq'] > 0):4.0%} 清算中央 {np.median(r['liq']):6.1f} | "
            f"P(累計損益>0) {np.mean(r['pl'] > 0):4.0%} | P(現金>0) {np.mean(r['real'] > 0):4.0%} | "
            f"月利12 {np.round(q(r['m12']), 1)} | 月商12中央 {np.median(r['sales12']):5.0f} | "
            f"累計成約 {np.round(q(r['cum_new']), 0)} | 送信中央 {np.median(r['sends']):5.0f} | 最薄P10 {np.percentile(r['min_cash'], 10):5.1f}")


def main():
    out = []
    pr = lambda s: (print(s), out.append(s))
    tk = dict(lag=False, wc='takeshi', erosion=False, regime='takeshi', pool=None)
    pr('## R 再現（自分の構造・タケシの置き値）')
    for plan in ['A', 'C']:
        pr(f'{plan}: ' + summ(simulate(plan, **tk)))
        pr(f'{plan} 月10停止: P(現金>0) {np.mean(simulate(plan, stop_month=10, **tk)["real"] > 0):.0%}')

    pr('\n## D 分解（案A・1つずつ自分の値へ）')
    steps = [('タケシの置き値', tk),
             ('+成約の遅れ', dict(tk, lag=True)),
             ('+運転資金10.7倍', dict(tk, lag=True, wc='mine')),
             ('+値崩れ', dict(tk, lag=True, wc='mine', erosion=True)),
             ('+送信停滞30%', dict(tk, lag=True, wc='mine', erosion=True, regime='mine'))]
    for name, kw in steps:
        pr(f'{name:12s}: ' + summ(simulate('A', **kw)))

    mine = dict(lag=True, wc='mine', erosion=True, regime='mine')
    pr('\n## P 母数の世界（案A・マサルの構造）')
    for pool in [250, 500, 994, 1500, 2331, 3000]:
        for after in ['none', 'second', 'replen']:
            r = simulate('A', pool=pool, after=after, **mine)
            ex = r['exhaust_m']
            pr(f'母数{pool:5d} {after:6s}: ' + summ(r) + f' | 枯渇月中央 {np.median(ex):4.0f}（尽きない {np.mean(ex == 99):.0%}）')
    pr('\n## P2 母数の世界・案C（週30通）')
    for pool in [250, 500, 994, 2331]:
        pr(f'C 母数{pool:5d} second: ' + summ(simulate('C', pool=pool, after='second', **mine)))

    pr('\n## Q 成約率の固定世界（案A・母数994・2通目あり）')
    for pf in [0.01, 0.015, 0.02, 0.03, 0.04]:
        pr(f'成約率{pf:.1%}: ' + summ(simulate('A', pool=994, after='second', p_fixed=pf, **mine)))
    pr('\n## Q2 実践者の率（成約4%・1社1万）')
    for pool in [994, 2331]:
        pr(f'母数{pool}: ' + summ(simulate('A', pool=pool, after='second', p_fixed=0.04, g_fixed=1.0, **mine)))

    pr('\n## M 物差し（案A・母数994・2通目）発注停止月別の P(現金>0)')
    for sm in [None, 7, 8, 9, 10, 11]:
        r = simulate('A', pool=994, after='second', stop_month=sm, **mine)
        pr(f'停止月{sm}: P(現金>0) {np.mean(r["real"] > 0):.0%} 現金中央 {np.median(r["real"]):6.1f} | P(清算>0) {np.mean(r["liq"] > 0):.0%} | P(累計損益>0) {np.mean(r["pl"] > 0):.0%}')
    pr('\n## M2 物差し（案A・母数2331・2通目）')
    for sm in [None, 10]:
        r = simulate('A', pool=2331, after='second', stop_month=sm, **mine)
        pr(f'停止月{sm}: P(現金>0) {np.mean(r["real"] > 0):.0%} 現金中央 {np.median(r["real"]):6.1f} | P(清算>0) {np.mean(r["liq"] > 0):.0%} | P(累計損益>0) {np.mean(r["pl"] > 0):.0%}')

    pr('\n## W 母数の重みづけ（推測 250:20% / 500:30% / 994:30% / 2331:20%・2通目あり）')
    ws = {250: .2, 500: .3, 994: .3, 2331: .2}
    acc = {'liq': 0, 'real': 0, 'real10': 0, 'pl': 0}
    for pool, w in ws.items():
        r = simulate('A', pool=pool, after='second', **mine)
        r10 = simulate('A', pool=pool, after='second', stop_month=10, **mine)
        acc['liq'] += w * np.mean(r['liq'] > 0); acc['real'] += w * np.mean(r['real'] > 0)
        acc['real10'] += w * np.mean(r10['real'] > 0); acc['pl'] += w * np.mean(r['pl'] > 0)
    pr(f"重みづけ: P(清算>0) {acc['liq']:.0%} P(累計損益>0) {acc['pl']:.0%} P(現金>0)継続 {acc['real']:.0%} 月10停止 {acc['real10']:.0%}")

    pr('\n## K 撤退線の較正（案A・母数994・2通目）12/31 累計成約（月0〜2）')
    r = simulate('A', pool=994, after='second', **mine)
    for th in [0, 1, 2, 3]:
        hitm = r['new_by_dec'] <= th
        lo = r['p'] < 0.012; hi = r['p'] >= 0.02
        pr(f'≤{th}社: 踏む {hitm.mean():.0%} | 成約率<1.2%の世界 {hitm[lo].mean():.0%} | ≥2%の世界 {hitm[hi].mean():.0%} | '
           f'踏んだ世界 P(清算>0) {np.mean(r["liq"][hitm] > 0):.0%} / 踏まない {np.mean(r["liq"][~hitm] > 0):.0%}')
    pr(f'送信停滞の世界 P(清算>0) {np.mean(r["liq"][r["stall"]] > 0):.0%} / 通常 {np.mean(r["liq"][~r["stall"]] > 0):.0%}')

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as f:
            f.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
