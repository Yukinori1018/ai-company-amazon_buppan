"""別商品の疑い検知ガード（name_match）の単体テスト。

社長報告(2026-06-06)の3実例を必ずカバーする:
  - 遊具 ⇔ 物置          → 別商品の疑い（SUSPECT）
  - ジャングルジム ⇔ デスク → 別商品の疑い（SUSPECT）
  - スライダージム同士     → 妥当（OK）
加えて、健全キーワードでの誤検知抑制（耳栓等）も検証する。
"""

from discovery import name_match


def test_real_case_playground_vs_storage_is_suspect():
    r = name_match.assess(
        "滑り台・ブランコ 大型遊具 すべり台 こども用",
        "物置 屋外 大型 SOFTSEA 収納庫 スチール",
    )
    assert r["ok"] is False
    assert name_match.is_suspect(
        "滑り台・ブランコ 大型遊具 すべり台 こども用",
        "物置 屋外 大型 SOFTSEA 収納庫 スチール",
    )


def test_real_case_jungle_gym_vs_desk_is_suspect():
    assert name_match.is_suspect(
        "つっぱり式ジャングルジム 室内 子供 遊具",
        "システムデスク OSJ パソコンデスク L字",
    )


def test_real_case_slider_gym_is_legitimate():
    r = name_match.assess(
        "おりたたみスライダージム すべり台 室内",
        "折りたたみ スライダージム 室内すべり台 ブランコ",
    )
    assert r["ok"] is True
    assert not name_match.is_suspect(
        "おりたたみスライダージム すべり台 室内",
        "折りたたみ スライダージム 室内すべり台 ブランコ",
    )


def test_earplug_keyword_is_not_suspect():
    """健全キーワード（耳栓）は別商品扱いにならない（誤検知抑制）。"""
    assert not name_match.is_suspect(
        "シリコン 耳栓 睡眠用 ノイズ低減 6個",
        "Loop Quiet 2 耳栓 睡眠用 ノイズキャンセリング",
    )
    assert not name_match.is_suspect(
        "耳栓 睡眠用 飛行機 気圧",
        "耳栓 飛行機 気圧 イヤープレーン 大人用",
    )


def test_shared_model_number_is_ok():
    """型番が一致すれば、他語が違っても妥当（最強シグナル）。"""
    r = name_match.assess("OSJ-1200 デスク", "パソコンデスク OSJ-1200 L字 ブラック")
    assert r["ok"] is True


def test_store_promo_words_are_stripped():
    """ストア名/プロモ語だけの共通は妥当判定に使わない（共通の実体が無ければ疑い）。"""
    # 「送料無料」「ポイント」しか共有しない＝商品本体は別物 → 疑い。
    r = name_match.assess(
        "送料無料 ポイント消化 滑り台 遊具",
        "送料無料 ポイント消化 物置 収納庫",
    )
    assert r["ok"] is False


def test_empty_or_sparse_names_not_suspect():
    """片側が空/極端に短い場合は判定材料不足→疑い扱いにしない（誤検知抑制）。"""
    assert not name_match.is_suspect("", "物置 大型")
    assert not name_match.is_suspect("A", "物置 大型 収納庫")


def test_numeric_conflict_volume_500_vs_1000():
    """容量が明確に矛盾（500ml vs 1000ml）→ 矛盾検知（別商品の疑い）。"""
    c = name_match.numeric_conflict(
        "シャンプー 500ml さらさら", "シャンプー 1000ml 詰め替え"
    )
    assert c is not None
    assert "容量" in c
    # 信頼度は「低」に落ち、原石対象外になる。
    r = name_match.match_confidence(
        "シャンプー 500ml さらさら", "シャンプー 1000ml 詰め替え"
    )
    assert r["level"] == name_match.CONFIDENCE_LOW


def test_numeric_conflict_liter_normalized_to_ml():
    """1L と 1000ml は同一容量＝矛盾なし（単位換算が効く）。"""
    assert name_match.numeric_conflict(
        "麦茶 1L ペット", "麦茶 1000ml ペットボトル"
    ) is None


def test_numeric_conflict_length_cm():
    """サイズが矛盾（24cm vs 30cm）→ 矛盾検知。"""
    c = name_match.numeric_conflict("フライパン 24cm", "フライパン 30cm IH対応")
    assert c is not None
    assert "サイズ" in c


def test_no_conflict_when_one_side_lacks_attribute():
    """片側にしか容量が無い場合は矛盾にしない（誤検知抑制）。"""
    assert name_match.numeric_conflict(
        "シャンプー 500ml", "シャンプー 詰め替え用"
    ) is None


def test_matching_volume_is_high_confidence():
    """容量一致＋名詞一致 → 高信頼度。"""
    r = name_match.match_confidence(
        "シャンプー 500ml さらさら", "さらさら シャンプー 500ml"
    )
    assert r["level"] == name_match.CONFIDENCE_HIGH


def test_model_number_conflict_is_low():
    """型番が食い違い、共通名詞も無ければ別商品の疑い（低）。"""
    r = name_match.match_confidence("水筒 JNL-504 サーモス", "弁当箱 FFZ-100 象印")
    assert r["level"] == name_match.CONFIDENCE_LOW


def test_tokenize_drops_measures_and_stopwords():
    toks = name_match.tokenize("送料無料 耳栓 500ml 睡眠用 セット")
    assert "耳栓" in toks
    assert "睡眠用" in toks
    assert "送料無料" not in toks
    assert "セット" not in toks
    # 500ml は計量なので個数/トークンに残らない
    assert "500" not in toks
