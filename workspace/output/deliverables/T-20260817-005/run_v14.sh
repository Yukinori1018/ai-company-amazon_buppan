#!/bin/bash
# scan_v14 を無人で走らせる（2段 nohup フロー）。
#
#   ./run_v14.sh              # 既定12時間で自動停止
#   ./run_v14.sh 6            # 6時間で自動停止
#
# 1段目 = スキャナ本体（Keepa を叩き、CSV に追記し続ける）
# 2段目 = 見張り（STATUS.md とレポートを定期更新し、終わったら FINISHED を置く）
#
# 止めたいとき:  touch v14/STOP     ← 次のバッチの切れ目で安全に止まります
# 再開するとき:  rm v14/STOP && ./run_v14.sh
set -euo pipefail

cd "$(dirname "$0")"
HOURS="${1:-12}"
mkdir -p v14

if [ -f v14/STOP ]; then
  echo "STOP ファイルがあります。再開するには先に消してください:"
  echo "    rm '$(pwd)/v14/STOP'"
  exit 1
fi

if [ -f v14/scan.pid ] && kill -0 "$(cat v14/scan.pid)" 2>/dev/null; then
  echo "すでに走っています（PID $(cat v14/scan.pid)）。二重起動するとトークンを二重に食います。"
  echo "止めるなら: touch '$(pwd)/v14/STOP'"
  exit 1
fi

nohup python3 scan_v14.py --max-hours "$HOURS" > v14/scan_stdout.log 2>&1 &
SCAN_PID=$!
echo "$SCAN_PID" > v14/scan.pid

sleep 2
nohup python3 watch_v14.py --pid "$SCAN_PID" --max-hours "$HOURS" \
      --deadline-hours "$(python3 -c "print($HOURS + 2)")" \
      > v14/watch_stdout.log 2>&1 &
echo "$!" > v14/watch.pid

cat <<EOF
起動しました。
  スキャナ  PID $SCAN_PID （$HOURS 時間で自動停止）
  見張り    PID $(cat v14/watch.pid)

見るもの:
  tail -f $(pwd)/v14/scan_v14.log
  cat     $(pwd)/v14/STATUS.md
  open    $(pwd)/v14/00_候補リスト.html

止めるとき:
  touch $(pwd)/v14/STOP
EOF
