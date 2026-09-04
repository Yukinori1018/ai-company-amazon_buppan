# -*- coding: utf-8 -*-
"""住所の部屋番号だけを落とす処理のテスト。

このテストの主眼は「落とせること」ではなく、**落としすぎないこと**にある。
`\\d+号` を雑に拾うと「2丁目5番1号」が壊れ、
伏せ字どころか**住所が別の場所になる**。それは公開より悪い。
"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from redact import strip_unit_number, has_unit_number, MARK  # noqa: E402


# --- 落とすもの ---------------------------------------------------------
@pytest.mark.parametrize("src,expected_hit", [
    ("大阪市浪速区難波中2-4-12 ティタカラナビル303号室", "303号室"),
    ("新宿区西新宿6丁目15番1号 ラ・トゥール新宿609号室", "609号室"),
    ("中央区京橋 天翔オフィス734号室", "734号室"),
    ("○○ビル 5階501号", "5階501号"),
    ("○○ビル5F-501", "5F-501"),
    ("○○ Building Room 302", "Room 302"),
])
def test_部屋番号は落とす(src, expected_hit):
    out, removed = strip_unit_number(src, address_field=True)
    assert removed == [expected_hit], "落とした語が想定と違う: %r" % removed
    assert expected_hit not in out
    assert MARK in out


@pytest.mark.parametrize("src,hit", [
    ("2605 Camino Tassajara #2594, Danville, CA 94526", "#2594"),
    ("1234 Main St, Suite 250, Springfield", "Suite 250"),
    ("500 Oak Ave Unit 12B", "Unit 12B"),
])
def test_海外の区画番号も住所欄なら落とす(src, hit):
    out, removed = strip_unit_number(src, address_field=True)
    assert removed == [hit]
    assert hit not in out


# --- 落としてはいけないもの（本命） -------------------------------------
@pytest.mark.parametrize("src", [
    "東京都千代田区丸の内1丁目2番3号",          # 「1号」は地番。住所の一部
    "新宿区西新宿6丁目15番1号",
    "東京都千代田区丸の内1-2-3 第1号館",         # 「1号館」は建物名
    "〒105-5515 東京都港区虎ノ門2-6-1 虎ノ門ヒルズステーションタワー15階",  # 階は残す
    "〒541-8765 大阪市中央区伏見町4-1-1 明治安田生命大阪御堂筋ビル9F",       # F も残す
    "〒141-0031 東京都品川区西五反田2丁目15-7 ジブラルタ生命五反田ビル1F",
])
def test_住所の一部と階は絶対に落とさない(src):
    out, removed = strip_unit_number(src, address_field=True)
    assert removed == [], "落としてはいけないものを落とした: %r" % removed
    assert out == src, "住所が書き換わっている: %r" % out


def test_自由文では番号記号を拾わない():
    """`#` は Python のコメントや Markdown の見出しで大量に出る。
    住所欄と宣言されていない限り拾わない。"""
    src = "# 2594 件を処理した"
    out, removed = strip_unit_number(src, address_field=False)
    assert removed == []
    assert out == src


def test_自由文でも号室は拾う():
    """備考欄に住所が引用されている場合がある（実際にあった）。"""
    src = "本店所在地が3回変わっている(2019年 天翔オフィス734号室→2022年 港区)"
    out, removed = strip_unit_number(src, address_field=False)
    assert removed == ["734号室"]
    assert "734号室" not in out


def test_空文字とNoneで落ちない():
    assert strip_unit_number("") == ("", [])
    assert strip_unit_number(None) == (None, [])


def test_複数の部屋番号を全部落とす():
    src = "A棟101号室 と B棟202号室"
    out, removed = strip_unit_number(src, address_field=True)
    assert removed == ["101号室", "202号室"]
    assert "101" not in out and "202" not in out


def test_二回かけても結果が変わらない():
    """伏せ字は冪等でないと、再ビルドのたびに壊れていく。"""
    src = "大阪市浪速区難波中2-4-12 ティタカラナビル303号室"
    once, _ = strip_unit_number(src, address_field=True)
    twice, removed2 = strip_unit_number(once, address_field=True)
    assert twice == once
    assert removed2 == []


def test_has_unit_number():
    assert has_unit_number("○○ビル303号室")
    assert not has_unit_number("○○ビル3階")


# --- 型番・品番・脚注を壊さないこと（2026-09-04 に実際に壊した） -------
@pytest.mark.parametrize("src", [
    "Arrows We2 F-52E 用 ケース 財布型 F-52E/FCG02 カバー",      # スマホの型番
    "GIVI(ジビ) バイク用 タンクロック 補修用 フランジ オス ZT480F-2 98632",  # 品番
    "キャンピングムーン IGT用 天板 アルミ 2ユニット 25F-2",
    "**[#42]** Amazonジャパンは2019年、任天堂・パナソニック等25社と",   # Markdown の脚注
    "notes[#121]、「古物」の定義",
    "# 2594 件を処理した",                                     # Python のコメント
    "ご購入方法の相談は #3058 まで",
])
def test_自由文では型番と脚注を壊さない(src):
    """全文に F-数字 や #数字 を当てて商品名を壊した事故の再発防止。
    住所欄と宣言されていない文字列は、号室系しか触らない。"""
    out, removed = strip_unit_number(src, address_field=False)
    assert removed == [], "自由文で落としてはいけないものを落とした: %r" % removed
    assert out == src
