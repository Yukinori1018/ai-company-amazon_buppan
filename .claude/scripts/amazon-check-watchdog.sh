#!/bin/bash
# Amazon 日次チェックの「実行漏れ」を、Claude が起動していなくても社長に知らせる番犬。
#
# なぜ launchd で別に持つのか（2026-09-06 / T-20260826-004）:
#   9/5 に日次チェックが飛びました。裏取りの結果、Mac は起動していて launchd の
#   github-sync は 07:03〜22:33 まで6回走っていましたが、Claude アプリのセッションは
#   9/4 14:21 を最後に 9/6 10:33 まで1件もありません。
#   → **落ちるのは Claude であって launchd ではない。** 巡回自体は Claude（＋ログイン済み
#     Chrome）が要るので代替できませんが、「今日まだ動いていない」と知らせるだけなら
#     launchd で足ります。SessionStart フックは Claude を開いた時にしか鳴らないので、
#     まさに壊れている時に鳴らない。この番犬はそこだけを埋めます。
#
# やること（これ以上は増やさない）:
#   1. 過去の欠測日に「未実行」の行をログへ挿入する（空白は見逃されるが、明示は見逃されにくい）
#   2. 今日ぶんが 12:30 を過ぎても無ければ、macOS の通知センターに出す
#   3. 自分が走った時刻を1行のファイルに残す（番犬が死んだことも検知できるように）
#
# やらないこと: Amazon へのアクセス・ログイン・送信。git commit（30分ごとの github-sync に任せる）。

set -euo pipefail

# launchd の環境には Homebrew の PATH が無い（knowledge_launchd_always_on_jobs.md §5）
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO="${CLAUDE_PROJECT_DIR:-/Users/yukinori/Claude Code/ai-company-amazon_buppan}"
LOGIC="$REPO/.claude/scripts/amazon_check_log.py"
MON_LOG="$REPO/workspace/monitoring/amazon-daily-check.md"
HEARTBEAT="$REPO/workspace/monitoring/watchdog-last-run.txt"

# 巡回の予定は 12:00。30分の猶予を見て 12:30 以降に「今日まだ」と鳴らす。
DEADLINE_HHMM="1230"

notify() {
  # $1=タイトル $2=本文
  # 通知が出ない環境（通知許可 off 等）でも落とさない。ここで失敗しても番犬は仕事を続ける。
  osascript -e "display notification \"$2\" with title \"$1\" sound name \"Ping\"" >/dev/null 2>&1 || true
}

case "${1:-run}" in
  --test-notify)
    notify "Amazon日次チェック（テスト）" "この通知が見えていれば、番犬の通知は届きます。"
    echo "通知を送りました。通知センターに出なければ、システム設定 > 通知 > スクリプトエディタ を許可してください。"
    exit 0
    ;;
  --status)
    python3 "$LOGIC" status
    echo "番犬の最終実行: $(cat "$HEARTBEAT" 2>/dev/null || echo '記録なし')"
    exit 0
    ;;
esac

if [ ! -f "$MON_LOG" ]; then
  notify "Amazon日次チェック" "ログファイルが見つかりません。監視が止まっています。"
  exit 0
fi

# --- 1. 過去の欠測日を明示する ---
ADDED="$(python3 "$LOGIC" fill --json 2>/dev/null | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)["added"]))' 2>/dev/null || true)"

# --- 2. 今日ぶんの有無を見る ---
STATE="$(python3 "$LOGIC" status --json 2>/dev/null || echo '{}')"
TODAY_DONE="$(printf '%s' "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("today_done"))' 2>/dev/null || echo 'None')"
MISSING_N="$(printf '%s' "$STATE" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("missing",[])))' 2>/dev/null || echo 0)"
LAST_OK="$(printf '%s' "$STATE" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("last_ok"))' 2>/dev/null || echo '?')"

NOW_HHMM="$(date +%H%M)"
MSG=""

if [ -n "$ADDED" ]; then
  MSG="欠測を記録しました: ${ADDED}。"
fi

if [ "$TODAY_DONE" != "True" ] && [ "$NOW_HHMM" -ge "$DEADLINE_HHMM" ]; then
  MSG="${MSG}今日はまだ巡回していません（最後に成功したのは ${LAST_OK}）。Claude で /amazon-check を実行してください。"
fi

if [ -n "$MSG" ]; then
  notify "Amazon日次チェックが動いていません" "$MSG"
fi

# --- 3. 番犬自身の生存記録（Git 追跡対象＝ git log で改ざんなく確認できる）---
printf '%s 実行 / 今日=%s / 欠測=%s日 / 最終成功=%s\n' \
  "$(date '+%Y-%m-%d %H:%M')" \
  "$([ "$TODAY_DONE" = "True" ] && echo 済 || echo 未)" \
  "$MISSING_N" "$LAST_OK" > "$HEARTBEAT"

exit 0
