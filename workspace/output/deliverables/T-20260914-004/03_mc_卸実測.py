#!/usr/bin/env python3
"""T-20260914-004 マサル（再計算）: 卸の母数を T-2 の実測に差し替えて、案A/B/C を出し直す。
T-20260914-003/01_mc_final.py の複製。構造（01_mc.py・00_cf_base.py）はそのまま読み込み、置き値だけ変える。
  旧: w_pool=4.0（対数正規の中央）・σ0.9 → 12ヶ月で立つ卸 SKU P10 0／中央 3／P90 11（平均4.8）
  新: w_pool=2.0・σ0.7            → P10 0／中央 1（2 が約半分）／P90 5（平均2.0）＝タカシ T-2「中央1〜2・幅0〜5」
SD 登録の通過60%・通らなければ×0.5 は据え置き。
python3 03_mc_卸実測.py [--quick|--smoke]   出力は 03_mc_卸実測_出力.txt に節ごとに追記。"""
import importlib.util, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "T-20260914-003"
spec = importlib.util.spec_from_file_location("mc", SRC / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
q, man, summ, run, M, PL = mc.q, mc.man, mc.summ, mc.run, mc.MASARU, mc.PLANS

NEW = dict(M, w_pool=2.0, w_pool_sig=0.7)          # ← 差し替えはここだけ（T-2 実測）
OLD = M
OUT = HERE / "03_mc_卸実測_出力.txt"


def rates(f):
    return [(r * f, w) for r, w in M["m_rate"]]


def sends(f):
    return [10, round(40 * f)] + [round(80 * f)] * 22


def ext(res):
    s = summ(res); n = len(res)
    cl = [r["close"] for r in res]
    fps = sorted(r["first_payout"] if r["first_payout"] != "None" else "9999" for r in res)
    wn = sorted(r["meta"]["w_n"] for r in res)
    s.update(dec0=sum(1 for r in res if sum(r["rev"][:3]) < 1) / n,
             fp=fps[n // 2], fp_none=sum(1 for x in fps if x == "9999") / n,
             close20=q(cl, .2), close10=q(cl, .1),
             wn=(q(wn, .1), q(wn, .2), q(wn, .5), q(wn, .8), q(wn, .9)), wn0=sum(1 for x in wn if x == 0) / n,
             wn_mean=sum(wn) / n, nest=q([r["meta"]["n_est"] for r in res], .5),
             inc=sum(1 for r in res if r["meta"]["inc"] is not None) / n,
             nosku3=sum(1 for r in res if r["meta"]["early_ratio"] is None) / n)
    return s


H1 = ("| 案・条件 | P(実質現金>0) | P20／中央／P80 | P10 | 平均 | 予備25万割れ | 12月末まで売上0 | 2027-01 までに SKU なし | 初回入金（中央） | 卸 SKU 中央 | 成立 中央 | 事故 |\n"
      "|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|")


def r1(lab, s):
    return (f"| {lab} | {s['p']:.0%} | {man(s['p20'])}／{man(s['p50'])}／{man(s['p80'])} | {man(s['p10'])} | {man(s['mean'])} | {s['breach']:.0%} | {s['dec0']:.0%} "
            f"| {s['nosku3']:.0%} | {s['fp'] if s['fp'] != '9999' else 'なし'} | {s['wn'][2]} | {s['nest']} | {s['inc']:.0%} |")


def main():
    smoke, quick = "--smoke" in sys.argv, "--quick" in sys.argv
    N, NS = (40, 40) if smoke else ((400, 300) if quick else (3000, 1500))
    t0 = time.time()
    OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a)
        print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 03_mc_卸実測 出力（T-20260914-004・マサル再計算）N={N}（感応度・逆算 {NS}）seed={mc.SEED}")
    P_("差し替え: w_pool 4.0/σ0.9 → 2.0/σ0.7（T-2 実測）。他の置き値・構造は T-20260914-003/01_mc_final と同じ。")
    P_("")

    keep = {}
    P_("## G1. 測り方1: 実質現金＋発注停止（最終形）"); P_(H1)
    rb_old = run(OLD, PL["B_final"], N); so = ext(rb_old)
    P_(r1("旧 案B（再現確認・w_pool 4）", so))
    for key, lab in (("A_final", "新 案A（週10通）"), ("B_final", "新 案B（週20通）"), ("C_final", "新 案C（週10通＋せどり）")):
        r = run(NEW, PL[key], N); keep[key] = r
        P_(r1(lab, ext(r)))
    sa, sb, sc = (ext(keep[k]) for k in ("A_final", "B_final", "C_final"))
    P_(f"- 卸 SKU の分布（新 案B）P10/P20/中央/P80/P90: {sb['wn']}・0件 {sb['wn0']:.0%}・平均 {sb['wn_mean']:.1f}（旧 {so['wn']}・0件 {so['wn0']:.0%}・平均 {so['wn_mean']:.1f}）")
    P_(f"- せどりの寄与（新）: 案C−案B {100 * (sc['p'] - sb['p']):+.0f}pt（中央 {man(sc['p50'] - sb['p50'])}）／案B−案A {100 * (sb['p'] - sa['p']):+.0f}pt")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## G2. 測り方2: 清算価値（現金＋未入金＋在庫×0.8−未払−200万）＋発注継続")
    P_("| 案 | P(清算価値>0) | P20／中央 | P10 | P(実質現金>0) | 月12の月商 中央 | 日次最低 P10 |"); P_("|---|---:|---|---:|---:|---:|---:|")
    for key, lab in (("A_final", "案A"), ("B_final", "案B"), ("C_final", "案C")):
        r = run(NEW, dict(PL[key], harvest=None, harvest_new=None), N); s = ext(r)
        P_(f"| {lab} | {s['pclose']:.0%} | {man(s['close20'])}／{man(s['close50'])} | {man(s['close10'])} | {s['p']:.0%} | {s['rev12'] / 1e4:.0f}万 | {s['thin10'] / 1e4:.0f}万 |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## G3. 新 案B を「実際に立った卸 SKU の数」で切った P（実質現金）")
    rb = keep["B_final"]
    for lo, hi, lab in ((0, 1, "0件"), (1, 3, "1〜2件"), (3, 6, "3〜5件"), (6, 999, "6件以上")):
        sub = [r for r in rb if lo <= r["meta"]["w_n"] < hi]
        if sub:
            s = summ(sub); P_(f"- {lab}（{len(sub) / len(rb):.0%}）: P {s['p']:.0%}・中央 {man(s['p50'])}・P20 {man(s['p20'])}")
    P_("")

    P_("## G4. 卸が0の世界（w_pool=0）＝メーカー打診専業／せどり＋打診"); P_(H1)
    Z = dict(NEW, w_pool=0.0)
    for key, lab in (("A_final", "専業 週10通"), ("B_final", "専業 週20通"), ("C_final", "週10通＋せどり（卸0）")):
        P_(r1(lab, ext(run(Z, PL[key], NS))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## G5. 逆算: 新 案B（実質現金＋発注停止）を P≥60% に戻す条件")
    P_("送信の週N通は send_B を N/20 倍。下書きの質は週20=0.85（据え置き）・週25=0.80・週30=0.75・週40=0.65（推測）。成立率は混合（平均3.05%）を倍率で拡大。")
    P_("| 送信＼成立率（平均） | 3.0%（×1.00） | 3.5%（×1.15） | 4.1%（×1.33） | 5.0%（×1.64） |"); P_("|---|---|---|---|---|")
    for w, qb in ((20, 0.85), (25, 0.80), (30, 0.75), (40, 0.65)):
        cells = []
        for f in (1.0, 1.15, 1.33, 1.64):
            s = summ(run(dict(NEW, send_B=sends(w / 20), q_B=qb, m_rate=rates(f)), PL["B_final"], NS))
            cells.append(f"{s['p']:.0%}／{man(s['p50'])}")
        P_(f"| 週{w}通 | " + " | ".join(cells) + " |")
    P_(f"- 経過 {time.time() - t0:.0f}秒")
    P_("")
    P_("| 1変数だけ動かす（週20通・成立率3.0%） | P／中央 |"); P_("|---|---|")
    one = [("週30通・質を落とさない（0.85）", dict(send_B=sends(1.5), q_B=0.85)),
           ("取り分の実現 0.85→1.0", dict(real=1.0)), ("取り分の実現 0.85→1.2", dict(real=1.2)),
           ("メーカー直の利益率 12%→14%", dict(m_m=0.14)), ("メーカー直の利益率 12%→16%", dict(m_m=0.16)),
           ("送信の低稼働 30%→15%", dict(low_B=0.15)), ("送信の低稼働 30%→45%（週20が続かない）", dict(low_B=0.45)),
           ("卸の母数 3（参考）", dict(w_pool=3.0)), ("卸の母数 4（旧・参考）", dict(w_pool=4.0, w_pool_sig=0.9)),
           ("送れる母数 300社（S-1 用）", dict(send_cap=300)), ("送れる母数 500社（S-1 用）", dict(send_cap=500)),
           ("送れる母数 700社（S-1 用）", dict(send_cap=700))]
    for lab, ov in one:
        s = summ(run(dict(NEW, **ov), PL["B_final"], NS)); P_(f"| {lab} | {s['p']:.0%}／{man(s['p50'])} |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## G6. 組み合わせ（週30通・質0.75 に1つ足す）"); P_("| 組み合わせ | P／中央 |"); P_("|---|---|")
    base30 = dict(send_B=sends(1.5), q_B=0.75)
    for lab, ov in (("週30＋低稼働15%（送信の仕組みが回る）", dict(low_B=0.15)), ("週30＋取り分1.0", dict(real=1.0)),
                    ("週20＋成立率4.1%＋取り分1.0", dict(send_B=sends(1.0), q_B=0.85, m_rate=rates(1.33), real=1.0))):
        s = summ(run({**NEW, **base30, **ov}, PL["B_final"], NS)); P_(f"| {lab} | {s['p']:.0%}／{man(s['p50'])} |")
    P_("")

    P_("## G7. 撤退条件を踏む確率（新 案B・新 案C）")
    for key in ("B_final", "C_final"):
        res = keep[key]; n = len(res)
        pr = lambda f: sum(1 for r in res if f(r)) / n
        cum = lambda r, t: sum(r["prof"][:t])
        P_(f"### {key}")
        P_(f"- E-1 2026-12末まで売上0: {pr(lambda r: sum(r['rev'][:3]) < 1):.0%}")
        P_(f"- E-2 2027-03末 累計損益 <−8万: {pr(lambda r: cum(r, 6) < -80_000):.0%}／<−5万: {pr(lambda r: cum(r, 6) < -50_000):.0%}")
        P_(f"- E-3 2027-06末 累計損益 <−5万: {pr(lambda r: cum(r, 9) < -50_000):.0%}")
        P_(f"- 最初の3 SKU の実現 <0.4: {pr(lambda r: r['meta']['early_ratio'] is not None and r['meta']['early_ratio'] < 0.4):.0%}／2027-01 までに SKU なし: {pr(lambda r: r['meta']['early_ratio'] is None):.0%}")
        for lab, f in (("最初の SKU の実現 ≥0.7", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] >= 0.7),
                       ("0.4〜0.7", lambda r: r["meta"]["early_ratio"] is not None and 0.4 <= r["meta"]["early_ratio"] < 0.7),
                       ("<0.4", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.4),
                       ("2027-01 までに SKU なし", lambda r: r["meta"]["early_ratio"] is None)):
            sub = [r for r in res if f(r)]
            if sub:
                s = summ(sub); P_(f"  - {lab}（{len(sub) / n:.0%}）: P {s['p']:.0%}・中央 {man(s['p50'])}")
        P_("")

    P_("## G8. 4軸×3シナリオ（新 案B・P20／中央／P80）")
    res = keep["B_final"]
    for lab, xs in (("月商 2027-06", [r["rev"][8] for r in res]), ("累計損益", [r["profit"] for r in res]),
                    ("実質現金", [r["cash"] for r in res]), ("日次最低現金", [r["thin"] for r in res])):
        P_(f"- {lab}: {man(q(xs, .2))}／{man(q(xs, .5))}／{man(q(xs, .8))}")
    P_(f"- 成立社数: {q([r['meta']['n_est'] for r in res], .2)}／{q([r['meta']['n_est'] for r in res], .5)}／{q([r['meta']['n_est'] for r in res], .8)}")
    P_(f"- 卸の SKU: {q([r['meta']['w_n'] for r in res], .2)}／{q([r['meta']['w_n'] for r in res], .5)}／{q([r['meta']['w_n'] for r in res], .8)}")
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
