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
import set_count                    # noqa: E402
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


class TestSetCount(unittest.TestCase):
    """卸は「1点あたり」、Amazon は「N点セット」。**突き合わせの前に単位を揃える。**

    2026-09-30、B0DJNX12KZ（Amazon 側が2点セット）の原価を卸単価そのままで計算し、
    利益率33.3%・GO と出した。正しくは原価2倍で ▲181円/個。
    """

    def test_fujiboeki_two_piece_set(self):
        self.assertEqual(set_count.parse_amazon_set_count(
            "【2点セット】不二貿易 洗えるバスケット カトラリー収納 仕切り付き×2点セット"), 2)

    def test_single_item_is_one(self):
        for title in ("タテ・ヨコ伸縮式ソファカバー(クレア)肘付き右コーナーベージュ",
                      "ファミリー・ライフ キャビネット ホワイト 幅70×奥行32×高さ70cm",
                      "不二貿易(Fujiboeki) シューズラック 4段 幅63cm ブラウン 木製"):
            self.assertEqual(set_count.parse_amazon_set_count(title), 1, title)

    def test_capsule_count_is_not_a_set(self):
        """「600粒」は600セットではない。助数詞を白リストで持つ。"""
        self.assertEqual(set_count.parse_amazon_set_count(
            "オリヒロ 玉葱エキス粒 徳用 約60日分 600粒"), 1)

    def test_dimensions_are_not_a_set(self):
        """「幅30×奥行30×高さ45cm」の × を個数に読まない。"""
        self.assertEqual(set_count.parse_amazon_set_count(
            "不二貿易 座椅子 幅30×奥行30×高さ45cm ブルー スタッキング"), 1)

    def test_headset_is_not_a_set(self):
        """「ヘッドセット」の「セット」に反応しない（母数を静かに削る型のバグ）。"""
        self.assertEqual(set_count.parse_amazon_set_count(
            "エレコム ゲーミングヘッドセット 両耳オーバーヘッド PS5 PS4 Switch"), 1)

    def test_unreadable_set_is_none_not_one(self):
        """個数が読めないセット品は **1 と決め打たない**（原価をN分の1に見誤る）。"""
        self.assertIsNone(set_count.parse_amazon_set_count(
            "【まとめ買い】 スクラビングバブル 流せるトイレブラシ 本体+付け替え"))
        self.assertIsNone(set_count.parse_amazon_set_count("【2点セット】…×3点セット"))

    def test_company_name_is_not_a_set(self):
        """「富士パックス販売」の包丁を「個数不明のセット品」と読んでいた。"""
        self.assertEqual(set_count.parse_amazon_set_count(
            "富士パックス販売 トッププロダクツ 万能包丁 楽 TH-78 刃渡り17cm"), 1)

    def test_assembly_word_is_not_a_set(self):
        """「簡単組立」の「組」に反応しない。"""
        self.assertEqual(set_count.parse_amazon_set_count(
            "不二貿易(Fujiboeki) シューズラック 4段 幅63cm ブラウン 木製 簡単組立"), 1)

    def test_pcs_and_pair(self):
        self.assertEqual(set_count.parse_amazon_set_count(
            "[C/D:37189] [セット数:4pcs] アニマルドアストッパー"), 4)
        self.assertEqual(set_count.parse_amazon_set_count(
            "小倉陶器 ビアタンブラー 420ml ペアセット IE NOMI BEER"), 2)

    def test_large_multipacks(self):
        self.assertEqual(set_count.parse_amazon_set_count(
            "サンカ 芝の根止め レギュラー (幅16cm×高さ13.7cm) 【35枚組】 ブラック"), 35)

    def test_standalone_bags_count(self):
        self.assertEqual(set_count.parse_amazon_set_count(
            "ウルフピー4袋[オオカミ尿100％] WOLFPEE 動物除け"), 4)

    def test_multiplier_none_makes_economics_unknown(self):
        """倍率が読めなければ GO にしない（採算は UNKNOWN）。"""
        mult, note = set_count.cost_multiplier("【まとめ買い】お得パック")
        self.assertIsNone(mult)
        status, reason = pipe.economics_status(None, 10, note)
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("個数が読めません", reason)

    def test_set_count_flips_fujiboeki_to_loss(self):
        """B0DJNX12KZ: 原価2,024円/個で赤字。結論はカズヨの実画面確認と同じ。

        手数料の見方が3通りあり、**どれでも赤字**になります（結論は動きません）:
          15.4%（税抜のまま）      → 手数料459円 → 手残り ▲181円  ← カズヨの計算
          15%×1.1 = 16.5%          → 手数料492円 → 手残り ▲214円  ← カズヨの別案
          **15.4%×1.1 = 16.94%**   → 手数料505円 → 手残り ▲227円  ← 本実装
        本実装は「Keepa の率は税抜表示なので ×1.1 する」という当リポの既定
        （成果物22・23、商品台帳 L001）に合わせた**いちばん保守的な**読みです。
        """
        unit = profit.unit_cost_incl_tax(920) * 2          # 1,012 × 2点
        self.assertEqual(unit, 2024)
        e = profit.compute(sell=2980, fee_pct=15.4, fba_yen=472,
                           unit_cost_incl=unit, qty=12, monthly_sold=10)
        self.assertEqual(e.referral_fee_yen, 505)
        self.assertEqual(e.net_per_unit, -227)
        self.assertEqual(pipe.economics_status(e, 10)[0], md.FAIL)

        # 税抜のまま見てもやはり赤字（カズヨの ▲181円）。
        e2 = profit.compute(sell=2980, fee_pct=14.0, fba_yen=472,
                            unit_cost_incl=unit, qty=12, monthly_sold=10)
        self.assertLess(e2.net_per_unit, 0)

    def test_order_lot_converted_to_amazon_units(self):
        """卸が3点単位・Amazon が2点セット → Amazon 2個単位で発注（切り上げ）。"""
        self.assertEqual(set_count.order_lot_in_amazon_units(3, 2), 2)
        self.assertEqual(set_count.order_lot_in_amazon_units(12, 1), 12)


class TestLiveness(unittest.TestCase):
    """生存ゲート — **唯一の積極条件**（2026-09-30 カズヨの実画面確認を受けて新設）。

    それまでのゲートは全部が消極条件（地雷を踏んでいないこと）で、
    「売れている」という積極条件が1つも無かった。結果 **誰も売っていない棚だけが
    全部のゲートを通り抜けた**。GO 5件はキーゾン実測で3か月 0〜3個だった。
    """

    def test_dead_shelves_are_no_go(self):
        """カズヨが実画面で落とした5件の実ランク（90日平均）。すべて NO-GO になること。"""
        measured = {
            "B0DSR19X7T": (1_800_677, 1_645_738),   # 3か月 0個
            "B0DC4RTXG9": (1_362_072,   996_144),   # キーゾン表示なし
            "B0DCMVV58Q": (1_354_613,   989_263),   # 3か月 0個
            "B0BSDZ71YG": (  856_448,   680_355),   # 3か月 1個・856,448位
            "B08VWS9GHD": (1_196_088,   985_403),   # 3か月 3個
        }
        for asin, (now, avg90) in measured.items():
            status, reason = pipe.liveness_status(None, now, avg90)
            self.assertEqual(status, md.FAIL, asin)
            self.assertIn("実質ゼロ", reason)
            self.assertEqual(pipe.combine(GO, md.PASS, md.PASS, md.PASS, status), NO_GO)

    def test_real_seller_at_20k_rank_passes(self):
        """B0DJNX12KZ は **キーゾン実測で月10個**・ランク20,748位／90日平均24,150位。

        `monthlySold` は出ないが死んでいない。**ここを落とすと社長が発注を決めた実例が消える。**
        """
        status, _r = pipe.liveness_status(None, 20_748, 24_150)
        self.assertEqual(status, md.PASS)

    def test_monthly_sold_is_the_positive_evidence(self):
        status, reason = pipe.liveness_status(200, 2_978, 2_910)
        self.assertEqual(status, md.PASS)
        self.assertIn("実際に売れている", reason)

    def test_middle_band_is_unknown(self):
        """10万〜50万位は売れているとも死んでいるとも言えない → 人がキーゾンで見る。"""
        status, reason = pipe.liveness_status(None, 300_000, 300_000)
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("キーゾン", reason)

    def test_no_rank_is_unknown_not_pass(self):
        self.assertEqual(pipe.liveness_status(None, None, None)[0], md.UNKNOWN)

    def test_riser_is_unknown_not_no_go(self):
        """90日平均は圏外でも現在が上位なら、新規で伸びている途中かもしれない。"""
        status, _r = pipe.liveness_status(None, 20_689, 700_000)
        self.assertEqual(status, md.UNKNOWN)

    def test_zero_is_not_a_threshold(self):
        """「月100個以上」を緩めた話とは別物。**ゼロは何倍してもゼロ。**"""
        self.assertEqual(pipe.liveness_status(None, 1_800_677, 1_645_738)[0], md.FAIL)
        self.assertEqual(pipe.liveness_status(10, 1_800_677, 1_645_738)[0], md.PASS)

    def test_rank_prefix_is_always_written(self):
        self.assertEqual(pipe.rank_prefix(None, None), "【ランク なし】")
        self.assertIn("24,150位", pipe.rank_prefix(20_748, 24_150))


class TestSupplyReality(unittest.TestCase):
    """CLAUDE.md §3.3-6「仕入れが実在することを確認するまで GO にしない」。"""

    def _c(self, **kw):
        import candidate_sources as cs
        base = dict(asin="B0TEST0001", supplier_url="https://example.invalid/item/1")
        base.update(kw)
        return cs.Candidate(**base)

    def test_missing_supplier_url_is_unknown(self):
        """URL が無い＝在庫・入り数・卸値のどれも裏が取れていない（B0015XNJMW の型）。"""
        status, reason = pipe.supply_status(self._c(supplier_url=""), "ホーム＆キッチン")
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("裏が取れていない", reason)
        self.assertEqual(pipe.combine(GO, md.PASS, md.PASS, status), UNKNOWN)

    def test_supplier_url_present_passes(self):
        status, _r = pipe.supply_status(self._c(), "ホーム＆キッチン > 家具")
        self.assertEqual(status, md.PASS)

    def test_perishable_categories_need_date_management(self):
        """サプリ・食品・ドラッグストアは要期限管理で初回には不適。"""
        for cat in ("ドラッグストア > 栄養補助食品 > サプリメント",
                    "食品・飲料・お酒 > 食品",
                    "ドラッグストア"):
            status, reason = pipe.supply_status(self._c(), cat)
            self.assertEqual(status, md.UNKNOWN, cat)
            self.assertIn("要期限管理", reason)

    def test_perishable_beats_url_check(self):
        """URL があっても期限管理が要るなら GO にしない。"""
        status, reason = pipe.supply_status(self._c(), "ドラッグストア > サプリメント")
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("45日", reason)


class TestErrorBand(unittest.TestCase):
    """手残りが誤差幅を下回る行は GO にしない（UNKNOWN）。"""

    def _e(self, sell, cost):
        return profit.compute(sell=sell, fee_pct=15.4, fba_yen=472,
                              unit_cost_incl=cost, qty=10, monthly_sold=10)

    def test_band_applies_even_when_monthly_sold_unknown(self):
        """月販が不明でも誤差幅は効く。**順番の間違いでゲートが空振りしていた**（9/30）。"""
        e = self._e(2280, 1188)
        self.assertEqual(pipe.economics_status(e, None)[0], md.UNKNOWN)

    def test_thin_margin_is_unknown_not_go(self):
        """手残り28円の候補を GO として出した（2026-09-30）。誤差幅が結論を超えている。"""
        e = self._e(2280, 1188)                  # 手残り 28円・誤差幅 360円
        self.assertEqual(e.net_per_unit, 28)
        self.assertGreater(e.net_per_unit, 0)     # 赤字ではない。**読み切れていない**
        status, reason = pipe.economics_status(e, 10)
        self.assertEqual(status, md.UNKNOWN)
        self.assertIn("誤差幅", reason)

    def test_error_band_scales_with_price(self):
        """高額品は誤差幅も大きい（26,800円の売価で手残り355円は読み切れていない）。"""
        e = self._e(26800, 21000)
        band = round(26800 * pipe.ERROR_BAND_PCT / 100) + pipe.ERROR_BAND_FIXED
        self.assertGreater(band, 1800)
        self.assertGreater(e.net_per_unit, 0)
        self.assertLess(e.net_per_unit, band)
        self.assertEqual(pipe.economics_status(e, 10)[0], md.UNKNOWN)

    def test_healthy_margin_still_passes(self):
        e = self._e(2980, 1012)                  # 手残り785円・誤差幅409円
        self.assertEqual(pipe.economics_status(e, 10)[0], md.PASS)


class TestContentVolume(unittest.TestCase):
    """内容量は機械では突き合わせられないが、**人の目に入るようにする**（§3.3-7）。"""

    def test_supplement_volume(self):
        self.assertEqual(
            set_count.extract_content_volume("オリヒロ 玉葱エキス粒 徳用 約60日分 600粒"),
            "60日分 / 600粒")

    def test_dimensions_are_not_volume(self):
        """寸法（cm）や電気仕様（W/V/ルーメン）は内容量ではない。"""
        for title in ("ファミリー・ライフ キャビネット 幅70×奥行32×高さ70cm",
                      "サンワダイレクト LEDライト 作業灯 1300ルーメン 800-LED096BK"):
            self.assertEqual(set_count.extract_content_volume(title), "", title)

    def test_prefix_is_always_written(self):
        """表記が無い行も「表記なし」と書く（空欄を作らない・§3.2）。"""
        self.assertEqual(pipe.volume_prefix("ソファカバー 肘付き右コーナー"),
                         "【内容量 表記なし】")
        self.assertIn("600粒", pipe.volume_prefix("玉葱エキス粒 600粒"))


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
