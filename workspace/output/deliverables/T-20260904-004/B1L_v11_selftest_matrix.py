# -*- coding: utf-8 -*-
"""A1（取引窓口を示す語）×否定形の網羅検査。v1.0 と v1.1 の判定を突き合わせる。"""
import io, json, itertools, csv, re
import B1L_v11_selftest_recheck399 as R

r10, r11 = R.load(R.V10), R.load(R.V11)
a1 = [r for r in r10["rules"] if r["id"] == "A1_trade_window"][0]["terms"]
neg_tpl = ["{}は行っておりません。", "{}はお受けしておりません。", "{}は募集しておりません。",
           "{}は受け付けておりません。", "{}のご依頼はお断りしております。",
           "{}のご相談はご遠慮ください。", "{}は現在停止しております。"]
bad10 = bad11 = 0
rows = []
for t, tpl in itertools.product(a1, neg_tpl):
    s = tpl.format(t)
    c10 = R.classify(s, r10)["optout_class"]
    c11 = R.classify(s, r11)["optout_class"]
    if c10 == "A_PLUS":
        bad10 += 1
    if c11 == "A_PLUS":
        bad11 += 1
        rows.append((t, s, c10, c11))
print("総パターン=%d  v1.0でA_PLUS(最優先)に化ける=%d  v1.1=%d" % (len(a1)*len(neg_tpl), bad10, bad11))
for x in rows:
    print("  残穴:", x)

# 肯定形が A_PLUS のまま保たれるか（過剰是正の確認）
pos_tpl = ["{}はこちらのフォームからご連絡ください。", "{}についてはお気軽にご相談ください。", "{}を募集しております。"]
lost = []
for t, tpl in itertools.product(a1, pos_tpl):
    s = tpl.format(t)
    c11 = R.classify(s, r11)["optout_class"]
    if c11 != "A_PLUS":
        lost.append((t, s, c11))
print("肯定形パターン=%d  v1.1でA_PLUSを失う=%d" % (len(a1)*len(pos_tpl), len(lost)))
for x in lost:
    print("  失注:", x)

# 消費者向け直販なし（N2）が誤って除外されないか
n2 = ["一般のお客様への直接の販売は致しておりません。", "一般消費者への直販は行っておりません。",
      "エンドユーザー様との直接のお取引は行っておりません。"]
for s in n2:
    print("N2:", s, "->", R.classify(s, r11)["optout_class"])
# E3（個人）は除外されるか
e3 = ["個人のお客様と直接のお取引は行っておりません。", "法人様以外のお取引を控えさせて頂いております。",
      "個人の方向けの直接の販売は行っておりません。"]
for s in e3:
    print("E3:", s, "->", R.classify(s, r11)["optout_class"])
# review_triggers スキャン
rows = list(csv.reader(io.open(R.CSV, encoding="utf-8-sig")))
hdr = rows[1]; data = [dict(zip(hdr, r)) for r in rows[2:]]
trg = r11["review_triggers"]["restrictive_scope"]
n = 0
for d in data:
    t = re.sub(r"\s+", "", d["form_optout_notice"])
    hit = [x for x in trg if x in t]
    if hit:
        n += 1
        print("review_trigger:", d["メーカー名"], hit, "現class=", d["optout_class"])
print("review_trigger該当=%d社" % n)
