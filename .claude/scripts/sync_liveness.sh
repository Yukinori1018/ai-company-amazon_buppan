#!/bin/bash
#
# sync_liveness.sh — Mac の自動同期（launchd github-sync / 30分ごと）が生きているかを
#                    **Git の履歴だけ**で判定する（T-20261016-002 / 2026-10-16）。
#
# なぜ要るか:
#   2026-09-06 19:05 の自動同期を最後に、Mac からのコミットが 40 日間ゼロでした。
#   Mac 側の番犬（launchd）は通知センターにしか出さず、Mac が止まっていれば番犬も止まります。
#   **Mac の外から見える唯一の証拠は「GitHub に自動同期コミットが届いているか」**です。
#   これならクラウドのセッションでもスケジュールタスクでも同じ判定ができます。
#
# 判定の根拠:
#   Mac が起きていれば番犬が 12:30 / 19:00 に watchdog-last-run.txt を書き換え、
#   github-sync がそれを `chore(auto-sync)` でコミットします。平常なら最大でも
#   約17.5時間（19:05 → 翌12:35）おき。24時間空いたら「Mac 側の何かが止まっている」。
#
# 使い方:
#   bash .claude/scripts/sync_liveness.sh           止まっている時だけ警告文を出す（平常時は無出力）
#   bash .claude/scripts/sync_liveness.sh --status  常に1行で状態を出す
#   THRESH_HOURS=48 bash ...                        閾値を変える（既定 24）
#
# やらないこと: fetch（フックを遅くしない。見えている参照だけで判定する）。
#
set -uo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
THRESH_HOURS="${THRESH_HOURS:-24}"
MODE="${1:-warn}"

# --all: クラウドでは HEAD が origin より古いことがあるので、見えている全参照から探す
last_ct="$(git -C "$REPO" log --all -1 --format=%ct --grep='chore(auto-sync)' 2>/dev/null || true)"
now="$(date +%s)"

if [ -z "$last_ct" ]; then
  msg="Mac の自動同期コミット（chore(auto-sync)）が手元の履歴に見当たりません。浅い clone で判定できないか、長期間止まっています。"
  if [ "$MODE" = "--status" ]; then echo "判定不能: $msg"; else echo "$msg"; fi
  exit 0
fi

age_h=$(( (now - last_ct) / 3600 ))
last_jst="$(TZ=Asia/Tokyo date -d "@$last_ct" '+%Y-%m-%d %H:%M' 2>/dev/null \
  || TZ=Asia/Tokyo date -r "$last_ct" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "$last_ct")"

if [ "$age_h" -ge "$THRESH_HOURS" ]; then
  days=$(( age_h / 24 ))
  echo "Mac の自動同期が ${age_h} 時間（約${days}日）止まっています。最後の自動同期コミット: ${last_jst} JST。"
  exit 0
fi

[ "$MODE" = "--status" ] && echo "正常: 最後の自動同期コミット ${last_jst} JST（${age_h} 時間前）"
exit 0
