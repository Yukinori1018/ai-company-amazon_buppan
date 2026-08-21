#!/bin/bash
# SessionStart リマインダーフック
#
# 役割: workspace/tickets/doing/ 配下のチケットを走査し、frontmatter の
# `next_check_at` が今日以前のものをリマインダーとしてセッションへ注入する。
#
# 設計判断:
# - 依存関係インストール用ではない（このリポはマークダウン中心）
# - Sync モード（リマインドは startup の最初に必ず見せたい）
# - JSON 出力で `additionalContext` にリマインド文を入れる
#
# 注: jq があれば使う、無ければ grep/awk でフロントマターを最小パースする

set -euo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(pwd)}"
# next_check_at は doing/（作業中）と waiting/（社長タスク一覧）の両方を走査する。
# 社長アクション待ちのチケットは waiting/ に置かれるため、日次リマインドの主対象。
#
# ⚠️ 必ず配列で持つこと（2026-08-21 修正）。
# 旧実装は空白区切りの文字列 + クォート無し for ループだった。このリポジトリのパスは
# `/Users/yukinori/Claude Code/...` と**フォルダ名に空白を含む**ため、単語分割で
# `/Users/yukinori/Claude` と `Code/workspace/tickets/doing` に割れ、`[ -d ]` が常に false。
# 結果、リマインダーが一度も発火していなかった（期限切れ33件が10日間無通知）。
TICKETS_DIRS=(
  "$REPO/workspace/tickets/doing"
  "$REPO/workspace/tickets/waiting"
)
TODAY="$(date +%Y-%m-%d)"

REMINDERS=""

for TICKETS_DIR in "${TICKETS_DIRS[@]}"; do
  [ -d "$TICKETS_DIR" ] || continue
  for f in "$TICKETS_DIR"/*.md; do
    [ -e "$f" ] || continue

    # frontmatter から next_check_at を抽出（YAML 形式 `next_check_at: YYYY-MM-DD`）
    next_check="$(awk '
      /^---$/ { in_fm++; next }
      in_fm == 1 && /^next_check_at:/ {
        sub(/^next_check_at:[[:space:]]*/, "")
        sub(/[[:space:]]+$/, "")
        print
        exit
      }
      in_fm >= 2 { exit }
    ' "$f")"

    [ -z "$next_check" ] && continue

    # 日付比較（ISO 8601 なので辞書順 = 時系列順）
    if [[ "$next_check" < "$TODAY" || "$next_check" == "$TODAY" ]]; then
      title="$(awk '
        /^---$/ { in_fm++; next }
        in_fm == 1 && /^title:/ {
          sub(/^title:[[:space:]]*/, "")
          print
          exit
        }
      ' "$f")"
      ticket_id="$(awk '
        /^---$/ { in_fm++; next }
        in_fm == 1 && /^ticket_id:/ {
          sub(/^ticket_id:[[:space:]]*/, "")
          print
          exit
        }
      ' "$f")"
      REMINDERS="${REMINDERS}- ${ticket_id}: ${title}（next_check_at=${next_check}、今日=${TODAY}）\n  ファイル: ${f#$REPO/}\n"
    fi
  done
done

# --- メッセージ組み立て ---
# 朝ルーティンとして、まず Notion リコンサイルを必ず促す（カズヨが /sync-notion を実行）。
# その後、next_check_at リマインダーがあれば続けて注入する。

SYNC_MSG="【秘書カズヨ宛・SessionStart：朝ルーティン①（最優先）】
セッション開始です。まず \`/sync-notion\` を実行し、workspace/tickets/ と Notion カンバンの整合を取ってください（リポジトリ→Notion の片方向・非破壊）。
- ブランチ分岐や前セッションの同期漏れ由来のドリフトはここで自己修復します。
- 差分が無ければそのまま即終了して構いません。社長の入力は不要（社長に /sync-notion を打たせない）。
- 責務は庶務マリエ。手順は agents/general_affairs/skills/notion-ticket-sync.md。"

if [ -n "$REMINDERS" ]; then
  # シェル変数の \n を実際の改行に展開
  REMINDERS_EXPANDED="$(printf '%b' "$REMINDERS")"

  REMINDER_MSG="

【SessionStart リマインダー②：next_check_at 到来】
以下のチケットが next_check_at に達しています。社長に進捗確認を切り出してください（簡潔に1〜2行で問いかけ、報告があればチケットと workspace/handover.md を更新）。

${REMINDERS_EXPANDED}
確認後の挙動:
- 進捗があった → ログ追記＋ next_check_at を翌日に更新 or done なら done/ へ移動
- 進捗なし → next_check_at を翌日に更新して継続リマインド
- 社長から後回し希望 → next_check_at を希望日に更新"
else
  REMINDER_MSG=""
fi

MESSAGE="${SYNC_MSG}${REMINDER_MSG}"

# JSON エスケープ（python が無い環境を考慮し、jq があれば使う）
if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$MESSAGE" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $msg
    }
  }'
else
  # jq が無ければ stdout に普通に出力（Claude は stdout も読む）
  printf '%s\n' "$MESSAGE"
fi

exit 0
