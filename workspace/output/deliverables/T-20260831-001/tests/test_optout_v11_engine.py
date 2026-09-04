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


# =====================================================================
# 法務ルール v1.2 の追加要求
# =====================================================================

def test_区切り文字はルールファイルが持つ():
    """実装が句点だけを決め打ちしていないこと。
    収集した注記原文は複数の窓口ブロックを『／』で連結しているので、
    そこをまたいで判定すると**別窓口の文言を混ぜる。**"""
    d = RULES["sentence_delimiters"]
    assert "／" in d and "｜" in d, "窓口の連結記号が区切りに入っていない"
    assert "、" not in d and "・" not in d, \
        "『、』『・』を区切りにすると『企業・店舗様との新規お取引は行っておりません』を落とす"


def test_スラッシュ区切りをまたいだ否定は拾わない():
    """『／』は別窓口の境目。またぐと他窓口の断り文句を持ち込む。"""
    # ★最初この文を長く書いていたら、変異（区切りを句点だけにする）でも通った。
    #   否定語が lookahead 25文字の外に出ていて、**区切りではなく長さで落ちていた**。
    #   区切りだけが効く長さにする。
    r = classify_window("新規お取引はこちら／お受けしておりません")
    assert "D6_trade_window_negated" not in r["optout_rule_ids"], r
    # 同じ長さで区切りが無ければヒットすること（＝長さで落ちていない証明）
    r2 = classify_window("新規お取引はこちらお受けしておりません")
    assert "D6_trade_window_negated" in r2["optout_rule_ids"], r2


def test_読点や中黒はまたいでよい():
    """『企業・店舗様との新規お取引は行っておりません』は正当な D。
    ここを区切ると**打ってはいけない相手を打ってしまう。**"""
    r = classify_window("以下の企業・店舗様との新規お取引は行っておりません。")
    assert r["optout_class"] == "D", r


def test_A1の否定フィルタも同一文条件を課す():
    """v1.1 は文字数だけだったため、**正当な A_PLUS を A に降格**させていた。
    母数を減らす方向の誤り（法務が自主検出）。"""
    only_a1 = json.loads(json.dumps(RULES))
    only_a1["rules"] = [r for r in RULES["rules"] if r["id"] == "A1_trade_window"]
    only_a1["apply_order"] = ["A_PLUS", "A"]
    r = classify_window("新規お取引はこちらから。なお、お電話はお受けしておりません。",
                        rules=only_a1)
    assert r["optout_class"] == "A_PLUS", \
        "句点をまたぐ否定で A_PLUS を落としている（母数を減らす方向の誤り）"


def test_needs_reviewは勝たなかった規則からも立つ():
    """★v1.2 の本丸。

    『勝ったクラスの規則』だけを見ると、**判定と無関係な理由でフラグが静かに消える。**
    v1.1 で適用順を E→D にした結果、ハイメスが E4（needs_review なし）で確定し、
    同時に発火していた D6（needs_review あり）のフラグを落とした。
    結論は E で変わらないのに、レビュー対象から外れた。
    """
    txt = ("以下の業種、業態の企業・店舗様との新規お取引は行っておりません。"
           "・WEBでの販売のみの企業様")
    r = classify_window(txt)
    assert r["optout_class"] == "E", r          # 判定は E のまま
    assert r["optout_needs_review"] is True, \
        "勝たなかった D6 の needs_review が落ちている"
    assert r["optout_review_reason"]


#: ハイメス（＝株式会社ブラザー・ジョルダン社）の窓口原文。法務が実機確認した社。
HEIMES = ("お取引希望の方は下記フォームに必要事項をご記入の上、送信下さい。"
          "尚、誠に勝手ながら以下の業種、業態の企業・店舗様との新規お取引は"
          "行っておりません。ご了承のほどお願い申し上げます。"
          "・WEBでの販売のみの企業様・小売以外のスタイルで店舗展開をされている企業様")


def test_勝たなかった規則IDを証跡として残す():
    """E が勝った社に D3（通報明示）も当たっていた、という事実を失わない。
    判定は正しくても**なぜ除外したのかが分からなくなる。**

    法務が実機確認した期待値そのもの:
      D6(needs_review あり) / E4(なし) / A1(なし) が発火し、
      勝ちクラス = E のまま needs_review = true、other = D6;A1。
    A1 は1文目の『お取引希望』で発火する（否定はされていない）。
    2文目の『新規お取引は行っておりません』は同一文内の否定なので数えない。
    """
    r = classify_window(HEIMES)
    assert r["optout_class"] == "E"
    assert r["optout_rule_ids"] == "E4_web_only_refused"
    assert r["optout_needs_review"] is True
    assert r["optout_other_rule_hits"] == "D6_trade_window_negated;A1_trade_window", \
        r["optout_other_rule_hits"]


def test_通報明示の証跡はEが勝っても残る():
    """愛知電線型。踏むと実害が出る社の根拠が、判定順の副作用で消えてはならない。"""
    txt = ("実店舗をお持ちでない事業者様とのお取引はお断りしております。"
           "無断の営業メールは特定電子メール法に基づき通報いたします。")
    r = classify_window(txt)
    assert r["optout_class"] == "E"
    assert "D3_report_threat" in r["optout_other_rule_hits"], r["optout_other_rule_hits"]


def test_other_rule_hitsの順序が安定している():
    """監査証跡は差分を取るので、実行のたびに並びが変わっては困る。"""
    a = classify_window(HEIMES)["optout_other_rule_hits"]
    b = classify_window(HEIMES)["optout_other_rule_hits"]
    assert a == b and a
