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


def test_商品名に電源の語があるとPSE_1Eで自動除外される_法務へ申し送り():
    """**これは仕様どおりの挙動であって、こちらで勝手に緩めない。**

    「直管LEDランプ 電源内蔵型」は 1E（家電本体）の語「電源」に当たり HARD になる。
    法務判定 §human_gate は、電源内蔵の直管形LED を『丸PSEマークと届出事業者名が
    あれば販売可』としているので、**judgment と rules で扱いが食い違って見える**。
    仕様の正は JSON 側なので実装は JSON に従い、食い違いは法務へ申し送る。
    ここを実装側で握りつぶすと、法務が塞いだ穴が黙って開き直る。
    """
    r = S.judge(netsea_name="直管LEDランプ 電源内蔵型", brand="テスト社",
                availability_amazon=-1)
    assert r.excluded
    assert r.pse_rule_id == "1E"


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
