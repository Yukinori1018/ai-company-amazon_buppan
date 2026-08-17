#!/bin/bash
#
# github-sync.sh — ローカル ⇄ GitHub の定期自動同期（T-20260817-007 / 親 T-20260531-001）
#
# 設計方針（CLAUDE.md §4.1「不可逆な操作は社長承認必須」に準拠）
#   - やること   : git add -A → commit → fetch → ff-only pull → push（カレントブランチのみ）
#   - やらないこと: force push / branch 削除 / reset --hard / rebase / main への自動マージ
#   - 分岐(diverge)を検知したら **何もせずログに残して終了**。人間が解決する。
#
# 起動: launchd `com.aicompany.amazon-buppan.github-sync`（30分間隔）
# ログ: workspace/.sync/github-sync.log（1MB でローテート・Git 非追跡）
#
set -uo pipefail

REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
LOG_DIR="$REPO/workspace/.sync"
LOG="$LOG_DIR/github-sync.log"
LOCK="$LOG_DIR/.lock"
MAX_LOG_BYTES=1048576                    # 1MB
QUIET_MIN="${QUIET_MIN:-5}"              # 直近この分数以内に変更されたファイルがあれば「編集中」とみなしコミットを見送る
STALE_LOCK_MIN="${STALE_LOCK_MIN:-30}"   # これより古いロックは異常終了の残骸とみなして解除

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LOG_DIR"
log() { printf '%s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

# --- ログローテート -----------------------------------------------------------
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt "$MAX_LOG_BYTES" ]; then
  mv -f "$LOG" "$LOG.1"
fi

# --- 多重起動防止（mkdir はアトミック）----------------------------------------
# 他の Claude セッションや夜間自走と同時に git を触ると index が壊れるため必須。
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +$STALE_LOCK_MIN 2>/dev/null)" ]; then
    log "WARN  ${STALE_LOCK_MIN}分以上前の古いロックを解除しました"
    rmdir "$LOCK" 2>/dev/null
    mkdir "$LOCK" 2>/dev/null || { log "SKIP  ロック取得に失敗"; exit 0; }
  else
    log "SKIP  別の同期プロセスが実行中"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || { log "ERROR リポジトリに cd できません: $REPO"; exit 1; }

# --- 安全チェック: git 操作の途中なら触らない ----------------------------------
GIT_DIR_PATH="$(git rev-parse --git-dir 2>/dev/null)" || { log "ERROR git リポジトリではありません"; exit 1; }
for marker in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD REVERT_HEAD; do
  if [ -e "$GIT_DIR_PATH/$marker" ]; then
    log "SKIP  git 操作が進行中（$marker）— 解決されるまで同期しません"
    exit 0
  fi
done

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" = "HEAD" ]; then
  log "SKIP  detached HEAD 状態のため同期しません"
  exit 0
fi

DID_SOMETHING=0

# --- 1) 変更をコミット --------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
  # 直近 QUIET_MIN 分以内に触られたファイルがあれば、セッションが編集中の可能性が高い。
  # 中途半端な状態を掴まないよう、コミットは次回に回す（push は行う）。
  newest=0
  while IFS= read -r -d '' entry; do
    path="${entry:3}"
    [ -f "$path" ] || continue
    m="$(stat -f %m "$path" 2>/dev/null)" || continue
    [ "$m" -gt "$newest" ] && newest="$m"
  done < <(git status --porcelain -z)

  now="$(date +%s)"
  if [ "$newest" -gt 0 ] && [ $((now - newest)) -lt $((QUIET_MIN * 60)) ]; then
    log "HOLD  直近${QUIET_MIN}分以内に更新されたファイルあり（編集中とみなしコミット見送り）"
  else
    git add -A
    if ! git diff --cached --quiet; then
      count="$(git diff --cached --name-only | wc -l | tr -d ' ')"
      if git commit -q -m "chore(auto-sync): $(date '+%Y-%m-%d %H:%M') 自動同期（${count}ファイル）

launchd com.aicompany.amazon-buppan.github-sync による定期自動コミット。
T-20260817-007 / .claude/scripts/github-sync.sh

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" 2>>"$LOG"; then
        log "COMMIT ${count}ファイルを自動コミット"
        DID_SOMETHING=1
      else
        log "ERROR コミットに失敗しました"
      fi
    fi
  fi
fi

# --- 2) リモート取得と分岐判定 -------------------------------------------------
if ! git fetch --quiet origin "$BRANCH" 2>>"$LOG"; then
  log "WARN  fetch に失敗（ネットワーク/認証）— 今回はここで終了"
  exit 0
fi

ahead=0
behind=0
if git rev-parse --verify -q "origin/$BRANCH" >/dev/null; then
  set -- $(git rev-list --left-right --count "origin/$BRANCH...HEAD")
  behind="${1:-0}"
  ahead="${2:-0}"

  if [ "$behind" -gt 0 ] && [ "$ahead" -gt 0 ]; then
    log "STOP  分岐を検知（origin が +$behind / ローカルが +$ahead）— force push は行いません。手動でマージしてください"
    exit 0
  fi

  if [ "$behind" -gt 0 ]; then
    if git merge --ff-only "origin/$BRANCH" >>"$LOG" 2>&1; then
      log "PULL  origin から ${behind} コミットを ff-only で取り込み"
      DID_SOMETHING=1
    else
      log "WARN  ff-only 取り込みに失敗（作業ツリーが汚れている可能性）"
      exit 0
    fi
  fi
else
  # リモートに未作成のブランチ → 初回 push で作る
  ahead=1
fi

# --- 3) push ------------------------------------------------------------------
if [ "$ahead" -gt 0 ]; then
  if git push --quiet origin "HEAD:$BRANCH" 2>>"$LOG"; then
    log "PUSH  $BRANCH → origin（${ahead}コミット）"
    DID_SOMETHING=1
  else
    log "ERROR push に失敗しました（force は行いません）"
  fi
fi

[ "$DID_SOMETHING" -eq 0 ] && log "NOOP  同期済み（$BRANCH）"
exit 0
