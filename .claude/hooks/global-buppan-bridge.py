#!/usr/bin/env python3
"""ユーザー全体（~/.claude/settings.json）に登録する「橋渡し」フック（T-20261026-002）。

何のためか
  社長の会話の多くが「フォルダを開かずに」始まる（10/20〜10/27 は25本中22本）。
  その会話ではリポの CLAUDE.md もリポのフック（委譲チェック等）も読み込まれない。
  ~/.claude/settings.json のフックはフォルダなしの会話でも動く（2026-10-27 実測：
  既存のセッション記録フックが、フォルダなしの会話 a038f1d8・f6a37f68 等でも発火していた）。
  そこで、このリポに関係する会話のときだけ、リポのフックを呼び出して効かせる。

他のプロジェクトに影響しない仕組み（3重の門）
  1. 会話の記録（transcript_path）が「フォルダなし」の置き場（scratch-workspaces）のときだけ動く。
     どこかのフォルダを開いて始めた会話（このリポ・他の事業リポ）では即終了。
     → このリポで始めた会話は、リポの .claude/settings.json のフックが動くので二重にならない。
  2. さらに、この会話が Amazon 物販の話だと分かったときだけ動く：
     作業フォルダ（cwd）がこのリポの中／社長の発話に物販の語がある。一度当たれば会話の終わりまで覚える。
  3. 何が起きても exit 0。止めるのは日本語チェック（社長に英語を出す直前）だけ。

動き
  UserPromptSubmit: 初回は「あなたは秘書カズヨ・§A を読む・振り分け・日本語」を差し込む。
                    2回目以降は短い一言（日本語・振り分け）＋リポの delegation-check.sh の結果。
  PostToolUse     : リポの work-without-delegation-check.py の結果（作業中の抱え込み検知）。
  PreToolUse/Stop : リポの japanese-only-guard.py の結果（英語を出す前に止める）。
"""
import json
import os
import re
import subprocess
import sys

REPO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan"
HOOKS = os.path.join(REPO, ".claude", "hooks")
TOPIC = re.compile(
    r"amazon|アマゾン|物販|仕入|卸|netsea|ネッシー|スーパーデリバリー|メーカー|打診|fba|出品|セラー|セラセン|"
    r"keepa|キーパ|asin|(?-i:JAN)|カズヨ|おりおん|satoy|サトイ|利益|採算|台帳|商品判定|T-20\d{6}-\d{3}",
    re.I)

FIRST = (
    "【Amazon物販事業の会話です（フォルダなしで始まったため、リポのルールが読み込まれていません）】\n"
    f"- あなたは秘書カズヨです。作業を始める前に `{REPO}/CLAUDE.md` の §A（先頭約100行）と "
    f"`{REPO}/agents/secretary/agent.md` を Read で読み、その人格とルールで動いてください。\n"
    "- 社長に見える文字（本文・質問・選択肢・ボタン・タスク一覧・カード・コミットの本文）はすべて日本語で書きます。\n"
    "- 振り分け（§A2）：社長との対話・統合・チケット操作・1手の事実確認・ブラウザ操作そのもの以外は、Agent で担当に振ります。"
    "accounting・legal などの種類が一覧に無ければ、general-purpose に "
    f"`{REPO}/agents/<担当>/agent.md` と `workspace/SUBAGENT_PROTOCOL.md` を読ませて振ります。\n"
    "- 社長承認が必須の操作（§A3：送信・決済・契約・削除・第三者連絡）は実行前に止めます。\n"
    f"- 成果物は `{REPO}/workspace/output/deliverables/<ticket_id>/` に置いて commit します。"
)
EVERY = "【物販の会話】社長に見える文字は日本語で。専門作業は Agent で担当に振る（CLAUDE.md §A2）。"


def state_path(session):
    tmp = os.environ.get("TMPDIR") or "/tmp"
    return os.path.join(tmp, f"claude-buppan-bridge-{session}.json")


def run(script, payload):
    """リポのフックを同じ入力で呼び、stdout を返す。失敗しても空文字。"""
    path = os.path.join(HOOKS, script)
    if not os.path.exists(path):
        return ""
    try:
        cmd = ["/bin/bash", path] if path.endswith(".sh") else [sys.executable, path]
        env = dict(os.environ, CLAUDE_PROJECT_DIR=REPO)
        r = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=20, env=env, cwd=REPO)
        return r.stdout.strip()
    except Exception:
        return ""


def context_of(out):
    """フックの出力（JSON か素の文字）から additionalContext を取り出す。"""
    if not out:
        return ""
    try:
        return (json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext", "") or ""
    except Exception:
        return out


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        return 0
    # 門1：フォルダなしの会話だけ
    if "scratch-workspaces" not in str(data.get("transcript_path") or ""):
        return 0
    if data.get("agent_id"):
        return 0
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or "nosession"))[:64]
    sp = state_path(session)
    try:
        st = json.load(open(sp, encoding="utf-8"))
    except Exception:
        st = {}
    ev = data.get("hook_event_name") or ""
    # 門2：物販の会話か（一度当たれば覚える）
    if not st.get("relevant"):
        cwd = str(data.get("cwd") or "")
        if cwd.startswith(REPO) or (ev == "UserPromptSubmit" and TOPIC.search(data.get("prompt") or "")):
            st["relevant"] = True
        else:
            return 0

    out = None
    if ev == "UserPromptSubmit":
        msgs = [EVERY if st.get("briefed") else FIRST]
        st["briefed"] = True
        extra = context_of(run("delegation-check.sh", raw))
        if extra:
            msgs.append(extra)
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(msgs)}}
    elif ev == "PostToolUse":
        extra = run("work-without-delegation-check.py", raw)
        out = json.loads(extra) if extra.startswith("{") else None
    elif ev in ("PreToolUse", "Stop"):
        extra = run("japanese-only-guard.py", raw)
        out = json.loads(extra) if extra.startswith("{") else None

    try:
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(st, fh)
    except Exception:
        pass
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
