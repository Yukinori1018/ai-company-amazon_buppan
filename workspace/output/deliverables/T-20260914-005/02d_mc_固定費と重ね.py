#!/usr/bin/env python3
"""T-20260914-005 タケシ（追加3）: 固定費を下げた上で、他の1条件を重ねる。
固定費の置き値はマサルの FIX=15,253円/月（ハジメ段階1 14,253＝大口5,390＋Keepa API 8,732＋ドメイン131＋会計ソフト1,000）。
  Keepa API €49→Pro €29 を月3から（8,732→5,168円。12ヶ月平均 −2,970円/月）→ 12,283円
  参考: 固定費0（レーン単独の力）
python3 02d_mc_固定費と重ね.py   出力 02d_mc_固定費と重ね_出力.txt"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rd", HERE / "02_mc_再設計.py")
rd = importlib.util.module_from_spec(spec); sys.modules["rd"] = rd; spec.loader.exec_module(rd)
OUT = HERE / "02d_mc_固定費と重ね_出力.txt"
NF = 1000


def main():
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 02d_mc_固定費と重ね 出力 N={NF}"); P_("| 条件 | P(実質現金>0) | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    PRO = 12_283
    L18 = dict(rd.PL["B_final"], harvest=16, harvest_new=15)
    for lab, P, plan, T in (("案A＋Pro＋母数330", dict(rd.A, fixed=PRO, send_cap=330), rd.PL["B_final"], 12),
                            ("案A＋Pro＋成立率2.0%", dict(rd.A, fixed=PRO, m_rate=rd.scale(rd.R_OLD, 0.656)), rd.PL["B_final"], 12),
                            ("案A＋Pro＋卸の母数4", dict(rd.A, fixed=PRO, w_pool=4.0, w_pool_sig=0.9), rd.PL["B_final"], 12),
                            ("案B＋Pro", dict(rd.B, fixed=PRO), rd.PL["B_final"], 12),
                            ("案A＋Pro＋18ヶ月", dict(rd.A, fixed=PRO), L18, 18),
                            ("案A＋Pro＋母数330＋18ヶ月", dict(rd.A, fixed=PRO, send_cap=330), L18, 18)):
        P_(rd.r2(lab, rd.ext2(rd.run(P, plan, NF, T=T))))
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
