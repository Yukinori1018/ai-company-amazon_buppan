#!/usr/bin/env python3
"""T-20260914-005 タケシ（追加）: 既定内の上限・P60 の境界・18ヶ月の案B/C。02_mc_再設計.py の置き値と差し込みをそのまま使う。
python3 02b_mc_追加.py   出力 02b_mc_追加_出力.txt"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rd", HERE / "02_mc_再設計.py")
rd = importlib.util.module_from_spec(spec); sys.modules["rd"] = rd; spec.loader.exec_module(rd)
A, B, C, PL, run, ext2, r2, R_OLD, scale = rd.A, rd.B, rd.C, rd.PL, rd.run, rd.ext2, rd.r2, rd.R_OLD, rd.scale
OUT = HERE / "02b_mc_追加_出力.txt"
NF = 1000
L18 = dict(PL["B_final"], harvest=16, harvest_new=15)
C18 = dict(PL["C_final"], harvest=16, harvest_new=15)


def main():
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 02b_mc_追加 出力 N={NF}"); P_("")
    P_("## X1. 既定内で上振れが重なった場合（案A 基準）"); P_("| 条件 | P(実質現金>0) | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    rows = [
        ("母数330＋卸の母数4＋取り分1.1", A, PL["B_final"], dict(send_cap=330, w_pool=4.0, w_pool_sig=0.9, real=1.1), 12),
        ("上＋SKU/社2.0＋低稼働15%（既定内の上限）", A, PL["B_final"], dict(send_cap=330, w_pool=4.0, w_pool_sig=0.9, real=1.1, m_sku=2.0, low_B=0.15), 12),
        ("既定内の上限＋成立率 平均2.0%", A, PL["B_final"], dict(send_cap=330, w_pool=4.0, w_pool_sig=0.9, real=1.1, m_sku=2.0, low_B=0.15, m_rate=scale(R_OLD, 0.656)), 12),
    ]
    for lab, P, plan, ov, T in rows:
        P_(r2(lab, ext2(run(dict(P, **ov), plan, NF, T=T))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## X2. P≥60% の境界（案A・週20・母数330）"); P_("| 成立率 平均 | P | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    for m in (0.035, 0.045, 0.05, 0.055, 0.06):
        s = ext2(run(dict(A, send_cap=330, m_rate=scale(R_OLD, m / 0.0305)), PL["B_final"], NF))
        P_(f"| {m:.1%} | {s['p']:.0%} | {rd.man(s['p50'])} | {rd.man(s['p20'])} | {s['nest']}社 |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## X3. 18ヶ月（2028-03-31 判定・2028-02 から発注停止）"); P_(rd.H)
    for lab, P, plan in (("案A 18ヶ月", A, L18), ("案B 18ヶ月", B, L18), ("案C 18ヶ月", C, C18),
                         ("案A 18ヶ月・成立率2.0%", dict(A, m_rate=scale(R_OLD, 0.656)), L18)):
        P_(rd.r1(lab, ext2(run(P, plan, NF, T=18))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## X4. 案C の感応"); P_("| 条件 | P(実質現金>0) | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    for lab, ov in (("案C 成立率2.0%", dict(m_rate=scale(R_OLD, 0.656))), ("案C 成立率4.0%", dict(m_rate=scale(R_OLD, 1.31))),
                    ("案C 母数330＋卸4", dict(send_cap=330, w_pool=4.0, w_pool_sig=0.9))):
        P_(r2(lab, ext2(run(dict(C, **ov), PL["C_final"], NF))))
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
