"""利益計算層のテスト。**ここが1円でもごまかしたら、この事業の判断が全部狂う。**

Keepa の実レスポンス（2026-08-31 実測）から写した形をテストデータに使う。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import config, evaluate, keepa_verify, screen  # noqa: E402

CFG = config.ScanConfig()


def _cand(**over):
    base = dict(
        jan="4971493901777", product_name="テスト商品", supplier_id=6804,
        supplier_name="オリヒロ 株式会社", product_url="https://www.netsea.jp/shop/6804/6",
        wholesale_ex_tax=1000,
    )
    base.update(over)
    return screen.Candidate(**base)


def _facts(**over):
    base = dict(
        jan="4971493901777", asin="B006W1FQGE", title="仏壇下台", found=True,
        price_yen=5000, price_source="現在の新品最安(送料込)", sales_rank=378652,
        drops30=53, drops90=150, offer_count=5, availability_amazon=-1,
        category_names=["ホーム&キッチン"], package_mm=(300, 200, 100), package_g=800,
    )
    base.update(over)
    return keepa_verify.AmazonFacts(**base)


# -- Amazon に無い場合 ---------------------------------------------------------
def test_Amazonに同一JANが無い場合は利益計算せず正直に状態を残す():
    ev = evaluate.evaluate(_cand(), keepa_verify.AmazonFacts(jan="x", found=False), CFG)
    assert ev.result is None
    assert ev.status == evaluate.STATUS_NOT_ON_AMAZON
    assert not ev.is_profitable


def test_出品はあるが価格が取れない場合も計算しない():
    ev = evaluate.evaluate(_cand(), _facts(price_yen=None), CFG)
    assert ev.result is None
    assert ev.status == evaluate.STATUS_NO_PRICE


# -- 利益計算 -----------------------------------------------------------------
def test_純利益は売値から全コストを引いた額と一致する():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=1000), _facts(price_yen=5000), CFG)
    r = ev.result
    # 手で足し直して一致すること。丸めをどこかに隠していないかの検算。
    total = (r.referral_fee + r.fba_fee + r.wholesale_price_incl_tax
             + r.inbound_shipping + r.other_costs)
    assert abs(r.net_profit - (5000 - total)) < 0.01
    assert abs(r.margin_rate - r.net_profit / 5000) < 1e-9


def test_卸価格は税抜として税込に換算される():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=1000), _facts(), CFG)
    assert abs(ev.result.wholesale_price_incl_tax - 1100) < 0.01


def test_カテゴリはKeepaのカテゴリ名から料率に対応づく():
    ev = evaluate.evaluate(_cand(), _facts(category_names=["家電&カメラ"]), CFG)
    assert ev.category_key == "electronics"
    assert abs(ev.result.referral_rate - 0.084) < 1e-9


def test_不明カテゴリは辛い側のdefault料率になる():
    ev = evaluate.evaluate(_cand(), _facts(category_names=["よく分からない棚"]), CFG)
    assert ev.category_key == "default"
    assert abs(ev.result.referral_rate - 0.154) < 1e-9


def test_大型は大型のFBA手数料が使われる():
    ev = evaluate.evaluate(_cand(), _facts(package_mm=(900, 400, 300), package_g=12000), CFG)
    assert ev.size_key == "large_1"
    assert ev.result.fba_fee == 603


def test_寸法も重量も無ければ不明として標準2で仮置きしその旨を状態に残す():
    ev = evaluate.evaluate(_cand(), _facts(package_mm=(), package_g=None), CFG)
    assert ev.size_key == "unknown"
    assert ev.result.fba_fee == 430
    assert "FBAサイズ不明" in ev.status
    # 体積が分からないので保管料は計上しない（0で埋めて安く見せない）
    assert ev.storage_fee == 0


def test_保管料は体積と月数から計算され純利益に反映される():
    ev = evaluate.evaluate(_cand(), _facts(package_mm=(300, 200, 100)), CFG)
    # 30×20×10cm = 6,000cm³ / 繁忙期 10.087円 per 1,000cm³ / 1.5ヶ月
    # （2.0→1.5 は経理ハジメ実測版 2026-09-04。3ヶ月線形消化なら平均在庫は1/2）
    assert abs(ev.storage_fee - 6.0 * 10.087 * 1.5) < 0.01
    assert ev.result.other_costs >= ev.storage_fee


def test_納品送料はFBA納品分と納品代行費とNETSEA送料の按分の合計():
    ev = evaluate.evaluate(_cand(ship_fee=800), _facts(), CFG)
    # FBA納品37.5円 + 納品代行12円 + NETSEA送料800円 ÷ 10個 = 129.5円
    # 旧値は「FBA納品100円 + 80円」で、**納品代行の作業費が1円も入っていなかった**。
    # 社長方針は物理作業の外注前提なので、これは費目の欠落だった（2026-09-04 修正）。
    assert abs(ev.inbound_shipping - (37.5 + 12 + 80)) < 0.01


def test_売れるたび乗る固定費が計上される():
    """2026-09-04 まで丸ごと抜けていた3費目の回帰テスト。

    小口プランの基本成約料・販売手数料の消費税・納品代行の作業費は、
    **売価に関係なく1点あたり必ず乗ります**。低単価品ほど効きます。
    """
    ev = evaluate.evaluate(_cand(), _facts(), CFG)
    assert ev.closing_fee == 110                      # 小口プラン基本成約料(税込)
    assert ev.inbound_shipping >= 12                  # 納品代行の作業費が入っている
    assert ev.return_provision > 0                    # 返品引当（旧「雑費」の置換）
    # 販売手数料は税抜表示。請求は×1.1。
    bare = ev.result.amazon_price * ev.result.referral_rate
    assert abs(ev.result.referral_fee - bare * 1.1) < 0.01


def test_返品引当は売価に連動しない():
    """旧実装は売価×3%だった。返品コストは手数料と仕入原価で決まる。"""
    cheap = evaluate.evaluate(_cand(), _facts(price_yen=3000), CFG)
    rich = evaluate.evaluate(_cand(), _facts(price_yen=30000), CFG)
    # 売価が10倍でも引当は10倍にならない（返金処理手数料の上限500円が効くため）
    assert rich.return_provision < cheap.return_provision * 10


def test_赤字でもはずれとして必ず評価が返る():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=9000), _facts(price_yen=5000), CFG)
    assert ev.result.net_profit < 0
    assert ev.result.verdict == "はずれ"
    assert not ev.is_profitable


# -- CSV 行 -------------------------------------------------------------------
def test_計算できない行でも列は揃い数値欄は空欄になる():
    ev = evaluate.evaluate(_cand(), keepa_verify.AmazonFacts(jan="x", found=False), CFG)
    row = evaluate.to_row(ev)
    assert set(row) == set(evaluate.COLUMNS)
    assert row["純利益"] == ""
    assert row["ASIN"] == ""
    # 卸値は NETSEA から取れているので空欄にはならない
    assert row["NETSEA卸値(税抜)"] == 1000


def test_手数料内訳は各費目の合計と一致する():
    ev = evaluate.evaluate(_cand(), _facts(), CFG)
    row = evaluate.to_row(ev)
    parts = (row["販売手数料(消費税込)"] + row["FBA配送料"] + row["保管料"]
             + row["納品送料(FBA+納品代行)"] + row["基本成約料"] + row["返品引当"])
    total = row["Amazon価格"] - row["純利益"] - row["NETSEA卸値(税込)"]
    assert abs(parts - total) <= 3  # 表示丸めぶんの誤差だけ許容


def test_出品者数の出所は未検証であることを明示する():
    row = evaluate.to_row(evaluate.evaluate(_cand(), _facts(), CFG))
    assert row["出品者数"] == 5
    assert "COUNT_NEW" in row["出品者数の出所"]


def test_実セラー数が確定していればそちらが優先され出所も切り替わる():
    f = _facts()
    f.real_seller_count = 1        # 出所ラベルは代入しない（値から導出される）
    row = evaluate.to_row(evaluate.evaluate(_cand(), f, CFG))
    assert row["出品者数"] == 1
    assert row["出品者数の出所"] == "実セラー数(offers検証済み)"


def test_Amazon本体の有無はavailabilityAmazonで判定する():
    # current[0] == -1 は「今この瞬間の価格が無い」だけで本体不在の証拠にならない。
    assert evaluate.to_row(
        evaluate.evaluate(_cand(), _facts(availability_amazon=-1), CFG))["Amazon本体の有無"] == "なし"
    assert evaluate.to_row(
        evaluate.evaluate(_cand(), _facts(availability_amazon=0), CFG))["Amazon本体の有無"] == "あり"


def test_リンク列はASINから組み立てられる():
    row = evaluate.to_row(evaluate.evaluate(_cand(), _facts(), CFG))
    assert row["Amazonページ"] == "https://www.amazon.co.jp/dp/B006W1FQGE"
    assert row["Keepaリンク"] == "https://keepa.com/#!product/5-B006W1FQGE"


# -- 同一JANに複数ASIN / 総合判定 ------------------------------------------------
def test_同一JANに複数ASINが返ったら売れている方を選ぶ():
    # 実測で150件中15件がこの形だった。最初の1件を採るのはただのくじ引きになる。
    def prod(asin, drops, rank):
        return {"asin": asin, "title": asin, "eanList": [4971493901777],
                "stats": {"current": [-1, 5000, -1, rank, 0, 0, 0, 0, 0, 0, 0, 3],
                          "salesRankDrops30": drops}}
    dead, alive = prod("BDEAD", 0, 900000), prod("BALIVE", 12, 3000)
    got = keepa_verify._pick_best([dead, alive])
    assert got["asin"] == "BALIVE"


def test_複数ASINの件数が記録される():
    f = _facts()
    f.asin_count = 2
    assert evaluate.to_row(evaluate.evaluate(_cand(), f, CFG))["同一JANのASIN数"] == 2


def test_利益が出ても30日で売れていなければ総合判定でそう書く():
    # 初回実走で「利益率55.9%・純利益7230円・drops30=0」が最上位に来た。
    # 在庫は現金なので、これを「原石」と呼んではいけない。
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=3000), _facts(price_yen=9000, drops30=0), CFG)
    assert ev.result.verdict == "原石"          # 利益だけ見れば原石
    assert evaluate.overall_verdict(ev) == "利益は出るが直近30日に売れた形跡なし"


def test_回転が遅い場合は個数を添えて総合判定に出す():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=3000), _facts(price_yen=9000, drops30=2), CFG)
    assert "回転が遅い" in evaluate.overall_verdict(ev)


def test_利益も回転もあれば利益判定がそのまま総合判定になる():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=3000), _facts(price_yen=9000, drops30=30), CFG)
    assert evaluate.overall_verdict(ev) == "原石"


def test_赤字は回転に関係なくはずれ():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=9000), _facts(price_yen=5000, drops30=99), CFG)
    assert evaluate.overall_verdict(ev) == "はずれ(赤字)"


def test_販売実績が不明な場合は不明と書く():
    ev = evaluate.evaluate(_cand(wholesale_ex_tax=3000), _facts(price_yen=9000, drops30=None), CFG)
    assert evaluate.overall_verdict(ev) == "利益は出るが販売実績が不明"


def test_全行に発注前の販売条件確認と商品ページURLが載る():
    # 販売条件の自由記述は API に無い（ハルオ判定・第3層）。人が読む導線を必ず添える。
    row = evaluate.to_row(evaluate.evaluate(_cand(), _facts(), CFG))
    assert "販売条件" in row["発注前に必ず確認"]
    assert row["NETSEA商品ページ"].startswith("https://www.netsea.jp/")


def test_電気製品の行には法令要確認が出る():
    row = evaluate.to_row(
        evaluate.evaluate(_cand(product_name="LEDライト ACアダプタ付"), _facts(), CFG))
    assert "PSE" in row["法令要確認"]


# -- まとめ売り（同一JANに単品と N個セットの ASIN がぶら下がる）----------------------
def test_商品名から入数を読む():
    # すべて実在の Amazon 出品名（NETSEA の単品JANにぶら下がっていたもの）。
    d = keepa_verify.detect_pack_size
    assert d("グロー球・ナツメ球お取り替えセット") == 1
    assert d("【3個セット】グロー球・ナツメ球セット") == 3
    assert d("【10個セット】変換名人 LAN 中継アダプタ") == 10
    assert d("変換名人 LAN 中継アダプタ LAN-BB ×10") == 10
    assert d("サンワサプライ コネクタカバー TK-CA×10") == 10


def test_ケース売りの入数を読む():
    # NETSEA は蒟蒻ゼリー1個117円、Amazon は48本入ケース6,798円。
    # 入数を1と読むと利益率77%という存在しない儲けが最上位に出る（実際に出た）。
    d = keepa_verify.detect_pack_size
    assert d("オリヒロ ぷるんと蒟蒻Plus グレープフルーツ味 130gパウチ×48本入") == 48
    assert d("オリヒロ ぷるんと凍らすアイス スタンディング(ST) グレープ 130gパウチ×48個入") == 48


def test_入れ子の掛け算は全部掛け合わせる():
    # 「(20gパウチ×12個)×12袋入」は内側だけでも外側だけでも12。正解は144。
    d = keepa_verify.detect_pack_size
    assert d("オリヒロ ぷるんと蒟蒻ゼリー 塩うめ+塩レモン (20gパウチ×12個)×12袋入") == 144
    assert d("オリヒロ ぷるんと凍らすアイス プレミアム バニラ (18g×10個)×12袋入") == 120


def test_型番や寸法の数字を入数と誤読しない():
    d = keepa_verify.detect_pack_size
    assert d("ヤザワ ステレオイヤホン 3m") == 1
    assert d("レフ形白熱ランプ 40W") == 1
    assert d("グロー球FG1E・5Pセット") == 1
    assert d("YAZAWA シャンデリア球 C32 E17") == 1
    assert d("抗菌まな板 20×30cm") == 1        # 寸法の × を掛け算と読まない


def test_まとめ売りは卸値を入数ぶん掛ける():
    # ここが抜けると「10個セットの売値 対 単品の卸値」になり、利益が嘘になる。
    single = keepa_verify.AmazonFacts(
        jan="j", asin="B1", title="グロー球", found=True, price_yen=3000,
        drops30=5, category_names=["ホーム&キッチン"],
        package_mm=(200, 150, 80), package_g=300, pack_size=1)
    ten = keepa_verify.AmazonFacts(**{**single.__dict__, "pack_size": 10,
                                      "title": "【10個セット】グロー球"})
    a = evaluate.evaluate(_cand(wholesale_ex_tax=200), single, CFG)
    b = evaluate.evaluate(_cand(wholesale_ex_tax=200), ten, CFG)
    assert abs(a.result.wholesale_price_incl_tax - 220) < 1
    assert abs(b.result.wholesale_price_incl_tax - 2200) < 1
    assert b.result.net_profit < a.result.net_profit


def test_まとめ売りであることを状態と列に出す():
    f = _facts(title="【5個セット】テスト", price_yen=1200)
    row = evaluate.to_row(evaluate.evaluate(_cand(wholesale_ex_tax=200), f, CFG))
    assert row["出品の入数"] == 5
    assert "ケース売り5倍" in row["状態"]
    assert row["NETSEA卸値(税込)"] == 1100      # 200 × 1.1 × 5
    assert "5倍" in row["入数の根拠"]


def test_同一JANなら単品を優先する_売れ行きが同じなら():
    def prod(asin, title, drops):
        return {"asin": asin, "title": title, "eanList": [1],
                "stats": {"current": [-1, 5000, -1, 100] + [0]*8,
                          "salesRankDrops30": drops}}
    pack = prod("BPACK", "【10個セット】グロー球", 5)
    single = prod("BSINGLE", "グロー球", 5)
    assert keepa_verify._pick_best([pack, single])["asin"] == "BSINGLE"


def test_売れている方が優先される_入数より売れ行きが強い():
    def prod(asin, title, drops):
        return {"asin": asin, "title": title, "eanList": [1],
                "stats": {"current": [-1, 5000, -1, 100] + [0]*8,
                          "salesRankDrops30": drops}}
    assert keepa_verify._pick_best([
        prod("BPACK", "【10個セット】グロー球", 50),
        prod("BSINGLE", "グロー球", 1),
    ])["asin"] == "BPACK"
