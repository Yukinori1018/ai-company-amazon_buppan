"""売れ筋ランク → 推定月販（Keepa）。キーゾンが使えない行の実売 UNKNOWN を「推定」で解く。

2026-10-11 タカシ（T-20260920-003）。社長指示「UNKNOWN が多すぎ。確認する方法を考えて実行しろ」。

🔴 これは推定であり、§3.3-16 により推定だけでは GO にしない。台帳では「GO(テスト)」として
   別記し、社長が「推定で最小ロットのテスト仕入れを許すか」を決める材料にする。

換算のしかた（当社の手元データで較正。外部の換算表は使わない）
-----------------------------------------------------------
① 錨（月50個のランク r50）：Keepa キャッシュ 64,923 ASIN（sd_queue_big/best.pkl）の
   90日平均ランク（stats.avg90[3]）× monthlySold（Amazon「過去1か月で◯点以上購入」・ASIN 単位・
   50未満は表示されない）。ルートカテゴリごとに「monthlySold≥50 が半数を超える最も深いランク」
   を r50 とする（ここは正解ラベルがある領域）。
② 傾き β：月50個未満には Keepa の正解ラベルが無い。そこで**カズヨがキーゾンで見た ASIN 単位の
   3か月実数（16件・シート「実売とゲート_20261005」）**で傾きを決めた：
       推定月販 = 50 × (ランク / r50) ^ β     β = −1.19（錨を通る最小二乗・2026-10-11）
   最初に「monthlySold の境目だけで直線を引く」方式を試したが、キーゾン実数に対し
   2〜40倍の過大推定になった（ランクの測定時期のずれで傾きが寝る）ので捨てた。
③ ドロップ30日：低販売域（月10個前後以下）では1回の販売が1回のランク改善になるので、
   キーゾン実数とほぼ一致した（蛍光灯 9/7/8/8 回 vs 実数 11/10/8/7 個）。
   **推定月販は ②と③の小さい方**（2根拠の安全側）。

ドロップ数（ランク改善の回数）は販売数ではなく観測回数を測っている（memory:
knowledge_keepa_dropcount_is_polling・相関0.991）。**大きさは読まない**。
「30日の観測 20回以上なのにドロップ 10回未満＝売れていない」の足切りにだけ使う
（knowledge_drop_count_floor_needs_observation_gate）。

バリエーションの子は、ランクが family 共有（兄弟の売上で動く）。推定月販は family 合計の
推定になり、その ASIN の値ではない → 「ランク共有」と明記し、GO(テスト) に入れない。
"""
from __future__ import annotations

import math
import pickle
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CALIB = REPO / "workspace/output/agent_output/T-20260920-003/sd_queue_big/best.pkl"
THRESHOLDS = (50, 100, 200, 400, 1000)
BIN = 0.125            # log10 ランクの刻み（1桁を8つ）
MIN_BIN_N = 15         # これ未満の刻みは判定に使わない
MIN_CAT_N = 800        # カテゴリ単独で較正する最低件数。未満は全カテゴリ共通の式
KEEPA_T0 = 21564000    # Keepa 分 → Unix 分のずれ


@dataclass(frozen=True)
class Fit:
    a: float
    b: float
    points: tuple          # ((r_T, T), ...)
    n: int
    scope: str             # "カテゴリ別" / "全カテゴリ共通"

    def monthly(self, rank: float) -> float:
        return 10 ** (self.a + self.b * math.log10(rank))

    def text(self) -> str:
        return (f"log10(月販)={self.a:.2f}{self.b:+.2f}·log10(ランク)"
                f"（{self.scope}・n={self.n}・境目 "
                + "・".join(f"月{t}個≈{int(r):,}位" for r, t in self.points) + "）")


def crossing_ranks(pairs: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """[(ランク, monthlySold or 0)] → [(r_T, T)]。中央値が T を割る最も深いランク。"""
    bins: dict[int, list[int]] = defaultdict(list)
    for r, m in pairs:
        bins[int(math.floor(math.log10(r) / BIN))].append(m)
    keys = sorted(k for k in bins if len(bins[k]) >= MIN_BIN_N)
    out = []
    for t in THRESHOLDS:
        last_ok = None
        for k in keys:
            frac = sum(1 for m in bins[k] if m >= t) / len(bins[k])
            if frac >= 0.5:
                last_ok = k
            elif last_ok is not None:
                break           # 上位から見て初めて半数を割った刻みで止める
        if last_ok is not None:
            out.append((10 ** ((last_ok + 1) * BIN), t))   # 刻みの深い側の端
    # 単調でない点（深いランクほど T が大きい）は捨てる
    clean = []
    for r, t in sorted(out, key=lambda x: x[1]):
        if not clean or r < clean[-1][0]:
            clean.append((r, t))
    return clean


def fit_line(points: list[tuple[float, int]]) -> tuple[float, float] | None:
    if len(points) < 2:
        return None
    xs = [math.log10(r) for r, _ in points]
    ys = [math.log10(t) for _, t in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if b >= 0:
        return None
    return my - b * mx, b


BETA = -1.19   # キーゾン実数16件で較正（上の②）。test_rank_velocity.py で再計算して一致を確認


@lru_cache(maxsize=1)
def anchors() -> tuple[dict[int, float], float, int]:
    """({ルートカテゴリ: r50}, 全カテゴリ共通の r50, 較正件数)。"""
    d = pickle.load(CALIB.open("rb"))
    by_cat: dict[int, list] = defaultdict(list)
    allp = []
    for v in d.values():
        a = v.get("avg90")
        r = a[3] if a and len(a) > 3 else None
        if not r or r <= 0 or not v.get("root"):
            continue
        p = (r, v.get("ms") or 0)
        by_cat[v["root"]].append(p)
        allp.append(p)
    out = {}
    for cat, ps in by_cat.items():
        if len(ps) < MIN_CAT_N:
            continue
        x = [r for r, t in crossing_ranks(ps) if t == 50]
        if x:
            out[cat] = x[0]
    common = [r for r, t in crossing_ranks(allp) if t == 50][0]
    return out, common, len(allp)


def rank_to_monthly(rank: float, root: int | None) -> tuple[float, float, str]:
    """(推定月販, 使った r50, 説明)。"""
    cats, common, n = anchors()
    r50 = cats.get(root, common)
    scope = "カテゴリ別" if root in cats else "全カテゴリ共通"
    return 50 * (rank / r50) ** BETA, r50, f"r50={int(r50):,}位（{scope}・n={n:,}）・β={BETA}"


def calibrate() -> tuple[dict[int, Fit], Fit]:  # 旧方式（不採用・検証用に残す）
    d = pickle.load(CALIB.open("rb"))
    by_cat: dict[int, list] = defaultdict(list)
    allp = []
    for v in d.values():
        a = v.get("avg90")
        r = a[3] if a and len(a) > 3 else None
        if not r or r <= 0 or not v.get("root"):
            continue
        p = (r, v.get("ms") or 0)
        by_cat[v["root"]].append(p)
        allp.append(p)
    pts = crossing_ranks(allp)
    ab = fit_line(pts)
    common = Fit(ab[0], ab[1], tuple(pts), len(allp), "全カテゴリ共通")
    fits = {}
    for cat, ps in by_cat.items():
        if len(ps) < MIN_CAT_N:
            continue
        cp = crossing_ranks(ps)
        ab = fit_line(cp)
        if ab and -3 < ab[1] < -0.3:
            fits[cat] = Fit(ab[0], ab[1], tuple(cp), len(ps), "カテゴリ別")
    return fits, common


def fit_for(root: int | None) -> Fit:
    fits, common = calibrate()
    return fits.get(root, common)


# ── 1商品のランク履歴から ───────────────────────────────────────────────

def series(csv_hist: list | None, now_min: int, days: int) -> list[tuple[int, int]]:
    """Keepa の [t, v, t, v, ...] から直近 days 日の (Keepa分, 値>0) を返す。"""
    if not csv_hist:
        return []
    lo = now_min - days * 1440
    out = []
    for i in range(0, len(csv_hist) - 1, 2):
        t, v = csv_hist[i], csv_hist[i + 1]
        if t >= lo and v and v > 0:
            out.append((t, v))
    return out


def time_weighted_median(csv_hist: list | None, now_min: int, days: int) -> float | None:
    """直近 days 日の時間加重中央値（観測の多い時期に引っ張られないように）。"""
    if not csv_hist:
        return None
    lo = now_min - days * 1440
    pts = [(csv_hist[i], csv_hist[i + 1]) for i in range(0, len(csv_hist) - 1, 2)]
    segs = []
    for j, (t, v) in enumerate(pts):
        t1 = pts[j + 1][0] if j + 1 < len(pts) else now_min
        s, e = max(t, lo), min(t1, now_min)
        if e > s and v and v > 0:
            segs.append((v, e - s))
    if not segs:
        return None
    segs.sort()
    half = sum(w for _, w in segs) / 2
    acc = 0
    for v, w in segs:
        acc += w
        if acc >= half:
            return float(v)
    return float(segs[-1][0])


@dataclass
class Velocity:
    rank90: float | None       # 90日の時間加重中央値ランク（ルートカテゴリ）
    est: float | None          # 推定月販（family 共有なら family 合計の推定）
    drops30: int | None
    obs30: int
    drops90: int | None
    family: bool
    fit: str | None            # 換算式の説明
    dead: bool                 # 観測20回以上なのにドロップ3回未満＝月3個に届かない兆候
    rank_est: float | None = None

    def text(self) -> str:
        if self.est is None:
            return "推定月販(Keepa)：推定できない"
        s = (f"推定月販(Keepa) {int(self.est)}個/月＝小さい方〔ランク換算 "
             f"{self.rank_est:.0f}個（90日中央 {int(self.rank90):,}位・{self.fit}）／"
             f"ドロップ30日 {self.drops30}回（観測 {self.obs30}回）〕")
        if self.obs30 < 20:
            s += "・観測20回未満でドロップは少なめに出る"
        if self.family:
            s += "・🔴バリエーションの子＝ランクは兄弟と共有（この数は family 合計の推定）"
        return s


def velocity(p: dict, now_unix: int) -> Velocity:
    """Keepa product（history=1）から推定月販を出す。"""
    now_min = now_unix // 60 - KEEPA_T0
    c = p.get("csv") or []
    rank_hist = c[3] if len(c) > 3 else None
    r90 = time_weighted_median(rank_hist, now_min, 90)
    st = p.get("stats") or {}
    obs30 = len(series(rank_hist, now_min, 30))
    d30 = st.get("salesRankDrops30")
    d90 = st.get("salesRankDrops90")
    fam = bool(p.get("parentAsin")) or bool(p.get("variations"))
    rank_est = note = None
    if r90:
        rank_est, _, note = rank_to_monthly(r90, p.get("rootCategory"))
    ests = [x for x in (rank_est, d30 if (d30 is not None and d30 >= 0) else None) if x is not None]
    est = math.floor(min(ests)) if ests else None
    dead = obs30 >= 20 and d30 is not None and 0 <= d30 < 3
    return Velocity(r90, est, d30, obs30, d90, fam, note, dead, rank_est)


def fit_beta(points: list[tuple[float, float, int | None]]) -> float:
    """[(90日中央ランク, キーゾン月販, ルートカテゴリ)] → 錨 r50 を通る最小二乗の傾き β。"""
    cats, common, _ = anchors()
    xs, ys = [], []
    for r, m, root in points:
        if not (r and m and m > 0):
            continue
        xs.append(math.log10(r / cats.get(root, common)))
        ys.append(math.log10(m / 50))
    return sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)


def median_or_none(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None
