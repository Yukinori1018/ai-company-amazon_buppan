#!/usr/bin/env python3
"""PostToolUse — 秘書（メイン）が担当に振らないまま作業を続けたら、同じターンの中で振るよう促す。

背景（T-20261027-001 / T-20261026-002）
  delegation-check.sh は社長の発話（UserPromptSubmit）にしか反応しない。会話の途中で
  秘書が Bash・Edit・Write・ブラウザを何十手も続けても、どこにも引っかからなかった
  （10/19 以降、振らなかったターンの上位1割は1ターン28手以上・最大110手）。
  マサルの評価（deliverables/T-20261027-001/21_評価_仮想実行.md）修正案3。

動き
  - **止めない**。additionalContext を差し込むだけ（常に exit 0）
  - サブエージェントの作業では発火しない。判定は入力の `agent_id`（サブエージェント内の
    フックにだけ入る。2026-10-27 に実測：it-engineer・content-creator・legal の全件に有り）
  - 同じターン（prompt_id）の中で、Agent に振らずに「作業」を NUDGE_AFTER 手続けたら1回差し込む。
    その後も振らなければ、さらに NUDGE_AFTER 手ごとに再び差し込む。Agent/Task を呼んだら数え直し
  - 作業として数える: Bash（読むだけのコマンドは除く）・Edit・Write・MultiEdit・NotebookEdit・ブラウザ操作
  - 数えない（秘書が自分でやってよい4つ）: チケット・owner-tasks・handover・Notion の操作、
    読むだけの Bash（cat/ls/grep/git log 等＝1手の事実確認）、Read/Grep、Agent 自体

閾値（CLAUDE.md §A6 の変数。実績で直す）
  NUDGE_AFTER = 8（環境変数 DELEGATION_NUDGE_AFTER で上書き可）
  決め方: セッション履歴の1ターンごとの作業手数（agent_output/T-20261027-001/delegation_turns.py）。
    10/01〜18（振っていた期間・本リポ・対話402ターン）で振らなかったターンのうち発火 43/295（15%）
    10/19〜（振らなくなった期間・フォルダなし含む対話146ターン）で振らなかったターンのうち発火 40/141（28%）、
    その40ターンで作業1,177手（10/19 以降の抱え込みのほぼ全量）を捕まえる。
    6 にすると期間Aの発火が 53 に増えるが期間Bの捕捉は 46 と少ししか増えない。10 以上は期間Bの捕捉がほぼ変わらず遅れるだけ。
"""
import json
import os
import re
import sys
import time

NUDGE_AFTER = int(os.environ.get("DELEGATION_NUDGE_AFTER", "8") or 8)
WORK = {"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"}
BROWSER = ("claude-in-chrome", "Claude_Browser", "computer-use", "Control_Chrome")
EXEMPT = re.compile(r"workspace/tickets/|owner-tasks\.md|handover\.md|notion", re.I)
READONLY = re.compile(
    r"^\s*(?:cd [^;&|]+(?:&&|;)\s*)?"
    r"(?:cat|ls|head|tail|sed -n|grep|rg|find|wc|stat|date|echo|pwd|which|"
    r"git (?:log|status|diff|show|branch|rev-parse|ls-files))\b")

# 担当の推定（delegation-check.sh と同じ地図。作業の中身＝コマンド・パス・本文の頭から当てる）
DOMAINS = [
    ("サトル（リサーチャー）", "researcher",
     r"調べ|調査|リサーチ|市場|競合|相場|情報収集|一次情報|事例|keepa|netsea|superdelivery|exa|WebFetch|WebSearch"),
    ("タケシ（プランナー）", "planner", r"戦略|方針|計画|ロードマップ|差別化|撤退条件|積み上げ"),
    ("ハジメ（経理）", "accounting",
     r"収支|利益|粗利|原価|採算|手数料|予算|資金|損益|試算|profit|fba_cost|consistency\.py"),
    ("ハルオ（法務）", "legal", r"規約|契約|法務|コンプラ|違反|許可|PSE|薬機|景表法|ToS"),
    ("マリエ（庶務）", "general-affairs", r"整理|アーカイブ|_inbox|カタログ|catalog|台帳|ledger|シート|gspread|sheet"),
    ("ヒデアキ（コンテンツ制作）", "content-creator",
     r"deliverables/.*\.(?:md|html)|文章|資料|スライド|マニュアル|打診文|下書き|推敲|報告書"),
    ("タカシ（IT エンジニア）", "it-engineer",
     r"\.py\b|\.sh\b|scripts/|\.claude/hooks|settings\.json|launchd|pytest|python3 [^-]|node |npm "),
]


def is_browser(name):
    return any(k in name for k in BROWSER)


def classify(name, ti):
    if name in ("Agent", "Task"):
        return "agent"
    if is_browser(name):
        return "work"
    if name not in WORK:
        return None
    blob = json.dumps(ti, ensure_ascii=False)
    if EXEMPT.search(blob):
        return None
    if name == "Bash" and READONLY.match(ti.get("command", "") or ""):
        return None
    return "work"


def evidence(name, ti):
    """担当推定の材料（短く）。本文は頭だけ見る。"""
    parts = [name, ti.get("command", ""), ti.get("file_path", ""), ti.get("url", ""),
             (ti.get("content", "") or "")[:300], (ti.get("new_string", "") or "")[:300],
             ti.get("description", "")]
    return " ".join(p for p in parts if isinstance(p, str))[:800]


def guess(texts):
    blob = "\n".join(texts)
    scores = []
    for label, sub, pat in DOMAINS:
        n = len(re.findall(pat, blob, re.I))
        if n:
            scores.append((n, label, sub))
    scores.sort(reverse=True)
    return [(label, sub) for _, label, sub in scores[:3]]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    # サブエージェントの作業は数えない（メインのフックとして呼ばれたときだけ働く）
    if data.get("agent_id"):
        return 0
    name = data.get("tool_name", "") or ""
    ti = data.get("tool_input") or {}
    kind = classify(name, ti)
    if kind is None:
        return 0

    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or "nosession"))[:64]
    turn = str(data.get("prompt_id") or "")
    tmp = os.environ.get("TMPDIR") or "/tmp"
    path = os.path.join(tmp, f"claude-work-nodelegate-{session}.json")
    now = time.time()
    try:
        st = json.load(open(path, encoding="utf-8"))
    except Exception:
        st = {}
    # 新しいターン（prompt_id が変わった。無い環境では30分の空白）で数え直し
    if st.get("turn") != turn or (not turn and now - st.get("ts", 0) > 1800):
        st = {"turn": turn, "count": 0, "next": NUDGE_AFTER, "ev": []}
    st["ts"] = now

    if kind == "agent":
        st.update(count=0, next=NUDGE_AFTER, ev=[])
        msg = ""
    else:
        st["count"] += 1
        st["ev"] = (st.get("ev") or [])[-(NUDGE_AFTER * 2):] + [evidence(name, ti)]
        msg = ""
        if st["count"] >= st.get("next", NUDGE_AFTER):
            st["next"] = st["count"] + NUDGE_AFTER
            cands = guess(st["ev"])
            cand = "、".join(f"{l} → subagent_type: {s}" for l, s in cands) or "（作業の中身から特定できず。§A2 の表で決める）"
            msg = (
                f"【委譲チェック（作業中）】このターンで担当に振らずに作業が {st['count']} 手続いています"
                f"（Bash・Edit・Write・ブラウザ。チケット・owner-tasks・Notion・読むだけのコマンドは数えていません）。\n"
                f"担当候補: {cand}\n"
                "続ける前に「この作業は〔担当〕です（理由）」と1行で宣言し、Agent ツールで**実発注**してください（CLAUDE.md §A2）。"
                "ブラウザで画面を見ること自体は秘書の仕事ですが、途中で出てきた調査・計算・台帳整備・文章作りは担当に振ります。\n"
                "秘書が自分でやってよいのは、社長との対話・統合と品質確認・チケット操作・1手の事実確認だけです。"
                "それに当たると判断したなら、理由を一言書いて続けて構いません。"
            )
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False)
    except Exception:
        pass
    if msg:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": msg}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # 壊れても作業を止めない
