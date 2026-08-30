# -*- coding: utf-8 -*-
"""運用要件のテスト: スロットリング・冪等・再開可能・ネットワーク門番。

「電源断で中断 → 再開できずやり直し」を二度と起こさないための回帰テスト。
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import resolvers as resolver_pkg  # noqa: E402
from pipeline.resolvers.base import Resolver, register  # noqa: E402
from pipeline.runner import run, select_resolvers  # noqa: E402
from pipeline.schema import ContactFields, CONF_CONFIRMED, CLS_EN_BRAND  # noqa: E402
from pipeline.store import ContactStore  # noqa: E402
from pipeline.throttle import Throttle  # noqa: E402


class FakeClock(object):
    """実時間を待たずにスロットリングを検証するための時計。"""

    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class TestThrottle(unittest.TestCase):
    def test_waits_the_configured_interval(self):
        clock = FakeClock()
        t = Throttle({"src": 5.0}, clock=clock, sleeper=clock.sleep)
        self.assertEqual(t.wait("src"), 0.0)     # 初回は待たない
        self.assertEqual(t.wait("src"), 5.0)     # 直後の2回目は5秒待つ

    def test_elapsed_time_counts(self):
        clock = FakeClock()
        t = Throttle({"src": 5.0}, clock=clock, sleeper=clock.sleep)
        t.wait("src")
        clock.now += 4.0
        self.assertEqual(t.wait("src"), 1.0)     # 残り1秒だけ待つ

    def test_no_wait_when_enough_time_passed(self):
        clock = FakeClock()
        t = Throttle({"src": 5.0}, clock=clock, sleeper=clock.sleep)
        t.wait("src")
        clock.now += 99.0
        self.assertEqual(t.wait("src"), 0.0)

    def test_interval_is_per_source(self):
        clock = FakeClock()
        t = Throttle({"a": 5.0, "b": 5.0}, clock=clock, sleeper=clock.sleep)
        t.wait("a")
        self.assertEqual(t.wait("b"), 0.0)       # 別ソースは影響しない

    def test_default_interval_applies_to_unknown_source(self):
        clock = FakeClock()
        t = Throttle({}, default_interval=7.0, clock=clock, sleeper=clock.sleep)
        t.wait("x")
        self.assertEqual(t.wait("x"), 7.0)


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="contacts-test-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestStore(TempDirCase):
    def _row(self, name, website=""):
        return {"メーカー名": name, "正規化名": name, "分類": CLS_EN_BRAND,
                "公式HP": website, "確度": CONF_CONFIRMED if website else "不明"}

    def test_append_survives_a_new_process(self):
        s1 = ContactStore(self.dir)
        s1.append(self._row("Anker", "https://anker.example"))
        s2 = ContactStore(self.dir)          # 別プロセス相当（電源断からの再開）
        self.assertTrue(s2.is_done("Anker"))
        self.assertEqual(s2.records()[0]["公式HP"], "https://anker.example")

    def test_broken_last_line_is_skipped_not_fatal(self):
        s = ContactStore(self.dir)
        s.append(self._row("Anker", "https://anker.example"))
        with io.open(s.records_path, "a", encoding="utf-8") as fp:
            fp.write('{"メーカー名": "途中で電源が')   # 書きかけの行
        reopened = ContactStore(self.dir)
        self.assertEqual(reopened.done_count(), 1)

    def test_reprocessing_overwrites_last_wins(self):
        s = ContactStore(self.dir)
        s.append(self._row("Anker"))
        s.append(self._row("Anker", "https://anker.example"))
        self.assertEqual(s.done_count(), 1)
        self.assertEqual(s.records()[0]["公式HP"], "https://anker.example")

    def test_fill_stats(self):
        s = ContactStore(self.dir)
        s.append(self._row("A", "https://a.example"))
        s.append(self._row("B"))
        stats = s.fill_stats()
        self.assertEqual(stats["処理済み件数"], 2)
        self.assertEqual(stats["連絡先が1つ以上埋まった件数"], 1)
        self.assertEqual(stats["埋まり率"], 0.5)

    def test_csv_is_regenerated_in_input_order(self):
        s = ContactStore(self.dir)
        s.append(self._row("B"))
        s.append(self._row("A"))
        path = s.write_csv(os.path.join(self.dir, "out.csv"), order=["A", "B"])
        with io.open(path, encoding="utf-8-sig") as fp:
            lines = fp.read().splitlines()
        self.assertTrue(lines[0].startswith("メーカー名,"))
        self.assertTrue(lines[1].startswith("A,"))
        self.assertTrue(lines[2].startswith("B,"))


class DummyResolver(Resolver):
    name = "テスト用ダミー"
    priority = 10
    needs_network = False

    def __init__(self):
        self.calls = []

    def resolve(self, row):
        self.calls.append(row.raw_name)
        if row.raw_name == "Anker":
            return ContactFields(website="https://anker.example", source=self.name,
                                 source_url="https://anker.example/company",
                                 confidence=CONF_CONFIRMED)
        return ContactFields(source=self.name, note="該当なし")


class NetworkResolver(DummyResolver):
    name = "テスト用ネットワーク"
    needs_network = True


class TestRunner(TempDirCase):
    def setUp(self):
        TempDirCase.setUp(self)
        self.input_csv = os.path.join(self.dir, "input.csv")
        with io.open(self.input_csv, "w", encoding="utf-8-sig", newline="") as fp:
            fp.write("メーカー/ブランド,該当商品数\nAnker,5\nUGREEN,3\nノーブランド品,1\n")
        self.dummy = register(DummyResolver())
        self.net = register(NetworkResolver())
        self.config = {
            "input_csv": self.input_csv,
            "input_name_column": "メーカー/ブランド",
            "output_csv": "out.csv",
            "enabled": [self.dummy.name],
            "allow_network": False,
            "throttle": {},
            "status_every": 1,
        }

    def test_run_produces_csv_and_stats(self):
        stats = run(self.config, out_dir=self.dir, verbose=False)
        self.assertEqual(stats["処理済み件数"], 3)
        self.assertEqual(stats["連絡先が1つ以上埋まった件数"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "out.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "state", "STATUS.json")))

    def test_second_run_skips_everything(self):
        run(self.config, out_dir=self.dir, verbose=False)
        self.dummy.calls = []
        stats = run(self.config, out_dir=self.dir, verbose=False)
        self.assertEqual(self.dummy.calls, [])          # 再取得しない
        self.assertEqual(stats["処理済み件数"], 3)       # 結果は保たれる

    def test_limit_then_resume(self):
        run(self.config, limit=1, out_dir=self.dir, verbose=False)
        self.assertEqual(len(self.dummy.calls), 1)
        run(self.config, out_dir=self.dir, verbose=False)
        self.assertEqual(len(self.dummy.calls), 3)      # 続きの2件だけ足された

    def test_network_resolver_is_blocked_until_legal_clears_it(self):
        self.config["enabled"] = [self.net.name]
        with self.assertRaises(RuntimeError) as ctx:
            select_resolvers(self.config)
        self.assertIn("allow_network", str(ctx.exception))

    def test_resolver_exception_does_not_stop_the_run(self):
        class Exploding(Resolver):
            name = "テスト用例外"
            priority = 5

            def resolve(self, row):
                raise ValueError("boom")

        register(Exploding())
        self.config["enabled"] = ["テスト用例外", self.dummy.name]
        stats = run(self.config, out_dir=self.dir, verbose=False)
        self.assertEqual(stats["処理済み件数"], 3)


if __name__ == "__main__":
    unittest.main()
