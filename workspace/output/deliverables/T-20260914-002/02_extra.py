#!/usr/bin/env python3
"""T-20260914-002 2周目 タケシ: マサルの 01_mc.py を import して、最終形で出ていない組み合わせだけ追加計算（n=1500）。
(1) 発注継続×清算価値（案A/B/C）(2) 案B の撤退条件の較正と W8 の分岐 (3) 期待値。モデルは作り直していない。
再実行: python3 02_extra.py [cont|bsplit|mean]（引数なしで全部・約5分）"""
import sys
PART = sys.argv[1] if len(sys.argv) > 1 else "all"

if PART in ("all", "cont"):
    exec(compile(r"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260914-003")
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
t0=time.time()
for key in ("A_final","B_final","C_final"):
    for lab, ov in (("停止(最終形)", {}), ("止めない", dict(harvest=None, harvest_new=None))):
        r = mc.run(mc.MASARU, dict(mc.PLANS[key], **ov), 1500)
        s = mc.summ(r)
        print(f"{key} {lab}: 実質P {s['p']:.0%}({mc.man(s['p50'])}) P20 {mc.man(mc.q([x['cash'] for x in r],.2))} 累計P {s['pp']:.0%}({mc.man(s['prof50'])}) 手仕舞いP {s['pclose']:.0%}({mc.man(s['close50'])}) 手仕舞いP20 {mc.man(mc.q([x['close'] for x in r],.2))} P10 {mc.man(mc.q([x['close'] for x in r],.1))} 月12月商 {s['rev12']/1e4:.0f}万 日次最低P10 {s['thin10']/1e4:.0f}万", flush=True)
print(time.time()-t0)
""", "cont", "exec"))
if PART in ("all", "bsplit"):
    exec(compile(r"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260914-003")
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
q, man, summ = mc.q, mc.man, mc.summ
t0=time.time()
res = mc.run(mc.MASARU, mc.PLANS["B_final"], 1500)
s = summ(res); n=len(res)
print(f"B_final n=1500: P {s['p']:.0%} ({man(s['p50'])})")
pr = lambda f: sum(1 for r in res if f(r))/n
cum = lambda r,t: sum(r["prof"][:t])
for lab,f in (("実現>=0.7", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"]>=0.7),
              ("0.4-0.7", lambda r: r["meta"]["early_ratio"] is not None and 0.4<=r["meta"]["early_ratio"]<0.7),
              ("<0.4", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"]<0.4),
              ("月3までSKUなし", lambda r: r["meta"]["early_ratio"] is None),
              ("低稼働", lambda r: r["meta"]["low"]), ("通常稼働", lambda r: not r["meta"]["low"])):
    sub=[r for r in res if f(r)]
    if sub:
        ss=summ(sub); print(f"W8 {lab} ({len(sub)/n:.0%}): P {ss['p']:.0%} 中央 {man(ss['p50'])} P10 {man(ss['p10'])}")
for t,lab in ((4,"2027-01"),(6,"2027-03"),(9,"2027-06")):
    cs=[(cum(r,t),r["cash"]) for r in res]
    print(f"## {lab} 累計 中央 {man(q([c for c,_ in cs],.5))} P20 {man(q([c for c,_ in cs],.2))}")
    for lo,hi in ((-1e9,-100000),(-100000,-80000),(-80000,-50000),(-50000,-20000),(-20000,0),(0,50000),(50000,1e9)):
        sub=[c2 for c1,c2 in cs if lo<=c1<hi]
        if sub: print(f"  [{lo/1e4:.0f},{hi/1e4:.0f}) {len(sub)/n:.0%} P {sum(x>0 for x in sub)/len(sub):.0%} 中央 {man(q(sub,.5))}")
    for th in (-100000,-80000,-50000,0):
        a=[c2 for c1,c2 in cs if c1<th]; b=[c2 for c1,c2 in cs if c1>=th]
        if a and b: print(f"  閾値<{th/1e4:.0f}万: 踏む {len(a)/n:.0%} 踏んだ世界P {sum(x>0 for x in a)/len(a):.0%} 踏まない世界P {sum(x>0 for x in b)/len(b):.0%}")
print(f"12月末SKU0: {pr(lambda r: r['meta']['early_ratio'] is None):.0%} 12月まで売上0: {pr(lambda r: sum(r['rev'][:3])<1):.0%}")
sub=[r for r in res if r['meta']['early_ratio'] is None]; ss=summ(sub); print(f" SKU0の世界 P {ss['p']:.0%}")
sub=[r for r in res if sum(r['rev'][:3])<1]; ss=summ(sub); print(f" 12月まで売上0の世界 P {ss['p']:.0%} 中央 {man(ss['p50'])}")
print(f"事故 {pr(lambda r: r['meta']['inc'] is not None):.0%} 恒久 {pr(lambda r: r['meta']['perm']):.0%} 成立3+ {pr(lambda r: r['meta']['n_est']>=3):.0%}")
print(f"4軸 月商2027-06 {man(q([r['rev'][8] for r in res],.2))}/{man(q([r['rev'][8] for r in res],.5))}/{man(q([r['rev'][8] for r in res],.8))} 累計 {man(q([r['profit'] for r in res],.2))}/{man(q([r['profit'] for r in res],.5))}/{man(q([r['profit'] for r in res],.8))} 成立 {q([r['meta']['n_est'] for r in res],.2)}/{q([r['meta']['n_est'] for r in res],.5)}/{q([r['meta']['n_est'] for r in res],.8)} 卸SKU {q([r['meta']['w_n'] for r in res],.2)}/{q([r['meta']['w_n'] for r in res],.5)}/{q([r['meta']['w_n'] for r in res],.8)} 初回入金 {sorted(r['first_payout'] for r in res)[n//2]}")
print(time.time()-t0)
""", "bsplit", "exec"))
if PART in ("all", "mean"):
    exec(compile(r"""
import importlib.util, sys, pathlib, statistics as st
HERE = pathlib.Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260914-003")
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
for key in ("A_final","B_final","C_final"):
    for lab, ov in (("停止", {}), ("継続", dict(harvest=None, harvest_new=None))):
        r = mc.run(mc.MASARU, dict(mc.PLANS[key], **ov), 1500)
        print(f"{key} {lab}: 実質 平均 {st.mean(x['cash'] for x in r)/1e4:+.1f}万 手仕舞い 平均 {st.mean(x['close'] for x in r)/1e4:+.1f}万 累計 平均 {st.mean(x['profit'] for x in r)/1e4:+.1f}万 手仕舞いP80 {mc.q([x['close'] for x in r],.8)/1e4:+.0f}万 実質P80 {mc.q([x['cash'] for x in r],.8)/1e4:+.0f}万", flush=True)
""", "mean", "exec"))
