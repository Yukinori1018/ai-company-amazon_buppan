"""SD への取得を機械的に縛る。**上限は引数で緩められない。**

根拠：法務ハルオの判定（成果物29 §5・§9-2）と CLAUDE.md §3.3-18。
使える線はレーンごとに定数で固定してある。超えたら例外で止まる。

| レーン | 用途 | 1日 | 1セッション | 間隔（初期値） |
|---|---|---|---|---|
| **A** | Amazon 起点「この JAN は SD で買えるか」（1件1リクエスト） | 30 | — | 10.0 秒 |
| **B** | 発注候補に挙がった社の取引条件・商品ページ（人が1社ずつ） | 50 | 20 | 3.0 秒 |
| **C** | 2,013社の全件スキャン | ⛔ 実装しない（歩留まり15%＝85%は捨てる作業） |

どちらのレーンも **`--attended` 必須**（無人運転は不可）。
間隔は `_backoff.py` が持つ**自動バックオフ**で上がる／下がる。初期値は上の表の値。

カウンタは日付ごとに JSON で残す（`<label>_budget_<YYYY-MM-DD>.json`）。
**プロセスを再起動しても使い切った回数は戻らない。**バックオフの段も同じく残る。

上限の単位は **リクエスト数**。取引条件ページは1社=1リクエストなので社数と一致するが、
商品一覧のページ送りは1社で複数リクエストになる。**安全側に、社数ではなく回数で数える。**
"""
from __future__ import annotations

import datetime
import json
import os
import time
from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# 停止フラグ
#
# 2026-09-30 に「SD への照会の回答が出るまで全面停止」として True にした。
# 🔴 2026-10-01 解除。
#     解除者 ＝ 秘書カズヨ
#     根拠   ＝ T-20260920-003 の「2026-10-01 社長指示：SD への取得を再開する（全面停止を撤回）」節
#               （社長指示「数を減らしたり、間隔を空ければいいじゃん。中止するのではなく、
#                 できる方法を考えろって。立ち止まったら次に進めないじゃん。」）
#     解除日 ＝ 2026-10-01
#     解除の条件（すべて実装済み）
#       1. レーンごとの上限を定数で固定（引数で緩められない）
#       2. 429/503 が出たらその日は打ち切り・翌日は間隔を倍にする自動バックオフ
#          （`_backoff.py`。状態はファイルに残り、プロセス再起動でも戻らない）
#       3. 全件スキャン（レーンC）の経路を残さない
#     🔴 譲らない線：通信の指紋を偽装する手段は使わない（CLAUDE.md §3.3-14）。
#        調整するのは **ペースだけ**。
#
# 再度止める必要が出たら True に戻し、**誰がいつ何を根拠に止めたかをチケットに書く。**
# ─────────────────────────────────────────────────────────────────────────────
SUSPENDED = False
SUSPENDED_REASON = (
    "SD への自動取得は停止中です。再開するときは _budget.py の SUSPENDED を False にし、"
    "誰がいつ何を根拠に解除したかをチケットに書いてください。")

#: バックオフの状態ファイル名（レーンごとに分ける）
BACKOFF_FILE = "backoff_state.json"


@dataclass(frozen=True)
class Lane:
    """レーンの上限。**ここを引数から書き換える経路は作らない。**"""
    key: str
    label: str
    max_per_day: int
    base_interval: float
    max_per_session: int        # 0 ならセッション上限なし
    note: str

    @property
    def backoff_path_name(self) -> str:
        return f"{self.label}_{BACKOFF_FILE}"


LANE_A = Lane(
    key="A", label="sd_jan", max_per_day=30, base_interval=10.0, max_per_session=0,
    note="Amazon 起点・1 JAN = 1リクエスト（/p/do/psl/?word=<JAN13>）")

LANE_B = Lane(
    key="B", label="sd_dealer", max_per_day=50, base_interval=3.0, max_per_session=20,
    note="発注候補に挙がった社だけ・人が在席して1社ずつ")

LANES = {LANE_A.key: LANE_A, LANE_B.key: LANE_B}


class BudgetExceeded(RuntimeError):
    """1日の上限に達した。**待っても今日は増えない。**"""


class SessionLimitReached(BudgetExceeded):
    """1セッションの上限に達した。人がいったん手を止めるための区切り。"""


class NotAttended(RuntimeError):
    """無人運転は不可。--attended を付けること。"""


class Suspended(RuntimeError):
    """SD へのアクセスが停止中。**回数や間隔では解除できない。**"""


# `_backoff` から持ち上げておく（呼び出し側が2つ import しなくて済むように）
import sys as _sys                                                    # noqa: E402
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _backoff import Backoff, DayCutOff                               # noqa: E402,F401


class Budget:
    """1リクエストごとに `take()` を呼ぶ。上限・間隔・在席・バックオフを全部ここで見る。

    使い方::

        budget = Budget(state_dir, attended=args.attended, lane=LANE_A)
        for jan in jans:
            budget.take()                     # 上限なら例外・間隔が足りなければ待つ
            try:
                page = fetch(url)
            except RateLimited:
                budget.note_rate_limited()    # 🔴 その日を打ち切り・間隔を1段上げる
                break
        budget.finish()                       # 429 なしで走り切ったら「きれいな日」を1日計上

    `sleep` を差し替えられるのはテストのため（ネットワークなしで間隔を検査する）。
    """

    def __init__(self, state_dir: str, *, attended: bool, lane: Lane = LANE_A,
                 today: str | None = None, sleep=time.sleep, now=time.time) -> None:
        if SUSPENDED:
            raise Suspended(SUSPENDED_REASON)
        if not attended:
            raise NotAttended(
                "SD への取得は人の在席下でのみ実行できます（法務判定・成果物29 §5）。"
                "--attended を明示してください。無人運転は不可です。")
        self.lane = lane
        self._sleep = sleep
        self._now = now
        self.today = today or datetime.date.today().isoformat()
        os.makedirs(state_dir, exist_ok=True)
        self.path = os.path.join(state_dir, f"{lane.label}_budget_{self.today}.json")
        self.backoff = Backoff(os.path.join(state_dir, lane.backoff_path_name),
                               lane.base_interval, today=self.today)
        # 🔴 429 が出た日はもう開かない。同日中の再試行はしない
        self.backoff.require_open_day()
        self.state = (self._read() if os.path.exists(self.path)
                      else {"date": self.today, "used": 0, "last_at": 0.0})
        self.state.setdefault("used", 0)
        self.session_used = 0
        self.rate_limited = False

    def _read(self) -> dict:
        try:
            saved = json.load(open(self.path, encoding="utf-8"))
        except (ValueError, OSError):
            saved = {}
        if not isinstance(saved, dict) or saved.get("date") != self.today:
            return {"date": self.today, "used": 0, "last_at": 0.0}
        return saved

    def _write(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ── 現在値 ────────────────────────────────────────────────────────────

    @property
    def interval(self) -> float:
        return self.backoff.interval

    @property
    def remaining(self) -> int:
        return max(0, self.lane.max_per_day - int(self.state["used"]))

    @property
    def session_remaining(self) -> int:
        if not self.lane.max_per_session:
            return self.remaining
        return max(0, min(self.lane.max_per_session - self.session_used, self.remaining))

    def describe(self) -> str:
        cap = (f"・1セッション {self.lane.max_per_session}" if self.lane.max_per_session else "")
        return (f"レーン{self.lane.key}（{self.lane.note}）: "
                f"本日の残り {self.remaining}/{self.lane.max_per_day}{cap}・"
                f"{self.backoff.describe()}")

    # ── 消費 ──────────────────────────────────────────────────────────────

    def take(self) -> None:
        """1リクエストぶん消費する。上限なら例外。間隔が足りなければ待つ。"""
        if self.rate_limited:
            raise DayCutOff(f"{self.today} は 429 で打ち切りました。同日中の再試行はしません。")
        if int(self.state["used"]) >= self.lane.max_per_day:
            raise BudgetExceeded(
                f"本日の上限 {self.lane.max_per_day} 回に達しました（{self.today}・"
                f"レーン{self.lane.key}）。明日まで待つか、秘書へ判断を戻してください。")
        if self.lane.max_per_session and self.session_used >= self.lane.max_per_session:
            raise SessionLimitReached(
                f"1セッションの上限 {self.lane.max_per_session} 回に達しました"
                f"（レーン{self.lane.key}）。いったん手を止めて、必要なら人が判断して再実行してください。")
        last = float(self.state.get("last_at") or 0.0)
        gap = self._now() - last
        if last and gap < self.interval:
            self._sleep(self.interval - gap)
        self.state["used"] = int(self.state["used"]) + 1
        self.session_used += 1
        self.state["last_at"] = self._now()
        self._write()

    def note_rate_limited(self) -> float:
        """🔴 429/503 が出た。**その日を打ち切り、間隔を1段上げる。**

        1件の失敗として飲み込まないこと。これを飲み込んだ結果、2026-09-30 に
        「SD に無かった」という無害そうな0件に化けた（CLAUDE.md §3.3-18）。
        """
        self.rate_limited = True
        return self.backoff.record_rate_limited()

    def finish(self) -> bool:
        """走り終わったら必ず呼ぶ。429 なしで1件以上走れた日を「きれいな日」として数える。

        戻り値: 段を1つ戻したか
        """
        if self.rate_limited or self.session_used == 0:
            return False
        return self.backoff.record_clean_day()
