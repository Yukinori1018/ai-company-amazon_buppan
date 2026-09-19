"""行儀のよい HTTP 取得。並列なし・間隔あり・robots.txt 尊重・キャッシュあり。

ポリシーの数値は config.py に集約してある。ここは「守る仕組み」だけ。
根拠は `05_リスト拡充の法務判定.md`（ハルオ 2026-09-20）§2-3・§2-4・§6。

守らせていること:
  - 同一ホストへの最小間隔。robots.txt に Crawl-delay があれば大きい方を採る
  - robots.txt の **404 と 403 を区別する**（下の「一番間違えやすいところ」）
  - 403 / 429 / 5xx が1回でも出たホストは即時・永久に打ち切る（同一実行内）
  - 1日の総リクエスト数の上限を**プロセスをまたいで**数える
  - 実行時間帯の制限（09:00〜21:00 JST）
  - 自社HP側の利用規約に「スクレイピング禁止」等があればドメインごと停止
  - 取得済みはディスクキャッシュから返す（再実行でリクエストを増やさない）

一番間違えやすいところ（05 §2-3）:
  robots.txt が **404 = 拒否の宣言が存在しない = 取得してよい**。
  **403 / 5xx / タイムアウト = サーバが拒んでいる = そのホストは打ち切る**。
  この2つを一緒に「取得失敗＝許可なし」と扱うと、NAPAC・日本ペット用品工業会・
  日本釣用品工業会の3本（計394社）が理由なく落ちる。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from . import config as C

# get() が返す負のステータス（取得しなかった理由）
SKIP_ROBOTS = -1        # robots.txt で不許可
SKIP_QUOTA = -2         # 1日の上限超過
SKIP_TIME = -3          # 時間帯の制限
SKIP_ERROR = -4         # 通信エラー
SKIP_BLOCKED = -5       # このホストは打ち切り済み
SKIP_TOS = -6           # サイトの規約にスクレイピング禁止の文言
SKIP_FORBIDDEN = -7     # 団体ごとの個別条件で取得禁止のパス

REASON = {
    SKIP_ROBOTS: "robots.txtで不許可", SKIP_QUOTA: "1日の上限に到達",
    SKIP_TIME: "時間帯の制限（09-21時 JST）", SKIP_ERROR: "通信エラー",
    SKIP_BLOCKED: "このホストは打ち切り済み", SKIP_TOS: "サイト規約に自動取得の禁止文言",
    SKIP_FORBIDDEN: "個別条件で取得禁止のパス",
}


class Quota:
    """1日のリクエスト数をプロセスをまたいで数える。

    シャード実行やスクリプトの再実行で上限が何倍にもなるのを防ぐ。
    厳密なロックはしない（多少の数え漏れより、上限が効くことの方が大事）。
    """

    def __init__(self, limit: int, name: str = "all"):
        self.limit = limit
        self.path = os.path.join(C.WORK_DIR, f"quota_{C.today()}.json")
        self.name = name

    def _read(self) -> dict:
        try:
            return json.load(open(self.path, encoding="utf-8"))
        except Exception:
            return {}

    @property
    def used(self) -> int:
        return int(self._read().get(self.name, 0))

    def add(self, n: int = 1) -> None:
        d = self._read()
        d[self.name] = int(d.get(self.name, 0)) + n
        os.makedirs(C.WORK_DIR, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(d, fh)

    def left(self) -> int:
        return max(0, self.limit - self.used)


class Fetcher:
    def __init__(self, min_interval: float, cache_dir: str | None = None,
                 daily_limit: int = C.DAILY_REQUEST_LIMIT, quota_name: str = "all"):
        self.min_interval = min_interval
        self.cache_dir = cache_dir or C.CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.quota = Quota(daily_limit, quota_name)
        self.count = 0
        self.blocked: dict[str, str] = {}      # host -> 打ち切りの理由
        self._last: dict[str, float] = {}
        self._rules: dict[str, tuple[RobotFileParser | None, float]] = {}

    # ── キャッシュ ──────────────────────────────────────────────
    def _path(self, url: str) -> str:
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".html")

    # ── robots.txt ──────────────────────────────────────────────
    def _robots(self, url: str) -> tuple[RobotFileParser | None, float]:
        """(パーサ, crawl_delay) を返す。取得できないホストは self.blocked に入れる。"""
        p = urlparse(url)
        host = p.netloc
        if host in self._rules:
            return self._rules[host]

        robots_url = f"{p.scheme}://{host}/robots.txt"
        status, body = self._raw_get(robots_url, count_quota=False)
        rp: RobotFileParser | None = None
        delay = 0.0
        if status == 200:
            rp = RobotFileParser()
            rp.parse(body.splitlines())
            try:
                d = rp.crawl_delay(C.USER_AGENT)
                delay = float(d) if d else 0.0
            except Exception:
                delay = 0.0
        elif status == 404 or (400 <= status < 500 and status not in (401, 403, 429)):
            # 404 = 拒否の宣言が存在しない。取得してよい（05 §2-3）。
            rp = None
        else:
            # 403 / 429 / 5xx / 通信エラー = サーバが拒んでいる。このホストは打ち切り。
            self.blocked[host] = f"robots.txt が {status}"
        self._rules[host] = (rp, delay)
        return self._rules[host]

    def allowed(self, url: str) -> bool:
        rp, _delay = self._robots(url)
        if urlparse(url).netloc in self.blocked:
            return False
        return True if rp is None else rp.can_fetch(C.USER_AGENT, url)

    def _wait(self, host: str) -> None:
        rp_delay = self._rules.get(host, (None, 0.0))[1]
        interval = max(self.min_interval, rp_delay)   # 大きい方を採る（05 §2-4）
        last = self._last.get(host)
        if last is not None:
            gap = interval - (time.time() - last)
            if gap > 0:
                time.sleep(gap)
        self._last[host] = time.time()

    # ── 本体 ────────────────────────────────────────────────────
    def _raw_get(self, url: str, count_quota: bool = True) -> tuple[int, str]:
        """間隔と回数だけ守って1本叩く。robots 判定はしない（robots.txt 自身にも使う）。"""
        host = urlparse(url).netloc
        self._wait(host)
        if count_quota:
            self.count += 1
            self.quota.add(1)
        req = urllib.request.Request(url, headers={
            "User-Agent": C.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain",
            "Accept-Language": "ja,en;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=C.TIMEOUT_SEC) as resp:
                raw = resp.read(C.MAX_BODY_BYTES)
                return resp.status, _decode(raw, resp.headers.get_content_charset())
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception:
            return SKIP_ERROR, ""

    def get(self, url: str, *, use_cache: bool = True,
            forbidden_paths: tuple[str, ...] = ()) -> tuple[int, str, str]:
        """(status, 本文, 最終URL) を返す。取得しなかったときの status は負の数（REASON 参照）。"""
        host = urlparse(url).netloc
        if any(fp in url for fp in forbidden_paths):
            return SKIP_FORBIDDEN, "", url
        if host in self.blocked:
            return SKIP_BLOCKED, "", url

        p = self._path(url)
        if use_cache and os.path.exists(p):
            return 200, open(p, encoding="utf-8", errors="ignore").read(), url
        if not C.in_daytime():
            return SKIP_TIME, "", url
        if self.quota.left() <= 0:
            return SKIP_QUOTA, "", url
        if not self.allowed(url):
            return (SKIP_BLOCKED if host in self.blocked else SKIP_ROBOTS), "", url

        status, body = self._raw_get(url)
        if status in C.ABORT_HOST_STATUSES:
            # 1回でも出たら、このホストは以後いっさい叩かない（05 §2-4）。
            self.blocked[host] = f"HTTP {status}"
            return status, "", url
        if status != 200 or not body:
            return status, "", url
        if scan_tos(body):
            self.blocked[host] = f"規約に禁止文言: {scan_tos(body)}"
            return SKIP_TOS, "", url

        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return status, body, url


def scan_tos(body: str) -> str:
    """サイト本文に自動取得の禁止文言があれば、その語を返す（05 §6）。

    ヒットしたドメインは以後停止し、法務が読むまで再開しない。
    1,006社ぶんの規約を人が読むのは無理なので、機械で網を張る。
    """
    for kw in C.TOS_KEYWORD_SCAN:
        if kw in body and ("禁止" in body or "お断り" in body or "不可" in body):
            return kw
    return ""


def _decode(raw: bytes, enc: str | None) -> str:
    """日本の中小メーカーのサイトは Shift_JIS / EUC-JP がまだ現役。"""
    cands = [enc] if enc else []
    head = raw[:2048].decode("ascii", "ignore").lower()
    for name in ("shift_jis", "sjis", "x-sjis", "euc-jp", "utf-8"):
        if f"charset={name}" in head.replace('"', "").replace("'", ""):
            cands.append(name)
    cands += ["utf-8", "cp932", "euc-jp"]
    for c in cands:
        if not c:
            continue
        try:
            return raw.decode(c)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")
