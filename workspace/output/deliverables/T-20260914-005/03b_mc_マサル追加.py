#!/usr/bin/env python3
"""T-20260914-005 マサル（追加）: Keepa を最小にした案の P2 格子と、Keepa を失う劣化の損益分岐。03_mc_マサル検証.py の構造をそのまま使う。
python3 03b_mc_マサル追加.py   出力 03b_mc_マサル追加_出力.txt。すべて（推測）。"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mv", HERE / "03_mc_マサル検証.py")
mv = importlib.util.module_from_spec(spec); sys.modules["mv"] = mv; spec.loader.exec_module(mv)
OUT = HERE / "03b_mc_マサル追加_出力.txt"; NF = 1000
BF = mv.PL["B_final"]


def main():
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 03b_mc_マサル追加 出力 N={NF} seed={mv.mc.SEED}"); P_("")
    FMIN = mv.fx(api=(3,)); p2h, p3h = mv.pops_sig(0.08)
    P_("## Y1. API は補給月だけ・Pro なし（読み σ+0.08）の P2 格子"); P_(mv.H)
    for p2 in (310, 230, 100):
        for m, lab in ((1.0, "3.05%"), (0.656, "2.0%"), (0.492, "1.5%")):
            P_(mv.row(f"P2 {p2}・成立率 平均{lab}", mv.S(mv.run(dict(mv.B_R(p2, 70, p2h, p3h), real_sig=0.78, m_rate=mv.scale(mv.R_OLD, m), fixed_list=FMIN), BF, NF))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## Y2. Keepa を失う劣化をきつくする（損益分岐）"); P_(mv.H)
    F0 = mv.fx()
    for lab, sig, real, fl, p2 in (("Keepa なし・σ+0.15・読みの偏り 0.85→0.75", 0.15, 0.75, F0, 230),
                                   ("Keepa なし・σ+0.30・読みの偏り 0.85→0.65", 0.30, 0.65, F0, 230),
                                   ("Keepa なし・σ+0.30・読みの偏り 0.85→0.55", 0.30, 0.55, F0, 230),
                                   ("API 補給月だけ・σ+0.15・偏り 0.85→0.75", 0.15, 0.75, FMIN, 310),
                                   ("比較 タケシ Pro 案（劣化なし）", 0.0, 0.85, mv.F_TK, 310)):
        a, b = mv.pops_sig(sig)
        P_(mv.row(lab, mv.S(mv.run(dict(mv.B_R(p2, 70, a, b), real_sig=0.70 + sig, real=real, fixed_list=fl), BF, NF))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## Y3. E-2 の較正（API は補給月だけ・Pro なし・P2 310・成立率3.05%）")
    P_("| 2027-03 末の累計損益 | 割合 | P12 |"); P_("|---|---:|---:|")
    rr = mv.run(dict(mv.B_R(310, 70, p2h, p3h), real_sig=0.78, fixed_list=FMIN), BF, NF)
    cp = lambda r: sum(r["prof"][:6])
    for lo, hi in ((-1e9, -60_000), (-60_000, -40_000), (-40_000, -30_000), (-30_000, -20_000), (-20_000, 0), (0, 1e9)):
        a = [r["cash"] for r in rr if lo <= cp(r) < hi]
        lab = (f"〜{mv.man(hi)}" if lo < -1e8 else (f"{mv.man(lo)}〜" if hi > 1e8 else f"{mv.man(lo)}〜{mv.man(hi)}"))
        P_(f"| {lab} | {len(a) / len(rr):.0%} | {(sum(x > 0 for x in a) / len(a)) if a else float('nan'):.0%} |")
    for th in (-40_000, -30_000):
        hit = [r["cash"] for r in rr if cp(r) < th]; mis = [r["cash"] for r in rr if cp(r) >= th]
        P_(f"- 線 {mv.man(th)}: 踏む {len(hit) / len(rr):.0%}・踏んだ世界の P {sum(x > 0 for x in hit) / max(1, len(hit)):.0%}・踏まない {sum(x > 0 for x in mis) / max(1, len(mis)):.0%}")
    P_(f"- 6ヶ月の固定費 {sum(FMIN[:6]):,.0f}円／2027-03 末の累計損益 中央 {mv.man(mv.q([cp(r) for r in rr], .5))}")
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
