"""SD への取得間隔を、**相手に聞かずに手探りで収束させる**。

なぜこれが要るのか（CLAUDE.md §3.3-18）
    2026-09-30、SD が 429 を返した。許容ラインは当社には分からない。
    そこで「照会の回答が出るまで全面停止」とした。**社長が照会を却下した時点で、
    それは永久停止と同義になった**（2026-10-01「立ち止まったら次に進めないじゃん」）。

    許容ラインが不明なら、止めるのではなく **安全側から近づく**。
    429 が出たらその日は打ち切り、翌日は間隔を倍にして再開する。出なければ現状維持。
    連続3日出なければ1段戻す。これは相手に何も聞かずに設計できる。

段（レーンAの base=10.0 秒のとき）
    10.0 → 20.0 → 40.0 → 80.0 → 160.0
    最上段 160 秒でも1日30件なら80分。**上限に当たっても実用に足る**ので諦めない。

守っていること
    * **同日中の自動リトライはしない。**429 が出た日はその日の残りを捨てる。
      「待ってもう一度」は相手に対して最悪の振る舞い。
    * **状態はファイルに残す。プロセスを再起動しても戻らない。**
      再起動で 10 秒に戻るなら、縛りとして意味がない。
    * **通信の指紋を偽装しない**（§3.3-14）。ここで調整するのは **ペースだけ**。

🔴 間隔は引数で緩められない。`base_interval` はレーンごとの定数（`_budget.py`）で、
   保存値が段から外れていたら**遅い側へ寄せて**読む。
"""
from __future__ import annotations

import datetime
import json
import os

#: 429 が出ずに走り切った日が何日続いたら1段戻すか
CLEAN_DAYS_TO_STEP_DOWN = 3

#: 段の数（base, ×2, ×4, ×8, ×16）
STEP_COUNT = 5

#: 履歴として残す行数（デバッグ用。古いものから捨てる）
HISTORY_KEEP = 30


class DayCutOff(RuntimeError):
    """その日は 429 が出たので打ち切り済み。**待っても今日は再開しない。**"""


def steps_for(base_interval: float) -> list[float]:
    """間隔の段を作る。base から倍々に `STEP_COUNT` 段。"""
    base = float(base_interval)
    return [round(base * (2 ** k), 3) for k in range(STEP_COUNT)]


class Backoff:
    """間隔の現在値と、段の上げ下げを保存する。

    状態ファイル（既定 `backoff_state.json`）の中身::

        {
          "base_interval": 10.0,          レーンの定数。変わったら段を作り直す
          "interval": 20.0,               いま使う間隔（秒）
          "last_429_date": "2026-10-01",  最後に 429 が出た日（その日は打ち切り）
          "clean_days": 1,                429 が出ずに走り切った日が何日続いたか
          "last_clean_date": "2026-10-02",  clean_days を数えた最後の日（二重計上の防止）
          "history": [...]                 段が動いた記録
        }
    """

    def __init__(self, path: str, base_interval: float, today: str | None = None) -> None:
        self.path = path
        self.base = float(base_interval)
        self.steps = steps_for(self.base)
        self.today = today or datetime.date.today().isoformat()
        self.state = self._load()

    # ── 読み書き ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        fresh = {
            "base_interval": self.base,
            "interval": self.base,
            "last_429_date": None,
            "clean_days": 0,
            "last_clean_date": None,
            "history": [],
        }
        saved: dict = {}
        if os.path.exists(self.path):
            try:
                loaded = json.load(open(self.path, encoding="utf-8"))
            except (ValueError, OSError):
                loaded = None                     # 壊れていたら安全側（base）から始める
            if isinstance(loaded, dict):
                saved = loaded
        # レーンの base が変わったら段の意味が変わる。古い interval は引き継がない。
        if saved and abs(float(saved.get("base_interval", self.base)) - self.base) > 1e-9:
            saved = {"history": saved.get("history", [])}
        fresh.update(saved)
        fresh["base_interval"] = self.base
        fresh["interval"] = self._snap(fresh.get("interval", self.base))
        fresh["clean_days"] = max(0, int(fresh.get("clean_days") or 0))
        return fresh

    def _snap(self, value) -> float:
        """保存値を段に寄せる。**遅い側へ寄せる**（手で書き換えられても緩まない）。"""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return self.steps[0]
        for s in self.steps:
            if v <= s + 1e-9:
                return s
        return self.steps[-1]

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)                # 途中で死んでも壊れたファイルを残さない

    def _log(self, msg: str) -> None:
        hist = self.state.setdefault("history", [])
        hist.append({"date": self.today, "msg": msg})
        del hist[:-HISTORY_KEEP]

    # ── 現在値 ────────────────────────────────────────────────────────────

    @property
    def interval(self) -> float:
        return float(self.state["interval"])

    @property
    def step_index(self) -> int:
        return self.steps.index(self._snap(self.interval))

    @property
    def cut_off_today(self) -> bool:
        return self.state.get("last_429_date") == self.today

    def require_open_day(self) -> None:
        """今日が打ち切り済みなら起動させない。"""
        if self.cut_off_today:
            raise DayCutOff(
                f"{self.today} は SD が 429 を返したので打ち切りました。"
                f"**同日中の再試行はしません。**明日は間隔 {self.interval:.1f} 秒で再開します"
                f"（段 {self.step_index + 1}/{len(self.steps)}）。")

    # ── 段の上げ下げ ──────────────────────────────────────────────────────

    def record_rate_limited(self) -> float:
        """429/503 が出た。**その日を打ち切り、間隔を1段上げる。**

        1件の失敗として飲み込まないこと。飲み込むと「SD に無かった」に化ける
        （2026-09-30 に実際に化けた。CLAUDE.md §3.3-18）。

        戻り値: 新しい間隔（秒）
        """
        before = self.interval
        self.state["interval"] = self.steps[min(self.step_index + 1, len(self.steps) - 1)]
        self.state["last_429_date"] = self.today
        self.state["clean_days"] = 0
        self.state["last_clean_date"] = None
        self._log(f"429 → 間隔 {before:.1f}s から {self.interval:.1f}s へ。この日は打ち切り")
        self.save()
        return self.interval

    def record_clean_day(self) -> bool:
        """429 が出ずに走り切った。**連続 3 日で1段戻す。**

        - 同じ日は1回しか数えない（再起動して2回走っても二重計上しない）
        - **走らなかった日は数えない。**走っていない日は何の証拠にもならない

        戻り値: 段を戻したか
        """
        if self.cut_off_today:
            return False
        if self.state.get("last_clean_date") == self.today:
            return False
        self.state["last_clean_date"] = self.today
        self.state["clean_days"] = int(self.state.get("clean_days") or 0) + 1
        stepped = False
        if self.state["clean_days"] >= CLEAN_DAYS_TO_STEP_DOWN and self.step_index > 0:
            before = self.interval
            self.state["interval"] = self.steps[self.step_index - 1]
            self.state["clean_days"] = 0
            stepped = True
            self._log(f"429 なしが {CLEAN_DAYS_TO_STEP_DOWN} 日続いた → "
                      f"間隔 {before:.1f}s から {self.interval:.1f}s へ")
        self.save()
        return stepped

    # ── 表示 ──────────────────────────────────────────────────────────────

    def describe(self) -> str:
        return (f"間隔 {self.interval:.1f} 秒（段 {self.step_index + 1}/{len(self.steps)}・"
                f"429なし {self.state.get('clean_days', 0)} 日連続・"
                f"最後の429 {self.state.get('last_429_date') or 'なし'}）")
