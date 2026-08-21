#!/bin/bash
# PostToolUse フック：チケットファイル変更 → Notion 即時同期を強制
#
# 役割: workspace/tickets/ 配下の .md を作成・編集・移動・削除する操作を検知し、
#       「マリエの Notion 同期スキルに従って該当 TicketID を即時反映せよ」という
#       リマインダーを additionalContext で注入する。
#
# 背景: Notion はホスト型 MCP 経由でしか書けず、シェルから直接 API を叩けない
#       （ローカルに NOTION_API_KEY が無い）。よって「ファイル変更で自動同期」は
#       原理的に不可能。代わりに本フックが強制関数として働き、エージェントに
#       「同期せずに turn を終えるな」と促す。
#
# 設計:
# - PostToolUse / Write|Edit|MultiEdit|NotebookEdit|Bash にマッチ
# - チケット変更でない操作では無音（exit 0）
# - 検知時のみ JSON で additionalContext を返す

set -euo pipefail

export HOOK_INPUT="$(cat)"

REMINDER="$(python3 - <<'PY'
import json, os, re, sys

try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}

paths = []
mutating = False

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    p = ti.get("file_path") or ti.get("notebook_path") or ""
    if p:
        paths.append(p)
        mutating = True
elif tool == "Bash":
    cmd = ti.get("command", "") or ""
    # チケットを物理的に動かす/消す操作のみ対象（参照系 ls/cat/sed 等は除外）
    if "workspace/tickets/" in cmd and re.search(r'\b(mv|cp|rm|git\s+mv|git\s+rm)\b', cmd):
        paths.append(cmd)
        mutating = True

if not mutating:
    sys.exit(0)

blob = " ".join(paths)
if "workspace/tickets/" not in blob:
    sys.exit(0)

ids = sorted(set(re.findall(r'T-\d{8}-\d{3}', blob)))
id_str = "、".join(ids) if ids else "（ファイル名から TicketID を確認）"

# --- frontmatter キー契約の検証（2026-08-21 追加 / T-20260821-002）------------------
# `owner:` と `assignee:` は日本語だとどちらも「担当」で、書いた本人には違いが見えない。
# 警告文をテンプレに書くだけでは再発するため、機械的にチェックする。
# 検証は警告のみ。ブロックはしない（社長の作業を止めない）。
ASSIGNEE_VOCAB = {
    "secretary", "researcher", "planner", "simulator", "accounting",
    "legal", "general_affairs", "content_creator", "it_engineer", "owner",
}
# ⚠️ この語彙は「チケット frontmatter の契約」であり snake_case。
#    `.claude/agents/` のサブエージェント名（general-affairs 等・ハイフン）とは別物。混同しないこと。
ALIAS_TRAPS = {
    "id": "ticket_id",
    "owner": "assignee",
    "assigned_to": "assignee",
    "related": "related_tickets",
    "next_check": "next_check_at",
    "due": "next_check_at",
}

def parse_frontmatter(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    kv = {}
    for line in m.group(1).split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")):   # ネスト/リスト継続行は対象外
            continue
        k, sep, v = line.partition(":")
        if sep:
            kv[k.strip()] = v.strip()
    return kv

base = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
problems = []
checked = []

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    for p in paths:
        if "workspace/tickets/" not in p or not p.endswith(".md"):
            continue
        if os.path.basename(p).startswith("_"):   # _template.md 等は対象外
            continue
        full = p if os.path.isabs(p) else os.path.join(base, p)
        try:
            with open(full, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue

        rel = os.path.basename(full)
        fm = parse_frontmatter(text)
        if fm is None:
            problems.append(f"- {rel}: frontmatter（先頭の `---` ブロック）が見つかりません")
            continue
        checked.append(rel)

        for bad, good in ALIAS_TRAPS.items():
            if bad in fm and good not in fm:
                problems.append(f"- {rel}: `{bad}:` は誤り。正しいキー名は `{good}:` です（機械が読む契約）")

        tid = fm.get("ticket_id", "")
        if not tid:
            problems.append(f"- {rel}: `ticket_id:` がありません（session-start.sh が awk で直読みします）")
        elif not re.fullmatch(r'T-\d{8}-\d{3}', tid):
            problems.append(f"- {rel}: `ticket_id: {tid}` の形式が不正です（T-YYYYMMDD-NNN）")

        asg = fm.get("assignee", "")
        if not asg:
            problems.append(f"- {rel}: `assignee:` がありません（Notion の担当欄が空白になります）")
        elif asg not in ASSIGNEE_VOCAB:
            problems.append(
                f"- {rel}: `assignee: {asg}` は固定語彙外です。"
                + "許可値: " + " / ".join(sorted(ASSIGNEE_VOCAB))
            )

# --- ticket_id 一意性の検証（2026-08-21 追加 / T-20260821-002 追補）------------------
# 形式が正しくても、同じ ticket_id が2枚あれば Notion の同期キーとして破綻する。
# 実害: 別チケットの状態を上書き／後発のカードが作成できずボードから消える
#       （T-20260603-003 と T-20260706-001 が3ヶ月弱、誰にも気づかれず放置された）。
#
# ⚠️ 重複は必ず「全パスを出す」こと。片方だけ出す実装は、この事故を招いた
#    `ls ... | head -1` と同じ見落としを再生産する。
if checked:
    # チケットルートは編集されたパス自身から導出する（cwd 依存を避ける）
    troot = ""
    for p_ in paths:
        i = p_.find("workspace/tickets/")
        if i >= 0:
            cand = p_[:i] + "workspace/tickets"
            troot = cand if os.path.isabs(cand) else os.path.join(base, cand)
            break

    if troot and os.path.isdir(troot):
        seen = {}
        for dirpath, _dirnames, filenames in os.walk(troot):
            for fn in filenames:
                if not fn.endswith(".md") or fn.startswith("_"):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    # frontmatter は必ずファイル先頭にあるので冒頭だけ読む（90枚でも軽い）
                    with open(fp, encoding="utf-8") as fh:
                        head = fh.read(4096)
                except Exception:
                    continue
                hm = re.match(r'^---\n(.*?)\n---\n', head, re.S)
                if not hm:
                    continue
                for line in hm.group(1).split("\n"):
                    if line.startswith("ticket_id:"):
                        v = line.split(":", 1)[1].strip()
                        if v:
                            seen.setdefault(v, []).append(fp)
                        break

        dups = {k: v for k, v in seen.items() if len(v) > 1}
        if dups:
            touched_ids = set(re.findall(r'T-\d{8}-\d{3}', " ".join(paths)))
            for tid_ in sorted(dups):
                mark = "  ← 今編集したチケット" if tid_ in touched_ids else ""
                problems.append(f"- 🔑 ticket_id `{tid_}` が {len(dups[tid_])} 枚に重複しています{mark}")
                for fp in sorted(dups[tid_]):
                    problems.append(f"    * {os.path.relpath(fp, troot)}")
            problems.append(
                "  → Notion の同期キーが衝突します（別チケットの状態を上書きする／"
                "後発のカードが作成できずボードから消える）。どちらかを改番してください。"
            )

if problems:
    print(
        "🚨 チケット frontmatter の契約違反を検知しました（ブロックはしません。直してから turn を終えてください）。\n"
        + "\n".join(problems)
        + "\n→ キー名は機械が読む契約です。省略は可、リネームは不可。"
          "雛形と固定語彙は workspace/tickets/_template.md の警告ブロックを参照。\n"
    )

print(
    "⚠️ チケットファイルの変更を検知しました（" + id_str + "）。\n"
    "庶務マリエの責務として、agents/general_affairs/skills/notion-ticket-sync.md に従い、"
    "この turn を終える前に該当チケットを Notion カンバン（Amazon物販事業 Tickets）へ即時同期してください。\n"
    "- 新規起票 → notion-create-pages でカード作成\n"
    "- 状態遷移/内容更新 → TicketID で該当カードを特定し notion-update-page で Status/UpdatedAt 等を更新\n"
    "未同期のまま応答を終えないこと。"
)
PY
)" || exit 0

[ -z "$REMINDER" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$REMINDER" '{
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: $msg
    }
  }'
else
  printf '%s\n' "$REMINDER"
fi

exit 0
