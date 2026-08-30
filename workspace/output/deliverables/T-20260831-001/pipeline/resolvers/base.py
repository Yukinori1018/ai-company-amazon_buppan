# -*- coding: utf-8 -*-
"""resolver のインターフェース。1ソース = 1モジュール。

新しいソースを足す手順（3行で終わる設計にしてある）:
  1. resolvers/<source>.py を作り、Resolver を継承して resolve() を書く
  2. モジュール末尾で register(YourResolver()) を呼ぶ
  3. config.json の enabled に名前を足す

**外部アクセスは runner が throttle を通してから resolve() を呼ぶ。**
resolver 側で sleep を書かないこと（間隔の一元管理が崩れる）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..schema import ContactFields, MakerRow, ALL_CLASSES


class Resolver(object):
    #: config.json / CLI から指定する名前。CSV の「取得手段」にも出る
    name = "base"
    #: 小さいほど強い（merge.PRIORITY_* を使う）
    priority = 100
    #: 既定のアクセス間隔（秒）。config.json の throttle で上書きできる
    min_interval_sec = 3.0
    #: この resolver が効く分類。None なら全分類
    applies_to = None  # type: Optional[List[str]]
    #: True なら外部へ出る。ハルオの適法性判定が出るまで runner が実行を拒む
    needs_network = False

    def applies(self, row: MakerRow) -> bool:
        if self.applies_to is None:
            return True
        return row.category in self.applies_to

    def resolve(self, row: MakerRow) -> Optional[ContactFields]:
        """1社ぶんの連絡先を返す。取れなければ None、または理由入りの空 ContactFields。

        **推測で埋めないこと。** 同名企業が複数あって特定できないなら、
        値は空のまま note に「同名企業が複数あり特定できず」と書いて返す。
        """
        raise NotImplementedError

    def close(self) -> None:
        """後始末（HTTP セッションを閉じる等）。不要なら実装しなくてよい。"""
        return None


# --- レジストリ -------------------------------------------------------------
_REGISTRY = {}  # type: Dict[str, Resolver]


def register(resolver: Resolver) -> Resolver:
    if resolver.applies_to is not None:
        unknown = set(resolver.applies_to) - set(ALL_CLASSES)
        if unknown:
            raise ValueError("未知の分類が applies_to にあります: %s" % sorted(unknown))
    _REGISTRY[resolver.name] = resolver
    return resolver


def get(name: str) -> Resolver:
    if name not in _REGISTRY:
        raise KeyError(
            "resolver '%s' は未登録です（登録済み: %s）" % (name, sorted(_REGISTRY))
        )
    return _REGISTRY[name]


def available() -> List[str]:
    return sorted(_REGISTRY)


def clear() -> None:
    """テスト用。"""
    _REGISTRY.clear()
