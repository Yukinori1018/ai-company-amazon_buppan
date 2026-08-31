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

# --- リマインダー③: _inbox_社長共有 の未処理ファイル検知（2026-08-21 追加 / T-20260821-009）---
#
# 背景: inbox は `.gitignore` 対象のため Git 差分に出ず、既存フック（PostToolUse のチケット同期・
#       Stop の owner-tasks チェック）はいずれもリポ内の**追跡ファイル**変更を起点に動く。
#       結果、inbox だけが全フックの死角になり、社長が置いたファイル21件が12日間放置された。
#       ここで「ファイルが在ること」自体を毎セッション数え、プル型トリガー（社長の申告）への依存を断つ。
#
# 数え方: inbox 直下のみ（`-maxdepth 1`）。`_archive/`（処理済みの受け皿）・README.txt（運用説明）・
#         .DS_Store（macOS 自動生成）は未処理カウントから除外する。

INBOX_DIR="$REPO/_inbox_社長共有"
INBOX_MSG=""

if [ -d "$INBOX_DIR" ]; then
  # 直下の通常ファイルのみを列挙（_archive/ 等のディレクトリは -type f で自然に除外される）
  INBOX_FILES="$(find "$INBOX_DIR" -maxdepth 1 -type f \
    ! -name 'README.txt' \
    ! -name '.DS_Store' \
    ! -name '.gitkeep' \
    -print 2>/dev/null || true)"

  if [ -n "$INBOX_FILES" ]; then
    INBOX_COUNT="$(printf '%s\n' "$INBOX_FILES" | grep -c . || true)"

    # 最古ファイルの更新日を取得（BSD stat = macOS。GNU stat にもフォールバック）
    OLDEST_DATE=""
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      d="$(stat -f '%Sm' -t '%Y-%m-%d' "$f" 2>/dev/null || stat -c '%y' "$f" 2>/dev/null | cut -d' ' -f1)"
      [ -n "$d" ] || continue
      if [ -z "$OLDEST_DATE" ] || [[ "$d" < "$OLDEST_DATE" ]]; then
        OLDEST_DATE="$d"
      fi
    done <<< "$INBOX_FILES"

    # 上位5件だけ名前を出す（大量投入時にコンテキストを埋めないため）
    INBOX_SAMPLE="$(printf '%s\n' "$INBOX_FILES" | head -5 | sed "s|^$INBOX_DIR/|  - |")"
    if [ "$INBOX_COUNT" -gt 5 ]; then
      INBOX_SAMPLE="${INBOX_SAMPLE}
  - …ほか $((INBOX_COUNT - 5)) 件"
    fi

    # 滞留日数を出す（2026-08-31 / T-20260831-003）。
    # 「最古 2026-08-30」より「9日間放置」のほうが行動を促す。日付だけだと古さが直感に入らない。
    INBOX_AGE=""
    if [ -n "$OLDEST_DATE" ] && command -v python3 >/dev/null 2>&1; then
      INBOX_AGE="$(python3 -c "
import datetime,sys
try:
    d=datetime.date.fromisoformat('$OLDEST_DATE')
    n=(datetime.date.today()-d).days
    print(f'・最古 {n} 日滞留' if n>0 else '・本日投函')
except Exception: pass
" 2>/dev/null)"
    fi

    INBOX_MSG="

【SessionStart リマインダー③：_inbox_社長共有 に未処理ファイル ${INBOX_COUNT} 件${INBOX_AGE}】

${INBOX_SAMPLE}

**社長に「棚卸ししますか？」と聞かないでください。そのまま庶務マリエへ Agent 発注してください**
（subagent_type: general-affairs / 手順: agents/general_affairs/skills/inbox-intake.md）。

- 棚卸しは**退避・リネームのみ**で不可逆操作を含まないため、CLAUDE.md §4.2 の自律範囲です。
  確認を挟むほど滞留します（2026-08 に21件・12日間、2026-08-30 に2件が滞留したのはこの確認待ちが原因）。
- 社長が明示的に「後にして」と言った場合だけ止めます。
- カズヨが自分で inbox を開いて処理しないこと（抱え込み＝T-20260821-001）。
- **削除だけは別**。CLAUDE.md §4.1（不可逆な削除）なので、破棄候補はリスト化して社長承認を取ること。"
  fi
fi

# --- リマインダー④: 候補リスト常時稼働ジョブの生死と増分（2026-08-31 / T-20260831-002）---
#
# 背景: night-shift.plist は存在しないスクリプトを指したまま **14日間・814回** exit 127 で
#       死に続け、誰も気づきませんでした。stderr ログは誰も読みません。
#       だから「生きているか」は毎セッション必ず目に入るところへ出します。
#
# 生死の判定に **PID は使いません**。PID は再利用されるので、死んだプロセスを
# 「走行中」と誤表示します。判定材料は heartbeat.json の mtime だけです。

LB_DIR="$REPO/workspace/output/deliverables/T-20260831-002"
LB_V14="$REPO/workspace/output/deliverables/T-20260817-005/v14"
LIST_MSG=""

if [ -f "$LB_DIR/daily/latest.json" ] || [ -f "$LB_V14/ALERT.md" ]; then
  LB_ALERT=""
  if [ -f "$LB_V14/ALERT.md" ]; then
    LB_ALERT="

⚠ **ALERT が出ています**（ジョブは止まっています）。中身: \`$LB_V14/ALERT.md\`
$(sed -n '5,10p' "$LB_V14/ALERT.md" 2>/dev/null | sed 's/^/  /')
直したら ALERT.md を消してから \`bash .claude/scripts/list-builder.sh start\`。
課金・契約・削除が絡むなら自分で判断せず社長へ（CLAUDE.md §4.1）。"
  fi

  # 心拍の古さ（分）。ファイルが無ければ「不明」。
  LB_BEAT="不明"
  if [ -f "$LB_V14/heartbeat.json" ]; then
    LB_M="$(stat -f %m "$LB_V14/heartbeat.json" 2>/dev/null || echo 0)"
    [ "$LB_M" -gt 0 ] && LB_BEAT="$(( ( $(date +%s) - LB_M ) / 60 ))分前"
  fi

  LB_LINE="（まだロールアップがありません）"
  if [ -f "$LB_DIR/daily/latest.json" ] && command -v python3 >/dev/null 2>&1; then
    LB_LINE="$(python3 -c "
import json,sys
try:
    d=json.load(open('$LB_DIR/daily/latest.json',encoding='utf-8'))
except Exception as e:
    print('latest.json を読めません:', e); sys.exit(0)
t,dl=d['totals'],d['delta']
print(f\"状態={d['status']} / 前回比 候補+{dl['go']}・メーカー+{dl['makers']} / \"
      f\"累計 候補{t['go']}件・メーカー{t['makers']}社 / 更新 {d['generated_at']}\")
w=d.get('warning')
if w: print('  ⚠', w)
" 2>/dev/null)"
  fi

  LIST_MSG="

【SessionStart リマインダー④：候補リスト常時稼働ジョブ】
${LB_LINE}
最終心拍: ${LB_BEAT}（**STATUS.md の「走行中」ではなくこれを見る**。PIDは再利用されるため）${LB_ALERT}

- 詳しく見る: \`bash .claude/scripts/list-builder.sh status\`
- 止める: \`bash .claude/scripts/list-builder.sh stop\`
- 運用書: workspace/output/deliverables/T-20260831-002/README.md"
fi

# --- リマインダー⑤: Amazon セラーセントラル日次チェックの実行漏れ検知（2026-08-31 / T-20260826-004）---
#
# 背景: 日本店が 2026-08-01 に停止したことに約4週間気づきませんでした。再発防止として
#       毎日12:00のスケジュールタスク（~/.claude/scheduled-tasks/amazon-seller-central-daily-check/）
#       を組みましたが、**「タスクを登録した」ことと「実際に動いている」ことは別**です。
#       アプリが閉じていれば発火せず、Chrome が落ちていれば画面確認が失敗します。
#       そして止まっていても誰も気づきません（night-shift.plist は814回死に続けました）。
#
# だから判定材料はログの最新見出し（`## YYYY-MM-DD`）**だけ**にします。
# スケジューラの内部状態は見ません。見えたとしても「実行したが何も確認できなかった」を
# 成功と区別できないためです。**ログに行が増えたことだけが、動いた証拠です。**

MON_LOG="$REPO/workspace/monitoring/amazon-daily-check.md"
MON_MSG=""
MON_HOWTO="確認先: ~/.claude/scheduled-tasks/amazon-seller-central-daily-check/
- アプリのサイドバー「Scheduled」に amazon-seller-central-daily-check があるか、enabled か
- 無い／無効なら再登録が必要。スケジュールは毎日12:00（cron \`0 12 * * *\`）
- ログ本体: workspace/monitoring/amazon-daily-check.md
- 手順書: workspace/output/deliverables/T-20260826-004/03_日次モニタリングの仕組みと確認手順_20260831.md"

# 「2日以上前」の閾値＝昨日。昨日より古ければ警告する（今日・昨日は正常）。
MON_THRESHOLD="$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d 2>/dev/null || echo "$TODAY")"

if [ ! -f "$MON_LOG" ]; then
  MON_MSG="

【SessionStart リマインダー⑤：Amazon 日次チェックのログが存在しません】
\`workspace/monitoring/amazon-daily-check.md\` が見つかりません。**日次チェックが一度も実行されていないか、ログが消えています。**
スケジュールタスクが止まっている可能性があります。

${MON_HOWTO}"
else
  # 最新の日付見出しを1件だけ取る。ログは新しい順なので先頭が最新。
  MON_LAST="$(grep -m1 -oE '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' "$MON_LOG" 2>/dev/null | awk '{print $2}' || true)"

  if [ -z "$MON_LAST" ]; then
    MON_MSG="

【SessionStart リマインダー⑤：Amazon 日次チェックの記録が0件です】
\`workspace/monitoring/amazon-daily-check.md\` に \`## YYYY-MM-DD\` の見出しが1件もありません。**日次チェックが一度も記録されていません。**
スケジュールタスクが止まっている可能性があります。

${MON_HOWTO}"
  elif [[ "$MON_LAST" < "$MON_THRESHOLD" ]]; then
    MON_DAYS="?"
    if command -v python3 >/dev/null 2>&1; then
      MON_DAYS="$(python3 -c "
import datetime
try:
    d = datetime.date.fromisoformat('$MON_LAST')
    print((datetime.date.today() - d).days)
except Exception:
    print('?')
" 2>/dev/null || echo '?')"
    fi

    MON_MSG="

【SessionStart リマインダー⑤：Amazon 日次チェックが ${MON_DAYS} 日間実行されていません】
最後の記録は **${MON_LAST}**（今日=${TODAY}）。**日次チェックが ${MON_DAYS} 日間実行されていません。スケジュールタスクが止まっている可能性があります。**

Amazon の通知・申し立てステータス・サポート返信を見落とすと復旧が止まります（2026-08-01 の日本店停止に約4週間気づかなかった前例あり）。
まず今この turn で手動確認を回し、そのうえで下記を点検してください。

${MON_HOWTO}"
  fi
fi

# --- 掲出順（2026-08-31 / T-20260831-003 で変更）---
#
# 旧: ① → ②(next_check_at) → ③(inbox) → ④
# 新: ① → ③(inbox) → ④ → ②(next_check_at)
#
# 理由: ② は実測で 22 件・約 2,600 文字に膨らんでおり、その後ろに置かれた ③ の数行は
#       まず読まれません。**③ は「今 turn で発注すれば片付く 1 アクション」**なのに対し、
#       ② は社長への問いかけリストであり、②が長い日ほど ③ が埋没するという逆相関がある。
#       件数が増えるほど埋もれる配置は、放置を検知する仕組みとして自己矛盾しています。
#       行動を要する短いものを前に、一覧性の長いものを後ろに置きます。
# ⑤ は 2026-08-31 に追加。掲出は ① の直後（① → ⑤ → ③ → ④ → ②）。
# 番号は作成順、掲出順とは別です（③④② が既にそうなっています）。
# ⑤ は「止まっている時だけ」出るため、平常日は1行も増えません。だから最前列に置けます。
MESSAGE="${SYNC_MSG}${MON_MSG}${INBOX_MSG}${LIST_MSG}${REMINDER_MSG}"

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
