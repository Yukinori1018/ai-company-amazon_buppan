# -*- coding: utf-8 -*-
"""法務ハルオの A〜E 判定ルール（v1.0）に対する単体テスト。

期待値はすべて **実在ページの原文**から取っている。作り話のテキストは使わない。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.optout import (  # noqa: E402
    classify_window, pick_company_class, message_rules, individual_decisions,
    is_personal_local_part,
)

# --- 実在ページの原文 -------------------------------------------------------
AICHI_FORM = ("※こちらのメールフォームからのセールス・勧誘等は、「特定電子メールの送信に関する法律」に"
              "基づき、固くお断りします。※こちらのメールフォームからセールス・勧誘等があった場合、"
              "「迷惑メール相談センター」に通報します。")
SUGOROKUYA = ("実店舗をお持ちでないオンライン専売業者さまとのお取引につきましては一律お断りを"
              "させていただいております。Amazon・楽天市場・Yahoo!ショッピング・メルカリなど、"
              "大手ECモールへの出品をご遠慮いただいております。")
CAPCOM = "※ 営業・ご提案については書面にて、カプコン本社宛にお送りください。"
RICHELL = "商品やサービスの売り込み、製品アイデア等のご提案はご遠慮ください。"
TAMAGAWA = "広告、協賛の依頼、営業活動もしくは営利を目的とするもの等はご遠慮ください。"


class TestClassification(unittest.TestCase):
    def _c(self, text):
        return classify_window(text)["optout_class"]

    def test_D_法定文言と通報明示(self):
        r = classify_window(AICHI_FORM)
        self.assertEqual(r["optout_class"], "D")
        self.assertEqual(r["allowed_channels"], [])
        self.assertEqual(r["contact_priority"], 99)
        self.assertIn("通報", r["optout_hit_terms"])

    def test_E_実店舗必須とモール禁止(self):
        r = classify_window(SUGOROKUYA)
        self.assertEqual(r["optout_class"], "E")
        self.assertIn("実店舗+お断り", r["optout_hit_terms"])
        self.assertTrue(r["recheck_condition"])   # 実店舗取得時に再評価

    def test_B_書面のみは経路指定であって拒絶ではない(self):
        r = classify_window(CAPCOM)
        self.assertEqual(r["optout_class"], "B")
        self.assertEqual(r["allowed_channels"], ["mail_post"])

    def test_C_売り込みお断りは保留(self):
        r = classify_window(RICHELL)
        self.assertEqual(r["optout_class"], "C")
        self.assertEqual(r["contact_priority"], 9)
        self.assertEqual(r["allowed_channels"], ["form"])

    def test_A_表示なし(self):
        self.assertEqual(self._c(""), "A")
        self.assertEqual(self._c("お問い合わせは下記フォームよりお願いいたします。"), "A")

    def test_A_PLUS_取引窓口の明示(self):
        r = classify_window("事業内容 輸入文具・生活用品等の企画、卸販売、OEM")
        self.assertEqual(r["optout_class"], "A_PLUS")
        self.assertEqual(r["contact_priority"], 1)


class TestFalsePositiveGuards(unittest.TestCase):
    """法務の注意① —— 「営業」の誤爆を防ぐこと。"""

    def test_営業時間は拒絶ではない(self):
        self.assertEqual(classify_window("営業時間は9:00〜17:00です。")["optout_class"], "A")

    def test_営業日_営業所_営業担当も誤爆しない(self):
        for t in ("土日祝は営業日ではありません。ご注文はお断りする場合があります。",
                  "最寄りの営業所へお問い合わせください。取扱いのない商品はお断りします。",
                  "営業担当までご連絡ください。"):
            self.assertNotEqual(classify_window(t)["optout_class"], "D", t)

    def test_営業部は取引窓口として拾う(self):
        self.assertEqual(classify_window("営業部までお問い合わせください。")["optout_class"], "A_PLUS")

    def test_遠く離れた語は共起とみなさない(self):
        text = "営業時間のご案内です。" + "あ" * 200 + "在庫切れの場合はご注文をお断りすることがあります。"
        self.assertEqual(classify_window(text)["optout_class"], "A")

    def test_同一文なら30文字を超えても共起(self):
        text = "セールスや勧誘を目的としたご連絡につきましては、誠に恐れ入りますが固くお断りしております"
        self.assertEqual(classify_window(text)["optout_class"], "D")


class TestWindowLevel(unittest.TestCase):
    """法務の注意③ —— 窓口単位で判定し、最も緩い有効な窓口を採る。"""

    def test_最も緩い窓口を採る(self):
        wins = [classify_window(RICHELL), classify_window("")]
        self.assertEqual(pick_company_class(wins)["optout_class"], "A")

    def test_Eは会社単位で固定する(self):
        wins = [classify_window(SUGOROKUYA), classify_window("")]
        self.assertEqual(pick_company_class(wins)["optout_class"], "E")

    def test_窓口ゼロならNone(self):
        self.assertIsNone(pick_company_class([]))


class TestMessageRules(unittest.TestCase):
    def test_URL禁止が最重要ルールとして取れる(self):
        rules = message_rules()
        self.assertTrue(rules)
        self.assertIn("URL", rules[0])

    def test_個社判定が読める(self):
        d = individual_decisions()
        self.assertEqual(d["すごろくや"]["class"], "E")
        self.assertEqual(d["リッチェル"]["class"], "C")
        self.assertEqual(d["カプコン"]["channels"], ["mail_post"])


class TestPersonalLocalPart(unittest.TestCase):
    def test_窓口名を人名と誤認しない(self):
        for a in ("Askfender.jp@fender.com", "customerservice.japan@ap.hasbro.com",
                  "infobox@astro-p.co.jp", "b2b@takagi.co.jp"):
            self.assertFalse(is_personal_local_part(a), a)

    def test_人名らしいものは拾う(self):
        self.assertTrue(is_personal_local_part("t.suzuki@example.co.jp"))


if __name__ == "__main__":
    unittest.main()


class TestRecheckCondition(unittest.TestCase):
    """再評価条件は**実際にヒットした規則のもの**だけを付ける（クラス単位で流用しない）。"""

    def test_D2該当にD5の再評価条件を付けない(self):
        r = classify_window(TAMAGAWA)          # 営業活動…はご遠慮ください → D2
        self.assertEqual(r["optout_class"], "D")
        self.assertNotIn("取引窓口の新設", r["recheck_condition"])

    def test_E1は実店舗取得を再評価条件に持つ(self):
        self.assertIn("実店舗", classify_window(SUGOROKUYA)["recheck_condition"])


class TestBusinessDecisionSubclass(unittest.TestCase):
    """「そもそも直販しない」= E の下位区分（2026-09-04 カズヨ判断）。

    **法務ルールJSON（ハルオの所有物）は変更していない。**
    クラスは既存の E のまま、下位区分と決定者を別列で持たせて所有者を明示している。
    その適用は apply_optout.py 側の責務なので、ここでは
    「JSONにこの類型のクラスが増えていないこと」を守る回帰テストにする。
    """

    def test_法務ルールにクラスを勝手に増やしていない(self):
        from pipeline.optout import load_rules
        self.assertEqual(set(load_rules()["classes"]), {"A_PLUS", "A", "B", "C", "D", "E"})

    def test_直販なしの文言は法務ルール単体ではAのまま(self):
        # 事業判断で E に落とすのは適用側。判定器は法務ルールに忠実であること。
        r = classify_window("弊社は一般のお客様への直接の販売は致しておりません。")
        self.assertEqual(r["optout_class"], "A")
