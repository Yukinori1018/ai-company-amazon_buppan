#!/usr/bin/env python3
"""build_order_sets.py の回帰テスト（パイプライン単位）— T-20260904-004 / D。

`python3 tests_order_sets.py` で走ります。**本物のデータは読みません**（合成行だけ）。

risk_rules 単体のテスト（tests_risk_rules.py）とは狙いが違います。
こちらが見るのは「ルールがパイプラインに**繋がっているか**」です。
判定関数が正しくても、呼び出し側が結果を捨てていれば同じ事故が起きます。
"""

import sys

sys.path.insert(0, ".")

import build_order_sets as B  # noqa: E402
import risk_rules as R        # noqa: E402

FAILS = []


def check(name, cond):
    print(f"  {'ok ' if cond else 'NG '} {name}")
    if not cond:
        FAILS.append(name)


def row(name, jan, **kw):
    """candidates.csv 1行ぶんの最小構成。実データの列名に合わせてある。"""
    base = {
        "商品名": name, "Amazon商品名": name, "JAN": jan, "ASIN": "B0TEST" + jan[-4:],
        "サプライヤー名": "テスト卸", "NETSEA卸値(税抜)": "900", "NETSEA卸値(税込)": "990",
        "Amazon価格": "2500", "純利益": "400", "利益率%": "16.0",
        "月間販売数(30日ランク下落数)": "8", "出品者数": "3", "出品者数の出所": "テスト",
        "Amazon本体の有無": "なし", "FBAサイズ": "小型", "出品の入数": "1",
        "最小発注数": "6", "最小発注額(税込)": "5940", "要確認理由": "",
        "ネット販売可否": "可", "NETSEA商品ページ": f"https://www.netsea.jp/shop/999/{jan}",
        "Amazonページ": "", "Keepaリンク": "",
    }
    base.update(kw)
    return base


FACTS = {
    "1000000000001": {"brand": "ノーブランド", "category_names": ["文房具・オフィス用品"],
                      "package_mm": [200, 150, 20], "package_g": 200},
    "1000000000002": {"brand": "ノーブランド", "category_names": ["文房具・オフィス用品"],
                      "package_mm": [200, 150, 20], "package_g": 200},
    "1000000000003": {"brand": "パナソニック(Panasonic)", "category_names": ["文房具・オフィス用品"],
                      "package_mm": [200, 150, 20], "package_g": 200},
    "1000000000004": {"brand": "ノーブランド", "category_names": ["ビューティー"],
                      "package_mm": [200, 150, 20], "package_g": 200},
    "1000000000005": {"brand": "ノーブランド", "category_names": ["文房具・オフィス用品"],
                      "package_mm": [200, 150, 20], "package_g": 200},
}

ROWS = [
    row("A4クリアファイル 10枚組", "1000000000001"),                      # 通るはず
    row("中古 デスクオーガナイザー", "1000000000002"),                    # #4 で落ちる
    row("Panasonic ボールペン", "1000000000003"),                        # #2 で落ちる
    row("薬用ハンドクリーム", "1000000000004"),                          # #3/カテゴリで落ちる
    row("A4バインダー 赤字商品", "1000000000005", **{"利益率%": "-3.0"}),  # S2 赤字で落ちる
]

print("── パイプラインに条件1が繋がっているか")
s1, s2, stats = B.run_filters(ROWS, FACTS)
kept_jans = {r["JAN"] for r, _, _ in s1}
check("正常な文房具は S1 を通る", "1000000000001" in kept_jans)
check("中古は S1 で落ちる", "1000000000002" not in kept_jans)
check("著名ブランドは S1 で落ちる", "1000000000003" not in kept_jans)
check("化粧品は S1 で落ちる", "1000000000004" not in kept_jans)
check("S1 の内訳が数えられている", sum(stats["S1_除外内訳_最初に触れた項目"].values()) == 3)

print("── パイプラインに条件2が繋がっているか")
s2_jans = {r["JAN"] for r, _, _, _ in s2}
check("赤字は S2 で落ちる", "1000000000005" not in s2_jans)
check("正常な文房具は S2 も通る", "1000000000001" in s2_jans)
check("S2 の内訳に『赤字』が立つ", any("赤字" in k for k in stats["S2_除外内訳"]))

print("── 検算: 落とした件数の合計 == 減った行数")
d1 = stats["S0_母数"] - stats["S1_残"]
check(f"S1: 落とした{sum(stats['S1_除外内訳_最初に触れた項目'].values())} == 減った{d1}",
      sum(stats["S1_除外内訳_最初に触れた項目"].values()) == d1)
d2 = stats["S1_残"] - stats["S2_残"]
check(f"S2: 落とした{sum(stats['S2_除外内訳'].values())} == 減った{d2}",
      sum(stats["S2_除外内訳"].values()) == d2)

print("── 中古の確定（S3）は商品説明を実際に見ているか")
descs = {"999-1000000000001": {"description": "アウトレット品につき箱に傷があります",
                              "spec_size": "", "shop_name": "テスト卸"}}
st = dict(stats)
st["S3_除外内訳"] = {}
s3 = B.apply_used_check(s2, descs, st)
check("商品名がきれいでも、説明文の「アウトレット」で落ちる",
      "1000000000001" not in {r["JAN"] for r, _, _, _, _ in s3})
check("落とした理由が記録されている", sum(st["S3_除外内訳"].values()) == 1)

st2 = {"S3_除外内訳": {}}
s3b = B.apply_used_check(s2, {}, st2)
check("説明が取れなければ「要目視」で残す（新品と言い切らない）",
      any(v.used_status == "要目視" for _, v, _, _, _ in s3b))
check("矛盾した古い注記が残っていない",
      all("機械判定できない" not in " ".join(v.notes) for _, v, _, _, _ in s3b))

print("── ミューテーション: ルールを壊すとパイプラインの発火が止まるか")
saved = R.USED_KEYWORDS[:]
try:
    R.USED_KEYWORDS.clear()
    s1m, _, _ = B.run_filters(ROWS, FACTS)
    check("USED_KEYWORDS を空にすると中古行が S1 を通ってしまう（＝繋がっている証拠）",
          "1000000000002" in {r["JAN"] for r, _, _ in s1m})
finally:
    R.USED_KEYWORDS[:] = saved

print("── 出力ガード: 宣言した列が全行空なら止まるか")
try:
    B.assert_columns_not_all_empty([{"★リスク判定": "", "★中古品表記の有無": "",
                                     "★仕入れ額(税込)": "", "実費込み純利益": "",
                                     "利益率%": "", "ASIN": "", "JAN": "", "発注先URL": ""}],
                                   B.OUT_COLUMNS)
    check("全行空の CSV は書かせない", False)
except SystemExit:
    check("全行空の CSV は書かせない", True)

print("── 発注セットは 5〜10SKU・総額5万円以内に収まるか")
many = [row(f"A4ファイル {i}", f"200000000{i:04d}") for i in range(20)]
facts_many = {r["JAN"]: {"brand": "ノーブランド", "category_names": ["文房具・オフィス用品"],
                         "package_mm": [200, 150, 20], "package_g": 200} for r in many}
_, s2m, stm = B.run_filters(many, facts_many)
s3m = B.apply_used_check(s2m, {r["NETSEA商品ページ"].split("/")[-2] + "-" + r["JAN"]:
                               {"description": "新品です"} for r in many}, {"S3_除外内訳": {}})
s4m = B.apply_fit_group(s3m, {"S4_除外内訳": {}})
sets = B.build_supplier_sets(s4m, {}, {"テスト卸": "999"})
check("セットが1つできる", len(sets) == 1)
if sets:
    s = sets[0]
    check(f"SKU数 {s['SKU数']} が 10 以内", s["SKU数"] <= B.SET_SKU_MAX)
    check(f"合計 {s['合計仕入れ額(税込)']:,}円 が 5万円以内",
          s["合計仕入れ額(税込)"] <= B.TOTAL_BUDGET)
    check("送料が取れなければ空欄（推測で埋めない）", s["この注文額での送料"] == "")

print()
if FAILS:
    print(f"❌ {len(FAILS)} 件失敗: {FAILS}")
    sys.exit(1)
print("✅ すべて green")
