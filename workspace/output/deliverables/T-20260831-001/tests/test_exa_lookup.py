# -*- coding: utf-8 -*-
"""ExaLookupResolver と optout の単体テスト（T-20260904-004 / B-1）。"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.normalize import normalize_row  # noqa: E402
from pipeline.optout import is_personal_local_part  # noqa: E402
from pipeline.resolvers.exa_lookup import ExaLookupResolver  # noqa: E402
from pipeline.schema import CONF_CANDIDATE, CONF_CONFIRMED, CONF_UNKNOWN  # noqa: E402


def _row(name):
    return normalize_row(name, {})


class TestExaLookupResolver(unittest.TestCase):
    def _resolver(self, entries, extra_lines=()):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with io.open(path, "w", encoding="utf-8") as fp:
            for e in entries:
                fp.write(json.dumps(e, ensure_ascii=False) + "\n")
            for line in extra_lines:
                fp.write(line)
        self.addCleanup(os.remove, path)
        return ExaLookupResolver(path=path)

    def test_一致した社の値を返す(self):
        r = self._resolver([{
            "メーカー名": "あしあげ隊", "正式商号": "株式会社タツフト",
            "所在地": "東京都品川区西五反田2-15-7", "公式HP": "https://www.tatsufuto.co.jp/",
            "電話": "03-3779-6186", "確度": "確定", "出典URL": "https://www.tatsufuto.co.jp/office/",
            "取得日": "2026-09-04",
        }])
        got = r.resolve(_row("あしあげ隊"))
        self.assertIsNotNone(got)
        self.assertEqual(got.official_name, "株式会社タツフト")
        self.assertEqual(got.tel, "03-3779-6186")
        self.assertEqual(got.confidence, CONF_CONFIRMED)
        self.assertIn("2026-09-04", got.note)

    def test_未収載の社はNoneを返す(self):
        r = self._resolver([{"メーカー名": "あしあげ隊", "確度": "確定"}])
        self.assertIsNone(r.resolve(_row("存在しないメーカー")))

    def test_参考は候補に落とす(self):
        r = self._resolver([{"メーカー名": "X社", "正式商号": "株式会社X", "確度": "参考"}])
        self.assertEqual(r.resolve(_row("X社")).confidence, CONF_CANDIDATE)

    def test_確度の記載漏れは不明(self):
        r = self._resolver([{"メーカー名": "Y社", "正式商号": "株式会社Y"}])
        self.assertEqual(r.resolve(_row("Y社")).confidence, CONF_UNKNOWN)

    def test_壊れた行は読み飛ばす(self):
        r = self._resolver(
            [{"メーカー名": "Z社", "正式商号": "株式会社Z", "確度": "確定"}],
            extra_lines=['{"メーカー名": "途中で切れ'],
        )
        self.assertEqual(r.resolve(_row("Z社")).official_name, "株式会社Z")

    def test_括弧つき表記でも照合できる(self):
        r = self._resolver([{
            "メーカー名": "プロクソン(PROXXON)", "正式商号": "株式会社キソパワーツール",
            "電話": "06-6693-5351", "確度": "確定",
        }])
        self.assertIsNotNone(r.resolve(_row("プロクソン(PROXXON)")))
        self.assertIsNotNone(r.resolve(_row("PROXXON")))

    def test_ネットワークに出ない(self):
        self.assertFalse(ExaLookupResolver.needs_network)


# 旧 detect_optout（真偽値の1段判定）のテストは、法務の A〜E 判定への作り替えに伴い
# tests/test_optout_classes.py へ移管した。個人名ローカル部の判定も同ファイルに集約している。


if __name__ == "__main__":
    unittest.main()


