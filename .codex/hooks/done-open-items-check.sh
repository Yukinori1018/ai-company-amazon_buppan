#!/bin/bash
# PostToolUse フック：チケットを done/ へ移した瞬間に、ログに残った未決事項を警告する
#
# 背景（2026-09-12 / T-20260912-001 08_忘れの原因と対策.md）:
#   T-20260826-004 を done にしたとき、ログにあった「メキシコの件は宙に浮いている」
#   が後継チケットへ引き継がれずに落ちた。後日、秘書が記録済みの事実を
#   「新発見」として社長に報告する事故になった。
#
# 動き:
#   - Bash の mv / git mv で workspace/tickets/done/ へ移した時、または
#     Write で done/ にファイルを作った時だけ発火（それ以外は無音）
#   - 移したチケットから「宙に浮」「未回答」「要確認」「未確認」の行を拾う
#   - 強い語（宙に浮・未回答）を先に、残りは新しい（下の）行から。最大8行
#   - 警告だけ。ブロックしない（exit 0 固定）
#
# 誤検知について: 解決済みの行も拾う。判定は人がする（拾った行を後継に
#   引き継ぐか、「解決済み」と追記するか）。自動で引き継ぎはしない。

set -uo pipefail

export HOOK_INPUT="$(cat)"
export REPO="${CLAUDE_PROJECT_DIR:-$(pwd)}"

MSG="$(python3 - <<'PY'
import json, os, re, glob, sys

try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}
done_dir = os.path.join(os.environ["REPO"], "workspace/tickets/done")

files = []
if tool == "Bash":
    cmd = ti.get("command", "") or ""
    if "tickets/done" in cmd and re.search(r'\b(mv|git\s+mv)\b', cmd):
        for tid in sorted(set(re.findall(r'T-\d{8}-\d{3}', cmd))):
            files += glob.glob(os.path.join(done_dir, tid + "*.md"))
elif tool == "Write":
    p = ti.get("file_path", "") or ""
    if "/workspace/tickets/done/" in p and p.endswith(".md"):
        files.append(p)

STRONG = ("宙に浮", "未回答")
WEAK = ("要確認", "未確認")
MAX_LINES = 8

out = []
for fp in files:
    try:
        lines = open(fp, encoding="utf-8").read().split("\n")
    except Exception:
        continue
    strong, weak = [], []
    for i, line in enumerate(lines, 1):
        if any(k in line for k in STRONG):
            strong.append((i, line))
        elif any(k in line for k in WEAK):
            weak.append((i, line))
    if not strong and not weak:
        continue
    picked = (strong + list(reversed(weak)))[:MAX_LINES]
    total = len(strong) + len(weak)
    out.append(f"■ {os.path.basename(fp)}（該当 {total} 行、うち {len(picked)} 行を表示）")
    for i, line in picked:
        s = line.strip()
        out.append(f"  L{i}: {s[:90]}{'…' if len(s) > 90 else ''}")

if out:
    print(
        "⚠️ done へ移したチケットに未決の可能性がある記述が残っています（ブロックはしません）。\n"
        + "\n".join(out)
        + "\n→ まだ生きている論点は後継チケットか台帳（memory/project_amazon_account_ledger.md）へ引き継ぐこと。"
          "解決済みならそのままで可。"
    )
PY
)" || exit 0

[ -z "$MSG" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $msg}}'
else
  printf '%s\n' "$MSG"
fi
exit 0
