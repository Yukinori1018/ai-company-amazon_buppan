#!/usr/bin/env python3
"""T-20260914-005 タケシ（追加4）: 固定費圧縮（Keepa API→Pro 月3から＝12,283円/月）を入れた上での、緩和1つ・2つの上限。
python3 02e_mc_緩和の上限.py   出力 02e_mc_緩和の上限_出力.txt"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rd", HERE / "02_mc_再設計.py")
rd = importlib.util.module_from_spec(spec); sys.modules["rd"] = rd; spec.loader.exec_module(rd)
OUT = HERE / "02e_mc_緩和の上限_出力.txt"
NF = 1000
PRO = 12_283


def main():
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 02e_mc_緩和の上限 出力 N={NF}"); P_(rd.H)
    L18 = dict(rd.PL["B_final"], harvest=16, harvest_new=15)
    C18 = dict(rd.PL["C_final"], harvest=16, harvest_new=15)
    for lab, P, plan, T in (("案B＋Pro（既定内の最大・再掲）", dict(rd.B, fixed=PRO), rd.PL["B_final"], 12),
                            ("案C＋Pro（せどり・週10通）", dict(rd.C, fixed=PRO), rd.PL["C_final"], 12),
                            ("案C＋Pro＋週20通", dict(rd.C, fixed=PRO), dict(rd.PL["C_final"], send="B"), 12),
                            ("案B＋Pro＋18ヶ月", dict(rd.B, fixed=PRO), L18, 18),
                            ("案C＋Pro＋18ヶ月", dict(rd.C, fixed=PRO), C18, 18)):
        P_(rd.r1(lab, rd.ext2(rd.run(P, plan, NF, T=T))))
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
