#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — 仕入れ前チェックが埋まっていない発注案を書かせない。

背景: 2026-10-04（T-20261004-001）。CLAUDE.md §3.3／§3.5 に「Amazon 本体がいる棚は買わない」
      「仕入れ前に出品制限を確認する」と書いてあるのに、同日の成果物36 で蛍光灯 B008FIPMP2 の
      ゲートが「要確認」のまま推奨に入り、売価も90日中央値ではなく現在価格だった。
      9/30 には実際に、本体がカートを持ち申請経路も閉じた鍋を12点発注している。
      文章のルールは発注案を作る瞬間に照合されないので、機械で止める。

対象: 発注案ファイル（workspace/output/ 配下でパスに「発注」「order_proposal」を含む文書、
      または本文に `<!-- order-asins: ... -->` マーカーがある文書。.md/.html/.csv/.tsv/.txt）。
      それ以外は素通り。
止める条件:
  - マーカーが無い（どの ASIN を発注するのか機械が読めない）
  - マーカーの ASIN が1つでも、checklist_spec.json の必須項目を満たさない
    （欠落・FAIL・UNKNOWN・期限切れ）
  - 発注する ASIN を含む表の行に「要確認／未確認／UNKNOWN／不明」が残っている
Edit/MultiEdit は**書き換え後の全文**で判定する。
判定本体: scripts/sourcing_gate/gate.py（pre-commit と write_order_proposal.py も同じものを使う）
解除: 抜け道は用意しない。check_record.py set で確認結果を記録すれば通る。
"""
import json
import os
import re
import sys
from pathlib import Path

# 判定モジュールはこのフックと同じリポにある（テストで CLAUDE_PROJECT_DIR を差し替えても、
# 部品はこちらを使う。spec と記録の場所は gate 側が CLAUDE_PROJECT_DIR から解決する）。
GATE_DIR = Path(__file__).resolve().parents[2] / "scripts" / "sourcing_gate"


def full_text_after(tool: str, ti: dict) -> str:
    """ツール実行後のファイル全文を組み立てる。"""
    if tool == "Write":
        return ti.get("content", "") or ""
    fp = ti.get("file_path") or ""
    try:
        text = Path(fp).read_text(encoding="utf-8")
    except Exception:
        text = ""
    edits = ti.get("edits") if tool == "MultiEdit" else [ti]
    for e in edits or []:
        old, new = e.get("old_string", ""), e.get("new_string", "") or ""
        if not old or old not in text:
            continue   # ツール側で失敗する。ここでは判定に影響させない
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    if not text:  # 新規ファイルへの Edit 等
        text = "\n".join((e.get("new_string") or "") for e in (edits or []))
    return text


def looks_like_order(fp: str) -> bool:
    """gate が読めないとき用の最小判定（fail-closed の範囲を絞るため）。"""
    p = fp.replace("\\", "/")
    p = re.sub(r"^.*/\.claude/worktrees/[^/]+/", "", p)
    return ("workspace/output/" in p and ("発注" in p or "order_proposal" in p)
            and p.lower().endswith((".md", ".html", ".htm", ".csv", ".tsv", ".txt")))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0
    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    if not fp:
        return 0

    try:
        sys.path.insert(0, str(GATE_DIR))
        import gate  # noqa: E402
    except Exception as e:
        if looks_like_order(fp):
            sys.stderr.write(f"\n🛑 発注ゲート — 判定モジュールが読めないため発注案を書けません（{e}）。\n"
                             f"   {GATE_DIR}/gate.py を確認してください。\n")
            return 2
        return 0

    text = full_text_after(tool, ti)
    if not gate.is_order_proposal(fp, text):
        return 0
    msgs = gate.check_document(fp, text)
    if not msgs:
        return 0

    out = ["", "🛑 発注ゲート — 仕入れ前チェック（CLAUDE.md §3.5）が埋まっていない発注案です。", "",
           f"  ファイル: {fp}", ""]
    out += ["  " + m for m in msgs]
    out += ["",
            "対応:",
            "  1. 足りない項目を実画面・データで確認する（取り方: python3 scripts/sourcing_gate/check_record.py items）",
            "  2. 確認結果を記録する:",
            "       python3 scripts/sourcing_gate/check_record.py set <ASIN> <項目id> \\",
            "         --value \"…\" --result PASS|FAIL|UNKNOWN --source \"<画面URL/データ源>\" --by <確認者>",
            "  3. python3 scripts/sourcing_gate/check_record.py verify <ASIN>... が OK になってから書き直す",
            "  ※ FAIL／UNKNOWN の ASIN は発注案から外す（マーカーからも外す）。",
            "",
            "※ 2026-10-04 新設（T-20261004-001）。9/30 の鍋の誤発注と、10/4 成果物36 の「ゲート要確認のまま推奨」を受けて。",
            ""]
    sys.stderr.write("\n".join(out))
    return 2


if __name__ == "__main__":
    sys.exit(main())
