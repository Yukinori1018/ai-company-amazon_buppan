"""2026-10-11 追加分のテスト：カートの保持者補完（Keepa）・実画面の月販表示・キーゾン再現値・
カートなし棚の基準売価。  python3 test_cart_kz_20261011.py"""
from __future__ import annotations

import hidden_cart as HC
import screen_checks as SC

NOW = 1791670000
NOW_K = NOW // 60 - HC.KEEPA_T0


def test_past_buybox_uses_last_cart_period():
    # 200日前〜60日前は 3,000円でカートあり、その後カート消失（-1）
    h = [NOW_K - 200 * 1440, 3000, 0, NOW_K - 60 * 1440, -1, 0]
    pb = HC.past_buybox({"csv": [None] * 18 + [h]}, NOW)
    assert pb and pb.median == 3000 and 55 <= pb.gap_days <= 62, pb
    assert HC.past_buybox({"csv": [None] * 18 + [[NOW_K - 100, -1, 0]]}, NOW) is None


def test_supplement_holder_amazon_fails():
    c = SC.Cart("", "225", "200+", "2026-10-11 05:00", has_cart=True)
    assert SC.cart_gate(SC.supplement_holder(c, SC.AMAZON_JP, None))[0] == "FAIL"


def test_supplement_holder_maker_suspect():
    c = SC.Cart("", "1595", "", "t", has_cart=True)
    st, why = SC.cart_gate(SC.supplement_holder(c, "AXXXX", "ハナリラ公式ストア", brand="ハナリラ"))
    assert st == "UNKNOWN" and "疑い" in why
    assert SC.cart_gate(SC.supplement_holder(c, "AYYYY", "ジャポニ屋", brand="サクラクレパス"))[0] == "PASS"


def test_blank_holder_with_cart_is_not_cartless():
    st, why = SC.cart_gate(SC.Cart("", "2630", "", "t", has_cart=True))
    assert st == "UNKNOWN" and "保持者名は未取得" in why and "カートなし" not in why


def test_screen_label_counts_as_sales():
    sc = SC.ScreenChecks({"A": SC.Cart("x", "1", "100+", "t", has_cart=True)}, {}, {})
    st, why, m = SC.sales("A", {"monthlySold": None}, "UNKNOWN", sc)
    assert st == "PASS" and m == 100
    sc2 = SC.ScreenChecks({"A": SC.Cart("x", "1", "", "t", has_cart=True)}, {}, {})
    assert SC.sales("A", {"monthlySold": None}, "UNKNOWN", sc2)[0] == "UNKNOWN"


def test_kz_estimate_is_keizon_equivalent_but_not_human():
    kz = SC.Keizon("4/3/5（平均4.0個）", 4.0, ["4", "3", "5"], "Keepa ランク改善3%超で再現（キーゾン同等・§3.3-16）")
    sc = SC.ScreenChecks({}, {}, {"A": kz})
    assert SC.sales("A", {}, "UNKNOWN", sc)[0] == "PASS"
    assert not sc.covers("A") and sc.has_any("A")          # 人の行の凍結は解かない
    low = SC.Keizon("0/0/0（平均0.0個）", 0.0, ["0", "0", "0"], "Keepa …・注意：観測少(3/2/4)")
    assert SC.sales("B", {}, "UNKNOWN", SC.ScreenChecks({}, {}, {"B": low}))[0] == "UNKNOWN"


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            n += 1
            print("ok", k)
    print(f"{n} 件通過")
