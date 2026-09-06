#!/bin/bash
# 夜間自走の起動スクリプト（nohup 2段）。
#
#   1段目: このスクリプト自身を nohup で切り離す（セッションが切れても死なない）
#   2段目: 中で監督ループを回し、worker が落ちたら**続きから**起こし直す
#
# 止め方:  touch STOP     （150秒以内に安全停止し、書き出し済みの行は全て残る）
# 見る:    tail -f out/run.log  /  cat out/progress.json  /  cat out/heartbeat.json
# launchd の環境には Homebrew の PATH が無い（memory: knowledge_launchd_always_on_jobs §5）
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [ -f STOP ]; then
  echo "STOP があります。rm STOP してから起動してください"; exit 1
fi

MAX_HOURS="${MAX_HOURS:-11}"
DEADLINE=$(( $(date +%s) + $(printf '%.0f' "$(echo "$MAX_HOURS * 3600" | bc)") ))

echo "$$" > supervisor.pid
{
  echo "=== 監督ループ開始 $(date '+%F %T') 上限 ${MAX_HOURS}h ==="
  n=0
  while true; do
    [ -f STOP ]     && { echo "STOP を検知。監督ループを終了"; break; }
    [ -f FINISHED ] && { echo "FINISHED を検知。完走したので終了"; break; }
    [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "通算上限に到達。終了"; break; }

    n=$((n+1))
    echo "--- worker 起動 #${n} $(date '+%F %T') ---"
    remain=$(echo "scale=3; ($DEADLINE - $(date +%s)) / 3600" | bc)
    python3 verify_pool.py --max-hours "$remain"
    rc=$?
    echo "--- worker 終了 rc=${rc} $(date '+%F %T') ---"
    # rc=2 は「契約が無効」。起こし直しても直らないので諦める
    [ "$rc" -eq 2 ] && { echo "Keepa の契約が無効。監督ループを終了"; break; }
    # 落ちた場合だけ少し待って起こし直す（暴走再起動を防ぐ）
    [ "$rc" -ne 0 ] && sleep 60
  done
  echo "=== 監督ループ終了 $(date '+%F %T') ==="
} >> out/supervisor.log 2>&1
rm -f supervisor.pid
