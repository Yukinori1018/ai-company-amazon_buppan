"""profit2026 の固定テスト。`python3 -m pytest test_profit2026.py -q`"""
import profit2026 as P


def test_大口なので基本成約料は0():
    p = P.breakdown(price=3000, wholesale_incl=1500, category_key="default",
                    package_mm=[200, 100, 50], package_g=300)
    assert [ln for ln in p.lines if ln.label == "基本成約料"][0].yen == 0


def test_引き算が合う():
    p = P.breakdown(price=3000, wholesale_incl=1500, category_key="default",
                    package_mm=[200, 100, 50], package_g=300)
    assert abs(p.price - sum(ln.yen for ln in p.lines) - p.net) < 1e-6


def test_広告10パーセントは売価基準():
    p = P.breakdown(price=3000, wholesale_incl=1500, category_key="default",
                    package_mm=[], package_g=None, ad_rate=0.10)
    assert p.ad == 300


def test_750円超はカテゴリ料率で消費税込み():
    p = P.breakdown(price=3000, wholesale_incl=1000, category_key="default",
                    package_mm=[], package_g=None)
    assert abs(p.referral_fee - 3000 * 0.154 * 1.1) < 1e-6


def test_寸法不明は標準2で仮置きし保管料は未計上():
    p = P.breakdown(price=3000, wholesale_incl=1000, category_key="default",
                    package_mm=[], package_g=None)
    assert p.size_label.startswith("不明")
    assert [ln for ln in p.lines if ln.label == "保管料"][0].yen == 0


def test_セットの梱包は最短辺を足し重量を合計する():
    dims, g = P.combine_packages([([200, 100, 30], 200), ([150, 120, 40], 300)])
    assert dims == [200, 120, 70] and g == 500


def test_片方でも寸法が無ければセットの寸法は不明():
    dims, g = P.combine_packages([([200, 100, 30], 200), ([], 300)])
    assert dims == [] and g == 500


def test_G3_はFBA25パーセントを別に返す():
    p = P.breakdown(price=3000, wholesale_incl=1200, category_key="beauty",
                    package_mm=[200, 100, 30], package_g=200)
    a, b = P.passes_g3(p)
    assert a is True  # 利益額・率は通る
    assert b == (p.fba_fee <= 0.25 * p.net)
