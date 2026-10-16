#!/usr/bin/env python3
"""2026-10-12 社長方針「今だけ、儲かるなら、廃止が決まっているものも仕入れて良い」の回帰テスト（タカシ）。

1. ledger_refresh.end_gate：終売の印＋3条件（在庫・在庫月数・価格の傾き）で PASS/FAIL/UNKNOWN
2. ledger_refresh.is_human：秘書が台帳で直接下した判断（確認者にタカシが無い）は凍結する
3. ledger_refresh.route_to_sd の在庫：価格だけ見た行（在庫=未確認）を「在庫あり」にしない（定義の確認）

実行：python3 test_now_only_20261012.py （0 で成功）
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger_refresh as L  # noqa: E402

NG = []


def check(name, cond):
    print(("OK  " if cond else "NG  ") + name)
    if not cond:
        NG.append(name)


def s_of(title, months, price_verdict):
    return {"row": {"商品名": title}, "econ": None, "price": SimpleNamespace(verdict=price_verdict),
            "_share": {"months": months}}


LAMP = "DNライティング エースライン スリム蛍光灯 FLR910T6EX-WW"
for name, stock, months, pv, want in (
        ("3条件そろえば PASS（印は残す）", "PASS", 1.6, "使える", "PASS"),
        ("卸の在庫が未確認なら UNKNOWN", "UNKNOWN", 1.6, "使える", "UNKNOWN"),
        ("卸が品切れなら FAIL", "FAIL", 1.6, "使える", "FAIL"),
        ("製造終了(2028-01)までに売り切れないなら FAIL", "PASS", 40.0, "使える", "FAIL"),
        ("下落トレンドなら FAIL", "PASS", 1.6, "下落トレンド", "FAIL")):
    gates = [("仕入れ", stock, "", "")]
    L.end_gate(s_of(LAMP, months, pv), gates)
    g = [x for x in gates if x[0] == "終売"]
    check(name, g and g[0][1] == want and "終売" in g[0][2])

gates = [("仕入れ", "PASS", "", "")]
L.end_gate(s_of("ふきん 3枚", 1.0, "使える"), gates)
check("印の無い商品にはゲートを足さない", [x[0] for x in gates] == ["仕入れ"])

check("秘書の直接判断は凍結",
      L.is_human({"ASIN": "B00Q64QHII", "確認者": "カズヨ（社長方針で終売品を許容・ヤザワ取引条件を実画面確認）"}))
check("機械だけの行は凍結しない",
      not L.is_human({"ASIN": "B000TEST00", "確認者": "タカシ（機械判定・実画面未確認）"}))

# 2026-10-17 秘書判断 A：SD 卸価格だけ人が見た行（機械が付ける注記）は凍結しない
check("SD 卸価格のみ実画面の行は凍結しない",
      not L.is_human({"ASIN": "B000TEST01",
                      "確認者": "タカシ（機械判定・実画面未確認）／カズヨ（SD 卸価格のみ実画面）"}))
check("sd_rows が付ける注記と is_human の除外が同じ文字列",
      L.SD_PRICE_ONLY_NOTE == "／カズヨ（SD 卸価格のみ実画面）")
check("カズヨの実画面確認（注記以外）は引き続き凍結",
      L.is_human({"ASIN": "B000TEST02", "確認者": "カズヨ（実画面 10/16）"}))

f, nv = L.fix_for("終売", "UNKNOWN", "(a)仕入れ先の在庫 未確認", {})
check("終売の「こう変えれば」が書ける", "今だけ" in f and not nv)

print("NG:", "なし" if not NG else NG)
sys.exit(1 if NG else 0)
