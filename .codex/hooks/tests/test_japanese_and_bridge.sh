#!/bin/bash
# 日本語チェック（japanese-only-guard.py）と、フォルダなし会話への橋渡し（global-buppan-bridge.py）の試験。
#   bash .claude/hooks/tests/test_japanese_and_bridge.sh
# T-20261026-002。実リポは読むだけ。状態ファイルは一時ディレクトリ（TMPDIR）に置く。
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
export TMPDIR="$(mktemp -d)"; trap 'rm -rf "$TMPDIR"' EXIT
N=0; F=0
ok() { N=$((N+1)); echo "ok   - $1"; }
ng() { N=$((N+1)); F=$((F+1)); echo "FAIL - $1"; }
# 呼び方は ~/.claude/settings.json に書く形と同じ（空白入りの絶対パスを引用符で囲み /bin/sh -c）
G="'$HOOKS/japanese-only-guard.py'"
B="'$HOOKS/global-buppan-bridge.py'"
call() { OUT="$(printf '%s' "$2" | /bin/sh -c "$1" 2>"$TMPDIR/err")"; RC=$?; ERR="$(cat "$TMPDIR/err")"; }
has()  { case "$OUT" in *"$2"*) ok "$1";; *) ng "$1（「$2」が無い / out=${OUT:0:160} err=${ERR:0:160}）";; esac; }
none() { [ -z "$OUT" ] && [ "$RC" = 0 ] && ok "$1" || ng "$1（無音のはず / rc=$RC out=${OUT:0:160} err=${ERR:0:160}）"; }

echo "== 日本語チェック：PreToolUse =="
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"mcp__ccd_turn__wrap_up","tool_input":{"recap":"ヨガワークスの採算表ができました。","ask":"Should I add the target discount rates to the draft?","actions":[{"label":"はい","message":"追加して"}]}}'
has "wrap_up の英語の問いは deny" '"permissionDecision": "deny"'
has "理由は日本語で書き直しの指示" "日本語に書き直して"
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"mcp__ccd_turn__wrap_up","tool_input":{"recap":"採算表ができました。","ask":"平松様への問い合わせ下書きに目標掛け率を足しますか？","actions":[{"label":"Yes, add them","message":"Add the target rates to the draft."}]}}'
has "英語のボタンも deny" '"permissionDecision": "deny"'
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"mcp__ccd_turn__wrap_up","tool_input":{"recap":"Yoga Works の採算表（169 ASIN）ができました。`consistency.py` で検算済み。","ask":"平松様に送る下書きを作りますか？","actions":[{"label":"作る"},{"label":"OK"}]}}'
none "日本語＋固有名詞・コードは通す"
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"Which folder are the records in?","header":"Folder","options":[{"label":"A","description":"x"}]}]}}'
has "AskUserQuestion の英語は deny" '"permissionDecision": "deny"'
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"mcp__ccd_turn__update_plan","tool_input":{"items":[{"content":"Find the inquiry draft for Hiramatsu","status":"in_progress"}]}}'
has "タスク一覧の英語は deny" '"permissionDecision": "deny"'
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"mcp__ccd_turn__update_plan","tool_input":{"advance":true}}'
none "advance だけの update_plan は通す"
call "$G" '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls","description":"List files in the folder"}}'
none "Bash は対象外（止めない）"
call "$G" '{"hook_event_name":"PreToolUse","agent_id":"x","tool_name":"mcp__ccd_turn__wrap_up","tool_input":{"ask":"Should I do this now please?"}}'
none "サブエージェント内は対象外"
call "$G" 'not json'
none "壊れた入力でも exit 0・無音"

echo "== 日本語チェック：Stop =="
TR="$TMPDIR/t.jsonl"
printf '%s\n' '{"type":"user","message":{"content":"ヨガワークスの件どう？"}}' \
  '{"type":"assistant","message":{"content":[{"type":"text","text":"Verification is running; it opens each source and checks it."}]}}' > "$TR"
call "$G" "{\"hook_event_name\":\"Stop\",\"transcript_path\":\"$TR\",\"stop_hook_active\":false}"
has "最後の返答が英語なら block" '"decision": "block"'
call "$G" "{\"hook_event_name\":\"Stop\",\"transcript_path\":\"$TR\",\"stop_hook_active\":true}"
none "stop_hook_active=true なら止めない（ループしない）"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"text","text":"検証は終わりました。"}]}}' >> "$TR"
call "$G" "{\"hook_event_name\":\"Stop\",\"transcript_path\":\"$TR\",\"stop_hook_active\":false}"
none "最後が日本語なら通す"

echo "== 橋渡し：他のプロジェクトに影響しないか =="
call "$B" '{"hook_event_name":"UserPromptSubmit","session_id":"s1","transcript_path":"/Users/yukinori/.claude/projects/-Users-yukinori-Claude-Code-ai-company-amazon-buppan/x.jsonl","cwd":"/Users/yukinori/Claude Code/ai-company-amazon_buppan","prompt":"Amazon の仕入れの採算を出して"}'
none "リポで始めた会話では動かない（リポのフックと二重にしない）"
call "$B" '{"hook_event_name":"UserPromptSubmit","session_id":"s2","transcript_path":"/Users/yukinori/.claude/projects/-Users-yukinori-Claude-Code-ai-company-video-posting/x.jsonl","cwd":"/Users/yukinori/Claude Code/ai-company-video-posting","prompt":"Amazon の動画の台本を作って"}'
none "他の事業リポの会話では動かない（物販の語があっても）"
SCR="/Users/yukinori/.claude/projects/-Users-yukinori-Library-Application-Support-Claude-scratch-workspaces-x/y.jsonl"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"s3\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"prompt\":\"YouTube API の連携を作ってください\"}"
none "フォルダなしでも物販と関係ない会話では動かない"
call "$B" "{\"hook_event_name\":\"PreToolUse\",\"session_id\":\"s3\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"tool_name\":\"mcp__ccd_turn__wrap_up\",\"tool_input\":{\"ask\":\"Should I add the API key now please?\"}}"
none "関係ない会話では日本語チェックも掛けない"

echo "== 橋渡し：フォルダなしの物販の会話 =="
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"s4\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"prompt\":\"ヨガワークスの全商品の採算を出して、仕入れできるか判定して\"}"
has "初回は秘書カズヨの役割を差し込む" "あなたは秘書カズヨです"
has "初回に日本語の決まりを差し込む" "すべて日本語で書きます"
has "リポの委譲チェックも一緒に出る（採算→経理）" "ハジメ（経理）"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"s4\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"prompt\":\"ありがとう、続きもお願いします。次はどうする？\"}"
has "2回目以降は短い一言（物販の語が無くても覚えている）" "【物販の会話】"
call "$B" "{\"hook_event_name\":\"PreToolUse\",\"session_id\":\"s4\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"tool_name\":\"mcp__ccd_turn__wrap_up\",\"tool_input\":{\"ask\":\"Should I draft an inquiry email to Hiramatsu?\"}}"
has "物販の会話では英語の問いを止める" '"permissionDecision": "deny"'
for i in 1 2 3 4 5 6 7 8; do
  call "$B" "{\"hook_event_name\":\"PostToolUse\",\"session_id\":\"s4\",\"prompt_id\":\"p1\",\"transcript_path\":\"$SCR\",\"cwd\":\"/tmp\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"python3 profit.py --all\"}}"
done
has "作業8手で抱え込み検知が出る" "委譲チェック（作業中）"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"s5\",\"transcript_path\":\"$SCR\",\"cwd\":\"/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace\",\"prompt\":\"続けて、お願いします。ここから先の段取りを考えて\"}"
has "作業フォルダがリポの中なら、語が無くても物販の会話とみなす" "あなたは秘書カズヨです"
echo "== 橋渡し：秘書の検算の3ケース（cwd=\$HOME・transcript_path=/dev/null） =="
K="kazuyo-check-$$"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"$K\",\"transcript_path\":\"/dev/null\",\"cwd\":\"$HOME\",\"prompt\":\"Amazonの仕入れの件、NETSEAの商品の採算を見て\"}"
has "記録の場所が無くても、ホームで始めた物販の会話なら初回の差し込みが出る" "あなたは秘書カズヨです"
call "$B" "{\"hook_event_name\":\"PreToolUse\",\"session_id\":\"$K\",\"transcript_path\":\"/dev/null\",\"cwd\":\"$HOME\",\"tool_name\":\"AskUserQuestion\",\"tool_input\":{\"questions\":[{\"question\":\"Which supplier should we check first?\",\"header\":\"Supplier\",\"options\":[{\"label\":\"Check NETSEA first\",\"description\":\"Start with the wholesale site\"},{\"label\":\"Check the maker\",\"description\":\"Contact the maker directly\"}]}]}}"
has "同じ会話の英語の AskUserQuestion は止まる" '"permissionDecision": "deny"'
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"$K-2\",\"transcript_path\":\"/dev/null\",\"cwd\":\"$HOME\",\"prompt\":\"今日の夕飯のレシピを教えて\"}"
none "ホームで始めた物販と関係ない会話では動かない"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"$K-3\",\"transcript_path\":\"/dev/null\",\"cwd\":\"/Users/yukinori/Library/Application Support/Claude/scratch-workspaces/a/b/scratch-2026-10-27-x\",\"prompt\":\"Amazonの仕入れの件\"}"
has "記録の場所が渡らなくても、作業フォルダが scratch-workspaces なら動く（実アプリの cwd の形）" "あなたは秘書カズヨです"
call "$B" "{\"hook_event_name\":\"UserPromptSubmit\",\"session_id\":\"$K-4\",\"transcript_path\":\"/dev/null\",\"cwd\":\"/Users/yukinori/Claude Code/ai-company-tokyo_tour_inbound\",\"prompt\":\"Amazonの仕入れの件\"}"
none "記録の場所が無くても、他の事業リポで始めた会話では動かない"

call "$B" 'broken'
none "壊れた入力でも exit 0・無音"

echo
echo "$N 件中 失敗 $F 件"
[ "$F" = 0 ]
