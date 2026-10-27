#!/usr/bin/env python3
"""日本語チェックと、フォルダなし会話への橋渡しを settings.json に登録する（T-20261026-002）。

既定は「見るだけ」（変更後の差分を表示して終わる）。登録は --apply を付けたときだけ。
設定ファイルの変更なので、社長の承認を取ってから秘書が実行する。

  python3 .claude/hooks/install_language_and_bridge_hooks.py            # 差分を見る
  python3 .claude/hooks/install_language_and_bridge_hooks.py --apply    # 両方に登録
  python3 .claude/hooks/install_language_and_bridge_hooks.py --apply --only project  # リポだけ
  python3 .claude/hooks/install_language_and_bridge_hooks.py --apply --only user     # ユーザー全体だけ

何を足すか
  project（このリポの .claude/settings.json）:
    PreToolUse（社長に見える道具）と Stop に japanese-only-guard.py
  user（~/.claude/settings.json）:
    UserPromptSubmit・PreToolUse・PostToolUse・Stop に global-buppan-bridge.py
    （フォルダなしで始まった物販の会話のときだけ動く。他のプロジェクトでは即終了）
何度実行しても同じ結果（登録済みなら足さない）。書き換え前に .bak.<日時> を残す。
"""
import argparse
import datetime
import difflib
import json
import os
import shutil

REPO = "/Users/yukinori/Claude Code/ai-company-amazon_buppan"
PROJECT = os.path.join(REPO, ".claude", "settings.json")
USER = os.path.expanduser("~/.claude/settings.json")
OWNER_FACING = "AskUserQuestion|SendUserFile|mcp__ccd_turn__.*|mcp__ccd_session__.*"
# 作業として数える道具（リポの work-without-delegation-check.py と同じ）。全部の道具で起動しないように絞る
WORK = ("Bash|Edit|Write|MultiEdit|NotebookEdit|Agent|Task|mcp__claude-in-chrome__.*|"
        "mcp__Claude_Browser__.*|mcp__computer-use__.*|mcp__Control_Chrome__.*")

GUARD_PROJECT = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/japanese-only-guard.py'
BRIDGE_USER = f"'{REPO}/.claude/hooks/global-buppan-bridge.py'"

PLAN = {
    "project": [("PreToolUse", OWNER_FACING, GUARD_PROJECT), ("Stop", None, GUARD_PROJECT)],
    "user": [("UserPromptSubmit", None, BRIDGE_USER),
             ("PreToolUse", OWNER_FACING, BRIDGE_USER),
             ("PostToolUse", WORK, BRIDGE_USER),
             ("Stop", None, BRIDGE_USER)],
}


def add(settings, event, matcher, command):
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
        return False
    g = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        g = {"matcher": matcher, **g}
    groups.append(g)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", choices=["project", "user"])
    a = ap.parse_args()
    for target, path in (("project", PROJECT), ("user", USER)):
        if a.only and a.only != target:
            continue
        before = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        after = json.loads(json.dumps(before))
        changed = [add(after, *p) for p in PLAN[target]]
        old = json.dumps(before, ensure_ascii=False, indent=2).splitlines()
        new = json.dumps(after, ensure_ascii=False, indent=2).splitlines()
        print(f"== {target}: {path}（追加 {sum(changed)} 件）")
        print("\n".join(difflib.unified_diff(old, new, "before", "after", lineterm="")) or "（変更なし）")
        if a.apply and any(changed):
            if os.path.exists(path):
                shutil.copy2(path, f"{path}.bak.{datetime.datetime.now():%Y%m%d-%H%M%S}")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(after, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"→ 書き込みました")
    if not a.apply:
        print("\n（見るだけ。登録するには --apply）")


if __name__ == "__main__":
    main()
