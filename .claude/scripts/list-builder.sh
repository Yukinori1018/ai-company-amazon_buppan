#!/bin/bash
#
# list-builder.sh — 候補リスト常時稼働ジョブの入口（T-20260831-002）
#
#   ./list-builder.sh            launchd から呼ばれる本体（常駐ループ）
#   ./list-builder.sh stop       止める（STOP ファイルを置くだけ）
#   ./list-builder.sh start      再開する（STOP ファイルを消す）
#   ./list-builder.sh status     今どうなっているかを1画面で見る
#   ./list-builder.sh once       1セッションだけ試す（検証用）
#   ./list-builder.sh resume-research   母数枯渇で終了した状態から再開する
#                                       （★社長の指示があるときだけ打つ）
#
# 設計方針は github-sync.sh に倣っています（PATH を明示・ログをローテート・
# 異常でも exit 0）。**異常終了しないのが肝**で、launchd の KeepAlive と
# 組み合わせたときに10秒ごとの再起動ストームを作らないためです。
#
set -uo pipefail

REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
JOB="$REPO/workspace/output/deliverables/T-20260831-002"
V14="$REPO/workspace/output/deliverables/T-20260817-005/v14"
STOP="$V14/STOP"
ALERT="$V14/ALERT.md"

# launchd の環境には Homebrew の PATH が無い。github-sync.sh と同じ形で明示する。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"

case "${1:-run}" in
  stop)
    mkdir -p "$V14" && touch "$STOP"
    echo "止めました。次のバッチの切れ目で安全に停止します（CSV は全部残ります）。"
    echo "再開: $0 start"
    ;;
  start)
    rm -f "$STOP"
    echo "STOP を外しました。常駐ジョブが次の見直し（最大5分後）で走り始めます。"
    ;;
  status)
    echo "== 稼働状態 =="
    [ -f "$STOP" ]  && echo "  STOP あり（停止中）" || echo "  STOP なし"
    [ -f "$ALERT" ] && { echo "  ⚠ ALERT あり:"; sed -n '5,12p' "$ALERT"; } || echo "  ALERT なし"
    echo
    echo "== launchd =="
    launchctl list | grep -E 'list-builder' || echo "  未登録"
    echo
    echo "== 最新のロールアップ =="
    [ -f "$JOB/daily/latest.json" ] && "$PYTHON" -c "
import json,sys
d=json.load(open('$JOB/daily/latest.json',encoding='utf-8'))
print(f\"  {d['generated_at']} / {d['status']}\")
print(f\"  候補 {d['totals']['go']}件 (+{d['delta']['go']}) / メーカー {d['totals']['makers']}社 (+{d['delta']['makers']})\")
" || echo "  まだありません"
    echo
    echo "== 直近のログ =="
    tail -n 8 "$JOB/state/always_on.log" 2>/dev/null || echo "  まだありません"
    ;;
  resume-research)
    "$PYTHON" "$JOB/always_on.py" --resume-research
    echo "リサーチを再開しました。常駐ジョブが次の見直し（最大30分後）で走り始めます。"
    echo "すぐ始めたいなら: launchctl kickstart -k gui/$(id -u)/com.aicompany.amazon-buppan.list-builder"
    ;;
  once)
    exec "$PYTHON" "$JOB/always_on.py" --once
    ;;
  preflight)
    exec "$PYTHON" "$JOB/always_on.py" --preflight
    ;;
  run)
    exec "$PYTHON" "$JOB/always_on.py"
    ;;
  *)
    echo "使い方: $0 [run|stop|start|status|once|preflight|resume-research]" >&2
    exit 0
    ;;
esac
exit 0
