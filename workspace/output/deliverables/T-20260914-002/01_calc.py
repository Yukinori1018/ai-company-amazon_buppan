#!/usr/bin/env python3
"""T-20260914-002 12ヶ月黒字の計画 — レーン別・案別の12ヶ月キャッシュ（モンテカルロ）

月1=2026-10 … 月12=2027-09。月0（9/14〜30）は固定費の半月分だけ。
開始現金 200万円。予備 25万円を割る仕入れはしない（割るのは固定費だけ）。
乱数固定。金額は円。すべての置き値は（推測）。根拠は 01_12ヶ月黒字の計画.md §3 の変数表。

定義
- 累計損益 = 12ヶ月の SKU 利益（定義B：販売手数料×1.1・FBA・納品・保管・返品引当・外注費込み）
            − 固定費 − レーン固定費（外注・ツール）− 一回払い − 広告 − 在庫の評価損。在庫は原価で資産に数える
- 現金ベース = 12ヶ月末の現金 − 200万（在庫を0円と数える。社長の言葉どおりの厳しい方）
- 最薄現金 = 期間中の現金残高の最小値（在庫に化けた分を除いた手元現金）
"""
import math, random, sys

SEED = 20260914
N = 12000
START = 2_000_000
FLOOR = 250_000
FIXED = 14_253 + 1_000          # 大口5,390＋Keepa API 8,732＋ドメイン131（ハジメ03 実測）＋会計ソフト1,000（二次）
SD_FEE = 2_200                  # スーパーデリバリー会費（推測・未確認）
MONTHS = 12
RECV = 0.66 * 0.70               # 月末の Amazon 未入金＝売上の約20日分×入金率（ハジメ T-20260914-003 §1：売上→着金 中央20日）
R_TRI = [1.3, 3.0, 1.8]          # 成立→初回売上の遅れ（月）：最小・最大・最頻

BASE = dict(
    # 共通
    wm_sig=0.30,                 # 需要の実現倍率（全レーン共通の相関）
    hazard=0.05,                 # アカウント事故（年率）。停止2ヶ月・25%で恒久
    perm=0.25,
    # W 需要先行×卸マルチ照合（NETSEA・SD・卸問屋.com・国分）
    w_pool=6.0, w_pool_sig=0.9, sd_pass=0.60,
    w_rev=30_000, w_real=0.85, w_m=0.11, w_m_sd=0.035, w_fee=0.31, w_h=2.0, w_drift=0.003,
    # M メーカー直（Keepa起点=本丸B 7割／展示会=本丸A 3割）
    m_send=[10, 30] + [40] * 10, m_q=1.0, m_q300=1.0, m_consume=0.80, m_low=0.25,
    m_rate=[(0.015, 0.30), (0.03, 0.45), (0.05, 0.25)], m_gate=0.86,
    m_sku=2.0, m_rev=30_000, m_real=0.85, m_m=0.12, m_m_sd=0.04, m_fee=0.31, m_h=2.5, m_drift=0.002,
    m_minlot=50_000,
    # K モール間差分（人の目視。外注）→ W の母数×1.6、M の成立×1.25
    k_cost=30_000, k_w=1.6, k_m=1.25,
    # S 電脳せどり（限定再開）
    s_cap=500_000, s_cap_sig=0.6, s_gate=[(0.10, 0.35), (0.25, 0.45), (0.45, 0.20)],
    s_ramp=[0.15, 0.35, 0.60, 0.80, 1.0], s_m=0.09, s_m_sd=0.03, s_fee=0.28, s_h=1.3,
    s_wd=0.02, s_cost=30_000, harvest_from=99, harvest_h=0.5, s_low=0.0, s_low_f=0.3, s_stop=99, s_hazard=0.10, s_drift=0.001,
    # O 簡易OEM（非食品）
    o_sprite=13_998, o_noagree=0.35, o_tm=44_900, o_gs1=17_050, o_design=40_000, o_lot=150_000,
    o_rev=80_000, o_rev_sig=0.9, o_dud=0.40, o_m=0.30, o_fee=0.30,
    o_ramp=[0.15, 0.30, 0.50, 0.70, 0.85, 1.0], o_ads_early=0.25, o_ads=0.12, o_h=3.0,
    # X 中国輸入（輸入代行・自社ブランド）
    x_setup=30_000, x_rev=100_000, x_rev_sig=1.0, x_dud=0.45, x_m=0.24, x_fee=0.30,
    x_ads_early=0.30, x_ads=0.15, x_h=3.5, x_reg=0.10, x_hazard=0.05, x_max=5,
)

W20 = dict(m_send=[10, 40] + [80] * 10, m_q=0.85, m_q300=0.6)   # 週20通。質×0.85、累計300通超は×0.6（マサル2周目）
LANE_SETS = {
    "W 卸マルチ（需要先行）単独": ("W", {}),
    "M メーカー直 単独 週10通": ("M", {}),
    "S 電脳せどり 単独（外注の目視3万/月）": ("S", {}),
    "S 電脳せどり 単独（社長が目視・外注0）": ("S", dict(s_cost=0)),
    "O 簡易OEM 単独": ("O", {}),
    "X 中国輸入 単独": ("X", {}),
    "K モール間差分を足す：W＋M＋K": ("WMK", {}),
    "案A：W＋M 週10通": ("WM", {}),
    "案B：W＋M 週20通": ("WM", W20),
    "案C：W＋M＋S 週10通（せどり限定再開・外注）": ("WMS", {}),
    "案C'：W＋M＋S 週10通（社長が目視・必ず続く）": ("WMS", dict(s_cost=0)),
    "案C：W＋M＋S 週10通（社長が目視・続かない35%込み）": ("WMS", dict(s_cost=0, s_low=0.35)),
    "参考：W＋M＋O（OEMを1年目から）": ("WMO", {}),
    "案B＋月10から発注停止（刈り取り）": ("WM", dict(W20, harvest_from=10, harvest_h=0.0)),
    "案C＋月10から発注停止（刈り取り）": ("WMS", dict(s_cost=0, s_low=0.35, harvest_from=10, harvest_h=0.0, s_stop=10)),
}


def lognorm(R, med, sig):
    return med * math.exp(R.gauss(0, sig))


def pick(R, table):
    u = R.random(); acc = 0.0
    for v, p in table:
        acc += p
        if u < acc:
            return v
    return table[-1][0]


class Sku:
    __slots__ = ("start", "exp", "real", "m", "c", "h", "stock", "sold", "dead", "drift", "lane", "hist")

    def __init__(self, start, exp, real, m, fee, h, drift, lane):
        self.start, self.exp, self.real, self.m = start, exp, real, m
        self.c = max(0.2, 1 - fee - m)
        self.h, self.drift, self.lane = h, drift, lane
        self.stock = 0.0; self.sold = 0.0; self.dead = False; self.hist = []


def sim(lanes, R, P):
    wm = lognorm(R, 1.0, P["wm_sig"])
    hz = P["hazard"] + (P["s_hazard"] if "S" in lanes else 0) + (P["x_hazard"] if "X" in lanes else 0)
    inc = R.randint(1, 12) if R.random() < hz else None
    perm = inc is not None and R.random() < P["perm"]
    halt = lambda t: inc is not None and (t in (inc, inc + 1) or (perm and t >= inc))

    cash = START - FIXED * 0.5
    cum = -FIXED * 0.5
    min_cash = cash; min_m = 0
    skus = []
    rev = [0.0] * (MONTHS + 1); prof = [0.0] * (MONTHS + 1); inv = [0.0] * (MONTHS + 1)
    first_sale = None
    breach = False
    lane_rev = {"W": [0.0] * (MONTHS + 1), "M": [0.0] * (MONTHS + 1), "S": [0.0] * (MONTHS + 1)}

    def buy(amount):
        nonlocal cash
        room = cash - FLOOR
        a = max(0.0, min(amount, room))
        cash -= a
        return a

    # ---- W の SKU 到着（プール型：12ヶ月で出る総数） ----
    if "W" in lanes:
        sd_ok = R.random() < P["sd_pass"]
        pool = lognorm(R, P["w_pool"], P["w_pool_sig"]) * (1.0 if sd_ok else 0.5) * (P["k_w"] if "K" in lanes else 1.0)
        n = int(pool) + (1 if R.random() < pool - int(pool) else 0)
        for _ in range(n):
            st = R.randint(2, 8)
            exp = lognorm(R, P["w_rev"], 0.6)
            skus.append(Sku(st, exp, exp * wm * lognorm(R, P["w_real"], 0.6),
                            max(0.03, R.gauss(P["w_m"], P["w_m_sd"])), P["w_fee"], P["w_h"], P["w_drift"], "W"))
    # ---- M の成立（送信→成立→販売開始） ----
    n_est = 0
    if "M" in lanes:
        rate = pick(R, P["m_rate"]) * P["m_gate"] * (P["k_m"] if "K" in lanes else 1.0)
        low = R.random() < P["m_low"]
        sent = 0
        for t in range(1, MONTHS + 1):
            k = P["m_send"][t - 1] * P["m_consume"] * (0.35 if low else 1.0)
            sends = int(k) + (1 if R.random() < k - int(k) else 0)
            for _ in range(sends):
                sent += 1
                q_ = P["m_q"] * (P["m_q300"] if sent > 300 else 1.0)
                if R.random() < rate * q_:
                    lag = R.triangular(R_TRI[0], R_TRI[1], R_TRI[2])
                    st = t + int(round(lag))
                    if st > MONTHS:
                        continue
                    n_est += 1
                    ks = max(1, int(round(lognorm(R, P["m_sku"], 0.45))))
                    for _ in range(ks):
                        exp = lognorm(R, P["m_rev"], 0.6)
                        skus.append(Sku(st, exp, exp * wm * lognorm(R, P["m_real"], 0.6),
                                        max(0.04, R.gauss(P["m_m"], P["m_m_sd"])), P["m_fee"], P["m_h"], P["m_drift"], "M"))
    # ---- S の設定 ----
    if "S" in lanes:
        s_ss = lognorm(R, P["s_cap"], P["s_cap_sig"]) * wm * pick(R, P["s_gate"]) / 0.25
        s_m0 = max(0.02, R.gauss(P["s_m"], P["s_m_sd"]))
        s_stock = 0.0
        s_lowm = R.randint(2, 4) if R.random() < P["s_low"] else 99   # この月から目視が続かず能力×0.3
    # ---- O の設定 ----
    oem = []
    o_costs = {}
    if "O" in lanes:
        if R.random() >= P["o_noagree"]:
            a = int(round(R.triangular(2, 8, 4)))
            listing = a + int(round(R.triangular(1.5, 4, 2.5)))
            o_costs[a] = o_costs.get(a, 0) + P["o_tm"] + P["o_gs1"] + P["o_design"]
            oem.append(dict(listing=listing, rev=lognorm(R, P["o_rev"], P["o_rev_sig"]) * wm * (0.15 if R.random() < P["o_dud"] else 1.0), stock=0.0))
            if R.random() < 0.5 and listing + 2 <= MONTHS:
                o_costs[a + 2] = o_costs.get(a + 2, 0) + P["o_design"]
                oem.append(dict(listing=listing + 2, rev=lognorm(R, P["o_rev"], P["o_rev_sig"]) * wm * (0.15 if R.random() < P["o_dud"] else 1.0), stock=0.0))
    # ---- X の設定 ----
    xs = []
    x_costs = {}
    if "X" in lanes:
        first = int(round(R.triangular(3, 6, 4)))
        x_costs[1] = P["o_tm"] + P["o_gs1"]
        t = first
        while t <= MONTHS and len(xs) < P["x_max"]:
            x_costs[t - 2 if t > 2 else 1] = x_costs.get(t - 2 if t > 2 else 1, 0) + P["x_setup"]
            reg = R.random() < P["x_reg"]
            xs.append(dict(listing=t, rev=lognorm(R, P["x_rev"], P["x_rev_sig"]) * wm * (0.15 if R.random() < P["x_dud"] else 1.0),
                           stock=0.0, reg=reg))
            t += 2 if R.random() < 0.5 else 1

    for t in range(1, MONTHS + 1):
        fixed = FIXED + (SD_FEE if ("W" in lanes and t >= 2) else 0)
        lane_fixed = 0.0
        if "K" in lanes or "S" in lanes:
            lane_fixed += P["s_cost"] if "S" in lanes else 0.0
            lane_fixed += (P["k_cost"] if "S" not in lanes else 10_000) if "K" in lanes else 0.0
        if "O" in lanes or "X" in lanes:
            lane_fixed += P["o_sprite"]
        one_off = o_costs.get(t, 0) + x_costs.get(t, 0)
        cash -= fixed + lane_fixed + one_off
        p_t = -(fixed + lane_fixed + one_off)
        r_t = 0.0
        h = halt(t)

        # --- 単品 SKU（W・M） ---
        for s in skus:
            if t < s.start or s.dead:
                continue
            age = t - s.start
            if age == 0 and s.stock == 0 and not s.hist:
                if t >= P["harvest_from"]:
                    s.dead = True; continue
                lot = s.h * s.exp * s.c
                if s.lane == "M":
                    lot = max(lot, P["m_minlot"] * 0.5)
                got = buy(lot)
                if got <= 0:
                    s.dead = True; continue
                s.stock += got
            if h:
                s.hist.append(0.0); continue
            m_now = max(0.0, s.m - s.drift * age)
            demand = s.real * (0.5 if age == 0 else 1.0)
            sale = min(demand, s.stock / s.c)
            s.stock -= sale * s.c
            cash += sale * (1 - (1 - s.c - s.m)) - 0  # 回収額 = 売上×(1−手数料率)
            cash -= sale * (s.m - m_now)             # 値下がり分
            r_t += sale; p_t += sale * m_now
            s.hist.append(sale)
            if first_sale is None and sale > 0:
                first_sale = t
            # 死に筋判定：2ヶ月経過で読みの40%未満 → 補充停止、4ヶ月目に処分（原価の70%回収）
            if age >= 2 and (sum(s.hist[-2:]) / 2) < 0.4 * s.exp:
                if age >= 4 and s.stock > 0:
                    cash += 0.7 * s.stock; p_t -= 0.3 * s.stock; s.stock = 0.0; s.dead = True
                continue
            run = (sum(s.hist[-2:]) / len(s.hist[-2:])) if age >= 1 else s.exp
            hh = s.h * (P["harvest_h"] if t >= P["harvest_from"] else 1.0)
            if s.stock < 0.5 * hh * run * s.c:
                s.stock += buy(hh * run * s.c - s.stock)

        # --- S 電脳せどり（月次バッチ） ---
        if "S" in lanes:
            idx = t - 1
            ramp = P["s_ramp"][min(idx, len(P["s_ramp"]) - 1)] * (P["s_low_f"] if t >= s_lowm else 1.0)
            ramp_next = P["s_ramp"][min(idx + 1, len(P["s_ramp"]) - 1)] * (P["s_low_f"] if t + 1 >= s_lowm else 1.0)
            m_s = max(0.0, s_m0 - P["s_drift"] * idx)
            c_s = 1 - P["s_fee"] - s_m0
            if t == 1:
                s_stock += buy(0.5 * P["s_h"] * s_ss * ramp * c_s)
            if not h:
                demand = s_ss * ramp * lognorm(R, 1.0, 0.25)
                sale = min(demand, s_stock / c_s) if c_s > 0 else 0.0
                s_stock -= sale * c_s
                cash += sale * (1 - P["s_fee"]) - sale * (s_m0 - m_s)
                wd = min(P["s_wd"] * sale, s_stock)   # 評価損は非現金。在庫簿価の範囲で落とす
                s_stock -= wd
                r_t += sale; p_t += sale * m_s - wd
                lane_rev["S"][t] += sale
                if first_sale is None and sale > 0:
                    first_sale = t
            if (perm and inc is not None and t >= inc) or t >= P["s_stop"]:
                pass
            else:
                target = P["s_h"] * s_ss * ramp_next * c_s
                if s_stock < target:
                    s_stock += buy(target - s_stock)

        # --- O 簡易OEM ---
        for o in oem:
            if t < o["listing"]:
                continue
            age = t - o["listing"]
            c_o = 1 - P["o_fee"] - P["o_m"]
            if age == 0 and o["stock"] == 0:
                o["stock"] += buy(max(P["o_lot"], P["o_h"] * o["rev"] * c_o))
            if h:
                continue
            ramp = P["o_ramp"][min(age, len(P["o_ramp"]) - 1)]
            sale = min(o["rev"] * ramp, o["stock"] / c_o)
            o["stock"] -= sale * c_o
            ads = sale * (P["o_ads_early"] if age < 3 else P["o_ads"])
            cash += sale * (1 - P["o_fee"]) - ads
            r_t += sale; p_t += sale * P["o_m"] - ads
            if first_sale is None and sale > 0:
                first_sale = t
            if o["stock"] < 0.5 * P["o_h"] * o["rev"] * ramp * c_o and sale > 0.4 * o["rev"] * ramp:
                o["stock"] += buy(P["o_h"] * o["rev"] * ramp * c_o - o["stock"])

        # --- X 中国輸入 ---
        for x in xs:
            if t < x["listing"]:
                continue
            age = t - x["listing"]
            c_x = 1 - P["x_fee"] - P["x_m"]
            if age == 0 and x["stock"] == 0:
                x["stock"] += buy(P["x_h"] * x["rev"] * c_x * 1.2)
                if x["reg"]:   # 規制・知財で販売停止 → 在庫の7割を失う
                    loss = 0.7 * x["stock"]; x["stock"] -= loss; p_t -= loss; x["rev"] = 0.0
            if h or x["rev"] <= 0:
                continue
            sale = min(x["rev"] * (0.3 if age == 0 else 0.6 if age == 1 else 1.0), x["stock"] / c_x)
            x["stock"] -= sale * c_x
            ads = sale * (P["x_ads_early"] if age < 3 else P["x_ads"])
            cash += sale * (1 - P["x_fee"]) - ads
            r_t += sale; p_t += sale * P["x_m"] - ads
            if first_sale is None and sale > 0:
                first_sale = t
            if x["stock"] < 0.4 * P["x_h"] * x["rev"] * c_x and t <= MONTHS:
                x["stock"] += buy(P["x_h"] * x["rev"] * c_x - x["stock"])

        # 恒久停止：残在庫は他販路で原価の40%回収
        if perm and inc is not None and t == inc + 2:
            pool_stock = sum(s.stock for s in skus) + (s_stock if "S" in lanes else 0) + sum(o["stock"] for o in oem) + sum(x["stock"] for x in xs)
            cash += 0.4 * pool_stock; p_t -= 0.6 * pool_stock
            for s in skus: s.stock = 0.0
            if "S" in lanes: s_stock = 0.0
            for o in oem: o["stock"] = 0.0
            for x in xs: x["stock"] = 0.0

        for s_ in skus:
            if s_.hist and t >= s_.start:
                lane_rev[s_.lane][t] += s_.hist[-1] if len(s_.hist) == t - s_.start + 1 else 0.0
        stock_total = sum(s.stock for s in skus) + (s_stock if "S" in lanes else 0) + sum(o["stock"] for o in oem) + sum(x["stock"] for x in xs)
        rev[t] = r_t; prof[t] = p_t; inv[t] = stock_total
        cum += p_t
        if cash < min_cash:
            min_cash = cash; min_m = t
        if cash < FLOOR:
            breach = True

    return dict(lane_rev=lane_rev, cum=cum, cashd=cash - START, inv=inv[MONTHS], rev12=rev[MONTHS], prof12=prof[MONTHS],
                rev=rev, prof=prof, invs=inv, min_cash=min_cash, min_m=min_m, first=first_sale,
                breach=breach, est=n_est, inc=inc is not None, perm=perm,
                sku=sum(1 for s in skus if not s.dead) + (1 if "S" in lanes else 0))


def q(xs, p):
    xs = sorted(xs); return xs[int(p * (len(xs) - 1))]


def run(lanes, P=None, n=N, seed=SEED):
    P = dict(BASE, **(P or {}))
    R = random.Random(seed)
    return [sim(lanes, R, P) for _ in range(n)]


def man(x):
    return f"{x / 10000:+.0f}万" if abs(x) >= 5000 else f"{x / 10000:+.1f}万"


def summary(name, res):
    cum = [r["cum"] for r in res]; cd = [r["cashd"] for r in res]
    p_cum = sum(c > 0 for c in cum) / len(res); p_cd = sum(c > 0 for c in cd) / len(res)
    mc = [r["min_cash"] for r in res]
    fs = [r["first"] for r in res if r["first"] is not None]
    rv = [r["rev12"] for r in res]
    liq = [r["cashd"] + 0.8 * r["inv"] for r in res]
    real = [r["cashd"] - RECV * r["rev12"] for r in res]
    return dict(name=name, p_cum=p_cum, p_cd=p_cd, p_liq=sum(x > 0 for x in liq) / len(res), liq=q(liq, .5),
                p_real=sum(x > 0 for x in real) / len(res), real=(q(real, .2), q(real, .5), q(real, .8)),
                cum=(q(cum, .2), q(cum, .5), q(cum, .8)), cd=(q(cd, .2), q(cd, .5), q(cd, .8)),
                rev=(q(rv, .2), q(rv, .5), q(rv, .8)),
                minc=(q(mc, .1), q(mc, .5)), minm=q([r["min_m"] for r in res], .5),
                first=(q(fs, .5) if fs else None), nofirst=1 - len(fs) / len(res),
                breach=sum(r["breach"] for r in res) / len(res),
                p12=sum(r["prof12"] > 0 for r in res) / len(res),
                inv=q([r["inv"] for r in res], .5))


def fmt(s):
    return (f"| {s['name']} | {s['p_cum']:.0%} | {s['p_real']:.0%}（{man(s['real'][1])}／{man(s['real'][0])}〜{man(s['real'][2])}） | {s['p_liq']:.0%}（{man(s['liq'])}） | {man(s['cum'][1])}（{man(s['cum'][0])}〜{man(s['cum'][2])}） "
            f"| {man(s['cd'][1])}（{man(s['cd'][0])}〜{man(s['cd'][2])}） | {s['rev'][1] / 1e4:.0f}万（{s['rev'][0] / 1e4:.0f}〜{s['rev'][2] / 1e4:.0f}） "
            f"| {s['minc'][1] / 1e4:.0f}万／P10 {s['minc'][0] / 1e4:.0f}万 | {s['p12']:.0%} | 月{s['first']} | {s['breach']:.0%} |")


HDR = ("| 案・レーン | P(累計損益>0) | P(実質現金>0)（中央／P20〜P80） | P(手仕舞い値>0)（中央） | 累計損益 中央（P20〜P80） | 現金ベース 中央（P20〜P80） "
       "| 月12の月商 中央（P20〜P80） | 最薄現金 中央／P10 | P(月12単月黒字) | 初回売上 中央 | 予備25万割れ |\n"
       "|---|---:|---:|---:|---|---|---|---|---:|---|---:|")


def monthly(res):
    out = ["| 月 | 月商 P20／中央／P80 | 月次損益 中央 | 累計損益 P20／中央／P80 | 手元現金 P10／中央 | 在庫（原価）中央 |", "|---|---|---|---|---|---|"]
    names = ["2026-10", "11", "12", "2027-01", "02", "03", "04", "05", "06", "07", "08", "09"]
    for t in range(1, MONTHS + 1):
        rv = [r["rev"][t] for r in res]; pf = [r["prof"][t] for r in res]
        cu = [sum(r["prof"][1:t + 1]) - FIXED * 0.5 for r in res]
        ca = [START - FIXED * 0.5 + sum(r["prof"][1:t + 1]) - r["invs"][t] for r in res]
        iv = [r["invs"][t] for r in res]
        out.append(f"| {names[t - 1]} | {q(rv, .2) / 1e4:.0f}／{q(rv, .5) / 1e4:.0f}／{q(rv, .8) / 1e4:.0f}万 | {man(q(pf, .5))} "
                   f"| {man(q(cu, .2))}／{man(q(cu, .5))}／{man(q(cu, .8))} | {q(ca, .1) / 1e4:.0f}／{q(ca, .5) / 1e4:.0f}万 | {q(iv, .5) / 1e4:.0f}万 |")
    return "\n".join(out)


def main():
    global FIXED
    lines = []
    P = lambda *a: lines.append(" ".join(str(x) for x in a))
    P("# 01_calc 出力（T-20260914-002）", f"N={N} seed={SEED}")
    P("")
    P("## 1. レーン単独と案（12ヶ月＝2026-10〜2027-09。固定費はすべてに入る。悲観=P20・楽観=P80）")
    P(HDR)
    results = {}
    for name, (lanes, ov) in LANE_SETS.items():
        res = run(lanes, ov)
        results[name] = res
        s = summary(name, res)
        s["mean"] = sum(r["cum"] for r in res) / len(res)
        P(fmt(s) + f" 期待値 {man(s['mean'])}")
    err = 0.0
    for key in ("案A：W＋M 週10通", "案C：W＋M＋S 週10通（せどり限定再開・外注）", "参考：W＋M＋O（OEMを1年目から）"):
        err = max(err, max(abs(r["cum"] - r["inv"] - r["cashd"]) for r in results[key][:300]))
    P("")
    P(f"恒等式チェック（現金−開始＝累計損益−在庫）最大誤差: {err:.0f}円")

    for key in ("案A：W＋M 週10通", "案B：W＋M 週20通", "案B＋月10から発注停止（刈り取り）", "案C：W＋M＋S 週10通（社長が目視・続かない35%込み）"):
        P("")
        P(f"## 2. 月次 — {key}（P20／中央／P80。各月独立の分位＝1本の経路ではない）")
        P(monthly(results[key]))

    sens = [
        ("メーカー成立率（混合 1.5/3/5%）", dict(m_rate=[(0.015, 1.0)]), dict(m_rate=[(0.05, 1.0)])),
        ("取り分の実現（読みの0.85倍）", dict(m_real=0.5, w_real=0.5), dict(m_real=1.2, w_real=1.2)),
        ("SKU/社（2）", dict(m_sku=1.0), dict(m_sku=3.0)),
        ("メーカー直の利益率（12%）", dict(m_m=0.08), dict(m_m=0.16)),
        ("送信の低稼働（25%）", dict(m_low=0.50), dict(m_low=0.10)),
        ("成立→初回売上の遅れ（中央1.8ヶ月）", "lag_slow", "lag_fast"),
        ("卸の母数（中央6 SKU）", dict(w_pool=2.0), dict(w_pool=15.0)),
        ("SD 審査（通過60%）", dict(sd_pass=0.0), dict(sd_pass=1.0)),
        ("アカウント事故（年5%）", dict(hazard=0.15), dict(hazard=0.02)),
    ]
    for plan_name, lanes, base_ov in (("案A", "WM", {}), ("案B", "WM", W20)):
        P("")
        P(f"## 3. 感応度 — {plan_name}（1変数ずつ。P(累計損益>0)／累計損益 中央。n=5000）")
        P("| 変数 | 悲観側 | 置き値 | 楽観側 |")
        P("|---|---|---|---|")
        b0 = summary("", run(lanes, base_ov, n=5000))
        for label, lo, hi in sens:
            outs = []
            for ov in (lo, hi):
                if ov == "lag_slow":
                    keep = R_TRI[:]; R_TRI[:] = [2.0, 4.0, 2.8]
                    o = summary("", run(lanes, base_ov, n=5000)); R_TRI[:] = keep
                elif ov == "lag_fast":
                    keep = R_TRI[:]; R_TRI[:] = [1.0, 2.0, 1.2]
                    o = summary("", run(lanes, base_ov, n=5000)); R_TRI[:] = keep
                else:
                    o = summary("", run(lanes, dict(base_ov, **ov), n=5000))
                outs.append(o)
            P(f"| {label} | {outs[0]['p_cum']:.0%}／{man(outs[0]['cum'][1])} | {b0['p_cum']:.0%}／{man(b0['cum'][1])} | {outs[1]['p_cum']:.0%}／{man(outs[1]['cum'][1])} |")

    P("")
    P("## 4. 何を変えれば確率が上がるか（案Aを基準）")
    P("| 変更 | P(累計損益>0) | 累計損益 中央（P20〜P80） | P(実質現金>0)（中央） | 最薄現金 P10 |")
    P("|---|---:|---|---:|---|")
    tries = [
        ("案A そのまま", "WM", {}),
        ("送信 週15通", "WM", dict(m_send=[10, 35] + [60] * 10, m_q=0.92, m_q300=0.75)),
        ("送信 週20通（＝案B）", "WM", W20),
        ("SD 審査が通る（確定）", "WM", dict(sd_pass=1.0)),
        ("成立率が3%以上と判明（3/5%のみ）", "WM", dict(m_rate=[(0.03, 0.64), (0.05, 0.36)])),
        ("固定費 −3,564円（Keepa API €49 → Pro €29 のみ）", "fixcut", {}),
        ("月10から在庫上限（新規ロット停止・補充1.25ヶ月分）", "WM", dict(harvest_from=10)),
        ("案B＋月10から在庫上限", "WM", dict(W20, harvest_from=10)),
        ("案B＋月11から発注停止", "WM", dict(W20, harvest_from=11, harvest_h=0.0)),
        ("案B＋月10から発注停止", "WM", dict(W20, harvest_from=10, harvest_h=0.0)),
        ("案B＋月9から発注停止", "WM", dict(W20, harvest_from=9, harvest_h=0.0)),
        ("せどりを足す（外注3万/月）", "WMS", {}),
        ("せどりを足す（社長が目視・続かない35%込み）＝案C", "WMS", dict(s_cost=0, s_low=0.35)),
        ("案C＋楽天ポイントで利益率11%", "WMS", dict(s_cost=0, s_low=0.35, s_m=0.11)),
        ("案C でゲートなし率10%（悪い側）", "WMS", dict(s_cost=0, s_low=0.35, s_gate=[(0.10, 1.0)])),
        ("案B＋せどり（社長が目視・続かない35%込み）", "WMS", dict(W20, s_cost=0, s_low=0.35)),
        ("案C 続かない70%", "WMS", dict(s_cost=0, s_low=0.70)),
        ("案C せどり利益率6%", "WMS", dict(s_cost=0, s_low=0.35, s_m=0.06)),
        ("案C せどり能力半分（定常25万）", "WMS", dict(s_cost=0, s_low=0.35, s_cap=250_000)),
        ("案C アカウント事故 せどり上乗せ年20%", "WMS", dict(s_cost=0, s_low=0.35, s_hazard=0.20)),
        ("案C 悪い側を重ねる（続かない70%・利益率6%・ゲートなし10%）", "WMS", dict(s_cost=0, s_low=0.70, s_m=0.06, s_gate=[(0.10, 1.0)])),
        ("案C＋月10から発注停止", "WMS", dict(s_cost=0, s_low=0.35, harvest_from=10, harvest_h=0.0, s_stop=10)),
        ("OEM を1年目から足す", "WMO", {}),
    ]
    for label, lanes, ov in tries:
        if lanes == "fixcut":
            keep = FIXED; FIXED = FIXED - 8_732 + 5_168
            s = summary(label, run("WM", n=8000)); FIXED = keep
        else:
            s = summary(label, run(lanes, ov, n=8000))
        P(f"| {label} | {s['p_cum']:.0%} | {man(s['cum'][1])}（{man(s['cum'][0])}〜{man(s['cum'][2])}） | {s['p_real']:.0%}（{man(s['real'][1])}） | {s['minc'][0] / 1e4:.0f}万 |")

    P("")
    P("## 6. cf_base に渡す需要パス（レーン別の月商。P20／中央／P80・万円）")
    import json
    for tag, key, lanes_ in (("B", "案B：W＋M 週20通", ("W", "M")), ("C", "案C：W＋M＋S 週10通（社長が目視・続かない35%込み）", ("W", "M", "S"))):
        res_ = results[key]
        P(f"### 案{tag}")
        for ln in lanes_:
            row = []
            for t in range(1, MONTHS + 1):
                xs_ = [r["lane_rev"][ln][t] for r in res_]
                row.append(f"{q(xs_, .2) / 1e4:.1f}/{q(xs_, .5) / 1e4:.1f}/{q(xs_, .8) / 1e4:.1f}")
            P(f"- {ln}: " + " | ".join(row))
        paths = {ln: {str(p_): [q([r["lane_rev"][ln][t] for r in res_], p_) for t in range(1, MONTHS + 1)] for p_ in (0.2, 0.5, 0.8)} for ln in lanes_}
        with open(__file__.replace("01_calc.py", f"01_demand_paths_{tag}.json"), "w") as f:
            json.dump(paths, f, ensure_ascii=False, indent=1)
    P("")
    P("## 5. 成立社数・SKU（案A／案B）")
    for key in ("案A：W＋M 週10通", "案B：W＋M 週20通"):
        res = results[key]
        e = [r["est"] for r in res]; k = [r["sku"] for r in res]
        P(f"- {key}: 成立（月11までに販売開始） 中央{q(e, .5)}（P20 {q(e, .2)}〜P80 {q(e, .8)}）・生きている SKU 中央{q(k, .5)}（P20 {q(k, .2)}〜P80 {q(k, .8)}）・P(成立≥3) {sum(x >= 3 for x in e) / len(e):.0%}")

    txt = "\n".join(lines)
    out = __file__.replace("01_calc.py", "01_calc_出力.txt")
    with open(out, "w") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
