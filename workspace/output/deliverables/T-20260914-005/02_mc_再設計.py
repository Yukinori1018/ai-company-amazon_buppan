#!/usr/bin/env python3
"""T-20260914-005 タケシ（再設計）: 打診先の母集団を P2（Amazon にいるがブランド未登録・第三者が売っている）と
P3（Amazon 不在・需要は類似/他モールで推定）に寄せた案A/B/C と、条件を1つ緩めたときの P（フロンティア）。

構造はマサルのまま（T-20260914-003/01_mc.py ＋ 00_cf_base.py、卸は T-20260914-004/03_mc_卸実測.py の NEW＝T-2 実測）。
変えたのは置き値だけ。ただし「1通ごとに母集団を引く」ため gen() の送信ループに3行だけ差し込む（pops が無ければ乱数列は元と同一）。
  - 母集団 pp: rm（成立率の倍率・経路共通の真の成立率に掛ける）/ m_sku / m_e / m_m / real_sig / lag_add（販売開始の追加遅れ・月）
検算: S-1 主（マサル 03_mc_S1反映 H3「両方＝S-1 主」31%／−7万・N=1500）を同じ乱数で再現してから差し替える。
python3 02_mc_再設計.py [--smoke]   出力は 02_mc_再設計_出力.txt に節ごとに追記。すべての置き値は（推測）。
"""
import importlib.util, sys, pathlib, time, math, inspect
HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "T-20260914-004"
spec = importlib.util.spec_from_file_location("w", SRC / "03_mc_卸実測.py")
w = importlib.util.module_from_spec(spec); sys.modules["w"] = w; spec.loader.exec_module(w)
mc = w.mc
NEW, PL, run, summ, man, q, ext, sends = w.NEW, w.PL, w.run, w.summ, w.man, w.q, w.ext, w.sends
OUT = HERE / "02_mc_再設計_出力.txt"

# ---------------------------------------------------------------- gen() への差し込み（母集団を1通ごとに引く）
src = inspect.getsource(mc.gen)
REP = [
    ('    def new_sku(kind, k0, e_mean, m_mean, m_sd):', '    def new_sku(kind, k0, e_mean, m_mean, m_sd, rs=None):'),
    ('        r = e * wm * lognorm(R, P["real"], P["real_sig"])', '        r = e * wm * lognorm(R, P["real"], rs if rs is not None else P["real_sig"])'),
    ('            if R.random() < rate * q:\n                lag = R.triangular(1.3, 3.0, 1.8)',
     '            pp = _pick_pop(R, P)\n            if R.random() < rate * q * (pp["rm"] if pp else 1.0):\n                lag = R.triangular(1.3, 3.0, 1.8) + (pp.get("lag_add", 0.0) if pp else 0.0)'),
    ('                est_k.append(k0)\n', '                est_k.append(k0)\n                if pp:\n                    meta.setdefault("est_pop", {}); meta["est_pop"][pp["name"]] = meta["est_pop"].get(pp["name"], 0) + (1 if k0 <= 11 else 0)\n'),
    ('                for _ in range(max(1, int(round(lognorm(R, P["m_sku"], 0.45))))):\n                    skus.append(new_sku("M", k0, P["m_e"], P["m_m"], P["m_msd"]))',
     '                _Q = pp or P\n                for _ in range(max(1, int(round(lognorm(R, _Q["m_sku"], 0.45))))):\n                    skus.append(new_sku("M", k0, _Q["m_e"], _Q["m_m"], P["m_msd"], (pp or {}).get("real_sig")))'),
]
for a, b in REP:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
def _pick_pop(R, P):
    pops = P.get("pops")
    if not pops:
        return None
    u = R.random(); acc = 0.0
    for wt, pp in pops:
        acc += wt
        if u < acc:
            return pp
    return pops[-1][1]
mc.__dict__["_pick_pop"] = _pick_pop
exec(compile(src, str(mc.__file__) + ":gen(patched)", "exec"), mc.__dict__)

# ---------------------------------------------------------------- 置き値
R_OLD = mc.MASARU["m_rate"]                        # 1.5/3/5%（30/45/25%）平均3.05%＝EC STARs（二次）
R_S1 = [(0.008, 0.30), (0.015, 0.45), (0.025, 0.25)]  # マサル S-1 主（参照用）
def scale(tab, f):
    return [(r * f, p) for r, p in tab]
S1 = dict(NEW, m_rate=R_S1, send_cap=375)          # マサルの S-1 主（検算用）

# 母集団（1通あたりの成立率は「経路共通の真の成立率（R_OLD から1回引く）× rm」）
P2 = dict(name="P2", rm=1.0, m_sku=1.5, m_e=30_000, m_m=0.12, real_sig=0.70, lag_add=0.0)
P3 = dict(name="P3", rm=1.0, m_sku=1.3, m_e=20_000, m_m=0.14, real_sig=1.10, lag_add=1.0)
# 案の置き値
A = dict(NEW, m_rate=R_OLD, m_sku=1.5, send_cap=230)                                   # P2 のみ 週20通
B = dict(NEW, m_rate=R_OLD, pops=[(0.6, P2), (0.4, P3)], send_B=sends(1.5), q_B=0.75,  # P2＋P3 週30通
         send_cap=450, low_B=0.35)
C = dict(A)                                                                           # P2 週10通＋せどり（C_final）

def ext2(res):
    s = ext(res); n = len(res)
    cp6 = [sum(r["prof"][:6]) for r in res]
    s["e2"] = sum(1 for x in cp6 if x < -80_000) / n
    hit = [r for r, x in zip(res, cp6) if x < -80_000]; miss = [r for r, x in zip(res, cp6) if x >= -80_000]
    s["e2_in"] = (sum(r["cash"] > 0 for r in hit) / len(hit)) if hit else float("nan")
    s["e2_out"] = (sum(r["cash"] > 0 for r in miss) / len(miss)) if miss else float("nan")
    s["n0"] = sum(1 for r in res if r["meta"]["n_est"] == 0) / n
    pops = {}
    for r in res:
        for k, v in r["meta"].get("est_pop", {}).items():
            pops.setdefault(k, []).append(v)
    s["pops"] = {k: (sum(v) / n) for k, v in pops.items()}
    return s

H = ("| 案・条件 | P(実質現金>0) | P20／中央／P80 | P10 | 平均 | 12月末まで売上0 | 初回入金（中央） | 成立 中央（0社の確率） | 月12の月商 中央 | 日次最低現金 P10 | 事故 |\n"
     "|---|---:|---|---:|---:|---:|---|---|---:|---:|---:|")
def r1(lab, s):
    return (f"| {lab} | {s['p']:.0%} | {man(s['p20'])}／{man(s['p50'])}／{man(s['p80'])} | {man(s['p10'])} | {man(s['mean'])} | {s['dec0']:.0%} "
            f"| {s['fp'] if s['fp'] != '9999' else 'なし'} | {s['nest']}社（{s['n0']:.0%}） | {s['rev12'] / 1e4:.0f}万 | {s['thin10'] / 1e4:.0f}万 | {s['inc']:.0%} |")
def r2(lab, s):
    return f"| {lab} | {s['p']:.0%} | {man(s['p50'])} | {man(s['p20'])} | {s['nest']}社 |"

def binom_ge(n, p, k):
    return 1 - sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k))


def main():
    smoke = "--smoke" in sys.argv
    N, NF = (40, 40) if smoke else (1500, 1000)
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    P_(f"# 02_mc_再設計 出力 N={N}（フロンティア {NF}）seed={mc.SEED}")
    P_("")
    P_("## K0. 検算（マサル S-1 主・案B 週20通 を同じ乱数で）")
    s = ext2(run(S1, PL["B_final"], 1500 if not smoke else 40)); P_(H); P_(r1("S-1 主 案B（マサル 31%／−7万 の再現）", s))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## K1. 案A/B/C（測り方1：実質現金＋2027-08 から発注停止）"); P_(H)
    keep = {}
    for key, P, plan, lab in (("A", A, "B_final", "案A P2 週20通"), ("B", B, "B_final", "案B P2＋P3 週30通"),
                              ("C", C, "C_final", "案C P2 週10通＋せどり（緩和）")):
        keep[key] = ext2(run(P, PL[plan], N)); P_(r1(lab, keep[key]))
    P_(r1("検算 案A を pops=[(1.0,P2)] で", ext2(run(dict(A, pops=[(1.0, P2)]), PL["B_final"], N))))
    P_(r1("参考 P3 のみ 週20通", ext2(run(dict(A, pops=[(1.0, P3)], send_cap=230), PL["B_final"], NF))))
    P_(r1("参考 P2 のみ 週30通（母数230）", ext2(run(dict(A, send_B=sends(1.5), q_B=0.75, low_B=0.35), PL["B_final"], NF))))
    for key in ("A", "B", "C"):
        s = keep[key]
        P_(f"- 案{key}: 成立の内訳（12ヶ月・平均社数）{ {k: round(v, 2) for k, v in s['pops'].items()} }／E-2（2027-03 累計損益<−8万）踏む {s['e2']:.0%}・踏んだ世界の P {s['e2_in']:.0%}・踏まない {s['e2_out']:.0%}")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## K2. 測り方2（清算価値＋発注継続）")
    P_("| 案 | P(清算価値>0) | 中央 | P20 | 月12の月商 中央 |"); P_("|---|---:|---:|---:|---:|")
    for key, P, plan in (("A", A, "B_final"), ("B", B, "B_final"), ("C", C, "C_final")):
        s = ext2(run(P, dict(PL[plan], harvest=None, harvest_new=None), N))
        P_(f"| 案{key} | {s['pclose']:.0%} | {man(s['close50'])} | {man(s['close20'])} | {s['rev12'] / 1e4:.0f}万 |")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## K3. フロンティア（案A から条件を1つだけ緩める／悪くする）"); P_("| 条件 | P(実質現金>0) | 中央 | P20 | 成立 中央 |"); P_("|---|---:|---:|---:|---:|")
    base = ext2(run(A, PL["B_final"], NF)); P_(r2("基準 案A（P2・週20・成立率 平均3.05%・母数230）", base))
    L18 = dict(PL["B_final"], harvest=16, harvest_new=15)
    rows = [
        ("成立率 平均2.0%（悪化）", A, PL["B_final"], dict(m_rate=scale(R_OLD, 0.656))),
        ("成立率 平均4.0%", A, PL["B_final"], dict(m_rate=scale(R_OLD, 1.31))),
        ("成立率 平均5.0%", A, PL["B_final"], dict(m_rate=scale(R_OLD, 1.64))),
        ("送れる母数 330（第2の展示会で補給）", A, PL["B_final"], dict(send_cap=330)),
        ("週30通・母数330", A, PL["B_final"], dict(send_B=sends(1.5), q_B=0.75, low_B=0.35, send_cap=330)),
        ("週30通・母数450", A, PL["B_final"], dict(send_B=sends(1.5), q_B=0.75, low_B=0.35, send_cap=450)),
        ("SKU/社 1.5→2.0", A, PL["B_final"], dict(m_sku=2.0)),
        ("取り分の実現 0.85→1.1（成立社の3割が月6以降に独占化の代理）", A, PL["B_final"], dict(real=1.1)),
        ("卸の母数 2→4（SD・卸2社の登録が当たる）", A, PL["B_final"], dict(w_pool=4.0, w_pool_sig=0.9)),
        ("送信の低稼働 30%→15%（週1ブロックが回る）", A, PL["B_final"], dict(low_B=0.15)),
        ("送信の低稼働 30%→45%（続かない）", A, PL["B_final"], dict(low_B=0.45)),
        ("メーカー直の利益率 12%→15%", A, PL["B_final"], dict(m_m=0.15)),
        ("期間 12→18ヶ月（2028-03 判定・2028-02 から発注停止）", A, L18, {}),
        ("せどり限定再開（案C・既定の緩和）", C, PL["C_final"], {}),
        ("せどり限定再開＋週20通", C, dict(PL["C_final"], send="B"), {}),
        ("—2つ緩める— 成立率4%＋週30通・母数450", A, PL["B_final"], dict(m_rate=scale(R_OLD, 1.31), send_B=sends(1.5), q_B=0.75, low_B=0.35, send_cap=450)),
        ("—2つ緩める— 成立率 平均3.05%のまま＋18ヶ月", A, L18, {}),
        ("—2つ緩める— せどり＋18ヶ月", C, dict(PL["C_final"], harvest=16, harvest_new=15), {}),
        ("—2つ緩める— 成立率4%＋18ヶ月", A, L18, dict(m_rate=scale(R_OLD, 1.31))),
        ("—悪い方に2つ— 成立率2%＋SKU/社1.2", A, PL["B_final"], dict(m_rate=scale(R_OLD, 0.656), m_sku=1.2)),
    ]
    for lab, P, plan, ov in rows:
        T = 18 if plan.get("harvest") == 16 else 12
        res = run(dict(P, **ov), plan, NF, T=T)
        P_(r2(lab, ext2(res)))
        if T == 18:
            pass
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    P_("## K4. 最初の50通で母集団を見分けられるか（二項分布・解析）")
    P_("見積到達率＝成立率÷0.37（v2 の置き値：送信あたり見積8%・成立3%の比）。")
    P_("| 真の成立率 | 見積到達率 | 50通で見積≥3件 | 50通で見積0件 | 100通で見積≥5件 |"); P_("|---|---:|---:|---:|---:|")
    for m in (0.015, 0.02, 0.03, 0.04, 0.05):
        qq = m / 0.37
        P_(f"| {m:.1%} | {qq:.1%} | {binom_ge(50, qq, 3):.0%} | {(1 - qq) ** 50:.0%} | {binom_ge(100, qq, 5):.0%} |")
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
