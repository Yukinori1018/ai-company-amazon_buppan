"""入数判定のテスト。

**ここは2回事故を起こした場所です。**
1回目: NETSEA蒟蒻ゼリー1個117円 × Amazon「130gパウチ×48本入」6,798円 → 利益率77.1%と表示
2回目: NETSEAシャンデリア球1個310円 × Amazon「【ケース販売 10個セット】」3,380円
       → 利益率58.4%「原石」と表示（秘書カズヨが実ページを開いて発見）

**テストデータはすべて実在の Amazon 商品名**（keepa_facts.jsonl から写した）。
架空の商品名で通しても、実際の表記ゆれは捕まりません。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import pack  # noqa: E402


# ── カズヨが実物で見つけた7件（全部このパターン）────────────────────────
KAZUYO_FOUND = [
    ("ヤザワ 【ケース販売 10個セット】 シャンデリア球 クリア 25W E26口金 C372625C_set", 10),
    ("ヤザワ 【ケース販売 10個セット】 シャンデリア球 クリア 25W E12口金 C321225C_set", 10),
    ("ヤザワ 【ケース販売特価 10個セット】シャンデリア球 クリア 10W E12口金 C321210C_set", 10),
    ("ヤザワ 【ケース販売特価 10個セット】シャンデリア球 クリア 40W E12口金 C321240C_set", 10),
    ("ヤザワ 【ケース販売 10個セット】 ミニランプ フロスト 25W形 E17口金 S351722F_set", 10),
    ("ヤザワ シャンデリア球 クリア 40W 口金E17 C321740C 5個セット", 5),
]


def test_ケース販売の表記を読み落とさない():
    """`【ケース販売 10個セット】` を1と読んで幻の「原石」を7件出した。

    原因は括弧の**直後**の数字しか見ていなかったこと。
    `【3個セット】` は読めるのに `【ケース販売 10個セット】` は読めなかった。
    """
    for title, expected in KAZUYO_FOUND:
        got = pack.detect_pack(title)
        assert got.size == expected, f"{title} → {got.size}（期待 {expected}）"
        assert not got.uncertain


def test_ケース売りの入数を読む():
    d = pack.detect_pack
    assert d("オリヒロ ぷるんと蒟蒻Plus グレープフルーツ味 130gパウチ×48本入").size == 48
    assert d("オリヒロ ぷるんと凍らすアイス スタンディング(ST) グレープ 130gパウチ×48個入").size == 48


def test_入れ子の掛け算は全部掛け合わせる():
    d = pack.detect_pack
    assert d("オリヒロ ぷるんと蒟蒻ゼリー 塩うめ+塩レモン (20gパウチ×12個)×12袋入").size == 144
    assert d("オリヒロ ぷるんと凍らすアイス プレミアム バニラ (18g×10個)×12袋入").size == 120
    assert d("オリヒロプランデュ ぷるんと蒟蒻ゼリーパウチ アップル+グレープ 20gx12個×6袋").size == 72


def test_掛け算と素の個数を両方拾う():
    # 「10個入」と「×20セット」を別々に扱うと20（1/10）になる。実際そう間違えた。
    assert pack.detect_pack("ヤザワ ケーブルホルダー シルバー 10個入 FCB5【×20セット】").size == 200


def test_助数詞なしの末尾の掛け算も拾う():
    d = pack.detect_pack
    assert d("変換名人 LAN 中継アダプタ LAN-BB ×10").size == 10
    assert d("サンワサプライ コネクタカバー TK-CA×10").size == 10


def test_全角の数字を読む():
    assert pack.detect_pack("ＹＡＺＡＷＡ 束ねるバンド黒２００ｍｍ５０本入 FTC200K50").size == 50


def test_型番や寸法を入数と誤読しない():
    d = pack.detect_pack
    assert d("ヤザワコーポレーション グロー球 4W～10W形用 E17 FG7E1P").size == 1
    assert d("ヤザワコーポレーション シャンデリア球 口金E17 60W形 クリア C321760C").size == 1
    assert d("抗菌まな板 20×30cm").size == 1
    # 「まとめるチューブ」という実在商品。「まとめ」を set 判定に入れると誤爆する。
    got = d("ＹＡＺＡＷＡ まとめるチューブ内径６ｍｍ白 FCT6W")
    assert got.size == 1 and not got.uncertain


# ── 読めないものは「1」と答えず、要確認にする ──────────────────────────
def test_内訳と総数が混ざった商品名は要確認にする():
    """「12個入（2種類×6個）×6袋」は正解72だが、素直に全部掛けると864。

    **推測で答えを作らない。** 機械で解けないものは人に渡す。
    """
    got = pack.detect_pack("オリヒロ ぷるんと蒟蒻ゼリー 日向夏＋ゴールデンパイン 12個入（2種類×6個）×6袋")
    assert got.uncertain
    got2 = pack.detect_pack("【期間限定】 ぷるんと蒟蒻ゼリー レモンスカッシュ+メロンソーダ 20ｇパウチ2種×6個入り 4袋セット")
    assert got2.uncertain


def test_セット表記があるのに個数が読めなければ要確認():
    got = pack.detect_pack("ヤザワ ミニランプ フロスト 25W形 E17口金 S351722F_set")
    assert got.uncertain
    assert "個数が読めない" in got.reason


# ── 両側の突き合わせ ──────────────────────────────────────────────
def test_NETSEAが単品でAmazonがケースなら倍率が立つ():
    mult, reason, review = pack.resolve_multiplier(
        "ＹＡＺＡＷＡ　シャンデリア球 C37 E26 25W クリア",
        "ヤザワ 【ケース販売 10個セット】 シャンデリア球 クリア 25W E26口金 C372625C_set")
    assert mult == 10 and not review


def test_両側が同じ入数なら倍率は1():
    """NETSEAもAmazonも「6個入り」なら、同じ物を数えている＝倍率1。

    Amazon側の入数をそのまま卸値に掛けると、6倍の原価になって別の嘘になる。
    """
    mult, reason, review = pack.resolve_multiplier(
        "ヤザワ イヤーパッド インナーイヤー型 6個入り",
        "ヤザワコーポレーション イヤーパッド インナーイヤー型 6個入り ブラック TYP1")
    assert mult == 1 and not review


def test_割り切れない食い違いは要確認にする():
    mult, reason, review = pack.resolve_multiplier("テスト商品 4個入", "テスト商品 10個セット")
    assert review and "食い違い" in reason


def test_どちらかが不明なら要確認にする():
    mult, reason, review = pack.resolve_multiplier("テスト商品", "テスト商品 S351722F_set")
    assert review and mult == 1
