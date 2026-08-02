#!/bin/bash
# PostToolUse フック：チケットファイル変更 → Notion 即時同期を強制
#
# 役割: workspace/tickets/ 配下の .md を作成・編集・移動・削除する操作を検知し、
#       「マリエの Notion 同期スキルに従って該当 TicketID を即時反映せよ」という
#       リマインダーを additionalContext で注入する。
#
# 背景: Notion はホスト型 MCP 経由でしか書けず、シェルから直接 API を叩けない
#       （ローカルに NOTION_API_KEY が無い）。よって「ファイル変更で自動同期」は
#       原理的に不可能。代わりに本フックが強制関数として働き、エージェントに
#       「同期せずに turn を終えるな」と促す。
#
# 設計:
# - PostToolUse / Write|Edit|MultiEdit|NotebookEdit|Bash にマッチ
# - チケット変更でない操作では無音（exit 0）
# - 検知時のみ JSON で additionalContext を返す

set -euo pipefail

export HOOK_INPUT="$(cat)"

REMINDER="$(python3 - <<'PY'
import json, os, re, sys

try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}

paths = []
mutating = False

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    p = ti.get("file_path") or ti.get("notebook_path") or ""
    if p:
        paths.append(p)
        mutating = True
elif tool == "Bash":
    cmd = ti.get("command", "") or ""
    # チケットを物理的に動かす/消す操作のみ対象（参照系 ls/cat/sed 等は除外）
    if "workspace/tickets/" in cmd and re.search(r'\b(mv|cp|rm|git\s+mv|git\s+rm)\b', cmd):
        paths.append(cmd)
        mutating = True

if not mutating:
    sys.exit(0)

blob = " ".join(paths)
if "workspace/tickets/" not in blob:
    sys.exit(0)

ids = sorted(set(re.findall(r'T-\d{8}-\d{3}', blob)))
id_str = "、".join(ids) if ids else "（ファイル名から TicketID を確認）"

print(
    "⚠️ チケットファイルの変更を検知しました（" + id_str + "）。\n"
    "庶務マリエの責務として、agents/general_affairs/skills/notion-ticket-sync.md に従い、"
    "この turn を終える前に該当チケットを Notion カンバン（Amazon物販事業 Tickets）へ即時同期してください。\n"
    "- 新規起票 → notion-create-pages でカード作成\n"
    "- 状態遷移/内容更新 → TicketID で該当カードを特定し notion-update-page で Status/UpdatedAt 等を更新\n"
    "未同期のまま応答を終えないこと。"
)
PY
)" || exit 0

[ -z "$REMINDER" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$REMINDER" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $msg
    }
  }'
else
  printf '%s\n' "$REMINDER"
fi

exit 0
