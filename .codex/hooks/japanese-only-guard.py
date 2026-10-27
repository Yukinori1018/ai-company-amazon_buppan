#!/usr/bin/env python3
"""社長に見える文字を英語で書いたら、出す前に止めて日本語で書き直させる（T-20261026-002）。

背景
  10/19〜10/27 の会話で、秘書が社長に英語で問いかけた・報告した箇所を数えた
  （agent_output/T-20261026-002/parse_v2.py）。英語は「締めの箱（wrap_up の recap・ask・ボタン）」
  「タスク一覧（update_plan）」「途中経過の本文」に出ていた。AskUserQuestion は0件。
  フォルダなしで始まった会話（CLAUDE.md が読まれない）と夜間の予約タスクに偏っていた。

動き（イベントごと）
  PreToolUse : 社長に見える道具（AskUserQuestion・wrap_up・update_plan・start_session/spawn_task・
               mark_chapter・SendUserFile）の文字に英語の欄があれば deny し、理由に「日本語で書き直す」を返す。
               → モデルが日本語で呼び直す。社長には英語が出ない。
  Stop       : このターンの最後の本文が英語なら1回だけ block し、日本語で言い直させる
               （stop_hook_active=true のときは止めない＝ループしない）。
  それ以外    : 何もしない。壊れた入力でも exit 0（作業を止めない）。

「英語」の判定
  コード片（`...`）・URL・パス・ファイル名を除いたうえで、日本語の文字が1つも無く、
  英単語（2文字以上）が3語以上ある欄。固有名詞2語（「Yoga Works」）や「OK」は通す。
"""
import json
import re
import sys

JP = re.compile(r"[぀-ヿ一-鿿]")
WORD = re.compile(r"[A-Za-z]{2,}")
CODEISH = re.compile(r"`[^`]*`|https?://\S+|(?<!\w)/[\w./-]+|\b[\w-]+\.(?:md|py|sh|json|csv|html|txt)\b|\b[A-Z0-9]{10}\b")

FIX = ("社長に見える文字は日本語で書く決まりです（CLAUDE.md §A1）。"
       "英語の欄を日本語に書き直して、同じ呼び出しをやり直してください。"
       "固有名詞・型番・コマンドはそのままで構いません。")


def is_english(s):
    if not isinstance(s, str) or not s.strip():
        return False
    t = CODEISH.sub(" ", s)
    if JP.search(t):
        return False
    return len(WORD.findall(t)) >= 3


def owner_facing_fields(name, ti):
    """(欄の名前, 文字) を返す。社長の画面に出る欄だけ。"""
    out = []
    if name == "AskUserQuestion":
        for q in ti.get("questions") or []:
            if not isinstance(q, dict):
                continue
            out += [("質問", q.get("question")), ("見出し", q.get("header"))]
            for o in q.get("options") or []:
                if isinstance(o, dict):
                    out += [("選択肢", o.get("label")), ("選択肢の説明", o.get("description"))]
    elif name.endswith("__wrap_up"):
        out += [("まとめ(recap)", ti.get("recap")), ("問い(ask)", ti.get("ask"))]
        acts = ti.get("actions") or []
        if isinstance(acts, str):
            try:
                acts = json.loads(acts)
            except Exception:
                acts = []
        for a in acts if isinstance(acts, list) else []:
            if isinstance(a, dict):
                out += [("ボタン", a.get("label")), ("ボタンの送信文", a.get("message"))]
    elif name.endswith("__update_plan"):
        for it in ti.get("items") or []:
            if isinstance(it, dict):
                out.append(("タスク一覧", it.get("content")))
    elif name.endswith("__start_session") or name.endswith("__spawn_task"):
        for k in ("title", "description", "summary", "tldr", "reason"):
            out.append((f"カード({k})", ti.get(k)))
    elif name.endswith("__mark_chapter"):
        out += [("章の名前", ti.get("title")), ("章の説明", ti.get("summary"))]
    elif name == "SendUserFile":
        for k in ("caption", "message", "description"):
            out.append((f"送付({k})", ti.get(k)))
    return [(k, v) for k, v in out if isinstance(v, str) and v.strip()]


def pre_tool_use(data):
    name = data.get("tool_name") or ""
    bad = [(k, v) for k, v in owner_facing_fields(name, data.get("tool_input") or {}) if is_english(v)]
    if not bad:
        return None
    sample = "／".join(f"{k}「{v[:40]}」" for k, v in bad[:3])
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"【日本語チェック】英語の欄があります：{sample}。{FIX}",
    }}


def last_turn_text(transcript_path):
    """このターン（最後の社長の発話より後）のアシスタント本文のうち、最後の1つ。"""
    try:
        lines = open(transcript_path, encoding="utf-8", errors="ignore").read().splitlines()[-400:]
    except Exception:
        return ""
    last = ""
    for line in lines:
        try:
            x = json.loads(line)
        except Exception:
            continue
        if x.get("isSidechain"):
            continue
        if x.get("type") == "user":
            m = (x.get("message") or {}).get("content")
            is_result = isinstance(m, list) and any(isinstance(y, dict) and y.get("type") == "tool_result" for y in m)
            if not is_result:
                last = ""          # 新しいターン
        elif x.get("type") == "assistant":
            for y in (x.get("message") or {}).get("content") or []:
                if isinstance(y, dict) and y.get("type") == "text" and (y.get("text") or "").strip():
                    last = y["text"]
    return last


def stop(data):
    if data.get("stop_hook_active"):
        return None
    text = data.get("last_assistant_message") or last_turn_text(data.get("transcript_path") or "")
    if not is_english(text):
        return None
    return {"decision": "block",
            "reason": f"【日本語チェック】最後の返答が英語でした（冒頭：「{text[:60]}」）。{FIX} 同じ内容を日本語で言い直してください。"}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("agent_id"):        # サブエージェント内は対象外（社長に直接は見えない）
        return 0
    ev = data.get("hook_event_name") or ""
    out = pre_tool_use(data) if ev == "PreToolUse" else stop(data) if ev == "Stop" else None
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
