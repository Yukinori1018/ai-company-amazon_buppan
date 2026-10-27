"""37_listed_dedup.listed_mark のテスト（タカシ 2026-10-21）

実行：python3 -m pytest test_listed_mark.py  または  python3 test_listed_mark.py
xlsx も gBiz も触らない。index_from に銘柄を直接渡す。
「大手（上場）」で始まる文言＝層5。それ以外は層5 にしない、を確かめる。
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("ld", os.path.join(HERE, "37_listed_dedup.py"))
ld = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ld)

EXACT, CORES = ld.index_from([
    ("トミタ", "トミタ（スタンダード・8147）"),
    ("ロゴスホールディングス", "ロゴスホールディングス（グロース・205A）"),
    ("サントリー食品インターナショナル", "サントリー食品インターナショナル（プライム・2587）"),
    ("花王", "花王（プライム・4452）"),
    ("資生堂", "資生堂（プライム・4911）"),
    ("ＳＡＮＥＩ", "ＳＡＮＥＩ（スタンダード・6230）"),
    ("イートアンドホールディングス", "イートアンドホールディングス（プライム・2882）"),
])


def mark(maker, brands=(), big="", size=""):
    return ld.listed_mark(maker, list(brands), EXACT, CORES, big=big, size=size)


def is_big(s):
    return s.startswith("大手（上場）")


def test_tomita_short_same_name_is_not_big():
    # 2026-10-20 ZW：燕市のトミタ（6名）が東証のトミタ 8147 に一致して層5 に入っていた
    s = mark("トミタ", ["トミタ"], size="規模不明（同名の法人が12社）")
    assert not is_big(s) and "同名" in s


def test_logos_alias_is_not_child_of_logos_hd():
    # 2026-10-20 ZU：「ロゴス(LOGOS)」が親「ロゴス」（北海道の住宅会社）の子会社疑いになっていた
    assert mark("ロゴス(LOGOS)", ["ロゴス(LOGOS)"]) == ""


def test_short_name_with_independent_big_evidence_stays_big():
    # 花王は2文字だが、gBiz／既知リストで大手と分かっていれば層5 のまま
    assert is_big(mark("花王", ["花王"], big="大手"))


def test_long_exact_match_is_big():
    assert is_big(mark("サントリー食品インターナショナル株式会社", []))


def test_long_exact_match_stays_big_even_if_gbiz_sme():
    # グロース上場には法定中小がある。長い社名の完全一致は規模で覆さない
    assert is_big(mark("サントリー食品インターナショナル", [], size="中小（従業員6人）"))


def test_short_brand_hit_needs_evidence():
    # ブランド欄の短い語（松屋フーズのブランド「松屋」など）で別の上場会社に当たる型
    assert not is_big(mark("株式会社ABC食品", ["トミタ"]))


def test_child_company_prefix_still_detected():
    assert mark("資生堂パーラー", []).startswith("大手（上場子会社の疑い）")


def test_short_latin_alias_needs_evidence():
    # 三永貿易のブランド「ＳＥ（Ｓａｎｅｉ）」が SANEI 6230 に当たる型（英字5文字）
    assert not is_big(mark("三永貿易株式会社", ["ＳＥ（Ｓａｎｅｉ）"]))


def test_operating_company_named_as_hd_core():
    assert mark("イートアンド(株)", ["大阪王将"]).startswith("大手（上場子会社の疑い）")


def test_no_hit():
    assert mark("グリーンベル", ["匠の技"]) == ""


if __name__ == "__main__":
    import sys
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            try:
                f(); print("ok  ", n)
            except AssertionError as e:
                fails += 1; print("FAIL", n, e)
    sys.exit(1 if fails else 0)
