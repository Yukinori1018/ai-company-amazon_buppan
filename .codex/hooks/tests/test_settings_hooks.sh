#!/bin/bash
# settings.json に登録したフック9本を「Claude Code が呼ぶのと同じ形」で叩く結合テスト（T-20261027-001）。
#   bash .claude/hooks/tests/test_settings_hooks.sh
#
# なぜ要るか:
#   8/21〜10/27 の2か月、フック9本は settings.json の `$CLAUDE_PROJECT_DIR` が引用符で
#   囲まれておらず、パスの空白（"Claude Code"）で切れて全件 exit 127 だった。
#   個々のフックの単体テストは全部通っていた（テストはフックを直接 bash で呼ぶので空白を踏まない）。
#   **登録のしかたを試すテストが無かった**ので、ここで settings.json の command 文字列そのものを
#   /bin/sh -c で実行する。
#
# 実リポは読むだけ（Stop フックの判定は一時ディレクトリの複製で試す）。
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HOOKS/../.." && pwd)"
SETTINGS="$REPO/.claude/settings.json"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
N=0; F=0
ok() { N=$((N+1)); echo "ok   - $1"; }
ng() { N=$((N+1)); F=$((F+1)); echo "FAIL - $1"; }

# settings.json から「イベント名 ファイル名」→ command 文字列を引く
cmd_of() { python3 - "$SETTINGS" "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for g in d["hooks"][sys.argv[2]]:
    for h in g["hooks"]:
        if h["command"].endswith(sys.argv[3]):
            print(h["command"]); sys.exit(0)
sys.exit(1)
PY
}
# $1=event $2=hook file $3=payload $4=CLAUDE_PROJECT_DIR(省略時=実リポ) → $OUT $ERR $RC
run() {
  local c; c="$(cmd_of "$1" "$2")" || { RC=999; OUT=""; ERR="settings.json に $2 が無い"; return; }
  OUT="$(printf '%s' "$3" | CLAUDE_PROJECT_DIR="${4:-$REPO}" /bin/sh -c "$c" 2>"$T/err")"; RC=$?
  ERR="$(cat "$T/err")"
}
expect_rc() { [ "$RC" = "$2" ] && ok "$1" || ng "$1（exit=$RC 期待=$2 / ${ERR:0:200}）"; }
has()   { case "$OUT$ERR" in *"$2"*) ok "$1";; *) ng "$1（「$2」が出力に無い / ${OUT:0:200}${ERR:0:200}）";; esac; }
quiet() { [ "$RC" = 0 ] && [ -z "$OUT" ] && ok "$1" || ng "$1（exit=$RC・無音のはず: ${OUT:0:200}${ERR:0:200}）"; }
w() { python3 -c 'import json,sys;print(json.dumps({"tool_name":"Write","tool_input":{"file_path":sys.argv[1],"content":sys.argv[2]}}))' "$1" "$2"; }

# 止めるべき文例（資産台帳ガードの 9/21 の事故文）。このファイル自体は .claude/hooks/ 配下なのでガードの対象外
NG_ASSET="当社は独自ドメイン""なし・HP""なし・会社概要""なし"

case "$REPO" in *" "*) ok "前提: リポのパスに空白がある（$REPO）";; *) echo "note - リポのパスに空白が無い環境。空白の再現は下の複製で行う";; esac

echo "== 登録の形（引用符） =="
python3 - "$SETTINGS" <<'PY' && ok "全 command が \"\$CLAUDE_PROJECT_DIR\" を引用符で囲んでいる" || ng "引用符で囲まれていない command がある"
import json, sys
d = json.load(open(sys.argv[1]))
bad = [h["command"] for gs in d["hooks"].values() for g in gs for h in g["hooks"]
       if "$CLAUDE_PROJECT_DIR" in h["command"] and '"$CLAUDE_PROJECT_DIR"' not in h["command"]]
print("\n".join(bad)); sys.exit(1 if bad else 0)
PY
OUT="$(printf '{}' | CLAUDE_PROJECT_DIR="$REPO" /bin/sh -c '$CLAUDE_PROJECT_DIR/.claude/hooks/delegation-check.sh' 2>&1)"; RC=$?
case "$REPO" in *" "*) [ "$RC" = 127 ] && ok "対照: 引用符なしの旧い書き方は exit 127 になる（壊れ方の再現）" || ng "対照: 旧い書き方が127にならない（rc=$RC）";; esac

echo "== SessionStart =="
run SessionStart session-start.sh '{"session_id":"t-ss","hook_event_name":"SessionStart","source":"startup"}'
expect_rc "session-start は exit 0（ブロックしない）" 0
printf '%s' "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["hookSpecificOutput"]["additionalContext"]' 2>/dev/null \
  && ok "session-start は additionalContext の JSON を返す" || ng "session-start の出力が JSON でない（${OUT:0:200}）"

echo "== UserPromptSubmit =="
run UserPromptSubmit delegation-check.sh '{"session_id":"t-del-'$$'","prompt":"このスクリプトを直して自動化してください"}'
expect_rc "委譲チェックは exit 0" 0; has "委譲チェックが IT 担当を挙げる" "it-engineer"
run UserPromptSubmit delegation-check.sh '{"session_id":"t-del2-'$$'","prompt":"はい"}'
expect_rc "相槌でも exit 0" 0; quiet "相槌は無音"
run UserPromptSubmit inbox-intake-check.sh '{"session_id":"t-inbox-'$$'","prompt":"おはよう"}'
expect_rc "inbox 検知は exit 0（ブロックしない）" 0

echo "== PostToolUse =="
run PostToolUse ticket-notion-sync-reminder.sh '{"tool_name":"Edit","tool_input":{"file_path":"'"$REPO"'/workspace/tickets/doing/T-20261027-001_claude-md-rebuild.md"}}'
expect_rc "Notion 同期リマインドは exit 0" 0; has "チケット編集で同期を促す" "T-20261027-001"
run PostToolUse ticket-notion-sync-reminder.sh '{"tool_name":"Edit","tool_input":{"file_path":"'"$REPO"'/README.md"}}'
quiet "チケット以外の編集は無音"
run PostToolUse done-open-items-check.sh '{"tool_name":"Bash","tool_input":{"command":"ls workspace/tickets/done"}}'
expect_rc "done 未決チェックは exit 0" 0; quiet "参照だけは無音"

echo "== PreToolUse（書く前に止めるガード3本） =="
D="$REPO/workspace/output/deliverables/T-99999999-001"
run PreToolUse asset-claim-guard.py "$(w "$D/01_x.md" "$NG_ASSET")"
expect_rc "資産台帳ガード: 9/21 の事故文は止める" 2
run PreToolUse asset-claim-guard.py "$(w "$D/01_x.md" "Amazon の JAN が NETSEA に1件も存在せず。キーゾン表示なし。製品サイトに会社概要が無い")"
expect_rc "資産台帳ガード: 相手先・表示の話は通す" 0
run PreToolUse asset-claim-guard.py "$(w "$REPO/.claude/hooks/tests/x.sh" "$NG_ASSET")"
expect_rc "資産台帳ガード: フックのテストは対象外" 0
run PreToolUse source-terms-guard.py "$(w "$D/01_x.md" "| 卸値 | 1,280円 |")"
expect_rc "出所ガード: 卸値の実額は止める" 2
run PreToolUse source-terms-guard.py "$(w "$D/01_x.md" "卸値÷売価 70% が目安。最低ロット｜1回に注文できる最小の数。卸価格が見える一覧")"
expect_rc "出所ガード: 率・説明文は通す" 0
run PreToolUse source-terms-guard.py "$(w "$REPO/workspace/output/agent_output/T-1/x.md" "| 卸値 | 1,280円 |")"
expect_rc "出所ガード: agent_output（非公開）は通す" 0
run PreToolUse order-gate-guard.py "$(w "$D/02_発注案.md" "本文だけ")"
expect_rc "発注ゲート: マーカー無しの発注案は止める" 2
run PreToolUse order-gate-guard.py "$(w "$REPO/workspace/output/deliverables/T-20261026-002/01_発注減少の原因分析.md" "秘書の発注が減った原因")"
expect_rc "発注ゲート: 委譲の「発注」の報告書は通す" 0
run PreToolUse order-gate-guard.py "$(w "$REPO/README.md" "ふつうの文書")"
expect_rc "発注ゲート: 関係ない文書は通す" 0

echo "== Stop（社長タスクまとめ）— 空白入りパスの複製で判定を試す =="
R="$T/with space/repo"; mkdir -p "$R/workspace/tickets/waiting" "$R/workspace/tickets/doing" "$R/.claude/hooks"
cp "$HOOKS/owner-tasks-sync-check.sh" "$R/.claude/hooks/"
printf '# 社長タスク\n- T-20990101-001 承認\n' >"$R/workspace/owner-tasks.md"
touch -t 202601010000 "$R/workspace/owner-tasks.md"
printf -- '---\nticket_id: T-20990101-001\n---\n' >"$R/workspace/tickets/waiting/T-20990101-001_a.md"
touch -t 202512310000 "$R/workspace/tickets/waiting/T-20990101-001_a.md"
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":false}' "$R"
expect_rc "平常（waiting が古く、全部載っている）は exit 0" 0; quiet "平常は無音"
printf 'log\n' >"$R/workspace/tickets/doing/T-20990101-009_b.md"
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":false}' "$R"
quiet "doing/ のログ追記だけでは止めない（毎ターン止めない）"
printf 'log\n' >>"$R/workspace/tickets/waiting/T-20990101-001_a.md"
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":false}' "$R"
has "waiting/ のチケットが更新されたら止める" '"decision"'
case "$OUT" in *36db0a40*) ng "廃止済みの Notion カードへの同期を指示している";; *) ok "廃止済みの Notion カードを指示しない";; esac
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":true}' "$R"
quiet "stop_hook_active=true なら再ブロックしない（ループしない）"
touch "$R/workspace/owner-tasks.md"
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":false}' "$R"
quiet "owner-tasks.md を更新すれば解除"
printf -- '---\nticket_id: T-20990101-002\n---\n' >"$R/workspace/tickets/waiting/T-20990101-002_c.md"
touch -t 202512310000 "$R/workspace/tickets/waiting/T-20990101-002_c.md"
run Stop owner-tasks-sync-check.sh '{"stop_hook_active":false}' "$R"
has "waiting へ移した（mv で時刻が古い）チケットも、まとめに無ければ止める" "T-20990101-002"

echo "== PostToolUse（作業中の委譲チェック・2026-10-27 追加） =="
export TMPDIR="$T/tmpdir"; mkdir -p "$TMPDIR"
# $1=session $2=prompt_id $3=tool $4=tool_input(JSON) $5=agent_id(任意)
wp() { python3 - "$@" <<'PY'
import json, sys
s, p, tool, ti = sys.argv[1:5]
d = {"session_id": s, "prompt_id": p, "hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": json.loads(ti)}
if len(sys.argv) > 5 and sys.argv[5]:
    d["agent_id"] = sys.argv[5]; d["agent_type"] = "it-engineer"
print(json.dumps(d, ensure_ascii=False))
PY
}
BASH_W='{"command":"python3 scripts/sourcing_gate/consistency.py check x.csv"}'
fire_at() { # $1=session $2=回数 $3=tool $4=input [$5=agent_id] → 何手目で初めて出たか（出なければ0）
  local i at=0
  for i in $(seq 1 "$2"); do
    run PostToolUse work-without-delegation-check.py "$(wp "$1" p1 "$3" "$4" "${5:-}")"
    [ "$RC" = 0 ] || { ng "作業中チェックが exit $RC"; return; }
    [ "$at" = 0 ] && [ -n "$OUT" ] && { at=$i; printf '%s' "$OUT" >"$T/fired_$1"; }
  done
  echo "$at"
}
at="$(fire_at s-main 8 Bash "$BASH_W")"
[ "$at" = 8 ] && ok "メインが振らずに作業8手 → 8手目で差し込む" || ng "8手目で差し込むはずが ${at}手目"
grep -q "it-engineer" "$T/fired_s-main" && grep -q "additionalContext" "$T/fired_s-main" \
  && ok "差し込みは additionalContext で、担当候補（IT）が入る" || ng "差し込みの中身が違う: $(head -c 300 "$T/fired_s-main")"
grep -q '"decision"' "$T/fired_s-main" && ng "block している" || ok "止めない（decision を返さない）"
run PostToolUse work-without-delegation-check.py "$(wp s-main p1 Bash "$BASH_W")"
case "$OUT" in "") ok "9手目は黙る（毎手は鳴らさない）";; *) ng "9手目でも鳴った";; esac
run PostToolUse work-without-delegation-check.py "$(wp s-main p1 Bash "$BASH_W")"
printf '%s' "$(cat "$TMPDIR"/claude-work-nodelegate-s-main.json)" | grep -q '"next": 16' && ok "次の差し込みは16手目" || ng "次の閾値が16でない"
at="$(fire_at s-sub 12 Bash "$BASH_W" a123)"
[ "$at" = 0 ] && ok "サブエージェント（agent_id あり）は12手でも発火しない" || ng "サブエージェントで ${at}手目に発火"
at="$(fire_at s-ticket 12 Edit '{"file_path":"/r/workspace/tickets/doing/T-1.md","new_string":"x"}')"
[ "$at" = 0 ] && ok "チケットの編集は数えない" || ng "チケット編集で発火"
at="$(fire_at s-own 12 Write '{"file_path":"/r/workspace/owner-tasks.md","content":"x"}')"
[ "$at" = 0 ] && ok "owner-tasks の更新は数えない" || ng "owner-tasks で発火"
at="$(fire_at s-ro 12 Bash '{"command":"git log --oneline -3"}')"
[ "$at" = 0 ] && ok "読むだけの Bash（1手の事実確認）は数えない" || ng "読むだけの Bash で発火"
for i in 1 2 3 4 5 6 7; do run PostToolUse work-without-delegation-check.py "$(wp s-ag p1 Bash "$BASH_W")"; done
run PostToolUse work-without-delegation-check.py "$(wp s-ag p1 Agent '{"subagent_type":"accounting","prompt":"x"}')"
at="$(fire_at s-ag 7 Bash "$BASH_W")"
[ "$at" = 0 ] && ok "7手のあと Agent で振れば数え直し（続く7手では鳴らない）" || ng "Agent 後も数え続けた（${at}手目で発火）"
for i in 1 2 3 4 5 6 7; do run PostToolUse work-without-delegation-check.py "$(wp s-turn p1 Bash "$BASH_W")"; done
run PostToolUse work-without-delegation-check.py "$(wp s-turn p2 Bash "$BASH_W")"
quiet "新しいターン（prompt_id が変わる）で数え直し"
at="$(fire_at s-br 8 mcp__claude-in-chrome__computer '{"action":"left_click"}')"
[ "$at" = 8 ] && ok "ブラウザ操作も数える（8手目）" || ng "ブラウザ操作で ${at}手目"
run PostToolUse work-without-delegation-check.py 'not json'
expect_rc "壊れた入力でも exit 0" 0

echo
echo "$N 件中 失敗 $F 件"
[ "$F" = 0 ]
