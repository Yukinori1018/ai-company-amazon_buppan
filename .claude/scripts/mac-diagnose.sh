#!/bin/bash
#
# mac-diagnose.sh — 「Mac 側の自動処理が止まった」時の原因を1コマンドで集める（T-20261016-002）
#
# 2026-09-06〜10-15 に Mac からのコミットが40日間止まりました。クラウドからは原因を
# 確定できない（Mac のログは Git の外にある）ので、Mac で1回これを打てば判別できるようにします。
#
# 使い方（Mac のターミナルで。リポが分岐していても動くよう、origin から直接読む）:
#   cd "/Users/yukinori/Claude Code/ai-company-amazon_buppan"
#   git fetch -q origin && git show origin/main:.claude/scripts/mac-diagnose.sh | bash
#
# 読むだけ。何も書き換えません（commit・push・launchctl load もしない）。
#
set -uo pipefail
REPO="${REPO:-/Users/yukinori/Claude Code/ai-company-amazon_buppan}"
cd "$REPO" 2>/dev/null || { echo "リポジトリが見つかりません: $REPO"; exit 0; }

sec() { printf '\n===== %s =====\n' "$1"; }

sec "1. github-sync のログ（末尾30行）— ERROR / STOP / HOLD / SKIP が原因を示す"
tail -30 workspace/.sync/github-sync.log 2>/dev/null || echo "ログなし（github-sync が一度も走っていない／ログが消えた）"

sec "2. launchd ジョブ（2列目が最後の終了コード。0=正常 127=スクリプトなし）"
launchctl list 2>/dev/null | grep -i aicompany || echo "aicompany のジョブが1つも登録されていません（plist が unload されている）"

sec "3. ローカルと GitHub の差（ahead=Mac にだけある / behind=GitHub にだけある）"
git rev-list --left-right --count origin/main...HEAD 2>/dev/null | awk '{print "behind=" $1 "  ahead=" $2}'
git log --oneline -5 --format='%h %ad %s' --date=format:'%m-%d %H:%M' 2>/dev/null

sec "4. 未コミットの変更（多い・新規ファイルがあれば pre-commit ゲートが止めている可能性）"
git status --porcelain 2>/dev/null | head -20
echo "（件数: $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')）"

sec "5. pre-commit ゲートの試走（今ステージすると止まるか。index は戻します）"
if [ -n "$(git status --porcelain --untracked-files=all 2>/dev/null | grep '^??' || true)" ]; then
  tmp_index="$(mktemp "${TMPDIR:-/tmp}/diag-index.XXXXXX")"
  cp .git/index "$tmp_index"
  GIT_INDEX_FILE="$tmp_index" git add -A >/dev/null 2>&1
  if GIT_INDEX_FILE="$tmp_index" bash .githooks/pre-commit >/dev/null 2>&1; then
    echo "通過：ゲートは自動同期を止めていません"
  else
    echo "★ 停止：今の未追跡ファイルを git add -A すると pre-commit が commit を止めます（自動同期が止まる原因）"
    GIT_INDEX_FILE="$tmp_index" bash .githooks/pre-commit 2>&1 | grep '  - ' | head -10
  fi
  rm -f "$tmp_index"
else
  echo "未追跡ファイルなし（ゲートが原因ではない）"
fi

sec "6. Claude アプリが起動していた日（~/.claude/session-env の日付。抜けている日＝開かなかった日）"
ls -lt ~/.claude/session-env/ 2>/dev/null | awk 'NR>1{print $6, $7}' | uniq -c | head -15 || echo "記録なし"

sec "7. スケジュールタスクの定義があるか"
ls -la ~/.claude/scheduled-tasks/amazon-seller-central-daily-check/ 2>/dev/null || echo "★ 定義フォルダがありません"

sec "8. スリープ／起動／シャットダウン（直近15件）"
pmset -g log 2>/dev/null | grep -E ' (Sleep|Wake|Shutdown|Start) ' | tail -15 || echo "取得できません"

sec "9. 100MB 超のファイル（push 失敗の原因になる）"
find . -path ./.git -prune -o -type f -size +100M -print 2>/dev/null | head -5
echo "(以上)"
