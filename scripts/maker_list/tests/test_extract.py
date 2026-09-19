"""抽出ロジックのテスト。社長が実際にダイヤルする値なので、ここは落とせない。

    python3 -m unittest discover -s scripts/maker_list/tests -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from scripts.maker_list.extract import ec, phone           # noqa: E402
from scripts.maker_list.extract.htmlutil import norm_name  # noqa: E402


class TestPhoneNormalize(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(phone.normalize("0798-26-1882"), "0798-26-1882")

    def test_paren_style(self):     # JASPO の表記
        self.assertEqual(phone.normalize("(011)-826-3533"), "011-826-3533")

    def test_fullwidth(self):
        self.assertEqual(phone.normalize("０３－１２３４－５６７８"), "03-1234-5678")

    def test_spaces(self):
        self.assertEqual(phone.normalize("06 6536 5002"), "06-6536-5002")

    def test_postal_code_is_not_a_phone(self):
        """郵便番号 003-0862 を電話番号として拾わない。これが最悪の事故。"""
        self.assertIsNone(phone.normalize("〒003-0862"))

    def test_address_banchi_is_not_a_phone(self):
        self.assertIsNone(phone.normalize("埼玉県越谷市増森207-1"))

    def test_too_short(self):
        self.assertIsNone(phone.normalize("03-123-456"))


class TestPhoneClassify(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(phone.classify("0120-712-122"), "フリーダイヤル")
        self.assertEqual(phone.classify("0800-123-4567"), "フリーダイヤル")
        self.assertEqual(phone.classify("090-1234-5678"), "携帯")
        self.assertEqual(phone.classify("050-1234-5678"), "IP電話")
        self.assertEqual(phone.classify("03-1234-5678"), "固定電話")

    def test_valid_lengths(self):
        self.assertTrue(phone.is_valid("0312345678"))       # 固定10桁
        self.assertTrue(phone.is_valid("0120712122"))       # 0120は10桁
        self.assertTrue(phone.is_valid("08001234567"))      # 0800は11桁
        self.assertFalse(phone.is_valid("0120712122X".replace("X", "")[:9]))
        self.assertFalse(phone.is_valid("1234567"))         # 郵便番号の桁


class TestPhoneFindAll(unittest.TestCase):
    def test_mobile_is_dropped_by_default(self):
        """個人の携帯番号をリストに混ぜない（PUBLIC リポに出る事故の予防）。"""
        got = phone.find_all("担当直通 090-1234-5678 TEL 03-1234-5678")
        self.assertEqual([g["番号"] for g in got], ["03-1234-5678"])

    def test_mobile_kept_when_asked(self):
        got = phone.find_all("090-1234-5678", keep_mobile=True)
        self.assertEqual(got[0]["種別"], "携帯")

    def test_fax_is_labelled(self):
        got = phone.find_all("TEL 03-1111-2222 FAX 03-1111-3333")
        self.assertEqual(got[0]["ラベル"], "TEL")
        self.assertEqual(got[1]["ラベル"], "FAX")


class TestPickTelAndFax(unittest.TestCase):
    def test_splits_tel_and_fax(self):
        tel, kind, fax = phone.pick_tel_and_fax("TEL:03-1111-2222 / FAX:03-1111-3333")
        self.assertEqual((tel, kind, fax), ("03-1111-2222", "固定電話", "03-1111-3333"))

    def test_fixed_line_beats_freedial(self):
        """0120 は担当者に繋がらないので、固定電話があればそちらを採る。"""
        tel, _k, _f = phone.pick_tel_and_fax("お客様センター 0120-712-122 代表 03-5555-6666")
        self.assertEqual(tel, "03-5555-6666")

    def test_freedial_used_when_only_option(self):
        tel, kind, _f = phone.pick_tel_and_fax("お客様センター 0120-712-122")
        self.assertEqual((tel, kind), ("0120-712-122", "フリーダイヤル"))

    def test_fax_only_page_yields_no_tel(self):
        tel, _k, fax = phone.pick_tel_and_fax("FAX 03-1111-3333")
        self.assertIsNone(tel)
        self.assertEqual(fax, "03-1111-3333")

    def test_nothing(self):
        self.assertEqual(phone.pick_tel_and_fax("会社概要"), (None, None, None))


class TestEC(unittest.TestCase):
    def test_cart_platform(self):
        got = ec.detect([("https://foo.thebase.in/", "ショップ")], "", "example.co.jp")
        self.assertEqual(got["自社EC"], "有（要確認）")
        self.assertIn("BASE", got["自社EC根拠"])

    def test_anchor_text(self):
        got = ec.detect([("/ec/", "オンラインショップ")], "", "example.co.jp")
        self.assertEqual(got["自社EC"], "有（要確認）")

    def test_no_signal(self):
        got = ec.detect([("/company/", "会社概要")], "会社概要", "example.co.jp")
        self.assertEqual(got["自社EC"], "未確認")

    def test_mall_links_from_own_page_only(self):
        """メーカー自身のHPに貼られたリンクを読むだけ。楽天には触れない。"""
        got = ec.detect([("https://www.rakuten.co.jp/shop-x/", "楽天市場店"),
                         ("https://www.amazon.co.jp/stores/x", "Amazon")], "", "example.co.jp")
        self.assertEqual(got["モール"], "Amazon, 楽天")

    def test_yahoo_store_link(self):
        got = ec.detect([("https://store.shopping.yahoo.co.jp/foo/", "Yahoo!店")], "", "x.jp")
        self.assertEqual(got["モール"], "Yahoo")

    def test_ec_never_says_no(self):
        """05 §4-4: 値は「有（要確認）」か「未確認」の2つだけ。「無」と書かない。"""
        for got in (ec.detect([], "", "x.jp"),
                    ec.detect([("/company/", "会社概要")], "会社概要", "x.jp")):
            self.assertIn(got["自社EC"], ("有（要確認）", "未確認"))
            self.assertIn(got["モール"], ("未確認",))

    def test_site_description(self):
        html_ = ('<title>株式会社テスト｜ステンレス厨房機器の製造</title>'
                 '<meta name="description" content="業務用厨房機器の総合メーカー">')
        d = ec.site_description(html_)
        self.assertIn("ステンレス厨房機器", d)
        self.assertIn("業務用厨房機器", d)

    def test_mall_unknown_is_not_zero(self):
        """リンクが無い＝出店していない、ではない。『未確認』と書く。"""
        self.assertEqual(ec.detect([], "", "example.co.jp")["モール"], "未確認")

    def test_foreign_shop_link_is_not_own_ec(self):
        got = ec.detect([("https://other-retailer.jp/shop/", "取扱店")], "", "example.co.jp")
        self.assertEqual(got["自社EC"], "未確認")

    def test_wholesale_words(self):
        self.assertEqual(ec.detect([], "OEM承ります", "x.jp")["卸OEM記載"], "有（要確認）")

    def test_guess_products(self):
        self.assertIn("ステンレス",
                      ec.guess_products("事業内容：ステンレス製厨房用品の製造販売"))


class TestNormName(unittest.TestCase):
    def test_legal_form_stripped(self):
        self.assertEqual(norm_name("株式会社アイセン"), norm_name("アイセン(株)"))

    def test_spacing(self):
        self.assertEqual(norm_name("株式会社 赤川器物製作所"), norm_name("赤川器物製作所"))


if __name__ == "__main__":
    unittest.main()
