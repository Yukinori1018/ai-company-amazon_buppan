"""T-20260914-003 マサル: タケシの 01_calc.py（案C＋月10停止）で、せどりの前提を1つずつ崩したときの P(実質現金>0)。n=6000・乱数はタケシと同じ"""
import importlib.util, sys
spec=importlib.util.spec_from_file_location("c", __import__("pathlib").Path(__file__).resolve().parent.parent / "T-20260914-002" / "01_calc.py")
c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
base=dict(s_cost=0, s_low=0.35, harvest_from=10, harvest_h=0.0, s_stop=10)
tests=[("置き値のまま（案C＋月10停止）",{}),("SD会費0円",None),("定常月商 50→25万",dict(s_cap=250_000)),("ゲートなし 10%固定",dict(s_gate=[(0.10,1.0)])),
       ("利益率 9→6%",dict(s_m=0.06)),("続かない 70%",dict(s_low=0.70)),("事故 せどり上乗せ20%",dict(s_hazard=0.20)),
       ("25万＋続かない70%＋利益率6%",dict(s_cap=250_000,s_low=0.70,s_m=0.06)),("25万＋ゲート10%",dict(s_cap=250_000,s_gate=[(0.10,1.0)]))]
print("| 前提（タケシの 01_calc・n=6000） | P(実質現金>0) | 実質 中央 | P(累計損益>0) |"); print("|---|---:|---:|---:|")
for lab,ov in tests:
    if ov is None:
        keep=c.SD_FEE; c.SD_FEE=0; res=c.run("WMS",base,n=6000); c.SD_FEE=keep
    else:
        res=c.run("WMS",dict(base,**ov),n=6000)
    s=c.summary(lab,res); print(f"| {lab} | {s['p_real']:.0%} | {c.man(s['real'][1])} | {s['p_cum']:.0%} |")
resb=c.run("WM",dict(c.W20,harvest_from=10,harvest_h=0.0),n=6000); s=c.summary("B",resb); print(f"| 参考 案B＋月10停止 | {s['p_real']:.0%} | {c.man(s['real'][1])} | {s['p_cum']:.0%} |")
resa=c.run("WM",dict(harvest_from=10,harvest_h=0.0),n=6000); s=c.summary("A",resa); print(f"| 参考 案A＋月10停止 | {s['p_real']:.0%} | {c.man(s['real'][1])} | {s['p_cum']:.0%} |")
