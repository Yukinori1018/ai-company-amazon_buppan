#!/bin/bash
# scheduled_task_health.py の回帰テスト：平常時は無出力／成果物が古い・ログに詰まりがあれば 🔴
set -u
cd "$(dirname "$0")/../../.."
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
P="$S/repo/workspace/output/agent_output/T-20260920-003/pipeline"; mkdir -p "$P" "$S/sess/a/b"; touch "$P/nightly.log"
NOW=$(date +%s); fmt(){ date -r "$1" '+%Y-%m-%d %H:%M:%S'; }
echo "$(fmt $NOW) [info] [CCDScheduledTasks] Dispatched x" > "$S/main.log"
echo "$(fmt $((NOW-172800))) [info] [CCDScheduledTasks] Skipping dispatch for old: global_limit (active=3, limit=3)" >> "$S/main.log"
echo "{\"scheduledTasks\":[{\"id\":\"amazon-buppan-nightly-sourcing\",\"enabled\":true,\"createdAt\":1000,\"cwd\":\"$S/repo\"}]}" > "$S/sess/a/b/scheduled-tasks.json"
run(){ CLAUDE_MAIN_LOG="$S/main.log" CLAUDE_SCHED_GLOB="$S/sess/*/*/scheduled-tasks.json" python3 .claude/hooks/scheduled_task_health.py; }
fail=0
[ -z "$(run)" ] && echo "PASS 平常時は無出力" || { echo "FAIL 平常時に出力"; fail=1; }
touch -t "$(date -r $((NOW-100000)) +%Y%m%d%H%M)" "$P/nightly.log"
run | grep -q "夜間作業が動いていない" && echo "PASS 成果物が古い" || { echo "FAIL 成果物が古いのに無出力"; fail=1; }
touch "$P/nightly.log"
echo "$(fmt $NOW) [info] [CCDScheduledTasks] Not auto-approving \"Bash\" in scheduled task \"t1\": no suggestions on request" >> "$S/main.log"
run | grep -q "t1：許可待ちで停止 1回" && echo "PASS 許可待ちを検出" || { echo "FAIL 許可待ち未検出"; fail=1; }
[ -z "$(CLAUDE_MAIN_LOG=/nonexistent CLAUDE_SCHED_GLOB=/nonexistent/x python3 .claude/hooks/scheduled_task_health.py)" ] && echo "PASS ログ無し環境は無音" || { echo "FAIL"; fail=1; }
exit $fail
