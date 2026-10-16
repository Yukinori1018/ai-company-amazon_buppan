#!/bin/bash
#
# sync_liveness.sh — Mac の自動同期（launchd github-sync / 30分ごと）が「生きているか」と
#                    「main に届いているか」を **Git の履歴だけ**で判定する（T-20261016-002）。
#
# なぜ要るか（2026-10-16 に分かったこと）:
#   クラウドから main を見ると、9/6 19:50 を最後に Mac からのコミットが40日間ゼロに見えました。
#   実際は Mac は毎日動いていて、**リポジトリが `claude/nighttime-work-checkin-iTWEa` ブランチに
#   居続けたため**、github-sync（カレントブランチだけを同期する）が1,193コミットを全部そのブランチへ
#   push していました。main だけを見る人（クラウドのセッション・秘書）には「止まった」と見え、
#   40日前の状態から作業を続けていました。
#   → 判定は2つ要る。①自動同期が動いているか（どのブランチでもよい）②それが main に届いているか。
#
# 判定の根拠:
#   Mac が起きていれば番犬が 12:30 / 19:00 に心拍ファイルを書き換え、github-sync がそれを
#   `chore(auto-sync)` でコミットする。平常なら最大でも約17.5時間おき。24時間空いたら停止。
#
# 使い方:
#   bash .claude/scripts/sync_liveness.sh           異常な時だけ警告文を出す（平常時は無出力）
#   bash .claude/scripts/sync_liveness.sh --status  常に状態を出す
#   bash .claude/scripts/sync_liveness.sh --branch  最新の自動同期が載っているブランチ名だけ出す
#   THRESH_HOURS=48 / SYNC_LIVENESS_NOFETCH=1       閾値の変更 / fetch を省く
#
# fetch について: クラウドの clone は main しか取っていないことが多く、そのままでは他ブランチの
#   自動同期が見えない（今回それで「40日停止」と誤判定した）。全ブランチを最大15秒だけ fetch する。
#   失敗しても手元の参照で判定を続け、その旨を出力に添える。
#
set -uo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
THRESH_HOURS="${THRESH_HOURS:-24}"
MODE="${1:-warn}"
cd "$REPO" || exit 0

FETCH_NOTE=""
if [ "${SYNC_LIVENESS_NOFETCH:-0}" != "1" ]; then
  if ! timeout 15 git fetch -q origin '+refs/heads/*:refs/remotes/origin/*' >/dev/null 2>&1; then
    FETCH_NOTE="（GitHub から最新を取れず、手元の参照だけで判定）"
  fi
fi

line="$(git log --remotes=origin -1 --format='%H %ct' --grep='chore(auto-sync)' 2>/dev/null || true)"
if [ -z "$line" ]; then
  line="$(git log --all -1 --format='%H %ct' --grep='chore(auto-sync)' 2>/dev/null || true)"
fi
if [ -z "$line" ]; then
  msg="Mac の自動同期コミット（chore(auto-sync)）が見当たりません${FETCH_NOTE}。"
  [ "$MODE" = "--branch" ] && exit 0
  echo "判定不能: $msg"
  exit 0
fi
sha="${line%% *}"
ct="${line##* }"

# その自動同期コミットを含むブランチ。main に含まれていれば main を優先して名乗る。
if git merge-base --is-ancestor "$sha" origin/main 2>/dev/null; then
  branch="main"
else
  branch="$(git branch -r --contains "$sha" --format='%(refname:short)' 2>/dev/null | grep -v '^origin/HEAD' | head -1 | sed 's#^origin/##')"
  branch="${branch:-不明}"
fi

if [ "$MODE" = "--branch" ]; then
  echo "$branch"
  exit 0
fi

now="$(date +%s)"
age_h=$(( (now - ct) / 3600 ))
fmt() { TZ=Asia/Tokyo date -d "@$1" '+%Y-%m-%d %H:%M' 2>/dev/null || TZ=Asia/Tokyo date -r "$1" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "$1"; }
last_jst="$(fmt "$ct")"

out=""
if [ "$age_h" -ge "$THRESH_HOURS" ]; then
  out="${out}Mac の自動同期が ${age_h} 時間（約$(( age_h / 24 ))日）止まっています。最後の自動同期: ${last_jst} JST（ブランチ ${branch}）${FETCH_NOTE}。
"
fi
if [ "$branch" != "main" ]; then
  main_ct="$(git log origin/main -1 --format=%ct --grep='chore(auto-sync)' 2>/dev/null || true)"
  main_last="$( [ -n "$main_ct" ] && fmt "$main_ct" || echo 'なし')"
  ahead="$(git rev-list --count "origin/main..origin/${branch}" 2>/dev/null || echo '?')"
  out="${out}**Mac のリポジトリは main ではなく \`${branch}\` に同期しています**（main に無い Mac のコミット ${ahead} 件・main に届いた最後の自動同期 ${main_last}）。main を見ている人には Mac が止まって見えます。Mac の最新状態は \`git show origin/${branch}:<パス>\` で読めます。
"
fi

if [ -n "$out" ]; then
  printf '%s' "$out"
elif [ "$MODE" = "--status" ]; then
  echo "正常: 最後の自動同期 ${last_jst} JST（${age_h} 時間前・main に到達）${FETCH_NOTE}"
fi
exit 0
