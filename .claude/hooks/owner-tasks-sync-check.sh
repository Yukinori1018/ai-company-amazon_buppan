#!/bin/bash
# Stop フック: 社長タスクまとめ 自動同期チェック
#
# 役割: ターン終了時に workspace/tickets/ 配下のチケットが
# workspace/owner-tasks.md より新しく更新されていれば、
# 「社長タスクまとめ」（ローカル + Notion まとめカード）の更新を促す。
#
# 設計:
# - チケット状態が動く = 社長のタスクが増減/変更されうる、という前提
# - owner-tasks.md より新しいチケットがあれば未同期とみなしてブロック
# - owner-tasks.md を更新すると owner-tasks.md が最新になり条件が自動解除（ループしない）
# - stop_hook_active=true（継続中）なら再ブロックしない安全弁

set -euo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SUMMARY="$REPO/workspace/owner-tasks.md"
TICKETS_DIR="$REPO/workspace/tickets"
CARD_ID="36db0a40-44fa-815b-a60b-f854b6cd431d"

INPUT="$(cat)"

# 無限ループ防止: 既に Stop フック継続中なら何もしない
stop_active="false"
if command -v jq >/dev/null 2>&1; then
  stop_active="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false')"
else
  if printf '%s' "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    stop_active="true"
  fi
fi
[ "$stop_active" = "true" ] && exit 0

[ -d "$TICKETS_DIR" ] || exit 0

# owner-tasks.md より新しいチケット = 未同期
if [ -f "$SUMMARY" ]; then
  CHANGED="$(find "$TICKETS_DIR" -name '*.md' -newer "$SUMMARY" 2>/dev/null || true)"
else
  CHANGED="$(find "$TICKETS_DIR" -name '*.md' 2>/dev/null || true)"
fi

[ -z "$CHANGED" ] && exit 0

CHANGED_REL="$(printf '%s\n' "$CHANGED" | sed "s|^$REPO/||")"

REASON="【社長タスクまとめ 自動同期チェック】
チケットが workspace/owner-tasks.md より新しく更新されています。終了前に社長の「📋 社長タスクまとめ」を最新化してください。

変更されたチケット:
${CHANGED_REL}

手順:
1. 各チケットの frontmatter（status / assignee）と本文から、社長アクションが必要なタスク（owner 依存・承認待ち・情報提供待ち・レビュー待ち）を再抽出する
2. workspace/owner-tasks.md を更新する（🔴/🟡/🟢/ℹ️ の区分と「最終更新」日付も）
3. Notion まとめカード（page_id ${CARD_ID}、Status=「まとめ」を維持）へ同期する
※ 社長アクションに影響しない変更だった場合は、確認済みとして owner-tasks.md の最終更新日のみ更新（または touch workspace/owner-tasks.md）で構いません。"

if command -v jq >/dev/null 2>&1; then
  jq -n --arg r "$REASON" '{decision:"block", reason:$r}'
else
  printf '%s\n' "$REASON" >&2
  exit 2
fi

exit 0
