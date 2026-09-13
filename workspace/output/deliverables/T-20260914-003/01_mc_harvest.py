#!/usr/bin/env python3
"""T-20260914-003 マサル: 発注停止の時期（新規ロットの停止月×補充の停止月）を細かく比べる。01_mc.py の推奨形のまま。n=1500"""
import importlib.util, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
if __name__ == "__main__":
    names = {7: "2027-04", 8: "2027-05", 9: "2027-06", 10: "2027-07", 11: "2027-08"}
    lines = ["# 01_mc_harvest 出力（n=1500）", "",
             "| 案 | 新規ロットの最終月 | 補充の最終月 | P(実質現金>0)（中央） | P20／P80 | P(累計損益>0)（中央） | P(手仕舞い値>0) | 月12の月商 中央 |",
             "|---|---|---|---|---|---|---:|---:|"]
    for key in ("C_best", "B_best"):
        for hn, hv in ((8, 9), (8, 10), (9, 10), (9, 11), (10, 11)):
            s = mc.summ(mc.run(mc.MASARU, dict(mc.PLANS[key], harvest_new=hn, harvest=hv), 1500))
            lines.append(f"| {key} | {names[hn - 1]} | {names[hv - 1]} | {s['p']:.0%}（{mc.man(s['p50'])}） | {mc.man(s['p20'])}／{mc.man(s['p80'])} | {s['pp']:.0%}（{mc.man(s['prof50'])}） | {s['pclose']:.0%} | {s['rev12'] / 1e4:.0f}万 |")
    txt = "\n".join(lines); print(txt)
    (HERE / "01_mc_harvest_出力.txt").write_text(txt + "\n")
