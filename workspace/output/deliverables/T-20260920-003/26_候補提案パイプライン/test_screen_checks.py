"""screen_checks の判定（§3.3-1/5・§3.5 #9/#10）。python3 test_screen_checks.py"""
import screen_checks as SC
from screen_checks import Cart, Keizon, ScreenChecks

SC._OFFERS = {"A1": (0, 1, "t"), "A2": (1, 2, "t"), "A3": (0, 0, "t")}


def t_cart():
    assert SC.cart_gate(Cart("Amazon.co.jp", "1", "", "x"))[0] == "FAIL"
    assert SC.cart_gate(Cart("某社", "1", "", "x", "確定", "本人"))[0] == "FAIL"
    assert SC.cart_gate(Cart("某社", "1", "", "x", "疑い", "?"))[0] == "UNKNOWN"
    assert SC.cart_gate(Cart("高値で非表示", "", "", "x"))[0] == "UNKNOWN"
    assert SC.cart_gate(Cart("カートなし", "", "", "x"))[0] == "UNKNOWN"
    assert SC.cart_gate(Cart("スター☆彡", "9130", "", "x"))[0] == "PASS"


def t_sales():
    sc = ScreenChecks({"A1": Cart("x", "1", "100+", "t")},
                      {}, {"K": Keizon("9/13/12", 11, ["9", "13", "12"]), "Z": Keizon("表示なし", None)})
    assert SC.sales("K", {}, "UNKNOWN", sc)[0] == "PASS"          # キーゾンが最優先
    assert SC.sales("Z", {"monthlySold": 100}, "PASS", sc)[0] == "UNKNOWN"
    assert SC.sales("A1", {"monthlySold": 100}, "PASS", sc)[0] == "PASS"
    assert SC.sales("A1", {"monthlySold": 300}, "PASS", sc)[0] == "UNKNOWN"   # 2倍ずれ
    assert SC.sales("N", {}, "UNKNOWN", sc)[2] is None                       # キーゾン未確認


def t_share():
    st, _, i = SC.share_gate("A1", 11, 10, 1, False)       # 11÷2=5.5
    assert st == "PASS" and i["rec"] == 10 and round(i["months"], 1) == 1.8
    st, _, i = SC.share_gate("A2", 7, 10, 1, False)        # 7÷4=1.75
    assert st == "FAIL" and "1社以下" in i["fix"]
    st, _, i = SC.share_gate("A3", 2, 10, 1, False)        # 競合ゼロでも2
    assert st == "FAIL" and "競合ゼロでも" in i["fix"]
    st, _, i = SC.share_gate("A3", 4, 30, 1, False)        # 30点は多すぎ→3か月分に減らす
    assert st == "PASS" and i["rec"] == 12
    st, _, i = SC.share_gate("A3", 4, 30, 30, False)       # 最小ロット30点＝7.5か月
    assert st == "FAIL"
    assert SC.share_gate("NONE", 10, 10, 1, False)[0] == "UNKNOWN"


def t_doc():
    assert "PSE" in SC.doc_note("スリム蛍光灯 FLR32")
    assert "SDS" in SC.doc_note("ホタテの霧 スプレー")
    assert SC.doc_note("バスタオル") == ""


for f in (t_cart, t_sales, t_share, t_doc):
    f()
print("ok")
