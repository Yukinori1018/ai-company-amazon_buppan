# -*- coding: utf-8 -*-
"""正規化ルールのテスト。

ケースはすべて **822行の実データに実在する文字列**（または55社実績の文字列）。
架空の例で通しても意味がないので、実物だけを入れている。
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.normalize import (  # noqa: E402
    canonicalize_legal_form,
    classify,
    extract_variants,
    match_key,
    normalize_row,
    split_scripts,
    strip_invisible,
    strip_legal_form,
    duplicate_groups,
)
from pipeline.schema import (  # noqa: E402
    CLS_EN_BRAND,
    CLS_FOREIGN,
    CLS_JP_CORP,
    CLS_NOBRAND,
)


class TestStripInvisible(unittest.TestCase):
    def test_removes_ltr_mark(self):
        # 実データ: '‎バーベイタム(Verbatim)'
        self.assertEqual(
            strip_invisible("‎バーベイタム(Verbatim)"), "バーベイタム(Verbatim)"
        )

    def test_nfkc_widens_zenkaku_alnum(self):
        # 実データ: 'ＡＮＤＥＲＹ' 'Ｌａｚｙｍｅ' 'ＹＡＺＡＫＩ'
        self.assertEqual(strip_invisible("ＡＮＤＥＲＹ"), "ANDERY")
        self.assertEqual(strip_invisible("Ｌａｚｙｍｅ"), "Lazyme")

    def test_nfkc_expands_kabushiki_ligature(self):
        # 実データ: '矢崎エナジーシステム㈱'
        self.assertEqual(strip_invisible("矢崎エナジーシステム㈱"), "矢崎エナジーシステム(株)")

    def test_collapses_stray_spaces(self):
        # 実データ: 'ワー ナー・ブ ラザース…' は空白が紛れ込んでいる
        self.assertEqual(strip_invisible("  A   B  "), "A B")

    def test_none_and_empty(self):
        self.assertEqual(strip_invisible(None), "")
        self.assertEqual(strip_invisible(""), "")


class TestLegalForm(unittest.TestCase):
    def test_abbrev_becomes_full_form(self):
        self.assertEqual(
            canonicalize_legal_form(strip_invisible("矢崎エナジーシステム㈱")),
            "矢崎エナジーシステム株式会社",
        )

    def test_space_after_legal_form_is_closed(self):
        # 実データ: '株式会社 山本人形'
        self.assertEqual(canonicalize_legal_form("株式会社 山本人形"), "株式会社山本人形")

    def test_position_is_preserved(self):
        # 前株・後株を勝手に入れ替えない
        self.assertEqual(canonicalize_legal_form("株式会社マーベラス"), "株式会社マーベラス")
        self.assertEqual(canonicalize_legal_form("イースター株式会社"), "イースター株式会社")

    def test_strip_legal_form_japanese(self):
        self.assertEqual(strip_legal_form("株式会社マーベラス"), "マーベラス")
        self.assertEqual(strip_legal_form("イースター株式会社"), "イースター")

    def test_strip_legal_form_foreign(self):
        # 実データ: 'ZHONGSHAN TURBOS TECHNOLOGY CO.,LTD'
        self.assertEqual(
            strip_legal_form("ZHONGSHAN TURBOS TECHNOLOGY CO.,LTD"),
            "ZHONGSHAN TURBOS TECHNOLOGY",
        )


class TestExtractVariants(unittest.TestCase):
    def test_japanese_outside_latin_inside(self):
        primary, aliases = extract_variants("パナソニック(Panasonic)")
        self.assertEqual(primary, "パナソニック")
        self.assertIn("Panasonic", aliases)

    def test_latin_outside_japanese_inside(self):
        primary, aliases = extract_variants("CASIO(カシオ)")
        self.assertEqual(primary, "CASIO")
        self.assertIn("カシオ", aliases)

    def test_space_before_paren(self):
        # 実データ: 'Eufy (ユーフィ)' — 括弧前の空白が残らないこと
        primary, aliases = extract_variants("Eufy (ユーフィ)")
        self.assertEqual(primary, "Eufy")
        self.assertIn("ユーフィ", aliases)

    def test_paren_is_not_always_a_translation(self):
        # 実データ: 'NBCユニバーサル…(LAQ)' — LAQ は訳語ではないが別名として保持する
        primary, aliases = extract_variants(
            "NBCユニバーサル・エンターテイメントジャパン(LAQ)"
        )
        self.assertEqual(primary, "NBCユニバーサル・エンターテイメントジャパン")
        self.assertIn("LAQ", aliases)

    def test_slash_keeps_first_as_primary(self):
        # 実データ: 'OM SYSTEM/オリンパス'
        primary, aliases = extract_variants("OM SYSTEM/オリンパス")
        self.assertEqual(primary, "OM SYSTEM")
        self.assertIn("オリンパス", aliases)

    def test_slash_with_spaces(self):
        # 実データ: 'Ligare / ノーブランド品'
        primary, aliases = extract_variants("Ligare / ノーブランド品")
        self.assertEqual(primary, "Ligare")
        self.assertIn("ノーブランド品", aliases)

    def test_invisible_char_is_dropped_from_primary(self):
        primary, _ = extract_variants("‎バーベイタム(Verbatim)")
        self.assertEqual(primary, "バーベイタム")


class TestSplitScripts(unittest.TestCase):
    def test_splits_on_script_boundary_not_words(self):
        # 55社実績: 'アストロプロダクツ Astro Products'
        # 単語で割ると 'Products' が 'P&S Detailing Products' に誤マッチする（実際に踏んだ）
        self.assertEqual(
            split_scripts("アストロプロダクツ Astro Products"),
            ["アストロプロダクツ", "Astro Products"],
        )

    def test_single_script_returns_nothing(self):
        self.assertEqual(split_scripts("UGREEN"), [])
        self.assertEqual(split_scripts("マキタ"), [])


class TestMatchKey(unittest.TestCase):
    def test_case_and_symbol_insensitive(self):
        # 実データ: 'マキタ(Makita)' と 'Makita(マキタ)' は同じ会社
        self.assertEqual(match_key("Makita"), match_key("makita"))
        self.assertEqual(match_key("MAKITA"), match_key("Makita"))

    def test_nakaguro_variants_collapse(self):
        # 実データ: 'ジャニーズ･エンタテイメント' vs 'ジャニーズ・エンタテイメント'
        self.assertEqual(
            match_key("ジャニーズ･エンタテイメント"),
            match_key("ジャニーズ・エンタテイメント"),
        )

    def test_legal_form_ignored(self):
        # 実データ: 'イースター株式会社' と 'イースター' は同じ会社
        self.assertEqual(match_key("イースター株式会社"), match_key("イースター"))

    def test_zenkaku_latin_collapses(self):
        self.assertEqual(match_key("ＹＡＺＡＫＩ"), match_key("YAZAKI"))

    def test_different_companies_stay_different(self):
        self.assertNotEqual(match_key("マキタ"), match_key("マキタ電機"))
        self.assertNotEqual(match_key("Anker"), match_key("Ankermake"))


class TestClassify(unittest.TestCase):
    def test_nobrand_wins_first(self):
        self.assertEqual(classify("ノーブランド品", []), CLS_NOBRAND)
        # 実データ: '株式会社' だけの行（社名が入っていない）
        self.assertEqual(classify("株式会社", []), CLS_NOBRAND)

    def test_foreign_legal_form(self):
        self.assertEqual(
            classify("ZHONGSHAN TURBOS TECHNOLOGY CO.,LTD", []), CLS_FOREIGN
        )
        self.assertEqual(classify("Shenzhen Xing Yuan Technology Co., Ltd", []), CLS_FOREIGN)

    def test_japanese_name(self):
        self.assertEqual(classify("パナソニック", ["Panasonic"]), CLS_JP_CORP)
        self.assertEqual(classify("株式会社マーベラス", []), CLS_JP_CORP)

    def test_latin_outside_but_japanese_alias_is_still_jp(self):
        # 'CASIO(カシオ)' は日本企業。和名別名があれば和名扱いに寄せる
        self.assertEqual(classify("CASIO", ["カシオ"]), CLS_JP_CORP)

    def test_pure_latin_brand(self):
        self.assertEqual(classify("UGREEN", []), CLS_EN_BRAND)
        self.assertEqual(classify("Anker", []), CLS_EN_BRAND)


class TestNormalizeRow(unittest.TestCase):
    def test_end_to_end(self):
        row = normalize_row("‎バーベイタム(Verbatim)", {"該当商品数": "3"})
        self.assertEqual(row.raw_name, "‎バーベイタム(Verbatim)")  # 生は保つ
        self.assertEqual(row.normalized_name, "バーベイタム")
        self.assertEqual(row.category, CLS_JP_CORP)
        self.assertIn(match_key("Verbatim"), row.match_keys)
        self.assertEqual(row.source_row["該当商品数"], "3")

    def test_duplicate_rows_share_a_match_key(self):
        # 実データの重複ペア: 'LEGO(レゴ)' と 'レゴ(LEGO)'
        a = normalize_row("LEGO(レゴ)")
        b = normalize_row("レゴ(LEGO)")
        self.assertTrue(set(a.match_keys) & set(b.match_keys))

    def test_core_name_drops_legal_form(self):
        self.assertEqual(normalize_row("イースター株式会社").core_name, "イースター")


class TestDuplicateGroups(unittest.TestCase):
    def test_finds_real_duplicate_pairs(self):
        # 実データ中の取りこぼしペア
        rows = [normalize_row(n) for n in
                ["LEGO(レゴ)", "レゴ(LEGO)", "UGREEN",
                 "イースター株式会社", "イースター"]]
        groups = duplicate_groups(rows)
        self.assertIn(["LEGO(レゴ)", "レゴ(LEGO)"], groups)
        self.assertIn(["イースター株式会社", "イースター"], groups)
        self.assertEqual(len(groups), 2)   # UGREEN は単独

    def test_no_groups_when_all_distinct(self):
        rows = [normalize_row(n) for n in ["UGREEN", "Anker", "CIO"]]
        self.assertEqual(duplicate_groups(rows), [])


if __name__ == "__main__":
    unittest.main()
