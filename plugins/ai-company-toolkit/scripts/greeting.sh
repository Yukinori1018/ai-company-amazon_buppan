#!/bin/bash
# ai-company-toolkit プラグイン — SessionStart 起動バナー
#
# 役割: セッション開始時に、会社のミッションと最重要 KPI を 1 ブロックだけ
#       秘書カズヨへ思い出させる。プラグインの hooks 機能と
#       ${CLAUDE_PLUGIN_ROOT} 変数の動作確認も兼ねる。
#
# 設計:
# - additionalContext で短い行動リマインドを注入（数行に抑える）
# - 既存の workspace/tickets リマインダー（リポ側 .claude/hooks）とは
#   責務が重複しないよう、ここでは KPI バナーのみ。

set -euo pipefail

MESSAGE="【ai-company-toolkit】会社の北極星リマインド
- ミッション: Amazon 上で利益と販売確度の高い SKU を 100 積み上げ、月商800万円・利益率20%を達成する
- 最重要KPI: 月商800万円 / 利益率20%以上 / SKU数100
- 秘書カズヨは結論ファースト・チケット駆動・§4.1該当は承認待ちで運用すること。
- KPI の現状を素早く出したい時は kpi-check スキルを使う。"

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$MESSAGE" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $msg
    }
  }'
else
  printf '%s\n' "$MESSAGE"
fi

exit 0
