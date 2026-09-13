#!/usr/bin/env python3
"""T-20260914-003 マサル: 送信の母数（メーカー打診先）を約400社で頭打ちにした場合（タカシ T-1 の 1,200件時点の試算・推測）。01_mc.py の構造・置き値のまま"""
import importlib.util, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
if __name__ == "__main__":
    lines = ["# 01_mc_sendcap 出力（n=1500）", "", mc.HDR]
    for key in ("A", "B", "B_best", "C_best"):
        for cap in (900, 400):
            s = mc.summ(mc.run(dict(mc.MASARU, send_cap=cap), mc.PLANS[key], 1500))
            lines.append(mc.row(f"{key} 送信の母数 {cap}社", s))
    txt = "\n".join(lines); print(txt)
    (HERE / "01_mc_sendcap_出力.txt").write_text(txt + "\n")
