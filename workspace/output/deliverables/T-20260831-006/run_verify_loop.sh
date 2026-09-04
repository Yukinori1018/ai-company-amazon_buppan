#!/bin/bash
# NETSEA 候補 15,132件 を Keepa で検証しきるための無人ランナー（T-20260904-004 / A-1）。
#
# なぜループにしたか:
#   Keepa の補充は 20トークン/分 = 28,800/日。1件あたり実効2.0〜2.2トークンなので、
#   15,132件は **1日では終わりません**（実測見込み 26〜32時間）。
#   1本の長いプロセスにすると、途中経過が最後まで1度も CSV に出ません。
#   そこで --new-limit で「新規N件だけ検証して、その時点の全結果を CSV に書いて終わる」
#   短いジョブに割り、それを繰り返します。1周ごとに candidates.csv が最新化されます。
#
# 落ちても損は1周ぶんだけです（Keepa の結果は1バッチごとに keepa_facts.jsonl へ追記済み）。
#
# 使い方:
#   nohup bash run_verify_loop.sh > out/loop.log 2>&1 &
#   python3 netsea_scan.py --status        # 生死は心拍で見る。ps で見ない
#
# ⛔ 発注・購入は一切しません（CLAUDE.md §4.1）。データ取得と計算だけです。

set -u
cd "$(dirname "$0")" || exit 1

CHUNK=2500          # 1周で新規に検証する件数。約2,500×2.1トークン ≒ 5,250 → 約4.4時間
MAX_ROUNDS=40       # 暴走の絶対上限。15,132 / 2,500 ≒ 7周で終わる想定
STOP_FILE="out/STOP"

for round in $(seq 1 "$MAX_ROUNDS"); do
  if [ -f "$STOP_FILE" ]; then
    echo "[loop] $STOP_FILE があるので停止します（人が消すまで走りません）"
    exit 0
  fi

  echo "[loop] ===== round $round / $MAX_ROUNDS 開始 $(date '+%Y-%m-%d %H:%M:%S') ====="
  python3 netsea_scan.py --stage verify --new-limit "$CHUNK"
  rc=$?
  echo "[loop] round $round 終了 rc=$rc $(date '+%Y-%m-%d %H:%M:%S')"

  if [ "$rc" -ne 0 ]; then
    # 異常終了は「掘り切った」と区別する。黙って次に行かない。
    echo "[loop] !! 異常終了 (rc=$rc)。3分待って再試行します"
    sleep 180
    continue
  fi

  # 残りが 0 になったら終わり。**この判定は run_stats.json の実数だけを見る。**
  remaining=$(python3 -c "
import json,sys
try:
    print(json.load(open('run_stats.json'))['keepa']['unverified_remaining'])
except Exception as e:
    print('unknown', file=sys.stderr); print(-1)
")
  echo "[loop] 未検証の残り: $remaining 件"
  if [ "$remaining" = "0" ]; then
    echo "[loop] ✅ 全件の検証が完了しました $(date '+%Y-%m-%d %H:%M:%S')"
    exit 0
  fi
  if [ "$remaining" = "-1" ]; then
    echo "[loop] !! run_stats.json を読めませんでした。安全のため停止します"
    exit 1
  fi
done

echo "[loop] !! MAX_ROUNDS に達しました。未検証が残っています（上を確認してください）"
exit 1
