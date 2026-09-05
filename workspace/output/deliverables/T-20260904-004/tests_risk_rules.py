#!/usr/bin/env python3
"""risk_rules.py の回帰テスト — T-20260904-004 / D。

`python3 tests_risk_rules.py` で走ります（pytest 不要。依存を増やさない）。

なぜテストを書くか:
    このフィルタは「買ってはいけない物を落とす」ためのもので、
    **落ちなかったこと**が事故になります。落ちるはずの物が落ちることを、
    毎回機械で確かめないと、静かに壊れても誰も気づきません。
"""

import sys

import risk_rules as R

FAILS = []


def check(name, cond):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"  NG  {name}")
        FAILS.append(name)


def blocked_by(v, rule_prefix):
    return v.blocked and any(r.startswith(rule_prefix) for r in v.reasons)


print("── #4 中古（最優先ルール）")
v = R.judge(netsea_name="中古 デスクチェア", brand="ノーブランド")
check("「中古」で落ちる", blocked_by(v, "#4"))
v = R.judge(netsea_name="アウトレット 収納ボックス", brand="ノーブランド")
check("「アウトレット」で落ちる", blocked_by(v, "#4"))
v = R.judge(netsea_name="開封済 タオルセット", brand="ノーブランド")
check("「開封済」で落ちる", blocked_by(v, "#4"))
v = R.judge(netsea_name="ＵＳＥＤ ジャケット", brand="ノーブランド")
check("全角 ＵＳＥＤ でも落ちる（NFKC 正規化）", blocked_by(v, "#4"))
v = R.judge(netsea_name="新品 クリアファイル A4", brand="ノーブランド",
            category_names=["文房具・オフィス用品"], description="新品未開封です")
check("新品は中古で落ちない", not blocked_by(v, "#4"))
check("中古ステータスが「該当なし」", v.used_status == "該当なし")

print("── 中古の「判定できない」を新品にしない")
v = R.judge(netsea_name="クリアファイル A4", brand="ノーブランド",
            category_names=["文房具・オフィス用品"], description="",
            description_available=False)
check("説明が取れなければ「要目視」", v.used_status == "要目視")
check("要目視は除外ではない（落とさない）", not blocked_by(v, "#4"))
check("要目視の注記が残る", any("目視" in n for n in v.notes))

print("── #1 電気用品（PSE）")
for name in ["USB充電式 LEDデスクライト", "モバイルバッテリー 10000mAh",
             "Bluetooth スピーカー", "ACアダプター 5V"]:
    v = R.judge(netsea_name=name, brand="ノーブランド")
    check(f"電気用品で落ちる: {name}", blocked_by(v, "#1"))
v = R.judge(netsea_name="電池不要 手動ミル", brand="ノーブランド",
            category_names=["ホーム＆キッチン"])
check("「電池不要」は除外しない", not blocked_by(v, "#1"))

print("── #2 ブランド（Tier A は落とす / Tier B は残して印を付ける）")
v = R.judge(netsea_name="Panasonic 乾電池", brand="パナソニック(Panasonic)")
check("著名ブランドで落ちる", blocked_by(v, "#2"))
check("brand_tier が A", v.brand_tier.startswith("A"))
v = R.judge(netsea_name="収納ケース 3個組", brand="Montagna",
            category_names=["ホーム＆キッチン"])
check("無名ブランドは落とさない", not blocked_by(v, "#2"))
check("brand_tier が B（要実機確認）", v.brand_tier.startswith("B"))
check("ゲート確認の注記が付く", any("ゲート" in n for n in v.notes))

print("── #3 #7 #8 #9 #12 #13 #14")
cases = [
    ("#3", "薬用 ハンドクリーム 100g"),
    ("#7", "エプソン互換 インクカートリッジ"),
    ("#8", "有機 コーヒー 豆 200g"),
    ("#9", "写真集 限定版"),
    ("#12", "ガラス製 花瓶"),
    ("#13", "管理医療機器 体温計"),
    ("#14", "殺虫剤 スプレー 450ml"),
]
for rule, name in cases:
    v = R.judge(netsea_name=name, brand="ノーブランド")
    check(f"{rule} で落ちる: {name}", blocked_by(v, rule))

print("── #11 大型・重量物（寸法が取れているときだけ）")
v = R.judge(netsea_name="収納ラック", brand="ノーブランド", package_mm=[900, 600, 400])
check("3辺合計1900mm で落ちる", blocked_by(v, "#11"))
v = R.judge(netsea_name="収納ラック", brand="ノーブランド", package_mm=[300, 200, 100])
check("小さければ落ちない", not blocked_by(v, "#11"))
v = R.judge(netsea_name="収納ラック", brand="ノーブランド", package_mm=None)
check("寸法不明は落とさない（不明を駄目にしない）", not blocked_by(v, "#11"))

print("── カテゴリ除外と4群適合")
v = R.judge(netsea_name="ヘアブラシ", brand="ノーブランド", category_names=["ビューティー", "ヘアケア"])
check("ビューティーはカテゴリごと落ちる", blocked_by(v, "カテゴリ除外"))
v = R.judge(netsea_name="A4クリアファイル 10枚", brand="ノーブランド",
            category_names=["文房具・オフィス用品", "ファイル"], description="新品")
check("文房具は落ちない", not v.blocked)
check("4群 ① に入る", v.fit_group.startswith("①"))
v = R.judge(netsea_name="ステンレス フック 4個", brand="ノーブランド",
            category_names=["DIY・工具・ガーデン", "金物"], description="新品")
check("DIY は 4群 ③ に入る", v.fit_group.startswith("③"))

print("── 完走軸（出品者100人規模）")
v = R.judge(netsea_name="A4クリアファイル", brand="ノーブランド",
            category_names=["文房具・オフィス用品"], description="新品", seller_count=120)
check("出品者120で落ちる", blocked_by(v, "完走不可"))
v = R.judge(netsea_name="A4クリアファイル", brand="ノーブランド",
            category_names=["文房具・オフィス用品"], description="新品", seller_count=6)
check("出品者6なら落ちない", not v.blocked)

print("── 触れないものは「触れない」と言う")
v = R.judge(netsea_name="ステンレス ワイヤーフック 4個入", brand="ノーブランド",
            category_names=["DIY・工具・ガーデン"], description="新品未使用品です")
check("リスク判定が「触れない」", "触れない" in v.risk_label)

print("── ミューテーション: ルールを壊したら落ちなくなることを確認する")
# 「落ちるはずの物が落ちる」テストだけだと、フィルタが常に True を返しても通ってしまう。
# 語彙を空にして**発火が止まる**ことを見て、テストが実際にこのルールを見ていると確かめる。
saved = R.USED_KEYWORDS[:]
try:
    R.USED_KEYWORDS.clear()
    v = R.judge(netsea_name="中古 デスクチェア", brand="ノーブランド")
    check("USED_KEYWORDS を空にすると #4 が発火しない（＝テストは本当にこの表を見ている）",
          not blocked_by(v, "#4"))
finally:
    R.USED_KEYWORDS[:] = saved
v = R.judge(netsea_name="中古 デスクチェア", brand="ノーブランド")
check("復元後は再び発火する", blocked_by(v, "#4"))

saved_e = R.ELECTRIC_KEYWORDS[:]
try:
    R.ELECTRIC_KEYWORDS.clear()
    v = R.judge(netsea_name="モバイルバッテリー 10000mAh", brand="ノーブランド")
    check("ELECTRIC_KEYWORDS を空にすると #1 が発火しない", not blocked_by(v, "#1"))
finally:
    R.ELECTRIC_KEYWORDS[:] = saved_e

print()
if FAILS:
    print(f"❌ {len(FAILS)} 件失敗: {FAILS}")
    sys.exit(1)
print("✅ すべて green")
