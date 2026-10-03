#!/usr/bin/env python3
"""判定ロジックのテスト。ネットワークもトークンも使いません。

    python3 test_verdict.py

ここで守っているのは1点だけです: **GO が甘くならないこと。**
「本体が居るのに GO」と「データが無いのに GO」を、両方とも落とします。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verdict import (AMAZON_JP_SELLER_ID, FAIL, GO, NO_GO, PASS, UNKNOWN,  # noqa: E402
                     judge, judge_missing)

THIRD = "A10QAH1G3NV06L"


def product(*, bb_is_amazon=False, bb_seller=THIRD, bb_hist_last=THIRD,
            oos365=100, oos90=100, offer_sellers=(THIRD,), buybox_stats=None,
            count_new=None, live=True):
    """テスト用の Keepa product を組み立てる。既定は「きれいな GO 候補」。"""
    offers = [{"sellerId": s, "condition": 1, "isFBA": True, "isAmazon": s == AMAZON_JP_SELLER_ID}
              for s in offer_sellers]
    cur = [-1] * 36
    cur[11] = len(offers) if count_new is None else count_new
    oos_arr365 = [-1] * 36
    oos_arr365[0] = oos365
    oos_arr90 = [-1] * 36
    oos_arr90[0] = oos90
    return {
        "asin": "B0TEST00001", "title": "テスト商品",
        "offers": offers,
        "liveOffersOrder": list(range(len(offers))) if live else None,
        "buyBoxSellerIdHistory": ["7000000", bb_hist_last] if bb_hist_last else [],
        "stats": {
            "buyBoxIsAmazon": bb_is_amazon, "buyBoxSellerId": bb_seller,
            "outOfStockPercentage365": oos_arr365, "outOfStockPercentage90": oos_arr90,
            "buyBoxStats": buybox_stats or {THIRD: {"percentageWon": 99.0}},
            "current": cur,
        },
    }


class TestGo(unittest.TestCase):
    def test_clean_third_party_is_go(self):
        j = judge(product())
        self.assertEqual(j.verdict, GO)
        self.assertTrue(all(c.status == PASS for c in j.checks))


class TestCartHolder(unittest.TestCase):
    def test_buybox_is_amazon_flag(self):
        j = judge(product(bb_is_amazon=True, bb_seller=AMAZON_JP_SELLER_ID,
                          bb_hist_last=AMAZON_JP_SELLER_ID))
        self.assertEqual(j.verdict, NO_GO)
        self.assertIn("Amazon.co.jp", j.cart_holder)

    def test_single_evidence_says_amazon_is_enough_to_fail(self):
        """根拠が1本でも AMAZON を指したら FAIL。多数決にしない（2026-09-30 の事故）。"""
        j = judge(product(bb_hist_last=AMAZON_JP_SELLER_ID))
        self.assertEqual(j.verdict, NO_GO)

    def test_conflicting_evidence_is_unknown_not_go(self):
        j = judge(product(bb_seller="-2", bb_hist_last=None))
        self.assertEqual(j.verdict, UNKNOWN)

    def test_amazon_won_majority_of_window_is_no_go(self):
        """期間の**過半**を本体が取っていれば、実質「本体の棚」＝NO-GO。"""
        j = judge(product(buybox_stats={THIRD: {"percentageWon": 40.0},
                                        AMAZON_JP_SELLER_ID: {"percentageWon": 60.0}}))
        self.assertEqual(j.verdict, NO_GO)

    def test_amazon_won_minority_of_window_is_not_no_go(self):
        """🔴 2026-10-04 に変えたところ。

        旧実装は「期間中に本体が **1%** でもカートを取っていたら NO-GO」でした。
        §3.3-1 が禁じているのは「**本体がカートを持つ棚への発注**」であって、
        本体が出入りしていることではありません。実測では 1.7〜2.7% の行が多数あり、
        それらは**第三者が98%以上カートを持っている棚**でした。
        落とさず、注記だけ残します。
        """
        j = judge(product(buybox_stats={THIRD: {"percentageWon": 98.1},
                                        AMAZON_JP_SELLER_ID: {"percentageWon": 1.9}}))
        self.assertEqual(j.verdict, GO)
        self.assertIn("⚠️", j.checks[0].reason)

    def test_only_one_known_evidence_is_unknown(self):
        p = product(bb_hist_last=None)
        p["stats"]["buyBoxIsAmazon"] = None
        p["stats"]["buyBoxSellerId"] = "-1"
        self.assertEqual(judge(p).verdict, UNKNOWN)


class TestStockHistory(unittest.TestCase):
    """🔴 2026-10-04: チェック2 は**補助情報**に格下げしました。FAIL を出しません。

    本体が在庫を持っていることと、本体がカートを取っていることは別です。
    実測（N=648）で、**本体あり373件のうち295件（79%）はカートを第三者が持っていました。**
    落とす判断はチェック1（カート保持者）だけが持ちます。
    """

    def test_amazon_had_stock_all_year_is_not_no_go(self):
        j = judge(product(oos365=0, oos90=0))
        self.assertEqual(j.verdict, GO)
        self.assertNotEqual(j.checks[1].status, FAIL)

    def test_stock_history_is_still_reported(self):
        """落とさないが、**数字は消さない**（報告の列と実画面確認に使う）。"""
        j = judge(product(oos365=0, oos90=0))
        self.assertEqual(j.checks[1].evidence["amazon_instock_365_pct"], 100.0)
        self.assertIn("100.0%", j.checks[1].reason)

    def test_recent_stock_is_not_no_go(self):
        j = judge(product(oos365=99, oos90=50))
        self.assertEqual(j.verdict, GO)

    def test_missing_oos_is_unknown(self):
        """取れなかったものは今も UNKNOWN。§3.3 の「1つでも未確認なら提案しない」は残す。"""
        j = judge(product(oos365=-1))
        self.assertEqual(j.verdict, UNKNOWN)

    def test_small_trace_passes(self):
        j = judge(product(oos365=99, oos90=100))
        self.assertEqual(j.verdict, GO)
        self.assertIn("1.0%", j.checks[1].reason)


class TestOfferListing(unittest.TestCase):
    """🔴 2026-10-04: チェック3 も**補助情報**に格下げ。FAIL を出しません。"""

    def test_amazon_in_offer_list_is_not_no_go(self):
        """本体が1本出品していても、カートが第三者なら落とさない。"""
        j = judge(product(offer_sellers=(THIRD, AMAZON_JP_SELLER_ID)))
        self.assertEqual(j.verdict, GO)
        self.assertNotEqual(j.checks[2].status, FAIL)
        self.assertTrue(j.checks[2].evidence["amazon_among_sellers"])
        self.assertIn("Amazon 本体が混ざっています", j.checks[2].reason)

    def test_truncated_list_is_not_unknown_but_noted(self):
        """打ち切りは**セラー数の精度**の話で、カート保持者の判定には関係しない。"""
        j = judge(product(offer_sellers=tuple(f"S{i:011d}" for i in range(20)),
                          count_new=25), offers_requested=20)
        self.assertEqual(j.verdict, GO)
        self.assertIn("下限値", j.checks[2].reason)

    def test_missing_offers_is_unknown(self):
        j = judge(product(live=False))
        self.assertEqual(j.verdict, UNKNOWN)

    def test_duplicate_seller_counted_once(self):
        j = judge(product(offer_sellers=(THIRD, THIRD)))
        self.assertEqual(j.checks[2].evidence["distinct_sellers"], 1)
        self.assertEqual(j.checks[2].evidence["live_new_offer_count"], 2)


class TestMissing(unittest.TestCase):
    def test_product_not_returned_is_unknown(self):
        self.assertEqual(judge_missing("B0NOTFOUND").verdict, UNKNOWN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
