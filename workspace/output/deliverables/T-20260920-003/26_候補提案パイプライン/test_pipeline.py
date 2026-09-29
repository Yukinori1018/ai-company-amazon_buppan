#!/usr/bin/env python3
"""ネットワーク不要のテスト。`python3 test_pipeline.py` で全部走ります。

重点は依頼どおり2つです。
  1. **メーカー直販の検出** — 2026-09-30 に実画面で判定が覆った B0FN3NWKYZ を機械で拾えるか
  2. **冪等性** — 既にシートにある ASIN を二度書かないか
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import candidate_pipeline as pipe   # noqa: E402
import ledger_sheet                 # noqa: E402
import maker_direct as md           # noqa: E402
import profit                       # noqa: E402
from verdict import GO, NO_GO, UNKNOWN  # noqa: E402


class TestMakerDirect(unittest.TestCase):
    """§3.3 の5番目。**カート保持者がメーカー本人なら NO-GO。**"""

    def test_sanwa_direct_is_fail(self):
        """実例: B0FN3NWKYZ。機械の3点チェックは GO だったが、カートはメーカー本人だった。"""
        status, reason, ev = md.detect_maker_direct(
            brand="サンワダイレクト", manufacturer="サンワサプライ",
            cart_seller_name="サンワサプライ直営【サンワダイレクト】",
            live_offer_count=1)
        self.assertEqual(status, md.FAIL)
        self.assertIn("サンワダイレクト", ev["cart_seller_name"])
        self.assertIn("メーカー", reason)

    def test_third_party_reseller_passes(self):
        """実例: B0DJNX12KZ。不二貿易の商品を Mr.＆Mrs. Store が売っている＝第三者。"""
        status, _r, _e = md.detect_maker_direct(
            brand="不二貿易(Fujiboeki)", manufacturer="不二貿易",
            cart_seller_name="Mr.＆Mrs. Store", live_offer_count=2)
        self.assertEqual(status, md.PASS)

    def test_brand_name_in_seller_name_is_fail(self):
        status, _r, _e = md.detect_maker_direct(
            brand="ぺんてる", manufacturer="ぺんてる株式会社",
            cart_seller_name="ぺんてる公式ストア", live_offer_count=5)
        self.assertEqual(status, md.FAIL)

    def test_romaji_variant_matches(self):
        """「不二貿易(Fujiboeki)」の併記は両方が鍵になる。"""
        status, _r, _e = md.detect_maker_direct(
            brand="不二貿易(Fujiboeki)", manufacturer="",
            cart_seller_name="FUJIBOEKI official shop", live_offer_count=3)
        self.assertEqual(status, md.FAIL)

    def test_official_word_without_brand_match_is_unknown(self):
        """「公式」を名乗るが、どのブランドの公式かは機械では確信できない → 人が見る。"""
        status, reason, _e = md.detect_maker_direct(
            brand="アイリスオーヤマ", manufacturer="アイリスオーヤマ",
            cart_seller_name="くらし雑貨 公式ストア", live_offer_count=4)
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("実画面", reason)

    def test_single_offer_unknown_when_name_does_not_match(self):
        """オファー1社は「有利」ではない。ブランド一致しなくても UNKNOWN に落とす。"""
        status, _r, _e = md.detect_maker_direct(
            brand="SOLCION", manufacturer="ソルシオン",
            cart_seller_name="みどり商店", live_offer_count=1)
        self.assertEqual(status, md.UNKNOWN)

    def test_single_offer_with_brand_match_in_other_names_is_fail(self):
        status, _r, _e = md.detect_maker_direct(
            brand="グンゼ", manufacturer="GUNZE", cart_seller_name="",
            live_offer_count=1, other_seller_names=["グンゼ直営オンライン"])
        # カート名が空なので UNKNOWN（名前が取れないものは GO にしない）
        self.assertEqual(status, md.UNKNOWN)

    def test_no_seller_name_is_never_pass(self):
        """名前が取れないことを「直販ではない」の根拠にしない（9/30 の事故と同型）。"""
        for count in (None, 1, 5):
            status, _r, _e = md.detect_maker_direct("ブランド", "メーカー", None, count)
            self.assertEqual(status, md.UNKNOWN)

    def test_normalize_strips_corporate_forms(self):
        self.assertEqual(md.normalize("株式会社 不二貿易"), "不二貿易")
        self.assertEqual(md.normalize("ＡＢＣ　Ｃｏ.,Ltd."), "abc")

    def test_short_ascii_key_does_not_false_match(self):
        """短い英字の偶然一致を避ける（"ism" が "PRISM" に当たらない）。"""
        keys = md.brand_keys("ISM")
        self.assertIsNone(md.matched_brand_key("PRISM Trading", keys))
        self.assertIsNotNone(md.matched_brand_key("ISM", keys))


class TestCombine(unittest.TestCase):
    """UNKNOWN を GO に畳まないこと。"""

    def test_maker_fail_overrides_go(self):
        self.assertEqual(pipe.combine(GO, md.FAIL), NO_GO)

    def test_maker_unknown_downgrades_go(self):
        self.assertEqual(pipe.combine(GO, md.UNKNOWN), UNKNOWN)

    def test_all_pass_is_go(self):
        self.assertEqual(pipe.combine(GO, md.PASS), GO)

    def test_base_no_go_stays_no_go(self):
        self.assertEqual(pipe.combine(NO_GO, md.PASS), NO_GO)
        self.assertEqual(pipe.combine(UNKNOWN, md.PASS), UNKNOWN)

    def test_economics_fail_overrides_go(self):
        self.assertEqual(pipe.combine(GO, md.PASS, md.FAIL), NO_GO)
        self.assertEqual(pipe.combine(GO, md.PASS, md.UNKNOWN), UNKNOWN)


class TestEconomicsGate(unittest.TestCase):
    """カートが第三者でも、赤字・捌けない在庫は提案しない。"""

    def _e(self, **kw):
        base = dict(sell=2980, fee_pct=15.4, fba_yen=472, unit_cost_incl=1012,
                    qty=12, monthly_sold=10)
        base.update(kw)
        return profit.compute(**base)

    def test_healthy_is_pass(self):
        status, _r = pipe.economics_status(self._e(), 10)
        self.assertEqual(status, md.PASS)

    def test_loss_is_fail(self):
        status, reason = pipe.economics_status(self._e(unit_cost_incl=2500), 10)
        self.assertEqual(status, md.FAIL)
        self.assertIn("赤字", reason)

    def test_slow_turnover_is_fail(self):
        """最小ロットが大きく6ヶ月で捌けない在庫は NO-GO（社長既定）。"""
        status, reason = pipe.economics_status(self._e(qty=24, monthly_sold=2), 2)
        self.assertEqual(status, md.FAIL)
        self.assertIn("ヶ月", reason)

    def test_unknown_monthly_sold_does_not_block_go(self):
        """月販が取れないことを理由に落とさない（2026-09-30 カズヨ訂正・CLAUDE.md §3.1）。

        `monthlySold` は月50個未満だと表示されないだけ。社長が発注を決めた B0DJNX12KZ は
        キーゾン実測で月10個。落とすのは①本体カート②メーカー直販③赤字の3つだけ。
        """
        status, reason = pipe.economics_status(self._e(monthly_sold=None), None)
        self.assertEqual(status, md.PASS)
        self.assertIn("落としません", reason)

    def test_missing_economics_is_unknown(self):
        status, _r = pipe.economics_status(None, 10)
        self.assertEqual(status, md.UNKNOWN)


class TestProfit(unittest.TestCase):
    """成果物22・23 と1円も食い違わないこと。"""

    def test_fujiboeki_matches_ledger_row(self):
        """台帳の B0DJNX12KZ: 粗利991円・利益率33.3%・発注12,144円・半値処分損2,052円。"""
        e = profit.compute(sell=2980, fee_pct=15.4, fba_yen=472,
                           unit_cost_incl=1012, qty=12, monthly_sold=10)
        self.assertEqual(e.gross_per_unit, 991)
        self.assertEqual(e.margin_pct, 33.3)
        self.assertEqual(e.order_total, 12144)
        self.assertEqual(e.half_disposal_loss, 2052)
        self.assertEqual(e.months_to_sell, 1.2)

    def test_sanwa_matches_ledger_row(self):
        """台帳の B0FN3NWKYZ: 粗利1,770円・利益率29.6%・半値処分損5,910円。"""
        e = profit.compute(sell=5980, fee_pct=15.4, fba_yen=415,
                           unit_cost_incl=2782, qty=10, monthly_sold=7)
        self.assertEqual(e.gross_per_unit, 1770)
        self.assertEqual(e.margin_pct, 29.6)
        self.assertEqual(e.half_disposal_loss, 5910)

    def test_purchase_tax_is_an_expense(self):
        """免税事業者なので仕入消費税は費用。NETSEA の price は1個の値段（割らない）。"""
        self.assertEqual(profit.unit_cost_incl_tax(920), 1012)     # B0DJNX12KZ 台帳実額
        self.assertEqual(profit.unit_cost_incl_tax(2529), 2782)    # B0FN3NWKYZ 台帳実額
        self.assertEqual(profit.unit_cost_incl_tax(2098), 2308)    # B0171AC6PI 成果物22

    def test_referral_fee_uses_tax_inclusive_yen(self):
        self.assertEqual(profit.referral_fee_yen(2980, 15.4), 505)

    def test_order_qty_respects_six_month_cap(self):
        self.assertEqual(profit.order_qty(monthly_sold=100, pack=1), 10)   # 10点で足りる
        self.assertEqual(profit.order_qty(monthly_sold=1, pack=1), 6)      # 6ヶ月ぶんで打ち止め
        self.assertEqual(profit.order_qty(monthly_sold=100, pack=4), 12)   # ロットの倍数へ

    def test_other_unit_costs_flip_thin_margins(self):
        """保管料・納品送料・梱包資材（実測206円/個）を引くと沈む棚を落とす。

        2026-09-30、1個粗利72円・利益率2.1%の候補を GO として台帳に出しかけた。
        `gross_per_unit` は成果物22・23 と同じ定義のまま、`net_per_unit` を別に持つ。
        """
        e = profit.compute(sell=3492, fee_pct=15.4, fba_yen=500,
                           unit_cost_incl=2328, qty=10, monthly_sold=None)
        self.assertGreater(e.gross_per_unit, 0)
        self.assertEqual(e.other_unit_costs, 206)
        self.assertLess(e.net_per_unit, e.gross_per_unit)
        status, reason = pipe.economics_status(e, None)
        self.assertEqual(status, md.FAIL)
        self.assertIn("実質赤字", reason)

    def test_healthy_margin_survives_other_costs(self):
        e = profit.compute(sell=2980, fee_pct=15.4, fba_yen=472,
                           unit_cost_incl=1012, qty=12, monthly_sold=10)
        self.assertEqual(e.gross_per_unit, 991)       # 台帳と同じ（定義は変えない）
        self.assertEqual(e.net_per_unit, 785)
        self.assertEqual(pipe.economics_status(e, 10)[0], md.PASS)

    def test_margin_never_flattered(self):
        """赤字は赤字のまま返す（UI の都合で 0 に丸めない）。"""
        e = profit.compute(sell=1000, fee_pct=15.4, fba_yen=472,
                           unit_cost_incl=800, qty=10, monthly_sold=5)
        self.assertLess(e.gross_per_unit, 0)


class FakeWorksheet:
    """gspread の代わり。appended に追記されたものが残る。"""

    def __init__(self, values):
        self.values = [list(r) for r in values]
        self.appended: list[list] = []
        self.updated: list[tuple] = []

    def get_all_values(self):
        return [list(r) for r in self.values]

    def append_rows(self, rows, **_kw):
        self.appended.extend(rows)
        self.values.extend(rows)

    def update(self, rng, rows, **_kw):
        self.updated.append((rng, rows))


def _row(asin, verdict="GO", method=ledger_sheet.MACHINE_ONLY):
    row = [""] * len(ledger_sheet.COLUMNS)
    row[ledger_sheet.COL_ASIN] = asin
    row[ledger_sheet.COL_VERDICT] = verdict
    row[ledger_sheet.COL_METHOD] = method
    return row


class TestLedgerIdempotency(unittest.TestCase):

    def setUp(self):
        self.ws = FakeWorksheet([ledger_sheet.COLUMNS,
                                 _row("B00000001A", "GO"),
                                 _row("B00000002A", "NO-GO"),
                                 _row("B00000003A", "GO", "Chrome 実画面＋キーゾン")])

    def test_read_state_counts_only_machine_go(self):
        st = ledger_sheet.read_state(self.ws)
        self.assertEqual(st.total_rows, 3)
        self.assertEqual(st.machine_go_count, 1)        # 実画面確認済みの GO は数えない
        self.assertEqual(set(st.asins), {"B00000001A", "B00000002A", "B00000003A"})
        self.assertEqual(st.asins["B00000001A"], 2)     # ヘッダの次＝2行目

    def test_existing_asin_is_not_appended_twice(self):
        st = ledger_sheet.read_state(self.ws)
        incoming = [_row("B00000001A"), _row("B00000009A")]
        new = [r for r in incoming if r[ledger_sheet.COL_ASIN] not in st.asins]
        ledger_sheet.append_rows(new, self.ws)
        self.assertEqual(len(self.ws.appended), 1)
        self.assertEqual(self.ws.appended[0][ledger_sheet.COL_ASIN], "B00000009A")

    def test_human_verified_row_is_never_overwritten(self):
        """機械判定が人の実画面確認を潰さないこと（2026-09-30 に一度やった）。"""
        ws = FakeWorksheet([ledger_sheet.COLUMNS,
                            _row("B00000004A", "GO", "Chrome 実画面＋キーゾン")])
        st = ledger_sheet.read_state(ws)
        self.assertTrue(st.is_human_verified("B00000004A"))
        with self.assertRaises(ledger_sheet.HumanRowProtected):
            ledger_sheet.update_row(2, _row("B00000004A", "NO-GO"), ws, st)
        self.assertEqual(ws.updated, [])

    def test_machine_row_can_be_updated(self):
        st = ledger_sheet.read_state(self.ws)
        ledger_sheet.update_row(st.asins["B00000001A"], _row("B00000001A", "NO-GO"),
                                self.ws, st)
        self.assertEqual(len(self.ws.updated), 1)

    def test_update_existing_writes_in_place(self):
        st = ledger_sheet.read_state(self.ws)
        ledger_sheet.update_row(st.asins["B00000002A"], _row("B00000002A", "GO"), self.ws)
        self.assertEqual(self.ws.updated[0][0], "A3:AF3")
        self.assertEqual(len(self.ws.appended), 0)

    def test_column_drift_is_rejected(self):
        bad = FakeWorksheet([ledger_sheet.COLUMNS + ["余計な列"]])
        ledger_sheet.read_state(bad)                     # 末尾に増えているだけなら通す
        broken = FakeWorksheet([["ASIN"] + ledger_sheet.COLUMNS[1:]])
        with self.assertRaises(SystemExit):
            ledger_sheet.read_state(broken)

    def test_row_has_exactly_32_columns(self):
        self.assertEqual(len(ledger_sheet.COLUMNS), 32)
        self.assertEqual(len(_row("B00000001A")), 32)


class TestStopCondition(unittest.TestCase):

    def test_target_is_thirty_by_default(self):
        self.assertEqual(pipe.GO_TARGET, 30)

    def test_token_cap_limits_batch_size(self):
        """1回の実行で上限トークンを超えない件数しか取らない。"""
        self.assertEqual(pipe.MAX_KEEPA_TOKENS_PER_RUN // pipe.TOKENS_PER_ASIN, 25)


class TestPrioritize(unittest.TestCase):
    """同じトークンで GO が出やすい順に使う。"""

    def test_high_monthly_sold_first(self):
        import candidate_sources as cs
        pool = [cs.Candidate(asin="B0000000A1"),
                cs.Candidate(asin="B0000000A2", monthly_sold=50, unit_cost_incl=900),
                cs.Candidate(asin="B0000000A3", monthly_sold=400),
                cs.Candidate(asin="B0000000A4", unit_cost_incl=1000)]
        order = [c.asin for c in pipe.prioritize(pool)]
        # 月販も原価も揃っている A2 が最優先（A3 は月販が大きいが原価が無く GO になれない）
        self.assertEqual(order, ["B0000000A2", "B0000000A4", "B0000000A3", "B0000000A1"])


class TestRowBuilding(unittest.TestCase):
    """シートに出す1行。空欄を作らないこと（§3.2）。"""

    def test_no_empty_cells(self):
        import candidate_sources as cs
        from verdict import judge_missing

        cand = cs.Candidate(asin="B0TEST0001", title="テスト商品", brand="テスト")
        facts = {"title": "テスト商品", "brand": "テスト", "manufacturer": "",
                 "sell": None, "fee_pct": None, "fba_yen": None, "monthly_sold": None,
                 "cart_seller_id": None, "live_offer_count": None, "seller_ids": [],
                 "rank": None}
        row = pipe.build_row(cand, facts, judge_missing("B0TEST0001"),
                             (md.UNKNOWN, "セラー名が取れません。", {}), None, None,
                             "2026-09-30")
        self.assertEqual(len(row), 32)
        self.assertNotIn("", row)
        self.assertEqual(row[ledger_sheet.COL_VERDICT], UNKNOWN)
        self.assertEqual(row[ledger_sheet.COL_METHOD], ledger_sheet.MACHINE_ONLY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
