"""SD への取得を機械的に止める。**既定は全面停止。**

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

# 🔴 2026-09-30（同日2回目）法務再判定（成果物30 §9-7）により **全面停止**。
#   理由：12秒間隔でも429が出た（法務の検算 #6→#7）。「1日30回・間隔10秒」は根拠を失った。
#   **緩めるのではなく、SD への照会（成果物30 §6）の回答が出るまで止める**のが正しい順序。
#   解除するのは秘書カズヨ。解除するときは SUSPENDED を False にし、
#   **誰がいつ何を根拠に解除したかをチケットに書く。**
SUSPENDED = True
SUSPENDED_REASON = (
    "SD への自動取得は停止中です（法務再判定・成果物30 §9-7）。"
    "429 の発生条件を当社は特定できておらず（各方向 n=1・161社の実績と不整合）、"
    "12秒間隔でも429が出ました。確定手段は SD への照会だけです。"
    "レーンB（Amazon 起点の 1 JAN = 1リクエスト）も回答が出るまで止めます。"
)

MAX_PER_DAY = 30
MIN_INTERVAL = 10.0


class BudgetExceeded(RuntimeError):
    """1日の上限に達した。**待っても今日は増えない。**"""


class NotAttended(RuntimeError):
    """無人運転は不可。--attended を付けること。"""


class Suspended(RuntimeError):
    """SD へのアクセスが停止中。**回数や間隔では解除できない。**"""


class Budget:
    def __init__(self, state_dir: str, attended: bool, label: str = "sd"):
        if SUSPENDED:
            raise Suspended(SUSPENDED_REASON)
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
