#!/usr/bin/env python3
"""予約タスク（Claude デスクトップアプリの scheduled tasks）が止まっていないかを検査する。

session-start.sh から呼ばれ、異常があるときだけ 🔴 のメッセージを stdout に出す。
異常がなければ何も出さない。ログや台帳が無い環境（クラウド等）でも黙って終わる。

背景（2026-10-10 / T-20260920-003）:
  予約実行は permission mode=default で起動する。最初の Bash などで許可画面を出し、
  夜間は誰も押さないので "running" のまま永久に止まる。per_task 上限1・global 上限3 が
  それで埋まり、新しいタスクは一度も起動しない。9/30 以降1件も完了していなかったのに、
  誰も気づかなかった。「動いていないこと」を毎朝目に入れるためのフック。

検査は2つ:
  (a) main.log の直近 LOOKBACK_HOURS 時間に「Skipping dispatch」「Not auto-approving」
      があれば、タスク名ごとに件数と最終時刻を出す（＝詰まりの直接証拠）
  (b) 有効な予約タスクのうち OUTPUT_WATCH に登録したものについて、成果物フォルダの
      最新ファイルが max_age_hours より古ければ「動いていない」と出す（＝結果の証拠）
      (a) だけだとログの文言が変わった日に黙る。(b) は文言に依存しない保険。

環境変数で差し替え可（テスト用）:
  CLAUDE_MAIN_LOG        main.log のパス
  CLAUDE_SCHED_GLOB      scheduled-tasks.json の glob
  SCHED_HEALTH_NOW       現在時刻（epoch 秒）
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
MAIN_LOG = Path(os.environ.get("CLAUDE_MAIN_LOG", HOME / "Library/Logs/Claude/main.log"))
SCHED_GLOB = os.environ.get(
    "CLAUDE_SCHED_GLOB",
    str(HOME / "Library/Application Support/Claude/claude-code-sessions/*/*/scheduled-tasks.json"),
)
NOW = float(os.environ.get("SCHED_HEALTH_NOW", time.time()))

LOOKBACK_HOURS = 36
TAIL_BYTES = 4_000_000  # main.log は数MB〜。末尾だけ読む（36時間ぶんで約3MB・2026-10-10実測）

# タスクID → (成果物フォルダ: cwd からの相対パス, 何時間更新が無ければ異常か)
# 新しい夜間タスクを足したら、ここにも1行足す。登録の無いタスクは (b) の対象外。
OUTPUT_WATCH: dict[str, tuple[str, float]] = {
    "amazon-buppan-nightly-sourcing": ("workspace/output/agent_output/T-20260920-003/pipeline", 26),
}

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) .*\[CCDScheduledTasks\] (.*)$")
SKIP_RE = re.compile(r"Skipping dispatch for (\S+?): (\w+)")
NOAPPROVE_RE = re.compile(r'Not auto-approving "([^"]+)" in scheduled task "([^"]+)"')


def scan_log() -> list[str]:
    if not MAIN_LOG.is_file():
        return []
    size = MAIN_LOG.stat().st_size
    with MAIN_LOG.open("rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        text = f.read().decode("utf-8", "replace")
    cutoff = NOW - LOOKBACK_HOURS * 3600
    # (task, 種別) -> [件数, 最終時刻, 詳細の集合]
    agg: dict[tuple[str, str], list] = defaultdict(lambda: [0, "", set()])
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        ts, body = m.groups()
        try:
            if datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp() < cutoff:
                continue
        except ValueError:
            continue
        if s := SKIP_RE.search(body):
            key, detail = (s.group(1), "起動できず"), s.group(2)
        elif n := NOAPPROVE_RE.search(body):
            key, detail = (n.group(2), "許可待ちで停止"), n.group(1)
        else:
            continue
        a = agg[key]
        a[0] += 1
        a[1] = max(a[1], ts)
        a[2].add(detail)
    lines = []
    for (task, kind), (cnt, last, details) in sorted(agg.items()):
        lines.append(f"- {task}：{kind} {cnt}回（最終 {last}・{', '.join(sorted(details))}）")
    return lines


def enabled_tasks() -> list[dict]:
    tasks = []
    for p in glob.glob(SCHED_GLOB):
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tasks += [t for t in data.get("scheduledTasks", []) if t.get("enabled")]
    return tasks


def scan_outputs() -> list[str]:
    lines = []
    for t in enabled_tasks():
        watch = OUTPUT_WATCH.get(t.get("id", ""))
        if not watch or not t.get("cwd"):
            continue
        rel, max_age = watch
        # 作成から max_age 経っていないタスクはまだ1回も走る機会が無いので見ない
        created = (t.get("createdAt") or 0) / 1000
        if NOW - created < max_age * 3600:
            continue
        # worktree からでも本体の成果物を見るため、リポではなくタスクの cwd を基準にする
        d = Path(t["cwd"]) / rel
        files = [p for p in d.rglob("*") if p.is_file()] if d.is_dir() else []
        newest = max((p.stat().st_mtime for p in files), default=0)
        age_h = (NOW - newest) / 3600
        if age_h > max_age:
            when = datetime.fromtimestamp(newest).strftime("%m/%d %H:%M") if newest else "ファイルなし"
            lines.append(
                f"- {t['id']}：成果物の最終更新 {when}（{age_h:.0f}時間前・基準{max_age:.0f}時間）＝夜間作業が動いていない"
            )
    return lines


def main() -> int:
    log_lines, out_lines = scan_log(), scan_outputs()
    if not (log_lines or out_lines):
        return 0
    msg = ["🔴【予約タスクが止まっています】夜間作業が完了していません。社長に最初に伝えてください。"]
    if out_lines:
        msg.append("成果物が更新されていないタスク:")
        msg += out_lines
    if log_lines:
        msg.append(f"main.log 直近{LOOKBACK_HOURS}時間の詰まり（許可画面で止まると上限が埋まり、後続も起動しない）:")
        msg += log_lines
    msg.append("対処：止まっている予約セッションを開いて停止 → 許可を事前に与える（または権限モードを見直す）。証拠: ~/Library/Logs/Claude/main.log の [CCDScheduledTasks]")
    print("\n".join(msg))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # フックは絶対にセッション開始を壊さない
        sys.exit(0)
