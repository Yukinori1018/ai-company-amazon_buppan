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

# --- リマインダー⑤: Amazon セラーセントラル日次チェックの実行漏れ検知 ---
#     （2026-08-31 / T-20260826-004 で新設、2026-09-06 に強化）
#
# 背景: 日本店が 2026-08-01 に停止したことに約4週間気づきませんでした。再発防止として
#       毎日12:00のスケジュールタスク（~/.claude/scheduled-tasks/amazon-seller-central-daily-check/）
#       を組みましたが、**「タスクを登録した」ことと「実際に動いている」ことは別**です。
#       実際 9/5（金）は Claude アプリが起動しておらず、丸1日飛びました。
#
# 2026-09-06 の強化で直した3点:
#   1. 閾値「2日以上前」→ **1日でも欠けたら警告**。ただし今日ぶんは12:00前なら鳴らさない
#      （巡回は12:00予定。朝のセッションで毎日誤検知するのは、警告そのものを無価値にする）
#   2. 最新日を「ファイル先頭の見出し」→ **全見出しの最大値**。並び順は人が手で書くので崩れる
#      （実際 9/5 の見出しが 9/6 の上にあった）
#   3. 「## 9/5」と見出しだけあって本文が「未実行」の日を、**実行済みと数えない**
#      （手で足した欠測行が検知を黙らせていた。旧実装はこれで今日も無言でした）
#
# 判定ロジックは .claude/scripts/amazon_check_log.py に1本化しています（番犬と共用）。
# ここに if 文を足さないでください。判定を2箇所に書くと必ずズレます。

MON_LOG="$REPO/workspace/monitoring/amazon-daily-check.md"
MON_LOGIC="$REPO/.claude/scripts/amazon_check_log.py"
MON_MSG=""
MON_HOWTO="復旧のしかた（どれか1つ）:
- **Claude でいますぐ回す: \`/amazon-check\`**（これが一番速い）
- スケジュールタスクの点検: アプリのサイドバー「Scheduled」に amazon-seller-central-daily-check があるか・enabled か
  （無い／無効なら再登録。スケジュールは毎日12:00 = cron \`0 12 * * *\`）
- 番犬の状態: \`bash .claude/scripts/amazon-check-watchdog.sh --status\`
- ログ本体: workspace/monitoring/amazon-daily-check.md
- 手順書: workspace/output/deliverables/T-20260826-004/09_日次チェックの実行漏れ対策_20260906.md"

if [ ! -f "$MON_LOG" ]; then
  MON_MSG="

【SessionStart リマインダー⑤：Amazon 日次チェックのログが存在しません】
\`workspace/monitoring/amazon-daily-check.md\` が見つかりません。**日次チェックが一度も実行されていないか、ログが消えています。**

${MON_HOWTO}"
elif command -v python3 >/dev/null 2>&1 && [ -f "$MON_LOGIC" ]; then
  MON_STATE="$(python3 "$MON_LOGIC" status --json 2>/dev/null || true)"

  if [ -n "$MON_STATE" ]; then
    # 警告文の組み立ては python 側に寄せる（bash で JSON を切り貼りしない）。
    # 何も問題が無ければ空文字を返す＝平常日は1行も出ない。
    MON_BODY="$(printf '%s' "$MON_STATE" | python3 -c "
import json,sys
try:
    s = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not s.get('log_exists', True):
    sys.exit(0)
missing = s.get('missing') or []
today_pending = (not s.get('today_done')) and (not s.get('before_deadline'))
if not missing and not today_pending:
    sys.exit(0)   # 平常。無風時は完全に静か
out = []
if missing:
    out.append(f\"**実行されなかった日が {len(missing)} 日あります: {', '.join(missing)}**\")
if today_pending:
    out.append(f\"**今日（{s['today']}）の巡回がまだです**（12:00 予定を過ぎています）。\")
last = s.get('last_ok')
out.append(f\"最後に巡回できたのは {last} です。\" if last else \"**一度も巡回できていません。**\")
print('\n'.join(out))
" 2>/dev/null || true)"

    if [ -n "$MON_BODY" ]; then
      # 番犬（launchd）の生存も一緒に出す。検知する側が死ぬと、静かに元に戻るため。
      MON_BEAT="$(cat "$REPO/workspace/monitoring/watchdog-last-run.txt" 2>/dev/null || echo '記録なし（番犬が一度も走っていない可能性）')"

      MON_MSG="

【SessionStart リマインダー⑤：Amazon 日次チェックに欠測があります】
${MON_BODY}

Amazon の通知・申し立てステータス・サポート返信を見落とすと復旧が止まります（2026-08-01 の日本店停止に約4週間気づかなかった前例あり）。
まず今この turn で巡回を回し、そのうえで下記を点検してください。

番犬の最終実行: ${MON_BEAT}

${MON_HOWTO}"
    fi
  fi
fi

# --- リマインダー⑥: 自律リサーチ資産「控え ⇔ 実体」の乖離検知（2026-09-02 / T-20260902-004）---
#
# 背景: T-20260902-003 でリポジトリ内 docs/reference/claude-research-skill/ に置いた5ファイルは
#       **控え**であり、正は ~/.claude/ にある実体です。実体を編集しても控えは追随しません。
#       T-20260902-002 では退避アーカイブが**作成翌日に既に657バイト古く**なっていました。
#       README に更新義務を書いてありますが、文書だけの約束は風化します。
#       そして**古い控えは、控えが無いより危険**です（「バックアップがある」と誤認させるため）。
#
# ⚠️ ここでやることは **検知と警告表示だけ** です（2026-09-02 社長の明示条件）。
#    自動同期・自動コピー・自動 commit は**実装しません**。どちらが正かを機械は判断できないからです
#    （実体が新しいのか、控え側の巻き戻しが意図的なのかは人間にしか分かりません）。
#    「便利だから」と cp / rsync / git add を走らせる分岐をここに足さないでください。編集を失います。
#    出力する cp は「人間が読んで判断してから自分で打つ」ための**文字列**です。

# 対応表はここ1箇所だけ。控えと実体で相対パスが共通なので、資産が増えたら行を1つ足すだけで済みます。
RESEARCH_MIRROR_PATHS=(
  "skills/research/SKILL.md"
  "skills/research/references/external-sources.md"
  "agents/research-collector.md"
  "agents/research-verifier.md"
  "agents/research-integrator.md"
)
MIRROR_COPY_ROOT="$REPO/docs/reference/claude-research-skill"  # 控え（リポジトリ内・Git 追跡）
MIRROR_COPY_REL="docs/reference/claude-research-skill"         # 表示用（リポジトリルート相対）
MIRROR_LIVE_ROOT="$HOME/.claude"                               # 実体＝正（リポジトリ外・Git 管理外）

# BSD(macOS) / GNU 両対応。取れなくても絶対に落とさない（フックがセッション開始を妨げないこと）。
mirror_mtime_human() {
  stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$1" 2>/dev/null && return 0
  stat -c '%y' "$1" 2>/dev/null | cut -c1-16 && return 0
  echo '不明'
}
mirror_mtime_epoch() {
  stat -f '%m' "$1" 2>/dev/null && return 0
  stat -c '%Y' "$1" 2>/dev/null && return 0
  echo 0
}
mirror_size() {
  stat -f '%z' "$1" 2>/dev/null && return 0
  stat -c '%s' "$1" 2>/dev/null && return 0
  echo '?'
}
# 秒差 → 「2日3時間5分」。0分未満は「1分未満」。
mirror_delta_human() {
  local s="${1:-0}" out=""
  case "$s" in (*[!0-9]*|'') echo '差不明'; return 0 ;; esac
  [ "$s" -ge 86400 ] && out="${out}$(( s / 86400 ))日"
  [ "$(( (s % 86400) / 3600 ))" -gt 0 ] && out="${out}$(( (s % 86400) / 3600 ))時間"
  [ "$(( (s % 3600) / 60 ))" -gt 0 ] && out="${out}$(( (s % 3600) / 60 ))分"
  [ -z "$out" ] && out="1分未満"
  echo "$out"
}

MIRROR_MSG=""
MIRROR_BODY=""
MIRROR_COUNT=0

# ~/.claude が無い環境（クラウド実行時など）は素通り。控えのディレクトリごと無い場合も同様。
if [ -d "$MIRROR_LIVE_ROOT" ] && [ -d "$MIRROR_COPY_ROOT" ]; then
  for rel in "${RESEARCH_MIRROR_PATHS[@]}"; do
    live="$MIRROR_LIVE_ROOT/$rel"
    copy="$MIRROR_COPY_ROOT/$rel"

    # 両方無い＝資産ごと廃止された。削除された資産まで警告し続けない。
    if [ ! -e "$live" ] && [ ! -e "$copy" ]; then
      continue
    fi

    # 表示用の cp コマンド（**文字列としてだけ**出す。実行はしない）。
    # $HOME は展開せずに出す: このリポジトリは PUBLIC なのでユーザー名を出力に載せない。
    CP_LIVE_TO_COPY="cp \"\$HOME/.claude/${rel}\" \"${MIRROR_COPY_REL}/${rel}\""
    CP_COPY_TO_LIVE="cp \"${MIRROR_COPY_REL}/${rel}\" \"\$HOME/.claude/${rel}\""

    if [ -e "$live" ] && [ -e "$copy" ]; then
      ck_live="$(cksum "$live" 2>/dev/null | awk '{print $1}' || true)"
      ck_copy="$(cksum "$copy" 2>/dev/null | awk '{print $1}' || true)"

      # 一致＝何も出さない（無風時は完全に静か）
      if [ -n "$ck_live" ] && [ "$ck_live" = "$ck_copy" ]; then
        continue
      fi

      live_t="$(mirror_mtime_human "$live")"; copy_t="$(mirror_mtime_human "$copy")"
      live_z="$(mirror_size "$live")";        copy_z="$(mirror_size "$copy")"
      live_e="$(mirror_mtime_epoch "$live")"; copy_e="$(mirror_mtime_epoch "$copy")"

      if [ "$live_e" -gt "$copy_e" ]; then
        newer="→ **実体（\$HOME/.claude/）のほうが $(mirror_delta_human $(( live_e - copy_e ))) 新しい**"
      elif [ "$copy_e" -gt "$live_e" ]; then
        newer="→ **控え（${MIRROR_COPY_REL}/）のほうが $(mirror_delta_human $(( copy_e - live_e ))) 新しい**"
      else
        newer="→ **更新時刻は同じですが中身が違います**（cksum 不一致）"
      fi

      MIRROR_COUNT=$(( MIRROR_COUNT + 1 ))
      MIRROR_BODY="${MIRROR_BODY}
■ ${rel} ［不一致］
  実体: ${live_t} / ${live_z} bytes （cksum ${ck_live}）
  控え: ${copy_t} / ${copy_z} bytes （cksum ${ck_copy}）
  ${newer}（※「新しい＝正しい」ではありません。控え側の巻き戻しが意図的な場合もあります）
  判断したうえで、**どちらか一方だけ**をリポジトリルートで実行:
    実体 → 控え: ${CP_LIVE_TO_COPY}
    控え → 実体: ${CP_COPY_TO_LIVE}
"
    elif [ -e "$live" ]; then
      MIRROR_COUNT=$(( MIRROR_COUNT + 1 ))
      MIRROR_BODY="${MIRROR_BODY}
■ ${rel} ［控えが欠損］
  実体: $(mirror_mtime_human "$live") / $(mirror_size "$live") bytes
  控え: 存在しません（${MIRROR_COPY_REL}/${rel}）
  → 控えが失われています。実体を控えへ戻すか、資産ごと廃止したなら対応表と README から外してください。
    実体 → 控え: ${CP_LIVE_TO_COPY}
"
    else
      MIRROR_COUNT=$(( MIRROR_COUNT + 1 ))
      MIRROR_BODY="${MIRROR_BODY}
■ ${rel} ［実体が欠損］
  実体: 存在しません（\$HOME/.claude/${rel}）
  控え: $(mirror_mtime_human "$copy") / $(mirror_size "$copy") bytes
  → 実体が消えています。控えから復元するか、意図的な削除なら控えと README を整理してください。
    控え → 実体: ${CP_COPY_TO_LIVE}
"
    fi
  done

  if [ "$MIRROR_COUNT" -gt 0 ]; then
    MIRROR_MSG="

【SessionStart リマインダー⑥：リサーチ資産の控えと実体が乖離しています（${MIRROR_COUNT}/${#RESEARCH_MIRROR_PATHS[@]} 件）】
正は \$HOME/.claude/ の実体、\`${MIRROR_COPY_REL}/\` は控えです（T-20260902-003）。
${MIRROR_BODY}
**このフックは検知だけを行います。自動同期・自動コピー・自動 commit は一切しません**（2026-09-02 社長指示）。
どちらが正かは機械には判断できません。必ず両者の中身を見比べ、**人間が決めてから**上のコマンドを打ってください。
- 控えの README: ${MIRROR_COPY_REL}/README.md
- 控えを更新した場合は commit まで行うこと（控えは Git 追跡対象）。"
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
# ⑤ は 2026-08-31 に追加。⑥ は 2026-09-02 に追加。掲出は ① → ⑤ → ⑥ → ③ → ④ → ②。
# 番号は作成順、掲出順とは別です（③④② が既にそうなっています）。
# ⑤⑥ はいずれも「異常な時だけ」出るため、平常日は1行も増えません。だから最前列に置けます。
MESSAGE="${SYNC_MSG}${MON_MSG}${MIRROR_MSG}${INBOX_MSG}${LIST_MSG}${REMINDER_MSG}"

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
