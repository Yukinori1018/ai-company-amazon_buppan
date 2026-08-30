# -*- coding: utf-8 -*-
"""【雛形】ソースが決まったらこのファイルをコピーして使う。

このファイル自体は register() していないので、置いてあるだけでは動かない。

差し込み手順:
  1. cp TEMPLATE_source.py houjin_bangou.py  （ソース名でファイルを作る）
  2. name / priority / applies_to / needs_network を埋める
  3. resolve() を実装する
  4. 末尾の register(...) のコメントを外す
  5. ../config.json の "enabled" に name を足し、"throttle" に間隔（秒）を足す

守ること:
  - **推測で埋めない。** 特定できなければ値は空、note に理由を書く
  - sleep を書かない。アクセス間隔は runner が throttle 経由で保証する
  - 出典URL（source_url）を必ず入れる。入らないなら confidence は「候補」以下
  - 資格情報は .env / 環境変数から読む。コードに直書きしない
"""
from __future__ import annotations

from typing import Optional

from ..merge import PRIORITY_PUBLIC_DB  # or PRIORITY_OFFICIAL_SITE / PRIORITY_SEARCH
from ..schema import (
    ContactFields,
    MakerRow,
    CONF_CONFIRMED,
    CONF_CANDIDATE,
    CONF_UNKNOWN,
    CLS_JP_CORP,
)
from .base import Resolver, register


class TemplateResolver(Resolver):
    name = "ソース名をここに"
    priority = PRIORITY_PUBLIC_DB
    min_interval_sec = 3.0
    applies_to = [CLS_JP_CORP]   # 効く分類だけに絞ると無駄打ちが減る
    needs_network = True         # 外部に出るなら True（法務判定が済むまで runner が止める）

    def resolve(self, row: MakerRow) -> Optional[ContactFields]:
        # 1. row.match_keys / row.normalized_name / row.aliases で検索する
        # 2. 候補が0件 → 理由入りの空 ContactFields を返す
        # 3. 候補が複数 → 値は空のまま confidence=候補、note に「同名企業が複数」
        # 4. 1件に確定 → 値を詰めて confidence=確定、source_url に実際に見たURL
        raise NotImplementedError

        # 実装例:
        # hits = client.search(row.normalized_name)
        # if not hits:
        #     return ContactFields(source=self.name, confidence=CONF_UNKNOWN,
        #                          note="該当なし")
        # if len(hits) > 1:
        #     return ContactFields(source=self.name, confidence=CONF_CANDIDATE,
        #                          note="同名企業が%d件あり特定できず" % len(hits))
        # h = hits[0]
        # return ContactFields(
        #     official_name=h["name"], corporate_number=h["number"],
        #     address=h["address"], source=self.name, source_url=h["url"],
        #     confidence=CONF_CONFIRMED)


# register(TemplateResolver())   # ← 実装したらコメントを外す
