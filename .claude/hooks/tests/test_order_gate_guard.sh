#!/bin/bash
# order-gate-guard.py（PreToolUse）・scripts/sourcing_gate/（gate.py / check_record.py）・
# .githooks/pre-commit の発注ゲート部分の回帰テスト（T-20261004-001）。
#   bash .claude/hooks/tests/test_order_gate_guard.sh
#
# 一時ディレクトリで動かし、実リポの記録（agent_output/_sourcing_checks）は触らない。
# ASIN・金額はすべて架空。
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HOOKS/../.." && pwd)"
GUARD="$HOOKS/order-gate-guard.py"
CR="$REPO/scripts/sourcing_gate/check_record.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0; N=0; F=0
ok() { N=$((N+1)); echo "ok   - $1"; }
ng() { N=$((N+1)); F=$((F+1)); echo "FAIL - $1"; FAIL=1; }

mkdir -p "$T/scripts/sourcing_gate" "$T/checks"
cp "$REPO/scripts/sourcing_gate/checklist_spec.json" "$T/scripts/sourcing_gate/"
export CLAUDE_PROJECT_DIR="$T" SOURCING_CHECKS_DIR="$T/checks"
TODAY="$(date +%Y-%m-%d)"
OLD="$(python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=5)).isoformat())')"
IDS="$(python3 -c 'import json,sys;print(" ".join(i["id"] for i in json.load(open(sys.argv[1]))["items"]))' "$T/scripts/sourcing_gate/checklist_spec.json")"

# ASIN の全項目を PASS で記録する
all_pass() { # $1=ASIN [$2=日付]
  local id
  for id in $IDS; do
    python3 "$CR" set "$1" "$id" --value "確認済み" --result PASS --source "https://example.test/$1" \
      --by test --date "${2:-$TODAY}" >/dev/null || ng "set $1 $id"
  done
}

payload_write() { python3 - "$1" "$2" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Write", "tool_input": {"file_path": sys.argv[1], "content": sys.argv[2]}}))
PY
}
payload_edit() { python3 - "$1" "$2" "$3" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Edit", "tool_input": {"file_path": sys.argv[1], "old_string": sys.argv[2], "new_string": sys.argv[3]}}))
PY
}
payload_multi() { python3 - "$1" "$2" "$3" "$4" "$5" <<'PY'
import json, sys
print(json.dumps({"tool_name": "MultiEdit", "tool_input": {"file_path": sys.argv[1], "edits": [
  {"old_string": sys.argv[2], "new_string": sys.argv[3]},
  {"old_string": sys.argv[4], "new_string": sys.argv[5]}]}}))
PY
}
rc_of() { python3 "$GUARD" <"$T/p.json" 2>"$T/err"; echo $?; }
expect() { # $1=名前 $2=期待rc $3=本文に含まれるべき語（任意）
  local rc; rc="$(rc_of)"
  if [ "$rc" != "$2" ]; then ng "$1（exit=$rc 期待=$2 / $(head -c 300 "$T/err")）"; return; fi
  if [ -n "${3:-}" ] && ! grep -q -- "$3" "$T/err"; then ng "$1（メッセージに「$3」が無い）"; return; fi
  ok "$1"
}

D="$T/workspace/output/deliverables/T-99999999-001"
mkdir -p "$D"
P="$D/01_発注案.md"

echo "== 対象外は素通り =="
payload_write "$D/02_調査メモ.md" "B008FIPMP2 のゲートは要確認です。" >"$T/p.json"; expect "発注案でない文書" 0
payload_write "$T/workspace/output/deliverables/T-99999999-001/order_plan.py" "x='<!-- order-asins: B0TEST0001 -->'" >"$T/p.json"; expect "コード(.py)はマーカーがあっても対象外" 0
payload_write "$T/.claude/hooks/x.md" "<!-- order-asins: B0TEST0001 -->" >"$T/p.json"; expect ".claude 配下は対象外" 0
payload_write "$T/scripts/sourcing_gate/README.md" "例: <!-- order-asins: B0XXXXXXXX -->" >"$T/p.json"; expect "ゲートの README は対象外" 0
payload_write "$T/workspace/tickets/doing/T-99999999-001_発注.md" "発注の段取りを決める" >"$T/p.json"; expect "チケット（パスに発注・マーカーなし）は対象外" 0
printf '{"tool_name":"Read","tool_input":{"file_path":"%s"}}' "$P" >"$T/p.json"; expect "Read は対象外" 0
echo 'not json' >"$T/p.json"; expect "壊れた入力でも落ちない" 0

echo "== マーカー =="
payload_write "$P" "# 発注案
| ASIN | 数量 |
|---|---|
| B0TEST0001 | 8 |" >"$T/p.json"; expect "マーカー無しの発注案はブロック" 2 "order-asins"
payload_write "$D/03_まとめ.md" "<!-- order-asins: B0TEST0009 -->
本文" >"$T/p.json"; expect "パスに発注が無くてもマーカーがあれば対象（未確認でブロック）" 2 "B0TEST0009"
payload_write "$P" "<!-- order-asins:  -->" >"$T/p.json"; expect "マーカーが空ならブロック" 2 "1つもありません"
payload_write "/x/.claude/worktrees/wt1/workspace/output/deliverables/T-1/01_発注案.md" "本文だけ" >"$T/p.json"
expect "worktree の発注案も対象（.claude/ を含む絶対パスでも素通りしない）" 2 "order-asins"

echo "== 未確認・FAIL・UNKNOWN・期限切れ =="
payload_write "$P" "<!-- order-asins: B0TEST0001 -->" >"$T/p.json"; expect "記録ゼロ＝ゲート未確認でブロック" 2 "gate_type"
grep -q "欠落" "$T/err" && ok "理由に「欠落」" || ng "理由に「欠落」"
grep -q "check_record.py set B0TEST0001" "$T/err" && ok "打ち方を示す" || ng "打ち方を示す"

all_pass B0TEST0002
python3 "$CR" set B0TEST0002 buybox_seller --value "Amazon.co.jp" --result FAIL --source https://example.test --by test >/dev/null
payload_write "$P" "<!-- order-asins: B0TEST0002 -->" >"$T/p.json"; expect "カート販売元 FAIL でブロック" 2 "FAIL"

all_pass B0TEST0003
python3 "$CR" set B0TEST0003 gate_type --value "未取得" --result UNKNOWN --source https://example.test --by test >/dev/null
payload_write "$P" "<!-- order-asins: B0TEST0003 -->" >"$T/p.json"; expect "ゲート UNKNOWN でブロック" 2 "UNKNOWN"

all_pass B0TEST0004 "$OLD"
payload_write "$P" "<!-- order-asins: B0TEST0004 -->" >"$T/p.json"; expect "5日前の確認＝期限切れでブロック" 2 "期限切れ"

echo "== 全PASS =="
all_pass B0TEST0005
payload_write "$P" "<!-- order-asins: B0TEST0005 -->
# 発注案
| ASIN | 商品 | ゲート |
|---|---|---|
| B0TEST0005 | 架空の商品 | 申請可 |

蛍光灯の件は別途要確認（地の文の注意書きは止めない）。" >"$T/p.json"; expect "全項目PASS・鮮度内なら通す" 0
payload_write "$P" "<!-- order-asins: B0TEST0005, B0TEST0001 -->" >"$T/p.json"; expect "2件のうち1件でも不可ならブロック" 2 "B0TEST0001"
payload_write "$P" "<!-- order-asins: B0TEST0005 -->
| ASIN | ゲート |
|---|---|
| B0TEST0005 | 要確認 |" >"$T/p.json"; expect "記録はPASSでも発注表に「要確認」が残ればブロック" 2 "要確認"
payload_write "$D/04_発注案.html" "<!-- order-asins: B0TEST0005 -->
<table><tr><td>B0TEST0005</td>
<td>UNKNOWN</td></tr></table>" >"$T/p.json"; expect "HTML の表の行（複数行）に UNKNOWN が残ればブロック" 2 "UNKNOWN"
payload_write "$P" "<!-- order-asins: B0TEST0005 -->
| ASIN | ゲート |
|---|---|
| B0TEST0005 | 申請可 |
| B0TEST0001 | 要確認（見送り） |" >"$T/p.json"; expect "発注しない行の要確認は止めない" 0

echo "== Edit／MultiEdit は書き換え後の全文で判定 =="
printf '%s\n' "<!-- order-asins: B0TEST0005 -->" "# 発注案" "本文A" >"$P"
payload_edit "$P" "本文A" "本文B" >"$T/p.json"; expect "Edit で地の文だけ直す → 通す" 0
payload_edit "$P" "B0TEST0005 -->" "B0TEST0005, B0TEST0001 -->" >"$T/p.json"; expect "Edit で未確認 ASIN を足す → ブロック" 2 "B0TEST0001"
payload_edit "$P" "<!-- order-asins: B0TEST0005 -->" "" >"$T/p.json"; expect "Edit でマーカーを消す → ブロック" 2 "order-asins"
payload_multi "$P" "本文A" "| B0TEST0005 | 未確認 |" "# 発注案" "# 発注案2" >"$T/p.json"; expect "MultiEdit で発注表に未確認を入れる → ブロック" 2 "未確認"
printf '%s\n' "# 旧い発注案（マーカー無し）" "本文A" >"$D/05_発注案.md"
payload_edit "$D/05_発注案.md" "本文A" "本文B" >"$T/p.json"; expect "マーカー無しの既存発注案は、部分 Edit でもブロック" 2 "order-asins"

echo "== check_record.py =="
python3 "$CR" set B0TEST0006 gate_type --value "要確認" --result PASS --source x --by test >/dev/null 2>&1
[ $? -ne 0 ] && ok "値が要確認のまま PASS は記録させない" || ng "値が要確認のまま PASS は記録させない"
python3 "$CR" set B0TEST0006 no_such_item --value a --result PASS --source x --by test >/dev/null 2>&1
[ $? -ne 0 ] && ok "未知の項目 id は拒否" || ng "未知の項目 id は拒否"
python3 "$CR" set bad gate_type --value a --result PASS --source x --by test >/dev/null 2>&1
[ $? -ne 0 ] && ok "ASIN の形でなければ拒否" || ng "ASIN の形でなければ拒否"
python3 "$CR" verify B0TEST0005 >/dev/null; [ $? -eq 0 ] && ok "verify 全PASS → exit 0" || ng "verify 全PASS → exit 0"
python3 "$CR" verify B0TEST0005 B0TEST0002 >"$T/v" ; [ $? -eq 1 ] && grep -q "buybox_seller" "$T/v" && ok "verify 1件でも不可 → exit 1・項目を列挙" || ng "verify 1件でも不可 → exit 1"
python3 "$CR" show B0TEST0002 | grep -q "発注不可" && ok "show が不可を表示" || ng "show が不可を表示"
python3 "$CR" set B0TEST0005 gate_type --value "再確認" --result PASS --source y --by test >/dev/null
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));assert d["history"][-1]["value"]=="確認済み"' "$T/checks/B0TEST0005.json" \
  && ok "上書き時は前の値を history に残す" || ng "上書き時は前の値を history に残す"

echo "== spec に項目を足しても動く（プランナーの17項目化に備える）=="
python3 - "$T/scripts/sourcing_gate/checklist_spec.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d["items"].append({"id": "maker_direct_seller", "no": 13, "name": "メーカー直販の有無（追加項目）",
                   "how": "テスト用", "fail_if": "テスト用", "max_age_days": 3, "required": True})
json.dump(d, open(p, "w"), ensure_ascii=False)
PY
payload_write "$P" "<!-- order-asins: B0TEST0005 -->" >"$T/p.json"; expect "項目追加後は、既存の全PASS ASIN も新項目の欠落で止まる" 2 "maker_direct_seller"
python3 "$CR" set B0TEST0005 maker_direct_seller --value "なし" --result PASS --source z --by test >/dev/null \
  && ok "追加項目を CLI で記録できる" || ng "追加項目を CLI で記録できる"
expect "追加項目を記録すれば通る" 0
cp "$REPO/scripts/sourcing_gate/checklist_spec.json" "$T/scripts/sourcing_gate/"

echo "== spec が壊れていたら発注案は止める（fail-closed）・通常文書は通す =="
echo '{broken' >"$T/scripts/sourcing_gate/checklist_spec.json"
payload_write "$P" "<!-- order-asins: B0TEST0005 -->" >"$T/p.json"; expect "spec 破損 → 発注案はブロック" 2 "読めない"
payload_write "$D/02_調査メモ.md" "ふつうのメモ" >"$T/p.json"; expect "spec 破損でも通常文書は通す" 0
cp "$REPO/scripts/sourcing_gate/checklist_spec.json" "$T/scripts/sourcing_gate/"

echo "== 既存フックとの非干渉 =="
payload_write "$D/02_調査メモ.md" "Amazon 売価 1,980円、販売手数料 297円。" >"$T/p.json"
for h in asset-claim-guard.py source-terms-guard.py order-gate-guard.py; do
  python3 "$HOOKS/$h" <"$T/p.json" 2>/dev/null; rc=$?
  [ "$rc" = "0" ] && ok "通常の成果物を $h が通す" || ng "通常の成果物を $h が通す（exit=$rc）"
done
grep -q 'order-gate-guard.py' "$REPO/.claude/settings.json" && grep -q 'source-terms-guard.py' "$REPO/.claude/settings.json" \
  && grep -q 'asset-claim-guard.py' "$REPO/.claude/settings.json" && ok "settings.json に3本とも登録" || ng "settings.json 登録"

echo "== pre-commit（使い捨ての git リポで本物のフックを動かす）=="
G="$T/git"; mkdir -p "$G/scripts/sourcing_gate" "$G/workspace/output/deliverables/T-1"
cp "$REPO/scripts/sourcing_gate/gate.py" "$REPO/scripts/sourcing_gate/checklist_spec.json" "$G/scripts/sourcing_gate/"
(
  cd "$G" && git init -q && git config user.email t@example.test && git config user.name t \
    && git config core.hooksPath "$REPO/.githooks"
  unset CLAUDE_PROJECT_DIR
  export SOURCING_CHECKS_DIR="$T/checks"
  printf '# 旧い発注案\n本文\n' >workspace/output/deliverables/T-1/01_発注案.md
  git add -A && git commit -q --no-verify -m base
  printf '# 旧い発注案\n本文を直した\n' >workspace/output/deliverables/T-1/01_発注案.md
  git add -A; git commit -q -m legacy 2>/dev/null && echo "PC1 ok" || echo "PC1 ng"
  printf '<!-- order-asins: B0TEST0001 -->\n# 発注案\n' >workspace/output/deliverables/T-1/02_発注案.md
  git add -A; git commit -q -m new-ng 2>/dev/null && echo "PC2 ng" || echo "PC2 ok"
  printf '<!-- order-asins: B0TEST0005 -->\n# 発注案\n' >workspace/output/deliverables/T-1/02_発注案.md
  git add -A; git commit -q -m new-ok 2>/dev/null && echo "PC3 ok" || echo "PC3 ng"
  printf '<!-- order-asins: B0TEST0005, B0TEST0002 -->\n# 発注案\n' >workspace/output/deliverables/T-1/02_発注案.md
  git add -A; git commit -q -m mod-ng 2>/dev/null && echo "PC4 ng" || echo "PC4 ok"
  git reset -q --hard
  printf 'メモ\n' >workspace/output/deliverables/T-1/03_memo.md
  git add -A; git commit -q -m memo 2>/dev/null && echo "PC5 ok" || echo "PC5 ng"
) >"$T/pc" 2>/dev/null
chk() { grep -q "^$1 ok" "$T/pc" && ok "$2" || ng "$2（$(tr '\n' ' ' <"$T/pc")）"; }
chk PC1 "pre-commit: マーカー無しの旧い発注案の編集は止めない（自動同期を止めない）"
chk PC2 "pre-commit: 未確認 ASIN の新規発注案は止める"
chk PC3 "pre-commit: 全PASS の発注案は通す"
chk PC4 "pre-commit: マーカー付き発注案の変更で未確認 ASIN を足したら止める"
chk PC5 "pre-commit: 発注案以外は通す"

echo ""
echo "$N 件中 失敗 $F 件"
exit $FAIL
