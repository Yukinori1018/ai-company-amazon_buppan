#!/usr/bin/env python3
"""00_cf_base.py — キャッシュフローの土台（T-20260914-003 / 経理ハジメ / 2026-09-14）

案に依存しない「キャッシュの物理」。日次で計算し、月次で出力する。
- 乱数なし・決定論・標準ライブラリのみ（Python 3.9 で動作確認）
- 利益（発生主義：売れた分だけ原価になる）と現金を分けて出す。在庫は経費ではない
- 置き値の出典は 00_キャッシュフローの土台.md §7 を参照（〔実測〕〔一次〕〔二次〕〔推定〕〔仮定〕）

使い方
  python3 00_cf_base.py            # テスト2本・経路別の現金化日数・境界線グリッド・黒字倒産の例を出力
  # マサルが import して使う場合（ファイル名が数字始まりなので importlib で読む）
  import importlib.util, pathlib
  spec = importlib.util.spec_from_file_location("cf", pathlib.Path(".../00_cf_base.py"))
  cf = importlib.util.module_from_spec(spec); spec.loader.exec_module(cf)
  lane = cf.preset("卸_カード", margin=0.11, turnover_m=2)
  res = cf.simulate(cf.Config(), cf.reinvest(lane))
  cf.print_monthly(res)

用語
  P（仕入れ額）  … 1回の発注で仕入れ先に払う額（商品代＋仕入れ送料。中国輸入は関税・輸入消費税・国際送料込み）
  S（売上相当額）… P を売価に換算した額 = P ÷ 原価率
  原価率 c       … 1 − 利益率 − Amazon三層率 − 外注率 − 返品率（利益率は固定費の前・外注費込み＝前回の定義B）
"""
import datetime as dt
import math
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Tuple

D = dt.date


def add(d: D, n: int) -> D:
    return d + dt.timedelta(days=n)


def month_first(d: D) -> D:
    return D(d.year, d.month, 1)


def next_month_first(d: D) -> D:
    return D(d.year + (d.month // 12), d.month % 12 + 1, 1)


def month_last(d: D) -> D:
    return add(next_month_first(d), -1)


def nth_month_start(start: D, k: int) -> D:
    d = month_first(start)
    for _ in range(k):
        d = next_month_first(d)
    return d


def ym(d: D) -> str:
    return f"{d.year}-{d.month:02d}"


# ---------------------------------------------------------------- 支払い方法（現金が出ていく日）
def pay_date(method: str, d: D, cfg: "Config") -> D:
    """d＝請求が立つ日（発注日・出荷日・着荷日など）→ 実際に口座から現金が出る日"""
    if method == "cash":            # 前払い・銀行振込・代引き：その日に出る
        return d
    if method == "card":            # カード：月末締め・翌月 card_pay_day 日引落し〔仮定〕
        nm = next_month_first(d)
        return D(nm.year, nm.month, cfg.card_pay_day)
    if method == "kake20":          # NETSEA 掛け払い：毎月20日締め・翌月20日期限〔一次 netsea.jp/help/manual/netsea-credit_1〕
        close = D(d.year, d.month, 20) if d.day <= 20 else D(next_month_first(d).year, next_month_first(d).month, 20)
        nm = next_month_first(close)
        return D(nm.year, nm.month, 20)
    if method == "eom_next_eom":    # 月末締め・翌月末払い（メーカー直の2回目以降の一般形）〔推定〕
        return month_last(next_month_first(d))
    raise ValueError(method)


# ---------------------------------------------------------------- 経路（レーン）
PayTerm = Tuple[float, str, int, str]   # (仕入れ額に対する割合, 起点 'order'|'ship'|'arrive'|'available', 起点からの日数, 方法)


@dataclass
class Lane:
    name: str
    margin: float                 # SKU利益率（固定費の前・外注費込み・定義B）
    turnover_m: float             # 回転月数（販売開始から売り切るまでの月数。v1.3 の「消化月数」）
    lead_first: int               # 初回：発注→FBA で販売開始 までの日数
    lead_repeat: int              # 2回目以降
    pay_first: List[PayTerm]
    pay_repeat: List[PayTerm]
    fee_rate: float = 0.25        # Amazon 三層（販売手数料税込＋FBA配送代行＋保管）÷売価〔推定：単価3,000円・標準サイズ〕
    out_rate: float = 0.05        # 外注（納品代行・ラベル・FBA納品送料）÷売価〔推定〕
    ret_rate: float = 0.01        # 返品・返金の引当 ÷売価〔推定〕
    out_pay: Tuple[str, int, str] = ("arrive", 0, "cash")   # 外注費の支払い（起点・日数・方法）
    fba_leg: int = 10             # 代行着荷→FBA 販売開始（代行処理3＋輸送2＋受領5）〔推定〕
    ship_days: int = 2            # 発注→仕入れ先の出荷
    unsold: float = 0.0           # 売れ残り率（売り切り期間の末日に廃棄）
    disposal_rate: float = 0.08   # 廃棄の手数料 ÷ 売れ残りの売価相当〔推定：242.5円/点・単価3,000円〕

    @property
    def cost_rate(self) -> float:
        c = 1 - self.margin - self.fee_rate - self.out_rate - self.ret_rate
        if c <= 0.05:
            raise ValueError(f"{self.name}: 原価率 {c:.2f} が不正（利益率・手数料率の組を見直す）")
        return c


def preset(kind: str, **kw) -> Lane:
    """経路の既定値。数字の出典は md §3・§7。kw で上書き可"""
    P = {
        # 国内卸（NETSEA 等）。カード払い：請求確定は出荷確定時〔一次 NETSEA FAQ〕
        "卸_カード": dict(name="卸（カード払い）", margin=0.11, turnover_m=2, lead_first=15, lead_repeat=15,
                        pay_first=[(1.0, "ship", 0, "card")], pay_repeat=[(1.0, "ship", 0, "card")],
                        out_pay=("arrive", 0, "card")),
        "卸_掛け": dict(name="卸（NETSEA掛け払い）", margin=0.11, turnover_m=2, lead_first=15, lead_repeat=15,
                      pay_first=[(1.0, "ship", 0, "kake20")], pay_repeat=[(1.0, "ship", 0, "kake20")],
                      out_pay=("arrive", 0, "card")),
        "卸_前払い": dict(name="卸（前払い・振込）", margin=0.11, turnover_m=2, lead_first=15, lead_repeat=15,
                       pay_first=[(1.0, "order", 0, "cash")], pay_repeat=[(1.0, "order", 0, "cash")]),
        # メーカー直：初回は前払いが多い〔二次 EC STARs「リピート＝現金前払い/掛け払い」〕→2回目以降 月末締め翌月末〔推定〕
        "メーカー直": dict(name="メーカー直", margin=0.15, turnover_m=3, lead_first=20, lead_repeat=18,
                       pay_first=[(1.0, "order", 0, "cash")], pay_repeat=[(1.0, "ship", 0, "eom_next_eom")]),
        # 国内の簡易OEM：前金50%・残金は納品時〔二次 化粧品/食品OEM 各社〕。初回は製造待ち
        "OEM": dict(name="国内OEM", margin=0.30, turnover_m=3, lead_first=60, lead_repeat=30,
                    pay_first=[(0.5, "order", 0, "cash"), (0.5, "arrive", 0, "cash")],
                    pay_repeat=[(0.5, "order", 0, "cash"), (0.5, "arrive", 0, "cash")]),
        # 中国輸入（船便）：商品代＋代行手数料は前払い、国際送料・関税・輸入消費税・通関は日本着で立替精算〔二次〕
        # 免税事業者は輸入消費税を控除できない＝原価に入る
        "中国輸入": dict(name="中国輸入（船便）", margin=0.20, turnover_m=3, lead_first=35, lead_repeat=35,
                     pay_first=[(0.70, "order", 0, "cash"), (0.30, "arrive", 0, "cash")],
                     pay_repeat=[(0.70, "order", 0, "cash"), (0.30, "arrive", 0, "cash")]),
        # 電脳せどり（参考・停止中）：カードで小売から買う
        "電脳せどり": dict(name="電脳せどり（参考）", margin=0.10, turnover_m=1, lead_first=10, lead_repeat=10,
                       pay_first=[(1.0, "order", 0, "card")], pay_repeat=[(1.0, "order", 0, "card")],
                       out_pay=("arrive", 0, "card"), fba_leg=7, ship_days=1),
    }[kind]
    P = dict(P)
    P.update(kw)
    return Lane(**P)


# ---------------------------------------------------------------- 設定
@dataclass
class Config:
    start: D = D(2026, 10, 1)            # 月1 = 2026-10。12ヶ月 = 2026-10〜2027-09
    months: int = 12
    cash0: float = 2_000_000             # 運転資金〔社長確定・PDF〕
    reserve: float = 250_000             # 予備（悲観でも割らない線）〔PDF §8〕
    order_dom: int = 5                   # 毎月の発注日〔仮定〕
    settle_anchor: D = D(2026, 9, 16)    # Amazon 振込開始日〔実測：ペイメントダッシュボード 2026-09-12〕
    settle_period: int = 14              # 大口は14日ごと〔二次3系統〕
    bank_days: int = 5                   # 振込開始→口座着（3〜5営業日）〔二次〕→暦日5〔推定〕
    deliver_days: int = 2                # 販売→お届け（FBA）〔推定〕
    hold_days: int = 7                   # お届けから7日は留保〔二次2系統・公式ヘルプはログイン後で未確認〕
    card_pay_day: int = 27               # カード引落し日〔仮定：社長のカード未確認〕
    card_limit: Optional[float] = 500_000   # カード利用枠〔仮定〕。None で無制限
    fixed_monthly: List[float] = field(default_factory=lambda: [14_253] * 12)  # 段階1〔前回 03 の実測＋仮定FX〕
    oneoffs: List[Tuple[D, float, str]] = field(default_factory=list)          # (日, 金額, 名目) 一回払い
    stress_hold_until: Optional[D] = None   # 売上金留保（ポリシー）：この日までの売上の入金を +stress_hold_extra 日
    stress_hold_extra: int = 60             # 留保日から60日後に申立可〔一次 PDF 2024-10-18〕
    tax: bool = True
    income_tax_rate: float = 0.2042      # 所得税の限界税率（復興税込）〔仮定：給与の課税所得 330〜695万の帯〕
    resident_rate: float = 0.10          # 住民税〔一次〕
    blue_deduction: float = 650_000      # 青色申告特別控除（電子申告＋複式簿記）〔一次〕
    biz_tax_rate: float = 0.05           # 個人事業税（物品販売業）〔一次〕
    biz_tax_exempt: float = 2_900_000    # 事業主控除〔一次〕

    @property
    def end(self) -> D:
        return add(nth_month_start(self.start, self.months), -1)


# ---------------------------------------------------------------- 発注方針（policy）
Policy = Callable[["State", int, D], List[Tuple[Lane, float]]]


def schedule(lane: Lane, amounts: List[float]) -> Policy:
    """月別の仕入れ額を固定で与える（amounts[k] = 月k+1 の仕入れ額 P）"""
    def f(st, k, d):
        return [(lane, amounts[k])] if k < len(amounts) and amounts[k] > 0 else []
    return f


def reinvest(lane: Lane, cap: Optional[List[float]] = None, stop_after: Optional[int] = None,
             first: Optional[float] = None) -> Policy:
    """毎月、使える現金を全額仕入れに回す（安全側：確定済みの未払い・翌月固定費・予備を先に引く。入金見込みは当てにしない）
    cap: 月別の上限（需要＝取り分の上限をマサルが入れる）／stop_after: この月より後は発注しない（刈り取り）
    first: 初回の仕入れ額を固定したい場合"""
    def f(st, k, d):
        if stop_after is not None and k + 1 > stop_after:
            return []
        budget = st.cash - st.cfg.reserve - st.committed_outflows(d) - st.cfg.fixed_monthly[min(k + 1, st.cfg.months - 1)]
        c = lane.cost_rate
        P = budget / (1 + lane.out_rate / c)
        if first is not None and st.n_orders(lane) == 0:
            P = min(P, first)
        if cap is not None:
            P = min(P, cap[k])
        P = math.floor(max(P, 0) / 1000) * 1000
        return [(lane, P)] if P > 0 else []
    return f


def combine(*policies: Policy) -> Policy:
    def f(st, k, d):
        out = []
        for p in policies:
            out += p(st, k, d)
        return out
    return f


# ---------------------------------------------------------------- 状態と計算
@dataclass
class Batch:
    lane: Lane
    order: D
    P: float
    S: float
    avail: D
    days: int
    first: bool


class State:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cash = cfg.cash0
        self.flows: Dict[D, Dict[str, float]] = {}
        self.ap: List[Tuple[D, D, float]] = []     # (計上日, 支払日, 金額) 未払い（買掛・カード・残金）
        self.ar: List[Tuple[D, D, float]] = []     # (売上日, 入金日, 金額) Amazon 未入金
        self.card: List[Tuple[D, D, float]] = []   # (請求日, 引落日, 金額)
        self.batches: List[Batch] = []
        self.accr: Dict[D, Dict[str, float]] = {}  # 発生主義（売上・SKU利益・廃棄損）
        self.order_count: Dict[str, int] = {}

    def n_orders(self, lane: Lane) -> int:
        return self.order_count.get(lane.name, 0)

    def flow(self, d: D, cat: str, amt: float):
        self.flows.setdefault(d, {}).setdefault(cat, 0.0)
        self.flows[d][cat] += amt

    def accrue(self, d: D, cat: str, amt: float):
        self.accr.setdefault(d, {}).setdefault(cat, 0.0)
        self.accr[d][cat] += amt

    def committed_outflows(self, d: D) -> float:
        return sum(a for r, p, a in self.ap if p > d)

    def card_outstanding(self, d: D) -> float:
        return sum(a for c, p, a in self.card if c <= d < p)

    def settle_date(self, eligible: D) -> D:
        cfg = self.cfg
        k = max(0, math.ceil((eligible - cfg.settle_anchor).days / cfg.settle_period))
        return add(cfg.settle_anchor, k * cfg.settle_period)

    def payout_date(self, sale: D) -> D:
        cfg = self.cfg
        elig = add(sale, cfg.deliver_days + cfg.hold_days)
        bank = add(self.settle_date(elig), cfg.bank_days)
        if cfg.stress_hold_until is not None and sale <= cfg.stress_hold_until:
            bank = add(bank, cfg.stress_hold_extra)
        return bank

    def outflow(self, rec: D, when: D, method: str, amt: float, cat: str):
        """現金の出を予約。card は利用枠を超えた分を現金払いに回す"""
        if amt <= 0:
            return
        if method == "card" and self.cfg.card_limit is not None:
            room = max(0.0, self.cfg.card_limit - self.card_outstanding(when))
            if amt > room:
                self.outflow(rec, when, "cash", amt - room, cat)
                amt = room
                if amt <= 0:
                    return
        pd_ = pay_date(method, when, self.cfg)
        if method == "card":
            self.card.append((when, pd_, amt))
        self.flow(pd_, cat, -amt)
        self.ap.append((rec, pd_, amt))

    def place(self, lane: Lane, d: D, P: float):
        first = self.n_orders(lane) == 0
        self.order_count[lane.name] = self.n_orders(lane) + 1
        c = lane.cost_rate
        S = P / c
        lead = lane.lead_first if first else lane.lead_repeat
        avail = add(d, lead)
        arrive = add(d, max(lane.ship_days, lead - lane.fba_leg))
        anchors = {"order": d, "ship": add(d, lane.ship_days), "arrive": arrive, "available": avail}
        for share, anc, off, method in (lane.pay_first if first else lane.pay_repeat):
            self.outflow(d, add(anchors[anc], off), method, share * P, "仕入れ")
        anc, off, method = lane.out_pay
        self.outflow(d, add(anchors[anc], off), method, lane.out_rate * S, "外注")
        days = max(1, round(lane.turnover_m * 30.4))
        b = Batch(lane, d, P, S, avail, days, first)
        self.batches.append(b)
        sold = S * (1 - lane.unsold)
        per = sold / days
        net = 1 - lane.fee_rate - lane.ret_rate
        for i in range(days):
            sd = add(avail, i)
            pdd = self.payout_date(sd)
            self.flow(pdd, "Amazon入金", per * net)
            self.ar.append((sd, pdd, per * net))
            self.accrue(sd, "売上", per)
            self.accrue(sd, "SKU利益", per * lane.margin)
        if lane.unsold > 0:
            end = add(avail, days)
            loss_goods = (c + lane.out_rate) * S * lane.unsold
            fee = lane.disposal_rate * S * lane.unsold
            self.accrue(end, "廃棄損", -(loss_goods + fee))
            self.flow(end, "廃棄手数料", -fee)
            self.ap.append((end, end, fee))

    def inventory(self, t: D) -> float:
        v = 0.0
        for b in self.batches:
            if b.order > t:
                continue
            unit = (b.lane.cost_rate + b.lane.out_rate) * b.S
            if t < b.avail:
                v += unit
            else:
                i = (t - b.avail).days + 1
                if i >= b.days:
                    continue  # 売り切り（売れ残りは廃棄済み）
                v += unit * (1 - b.lane.unsold) * (1 - i / b.days) + unit * b.lane.unsold
        return v

    def receivable(self, t: D) -> float:
        return sum(a for s, p, a in self.ar if s <= t < p)

    def payable(self, t: D) -> float:
        return sum(a for r, p, a in self.ap if r <= t < p)


def _schedule_taxes(st: State, year: int):
    """year 年分の事業所得（発生主義）から、翌年に出ていく税を予約する。
    所得税：翌3/15（赤字なら給与と損益通算→還付 4/15〔仮定〕）／住民税：翌6・8・10・翌々1月（普通徴収）
    個人事業税：翌8・11月／予定納税：所得税額15万以上なら翌7・11月に各1/3"""
    cfg = st.cfg
    bi = 0.0
    for d, cats in st.accr.items():
        if d.year == year:
            bi += cats.get("SKU利益", 0) + cats.get("廃棄損", 0)
    for d, cats in st.flows.items():
        if d.year == year:
            bi += cats.get("固定費", 0) + cats.get("一回払い", 0)
    y = year + 1
    if bi > 0:
        taxable = max(0.0, bi - cfg.blue_deduction)
        it = taxable * cfg.income_tax_rate
        rt = taxable * cfg.resident_rate
        bt = max(0.0, bi - cfg.biz_tax_exempt) * cfg.biz_tax_rate
        st.flow(D(y, 3, 15), "税", -it)
        for dd in [D(y, 6, 30), D(y, 8, 31), D(y, 10, 31), D(y + 1, 1, 31)]:
            st.flow(dd, "税", -rt / 4)
        if bt > 0:
            st.flow(D(y, 8, 31), "税", -bt / 2)
            st.flow(D(y, 11, 30), "税", -bt / 2)
        if it >= 150_000:
            st.flow(D(y, 7, 31), "税", -it / 3)
            st.flow(D(y, 11, 30), "税", -it / 3)
    elif bi < 0:
        st.flow(D(y, 4, 15), "税", -bi * cfg.income_tax_rate)   # 還付（プラス）
    return bi


def simulate(cfg: Config, policy: Policy) -> dict:
    st = State(cfg)
    for k in range(cfg.months):
        m0 = nth_month_start(cfg.start, k)
        st.flow(m0, "固定費", -cfg.fixed_monthly[k])
    for d, a, label in cfg.oneoffs:
        st.flow(d, "一回払い", -a)
    day = cfg.start
    daily_cash = []
    taxed_years = set()
    while day <= cfg.end:
        if day.day == 1 and day.month == 1 and cfg.tax and (day.year - 1) not in taxed_years:
            _schedule_taxes(st, day.year - 1)
            taxed_years.add(day.year - 1)
        k = (day.year - cfg.start.year) * 12 + day.month - cfg.start.month
        for cat, amt in st.flows.get(day, {}).items():   # その日の入出金を反映してから予算を見る
            st.cash += amt
        if day.day == cfg.order_dom:
            for lane, P in policy(st, k, day):
                if P > 0:
                    st.place(lane, day, P)
            st.cash = _recompute_cash_to(st, day)          # 前払い（当日出金）を反映
        daily_cash.append((day, st.cash))
        day = add(day, 1)
    # 12ヶ月の外で出ていく税の見込み（2027年分を窓の末日時点で試算）
    after = {}
    if cfg.tax:
        bi_next = 0.0
        yr = cfg.end.year
        for d, cats in st.accr.items():
            if d.year == yr and d <= cfg.end:
                bi_next += cats.get("SKU利益", 0) + cats.get("廃棄損", 0)
        for d, cats in st.flows.items():
            if d.year == yr and d <= cfg.end:
                bi_next += cats.get("固定費", 0) + cats.get("一回払い", 0)
        after = dict(year=yr, biz_income_to_end=bi_next,
                     income_tax_est=max(0, bi_next - cfg.blue_deduction) * cfg.income_tax_rate,
                     resident_est=max(0, bi_next - cfg.blue_deduction) * cfg.resident_rate,
                     biz_tax_est=max(0, bi_next - cfg.biz_tax_exempt) * cfg.biz_tax_rate)
    return _report(st, daily_cash, after)


def _recompute_cash_to(st: State, day: D) -> float:
    total = st.cfg.cash0
    for d, cats in st.flows.items():
        if d <= day:
            total += sum(cats.values())
    return total


def _report(st: State, daily_cash, after) -> dict:
    cfg = st.cfg
    rows = []
    for k in range(cfg.months):
        m0 = nth_month_start(cfg.start, k)
        m1 = month_last(m0)
        cats: Dict[str, float] = {}
        acc: Dict[str, float] = {}
        d = m0
        while d <= m1:
            for c, a in st.flows.get(d, {}).items():
                cats[c] = cats.get(c, 0) + a
            for c, a in st.accr.get(d, {}).items():
                acc[c] = acc.get(c, 0) + a
            d = add(d, 1)
        cash_end = [c for dd, c in daily_cash if dd == m1][0]
        cash_min = min(c for dd, c in daily_cash if m0 <= dd <= m1)
        inv, ar, ap = st.inventory(m1), st.receivable(m1), st.payable(m1)
        profit = acc.get("SKU利益", 0) + acc.get("廃棄損", 0) + cats.get("固定費", 0) + cats.get("一回払い", 0) + cats.get("税", 0)
        ordered = sum(b.P for b in st.batches if m0 <= b.order <= m1)
        rows.append(dict(month=ym(m0), 仕入れ額=ordered, 売上=acc.get("売上", 0), Amazon入金=cats.get("Amazon入金", 0),
                         仕入れ支払=cats.get("仕入れ", 0), 外注支払=cats.get("外注", 0), 固定費=cats.get("固定費", 0),
                         一回払い=cats.get("一回払い", 0), 税=cats.get("税", 0), 廃棄=cats.get("廃棄手数料", 0),
                         利益=profit, 月末現金=cash_end, 月中最低=cash_min, 在庫=inv, 売掛=ar, 未払=ap,
                         純資産=cash_end + inv + ar - ap))
    cash_end = rows[-1]["月末現金"]
    thin = min(rows, key=lambda r: r["月中最低"])
    first_in = next((dd for dd, _ in sorted(st.flows.items()) if st.flows[dd].get("Amazon入金", 0) > 0), None)
    ap_end = rows[-1]["未払"]
    return dict(cfg=cfg, rows=rows, state=st,
                cum_cash=cash_end - ap_end - cfg.cash0,          # 12ヶ月累計キャッシュ（実質＝現金−未払）
                cum_cash_raw=cash_end - cfg.cash0,              # 口座残高だけで見た値（カードの未払を含む）
                cum_profit=sum(r["利益"] for r in rows),
                net_assets_gain=rows[-1]["純資産"] - cfg.cash0,
                thin_month=thin["month"], thin_cash=thin["月中最低"],
                month_end_min=min(r["月末現金"] for r in rows),
                first_payout=first_in, after_window_tax=after)


# ---------------------------------------------------------------- 表示
def yen(x: float) -> str:
    return f"{x/1e4:,.1f}万"


def print_monthly(res: dict, title: str = ""):
    if title:
        print(f"\n### {title}")
    cols = ["仕入れ額", "売上", "Amazon入金", "仕入れ支払", "外注支払", "固定費", "税", "利益", "月末現金", "月中最低", "在庫", "売掛", "未払", "純資産"]
    print("| 月 | " + " | ".join(cols) + " |")
    print("|---|" + "---:|" * len(cols))
    for r in res["rows"]:
        print(f"| {r['month']} | " + " | ".join(f"{r[c]/1e4:,.1f}" for c in cols) + " |")
    print(f"\n- 12ヶ月累計キャッシュ（実質＝月末現金−未払−初期200万）: {yen(res['cum_cash'])}（口座残高だけなら {yen(res['cum_cash_raw'])}）")
    print(f"- 12ヶ月累計利益（発生主義・固定費と税込み）: {yen(res['cum_profit'])}")
    print(f"- 純資産の増加（現金＋在庫＋売掛−未払 − 200万）: {yen(res['net_assets_gain'])}")
    print(f"- 最薄月（日次の最低）: {res['thin_month']} {yen(res['thin_cash'])}／月末現金の最低 {yen(res['month_end_min'])}")
    print(f"- 初回の Amazon 入金日: {res['first_payout']}")
    a = res["after_window_tax"]
    if a:
        print(f"- 窓の外で出る税の見込み（{a['year']}年分・{res['cfg'].end}までの事業所得 {yen(a['biz_income_to_end'])}）: "
              f"所得税 {yen(a['income_tax_est'])}（{a['year']+1}-03）＋住民税 {yen(a['resident_est'])}（{a['year']+1}-06〜）＋事業税 {yen(a['biz_tax_est'])}（{a['year']+1}-08〜）※限界税率を20.42%で固定＝所得が大きいと過小")


def check_identity(res: dict) -> float:
    """純資産の増加 ＝ 12ヶ月の利益（発生主義・固定費・一回払い・税込み）。ずれ（円）を返す"""
    return res["net_assets_gain"] - res["cum_profit"]


# ---------------------------------------------------------------- 1バッチの現金化日数（CCC）
def batch_ccc(lane: Lane, cfg: Optional[Config] = None, order: D = D(2026, 10, 5), first: bool = True, P: float = 100_000) -> dict:
    cfg = replace(cfg or Config(), fixed_monthly=[0] * 12, tax=False, card_limit=None, oneoffs=[])
    st = State(cfg)
    if not first:
        st.order_count[lane.name] = 1
    st.place(lane, order, P)
    outs = [(d, -c.get("仕入れ", 0) - c.get("外注", 0) - c.get("廃棄手数料", 0)) for d, c in st.flows.items()]
    ins = [(d, c.get("Amazon入金", 0)) for d, c in st.flows.items()]
    out_tot = sum(a for _, a in outs)
    in_tot = sum(a for _, a in ins)
    t_out = sum((d - order).days * a for d, a in outs) / out_tot
    t_in = sum((d - order).days * a for d, a in ins) / in_tot
    b = st.batches[0]
    sales_mid = (b.avail - order).days + b.days / 2
    cum_in, rec = 0.0, None                      # 回収＝累計入金が支払い総額に届いた日
    for d in sorted(st.flows):
        cum_in += st.flows[d].get("Amazon入金", 0)
        if rec is None and cum_in >= out_tot:
            rec = (d - order).days
    last_in = max(d for d, a in ins if a > 0)
    first_in = min(d for d, a in ins if a > 0)
    first_out = min(d for d, a in outs if a > 0)
    return dict(lane=lane.name, 支払い平均=t_out, 最初の支払い=(first_out - order).days, 販売開始=(b.avail - order).days,
                販売の平均=sales_mid, 初回入金=(first_in - order).days, 入金平均=t_in, CCC=t_in - t_out,
                回収=rec, 全額入金=(last_in - order).days, 回収倍率=in_tot / out_tot)


def payout_lag_stats(cfg: Optional[Config] = None) -> dict:
    cfg = cfg or Config()
    st = State(cfg)
    lags = []
    d = cfg.start
    while d <= cfg.end:
        lags.append((st.payout_date(d) - d).days)
        d = add(d, 1)
    lags.sort()
    n = len(lags)
    return dict(min=lags[0], p10=lags[n // 10], median=lags[n // 2], p90=lags[n * 9 // 10], max=lags[-1], mean=sum(lags) / n)


# ---------------------------------------------------------------- 境界線（毎月同額を仕入れ続けた場合）
def max_constant_purchase(lane: Lane, cfg: Config, hi: float = 3_000_000) -> float:
    """毎月同額 P を12ヶ月仕入れ続け、日次の現金が一度も予備を割らない最大の P（二分探索・1,000円単位）"""
    lo = 0.0
    for _ in range(22):
        mid = (lo + hi) / 2
        r = simulate(cfg, schedule(lane, [mid] * cfg.months))
        if r["thin_cash"] >= cfg.reserve:
            lo = mid
        else:
            hi = mid
    return math.floor(lo / 1000) * 1000


def boundary_grid(kind: str, margins, turns, cfg: Optional[Config] = None, P: Optional[float] = None) -> List[dict]:
    cfg = cfg or Config()
    out = []
    for N in turns:
        for m in margins:
            lane = preset(kind, margin=m, turnover_m=N)
            p = P if P is not None else max_constant_purchase(lane, cfg)
            r = simulate(cfg, schedule(lane, [p] * cfg.months))
            out.append(dict(kind=kind, N=N, m=m, P=p, cum_cash=r["cum_cash"], net=r["net_assets_gain"], thin=r["thin_cash"]))
    return out


def breakeven_margin(kind: str, N: float, cfg: Optional[Config] = None, P: Optional[float] = None,
                     lo: float = 0.02, hi: float = 0.45, iters: int = 9) -> Tuple[Optional[float], float]:
    """12ヶ月累計キャッシュ（実質）が0を超える最小の利益率（二分探索・精度0.1pt）。
    P=None なら「予備を割らない最大の月額」を毎回取り直す（資金律速）。P を与えれば需要律速の月額。
    戻り値: (境界利益率 or None, 境界での最薄の現金)"""
    cfg = cfg or Config()

    def run(m):
        lane = preset(kind, margin=m, turnover_m=N)
        p = P if P is not None else max_constant_purchase(lane, cfg)
        return simulate(cfg, schedule(lane, [p] * cfg.months))

    rh = run(hi)
    if rh["cum_cash"] <= 0:
        return None, rh["thin_cash"]
    rl = run(lo)
    if rl["cum_cash"] > 0:
        return lo, rl["thin_cash"]
    for _ in range(iters):
        mid = (lo + hi) / 2
        r = run(mid)
        if r["cum_cash"] > 0:
            hi, rh = mid, r
        else:
            lo = mid
    return hi, rh["thin_cash"]


# ---------------------------------------------------------------- 実行
def main(quick: bool = False):
    cfg = Config()
    print("# 00_cf_base.py 出力（決定論・乱数なし）")
    print(f"窓: {cfg.start}〜{cfg.end}（12ヶ月）／初期現金 {yen(cfg.cash0)}／予備 {yen(cfg.reserve)}／固定費 段階1 {cfg.fixed_monthly[0]:,}円/月")

    print("\n## 1. Amazon の売上日→口座着の日数（2026-10〜2027-09 の毎日の売上で計測）")
    s = payout_lag_stats(cfg)
    print(f"最短 {s['min']}日／10% {s['p10']}日／中央 {s['median']}日／90% {s['p90']}日／最長 {s['max']}日／平均 {s['mean']:.1f}日")

    print("\n## 2. 経路別の現金化日数（1回の発注 10万円・発注日 2026-10-05 起点・日数）")
    kinds = ["卸_カード", "卸_掛け", "卸_前払い", "メーカー直", "OEM", "中国輸入", "電脳せどり"]
    print("| 経路 | 利益率 | 回転月数 | 最初の支払い | 支払い平均 | 販売開始 | 初回入金 | 入金平均 | CCC（入金平均−支払い平均） | 回収（累計±0） | 全額入金 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k in kinds:
        for first in ([True, False] if k in ("メーカー直", "OEM") else [True]):
            ln = preset(k)
            b = batch_ccc(ln, cfg, first=first)
            tag = ln.name + ("（初回）" if first and k in ("メーカー直", "OEM") else ("（2回目以降）" if not first else ""))
            print(f"| {tag} | {ln.margin:.0%} | {ln.turnover_m} | {b['最初の支払い']} | {b['支払い平均']:.0f} | {b['販売開始']} | {b['初回入金']} | "
                  f"{b['入金平均']:.0f} | {b['CCC']:.0f} | {b['回収']} | {b['全額入金']} |")
    print("\nリードタイムの幅（悲観＝繁忙期・受領遅延）での CCC")
    for k, lo, hi in [("卸_カード", 10, 28), ("卸_前払い", 10, 28), ("メーカー直", 12, 35), ("OEM", 30, 90), ("中国輸入", 20, 60), ("電脳せどり", 7, 14)]:
        vals = []
        for L in (lo, preset(k).lead_first, hi):
            vals.append(batch_ccc(preset(k, lead_first=L, lead_repeat=L), cfg)["CCC"])
        print(f"- {preset(k).name}: リード {lo}/{preset(k).lead_first}/{hi}日 → CCC {vals[0]:.0f}/{vals[1]:.0f}/{vals[2]:.0f}日")
    print("回転月数の効果: 回転が1ヶ月延びるごとに CCC は +15日（販売の平均が 30.4÷2 日後ろへ）")

    print("\n## 3. テストケース")
    t1 = simulate(cfg, reinvest(preset("卸_カード", margin=0.11, turnover_m=2)))
    print_monthly(t1, "テスト1：卸（カード払い）利益率11%・回転2ヶ月・毎月全額再投資")
    print(f"- 検算（純資産の増加 − 累計利益）: {check_identity(t1):,.0f}円")
    t1h = simulate(cfg, reinvest(preset("卸_カード", margin=0.11, turnover_m=2), stop_after=9))
    print(f"- 変種 刈り取り（2027-07以降は発注しない）: 12ヶ月累計キャッシュ {yen(t1h['cum_cash'])}／純資産の増加 {yen(t1h['net_assets_gain'])}／最薄 {t1h['thin_month']} {yen(t1h['thin_cash'])}")
    cfg_s = replace(cfg, stress_hold_until=D(2026, 12, 31))
    t1s = simulate(cfg_s, reinvest(preset("卸_カード", margin=0.11, turnover_m=2)))
    print(f"- 変種 売上金留保（2026年中の売上の入金が60日遅れる）: 12ヶ月累計キャッシュ {yen(t1s['cum_cash'])}／最薄 {t1s['thin_month']} {yen(t1s['thin_cash'])}")
    t1p = simulate(cfg, reinvest(preset("卸_前払い", margin=0.11, turnover_m=2)))
    print(f"- 変種 前払い（カードの猶予なし）: 12ヶ月累計キャッシュ {yen(t1p['cum_cash'])}／純資産の増加 {yen(t1p['net_assets_gain'])}")

    cfg2 = replace(cfg, oneoffs=[(D(2026, 10, 5), 17_050, "GS1 事業者コード（年）")])
    t2 = simulate(cfg2, reinvest(preset("OEM", margin=0.30, turnover_m=3, lead_first=60, lead_repeat=30)))
    print_monthly(t2, "テスト2：国内OEM 利益率30%・初回リードタイム60日（2回目30日）・前金50%/残金納品時・回転3ヶ月・毎月全額再投資")
    print(f"- 検算（純資産の増加 − 累計利益）: {check_identity(t2):,.0f}円")
    t2h = simulate(cfg2, reinvest(preset("OEM", margin=0.30, turnover_m=3, lead_first=60, lead_repeat=30), stop_after=7))
    print(f"- 変種 刈り取り（2027-05以降は発注しない）: 12ヶ月累計キャッシュ {yen(t2h['cum_cash'])}／純資産の増加 {yen(t2h['net_assets_gain'])}／最薄 {t2h['thin_month']} {yen(t2h['thin_cash'])}")
    t2c = simulate(cfg2, reinvest(preset("OEM", margin=0.30, turnover_m=3, lead_first=60, lead_repeat=30), cap=[600_000] + [150_000] * 11))
    print(f"- 変種 需要上限（初回60万・以降15万/月）: 12ヶ月累計キャッシュ {yen(t2c['cum_cash'])}／純資産の増加 {yen(t2c['net_assets_gain'])}／最薄 {t2c['thin_month']} {yen(t2c['thin_cash'])}")

    if quick:
        return
    print("\n## 4. 境界線：毎月同額を12ヶ月仕入れ続けたときの12ヶ月累計キャッシュ（万円）")
    print("P＝予備25万を一度も割らない最大の月額（カード枠50万）。セル＝12ヶ月累計キャッシュ／括弧＝純資産の増加")
    margins = [0.05, 0.08, 0.11, 0.15, 0.20, 0.25, 0.30]
    turns = [0.5, 1, 2, 3, 4, 6]
    for kind in ["卸_カード", "卸_前払い", "メーカー直", "中国輸入", "OEM"]:
        g = boundary_grid(kind, margins, turns, cfg)
        print(f"\n#### {preset(kind).name}")
        print("| 回転月数＼利益率 | " + " | ".join(f"{m:.0%}" for m in margins) + " | 境界（累計キャッシュ>0 の最小利益率） |")
        print("|---|" + "---:|" * (len(margins) + 1))
        for N in turns:
            cells = [x for x in g if x["N"] == N]
            b = next((f"{x['m']:.0%}" for x in cells if x["cum_cash"] > 0), "30%超")
            print(f"| {N} | " + " | ".join(f"{x['cum_cash']/1e4:+.0f}（{x['net']/1e4:+.0f}）" for x in cells) + f" | {b} |")
        pm = [x["P"] for x in g if x["N"] == 2 and x["m"] == 0.11]
        if pm:
            print(f"（参考：回転2・利益率11%の P = {pm[0]/1e4:.1f}万/月）")

    print("\n## 5. 12ヶ月累計キャッシュ>0 の損益分岐利益率（毎月同額を12ヶ月仕入れ続ける・精度0.1pt）")
    print("資金律速＝予備25万を割らない最大の月額／需要律速＝月50万・月20万を仕入れる（※＝その月額では予備を割る）")
    print("| 経路 | 回転月数 | 資金律速 | 仕入れ月50万 | 仕入れ月20万 |")
    print("|---|---:|---:|---:|---:|")
    for kind in ["卸_カード", "卸_前払い", "メーカー直", "中国輸入", "OEM"]:
        for N in [0.5, 1, 2, 3, 4, 6]:
            cells = []
            for P in (None, 500_000, 200_000):
                m, thin = breakeven_margin(kind, N, cfg, P)
                cells.append(("45%超" if m is None else f"{m:.1%}") + ("※" if thin < cfg.reserve else ""))
            print(f"| {preset(kind).name} | {N} | " + " | ".join(cells) + " |")

    print("\n## 6. 黒字倒産の筋：仕入れを毎月25%ずつ増やす（10万→）")
    grow = [100_000 * 1.25 ** k for k in range(12)]
    print("| 経路 | 回転月数 | 12ヶ月累計利益 | 12ヶ月累計キャッシュ | 最薄月 | 最薄の現金 | 予備割れ |")
    print("|---|---:|---:|---:|---|---:|---|")
    for kind in ["卸_カード", "卸_前払い"]:
        for N in [1, 2, 4]:
            r = simulate(cfg, schedule(preset(kind, margin=0.11, turnover_m=N), grow))
            print(f"| {preset(kind).name} 11% | {N} | {yen(r['cum_profit'])} | {yen(r['cum_cash'])} | {r['thin_month']} | {yen(r['thin_cash'])} | {'割る' if r['thin_cash'] < cfg.reserve else '割らない'} |")
    print(f"（仕入れ額の合計 {sum(grow)/1e4:,.0f}万・12月目 {grow[-1]/1e4:,.0f}万/月）")


if __name__ == "__main__":
    import sys
    main(quick="--quick" in sys.argv)
