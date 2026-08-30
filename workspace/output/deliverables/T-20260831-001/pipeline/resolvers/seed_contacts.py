# -*- coding: utf-8 -*-
"""既取得55社（T-20260804-001）を再取得しないためのオフライン resolver。

入力: workspace/output/deliverables/T-20260804-001/contacts_batch1-4.json
      （2026-08-05 にサブエージェント4班が1社ずつ Web を読んで確認した実績）

人が公式サイトを実物確認した結果なので、優先度は最強（PRIORITY_HUMAN_VERIFIED）。
ネットワークには一切出ない。
"""
from __future__ import annotations

import glob
import io
import json
import os
from typing import Dict, List, Optional

from ..merge import PRIORITY_HUMAN_VERIFIED
from ..normalize import match_key, extract_variants
from ..schema import (
    ContactFields,
    MakerRow,
    CONF_CONFIRMED,
    CONF_UNKNOWN,
)
from .base import Resolver, register

DEFAULT_GLOB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "T-20260804-001", "contacts_batch*.json",
)


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


class SeedContactsResolver(Resolver):
    name = "既取得55社(T-20260804-001)"
    priority = PRIORITY_HUMAN_VERIFIED
    needs_network = False

    def __init__(self, pattern: str = None):
        self.pattern = pattern or DEFAULT_GLOB
        self._index = None  # type: Optional[Dict[str, dict]]

    # --- 読み込み -----------------------------------------------------------
    def _load(self) -> Dict[str, dict]:
        if self._index is not None:
            return self._index
        index = {}  # type: Dict[str, dict]
        for path in sorted(glob.glob(self.pattern)):
            with io.open(path, encoding="utf-8") as fp:
                for entry in json.load(fp):
                    maker = (entry.get("maker") or "").strip()
                    if not maker:
                        continue
                    primary, aliases = extract_variants(maker)
                    for text in [primary] + aliases:
                        key = match_key(text)
                        if len(key) >= 2:
                            # 先勝ち（同一メーカーの重複エントリがある）
                            index.setdefault(key, entry)
        self._index = index
        return index

    # --- 解決 ---------------------------------------------------------------
    def resolve(self, row: MakerRow) -> Optional[ContactFields]:
        index = self._load()
        entry = None
        for key in row.match_keys:
            if key in index:
                entry = index[key]
                break
        if entry is None:
            return None

        email = (entry.get("email") or "").strip()
        # 55社の実績では email 欄に問い合わせフォームURLが入っている行がある。
        # 列の意味を取り違えないよう、URL かどうかで振り分ける（推測ではなく形で判定）。
        contact_form = ""
        if _is_url(email):
            contact_form, email = email, ""

        website = (entry.get("official_url") or "").strip()
        note_parts = []
        if entry.get("note"):
            note_parts.append(entry["note"])
        if entry.get("kind"):
            note_parts.append("規模:%s" % entry["kind"])
        note_parts.append("元メーカー名表記:%s" % entry.get("maker", ""))

        return ContactFields(
            website=website,
            tel=(entry.get("tel") or "").strip(),
            contact_form=contact_form,
            email=email,
            source=self.name,
            source_url=(entry.get("source_url") or "").strip(),
            confidence=CONF_CONFIRMED if website else CONF_UNKNOWN,
            note=" / ".join(p for p in note_parts if p),
        )


register(SeedContactsResolver())
