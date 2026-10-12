#!/bin/bash
#
# login-keepalive.sh — ログイン延命の入口（T-20260920-003 / 2026-10-12）
#
#   ./login-keepalive.sh            launchd から10分ごと（期限の来たサイトだけ読み込み直す）
#   ./login-keepalive.sh setup      延命ウィンドウを作る＋全サイトを今すぐ確認
#   ./login-keepalive.sh check      全サイトを今すぐ確認（ウィンドウは作らない）
#   ./login-keepalive.sh status     状態を表示（ALERT の有無も）
#   ./login-keepalive.sh stop       止める（STOP ファイルを置くだけ）
#   ./login-keepalive.sh start      再開する
#
# 本体: workspace/output/deliverables/T-20260920-003/login_keepalive/login_keepalive.py
# 状態・ALERT: workspace/output/agent_output/T-20260920-003/login_watch/（gitignore）
# パスワード・Cookie は扱わない。ログインの入力は社長の一手。
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
PY="$REPO/workspace/output/deliverables/T-20260920-003/login_keepalive/login_keepalive.py"
WATCH="$REPO/workspace/output/agent_output/T-20260920-003/login_watch"
mkdir -p "$WATCH"

case "${1:-run}" in
  stop)  touch "$WATCH/STOP"; echo "止めました（再開は start）"; exit 0 ;;
  start) rm -f "$WATCH/STOP"; echo "再開しました"; exit 0 ;;
  *)     /usr/bin/python3 "$PY" "${1:-run}"; exit 0 ;;   # 異常でも exit 0（launchd の再起動ストーム防止）
esac
