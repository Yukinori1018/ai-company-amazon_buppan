# -*- coding: utf-8 -*-
"""Exa（web_search_exa / web_fetch_exa）で取得した連絡先を取り込む resolver。

**なぜオフライン resolver なのか（重要）**

Exa はこの環境では MCP サーバ（https://mcp.exa.ai/mcp）経由でしか使えません。
API キーが無いため Python から直接叩けず、`requests` を書いても動きません。
したがって役割分担はこうなります。

    エージェント（タカシ）が Exa を叩く
        → 結果を data/exa_lookups.jsonl に1社1行で追記
        → この resolver がそれを読んでマージする

結果として **needs_network = False** です。ネットワークには一切出ないので、
config.json の `allow_network` が false のままでも動きます（法務ゲートに触れない）。

Exa API キーを調達できたら（＝有料契約＝CLAUDE.md §4.1 で社長承認が要る）、
本 resolver を needs_network=True の実オンライン版に差し替えられます。
そのときも JSONL の形は変えないでください。

**優先度について**

検索由来なので PRIORITY_SEARCH（30）＝一番弱い。既取得55社や公的DBの値があれば
そちらが勝ちます。ただし「空欄には勝てない」ので、埋まっていない列だけを埋めます。

JSONL の1行（すべて文字列。取れなかった項目は空文字。**推測で埋めない**）:
    {"メーカー名": "...", "正式商号": "...", "法人番号": "", "所在地": "...",
     "公式HP": "...", "電話": "...", "問い合わせフォームURL": "", "メール": "",
     "出典URL": "https://... ; https://...", "確度": "確定|参考|不明",
     "備考": "...", "取得日": "2026-09-04"}
"""
from __future__ import annotations

import io
import json
import os
from typing import Dict, Optional

from ..merge import PRIORITY_SEARCH
from ..normalize import match_key, extract_variants
from ..schema import (
    ContactFields,
    MakerRow,
    CONF_CONFIRMED,
    CONF_CANDIDATE,
    CONF_UNKNOWN,
)
from .base import Resolver, register

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "exa_lookups.jsonl",
)

#: JSONL 側の確度表記 → schema の3値。
#: 「参考」は第三者DB・二次情報のみで裏が取れていない状態なので「候補」に落とす。
_CONFIDENCE_MAP = {
    "確定": CONF_CONFIRMED,
    "候補": CONF_CANDIDATE,
    "参考": CONF_CANDIDATE,
    "不明": CONF_UNKNOWN,
    "": CONF_UNKNOWN,
}


class ExaLookupResolver(Resolver):
    name = "Exa検索(エージェント取得)"
    priority = PRIORITY_SEARCH
    needs_network = False

    def __init__(self, path: str = None):
        self.path = path or DEFAULT_PATH
        self._index = None  # type: Optional[Dict[str, dict]]

    # --- 読み込み -----------------------------------------------------------
    def _load(self) -> Dict[str, dict]:
        if self._index is not None:
            return self._index
        index = {}  # type: Dict[str, dict]
        if os.path.exists(self.path):
            with io.open(self.path, encoding="utf-8") as fp:
                for lineno, line in enumerate(fp, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        # 書きかけの壊れた行は読み飛ばす（電源断耐性。store.py と同じ方針）
                        continue
                    maker = (entry.get("メーカー名") or "").strip()
                    if not maker:
                        continue
                    primary, aliases = extract_variants(maker)
                    for text in [primary] + aliases:
                        key = match_key(text)
                        if len(key) >= 2:
                            # 後勝ち（同じメーカーを取り直したら新しい行を採る）
                            index[key] = entry
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

        def g(k):
            return (entry.get(k) or "").strip()

        confidence = _CONFIDENCE_MAP.get(g("確度"), CONF_UNKNOWN)

        note_parts = []
        if g("備考"):
            note_parts.append(g("備考"))
        if g("取得日"):
            note_parts.append("Exa取得日:%s" % g("取得日"))

        return ContactFields(
            official_name=g("正式商号"),
            corporate_number=g("法人番号"),
            address=g("所在地"),
            website=g("公式HP"),
            tel=g("電話"),
            contact_form=g("問い合わせフォームURL"),
            email=g("メール"),
            source=self.name,
            source_url=g("出典URL"),
            confidence=confidence,
            note=" / ".join(note_parts),
        )


register(ExaLookupResolver())
