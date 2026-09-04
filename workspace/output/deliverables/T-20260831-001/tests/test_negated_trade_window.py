#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A1_trade_window の否定形誤爆の検知テスト。

**なぜ要るのか。**
法務ルール v1.0 の `A1_trade_window` は「新規お取引」「卸売」「代理店」「OEM」等を
**肯定の取引窓口シグナル**として拾うが、規則に右辺（否定語）が無い。
そのため次のように意味が正反対に転ぶ。

    「新規お取引は行っておりません」          → A_PLUS（最優先で打診）
    「海外代理店への販売のみ」（＝直販しない）→ A_PLUS

**打診してはいけない相手が、最優先で打診すべき相手に化ける**方向の誤りで、
実際に社長が間違った相手に連絡してしまう。「取れなかった」より悪い。

前任が2026-09-04 にキョーリンで踏み、私が第2走行でブラザー・ジョルダン社で踏んだ。
2回踏んでいるので、テストで固定する。

**この検知器はクラスを決めない。** 判定基準の所有者は法務ハルオであり、
検知器の役割は「ルールに穴がある」と人に知らせるところまで。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.optout import classify_window, detect_negated_trade_window  # noqa: E402


# --- 実在ページの原文で固定する（期待値は作り話にしない） -------------------

#: ブラザー・ジョルダン社 https://www.brjordan.com/contact-2/ （2026-09-04 確認）
BRJORDAN = (
    "尚、誠に勝手ながら以下の業種、業態の企業・店舗様との新規お取引は行っておりません。"
    "ご了承のほどお願い申し上げます。・WEBでの販売のみの企業様"
    "・小売以外のスタイルで店舗展開をされている企業様"
    "・グループ法人内で幼稚園や保育園を運営されている企業様"
)

#: キョーリン（前任が踏んだ実例）
KYORIN = "海外代理店への販売のみとなります。"


def test_法務ルール単体ではブラザージョルダンをA_PLUSと誤判定する():
    """**現状の欠陥を明示的に固定する。** 直ったらこのテストが落ちて気づける。

    法務ルールJSONは法務の所有物なので私が直すことはできない。
    だからこそ「今はこう誤る」を書き残して、検知器で補っていることを示す。
    """
    r = classify_window(BRJORDAN, "https://www.brjordan.com/contact-2/")
    assert r["optout_class"] == "A_PLUS"
    assert "A1_trade_window" in r["optout_rule_ids"]


def test_検知器がブラザージョルダンの否定を捕まえる():
    r = classify_window(BRJORDAN, "https://www.brjordan.com/contact-2/")
    hit = detect_negated_trade_window(BRJORDAN, r["optout_hit_terms"])
    assert hit is not None, "A_PLUS への誤爆を検知できていない"
    term, ng, excerpt = hit
    assert ng == "行っておりません"
    assert term in excerpt


def test_検知器がキョーリン型の限定表現を捕まえる():
    r = classify_window(KYORIN, "https://www.kyorin-net.co.jp/")
    hit = detect_negated_trade_window(KYORIN, r["optout_hit_terms"])
    assert hit is not None
    assert hit[1] == "のみ"


# --- 誤爆させないこと（本物の取引窓口を潰したら本末転倒） -------------------

def test_本物の取引窓口は検知しない_タカギ():
    notice = "会社名 株式会社タカギ 電話番号 048-615-3551（受注センター） メールアドレス b2b@takagi.co.jp"
    r = classify_window(notice, "https://hi-business.takagi.co.jp/corporate.php")
    if r["optout_class"] == "A_PLUS":
        assert detect_negated_trade_window(notice, r["optout_hit_terms"]) is None


def test_本物の取引窓口は検知しない_曙産業():
    notice = ("お客様の仕様に従った製品（ＯＥＭ製品）の開発設計も承っております。"
              "既製品の少量から大量受注も承ります。")
    r = classify_window(notice, "https://webdb.tsjiba.or.jp/")
    assert detect_negated_trade_window(notice, r["optout_hit_terms"]) is None


def test_本物の取引窓口は検知しない_トキワ商事():
    notice = "おもちゃの卸全般ご相談下さい 個人でも取引できるの？ 初めての取引の場合はどうするの？"
    r = classify_window(notice, "https://www.tokiwatoy.com/")
    assert detect_negated_trade_window(notice, r["optout_hit_terms"]) is None


# --- 境界 -------------------------------------------------------------

def test_否定語が遠ければ検知しない():
    """別の文の否定を巻き込まないこと。直後だけを見る設計の確認。"""
    notice = "卸売のご相談はこちらの窓口へお願いします。" + "あ" * 40 + "なお採用に関するご連絡はお受けしておりません。"
    assert detect_negated_trade_window(notice, "卸売") is None


def test_ヒット語が空なら何も返さない():
    assert detect_negated_trade_window(BRJORDAN, "") is None
    assert detect_negated_trade_window("", "卸売") is None


def test_複数ヒット語のうち1つでも否定されていれば返す():
    notice = "卸売のご相談はこちら。なお代理店の募集は行っておりません。"
    hit = detect_negated_trade_window(notice, "卸売;代理店")
    assert hit is not None
    assert hit[0] == "代理店"
