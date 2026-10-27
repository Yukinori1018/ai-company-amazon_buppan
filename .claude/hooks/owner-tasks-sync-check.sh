#!/bin/bash
# Stop フック: 社長タスクまとめ 自動同期チェック
#
# 役割: ターン終了時に workspace/tickets/ 配下のチケットが
# workspace/owner-tasks.md より新しく更新されていれば、
# 「社長タスクまとめ」（ローカル + Notion まとめカード）の更新を促す。
#
# 設計:
# - 社長のタスク＝waiting/ のチケット（CLAUDE.md §A4：waiting は「社長の番」）
# - 次のどちらかなら未同期とみなしてブロックする（1ターンにつき1回だけ）
#     (a) waiting/ のチケットが owner-tasks.md より新しく更新されている
#     (b) waiting/ にあるのに owner-tasks.md に ticket_id が1度も出てこない（＝新しく社長の番になった）
# - owner-tasks.md を更新（または touch）すると条件が自動解除（ループしない）
# - stop_hook_active=true（継続中）なら再ブロックしない安全弁
#
# 2026-10-27 改修（T-20261027-001）
#   - 8/21〜10/27 は settings.json の引用符の欠落（パスの空白）で一度も動いていなかった
#   - 旧版は「tickets/ 配下のどれかが owner-tasks.md より新しい」で止めていた。doing/ のログ追記でも
#     毎ターン止まり、しかも mv は更新時刻を変えないので「waiting へ移した」こと自体は拾えなかった。
#     社長の番かどうかで判定するよう (a)(b) に変えた
#   - Notion「社長タスクまとめ」カード（page_id 36db0a40…）への同期指示を削除。カードは
#     アーカイブ済みで 404（memory: project_stale_reference_cleanup）。Notion 側の正は waiting 列

set -euo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SUMMARY="$REPO/workspace/owner-tasks.md"
WAITING_DIR="$REPO/workspace/tickets/waiting"

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

[ -d "$WAITING_DIR" ] || exit 0

CHANGED=""
MISSING=""
if [ -f "$SUMMARY" ]; then
  CHANGED="$(find "$WAITING_DIR" -name 'T-*.md' -newer "$SUMMARY" 2>/dev/null || true)"
  for f in "$WAITING_DIR"/T-*.md; do
    [ -e "$f" ] || continue
    id="$(basename "$f" | grep -oE 'T-[0-9]{8}-[0-9]{3}' | head -1 || true)"
    [ -n "$id" ] || continue
    grep -q -- "$id" "$SUMMARY" 2>/dev/null || MISSING="${MISSING}${id}
"
  done
else
  CHANGED="$(find "$WAITING_DIR" -name 'T-*.md' 2>/dev/null || true)"
fi

[ -z "$CHANGED" ] && [ -z "$MISSING" ] && exit 0

CHANGED_REL="$(printf '%s\n' "$CHANGED" | sed "s|^$REPO/||" | sed '/^$/d')"
MISSING_TXT="$(printf '%s' "$MISSING" | sed '/^$/d')"

REASON="【社長タスクまとめ 自動同期チェック】
社長の番（waiting/）のチケットが workspace/owner-tasks.md に反映されていません。終了前に owner-tasks.md を最新化してください。

waiting/ で owner-tasks.md より新しく更新されたチケット:
${CHANGED_REL:-（なし）}

waiting/ にあるのに owner-tasks.md に載っていないチケット:
${MISSING_TXT:-（なし）}

担当: マリエ（庶務）。カズヨは「この作業はマリエです」と宣言してマリエに発注する。軽微・即時なら代行可。

手順:
1. 上のチケットの frontmatter と本文から、社長がやること（承認・判断・レビュー・手作業）を抜き出す
2. workspace/owner-tasks.md を更新する（🔴/🟡/🟢/ℹ️ の区分と「最終更新」日付も）
3. Notion 側は各チケットのカードの Status=waiting が正。まとめカードは廃止済みなので同期しない
※ 社長がやることに影響しない変更なら、確認済みとして owner-tasks.md の最終更新日だけ直す（または touch workspace/owner-tasks.md）。"

if command -v jq >/dev/null 2>&1; then
  jq -n --arg r "$REASON" '{decision:"block", reason:$r}'
else
  printf '%s\n' "$REASON" >&2
  exit 2
fi

exit 0
