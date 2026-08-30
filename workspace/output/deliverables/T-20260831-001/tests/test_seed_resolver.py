# -*- coding: utf-8 -*-
"""既取得55社 resolver のテスト。実ファイル（T-20260804-001）を読む。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.normalize import normalize_row  # noqa: E402
from pipeline.resolvers.seed_contacts import SeedContactsResolver, DEFAULT_GLOB  # noqa: E402
from pipeline.schema import CONF_CONFIRMED  # noqa: E402

import glob as _glob

HAS_SEEDS = bool(_glob.glob(DEFAULT_GLOB))


@unittest.skipUnless(HAS_SEEDS, "T-20260804-001/contacts_batch*.json が見つからない")
class TestSeedResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = SeedContactsResolver()

    def test_matches_across_naming_styles(self):
        """55社側は 'レゴ LEGO'（空白併記）、822社側は 'LEGO(レゴ)'（括弧併記）。

        表記が違っても同じ会社として引けることが、この resolver の存在理由。
        """
        got = self.resolver.resolve(normalize_row("LEGO(レゴ)"))
        self.assertIsNotNone(got)
        self.assertTrue(got.website)
        self.assertEqual(got.confidence, CONF_CONFIRMED)

    def test_unknown_maker_returns_none(self):
        self.assertIsNone(self.resolver.resolve(normalize_row("存在しないメーカーXYZ")))

    def test_url_in_email_field_goes_to_contact_form(self):
        """55社の実績では email 欄にフォームURLが入っている行がある。

        列名から意味を推測せず、値の形（http で始まるか）で振り分ける。
        """
        got = self.resolver.resolve(normalize_row("エプソン"))
        self.assertIsNotNone(got)
        if got.email:
            self.assertNotIn("http", got.email)

    def test_no_false_positive_on_common_words(self):
        """'アストロプロダクツ Astro Products' が 'P&S Detailing Products' に
        誤マッチしないこと（単語分割で実際に踏んだ事故の回帰テスト）。"""
        got = self.resolver.resolve(normalize_row("P&S Detailing Products"))
        self.assertIsNone(got)

    def test_source_url_is_always_present_when_confirmed(self):
        got = self.resolver.resolve(normalize_row("シモジマ(SHIMOJIMA)"))
        self.assertIsNotNone(got)
        self.assertTrue(got.source_url or got.website)

    def test_never_invents_values(self):
        """55社の中には「特定できず空欄」の行がある。それを埋めて返さない。"""
        row = normalize_row("ノーブランド品")
        got = self.resolver.resolve(row)
        if got is not None:
            self.assertEqual(got.website, "")
            self.assertIn("特定できず", got.note)


if __name__ == "__main__":
    unittest.main()
