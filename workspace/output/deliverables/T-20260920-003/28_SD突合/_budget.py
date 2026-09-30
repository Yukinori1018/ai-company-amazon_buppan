"""SD への取得回数を機械的に縛る。**超えたら例外で止まる。**

根拠：法務ハルオの判定（成果物29 §5）で「Amazon 起点の 1 JAN = 1リクエストに限り条件つき可」。
条件のうち機械で守れる3つをここに定数で固定する。**引数で緩められないようにしてある。**

    MAX_PER_DAY = 30       1日30回
    MIN_INTERVAL = 10.0    間隔10.0秒（robots.txt の Crawl-delay は * グループには無いが、
                           名指しクローラ向けに 10 が示されているのでその値に合わせる）
    ATTENDED_REQUIRED      人（秘書カズヨ）の在席下でのみ実行。--attended を明示しないと動かない

カウンタは日付ごとに JSON で残す（`sd_budget_<YYYY-MM-DD>.json`）。
プロセスを再起動しても使い切った回数は戻らない。
"""
from __future__ import annotations
import json, os, time, datetime

MAX_PER_DAY = 30
MIN_INTERVAL = 10.0


class BudgetExceeded(RuntimeError):
    """1日の上限に達した。**待っても今日は増えない。**"""


class NotAttended(RuntimeError):
    """無人運転は不可。--attended を付けること。"""


class Budget:
    def __init__(self, state_dir: str, attended: bool, label: str = "sd"):
        if not attended:
            raise NotAttended(
                "SD への取得は人の在席下でのみ実行できます（法務判定・成果物29 §5）。"
                "--attended を明示してください。無人運転は不可です。")
        self.today = datetime.date.today().isoformat()
        self.path = os.path.join(state_dir, f"{label}_budget_{self.today}.json")
        os.makedirs(state_dir, exist_ok=True)
        self.state = (json.load(open(self.path)) if os.path.exists(self.path)
                      else {"date": self.today, "used": 0, "last_at": 0.0})
        self._last = self.state.get("last_at", 0.0)

    @property
    def remaining(self) -> int:
        return MAX_PER_DAY - self.state["used"]

    def take(self) -> None:
        """1リクエストぶん消費する。上限なら例外。間隔が足りなければ待つ。"""
        if self.state["used"] >= MAX_PER_DAY:
            raise BudgetExceeded(
                f"本日の上限 {MAX_PER_DAY} 回に達しました（{self.today}）。"
                f"明日まで待つか、秘書へ判断を戻してください。")
        gap = time.time() - self._last
        if self._last and gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        self.state["used"] += 1
        self._last = time.time()
        self.state["last_at"] = self._last
        json.dump(self.state, open(self.path, "w"), ensure_ascii=False)
