# -*- coding: utf-8 -*-
"""複数ソースの結果を優先順位でマージする層。

原則:
- 列ごとに、**優先度の高いソースが持っている値**を採る（空欄は勝てない）
- 値を1つでも提供したソースだけを「取得手段」「出典URL」に記録する
- 確度は**寄与したソースの中で一番弱いもの**に合わせる（安全側に倒す）
- 何も取れなければ空欄のまま。**埋めるための推測はしない**
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .schema import ContactFields, CONF_UNKNOWN, worst_confidence

# 優先度の既定値（小さいほど強い）。resolver 側で priority を持たせる。
PRIORITY_HUMAN_VERIFIED = 5   # 人が公式サイトを実物確認した実績（T-20260804-001 の55社）
PRIORITY_PUBLIC_DB = 10       # 公的DB（法人番号など）
PRIORITY_OFFICIAL_SITE = 20   # 公式サイト本体
PRIORITY_SEARCH = 30          # 検索結果ベースの推定


def merge(results: Iterable[Tuple[int, ContactFields]]) -> ContactFields:
    """(priority, ContactFields) の並びを1つに畳む。

    priority が同じ場合は渡された順（先勝ち）。
    """
    ordered: List[Tuple[int, ContactFields]] = sorted(
        list(enumerate(results)), key=lambda pair: (pair[1][0], pair[0])
    )
    ordered = [item[1] for item in ordered]

    merged = ContactFields()
    contributors: List[ContactFields] = []
    notes: List[str] = []

    for _priority, contact in ordered:
        if contact is None:
            continue
        used = False
        for field_name in ContactFields.VALUE_FIELDS:
            value = (getattr(contact, field_name) or "").strip()
            if value and not getattr(merged, field_name):
                setattr(merged, field_name, value)
                used = True
        if used:
            contributors.append(contact)
        if contact.note:
            notes.append("[%s] %s" % (contact.source or "?", contact.note))

    merged.source = " ; ".join(
        dict.fromkeys(c.source for c in contributors if c.source)
    )
    merged.source_url = " ; ".join(
        dict.fromkeys(c.source_url for c in contributors if c.source_url)
    )
    merged.confidence = (
        worst_confidence([c.confidence for c in contributors])
        if contributors
        else CONF_UNKNOWN
    )
    merged.note = " / ".join(dict.fromkeys(notes))
    return merged
