"""入数パーサ discovery.quantity のテスト（多様な表記＝偽利益バグの土台の品質保証）。

実行: code/ ディレクトリで `python -m pytest discovery/test_quantity.py`
"""

import pytest

from discovery.quantity import parse_quantity


@pytest.mark.parametrize(
    "name,expected",
    [
        # ── 個数単位（日本語） ──
        ("リューブゼリー 20個入り", 20),
        ("リューブゼリー 1個", 1),
        ("お茶 500ml ペットボトル 24本入り", 24),
        ("マスク 50枚入", 50),
        ("コーヒー 30袋セット", 30),
        ("プロテインバー 12本パック", 12),
        ("サプリ 60粒", 60),
        ("レトルトカレー 10食", 10),
        ("乾電池 単3 8個パック", 8),
        # ── 掛け算記号 ──
        ("インスタント味噌汁 ×20", 20),
        ("ティッシュ x5 箱", 5),
        ("缶コーヒー 185g✕30", 30),
        # ── 英語/略記 ──
        ("Wet Wipes 80P", 80),
        ("AA Battery 4pcs", 4),
        ("snack 6 pack", 6),
        # ── セット表現 ──
        ("タオル 3枚セット", 3),
        ("グラス 2個セット", 2),
        ("ペン 12本セット", 12),
        # ── 単数明示 ──
        ("リューブゼリー 単品", 1),
        ("ボトル ばら売り", 1),
        # ── 入数不明（None を返すべき） ──
        ("リューブゼリー", None),
        ("サーモス 水筒 真空断熱", None),
        ("ワイヤレスイヤホン Bluetooth", None),
    ],
)
def test_parse_quantity(name, expected):
    assert parse_quantity(name) == expected


def test_none_and_empty():
    assert parse_quantity(None) is None
    assert parse_quantity("") is None


@pytest.mark.parametrize(
    "name",
    [
        "お茶 500ml",          # 容量を個数500と誤読しない
        "プロテイン 1kg",       # 重量
        "モバイルバッテリー 10000mAh",
        "モニター 24インチ",
        "USBケーブル 2m",
        "保冷剤 -20度対応",
    ],
)
def test_measurement_not_mistaken_for_quantity(name):
    """容量・サイズ・スペック由来の数字を個数と誤検出しないこと（誤・原石の温床）。"""
    assert parse_quantity(name) is None


def test_capacity_plus_count_picks_count():
    """容量と入数が両方ある場合、入数（本数）を採る。"""
    assert parse_quantity("コカコーラ 500ml ×24本") == 24
    assert parse_quantity("ミネラルウォーター 2L 6本入り") == 6
