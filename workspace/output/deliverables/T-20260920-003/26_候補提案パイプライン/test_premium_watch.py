"""premium_watch の検算（2026-10-12 タカシ）。python3 test_premium_watch.py"""
import importlib.util
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import premium_watch as W  # noqa: E402


def _hist(day, price, m1=10, fba=0, fbm=1, amazon="0"):
    return {"日付": day, "ASIN": "BTEST", "カート価格": price, "新品最安": "", "カートは本体": amazon,
            "カート対象FBA": fba, "カート対象自己発送": fbm, "kz_m1": m1,
            "FBA配送代行(Keepa)": 675, "販売手数料率(Keepa)": 15.4}


W0 = {"ASIN": "BTEST", "商品名": "t", "追加日": "2026-10-12", "追加理由": "x",
      "Amazon1個あたり原価(税込)": 6148, "最小ロット(Amazon個)": 10, "1年中央値(追加時)": 3284}


def test_before_sale_is_cost_only():
    r = W.simulate(W0, [_hist("2026-10-12", 9130)], date(2026, 10, 12))
    assert r["売れた個数"] == 0 and r["現金損益"] == -61480, r


def test_sales_after_lead_and_amazon_cart_blocks():
    obs = [_hist("2026-10-12", 9130), _hist("2026-11-02", 9130)]
    r = W.simulate(W0, obs, date(2026, 11, 11))       # 11/02〜11/11 の10日 × 5個/月 ÷30
    assert abs(r["売れた個数"] - round(10 * 5 / 30, 1)) < 0.11, r
    obs2 = [_hist("2026-10-12", 9130), _hist("2026-11-02", 9130, amazon="1")]
    r2 = W.simulate(W0, obs2, date(2026, 11, 11))
    assert r2["売れた個数"] == 0, r2


def test_deterministic():
    obs = [_hist("2026-10-12", 9130), _hist("2026-11-02", 8000)]
    a = W.simulate(W0, obs, date(2026, 12, 7))
    b = W.simulate(W0, list(reversed(obs)), date(2026, 12, 7))
    assert a == b


def test_no_cost_no_pnl():
    w = dict(W0, **{"Amazon1個あたり原価(税込)": ""})
    r = W.simulate(w, [_hist("2026-10-12", 9130)], date(2026, 10, 12))
    assert "現金損益" not in r and "原価未確認" in r["注意"]


def test_kz_same_as_kz_estimate():
    """キーゾン再現式が agent_output の kz_estimate.py と同じ値を返す（手元に生データがあれば）。"""
    src = W.WORK / "ledger20261010/kz_estimate.py"
    raw = W.WORK / "ledger20261010/keepa_unknown_20261011.jsonl"
    if not (src.exists() and raw.exists()):
        print("  skip（kz_estimate.py / 生データなし）")
        return
    spec = importlib.util.spec_from_file_location("kz", src)
    kz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kz)
    n = 0
    for a, d in W._iter_raw([raw]):
        now = d["fetched"] // 60 - W.KEEPA_T0
        assert W.kz_months(d["product"], d["fetched"]) == kz.months(d["product"], now), a
        n += 1
        if n >= 200:
            break
    assert n > 0


def test_fair_price_flag_and_off_amazon_pessimistic():
    off = {"Amazon外最安(税込)": 6065, "確認日": "2026-10-12"}
    r = W.simulate(W0, [_hist("2026-10-12", 9130)], date(2026, 10, 12), off)
    assert r["公正価格の恐れ"] == "恐れあり" and r["倍率(Amazon/Amazon外)"] == 1.51, r
    assert r["悲観損益(全数をAmazon外最安で)"] > r["悲観損益(全数を1年中央値で)"], r   # 6,065 > 平常 3,284
    r2 = W.simulate(W0, [_hist("2026-10-12", 7000)], date(2026, 10, 12), off)
    assert r2["公正価格の恐れ"] == "", r2


if __name__ == "__main__":
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            try:
                f()
                print("PASS", k)
            except AssertionError as e:
                fails += 1
                print("FAIL", k, e)
    sys.exit(1 if fails else 0)
