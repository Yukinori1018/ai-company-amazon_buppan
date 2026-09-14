#!/usr/bin/env python3
"""T-20260914-005 マサル（検証）: タケシ再設計の推奨（案B＋固定費圧縮）を独立に再現し、P2 前提・固定費・18ヶ月を検証する。
構造は T-20260914-003/01_mc.py（日次 00_cf_base.py）＋ T-20260914-004/03_mc_卸実測.py（卸 T-2 実測）。タケシの 02_mc_再設計.py は import しない。
差し込み（タケシと別の作り）:
  - 母集団は「成立した社」に1回だけ付ける。乱数は主系列を消費しない別系列（R2）。pops が無い案は元の乱数列と完全に同一
  - seq モード＝「P2 を先に送り切り、尽きたら P3」（タケシ本文の運用）。mix モード＝1通ごとに 60/40（タケシのコードの運用）
  - 固定費を月別リストで持つ（Keepa の契約月・段階2 の発動月を表せる）
python3 03_mc_マサル検証.py [--smoke]   出力 03_mc_マサル検証_出力.txt（節ごとに追記）。すべて（推測）。"""
import importlib.util, sys, pathlib, time, math, random, inspect
import multiprocessing as mp

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "T-20260914-004"
spec = importlib.util.spec_from_file_location("w", SRC / "03_mc_卸実測.py")
w = importlib.util.module_from_spec(spec); sys.modules["w"] = w; spec.loader.exec_module(w)
mc = w.mc; cf = mc.cf
NEW, PL, sends = w.NEW, w.PL, w.sends
R_OLD = mc.MASARU["m_rate"]          # 1.5/3/5%（30/45/25%）平均3.05%
OUT = HERE / "03_mc_マサル検証_出力.txt"

def scale(tab, f):
    return [(r * f, p) for r, p in tab]

# ---------------------------------------------------------------- gen() の差し込み（マサル版）
src = inspect.getsource(mc.gen)
REP = [
    ('    def new_sku(kind, k0, e_mean, m_mean, m_sd):', '    def new_sku(kind, k0, e_mean, m_mean, m_sd, rs=None):'),
    ('        r = e * wm * lognorm(R, P["real"], P["real_sig"])', '        r = e * wm * lognorm(R, P["real"], P["real_sig"] if rs is None else rs)'),
    ('    rate = pick(R, P["m_rate"]) * P["m_gate"]\n',
     '    rate = pick(R, P["m_rate"]) * P["m_gate"]\n    R2 = random.Random(_seed_of(R))\n    meta["est_pop"] = {}\n'),
    ('            if R.random() < rate * q:\n                lag = R.triangular(1.3, 3.0, 1.8)\n                k0 = k + int(round(lag))',
     '            pp = _pop_of(P, sent, R2)\n            if R.random() < rate * q * (pp["rm"] if pp else 1.0):\n'
     '                lag = R.triangular(1.3, 3.0, 1.8) + (pp["lag_add"] if pp else 0.0)\n                k0 = k + int(round(lag))'),
    ('                est_k.append(k0)\n',
     '                est_k.append(k0)\n                if pp and k0 <= 11:\n                    meta["est_pop"][pp["name"]] = meta["est_pop"].get(pp["name"], 0) + 1\n'),
    ('                for _ in range(max(1, int(round(lognorm(R, P["m_sku"], 0.45))))):\n                    skus.append(new_sku("M", k0, P["m_e"], P["m_m"], P["m_msd"]))',
     '                Q = pp or P\n                for _ in range(max(1, int(round(lognorm(R, Q["m_sku"], 0.45))))):\n'
     '                    skus.append(new_sku("M", k0, Q["m_e"], Q["m_m"], P["m_msd"], pp["real_sig"] if pp else None))'),
    ('    meta["n_est"] = sum(1 for k0 in est_k if k0 <= 11)', '    meta["n_est"] = sum(1 for k0 in est_k if k0 <= 11)\n    meta["est_k"] = sorted(est_k)'),
]
for a, b in REP:
    assert src.count(a) == 1, a
    src = src.replace(a, b)

def _seed_of(R):                      # 主系列を消費しない
    return hash(R.getstate()[1][:8])

def _pop_of(P, sent, R2):
    if "seq" in P:                    # [(通数, 母集団)…] を前から送る
        acc = 0
        for cap, pp in P["seq"]:
            acc += cap
            if sent <= acc:
                return pp
        return P["seq"][-1][1]
    if "mix" in P:
        u = R2.random(); acc = 0.0
        for wt, pp in P["mix"]:
            acc += wt
            if u < acc:
                return pp
        return P["mix"][-1][1]
    return None

mc.__dict__["_seed_of"] = _seed_of; mc.__dict__["_pop_of"] = _pop_of
exec(compile(src, str(mc.__file__) + ":gen(masaru)", "exec"), mc.__dict__)


def run_one2(args):
    seed, P, plan, T = args
    P = dict(P, **plan.get("Pov", {}))
    R = random.Random(seed)
    orders, meta = mc.gen(R, P, plan, T)
    fl = P.get("fixed_list")
    fixed = [float(fl[min(k, len(fl) - 1)]) if fl else float(P["fixed"]) for k in range(T)]
    if P.get("stage2") and len(meta["est_k"]) >= 2:        # 段階2（ハジメ）: 成立2社目の販売開始の翌月から
        k2 = meta["est_k"][1] + 1
        for k in range(k2, T):
            fixed[k] += P["stage2"]
        if k2 < T:
            fixed[k2] += P.get("stage2_once", 0)
    cfg = cf.Config(months=T, fixed_monthly=fixed)
    if meta["inc"] is not None:
        a = cf.nth_month_start(cfg.start, meta["inc"]); cfg.halt_win = (cf.add(a, -14), cf.add(a, 61))
    def policy(st, k, d):
        req = orders[k]
        if not req:
            return []
        budget = st.cash - cfg.reserve - st.committed_outflows(d) - cfg.fixed_monthly[min(k + 1, cfg.months - 1)]
        tot = sum(a for _, a in req)
        f = 1.0 if tot <= 0 else max(0.0, min(1.0, budget / tot))
        return [(ln, a * f) for ln, a in req if a * f > 0]
    res = cf.simulate(cfg, policy)
    rows = res["rows"]; cash = res["cum_cash"]
    if meta["perm"]:
        dinc = cf.nth_month_start(cfg.start, meta["inc"]); cash -= 0.65 * res["state"].inventory(dinc)
    last = rows[-1]
    close = last["月末現金"] + last["売掛"] + 0.8 * last["在庫"] - last["未払"] - cfg.cash0
    return dict(cash=cash, thin=res["thin_cash"], profit=res["cum_profit"], close=close,
                rev=[r["売上"] for r in rows], prof=[r["利益"] for r in rows],
                endcash=[r["月末現金"] for r in rows], ap=[r["未払"] for r in rows], ar=[r["売掛"] for r in rows], inv=[r["在庫"] for r in rows],
                first_payout=str(res["first_payout"]), meta=meta)


_POOL = None
def run(P, plan, n, T=12):
    global _POOL
    if _POOL is None:
        _POOL = mp.get_context("fork").Pool(8)
    return _POOL.map(run_one2, [(mc.SEED * 1000 + i, P, plan, T) for i in range(n)], chunksize=max(1, n // 64))

q, man = mc.q, mc.man
def S(res):
    n = len(res); c = [r["cash"] for r in res]
    pops = {}
    for r in res:
        for k, v in r["meta"].get("est_pop", {}).items():
            pops[k] = pops.get(k, 0) + v
    return dict(p=sum(x > 0 for x in c) / n, p10=q(c, .1), p20=q(c, .2), p50=q(c, .5), p80=q(c, .8), mean=sum(c) / n,
                nest=q([r["meta"]["n_est"] for r in res], .5), n0=sum(r["meta"]["n_est"] == 0 for r in res) / n,
                dec0=sum(sum(r["rev"][:3]) < 1 for r in res) / n, inc=sum(r["meta"]["inc"] is not None for r in res) / n,
                thin10=q([r["thin"] for r in res], .1), rev9=q([r["rev"][8] for r in res], .5),
                pops={k: round(v / n, 2) for k, v in pops.items()})
H = "| 条件 | P(実質現金>0) | P10 | P20／中央／P80 | 平均 | 成立 中央（0社） | 12月末まで売上0 |\n|---|---:|---:|---|---:|---|---:|"
def row(lab, s):
    return (f"| {lab} | {s['p']:.0%} | {man(s['p10'])} | {man(s['p20'])}／{man(s['p50'])}／{man(s['p80'])} | {man(s['mean'])} "
            f"| {s['nest']}社（{s['n0']:.0%}） | {s['dec0']:.0%} |")

# ---------------------------------------------------------------- 置き値
P2 = dict(name="P2", rm=1.0, m_sku=1.5, m_e=30_000, m_m=0.12, real_sig=0.70, lag_add=0.0)   # タケシ §2-2 のまま
P3 = dict(name="P3", rm=1.0, m_sku=1.3, m_e=20_000, m_m=0.14, real_sig=1.10, lag_add=1.0)
def pops_sig(d):                     # Keepa なしで読みが粗くなる（推測）
    return dict(P2, real_sig=P2["real_sig"] + d), dict(P3, real_sig=P3["real_sig"] + d)
W30 = dict(send_B=sends(1.5), q_B=0.75, low_B=0.35)
A = dict(NEW, m_rate=R_OLD, m_sku=1.5, send_cap=230)                                # タケシ案A
B_T = dict(NEW, m_rate=R_OLD, **W30, mix=[(0.6, P2), (0.4, P3)], send_cap=450)        # タケシ案B（コードどおり）
def B_R(p2=310, p3=70, pp2=P2, pp3=P3, **kw):                                         # 本文どおり: P2 を先に、尽きたら P3
    return dict(NEW, m_rate=R_OLD, **W30, seq=[(p2, pp2), (p3, pp3)], send_cap=p2 + p3, **kw)

API, PRO, DOM, ACC, OGU = 8_732, 5_168, 131, 1_000, 5_390       # 月額（円）。€49／€29 は 178.2円/€（ハジメ段階1と同じ換算）
def fx(T=12, api=(), pro_from=None, ogu=True, other=True):
    return [(OGU if ogu else 0) + ((DOM + ACC) if other else 0) + (API if k in api else 0) + (PRO if (pro_from is not None and k >= pro_from) else 0)
            for k in range(T)]
F_NOW = fx(api=range(12))                   # 現状: API €49 を12ヶ月（15,253）
F_TK = fx(api=(0, 1), pro_from=2)          # タケシ: 10〜11月 API → 12月から Pro
L18 = dict(PL["B_final"], harvest=16, harvest_new=15)


def main():
    smoke = "--smoke" in sys.argv
    N, NF = (40, 40) if smoke else (1500, 1000)
    t0 = time.time(); OUT.write_text("")
    def P_(*a):
        line = " ".join(str(x) for x in a); print(line, flush=True)
        with OUT.open("a") as f:
            f.write(line + "\n")
    BF = PL["B_final"]
    P_(f"# 03_mc_マサル検証 出力 N={N}（感応度 {NF}）seed={mc.SEED}"); P_("")

    # ---- V1 再現
    P_("## V1. 独立再現（推奨＝案B＋固定費圧縮）"); P_(H)
    s = S(run(dict(A, fixed=12_283), BF, NF)); P_(row("案A＋Pro（差し込みなし＝元の乱数列。タケシ N=1000 で 47.6%・−0.8万）", s))
    s = S(run(dict(B_T, fixed=12_283), BF, N)); P_(row("案B＋Pro コードどおり（mix 60/40・母数450・固定費 平均12,283）", s))
    keep = {}
    keep["BT"] = run(dict(B_T, fixed_list=F_TK), BF, N); P_(row("同・固定費を月別（10〜11月 15,253 → 12月から 11,689）", S(keep["BT"])))
    P_(row("本文どおり: P2 を先に送る・母数450（P2 230→P3 220）", S(run(dict(B_R(230, 220), fixed_list=F_TK), BF, N))))
    P_(row("本文どおり＋供給の実数: P2 230→P3 70（計300・名簿補給なし）", S(run(dict(B_R(230, 70), fixed_list=F_TK), BF, N))))
    keep["BR"] = run(dict(B_R(310, 70), fixed_list=F_TK), BF, N)
    P_(row("本文どおり＋供給の実数＋第2の名簿（P2 310→P3 70・計380）＝マサル基準", S(keep["BR"])))
    P_(f"- 成立の内訳（平均社数）: コードどおり {S(keep['BT'])['pops']}／マサル基準 {S(keep['BR'])['pops']}")
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    # ---- V2 P2 の脆さ
    P_("## V2. P2 の送れる数 × 成立率（マサル基準の構造・固定費はタケシの月別）"); P_(H)
    for p2, lab2 in ((310, "P2 310（230＋第2の名簿80）"), (230, "P2 230（補給なし）"), (100, "P2 100")):
        for m, labm in ((1.0, "3.05%"), (0.656, "2.0%"), (0.492, "1.5%")):
            P_(row(f"{lab2}・成立率 平均{labm}", S(run(dict(B_R(p2, 70), m_rate=scale(R_OLD, m), fixed_list=F_TK), BF, NF))))
    P_(row("コードどおり（mix・母数450）・成立率 平均2.0%", S(run(dict(B_T, m_rate=scale(R_OLD, 0.656), fixed_list=F_TK), BF, NF))))
    P_(row("P2 100・P3 150（P3 の上限）・成立率 平均2.0%", S(run(dict(B_R(100, 150), m_rate=scale(R_OLD, 0.656), fixed_list=F_TK), BF, NF))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    # ---- V3 固定費
    P_("## V3a. 固定費だけを動かす（コードどおりの案B・他は同じ）"); P_(H)
    rows3 = [("現状 API €49×12（15,253）", F_NOW), ("タケシ: 10〜11月 API→12月から Pro", F_TK),
             ("API を 9月の支払い済み期間で使い切り 10/4 解約→Pro 12ヶ月＋補給月（1月）だけ API", fx(api=(3,), pro_from=0)),
             ("API は補給月（1月）だけ・Pro なし", fx(api=(3,))), ("API は10月と1月だけ・Pro なし", fx(api=(0, 3))),
             ("Keepa なし（無料拡張のみ）", fx()), ("Pro のみ（API は今月で終了）", fx(pro_from=0)),
             ("参考 ドメイン・会計ソフトも0（タケシ固定費−1,131）", [v - DOM - ACC for v in F_TK]),
             ("参考 大口→小口（−5,390。成約料・カート喪失はモデル外）", [v - OGU for v in F_TK]),
             ("参考 固定費0", [0] * 12)]
    for lab, fl in rows3:
        P_(row(f"{lab}（月平均 {sum(fl) / 12:,.0f}円）", S(run(dict(B_T, fixed_list=fl), BF, NF))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")
    P_("## V3b. 失う機能まで入れる（マサル基準の構造。劣化は推測）"); P_(H)
    p2s, p3s = pops_sig(0.15); p2h, p3h = pops_sig(0.08)
    rows3b = [("タケシ: 10〜11月 API→Pro（補給あり・読み劣化なし）", B_R(310, 70), F_TK, {}),
              ("現状 API×12（同上）", B_R(310, 70), F_NOW, {}),
              ("9月分で抽出→10/4 解約→Pro＋補給月 API", B_R(310, 70), fx(api=(3,), pro_from=0), {}),
              ("API は補給月だけ・Pro なし（読み σ+0.08）", B_R(310, 70, p2h, p3h), fx(api=(3,)), dict(real_sig=0.78)),
              ("Pro のみ・補給なし（名簿の Keepa 検証ができない）", B_R(230, 70), fx(pro_from=0), {}),
              ("Keepa なし・補給なし・読み σ+0.15", B_R(230, 70, p2s, p3s), fx(), dict(real_sig=0.85)),
              ("段階2が発動（成立2社目の翌月からセラースプライト13,998＋商標44,900）", dict(B_R(310, 70), stage2=13_998, stage2_once=44_900), F_TK, {})]
    for lab, P, fl, ov in rows3b:
        P_(row(f"{lab}（月平均 {sum(fl) / 12:,.0f}円）", S(run(dict(P, fixed_list=fl, **ov), BF, NF))))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    # ---- V4 18ヶ月
    P_("## V4. 18ヶ月判定（2028-03-31・2028-02 から発注停止）"); P_("| 条件 | P(18ヶ月の実質現金>0) | 18ヶ月 中央 | P10 | 同じ経路の12ヶ月時点 P（中央） | E-2 踏む／踏んだ世界の P18／踏まない世界の P18 |"); P_("|---|---:|---:|---:|---|---|")
    F18 = fx(T=18, api=(0, 1), pro_from=2)
    for lab, P in (("コードどおりの案B＋Pro", B_T), ("マサル基準＋Pro", B_R(310, 70)), ("マサル基準＋Pro・成立率2.0%", dict(B_R(310, 70), m_rate=scale(R_OLD, 0.656)))):
        res = run(dict(P, fixed_list=F18), L18, NF, T=18)
        c = [r["cash"] for r in res]; c12 = [r["endcash"][11] - r["ap"][11] - 2_000_000 for r in res]
        e2 = [sum(r["prof"][:6]) < -80_000 for r in res]
        hit = [x for x, e in zip(c, e2) if e]; mis = [x for x, e in zip(c, e2) if not e]
        P_(f"| {lab} | {sum(x > 0 for x in c) / len(c):.0%} | {man(q(c, .5))} | {man(q(c, .1))} | {sum(x > 0 for x in c12) / len(c12):.0%}（{man(q(c12, .5))}） "
           f"| {sum(e2) / len(e2):.0%}／{(sum(x > 0 for x in hit) / len(hit)) if hit else float('nan'):.0%}／{(sum(x > 0 for x in mis) / len(mis)) if mis else float('nan'):.0%} |")
    # 同じ18ヶ月の地平で「12ヶ月計画（2027-08 から停止）」と「18ヶ月計画」を同じ乱数で比べる
    r12x = run(dict(B_T, fixed_list=F18), BF, NF, T=18); r18 = run(dict(B_T, fixed_list=F18), L18, NF, T=18)
    for kk in (6, 9, 10):
        same = sum(all(abs(a - b) < 1 for a, b in zip(x["prof"][:kk], y["prof"][:kk])) for x, y in zip(r12x, r18)) / NF
        P_(f"- 同じ乱数で、月1〜{kk} の損益が12ヶ月計画と18ヶ月計画で一致する経路: {same:.0%}")
    cl12 = [r["endcash"][11] + r["ar"][11] + 0.8 * r["inv"][11] - r["ap"][11] - 2_000_000 for r in r18]
    c12 = [r["endcash"][11] - r["ap"][11] - 2_000_000 for r in r18]
    P_(f"- 18ヶ月計画の 2027-09-30 時点: 実質現金 P {sum(x > 0 for x in c12) / NF:.0%}・中央 {man(q(c12, .5))}／清算価値 P {sum(x > 0 for x in cl12) / NF:.0%}・中央 {man(q(cl12, .5))}・在庫 中央 {q([r['inv'][11] for r in r18], .5) / 1e4:.0f}万")
    P_("")
    P_("### E-2 の較正（2027-03 末の累計損益の帯 → 最後の P）")
    P_("| 帯 | 12ヶ月: 割合 | 12ヶ月: P12 | 18ヶ月: 割合 | 18ヶ月: P18 |"); P_("|---|---:|---:|---:|---:|")
    rr12 = keep["BR"]; rr18 = run(dict(B_R(310, 70), fixed_list=F18), L18, NF, T=18)
    cp = lambda r: sum(r["prof"][:6])
    for lo, hi in ((-1e9, -80_000), (-80_000, -60_000), (-60_000, -40_000), (-40_000, -20_000), (-20_000, 0), (0, 1e9)):
        a = [r["cash"] for r in rr12 if lo <= cp(r) < hi]; b = [r["cash"] for r in rr18 if lo <= cp(r) < hi]
        lab = (f"〜{man(hi)}" if lo < -1e8 else (f"{man(lo)}〜" if hi > 1e8 else f"{man(lo)}〜{man(hi)}"))
        P_(f"| {lab} | {len(a) / len(rr12):.0%} | {(sum(x > 0 for x in a) / len(a)) if a else float('nan'):.0%} | {len(b) / len(rr18):.0%} | {(sum(x > 0 for x in b) / len(b)) if b else float('nan'):.0%} |")
    P_(f"- 2027-03 末の累計損益 中央（12ヶ月計画・マサル基準）: {man(q([cp(r) for r in rr12], .5))}／P20 {man(q([cp(r) for r in rr12], .2))}")
    stop = dict(W30, send_B=sends(1.5)[:6] + [0] * 18)
    P_(row("12ヶ月判定で 2027-04 以降の送信を止めた場合（マサル基準＋Pro）", S(run(dict(B_R(310, 70), **stop, fixed_list=F_TK), BF, NF))))
    P_(row("比較: 送信を続ける（マサル基準＋Pro）", S(keep["BR"][:NF] if len(keep["BR"]) >= NF else keep["BR"])))
    P_(f"- 経過 {time.time() - t0:.0f}秒"); P_("")

    # ---- V5 4軸×3シナリオとプレモーテム（マサル基準＋Pro）
    P_("## V5. 4軸×3シナリオ（マサル基準＋Pro・P20／中央／P80）")
    res = keep["BR"]
    for lab, xs in (("月商 2027-06", [r["rev"][8] for r in res]), ("成立社数", [r["meta"]["n_est"] for r in res]),
                    ("実質現金 2027-09", [r["cash"] for r in res]), ("日次最低現金", [r["thin"] for r in res])):
        f_ = (lambda v: f"{v}社") if lab == "成立社数" else (lambda v: f"{v / 1e4:+.0f}万" if "現金 20" in lab else f"{v / 1e4:.0f}万")
        P_(f"- {lab}: {f_(q(xs, .2))}／{f_(q(xs, .5))}／{f_(q(xs, .8))}")
    for lab, ov in (("価格・競合 楽観（値下げ応酬なし・本体参入なし）", dict(pw=0.0, amz=0.0)),
                    ("価格・競合 悲観（値下げ応酬 月6%・本体参入 年14%）", dict(pw=0.06, amz=0.012))):
        P_(row(lab, S(run(dict(B_R(310, 70), fixed_list=F_TK, **ov), BF, NF))))
    bad = [r for r in res if r["cash"] <= 0]; good = [r for r in res if r["cash"] > 0]
    P_(f"| 特徴 | マイナスの世界（{len(bad)}） | プラスの世界（{len(good)}） | 倍率 |"); P_("|---|---:|---:|---:|")
    feats = [("成立 3社以下", lambda r: r["meta"]["n_est"] <= 3), ("送信の低稼働", lambda r: r["meta"]["low"]),
             ("最初の SKU の実現 <0.5", lambda r: r["meta"]["early_ratio"] is not None and r["meta"]["early_ratio"] < 0.5),
             ("2027-01 までに SKU なし", lambda r: r["meta"]["early_ratio"] is None), ("卸の SKU 0", lambda r: r["meta"]["w_n"] == 0),
             ("P3 の成立が P2 以上", lambda r: r["meta"]["est_pop"].get("P3", 0) >= max(1, r["meta"]["est_pop"].get("P2", 0))),
             ("アカウント事故", lambda r: r["meta"]["inc"] is not None)]
    for lab, f in feats:
        a = sum(1 for r in bad if f(r)) / max(1, len(bad)); b = sum(1 for r in good if f(r)) / max(1, len(good))
        P_(f"| {lab} | {a:.0%} | {b:.0%} | {(a / b) if b > 0 else float('nan'):.1f} |")
    P_(f"\n所要 {time.time() - t0:.0f}秒")


if __name__ == "__main__":
    main()
