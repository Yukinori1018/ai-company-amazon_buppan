# -*- coding: utf-8 -*-
"""ソース別のアクセス間隔スロットリング（共通層）。

ハルオ（法務）が「条件付き可」の条件としてアクセス頻度を指定してくる見込みなので、
秒数は設定値（config.json の throttle）で持つ。resolver 側に書かせない。

resolver が外部へ出るときは runner が必ずこの wait() を通す。
"""
from __future__ import annotations

import time
from typing import Callable, Dict


class Throttle:
    """ソース名ごとに「前回アクセスから最低 N 秒あける」を保証する。

    clock / sleeper を差し替えられるのはテストのため（実時間を待たない）。
    """

    def __init__(
        self,
        intervals: Dict[str, float],
        default_interval: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.intervals = dict(intervals or {})
        self.default_interval = default_interval
        self._clock = clock
        self._sleep = sleeper
        self._last: Dict[str, float] = {}

    def interval_for(self, source: str) -> float:
        return float(self.intervals.get(source, self.default_interval))

    def wait(self, source: str) -> float:
        """必要なだけ待つ。実際に待った秒数を返す（ログ用）。"""
        interval = self.interval_for(source)
        now = self._clock()
        last = self._last.get(source)
        waited = 0.0
        if last is not None:
            remaining = interval - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
                now = self._clock()
        self._last[source] = now
        return waited
