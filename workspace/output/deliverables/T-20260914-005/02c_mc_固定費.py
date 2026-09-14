#!/usr/bin/env python3
"""T-20260914-005 タケシ（追加2）: 固定費が P をどれだけ押し下げているか。案A・案C。
固定費の置き値はマサルの FIX=15,253円/月（ハジメ段階1 14,253＝大口5,390＋Keepa API 8,732＋ドメイン131＋会計ソフト1,000）。
  Keepa API €49→Pro €29 を月3から（8,732→5,168円。12ヶ月平均 −2,970円/月）→ 12,283円
  参考: 固定費0（レーン単独の力）
python3 02c_mc_固定費.py   出力 02c_mc_固定費_出力.txt"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rd", HERE / "02_mc_再設計.py")
rd = importlib.util.module_from_spec(spec); sys.modules["rd"] = rd; spec.loader.exec_module(rd)
OUT = HERE / "02c_mc_固定費_出力.txt"
NF = 1000


def main():
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 02c_mc_固定費 出力 N={NF}"); P_("| 条件 | P(実質現金>0) | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    for lab, P, plan in (("案A 固定費 12,283円（Keepa API→Pro 月3から）", dict(rd.A, fixed=12_283), "B_final"),
                         ("案A 固定費0（参考）", dict(rd.A, fixed=0), "B_final"),
                         ("案C 固定費 12,283円", dict(rd.C, fixed=12_283), "C_final"),
                         ("案C 固定費0（参考）", dict(rd.C, fixed=0), "C_final")):
        P_(rd.r2(lab, rd.ext2(rd.run(P, rd.PL[plan], NF))))
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
