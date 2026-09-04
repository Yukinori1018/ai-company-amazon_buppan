# -*- coding: utf-8 -*-
"""法務ルール v1.1 の engine_requirements をテストに落としたもの。

これは**実装のテストではなく、法務が実装に課した要求のテスト**である。
ルールの語彙が変わっても、ここに書いた性質は変わらない。
語彙そのものは B1L_optout_rules.json が持つ（コードにも、ここにも書かない）。
"""
import json, os, sys
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import optout  # noqa: E402
from optout import classify_window, load_rules  # noqa: E402

RULES = load_rules()


# --- 要求1: 未知の match 種別は黙って読み飛ばさず異常終了する -------------
def test_未知のmatch種別は例外にする():
    """v1.0 の A1 欠落と同じ事故を二度と起こさないための要求。

    実装が知らない規則を無視すると、**法務が塞いだ穴が実装側で黙って開く。**
    しかも「0件ヒット」は「該当なし」と区別がつかないので誰も気づかない。
    """
    broken = json.loads(json.dumps(RULES))
    broken["rules"] = [{"id": "X_未知", "class": "D", "match": "telepathy",
                        "terms": ["なんでもよい"]}]
    with pytest.raises(optout.UnknownMatchKind):
        classify_window("取引はお断りします", rules=broken)


def test_実際のルールファイルの全match種別を実装が知っている():
    """法務が新しい種別を足したら、ここが落ちて実装漏れに気づく。"""
    kinds = {r.get("match") for r in RULES["rules"]}
    assert kinds <= optout.KNOWN_MATCH_KINDS, \
        "実装が知らない match 種別がある: %r" % (kinds - optout.KNOWN_MATCH_KINDS)


# --- 要求2: suffix_negation は方向性のある近接判定 -----------------------
def test_取引窓口の直後が否定ならDになる():
    """v1.0 最大の欠陥。『新規お取引は行っておりません』が A_PLUS に化けていた。
    誤りの向きが『打診してはいけない相手が最優先候補になる』という最悪方向だった。"""
    r = classify_window("新規お取引は行っておりません。")
    assert r["optout_class"] == "D", r
    assert "D6_trade_window_negated" in r["optout_rule_ids"]


def test_否定が前にあるだけでは拾わない():
    """無方向の共起で代用してはならない、という法務の明示要求。
    『新規お取引はこちらから。なお電話はお受けしておりません』は
    取引を断っていない。ここを間違えると**打てる相手を捨てる。**"""
    r = classify_window("新規お取引はこちらから。なお、お電話はお受けしておりません。")
    assert "D6_trade_window_negated" not in r["optout_rule_ids"], r


def test_否定が遠すぎれば拾わない():
    lookahead = [x for x in RULES["rules"]
                 if x["id"] == "D6_trade_window_negated"][0]["negation_lookahead_chars"]
    far = "新規お取引" + "あ" * (lookahead + 10) + "行っておりません"
    r = classify_window(far)
    assert "D6_trade_window_negated" not in r["optout_rule_ids"], r


def test_一般消費者向けの断り書きはD6にしない():
    """left_context_guard。『一般のお客様への直接のお取引は行っておりません』は
    **卸だけをやっている会社**の表示であって、当社への拒絶ではない。
    むしろ本命に近い。ここを D にすると本丸を捨てる。"""
    r = classify_window("一般のお客様との直接のお取引は行っておりません。")
    assert "D6_trade_window_negated" not in r["optout_rule_ids"], r


# --- 要求3: A1 の否定右辺 ------------------------------------------------
def test_A_PLUSは否定が続いたら成立しない():
    r = classify_window("新規お取引は行っておりません。")
    assert r["optout_class"] != "A_PLUS"


def test_A_PLUSは否定が無ければ成立する():
    r = classify_window("新規お取引に関するお問い合わせはこちらの窓口へ。")
    assert r["optout_class"] == "A_PLUS", r


# --- 要求4: needs_review を立てる ---------------------------------------
def test_needs_review規則は理由付きでフラグを立てる():
    r = classify_window("新規お取引は行っておりません。")
    assert r["optout_needs_review"] is True
    assert r["optout_review_reason"], "理由が空。人が読み返せない"


def test_review_triggersは判定を変えずフラグだけ立てる():
    """『〜のみ』は文脈で正反対になるので機械で断定しない、という法務の要求。"""
    r = classify_window("お取引は既存のお取引先様のみとさせていただいております。")
    assert r["optout_needs_review"] is True
    assert r["optout_review_reason"]


def test_該当が無ければneeds_reviewは立たない():
    r = classify_window("会社概要はこちらをご覧ください。")
    assert r["optout_needs_review"] is False
    assert r["optout_class"] == "A"


# --- 要求5: e_subclass を出す -------------------------------------------
def test_Eには下位分類が付く():
    r = classify_window("実店舗をお持ちでない事業者様とのお取引はお断りしております。")
    assert r["optout_class"] == "E"
    assert r["optout_e_subclass"], "E なのに e_subclass が空"


def test_E以外に下位分類は付かない():
    assert classify_window("会社概要はこちら")["optout_e_subclass"] == ""


# --- 要求6: 適用順は E → D（データ側で決まる） ---------------------------
def test_適用順はルールファイルが決める():
    """実装が順序をハードコードしていないこと。
    v1.1 で D→E から E→D に変わったが、実装は触っていない。"""
    assert RULES["apply_order"][:2] == ["E", "D"]


# --- 要求7: 個別判断は別名でも突き合わせる -------------------------------
def test_個別判断は別名でも引ける():
    """ストームレーベルズが3表記で登録され、D が付いたのは1行だけだった事故の再発防止。
    **除外したはずの会社が別表記で打診キューに残る。**"""
    dec = optout.individual_decisions()
    for alias in ("株式会社ストームレーベルズ", "イーラブ・レーベル", "ジェイストーム"):
        assert alias in dec, "別名 %r で個別判断を引けない" % alias
        assert dec[alias]["class"] == "D"


def test_個別判断は正式商号でも引ける():
    dec = optout.individual_decisions()
    assert "株式会社ブラザー・ジョルダン社" in dec


# --- 要求8: recheck_condition を取りこぼさない ---------------------------
def test_複数のE規則に当たったら再評価条件を両方残す():
    """1つしか残さないと、片方の条件が解消されても再評価されない。"""
    txt = ("実店舗をお持ちでない事業者様とのお取引はお断りしております。"
           "またAmazon等のモールでの販売は認めておりません。")
    r = classify_window(txt)
    assert "実店舗" in r["recheck_condition"], r["recheck_condition"]


def test_A1の否定右辺は単独でも効く():
    """★このテストは、変異が生き残ったから書いた。

    `_drop_negated`（A1 の否定右辺）を無効化しても全163件が通ってしまった。
    適用順が E → D なので D6 が先に捕まえ、A1 の否定が一度も試されないため。
    法務 v1.1 は A1 の negation_terms を『三層』の一層として要求しているので
    削除はできない。**なら、単独で効くことを確かめられる形にする。**
    テストで守れない実装は、動いている証拠がないまま安心だけを与える。
    """
    only_a1 = json.loads(json.dumps(RULES))
    only_a1["rules"] = [r for r in RULES["rules"] if r["id"] == "A1_trade_window"]
    only_a1["apply_order"] = ["A_PLUS", "A"]

    assert classify_window("新規お取引の窓口はこちらです。",
                           rules=only_a1)["optout_class"] == "A_PLUS"
    assert classify_window("新規お取引は行っておりません。",
                           rules=only_a1)["optout_class"] == "A", \
        "A1 の否定右辺が効いていない。取引を断っている社が最優先候補に化ける"
