"""T-20260915-002 / 12 実測の母数での確率 — 09_mc_takeshi.py（→ 07_mc_masaru.py）をそのまま読み込み、母数に S-A の実測を入れる。

足したのは2つだけ:
  1. 母数 = S-A（T-20260914-006/01）の 1,602 / 1,896 / 2,118 / 2,425 / 2,984 社
     （保守の下限 / 採用の下限 / 保守の中央 / 採用の中央 / 採用の上限）。ストアなしで数えた母数なので pscale は率の世界だけに使う
  2. 1社の定常月利の倍率 gscale（中央 0.70 の引数だけ）と、1社のテスト費 TEST_COST（「1社あたり11 ASIN」の感度）
成約率の中央1.5%は、09 §2.1 と同じく中央2%の分布に×0.75（固定値ではない）。
実行: python3 12_mc_masaru_pool.py [出力ファイル]   シード 20260916・2万回。
"""
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('m09', os.path.join(HERE, '09_mc_takeshi.py'))
m09 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m09)
m07 = m09.m07

_inner = m07.lognorm          # 09 の包み（成約率の倍率）
GSCALE = {'v': 1.0}


def _lognorm(median, p80_ratio, size, rng):
    x = _inner(median, p80_ratio, size, rng)
    return x * GSCALE['v'] if median == 0.70 else x


m07.lognorm = _lognorm


def row(pool, pscale=1.0, gscale=1.0, test_cost=2.0):
    GSCALE['v'] = gscale
    m07.TEST_COST = test_cost
    d = m09.row(pool, pscale)
    GSCALE['v'] = 1.0
    m07.TEST_COST = 2.0
    return d


def main():
    out = []
    pr = lambda s: (print(s), out.append(s))
    pr('## 0 照合（09 の表と一致するか）')
    pr(m09.fmt('母数994', row(994)))
    pr(m09.fmt('母数2331', row(2331)))

    pools = [1602, 1896, 2118, 2425, 2984]
    res = {}
    for label, ps in [('率2%', 1.0), ('率1.5%', 0.75)]:
        pr(f'\n## A S-A の母数 × {label}（案A・週70通・2通目あり）')
        for pool in pools:
            d = row(pool, ps)
            res[(pool, ps)] = d
            pr(m09.fmt(f'母数{pool}', d))

    pr('\n## W 採用の80%区間を3点で混ぜる（1,896:30% / 2,425:40% / 2,984:30%・推測）')
    w = {1896: .3, 2425: .4, 2984: .3}
    for label, ps in [('率2%', 1.0), ('率1.5%', 0.75)]:
        agg = {k: sum(wt * res[(p, ps)][k] for p, wt in w.items()) for k in ['liq', 'cash', 'cash9', 'cash10', 'fire', 'pl']}
        pr(f"{label}: P(清算>0) {agg['liq']:.0%} | P(累計損益>0) {agg['pl']:.0%} | P(現金>0) 継続 {agg['cash']:.0%} / 7月停止 {agg['cash9']:.0%} / 8月停止 {agg['cash10']:.0%} | 1/31踏む {agg['fire']:.0%}")

    pr('\n## G 1社あたり11 ASIN の感度（母数2,425）。gscale＝1社の月利の倍率、テスト費は SKU 数に比例（2万＝1〜2 SKU）')
    for label, ps in [('率2%', 1.0), ('率1.5%', 0.75)]:
        for gs, tc, name in [(1.0, 2.0, '据え置き 0.7万・1〜2 SKU'),
                             (1.43, 3.0, '1.0万（松井）・2〜3 SKU'),
                             (2.0, 4.0, '1.4万・3〜4 SKU'),
                             (0.7, 2.0, '下振れ 0.49万')]:
            pr(m09.fmt(f'{label} {name}', row(2425, ps, gs, tc)))

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as f:
            f.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
