#!/bin/bash
# UserPromptSubmit フック：_inbox_社長共有 の未処理ファイル検知（セッション中の投函をつかまえる）
#
# 新設: 2026-08-31 / T-20260831-003
#
# ── なぜ SessionStart だけでは足りないのか ──
#
# 既存の検知は `.claude/hooks/session-start.sh` のリマインダー③だけでした。これは
# **セッション開始時に一度しか動きません**。ところが社長がファイルを投函するのは、
# たいてい「その話をしている最中」です。実例（2026-08-31）:
#
#   10:03  セッション開始（この時点の inbox 直下は HEIC 2件）
#   10:13〜10:34  社長が e-Tax の PDF を4件投函
#   → SessionStart はとっくに終わっているので、この4件は**構造的に検知不可能**
#
# つまり「社長が今まさに共有したファイル」こそ、旧実装がいちばん取りこぼす対象でした。
# T-20260821-009 が断とうとした「社長の申告に依存するプル型トリガー」が、
# セッション中に限っては温存されていたことになります。ここを塞ぎます。
#
# ── 設計 ──
# - **ターンを絶対にブロックしない**（常に exit 0）。社長の手を止めない
# - 発火条件は2つだけ:
#     (a) 前回見たファイル集合から**変化した**（＝新しく投函された）→ 即発火
#     (b) 変化はないが未処理のまま **COOLDOWN 秒**が経過した → 再発火（忘れ防止）
# - 状態は $TMPDIR にセッション ID で置く（リポを汚さない／セッション終了で自然消滅）
# - プロンプト内容では抑制しない。トリガーはファイルシステムの状態であってプロンプトではないため

set -euo pipefail

export HOOK_INPUT="$(cat)"
export REPO="${CLAUDE_PROJECT_DIR:-$(pwd)}"

MESSAGE="$(python3 - <<'PY'
import json, os, re, sys, time, datetime, hashlib

REPO = os.environ.get("REPO") or "."
INBOX = os.path.join(REPO, "_inbox_社長共有")
if not os.path.isdir(INBOX):
    sys.exit(0)

# 未処理カウントの定義は session-start.sh のリマインダー③と厳密に揃える。
# ここがずれると「片方だけ鳴る」ことになり、どちらも信用されなくなる。
EXCLUDE = {"README.txt", ".DS_Store", ".gitkeep"}

try:
    names = sorted(
        n for n in os.listdir(INBOX)
        if n not in EXCLUDE and os.path.isfile(os.path.join(INBOX, n))
    )
except Exception:
    sys.exit(0)

if not names:
    sys.exit(0)

try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
except Exception:
    data = {}
session = re.sub(r'[^A-Za-z0-9_-]', '_', str(data.get("session_id") or "nosession"))[:64]

COOLDOWN = 1800  # 30分。未処理が残り続けている間は30分ごとに1回だけ再点火する

tmp = os.environ.get("TMPDIR") or "/tmp"
state = os.path.join(tmp, f"claude-inbox-intake-{session}.state")

sig = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()[:16]
now = time.time()

last_ts, last_sig = 0.0, ""
try:
    with open(state, encoding="utf-8") as fh:
        raw = fh.read().strip().split("|", 1)
        last_ts = float(raw[0])
        last_sig = raw[1] if len(raw) > 1 else ""
except Exception:
    pass

changed = (sig != last_sig)
if not changed and (now - last_ts) < COOLDOWN:
    sys.exit(0)

try:
    with open(state, "w", encoding="utf-8") as fh:
        fh.write(f"{now}|{sig}")
except Exception:
    pass

# --- 新規投函分を名指しする（社長が「今入れたよ」と言わなくても分かるように）---
last_names = set()
nl = os.path.join(tmp, f"claude-inbox-intake-{session}.names")
try:
    with open(nl, encoding="utf-8") as fh:
        last_names = set(filter(None, fh.read().split("\n")))
except Exception:
    pass
new_names = [n for n in names if n not in last_names] if last_names else []
try:
    with open(nl, "w", encoding="utf-8") as fh:
        fh.write("\n".join(names))
except Exception:
    pass

# --- 滞留日数 ---
age_txt = ""
try:
    oldest = min(os.path.getmtime(os.path.join(INBOX, n)) for n in names)
    days = (datetime.date.today() - datetime.date.fromtimestamp(oldest)).days
    age_txt = f"・最古 {days} 日滞留" if days > 0 else "・本日投函"
except Exception:
    pass

sample = "\n".join(f"  - {n}" for n in names[:5])
if len(names) > 5:
    sample += f"\n  - …ほか {len(names) - 5} 件"

head = f"【inbox 検知】`_inbox_社長共有/` に未処理 {len(names)} 件{age_txt}"
if new_names:
    shown = "、".join(new_names[:3])
    if len(new_names) > 3:
        shown += f" ほか{len(new_names)-3}件"
    head += f"\n**このセッション中に新しく投函されました: {shown}**"

print(
    head + "\n\n" + sample + "\n\n"
    "**社長に「棚卸ししますか？」と聞かず、そのまま庶務マリエへ Agent 発注してください**"
    "（subagent_type: general-affairs / 手順: agents/general_affairs/skills/inbox-intake.md）。\n"
    "棚卸しは退避・リネームのみで不可逆操作を含まないため CLAUDE.md §4.2 の自律範囲です。"
    "社長が明示的に「後にして」と言った場合だけ止めます。\n"
    "削除だけは §4.1（不可逆な削除）。破棄候補はリスト化して社長承認を取ること。"
)
PY
)" || exit 0

[ -z "$MESSAGE" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$MESSAGE" '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: $msg
    }
  }'
else
  printf '%s\n' "$MESSAGE"
fi

exit 0
