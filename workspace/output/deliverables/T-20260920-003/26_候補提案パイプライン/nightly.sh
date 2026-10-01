#!/bin/bash
# 夜間に「仕入れ先起点の候補を積む」1晩ぶん。**1日のトークン上限を跨いで守ります。**
#
#   ./nightly.sh                 # 既定（1日6,000トークン・最長5時間）
#   ./nightly.sh 3000 180        # 1日3,000トークン・最長180分
#   ./nightly.sh stop            # 止める（STOP ファイルを置く）
#   ./nightly.sh start           # 再開する（STOP を消す）
#   ./nightly.sh status          # 今日の消費と残りを見る
#
# 自動で止まる条件（4つ）
#   1. 1日のトークン上限に達した（`daily_token_budget.json` でプロセスを跨いで数える）
#   2. 通算時間の上限
#   3. 未投入の JAN が尽きた
#   4. STOP ファイルがある
#
# ⚠️ **launchd への登録はしていません。**常設の設定変更は社長の許可が要るので
#    （memory: knowledge_keepa_token_ceiling_and_unattended_scan §10）、
#    `com.aicompany.amazon-buppan.night-shift.plist.disabled` と同じ扱いで
#    plist は README に手順だけ書いてあります。
#
# ⚠️ **Keepa の API キーは全チケット共有の1本です。**この夜間走行が走っている間、
#    他のチケットは Keepa をほぼ使えません（補充20/分）。昼に走らせないこと。

set -u
REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
HERE="$REPO/workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
WORK="$REPO/workspace/output/agent_output/T-20260920-003/pipeline"
STOP="$WORK/STOP"
LOG="$WORK/nightly.log"

case "${1:-}" in
  stop)   mkdir -p "$WORK" && touch "$STOP"; echo "STOP を置きました: $STOP"; exit 0 ;;
  start)  rm -f "$STOP"; echo "STOP を外しました。次の起動から走ります。"; exit 0 ;;
  status)
    [ -f "$STOP" ] && echo "  STOP あり（停止中）" || echo "  STOP なし"
    python3 - <<'PY'
import json, pathlib
from datetime import date
p = pathlib.Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003/pipeline/daily_token_budget.json")
d = json.loads(p.read_text()) if p.exists() else {}
print(f"  今日の消費: {d.get(date.today().isoformat(), 0)} トークン")
t = pathlib.Path(p.parent / "tried_jans.json")
print(f"  既に投げた JAN: {len(json.loads(t.read_text())) if t.exists() else 0:,}件 / 索引 67,662件")
PY
    exit 0 ;;
esac

DAILY="${1:-6000}"          # 1日に使ってよい総量
MINUTES="${2:-300}"         # 通算の上限（分）

# 配分。段A（1.17/JAN）で母数を作り、安い段（1/ASIN）でランクを取り、
# 高い段（6.9/ASIN）は通過しそうな順にだけ掛ける。**二段構えを崩さないこと。**
A=$((DAILY * 2 / 3))        # 段A: JAN → ASIN
B=$((DAILY / 3))            # ランク取り直し + §3.3 ゲート

{
  echo "===== $(date '+%F %T') 夜間走行 開始（1日上限 ${DAILY} / 最長 ${MINUTES}分）====="
  # 取引条件の表（SD 163社）を取り直す。Keepa トークンは使いません。
  # ⚠️ 失敗しても止めません。`trading_terms` は「読めなかった」を UNKNOWN として返すので、
  #    表が無い晩に全件 ○ 扱いで走ることはありません。
  python3 -u "$HERE/trading_terms.py" --refresh || echo "（取引条件の表は読めませんでした。UNKNOWN で進みます）"
  python3 -u "$HERE/run_supplier_first.py" --total-tokens "$A" --daily-tokens "$DAILY" \
      --floor 0 --minutes $((MINUTES / 2))
  python3 -u "$HERE/rank_pass.py" --minutes $((MINUTES / 6))
  python3 -u "$HERE/run_stage_b.py" --total-tokens "$B" --floor 0 \
      --minutes $((MINUTES / 3)) --min-wave 200
  python3 -u "$HERE/write_report.py"
  echo "===== $(date '+%F %T') 夜間走行 終了 ====="
} >> "$LOG" 2>&1
