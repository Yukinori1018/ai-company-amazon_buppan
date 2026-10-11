#!/usr/bin/env python3
"""supplier_screen.py / discontinued.py / supplier_inputs.py のテスト（通信0）。

    python3 test_supplier_screen.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import discontinued as D          # noqa: E402
import supplier_inputs as SI      # noqa: E402
import supplier_screen as SS      # noqa: E402

NOW = 1791700000                   # Unix 秒（2026-10-11 頃）
KNOW = NOW // 60 - D.KEEPA_EPOCH_MIN
DAY = 1440


def series(points: list[tuple[int, int]]) -> list[int]:
    """[(何日前, 値)] → Keepa の [t, v, t, v ...]（古い順）。"""
    out = []
    for days_ago, v in sorted(points, key=lambda x: -x[0]):
        out += [KNOW - days_ago * DAY, v]
    return out


def product(**csvs) -> dict:
    c = [None] * 12
    for k, v in csvs.items():
        c[int(k[1:])] = series(v)
    return {"asin": "B000TEST00", "csv": c}


class TestLampRule(unittest.TestCase):
    def test_hits(self):
        cases = {
            "DNライティング エースライン スリム蛍光灯 FLR910T6EX-WW": "直管形",
            "パナソニック パルック 丸形 FCL30ECW/28": "環形",
            "東芝 ネオボールZ 電球形蛍光ランプ EFA10EL": "電球形",
            "ツイン蛍光灯 FPL27EX-N": "コンパクト形",
            "ＦＬ２０ＳＳ・ＥＸ－Ｎ／１８ 直管": "直管形",          # 全角でも当たる
            "DNライティング シームレスライン スリム蛍光灯 FRT850ED": "種類不明",
        }
        for t, kind in cases.items():
            self.assertEqual(D.lamp_kind(t), kind, t)
            self.assertEqual(D.check(None, t).verdict, D.NO_GO, t)

    def test_not_lamp(self):
        for t in ("LED蛍光灯 40W形 直管 昼白色", "蛍光灯カバー 40形", "蛍光ペン 5色セット",
                  "ゼブラ 蛍光マーカー", "蛍光灯スタンド用 アーム", "FLAT ファイル A4",
                  "ミニクリプトン電球 LED 40W相当"):
            self.assertIsNone(D.lamp_kind(t), t)
            self.assertEqual(D.check(None, t).verdict, D.PASS, t)

    def test_unconfirmed_rule_is_unknown(self):
        d = D.check(None, "朝日電器 白熱電球 E26 60W")
        self.assertEqual(d.verdict, D.UNKNOWN)
        self.assertIn("法令ではなく", d.label())

    def test_rule_has_source_url(self):
        d = D.check(None, "FLR40S・EX-N/M")
        self.assertIn(D.ENV_LAMP_URL, d.label())
        self.assertIn("2028-01-01", d.label())

    def test_wholesale_title_also_counts(self):
        self.assertEqual(D.check(None, "エースラインランプ", "FLR910T6EX-W 蛍光灯").verdict, D.NO_GO)


class TestSupplierWords(unittest.TestCase):
    def test_supplier_says_discontinued(self):
        d = D.check(None, "エステー オンパックス", "【エステー】オンパックス", "メーカー廃番・取扱終了と記載")
        self.assertEqual(d.verdict, D.NO_GO)

    def test_amazon_title_word_is_only_a_sign(self):
        self.assertEqual(D.check(None, "【在庫限り】ふきん 3枚").verdict, D.UNKNOWN)


class TestSigns(unittest.TestCase):
    def test_offer_cliff(self):
        p = product(c11=[(110, 5), (80, 4), (40, 4), (5, 1)], c3=[(3, 50000)])
        keys = {s.key for s in D.signs(p, NOW)}
        self.assertIn("offer_cliff", keys)
        self.assertEqual(D.check(p, "ふきん", now_unix=NOW).verdict, D.UNKNOWN)

    def test_no_cliff_when_always_few(self):
        p = product(c11=[(110, 1), (40, 1), (5, 1)], c3=[(3, 50000)])
        self.assertNotIn("offer_cliff", {s.key for s in D.signs(p, NOW)})

    def test_amazon_gone_alone_is_weak(self):
        p = product(c0=[(400, 980), (300, 990), (190, -1)], c3=[(2, 40000)])
        d = D.check(p, "ふきん", now_unix=NOW)
        self.assertEqual(d.verdict, D.PASS)          # 弱い兆候1つでは落とさない
        self.assertIn("弱い兆候", d.label() + " ".join(d.reasons))

    def test_dead_listing_with_alive_family_is_not_discontinued(self):
        p = product(c1=[(400, 1200), (300, -1)], c3=[(900, 30000), (800, -1)])
        self.assertEqual(D.check(p, "ドライニング ×10個セット", now_unix=NOW).verdict, D.UNKNOWN)
        d = D.check(p, "ドライニング ×10個セット", now_unix=NOW, family_alive=True)
        self.assertEqual(d.verdict, D.PASS)
        self.assertIn("出品単位の停止", " ".join(d.reasons))


class TestKz(unittest.TestCase):
    def test_counts_3pct_improvements_per_30_days(self):
        # 1か月目：10万→9万（10%改善）→8.9万（1.1%＝数えない）→7万（改善）
        pts = [(25, 100000), (20, 90000), (15, 89000), (10, 70000)]
        pts += [(45, 100000), (40, 80000)]                   # 2か月目：1回
        p = product(c3=pts)
        m, obs = SS.kz_months(p, NOW)
        self.assertEqual(m, [2, 1, 0])
        self.assertEqual(obs[:2], [4, 2])

    def test_reset_on_minus_one(self):
        p = product(c3=[(25, 100000), (20, -1), (15, 50000)])
        self.assertEqual(SS.kz_months(p, NOW)[0][0], 0)    # -1 を挟んだら比べない

    def test_no_observation_is_dead(self):
        p = product(c3=[(900, 30000), (800, -1)])
        st, why, _m, _a = SS.sales_gate(p, NOW)
        self.assertEqual(st, "FAIL")
        self.assertIn("観測が1回もない", why)

    def test_family_child_is_unknown(self):
        pts = [(d, 80000 if d % 2 else 100000) for d in range(1, 89)]   # 1日おきに20%改善
        p = product(c3=pts)
        p["parentAsin"] = "B0PARENT00"
        self.assertEqual(SS.sales_gate(p, NOW)[0], "UNKNOWN")


class TestShareAndOrder(unittest.TestCase):
    def test_share(self):
        sh, why = SS.share_of({"buyBoxEligibleOfferCounts": [2, 3, 0, 0]}, 12.0)
        self.assertAlmostEqual(sh, 2.0)
        self.assertIn("FBA 2", why)
        self.assertIsNone(SS.share_of({}, 12.0)[0])        # buybox 未取得なら決めない

    def test_roundrobin(self):
        rows = [{"仕入れ先": "A", "i": i} for i in range(3)] + [{"仕入れ先": "B", "i": i} for i in range(2)]
        order = [(r["仕入れ先"], r["i"]) for r in SS.roundrobin(rows, per=2)]
        self.assertEqual(order, [("A", 0), ("A", 1), ("B", 0), ("B", 1), ("A", 2)])
        self.assertEqual(len(order), 5)                     # 上限ではなく順番（全部残る）


class TestShareFloor(unittest.TestCase):
    def test_low_average_fails_without_buybox(self):
        # 3か月で2個しか動いていない棚は、出品者数を見なくても取り分3個/月に届かない
        pts = [(d, 100000) for d in range(1, 89)]
        pts[10] = (78, 80000)
        pts[50] = (38, 70000)
        p = product(c3=sorted(pts))
        st, why, m, avg = SS.sales_gate(p, NOW)
        self.assertEqual(st, "PASS")
        self.assertLess(avg, SS.MIN_SHARE)


class TestInputs(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(SI.parse_tiers("300x1/280x120/290x10"), [(300, 1), (290, 10), (280, 120)])
        self.assertEqual(SI.parse_tiers("400x24"), [(400, 24)])

    def test_normalize_keeps_leading_zero(self):
        r = SI.normalize_row({"JAN": "0490000000001", "卸単価": "300"})
        self.assertEqual(r["JAN"], "0490000000001")
        self.assertEqual(r["卸単価(税抜)"], "300")

    def test_sd_screen_uses_smallest_lot_price(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.csv").write_text(
                "SD品番,購入先URL,卸単価(税抜)x最小点数,最安の卸1点(税抜),在庫,確認時刻,確認者\n"
                "9000001,https://example.invalid/9000001/,300x1/290x10/280x200,280,品切れあり,2026-10-11 22:30,人\n",
                encoding="utf-8")
            (d / "r.json").write_text(json.dumps([
                {"product_id": "9000001", "jan": "4900000000009", "units_per_set": 10, "name": "x10"},
                {"product_id": "9000001", "jan": "4900000000009", "units_per_set": 1, "name": "単品",
                 "supplier": {"name": "テスト商事"}}]), encoding="utf-8")
            rows = SI.sd_screen(d / "s.csv", d / "r.json")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["卸単価(税抜)"], r["最小ロット"]), (300, 1))   # 保守側（最小ロットの段）
        self.assertEqual(r["在庫"], "一部品切れ")                          # 「在庫あり」に畳まない
        self.assertEqual(r["仕入れ先"], "テスト商事")
        self.assertIn("280円×200点", r["備考"])


class TestStore(unittest.TestCase):
    def test_cache_prefers_newer_and_borrows_buybox(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.jsonl"
            old = {"asin": "B0X", "eanList": ["4900000000001"], "title": "old",
                   "stats": {"buyBoxSellerId": "A1", "buyBoxIsAmazon": False},
                   "buyBoxEligibleOfferCounts": [1, 2, 0, 0]}
            new = {"asin": "B0X", "eanList": ["4900000000001"], "title": "new", "stats": {}}
            with f.open("w") as w:
                w.write(json.dumps({"asin": "B0X", "fetched": NOW - 86400, "product": old}) + "\n")
                w.write(json.dumps({"asin": "B0X", "fetched": NOW, "product": new}) + "\n")
                w.write(json.dumps({"asin": "B0Y", "fetched": NOW,
                                    "product": {"asin": "B0Y", "eanList": ["4999999999999"]}}) + "\n")
            st = SS.KeepaStore({"4900000000001"}, sources=[f], log=lambda *_: None)
        self.assertEqual(set(st.by_jan["4900000000001"]), {"B0X"})
        self.assertNotIn("B0Y", st.latest)                 # 対象外の JAN は読まない
        p, fetched, _src, note = st.product("B0X")
        self.assertEqual(p["title"], "new")
        self.assertEqual(p["stats"]["buyBoxSellerId"], "A1")
        self.assertEqual(p["buyBoxEligibleOfferCounts"], [1, 2, 0, 0])
        self.assertIn("カート情報は", note)

    def test_code_record_marks_jan_complete_even_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.jsonl"
            f.write_text(json.dumps({"code": "4900000000002", "fetched": NOW, "products": []}) + "\n")
            st = SS.KeepaStore({"4900000000002"}, sources=[f], log=lambda *_: None)
        self.assertIn("4900000000002", st.complete)


if __name__ == "__main__":
    unittest.main(verbosity=1)
