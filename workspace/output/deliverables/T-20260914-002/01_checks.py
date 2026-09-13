#!/usr/bin/env python3
"""T-20260914-002 撤退条件・答え合わせの確率（01_calc.py のモデルをそのまま使う・n=6000・乱数固定）"""
import importlib.util, pathlib
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("c", HERE / "01_calc.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
F = c.FIXED
def cum_at(r, t): return sum(r["prof"][1:t + 1]) - F * 0.5
base = dict(s_cost=0, s_low=0.35)
cases = [
    ("案C（発注継続）", "WMS", base),
    ("案C＋月10発注停止", "WMS", dict(base, harvest_from=10, harvest_h=0.0, s_stop=10)),
    ("案B（発注継続）", "WM", c.W20),
    ("案B＋月10発注停止", "WM", dict(c.W20, harvest_from=10, harvest_h=0.0)),
    ("案A＋月10発注停止", "WM", dict(harvest_from=10, harvest_h=0.0)),
]
lines = ["# 01_checks 出力（n=6000・seed=%d）" % c.SEED, ""]
for label, lanes, ov in cases:
    res = c.run(lanes, ov, n=6000); n = len(res); s = c.summary(label, res)
    pr = lambda f: sum(1 for r in res if f(r)) / n
    lines += [f"## {label}",
              f"- P(累計>0) {s['p_cum']:.0%}／累計 P20・中央・P80 {c.man(s['cum'][0])}・{c.man(s['cum'][1])}・{c.man(s['cum'][2])}",
              f"- P(実質>0) {s['p_real']:.0%}／実質 P20・中央・P80 {c.man(s['real'][0])}・{c.man(s['real'][1])}・{c.man(s['real'][2])}",
              f"- 最薄現金 P10 {s['minc'][0]/1e4:.0f}万・中央 {s['minc'][1]/1e4:.0f}万・最薄月 中央 月{s['minm']}",
              f"- 撤退1 期間中の手元現金<60万: {pr(lambda r: r['min_cash'] < 600_000):.0%}",
              f"- 撤退2 月3（12月）末まで売上0: {pr(lambda r: r['first'] is None or r['first'] > 3):.0%}",
              f"- 撤退3 月6（3月）末 累計<-10万: {pr(lambda r: cum_at(r, 6) < -100_000):.0%}",
              f"- 撤退4 月9（6月）末 累計<-10万: {pr(lambda r: cum_at(r, 9) < -100_000):.0%}",
              f"- 月9 累計≥+10万: {pr(lambda r: cum_at(r, 9) >= 100_000):.0%}",
              f"- 初回売上が月1（10月）: {pr(lambda r: r['first'] == 1):.0%}",
              f"- 月9（2027-06）の月商≥50万: {pr(lambda r: r['rev'][9] >= 500_000):.0%}（中央 {c.q([r['rev'][9] for r in res], .5)/1e4:.0f}万）",
              f"- 月11（2027-08）の月商 中央 {c.q([r['rev'][11] for r in res], .5)/1e4:.0f}万／月12 中央 {c.q([r['rev'][12] for r in res], .5)/1e4:.0f}万",
              f"- 成立≥3: {pr(lambda r: r['est'] >= 3):.0%}／予備25万割れ: {s['breach']:.0%}",
              f"- 在庫 中央 月9 {c.q([r['invs'][9] for r in res], .5)/1e4:.0f}万・月12 {s['inv']/1e4:.0f}万", ""]
txt = "\n".join(lines)
(HERE / "01_checks_出力.txt").write_text(txt + "\n"); print(txt)
