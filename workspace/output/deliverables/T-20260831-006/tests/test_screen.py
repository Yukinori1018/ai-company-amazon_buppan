"""段2（0トークンの前段フィルタ）のテスト。

実行: cd workspace/output/deliverables/T-20260831-006 && python3 -m pytest tests -q

テストデータは **NETSEA の実レスポンスから写した形** を使う（架空の形で通しても意味がない）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import config, screen  # noqa: E402

CFG = config.ScanConfig()

# NETSEA /items の実レスポンス（supplier 6804 の1件目）から写した形。
REAL_ITEM = {
    "supplier_id": 6804,
    "product_id": "6",
    "product_url": "https://www.netsea.jp/shop/6804/6",
    "product_name": "★アウトレット★ アクティブプロテイン100",
    "shop_name": "オリヒロ 株式会社",
    "jan_code": "4971493901777",
    "category_id": 81606,
    "ship_fee_type": "N",
    "ship_fee": 0,
    "deal_net_shop_flag": "Y",
    "set": [{
        "direct_item_id": "43452-1", "branch_code": "70101102",
        "jan_code": "4971493901777", "label": "360g", "reference_price": "",
        "price": 403, "set_num": 1, "set_price": 435,
        "set_price_without_tax": 403, "set_price_tax": 32,
        "consumption_tax_class": 1, "sold_out_flag": "Y",
    }],
}


# どのキーが商品(トップレベル)側で、どれが規格(set)側かを明示する。
# `jan_code` は**両方に存在する**ため、暗黙のルーティングに任せると
# 「set 側だけ書き換わらずテストが通ってしまう」事故になる（実際に一度やった）。
_ITEM_KEYS = {"product_name", "deal_net_shop_flag", "ship_fee", "shop_name", "product_url"}


def _item(**over):
    """REAL_ITEM を土台に差し替えた商品を作る。jan_code は商品・規格の両方へ反映する。"""
    item = {k: v for k, v in REAL_ITEM.items() if k != "set"}
    s = dict(REAL_ITEM["set"][0])
    for k, v in over.items():
        if k == "jan_code":
            item[k] = s[k] = v
        elif k in _ITEM_KEYS:
            item[k] = v
        else:
            s[k] = v
    item["set"] = [s]
    return item


def _one(**over):
    """判定テスト用の1件。

    REAL_ITEM の商品名は実データそのままの「★アウトレット★ アクティブプロテイン100」で、
    これは中古品ルール（古物商許可が未取得）で**除外される**のが正しい挙動です。
    それ以外の条件を試すときに毎回引っかかると邪魔なので、既定では素の商品名にします。
    アウトレット除外そのものは専用のテストで確かめます。
    """
    over.setdefault("product_name", "アクティブプロテイン100 360g")
    return screen.to_candidates(_item(**over))[0]


# -- 展開 ---------------------------------------------------------------------
def test_複数規格は規格ごとの候補に展開される():
    item = dict(REAL_ITEM)
    item["set"] = [
        dict(REAL_ITEM["set"][0], jan_code="4971493901777", price=403),
        dict(REAL_ITEM["set"][0], jan_code="4971493901784", price=500),
    ]
    got = screen.to_candidates(item)
    assert [c.jan for c in got] == ["4971493901777", "4971493901784"]
    assert [c.wholesale_ex_tax for c in got] == [403, 500]


def test_規格側のJANが空ならトップレベルのJANで補う():
    item = dict(REAL_ITEM)
    item["set"] = [dict(REAL_ITEM["set"][0], jan_code="")]
    assert screen.to_candidates(item)[0].jan == "4971493901777"


def test_空文字の上代は0として扱う():
    # NETSEA は reference_price に空文字を返す。int() で落ちてはいけない。
    assert _one().reference_price_ex_tax == 0


# -- 判定 ---------------------------------------------------------------------
def test_品切れは落とす():
    c = screen.screen_one(_one(sold_out_flag="Y"), CFG)
    assert c.reason == screen.REASON_SOLD_OUT


def test_在庫ありは通る():
    c = screen.screen_one(_one(sold_out_flag="N"), CFG)
    assert c.verdict == screen.PASS


def test_JANが13桁でなければ落とす():
    c = screen.screen_one(_one(sold_out_flag="N", jan_code="49714939"), CFG)
    assert c.reason == screen.REASON_BAD_JAN


def test_ネット販売不可は落とす():
    c = screen.screen_one(_one(sold_out_flag="N", deal_net_shop_flag="N"), CFG)
    assert c.reason == screen.REASON_NET_SHOP_NG


def test_卸価格がレンジ外なら落とす():
    c = screen.screen_one(_one(sold_out_flag="N", price=50), CFG)
    assert c.reason.startswith(screen.REASON_PRICE_BAND)


def test_規制品ワードは落とす():
    c = screen.screen_one(
        _one(sold_out_flag="N", product_name="リチウムイオン モバイルバッテリー 10000mAh"), CFG
    )
    assert c.reason.startswith(screen.REASON_REGULATED)


def test_中古品は落とす():
    # 古物商許可が未取得のうちは、1点でも扱えば古物営業法違反になる。
    c = screen.screen_one(
        _one(sold_out_flag="N", product_name="中古vintage アクセサリー ブローチ"), CFG
    )
    assert c.reason.startswith(screen.REASON_USED)


def test_実データのアウトレット表記も中古品として落とす():
    # REAL_ITEM は NETSEA の実レスポンスそのまま。ハルオ判定でアウトレット＝返品再生品は
    # 古物にあたりうるとされたため、許可取得までは落とす。
    c = screen.screen_one(screen.to_candidates(_item(sold_out_flag="N"))[0], CFG)
    assert c.reason.startswith(screen.REASON_USED)


def test_古物商許可を取得後は中古品を通せる():
    cfg = config.ScanConfig(drop_used=False)
    c = screen.screen_one(_one(sold_out_flag="N", product_name="中古 ブローチ"), cfg)
    assert c.verdict == screen.PASS


def test_ネット販売可否は設定で緩められない():
    # ハルオ判定「フィルタではなく除外」。設定で True 以外にできない形かを固定する。
    assert config.ScanConfig(require_net_shop_ok=False).require_net_shop_ok is False, (
        "dataclass の仕様上は代入できてしまうため、CLI にオプションを置かないことで守る"
    )
    c = screen.screen_one(_one(sold_out_flag="N", deal_net_shop_flag="N"), config.ScanConfig())
    assert c.reason == screen.REASON_NET_SHOP_NG


def test_電気製品は除外せず法令要確認のフラグだけ立てる():
    # ここで落とすと家電がまるごと消えて母数が死ぬ。目印だけ立てて人に渡す。
    c = screen.screen_one(_one(sold_out_flag="N", product_name="LEDライト 充電器つき"), CFG)
    assert c.verdict == screen.PASS
    flags = screen.law_check_flags(c.product_name)
    assert any("PSE" in f for f in flags)


def test_法令に関係ない商品はフラグが立たない():
    assert screen.law_check_flags("アクティブプロテイン100 360g") == []


def test_上代不明なら利益判定をスキップして通す():
    # 「不明」を「駄目」にしないという方針の要。ここが壊れると母数が静かに減る。
    c = screen.screen_one(_one(sold_out_flag="N", reference_price=""), CFG)
    assert c.verdict == screen.PASS
    assert any("上代不明" in n for n in c.notes)


def test_上代が低すぎれば最良ケースでも届かず落ちる():
    # 卸403円・上代450円 → 最良の料率と最小FBAでも500円は残らない。
    c = screen.screen_one(_one(sold_out_flag="N", reference_price=450), CFG)
    assert c.reason.startswith(screen.REASON_HOPELESS)


def test_上代が十分高ければ通る():
    c = screen.screen_one(_one(sold_out_flag="N", reference_price=3000), CFG)
    assert c.verdict == screen.PASS


def test_最良ケースの利益は各種手数料を引いた額になる():
    c = _one(sold_out_flag="N", reference_price=3000)
    best = screen.best_case_net_profit(c, CFG)
    # 売値 3000*1.1*1.3 = 4290 / 最良料率8.4% / 最小FBA288 / 卸403*1.1=443.3
    assert 3100 < best < 3200


# -- 重複排除 -----------------------------------------------------------------
def test_同一JANは最安の1件だけ残り他社数が記録される():
    a = _one(sold_out_flag="N", price=500)
    b = _one(sold_out_flag="N", price=300)
    b.supplier_name = "別の卸"
    kept, dropped = screen.dedupe_by_jan([a, b])
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0].wholesale_ex_tax == 300
    assert kept[0].alt_supplier_count == 1


def test_歩留まりの集計は理由ラベル単位でまとまる():
    cs = [
        screen.screen_one(_one(sold_out_flag="N", price=50), CFG),
        screen.screen_one(_one(sold_out_flag="N", price=60), CFG),
        screen.screen_one(_one(sold_out_flag="N"), CFG),
    ]
    got = screen.summarize(cs)
    # 金額つきの理由でも1つのラベルに集約されること
    assert got[screen.REASON_PRICE_BAND] == 2
    assert got[screen.PASS] == 1
