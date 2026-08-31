"""心拍ファイル —— 無人ジョブが「本当に進んでいるか」を外から確かめるための仕組み。

なぜ要るか（2026-08-31 に同じ失敗を2回した）:

  朝  night-shift の plist が指すスクリプトが存在せず、**814回 exit 127 で死に続けた**。
      14日間、誰も気づかなかった。
  夕方 このスキャンを再起動したつもりが `pkill` しか実行されておらず、
      **殺しただけで再起動できていなかった**。直後の `ps` には中間プロセスが出るので
      「稼働中」に見えた。気づけたのは**ログの最終行が8分前のまま**だったから。

> **プロセスの存在は、仕事が進んでいる証拠になりません。**
> PID は使い回されるし、生きているだけで何もしていないプロセスもある。
> **見るべきは「成果が増えた時刻」** です。

この心拍ファイルは60秒以内ごとに上書きされます。**トークンの回復待ちで15分眠る間も**
打ち続けるので、「止まった」と「待っている」を取り違えません。
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

# これ以上更新が途絶えたら「止まっている疑い」。
# 1バッチ＝最長15分の待機を挟むので、その倍を目安にする。
STALE_SECONDS = 180


class Heartbeat:
    """`beat()` を呼ぶたびに現在地を1ファイルに上書きする。追記ではなく上書き。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()

    def beat(self, phase: str, **fields) -> None:
        """現在地を書く。**失敗しても本体を止めない**（心拍のために仕事を落とさない）。"""
        payload = {
            "phase": phase,
            "updated_at": datetime.now(JST).isoformat(timespec="seconds"),
            "updated_epoch": time.time(),
            "elapsed_sec": round(time.time() - self.started_at, 1),
            "pid": os.getpid(),   # 参考情報。**生死の判定には使わない**
            **fields,
        }
        try:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)   # 差し替えは原子的に（読み手が壊れた JSON を見ない）
        except OSError:
            pass


def read(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def describe(path) -> str:
    """人が1行で読める生死表示。**カズヨさんがこれを見て判断できることが目的。**"""
    beat = read(path)
    if not beat:
        return "心拍ファイルがありません（一度も起動していないか、out/ が消えています）"

    age = time.time() - (beat.get("updated_epoch") or 0)
    if age < STALE_SECONDS:
        state = "稼働中"
    else:
        state = f"⚠ 停止の疑い（{_ago(age)}更新なし）"

    parts = [f"{state} / 最終更新 {_ago(age)}前 / {beat.get('phase', '?')}"]
    if beat.get("done") is not None and beat.get("total") is not None:
        parts.append(f"進捗 {beat['done']}/{beat['total']}件")
    if beat.get("tokens_left") is not None:
        parts.append(f"トークン残 {beat['tokens_left']}")
    if beat.get("tokens_per_code"):
        parts.append(f"実効 {beat['tokens_per_code']:.2f}/件")
    if beat.get("note"):
        parts.append(str(beat["note"]))
    return " / ".join(parts)


def _ago(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分"
    return f"{seconds // 3600}時間{(seconds % 3600) // 60}分"
