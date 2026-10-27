#!/usr/bin/env python3
"""ユーザー全体（~/.claude/settings.json）に登録する「橋渡し」フック（T-20261026-002）。

何のためか（2026-10-27 夜に前提を訂正。03_前提の訂正と真因.md）
  2026-10-19（アプリ 2.1.299）以降、社長の会話は「フォルダを選ばない新規会話」として作られ、
  最初の一言で Claude が change_directory（mcp__ccd_directory__change_directory）でこのリポへ移る。
  社長から見ると「Amazon物販のフォルダで作業している会話」だが、記録で確かめると、
  Claude が道具で移った場合は次の3つが読み込まれない（10/19〜10/27 の該当15本で全部 0 件）：
    - リポの CLAUDE.md（会社ルール・日本語・振り分け）
    - リポの .claude/settings.json のフック（委譲チェック・会員限定条件の漏えいガード・発注ゲート等）
    - 担当の Agent 種類（accounting・it-engineer 等。分岐・再開した会話では後から出ることがある）
  対照：社長がアプリの画面でフォルダを切り替えた会話（10/26 0af8ed10・dc7544e1）は
  「working directory has changed ... (by the user)」の後に CLAUDE.md・リポのフック・担当の種類が全部入った。
  ~/.claude/settings.json のフックは、この会話でも動く（既存のセッション記録フックで実測）。
  そこで、この会話のときだけ、リポの CLAUDE.md §A を差し込み、リポの settings.json のフックを代わりに呼ぶ。

他のプロジェクトに影響しない仕組み（3重の門）
  1. 会話の記録（transcript_path）か作業フォルダ（cwd）が「フォルダを選ばない会話」の置き場（scratch-workspaces）、
     または作業フォルダがホームそのもの・空のときだけ動く。
     フォルダを選んで始めた会話・画面でフォルダを切り替えた会話（記録がリポの置き場へ移る）では即終了。
     → リポの .claude/settings.json のフックが動く会話とは二重にならない。
  2. さらに、この会話が Amazon 物販の話だと分かったときだけ動く：
     作業フォルダ（cwd）がこのリポの中／社長の発話に物販の語がある。一度当たれば会話の終わりまで覚える。
  3. 橋渡し自身の失敗は exit 0（無音）。リポのフックが exit 2 で止めたときだけ、その止めをそのまま返す。

動き
  UserPromptSubmit: 初回は CLAUDE.md §A1〜§A4 の本文と「道具で移っても規則は読み込まれない」を差し込む。
                    2回目以降は短い一言。どちらにも、リポの UserPromptSubmit フックの結果を足す。
  PreToolUse/PostToolUse/Stop: リポの .claude/settings.json に登録されたフックのうち、
                    出来事と matcher が合うものを全部呼ぶ（設定を読み直すので、リポのフックを足せば自動で効く）。
                    ただし、橋渡しが呼ばれるのは ~/.claude/settings.json の matcher に合う道具だけ。
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

SETTINGS = os.path.join(REPO, ".claude", "settings.json")
CLAUDE_MD = os.path.join(REPO, "CLAUDE.md")

HEAD = (
    "【Amazon物販事業の会話です。リポの規則が読み込まれていません】\n"
    "この会話は「フォルダを選ばない新規会話」として作られ、change_directory でリポへ移っています（または移る前です）。"
    "道具で移った場合、リポの CLAUDE.md・リポのフック・担当の Agent 種類は読み込まれません（2026-10-27 記録で確認）。"
    "下に CLAUDE.md §A1〜§A4 を貼ります。これがこの会話の規則です。§A5 以降は "
    f"`{REPO}/CLAUDE.md` を Read で読んでください。人格は `{REPO}/agents/secretary/agent.md`。\n"
    "- 担当の種類（accounting・it-engineer 等）が一覧に無ければ、general-purpose に "
    f"`{REPO}/agents/<担当>/agent.md` と `{REPO}/workspace/SUBAGENT_PROTOCOL.md` を読ませて振ります（§A2 の最後の項）。\n"
    "- 社長に見える文字はすべて日本語で書きます。"
)
FALLBACK = (
    f"- あなたは秘書カズヨです。作業を始める前に `{REPO}/CLAUDE.md` の §A と "
    f"`{REPO}/agents/secretary/agent.md` を Read で読み、その人格とルールで動いてください。"
)
EVERY = "【物販の会話・規則は橋渡しで適用中】社長に見える文字は日本語で。専門作業は Agent で担当に振る（CLAUDE.md §A2）。"


def section_a():
    """CLAUDE.md の §A1〜§A4 をそのまま返す（読めなければ空）。毎回ファイルから読むので最新が載る。"""
    try:
        text = open(CLAUDE_MD, encoding="utf-8").read()
    except Exception:
        return ""
    m = re.search(r"^### §A1.*?(?=^### §A5)", text, re.S | re.M)
    return m.group(0).strip() if m else ""


def first_message():
    body = section_a()
    return HEAD + "\n\n" + (body if body else FALLBACK)


def folderless(data):
    """フォルダを開かずに始まった会話か。

    実際のアプリ（2026-10-27 実測）は、記録も作業フォルダも scratch-workspaces の下になる。
    記録の場所だけで判定すると、記録の場所が渡らない・別の場所のとき（秘書の検算：
    transcript_path=/dev/null・cwd=$HOME）に物販の会話でも黙る。そこで作業フォルダも見る。
    作業フォルダがホームそのもの・空のときも、どのプロジェクトのルールも読まれていないので対象にする。
    どこかのフォルダ（このリポ・他の事業リポ）を開いた会話は、ここで落ちる。
    """
    tp = str(data.get("transcript_path") or "")
    cwd = str(data.get("cwd") or "").rstrip("/")
    if "scratch-workspaces" in tp or "scratch-workspaces" in cwd:
        return True
    return cwd in ("", os.path.expanduser("~").rstrip("/"))


def state_path(session):
    tmp = os.environ.get("TMPDIR") or "/tmp"
    return os.path.join(tmp, f"claude-buppan-bridge-{session}.json")


def repo_commands(event, tool_name):
    """リポの .claude/settings.json から、この出来事・道具に合うフックの command を順に返す。"""
    try:
        conf = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception:
        return []
    cmds = []
    for group in (conf.get("hooks") or {}).get(event, []) or []:
        matcher = group.get("matcher")
        if matcher and tool_name:
            try:
                if not re.fullmatch(matcher, tool_name):
                    continue
            except re.error:
                continue
        for h in group.get("hooks", []) or []:
            if h.get("type", "command") == "command" and h.get("command"):
                cmds.append((h["command"], h.get("timeout") or 30))
    return cmds


def run_repo_hooks(event, tool_name, payload):
    """合うフックを全部呼ぶ。戻り値：(exit 2 で止めたフックの stderr の一覧, stdout の一覧)。"""
    blocks, outs = [], []
    env = dict(os.environ, CLAUDE_PROJECT_DIR=REPO)
    for cmd, timeout in repo_commands(event, tool_name):
        try:
            r = subprocess.run(["/bin/sh", "-c", cmd], input=payload, capture_output=True, text=True,
                               timeout=min(int(timeout), 60), env=env, cwd=REPO)
        except Exception:
            continue
        if r.returncode == 2 and r.stderr.strip():
            blocks.append(r.stderr.strip())
        elif r.returncode == 0 and r.stdout.strip():
            outs.append(r.stdout.strip())
    return blocks, outs


def parse(out):
    try:
        o = json.loads(out)
        return o if isinstance(o, dict) else None
    except Exception:
        return None


def merge(event, outs, lead=None):
    """リポのフックの stdout をまとめて、橋渡しの出力（dict か None）にする。
    止める判断（PreToolUse の deny／Stop の block）は最初のものを優先し、それ以外は差し込み文を連結する。"""
    contexts = [lead] if lead else []
    for out in outs:
        o = parse(out)
        if o is None:
            contexts.append(out)          # 素の文字は差し込み文として扱う（Claude Code と同じ）
            continue
        hso = o.get("hookSpecificOutput") or {}
        if event == "PreToolUse" and hso.get("permissionDecision") in ("deny", "ask"):
            return o
        if event == "Stop" and o.get("decision") == "block":
            return o
        if hso.get("additionalContext"):
            contexts.append(hso["additionalContext"])
        elif o.get("systemMessage"):
            contexts.append(o["systemMessage"])
    contexts = [c for c in contexts if c]
    if not contexts:
        return None
    if event in ("UserPromptSubmit", "PostToolUse", "PreToolUse"):
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n\n".join(contexts)}}
    return {"systemMessage": "\n\n".join(contexts)}


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        return 0
    # 門1：フォルダなしの会話だけ
    if not folderless(data):
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

    lead = None
    if ev == "UserPromptSubmit":
        lead = EVERY if st.get("briefed") else first_message()
        st["briefed"] = True
    blocks, outs = ([], [])
    if ev in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        blocks, outs = run_repo_hooks(ev, data.get("tool_name"), raw)
    try:
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(st, fh)
    except Exception:
        pass
    if blocks:
        # リポのフックが exit 2 で止めた（会員限定条件の漏えい・発注ゲート等）。同じ止め方で返す。
        sys.stderr.write("\n\n".join(blocks))
        return 2
    out = merge(ev, outs, lead)
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
