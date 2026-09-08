"""選定条件のテスト。**社長判断と法務判定を、消えないようにここへ固定する。**"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import selection_rules as S  # noqa: E402


# ── 1. 蛍光灯（LED は残す）─────────────────────────────────────────────
def test_LEDでない蛍光灯は除外する():
    r = S.judge(netsea_name="DNライティング エースライン スリム蛍光灯 FLR57T6EX-W",
                brand="DNライティング")
    assert r.excluded
    assert any("蛍光灯" in x for x in r.exclude_reasons)


def test_LED蛍光灯は残す():
    """社長判断 2026-09-07「LED蛍光灯（直管形LED）は残す」。

    ここが落ちたら、残すと決めた商品を消している。
    """
    for name in ("LED蛍光灯 直管40形 昼白色",
                 "直管形LEDランプ 40W形 グロー式",
                 "ＬＥＤ蛍光灯 20W形",
                 "led 蛍光灯 直管 120cm"):
        r = S.judge(netsea_name=name, brand="テスト社")
        assert not r.excluded, f"{name} を落としてはいけない: {r.exclude_reasons}"


def test_直管を無条件に落とす条件を書いていない():
    """`直管` だけを理由に落としてはいけない（危うくLED蛍光灯まで落とすところだった）。

    LED でない直管蛍光灯は「蛍光灯」の語で落ちる。「直管」では落とさない。
    """
    r = S.judge(netsea_name="直管形 グロースターター 40形", brand="テスト社")
    assert not any("直管" in x for x in r.exclude_reasons)


def test_直管形LEDは機械で判定せず要確認で残す():
    """電安法の対象/対象外が同じ商品名に混在し、機械では判別できない（法務 human_gate）。

    **落とすのでも、発注可にするのでもなく、要書類確認で残す**のが正解。
    """
    for name in ("直管形LEDランプ 40形 昼白色 グロー式工事不要",
                 "LED蛍光灯 直管 20W形 580mm"):
        r = S.judge(netsea_name=name, brand="テスト社", availability_amazon=-1)
        assert not r.excluded, f"{name}: {r.exclude_reasons}"
        assert r.requires_document_check, name


def test_電源内蔵の直管形LEDは除外せず要書類確認で残す():
    """PSE v2.1 で HARD → REVIEW に変わった（法務ハルオ 2026-09-08）。

    v2.0 では 1E（家電本体）の bare「電源」に当たって自動除外されており、
    human_gate（丸PSE表示があれば販売可）と矛盾していた。**仕様側の誤り**で、
    実装は仕様どおりに動いていたと法務から回答があった。
    v2.1 で bare「電源」「電気」を 1E から削除し、危険な形は複合語で書く方針に変更
    （電源コード等は 1A で捕捉済み）。

    このテストは「申し送り中の挙動の固定」から「**修正後の正しい挙動の固定**」に役目が変わった。
    """
    r = S.judge(netsea_name="直管LEDランプ 電源内蔵型", brand="テスト社",
                availability_amazon=-1)
    assert not r.excluded, f"除外してはいけない: {r.exclude_reasons}"
    assert r.pse_verdict == "REVIEW"
    assert r.pse_rule_id == "1F_PRE", "曖昧さのない照明製品名として 1E より先に拾われる"
    assert r.requires_document_check


def test_照明の文脈がない弱い語では発火しない():
    """PSE v2.1 の申し送り1への対応（法務ハルオ 2026-09-08）。

    v2.0 では bare「ライト」「スタンド」が光源以外を拾い、REVIEW 72件中59件（82%）が
    商品名に光源語を1つも持たなかった。v2.1 で弱い語を分離し、
    **複合語または照明の文脈語との共起でのみ発火**するようになった。

    ここが落ちたら、空振りの確認作業がまた増えている。
    """
    for name, why in (
            ("宇都宮製作所 シンガーニトリルライト パウダーフリー SS 100枚", "ニトリル手袋"),
            ("かわ畑 テーブルランナー ライトベージュ 約180×33cm", "色名の『ライト』"),
            ("アンブレラスタンド アイアン製 傘立て", "傘立て"),
    ):
        r = S.judge(netsea_name=name, brand="テスト社", availability_amazon=-1)
        assert r.pse_verdict == "PASS", f"{why} は PSE の対象ではない: {r.pse_rule_id}"
        assert not r.requires_document_check


def test_センサーライトは1Eより先に照明として拾われる():
    """PSE v2.1 の自主検出A（法務ハルオ）。

    1E が 1F より先に評価されるため、明確な照明製品が「センサー」で HARD に
    なっていた（実測18件）。1F_PRE を 1E より前に置いて解消。
    **評価順そのものが仕様**なので、順序を変えたら法務のテストを必ず回すこと。
    """
    r = S.judge(netsea_name="センサーライト 人感 屋外 LED", brand="テスト社",
                availability_amazon=-1)
    assert not r.excluded
    assert r.pse_rule_id == "1F_PRE"


# ── 2. Amazon 本体 ────────────────────────────────────────────────────
def test_Amazon本体が出品していたら除外する():
    assert S.judge(netsea_name="なにか", brand="B", availability_amazon=0).excluded
    assert not S.judge(netsea_name="なにか", brand="B", availability_amazon=-1).excluded


# ── 3. 知財ブランド ───────────────────────────────────────────────────
def test_知財ブランドは除外せずフラグだけ立てる():
    """社長判断: 除外ではなくゲート確認の対象として印を付ける。"""
    r = S.judge(netsea_name="ポケットモンスター ぬいぐるみ", brand="三英貿易",
                availability_amazon=-1)
    assert not r.excluded, "知財ブランドは落とさない"
    assert any("知財" in f for f in r.flags)


# ── 4. PSE v2 ────────────────────────────────────────────────────────
def test_特定電気用品はHARDで除外():
    r = S.judge(netsea_name="ACアダプター 12V", brand="テスト社")
    assert r.excluded and r.pse_verdict == "HARD"


def test_光源系はREVIEWで残すが発注可にはしない():
    r = S.judge(netsea_name="LEDシーリングライト", brand="テスト社",
                availability_amazon=-1)
    assert not r.excluded
    assert r.pse_verdict == "REVIEW"
    assert r.requires_document_check, "通過だが要書類確認"
    assert r.pse_review_note, "確認文が CSV に出せること"


def test_乾電池駆動はPASS():
    """v1 が誤って落としていた類型。コンセントに繋がないものは電気用品ではない。"""
    r = S.judge(netsea_name="目覚まし時計 アラームクロック", brand="テスト社",
                availability_amazon=-1)
    assert r.pse_verdict == "PASS"
    assert not r.excluded


def test_法務の語彙を写経していない():
    """仕様は法務の JSON を読む。こちらに語彙を持たない。

    写経すると、法務が仕様を直したときに実装だけ古いまま黙って動き続ける。
    """
    src = (Path(__file__).resolve().parents[1] / "selection_rules.py").read_text()
    assert "ACアダプタ" not in src, "PSE の語彙をコピーしないこと"
    assert "04_pse_rule_v2.py" in src, "法務の参照実装を読み込むこと"
