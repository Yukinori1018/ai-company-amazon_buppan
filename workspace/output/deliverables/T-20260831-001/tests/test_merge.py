# -*- coding: utf-8 -*-
"""マージ層のテスト。優先順位・空欄の扱い・確度の落とし方を固定する。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.merge import (  # noqa: E402
    merge,
    PRIORITY_HUMAN_VERIFIED,
    PRIORITY_PUBLIC_DB,
    PRIORITY_OFFICIAL_SITE,
    PRIORITY_SEARCH,
)
from pipeline.schema import (  # noqa: E402
    ContactFields,
    CONF_CONFIRMED,
    CONF_CANDIDATE,
    CONF_UNKNOWN,
    worst_confidence,
)


class TestMerge(unittest.TestCase):
    def test_higher_priority_wins_per_field(self):
        strong = ContactFields(website="https://a.example", source="公的DB",
                               confidence=CONF_CONFIRMED)
        weak = ContactFields(website="https://b.example", tel="03-0000-0000",
                             source="検索", confidence=CONF_CANDIDATE)
        got = merge([(PRIORITY_SEARCH, weak), (PRIORITY_PUBLIC_DB, strong)])
        self.assertEqual(got.website, "https://a.example")   # 強い方が勝つ
        self.assertEqual(got.tel, "03-0000-0000")            # 空欄は勝てない

    def test_empty_string_never_overwrites(self):
        strong = ContactFields(website="", source="公的DB", confidence=CONF_CONFIRMED)
        weak = ContactFields(website="https://b.example", source="検索",
                             confidence=CONF_CANDIDATE)
        got = merge([(PRIORITY_PUBLIC_DB, strong), (PRIORITY_SEARCH, weak)])
        self.assertEqual(got.website, "https://b.example")

    def test_only_contributing_sources_are_recorded(self):
        contributor = ContactFields(website="https://a.example", source="公的DB",
                                    source_url="https://db.example/1",
                                    confidence=CONF_CONFIRMED)
        bystander = ContactFields(source="検索", source_url="https://s.example",
                                  confidence=CONF_UNKNOWN, note="該当なし")
        got = merge([(PRIORITY_PUBLIC_DB, contributor), (PRIORITY_SEARCH, bystander)])
        self.assertEqual(got.source, "公的DB")
        self.assertEqual(got.source_url, "https://db.example/1")
        self.assertEqual(got.confidence, CONF_CONFIRMED)
        # 値を出さなかったソースの理由は備考には残す（消さない）
        self.assertIn("該当なし", got.note)

    def test_confidence_falls_to_the_weakest_contributor(self):
        a = ContactFields(website="https://a.example", source="A", confidence=CONF_CONFIRMED)
        b = ContactFields(tel="03-1", source="B", confidence=CONF_CANDIDATE)
        got = merge([(PRIORITY_PUBLIC_DB, a), (PRIORITY_OFFICIAL_SITE, b)])
        self.assertEqual(got.confidence, CONF_CANDIDATE)

    def test_no_results_is_unknown_and_empty(self):
        got = merge([])
        self.assertTrue(got.is_empty())
        self.assertEqual(got.confidence, CONF_UNKNOWN)
        self.assertEqual(got.source, "")

    def test_all_empty_results_stay_empty(self):
        """取れなかったときに勝手に埋めない、を固定する。"""
        got = merge([
            (PRIORITY_PUBLIC_DB,
             ContactFields(source="公的DB", confidence=CONF_UNKNOWN, note="該当なし")),
            (PRIORITY_SEARCH,
             ContactFields(source="検索", confidence=CONF_CANDIDATE,
                           note="同名企業が複数あり特定できず")),
        ])
        self.assertTrue(got.is_empty())
        self.assertEqual(got.confidence, CONF_UNKNOWN)
        self.assertIn("同名企業が複数", got.note)

    def test_same_priority_is_first_come(self):
        a = ContactFields(website="https://first.example", source="A")
        b = ContactFields(website="https://second.example", source="B")
        got = merge([(PRIORITY_SEARCH, a), (PRIORITY_SEARCH, b)])
        self.assertEqual(got.website, "https://first.example")

    def test_human_verified_beats_machine(self):
        human = ContactFields(website="https://human.example", source="既取得55社",
                              confidence=CONF_CONFIRMED)
        machine = ContactFields(website="https://bot.example", source="公的DB",
                                confidence=CONF_CONFIRMED)
        got = merge([(PRIORITY_PUBLIC_DB, machine), (PRIORITY_HUMAN_VERIFIED, human)])
        self.assertEqual(got.website, "https://human.example")

    def test_none_result_is_ignored(self):
        got = merge([(PRIORITY_SEARCH, None),
                     (PRIORITY_PUBLIC_DB, ContactFields(tel="03-1", source="A"))])
        self.assertEqual(got.tel, "03-1")


class TestWorstConfidence(unittest.TestCase):
    def test_order(self):
        self.assertEqual(worst_confidence([CONF_CONFIRMED, CONF_CANDIDATE]), CONF_CANDIDATE)
        self.assertEqual(worst_confidence([CONF_CANDIDATE, CONF_UNKNOWN]), CONF_UNKNOWN)
        self.assertEqual(worst_confidence([CONF_CONFIRMED]), CONF_CONFIRMED)
        self.assertEqual(worst_confidence([]), CONF_UNKNOWN)
        self.assertEqual(worst_confidence(["でたらめ"]), CONF_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
