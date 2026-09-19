#!/bin/bash
# メーカーリスト拡充を頭から通す。09:00 JST まで待ってから取得を始める。
#
#   bash scripts/maker_list/run_pipeline.sh            # 9時まで待って実行
#   NOWAIT=1 bash scripts/maker_list/run_pipeline.sh   # 待たずに実行（9-21時内であること）
#
# 取得してよい時間帯は 09:00〜21:00 JST（05_リスト拡充の法務判定 §2-4）。
# 1日1,500リクエストの上限に当たったら途中で止まる。翌日もう一度同じコマンドを
# 打てば続きから走る（済んだ社は飛ばす）。
set -u
cd "$(dirname "$0")/../.." || exit 1
LOG=workspace/output/agent_output/T-20260920-002/S-F/pipeline.log
exec >>"$LOG" 2>&1
echo "=== $(date '+%F %T %Z') パイプライン開始 ==="

if [ "${NOWAIT:-0}" != "1" ]; then
  WAIT=$(python3 -c "
import datetime
jst=datetime.timezone(datetime.timedelta(hours=9))
n=datetime.datetime.now(jst)
t=n.replace(hour=9,minute=0,second=5,microsecond=0)
print(max(0,int((t-n).total_seconds())) if n.hour<9 else 0)")
  if [ "$WAIT" -gt 0 ]; then
    echo "09:00 JST まで ${WAIT} 秒待ちます（取得してよい時間帯の制限）"
    sleep "$WAIT"
  fi
fi

echo "--- (a) 業界団体名簿（保存済みHTML・ネット非接続） ---"
python3 scripts/maker_list/build_associations.py

echo "--- (a-2) NAPAC / 燕 の会社詳細ページ ---"
python3 scripts/maker_list/build_association_details.py

echo "--- (b) メーカー自社HPの巡回 ---"
python3 scripts/maker_list/crawl_maker_sites.py

echo "--- 再抽出（キャッシュから・ネット非接続） ---"
ALLOW_ANYTIME=1 python3 scripts/maker_list/reextract.py

echo "--- 統合・出力 ---"
python3 scripts/maker_list/merge_list.py

echo "=== $(date '+%F %T %Z') 完了 ==="
