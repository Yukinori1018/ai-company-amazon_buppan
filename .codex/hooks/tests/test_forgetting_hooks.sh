#!/bin/bash
# T-20260912-001 のフック2本のテスト。一時ディレクトリで動かし、実リポは触らない。
#   bash .claude/hooks/tests/test_forgetting_hooks.sh
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0
ok()  { echo "ok   - $1"; }
ng()  { echo "FAIL - $1"; FAIL=1; }
has() { case "$2" in *"$3"*) ok "$1";; *) ng "$1（出力: ${2:0:200}）";; esac; }
empty() { [ -z "$2" ] && ok "$1" || ng "$1（出力: ${2:0:200}）"; }

# ---- done-open-items-check.sh ----
mkdir -p "$T/workspace/tickets/done"
cat > "$T/workspace/tickets/done/T-20990101-001_x.md" <<'EOF'
## ログ
- 2026-08-26 メキシコの件は回答なくケースが閉じた＝宙に浮いている
- 日本店側の画面で別途要確認
EOF
printf '## ログ\n- 全部片付いた\n' > "$T/workspace/tickets/done/T-20990101-002_y.md"
run() { CLAUDE_PROJECT_DIR="$T" bash "$HOOKS/done-open-items-check.sh" <<<"$1"; }

out="$(run '{"tool_name":"Bash","tool_input":{"command":"git mv workspace/tickets/doing/T-20990101-001_x.md workspace/tickets/done/"}}')"
has "mv で done へ → 宙に浮 を拾う" "$out" "宙に浮いている"
has "要確認も拾う" "$out" "要確認"
has "JSON で additionalContext を返す" "$out" '"additionalContext"'

out="$(run '{"tool_name":"Bash","tool_input":{"command":"git mv workspace/tickets/doing/T-20990101-002_y.md workspace/tickets/done/"}}')"
empty "未決語が無ければ無音" "$out"

out="$(run '{"tool_name":"Bash","tool_input":{"command":"cat workspace/tickets/done/T-20990101-001_x.md"}}')"
empty "参照だけ（cat）は無音" "$out"

out="$(run '{"tool_name":"Edit","tool_input":{"file_path":"'"$T"'/workspace/tickets/done/T-20990101-001_x.md"}}')"
empty "Edit は対象外" "$out"

out="$(run '{"tool_name":"Write","tool_input":{"file_path":"'"$T"'/workspace/tickets/done/T-20990101-001_x.md"}}')"
has "Write で done に作成 → 拾う" "$out" "宙に浮"

out="$(run 'not json')"
empty "壊れた入力でも落ちない" "$out"

# ---- session-start.sh ⑧ ----
mkdir -p "$T/repo/workspace/tickets/doing" "$T/repo/workspace/tickets/waiting"
ss() { LEDGER_PATH="$1" CLAUDE_PROJECT_DIR="$T/repo" bash "$HOOKS/session-start.sh" </dev/null 2>/dev/null; }

printf '## 更新ログ\n- 2020-01-01 古い\n' > "$T/old.md"
has "7日より古い台帳 → 警告" "$(ss "$T/old.md")" "リマインダー⑧"

printf '## 国別（最終確認 2020-01-01）\n## 更新ログ\n- %s 今日\n' "$(date +%Y-%m-%d)" > "$T/new.md"
out="$(ss "$T/new.md")"
case "$out" in *"リマインダー⑧"*) ng "新しい台帳は無音";; *) ok "新しい台帳は無音";; esac

out="$(ss "$T/none.md")"
case "$out" in *"リマインダー⑧"*) ng "台帳が無ければ無音";; *) ok "台帳が無ければ無音";; esac

exit $FAIL
