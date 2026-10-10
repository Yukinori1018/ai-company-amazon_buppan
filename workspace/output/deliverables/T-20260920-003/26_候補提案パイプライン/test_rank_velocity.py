"""rank_velocity / hidden_cart / screen_checks（2026-10-11 追加分）のテスト。
python3 test_rank_velocity.py"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import hidden_cart as HC
import rank_velocity as R
import screen_checks as SC

NOW = 1791670000                       # 2026-10-11 頃（Unix 秒）
NOW_K = NOW // 60 - R.KEEPA_T0
CALIB_POINTS = R.REPO / "workspace/output/agent_output/T-20260920-003/ledger20261010/keizon_rank_calib_20261011.csv"


def test_crossing_ranks_monotone():
    # ランク 10^k の商品は月販 10^(4-k)（理想的な直線）。打ち切り（50未満=0）を入れる
    pairs = []
    for i in range(2000):
        r = 10 ** (1 + 4 * i / 2000)
        m = 10 ** (4.5 - math.log10(r))
        pairs.append((r, int(m) if m >= 50 else 0))
    pts = R.crossing_ranks(pairs)
    assert pts and pts[0][1] == 50
    assert all(a[0] > b[0] for a, b in zip(pts, pts[1:])), pts   # T が大きいほど浅いランク
    # 月50個の境目は 10^(4.5-log10 50) ≈ 632位 付近（刻み 0.125 桁の誤差内）
    assert 400 < pts[0][0] < 1000, pts


def test_velocity_takes_min_of_rank_and_drops():
    # 90日間ずっと 10万位・30日に4回の改善（観測30回）
    hist = []
    t0 = NOW_K - 100 * 1440
    for k in range(120):
        t = t0 + k * 1440
        hist += [t, 100_000 if k % 7 else 90_000]
    p = {"csv": [None, None, None, hist], "rootCategory": 3828871,
         "stats": {"salesRankDrops30": 4, "salesRankDrops90": 12}}
    v = R.velocity(p, NOW)
    assert v.rank90 == 100_000
    rank_est = R.rank_to_monthly(100_000, 3828871)[0]
    assert v.est == math.floor(min(rank_est, 4)), (v.est, rank_est)
    assert "小さい方" in v.text()


def test_family_flag():
    p = {"csv": [None, None, None, [NOW_K - 1000, 5000]], "parentAsin": "B0PARENT",
         "rootCategory": 3828871, "stats": {"salesRankDrops30": 20}}
    v = R.velocity(p, NOW)
    assert v.family and "共有" in v.text()


def test_no_history():
    v = R.velocity({"csv": [], "stats": {}}, NOW)
    assert v.est is None and "推定できない" in v.text()


def test_beta_matches_keizon_calibration():
    """β=-1.19 はキーゾン実数で決めた。点のファイルがあれば再計算して一致を見る（無ければ飛ばす）。"""
    if not CALIB_POINTS.exists():
        print("  （較正点ファイルなし・スキップ）")
        return
    pts = [(float(r["rank90"]), float(r["keizon"]), int(r["root"]))
           for r in csv.DictReader(CALIB_POINTS.open(encoding="utf-8-sig"))]
    b = R.fit_beta(pts)
    assert abs(b - R.BETA) < 0.02, b


def test_past_buybox_uses_last_cart_period():
    # 200日前〜60日前は 3,000円でカートあり、その後カート消失（-1）
    h = [NOW_K - 200 * 1440, 3000, 0, NOW_K - 60 * 1440, -1, 0]
    p = {"csv": [None] * 18 + [h]}
    pb = HC.past_buybox(p, NOW)
    assert pb and pb.median == 3000 and 55 <= pb.gap_days <= 62, pb
    assert HC.past_buybox({"csv": [None] * 18 + [[NOW_K - 100, -1, 0]]}, NOW) is None


def test_supplement_holder_amazon_fails():
    c = SC.Cart("", "225", "200+", "2026-10-11 05:00", has_cart=True)
    c2 = SC.supplement_holder(c, SC.AMAZON_JP, None)
    assert SC.cart_gate(c2)[0] == "FAIL"


def test_supplement_holder_maker_suspect():
    c = SC.Cart("", "1595", "", "t", has_cart=True)
    c2 = SC.supplement_holder(c, "AXXXX", "ハナリラ公式ストア", brand="ハナリラ")
    st, why = SC.cart_gate(c2)
    assert st == "UNKNOWN" and "疑い" in why
    c3 = SC.supplement_holder(c, "AYYYY", "ジャポニ屋", brand="サクラクレパス")
    assert SC.cart_gate(c3)[0] == "PASS"


def test_blank_holder_with_cart_is_not_cartless():
    c = SC.Cart("", "2630", "", "t", has_cart=True)
    st, why = SC.cart_gate(c)
    assert st == "UNKNOWN" and "保持者名は未取得" in why and "カートなし" not in why


def test_screen_label_counts_as_sales():
    sc = SC.ScreenChecks({"A": SC.Cart("x", "1", "100+", "t", has_cart=True)}, {}, {})
    st, why, m = SC.sales("A", {"monthlySold": None}, "UNKNOWN", sc)
    assert st == "PASS" and m == 100
    sc2 = SC.ScreenChecks({"A": SC.Cart("x", "1", "", "t", has_cart=True)}, {}, {})
    assert SC.sales("A", {"monthlySold": None}, "UNKNOWN", sc2)[0] == "UNKNOWN"


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            n += 1
            print("ok", k)
    print(f"{n} 件通過")
