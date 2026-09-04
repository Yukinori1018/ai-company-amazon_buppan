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
from pipeline.optout import detect_optout, is_personal_local_part  # noqa: E402
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


class TestOptout(unittest.TestCase):
    def test_営業お断りを検出する(self):
        self.assertIsNotNone(detect_optout("営業目的のメールは固くお断りいたします。"))
        self.assertIsNotNone(detect_optout("セールスの電話・メールはご遠慮ください"))

    def test_営業時間は誤検知しない(self):
        text = "営業時間は9:00〜17:00です。" + "あ" * 300 + "在庫切れの場合はご注文をお断りすることがあります。"
        self.assertIsNone(detect_optout(text))

    def test_語が片方だけなら検出しない(self):
        self.assertIsNone(detect_optout("勧誘に関するご相談を承ります"))
        self.assertIsNone(detect_optout("returnはお断りします"))

    def test_空文字(self):
        self.assertIsNone(detect_optout(""))

    def test_個人名らしいローカル部(self):
        self.assertTrue(is_personal_local_part("t.suzuki@example.co.jp"))
        self.assertTrue(is_personal_local_part("taro_yamada@example.jp"))
        self.assertFalse(is_personal_local_part("info@example.co.jp"))
        self.assertFalse(is_personal_local_part("support@ottocast.co.jp"))
        self.assertFalse(is_personal_local_part("not-an-email"))


if __name__ == "__main__":
    unittest.main()


class TestOptoutFalsePositives(unittest.TestCase):
    """2026-09-04 に実データで踏んだ誤検知の再発防止（T-20260904-004 / B-1）。"""

    def test_窓口名を人名と誤認しない(self):
        for addr in (
            "Askfender.jp@fender.com",
            "customerservice.japan@ap.hasbro.com",
            "infobox@astro-p.co.jp",
        ):
            self.assertFalse(is_personal_local_part(addr), addr)
