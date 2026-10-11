#!/usr/bin/env python3
"""2026-10-11 夜の修正の回帰テスト（タカシ）。

1. write_report.yen：None を「未取得」と書く（03:44 の TypeError の再発防止）
2. screen_checks.cart_gate：注記つきの「カートなし(…非表示)」を第三者 PASS にしない
3. screen_checks.load_keizon_screen：キーゾン表が出なかった行は載せない（0個と書かない）
4. screen_checks.backorder_only：即納0・取り寄せ型だけの棚を拾う

実行：python3 test_night_20261011.py （0 で成功）
"""
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_checks as SC  # noqa: E402
import write_report as W    # noqa: E402

NG = []


def check(name, cond):
    print(("OK  " if cond else "NG  ") + name)
    if not cond:
        NG.append(name)


# 1. yen
check("yen(None) は未取得", W.yen(None) == "未取得")
check("yen('') は未取得", W.yen("") == "未取得")
check("yen(1234) は 1,234円", W.yen(1234) == "1,234円")
check("yen(-566.4) は -566円", W.yen(-566.4) == "-566円")
check("yen(0) は 0円（0 は値として書く）", W.yen(0) == "0円")

# 1b. 卸の実額を伏せる（PUBLIC リポ）
m = W.mask_wholesale("【こう変えれば】卸1点 111円（税抜）以下なら B（いま 2,222円）／売価 2,940円 以上の棚なら B")
check("卸の実額（架空値 111・2,222）が消える", "111" not in m and "2,222" not in m)
check("Amazon 側の売価（2,940円）は残る", "2,940円" in m)
m = W.mask_wholesale("SD 経由（卸1点 3,333円税抜 実画面）")
check("卸1点 3,333円税抜 も消える", "3,333" not in m)
m = W.mask_wholesale("卸1点 300円（税抜）以下なら B・250円以下なら A")
check("A の閾値も消える", "300" not in m and "250" not in m)

# 2. cart_gate
for holder, yn in (("カートなし(一般的な価格より高いため非表示)", False),
                   ("カートなし(一般的な価格より高いため非表示)", None),
                   ("高値で非表示", None), ("カートなし", None)):
    st, _ = SC.cart_gate(SC.Cart(holder, "", "", "2026-10-11", has_cart=yn))
    check(f"cart_gate「{holder}」(has_cart={yn}) は UNKNOWN", st == "UNKNOWN")
st, _ = SC.cart_gate(SC.Cart("A1ショップ", "3453", "", "2026-10-11", has_cart=True))
check("cart_gate 第三者の店名は PASS", st == "PASS")

# 3/4. ファイル系（OUT を一時ディレクトリに差し替える）
orig = SC.OUT
with tempfile.TemporaryDirectory() as d:
    SC.OUT = Path(d)
    with (SC.OUT / "kz_screen_t.csv").open("w", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ASIN", "キーゾン過去1ヶ月目", "過去2ヶ月目", "過去3ヶ月目", "平均月間", "確認時刻", "確認者"])
        w.writerow(["A1", "13", "11", "14", "12", "2026-10-11 04:25", "カズヨ"])
        w.writerow(["A2", "", "", "", "", "2026-10-11 04:16", "カズヨ"])
        w.writerow(["A3", "0", "0", "6", "2", "2026-10-11 04:18", "カズヨ"])
    kz = SC.load_keizon_screen()
    check("キーゾン表あり A1 は平均12", "A1" in kz and kz["A1"].avg == 12 and kz["A1"].months == ["13", "11", "14"])
    check("キーゾン表なし A2 は載せない（未確認のまま）", "A2" not in kz)
    check("0/0/6 の A3 は 0 を含めて載る", "A3" in kz and kz["A3"].avg == 2)
    check("人のキーゾンは checked が Keepa で始まらない（人の確認として数える）",
          not kz["A1"].checked.startswith("Keepa"))
    with (SC.OUT / "offer_check_t.csv").open("w", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ASIN", "カート対象FBA", "即納の自己発送", "取り寄せ型", "内訳", "確認時刻", "確認者"])
        w.writerow(["B1", "0", "0", "1", "取り寄せ型1本", "t", "カズヨ"])
        w.writerow(["B2", "0", "3", "0", "即納3本", "t", "カズヨ"])
    check("即納0・取り寄せ1 は backorder_only が理由を返す", bool(SC.backorder_only("B1")))
    check("即納3 は backorder_only が空", SC.backorder_only("B2") == "")
    check("画面実数は offers に優先される", SC.offers("B2")[:2] == (0, 3))
    st, why, info = SC.share_gate("B2", 10, None, None, False)
    check("月販10・即納3 は取り分2.5で FAIL（緩めない）", st == "FAIL" and abs(info["share"] - 2.5) < 1e-9)
    st, why, info = SC.share_gate("B2", 12, None, None, True)
    check("月販12・即納3 は取り分3.0で PASS・書類ゲートで最小10点", st == "PASS" and info["floor"] == 10)
SC.OUT = orig

print("NG:", NG or "なし")
raise SystemExit(1 if NG else 0)
