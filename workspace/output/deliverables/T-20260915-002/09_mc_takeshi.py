"""T-20260915-002 / 09 真似する計画（改訂）— マサルの 07_mc_masaru.py を読み込んで、R1・R2・R5 に要る世界を足す。

07 の構造と置き値（成約の遅れ・運転資金10.7倍・値崩れ・送信の停滞30%・2通目あり）はそのまま使う。
足したのは次の3つだけ:
  1. 母数 580 社の世界（T-3 の実測：T-1 打診母数 1,394 ASIN のうちストアなし 829＝59%。これを 994 社に当てた推測）
  2. 成約率の倍率 pscale（ブランドストア持ちを外さずに送る世界。持ち41%の率を半分→×0.80、0→×0.59）
  3. 撤退線「2027-01-31 に累計成約3社以下」を母数の世界ごとに較正（t=0..3 ＝ 2026-10..2027-01）

実行: python3 09_mc_takeshi.py [出力ファイル]   乱数は 07 と同じシード 20260916。
"""
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('m07', os.path.join(HERE, '07_mc_masaru.py'))
m07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m07)

_orig_lognorm = m07.lognorm
PSCALE = {'v': 1.0}


def _lognorm(median, p80_ratio, size, rng):
    # 成約率（中央 0.02 の引数）だけ倍率を掛ける。他の置き値（1社の月利など）は触らない
    x = _orig_lognorm(median, p80_ratio, size, rng)
    return x * PSCALE['v'] if median == 0.02 else x


m07.lognorm = _lognorm
MINE = dict(lag=True, wc='mine', erosion=True, regime='mine', after='second')


def run(pool, pscale=1.0, **kw):
    PSCALE['v'] = pscale
    r = m07.simulate('A', pool=pool, **dict(MINE, **kw))
    PSCALE['v'] = 1.0
    return r


def row(pool, pscale=1.0):
    r = run(pool, pscale)
    r9 = run(pool, pscale, stop_month=9)
    r10 = run(pool, pscale, stop_month=10)
    jan = r['new_hist'][:4].sum(0)          # 2026-10〜2027-01 の成約
    fire = jan <= 3
    q = np.percentile(r['m12'], [20, 50, 80])
    return dict(
        liq=np.mean(r['liq'] > 0), liq_med=np.median(r['liq']), pl=np.mean(r['pl'] > 0),
        cash=np.mean(r['real'] > 0), cash_med=np.median(r['real']),
        cash9=np.mean(r9['real'] > 0), cash10=np.mean(r10['real'] > 0),
        m12=q, deals=np.median(r['cum_new']), fire=fire.mean(),
        p_fire=np.mean(r['liq'][fire] > 0) if fire.any() else float('nan'),
        p_nofire=np.mean(r['liq'][~fire] > 0),
        fire_hi=fire[r['p'] >= 0.02].mean() if (r['p'] >= 0.02).any() else float('nan'),
        min10=np.percentile(r['min_cash'], 10),
        jan_med=np.median(jan), nov_med=np.median(r['new_hist'][:2].sum(0)),
        active12=np.median(r['active12']), sales12=np.median(r['sales12']), sends=np.median(r['sends']))


def fmt(name, d):
    return (f"{name:22s} P(清算>0) {d['liq']:4.0%} 中央 {d['liq_med']:6.1f} | P(累計損益>0) {d['pl']:4.0%} | "
            f"P(現金>0) 継続 {d['cash']:4.0%}（中央 {d['cash_med']:6.1f}）/7月停止 {d['cash9']:4.0%}/8月停止 {d['cash10']:4.0%} | "
            f"月利12 {np.round(d['m12'], 1)} | 累計成約中央 {d['deals']:4.0f} | "
            f"1/31≤3社 踏む {d['fire']:4.0%}（率2%以上で {d['fire_hi']:4.0%}）踏んだ世界P {d['p_fire']:4.0%}/踏まない {d['p_nofire']:4.0%} | 最薄P10 {d['min10']:5.1f} | "
            f"成約中央 11/30 {d['nov_med']:.0f}・1/31 {d['jan_med']:.0f} | 取引中12 {d['active12']:.0f} | 月商12 {d['sales12']:.0f} | 送信 {d['sends']:.0f}")


def complaint_stop(rate, sends=2000, window=300, k=3, n=20000, seed=20260916):
    """苦情の段階ルール（直近300通で3件で全停止）が、送信 sends 通の間に一度でも発動する確率。苦情率 rate/通は推測。"""
    rng = np.random.default_rng(seed)
    x = rng.random((n, sends)) < rate
    c = np.cumsum(x, axis=1)
    c = np.concatenate([np.zeros((n, 1), int), c], axis=1)
    win = c[:, window:] - c[:, :-window]
    return np.mean(win.max(axis=1) >= k), np.mean(c[:, 1000] >= 1)


def main():
    out = []
    pr = lambda s: (print(s), out.append(s))
    pr('## A 母数の世界（案A・07 の作り・2通目あり）')
    for pool in [250, 500, 580, 994, 1500, 2331, 3000]:
        pr(fmt(f'母数{pool}', row(pool)))

    pr('\n## B R2 ブランドストア持ちを外すか')
    pr(fmt('外す・S-1比（250）', row(250)))
    pr(fmt('外す・T-3比（580）', row(580)))
    pr(fmt('外さない・持ちの率半分（994×0.80）', row(994, 0.795)))
    pr(fmt('外さない・持ちは0（994×0.59）', row(994, 0.59)))
    pr(fmt('外す・T-3比・2,331の世界（1,380）', row(1380)))
    pr(fmt('外さない・2,331×0.80', row(2331, 0.795)))

    pr('\n## C 成約率の中央を1.5%に下げた世界（S-B：3〜5%は目標値）')
    for pool in [500, 994, 2331]:
        pr(fmt(f'母数{pool}・率×0.75', row(pool, 0.75)))

    pr('\n## D R4 苦情の段階ルール（送信2,000通・直近300通で3件＝全停止）')
    for rate in [0.001, 0.002, 0.003, 0.005]:
        stop, any1 = complaint_stop(rate)
        pr(f'苦情率{rate:.1%}/通: 全停止が発動 {stop:4.0%} | 旧ルール（1件で全停止）1,000通までに発動 {any1:4.0%}')

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as f:
            f.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
