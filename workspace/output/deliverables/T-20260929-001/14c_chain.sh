#!/bin/bash
# 名簿拡張 ① の無人仕上げ（T-20260929-001）。14a の取得ジョブを見張り、段ごとに 14b を回す。
#   ①a の取得が終わる（DONE_r14a ができる）→ 14b --bb --sheet（①a の代表のカート保持者を取ってシートへ）
#   14a が終わる（①b まで）              → 14b --bb --sheet（①b の分も）
# 見張りの決まり（memory knowledge_unattended_job_must_not_lie / knowledge_amazon_first_maker_extraction）
#   - 生存は kill -0 では見ない（停止 T でも成功する）。ps の stat が T なら SIGCONT で起こしてログに残す
#   - ログが 90 分更新されなければ STALL を書く（token 待ちでも 10 分ごとに1行は出る）
#   起動：nohup bash 14c_chain.sh <14a の PID> > ../../agent_output/T-20260929-001/14_roster/chain.log 2>&1 &
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../../agent_output/T-20260929-001/14_roster"
PID="$1"
LOG="$OUT/fetch_r14.log"
did_a=0
note() { echo "$(date '+%m-%d %H:%M') $*"; }
while ps -p "$PID" >/dev/null 2>&1; do
  st=$(ps -o stat= -p "$PID" | tr -d ' ')
  if [[ "$st" == T* ]]; then note "14a が停止(T)していたので SIGCONT"; kill -CONT "$PID"; fi
  age=$(( $(date +%s) - $(stat -f %m "$LOG") ))
  if (( age > 5400 )); then note "STALL: ログが ${age} 秒更新されていない"; fi
  if (( did_a == 0 )) && [[ -f "$OUT/DONE_r14a" ]]; then
    note "①a 取得完了 → 14b --bb --sheet"
    (cd "$HERE" && python3 14b_build_roster.py --bb --sheet > "$OUT/build_after_a.log" 2>&1) && note "14b 完了(①a)" || note "14b 失敗(①a) → build_after_a.log"
    did_a=1
  fi
  sleep 300
done
note "14a 終了（DONE: $(ls "$OUT" | grep DONE_ | tr '\n' ' ')）→ 14b --bb --sheet"
(cd "$HERE" && python3 14b_build_roster.py --bb --sheet > "$OUT/build_final.log" 2>&1) && note "14b 完了(最終)" || note "14b 失敗(最終) → build_final.log"
