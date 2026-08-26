#!/usr/bin/env bash
# マスターToDoリスト再生成の機械側。判断が要らない工程を全部まとめてある。
#
#   scripts/todo.sh prepare [ticket_id]   … 作業場を用意し、チケットを棚卸しする
#   scripts/todo.sh build   [ticket_id]   … 集計・ボード更新・HTML生成・検算
#
# ticket_id 既定は T-20260826-002（社長の既存リストを上書き更新する）。
# 別 ID を渡すと、既存リストを骨格として複製してからそこに作り直す。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
BASE_TICKET="T-20260826-002"   # 骨格 208 項目の出どころ

cmd="${1:-}"
TID="${2:-$BASE_TICKET}"
DELIV="$REPO/workspace/output/deliverables/$TID"
WORK="$REPO/workspace/output/agent_output/$TID"
BASE_DELIV="$REPO/workspace/output/deliverables/$BASE_TICKET"
BASE_WORK="$REPO/workspace/output/agent_output/$BASE_TICKET"

case "$cmd" in
prepare)
  mkdir -p "$DELIV" "$WORK"
  # 骨格は毎回作り直さない。無いときだけ既存リストから複製する。
  for f in 01_master-todo.md 02_lifecycle-checklist.md 03_process-board.html README.md; do
    if [ ! -e "$DELIV/$f" ] && [ -e "$BASE_DELIV/$f" ]; then
      cp "$BASE_DELIV/$f" "$DELIV/$f"
      echo "seeded: $DELIV/$f"
    fi
  done
  # 更新前の姿を控えておく。あとで「何が変わったか」を diff で説明できる。
  cp "$DELIV/01_master-todo.md" "$WORK/00_before_master-todo.md"

  # 台帳には前回の分類が入っている。上書きする前に必ず控えを取る
  # （agent_output は .gitignore 対象で、消すと git からは戻せない）。
  PREV="$WORK/01_ticket-inventory.md"
  [ -e "$PREV" ] || PREV="$BASE_WORK/01_ticket-inventory.md"
  if [ -e "$PREV" ]; then
    cp "$PREV" "$WORK/01_ticket-inventory.$(date +%Y%m%d-%H%M%S).bak.md"
  fi
  python3 "$HERE/ticket_inventory.py" "$REPO/workspace/tickets" \
    "$WORK/01_ticket-inventory.md" --prev "$PREV"

  echo
  echo "編集対象: $DELIV/01_master-todo.md"
  echo "骨格の原本（本文は触らない）: $DELIV/02_lifecycle-checklist.md"
  ;;

build)
  [ -e "$DELIV/01_master-todo.md" ] || { echo "先に prepare を実行してください"; exit 1; }
  awk -f "$HERE/aggregate.awk" "$DELIV/01_master-todo.md" > "$WORK/counts.json"
  TICKETS=$(grep -c '^| T-' "$WORK/01_ticket-inventory.md" || echo 0)
  python3 "$HERE/update_board.py" "$DELIV/03_process-board.html" "$WORK/counts.json" \
    --tickets "$TICKETS"
  python3 "$HERE/render_html.py" \
    "$DELIV/01_master-todo.md" "$DELIV/01_master-todo.html" \
    --title "Amazon物販 マスターToDoリスト｜$TID" \
    --footer "$TID ／ 制作: ヒデアキ ／ $(date +%Y-%m-%d) ／ 骨格: サトル ・ 進捗根拠: マリエ"
  echo
  python3 "$HERE/verify.py" "$DELIV"
  echo
  echo "更新前との差分（小項目の行のみ。行番号は入れない＝挿入でズレないように）:"
  diff <(grep '^- \[' "$WORK/00_before_master-todo.md" || true) \
       <(grep '^- \[' "$DELIV/01_master-todo.md" || true) || true
  echo
  echo "Artifact 再発行用（カズヨへ渡すパス）:"
  echo "  $DELIV/03_process-board.html"
  ;;

*)
  sed -n '2,10p' "${BASH_SOURCE[0]}"
  exit 2
  ;;
esac
