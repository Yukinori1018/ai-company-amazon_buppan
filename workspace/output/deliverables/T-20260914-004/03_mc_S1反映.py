#!/usr/bin/env python3
"""T-20260914-004 マサル（再計算）: S-1（サトル・上位60社）を「送れる母数」と「成立率」に反映。
卸の母数は 03_mc_卸実測.py の新値（w_pool 2.0/σ0.7）。構造は T-20260914-003/01_mc.py のまま。
  送れる母数: A のみ 約375社（上位60の A 25＋61位以下 約850×A比率42%≒350・推測）／A+B 約590社（65%・推測）。旧 900。
  成立率: A 25社中19社が Amazon ブランドストア保有＝自社出品のブランド保有者。
    S1主: 0.8/1.5/2.5%（30/45/25%）平均1.54% ＝ 自社出品76%×約1%＋非出品24%×3.05%（推測）
    S1副: 1/2/3%（サトル・秘書の例示）平均1.95%
    旧 : 1.5/3/5%（EC STARs 二次情報）平均3.05%
python3 03_mc_S1反映.py [--smoke]"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("w", HERE / "03_mc_卸実測.py")
w = importlib.util.module_from_spec(spec); sys.modules["w"] = w; spec.loader.exec_module(w)
mc, NEW, PL, run, summ, man, q, ext, r1, H1, sends = w.mc, w.NEW, w.PL, w.run, w.summ, w.man, w.q, w.ext, w.r1, w.H1, w.sends
OUT = HERE / "03_mc_S1反映_出力.txt"

R_S1 = [(0.008, 0.30), (0.015, 0.45), (0.025, 0.25)]
R_S1b = [(0.010, 0.30), (0.020, 0.45), (0.030, 0.25)]
R_OLD = mc.MASARU["m_rate"]
def scale(tab, f):
    return [(r * f, p) for r, p in tab]
S1 = dict(NEW, m_rate=R_S1, send_cap=375)


def main():
    smoke = "--smoke" in sys.argv
    N, NS = (40, 40) if smoke else (3000, 1500)
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 03_mc_S1反映 出力 N={N}（逆算 {NS}）seed={mc.SEED}")
    P_("卸 w_pool 2.0/σ0.7（T-2）＋ 送れる母数 375 ＋ 成立率 S1主（平均1.54%）。")
    P_("")
    P_("## H1. 測り方1（実質現金＋発注停止）: S-1 主"); P_(H1)
    keep = {}
    for key, lab in (("A_final", "案A 週10通"), ("B_final", "案B 週20通"), ("C_final", "案C 週10通＋せどり")):
        r = run(S1, PL[key], N); keep[key] = ext(r); P_(r1(lab, keep[key]))
    P_(r1("専業 週20通（卸0）", ext(run(dict(S1, w_pool=0.0), PL["B_final"], NS))))
    P_(f"- 案C−案B {100 * (keep['C_final']['p'] - keep['B_final']['p']):+.0f}pt／案B−案A {100 * (keep['B_final']['p'] - keep['A_final']['p']):+.0f}pt")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## H2. 測り方2（清算価値＋発注継続）: S-1 主")
    P_("| 案 | P(清算価値>0) | P20／中央 | P10 | 月12の月商 中央 |"); P_("|---|---:|---|---:|---:|")
    for key, lab in (("A_final", "案A"), ("B_final", "案B"), ("C_final", "案C")):
        s = ext(run(S1, dict(PL[key], harvest=None, harvest_new=None), N))
        P_(f"| {lab} | {s['pclose']:.0%} | {man(s['close20'])}／{man(s['close50'])} | {man(s['close10'])} | {s['rev12'] / 1e4:.0f}万 |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## H3. 分解と副案（案B・測り方1）"); P_("| 条件 | P／中央 | 成立 中央 |"); P_("|---|---|---:|")
    for lab, P in (("卸の実測のみ（母数900・成立率 旧）", NEW), ("＋母数375のみ", dict(NEW, send_cap=375)),
                   ("＋成立率 S1主のみ（母数900）", dict(NEW, m_rate=R_S1)), ("＋両方＝S-1 主", S1),
                   ("S-1 副（成立率 1/2/3%・母数375）", dict(S1, m_rate=R_S1b)), ("S-1 主・母数 A+B 590", dict(S1, send_cap=590))):
        s = ext(run(P, PL["B_final"], NS)); P_(f"| {lab} | {s['p']:.0%}／{man(s['p50'])} | {s['nest']} |")
    for lab, P in (("案C・S-1 副", dict(S1, m_rate=R_S1b)), ("案A・S-1 副", dict(S1, m_rate=R_S1b))):
        key = "C_final" if "案C" in lab else "A_final"
        s = ext(run(P, PL[key], NS)); P_(f"| {lab} | {s['p']:.0%}／{man(s['p50'])} | {s['nest']} |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## H4. 逆算（S-1 の世界で案B を P≥60% に戻す）")
    P_("列＝成立率の平均（混合の形は S1主のまま倍率）。送信の質 週20=0.85・週30=0.75・週40=0.65（推測）。")
    P_("| 送信・母数＼成立率 | 1.5%（S1主） | 2.0% | 3.0% | 4.0% | 5.0% |"); P_("|---|---|---|---|---|---|")
    for lab, ov in (("週20・母数375", dict(send_B=sends(1.0), q_B=0.85, send_cap=375)),
                    ("週30・母数375", dict(send_B=sends(1.5), q_B=0.75, send_cap=375)),
                    ("週30・母数590", dict(send_B=sends(1.5), q_B=0.75, send_cap=590)),
                    ("週40・母数590", dict(send_B=sends(2.0), q_B=0.65, send_cap=590))):
        cells = []
        for m in (0.0154, 0.020, 0.030, 0.040, 0.050):
            s = summ(run(dict(S1, **ov, m_rate=scale(R_S1, m / 0.0154)), PL["B_final"], NS)); cells.append(f"{s['p']:.0%}／{man(s['p50'])}")
        P_(f"| {lab} | " + " | ".join(cells) + " |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("| S-1 主に1つ足す（案B 週20） | P／中央 |"); P_("|---|---|")
    for lab, ov in (("取り分の実現 0.85→1.2", dict(real=1.2)), ("卸の母数 4（旧）", dict(w_pool=4.0, w_pool_sig=0.9)),
                    ("卸の母数 8", dict(w_pool=8.0, w_pool_sig=0.7)), ("メーカー直の利益率 16%", dict(m_m=0.16))):
        s = summ(run(dict(S1, **ov), PL["B_final"], NS)); P_(f"| {lab} | {s['p']:.0%}／{man(s['p50'])} |")
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
