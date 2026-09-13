#!/usr/bin/env python3
"""T-20260914-003 マサル: 推奨の最終形（C_final/B_final）の本計算。
最終形＝初回ロット1ヶ月分（補充で追う）・新規ロットは2027-06まで・補充は2027-07まで（2027-08から発注停止）・せどりは「2週で採用0件か1件8分超」と S-3 だけで止める。
01_mc.py の構造・置き値のまま。N=3000（感応度1500）。 python3 01_mc_final.py [--quick]"""
import importlib.util, sys, pathlib, io, time
HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mc", HERE / "01_mc.py")
mc = importlib.util.module_from_spec(spec); sys.modules["mc"] = mc; spec.loader.exec_module(mc)
q, man, summ, row, HDR, run, M, PL = mc.q, mc.man, mc.summ, mc.row, mc.HDR, mc.run, mc.MASARU, mc.PLANS


def main():
    quick = "--quick" in sys.argv
    N, NS = (400, 300) if quick else (3000, 1500)
    t0 = time.time(); out = io.StringIO()
    def P_(*a):
        print(*a, file=out); print(*a, flush=True)
    P_(f"# 01_mc_final 出力（T-20260914-003・マサル）N={N}（感応度 {NS}）")
    P_("最終形＝初回ロット1ヶ月分・新規ロットは2027-06まで・補充は2027-07まで（2027-08から発注停止）・せどりは2週で採用0件か1件8分超と S-3 だけで停止")
    P_("")
    keep = {}
    P_("## F1. 最終形の比較"); P_(HDR)
    for key, lab in (("A_final", "案A 最終形（週10通）"), ("B_final", "案B 最終形（週20通）"), ("C_final", "案C 最終形")):
        r = run(M, PL[key], N); keep[key] = r
        s = summ(r); P_(row(lab, s) + f" 手仕舞い値 P {s['pclose']:.0%}（{man(s['close50'])}）・月12の月商 中央 {s['rev12'] / 1e4:.0f}万")
    sc, sb, sa = summ(keep["C_final"]), summ(keep["B_final"]), summ(keep["A_final"])
    P_(f"- せどりの寄与: 案C−案B {100 * (sc['p'] - sb['p']):+.0f}pt（中央 {man(sc['p50'] - sb['p50'])}）／案C−案A {100 * (sc['p'] - sa['p']):+.0f}pt（中央 {man(sc['p50'] - sa['p50'])}）")
    rn = run(M, dict(PL["C_final"], rule="none"), N); keep["C_none_f"] = rn
    P_(row("参考 案C 最終形・試行の撤退条件なし（S-3 は適用）", summ(rn)))
    P_("")

    P_("## F2. 感応度（案C 最終形・1変数ずつ）"); P_("| 変数 | 悲観側 | 置き値 | 楽観側 |"); P_("|---|---|---|---|")
    sens = [("メーカー成立率（混合）", dict(m_rate=[(0.015, 1.0)]), dict(m_rate=[(0.05, 1.0)])),
            ("取り分の実現（0.85倍）", dict(real=0.5), dict(real=1.2)),
            ("卸の母数（4）", dict(w_pool=2.0), dict(w_pool=10.0)),
            ("メーカー直の利益率（12%）", dict(m_m=0.08), dict(m_m=0.16)),
            ("せどり採用率（2.5%）", dict(s_h=0.015), dict(s_h=0.05)),
            ("目視が続かない（40%）", dict(s_fatigue=0.70), dict(s_fatigue=0.15)),
            ("アカウント事故（年5%＋せどり12%）", dict(hz=0.15, s_hz=0.25), dict(hz=0.02, s_hz=0.03)),
            ("送信の低稼働（15%/50%）", dict(low_nofat=0.35, low_fat=0.70), dict(low_nofat=0.05, low_fat=0.25))]
    for lab, lo, hi in sens:
        a = summ(run(dict(M, **lo), PL["C_final"], NS)); c = summ(run(dict(M, **hi), PL["C_final"], NS))
        P_(f"| {lab} | {a['p']:.0%}／{man(a['p50'])} | {sc['p']:.0%}／{man(sc['p50'])} | {c['p']:.0%}／{man(c['p50'])} |")
    P_("")

    P_("## F3. 撤退条件を踏む確率")
    for key in ("C_final", "B_final"):
        res = keep[key]; n = len(res)
        pr = lambda f: sum(1 for r in res if f(r)) / n
        cum = lambda r, t: sum(r["prof"][:t])
        P_(f"### {key}")
        P_(f"- 1 日次現金 <60万: {pr(lambda r: r['thin'] < 600_000):.0%}")
        P_(f"- 2 2026-12末まで売上0: {pr(lambda r: sum(r['rev'][:3]) < 1):.0%}")
        P_(f"- 3 2027-03末 累計損益 <−10万: {pr(lambda r: cum(r, 6) < -100_000):.0%}／<−5万: {pr(lambda r: cum(r, 6) < -50_000):.0%}")
        P_(f"- 4 2027-06末 累計損益 <−10万: {pr(lambda r: cum(r, 9) < -100_000):.0%}／<0: {pr(lambda r: cum(r, 9) < 0):.0%}")
        def low2(r):
            s = r["meta"]["sends"]
            return any(s[i][0] < 0.5 * s[i][1] and s[i + 1][0] < 0.5 * s[i + 1][1] for i in range(1, 11))
        P_(f"- 6 送信が2ヶ月続けて計画の50%未満: {pr(low2):.0%}")
        if key == "C_final":
            P_(f"- 最終形のせどり停止 2週で採用0件: {pr(lambda r: r['meta']['trial_adopt'] == 0):.0%}／停止計（時間超過を含む）: {pr(lambda r: r['meta']['s_stop'] == 0):.0%}")
            P_(f"- S-3 申し立て1件: {pr(lambda r: r['meta']['complaint'] is not None):.0%}")
        P_(f"- 2027-06末 累計損益 ≥+10万: {pr(lambda r: cum(r, 9) >= 100_000):.0%}")
        P_(f"- アカウント事故: {pr(lambda r: r['meta']['inc'] is not None):.0%}（恒久 {pr(lambda r: r['meta']['perm']):.0%}）")
        P_(f"- 最初の3 SKU の実現 <0.5: {pr(lambda r: r['meta']['early_ratio'] is not None and r['meta']['early_ratio'] < 0.5):.0%}／月3までに SKU なし: {pr(lambda r: r['meta']['early_ratio'] is None):.0%}")
        P_(f"- 成立3社以上（12ヶ月内）: {pr(lambda r: r['meta']['n_est'] >= 3):.0%}")
        P_("")

    P_("## F4. せどりの試行（2週）の結果で分けた価値（案C 最終形・試行の撤退条件なし）")
    for lo, hi, lab in ((0, 1, "採用0件"), (1, 3, "1〜2件"), (3, 6, "3〜5件"), (6, 999, "6件以上")):
        sub = [r for r in rn if lo <= r["meta"]["trial_adopt"] < hi]
        if sub:
            s = summ(sub); P_(f"- {lab}（{len(sub) / len(rn):.0%}）: P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}（案B 最終形 {sb['p']:.0%}・{man(sb['p50'])}）")
    for gv in (0.10, 0.25, 0.45):
        sub = [r for r in rn if abs(r["meta"]["g"] - gv) < 1e-9]
        if sub:
            s = summ(sub); P_(f"- ゲートなし {gv:.0%} の世界（{len(sub) / len(rn):.0%}）: S-1 発動 {sum(1 for r in sub if r['meta']['trial_gate'] <= 4) / len(sub):.0%}／P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}")
    P_("")

    P_("## F5. W8（11/6）と途中の累計損益で、最後の実質現金はどう分かれるか（案C 最終形）")
    res = keep["C_final"]
    for lab, f in (("最初の SKU の実現 ≥0.7", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] >= 0.7),
                   ("0.4〜0.7", lambda r: r["meta"]["early_ratio"] is not None and 0.4 <= r["meta"]["early_ratio"] < 0.7),
                   ("<0.4", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.4),
                   ("月3までに SKU が立たない", lambda r: r["meta"]["early_ratio"] is None)):
        sub = [r for r in res if f(r)]
        if sub:
            s = summ(sub); P_(f"- {lab}（{len(sub) / len(res):.0%}）: P(実質>0) {s['p']:.0%}・中央 {man(s['p50'])}・P10 {man(s['p10'])}")
    for t, lab in ((4, "2027-01末"), (6, "2027-03末"), (9, "2027-06末")):
        cums = [(sum(r["prof"][:t]), r["cash"]) for r in res]
        P_(f"### {lab}（累計損益 中央 {man(q([c for c, _ in cums], .5))}／P20 {man(q([c for c, _ in cums], .2))}）")
        P_("| 累計損益の帯 | 経路の割合 | P(実質現金>0) | 実質現金 中央 |"); P_("|---|---:|---:|---:|")
        for lo, hi in ((-1e9, -80_000), (-80_000, -50_000), (-50_000, -20_000), (-20_000, 0), (0, 50_000), (50_000, 1e9)):
            sub = [c2 for c1, c2 in cums if lo <= c1 < hi]
            if sub:
                P_(f"| {man(lo) if lo > -1e8 else ''}〜{man(hi) if hi < 1e8 else ''} | {len(sub) / len(cums):.0%} | {sum(x > 0 for x in sub) / len(sub):.0%} | {man(q(sub, .5))} |")
    P_("")

    P_("## F6. 実質現金がマイナスの世界の特徴（案C 最終形）")
    bad = [r for r in res if r["cash"] <= 0]; good = [r for r in res if r["cash"] > 0]
    feats = [("最初の SKU の実現 <0.5", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.5),
             ("月3までに SKU が立たない", lambda r: r["meta"]["early_ratio"] is None),
             ("成立 2社以下", lambda r: r["meta"]["n_est"] <= 2), ("卸の SKU 2以下", lambda r: r["meta"]["w_n"] <= 2),
             ("送信の低稼働", lambda r: r["meta"]["low"]), ("せどりの目視が続かない", lambda r: r["meta"]["fatigue"]),
             ("せどりが試行で停止", lambda r: r["meta"]["s_stop"] == 0), ("アカウント事故", lambda r: r["meta"]["inc"] is not None),
             ("楽天の制限", lambda r: r["meta"]["rakuten"] is not None), ("申し立て（S-3）", lambda r: r["meta"]["complaint"] is not None)]
    P_(f"| 特徴 | マイナスの世界（{len(bad) / len(res):.0%}） | プラスの世界 | 倍率 |"); P_("|---|---:|---:|---:|")
    for lab, f in feats:
        a = sum(1 for r in bad if f(r)) / max(1, len(bad)); b = sum(1 for r in good if f(r)) / max(1, len(good))
        P_(f"| {lab} | {a:.0%} | {b:.0%} | {(a / b) if b else float('nan'):.1f} |")
    P_("")

    P_("## F7. 年2（24ヶ月）：2027-08〜09 停止→2027-10 再開 vs 続ける")
    P_("| 案 | 運用 | 12ヶ月の実質現金 中央（P） | 年2の月商 中央（月13／14／15／18／24） | 年2の利益 中央 | 24ヶ月の実質現金 中央（P） | 24ヶ月の累計損益 中央 | 24ヶ月の手仕舞い値 中央（P） |")
    P_("|---|---|---|---|---:|---|---:|---|")
    for key in ("C_final", "B_final"):
        for hv, hn, rs, lab in ((10, 9, 12, "停止→再開"), (None, None, None, "続ける")):
            r24 = run(M, dict(PL[key], harvest=hv, harvest_new=hn, resume=rs), NS, T=24)
            c12 = [r["endcash"][11] - r["ap"][11] - 2_000_000 for r in r24]
            y2p = [sum(r["prof"][12:]) for r in r24]; c24 = [r["cash"] for r in r24]
            cl = [r["close"] for r in r24]
            revm = lambda m: q([r["rev"][m - 1] for r in r24], .5) / 1e4
            P_(f"| {key} | {lab} | {man(q(c12, .5))}（{sum(x > 0 for x in c12) / len(c12):.0%}） | {revm(13):.0f}／{revm(14):.0f}／{revm(15):.0f}／{revm(18):.0f}／{revm(24):.0f}万 "
               f"| {man(q(y2p, .5))} | {man(q(c24, .5))}（{sum(x > 0 for x in c24) / len(c24):.0%}） | {man(q([r['profit'] for r in r24], .5))} | {man(q(cl, .5))}（{sum(x > 0 for x in cl) / len(cl):.0%}） |")
    P_("")

    P_("## F8. 3シナリオの代表経路（案C 最終形・実質現金の P20／中央／P80 に最も近い経路）")
    order = sorted(range(len(res)), key=lambda i: res[i]["cash"])
    names = [f"2026-{m_:02d}" for m_ in (10, 11, 12)] + [f"2027-{m_:02d}" for m_ in range(1, 10)]
    for p, lab in ((0.2, "悲観（P20）"), (0.5, "中央"), (0.8, "楽観（P80）")):
        r = res[order[int(p * (len(order) - 1))]]; m = r["meta"]
        P_(f"### {lab}: 実質現金 {man(r['cash'])}・累計損益 {man(r['profit'])}・日次最低 {r['thin'] / 1e4:.0f}万・初回入金 {r['first_payout']}")
        P_(f"- 中身: 卸SKU {m['w_n']}・成立 {m['n_est']}社・せどり {'停止(' + m['s_reason'] + ')' if m['s_stop'] is not None else '継続'}・原石 {m['gems']}件・目視 {'途中で減る' if m['fatigue'] else '続く'}・送信 {'低稼働' if m['low'] else '通常'}・事故 {'あり' if m['inc'] is not None else 'なし'}")
        P_("| 月 | 売上 | 利益 | 月末現金 | 在庫 | 売掛 | 未払 |"); P_("|---|---:|---:|---:|---:|---:|---:|")
        for t in range(12):
            P_(f"| {names[t]} | {r['rev'][t] / 1e4:.1f} | {r['prof'][t] / 1e4:+.1f} | {r['endcash'][t] / 1e4:.1f} | {r['inv'][t] / 1e4:.1f} | {r['ar'][t] / 1e4:.1f} | {r['ap'][t] / 1e4:.1f} |")
        P_("")
    P_("### 4軸×3シナリオ（案C 最終形・P20／中央／P80）")
    for lab, xs in (("月商 2027-06", [r["rev"][8] for r in res]), ("月商 2027-07（発注の最終月）", [r["rev"][9] for r in res]),
                    ("累計損益", [r["profit"] for r in res]), ("実質現金", [r["cash"] for r in res]), ("日次最低現金", [r["thin"] for r in res])):
        P_(f"- {lab}: {man(q(xs, .2))}／{man(q(xs, .5))}／{man(q(xs, .8))}")
    P_(f"- 成立社数: {q([r['meta']['n_est'] for r in res], .2)}／{q([r['meta']['n_est'] for r in res], .5)}／{q([r['meta']['n_est'] for r in res], .8)}")
    P_(f"- 卸の SKU: {q([r['meta']['w_n'] for r in res], .2)}／{q([r['meta']['w_n'] for r in res], .5)}／{q([r['meta']['w_n'] for r in res], .8)}")
    P_(f"- 初回入金日（中央）: {sorted(r['first_payout'] for r in res)[len(res) // 2]}")
    P_(f"\n所要 {time.time() - t0:.0f}秒")
    if not quick:
        (HERE / "01_mc_final_出力.txt").write_text(out.getvalue())


if __name__ == "__main__":
    main()
