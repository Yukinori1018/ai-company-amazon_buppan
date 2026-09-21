#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — 保有済み資産を「持っていない」と書くのを止める。

背景: 2026-09-21、書籍のチェックリストを当社に当てはめる際に done チケットと成果物を
      検索せず「独自ドメインなし・HPなし・会社概要なし」と報告した（実際は全部保有）。
      同型の事故が3回目で、memory への記録だけでは止まらなかったため機構化した。
参照: workspace/asset-ledger.md の `ASSET:` 行のみ。
解除: 本当に手放したのなら、先に台帳を更新すれば通る。
"""
import json, os, re, sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
LEDGER = os.path.join(ROOT, "workspace", "asset-ledger.md")

def main():
    if not os.path.exists(LEDGER):
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    ti = payload.get("tool_input") or {}
    parts = [ti.get("content", ""), ti.get("new_string", "")]
    for e in (ti.get("edits") or []):
        parts.append(e.get("new_string", ""))
    text = "\n".join(p for p in parts if isinstance(p, str))
    if not text.strip():
        return 0

    # 台帳そのものの編集は対象外（更新できなくなるため）
    fp = (ti.get("file_path") or "")
    if fp.endswith("asset-ledger.md") or fp.endswith("asset-claim-guard.py"):
        return 0

    HELD = ("保有", "契約中", "登録済", "提出済", "通過済")
    assets = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("ASSET:"):
                continue
            cols = [c.strip() for c in line[len("ASSET:"):].split("|")]
            if len(cols) >= 2 and cols[1].startswith(HELD):
                assets.append((cols[0], cols[1], cols[2] if len(cols) > 2 else ""))

    # 「〜していません/していない」系を必ず含めること。2026-09-21、キーゾンで
    # 「導入していません」が素通りする抜けを実テストで検出した。
    GAP = (r"(持って(?:い)?(?:ません|ない)|未整備|未保有|未取得|未契約|未導入|未登録|未開設|"
           r"ありません|無い|なし|ゼロから|用意が必要|用意する必要|必要があります|"
           r"揃って(?:いません|いない)|整えて(?:いません|いない)|欠けて|"
           r"(?:導入|契約|取得|保有|用意|準備|開設|登録|作成|申込|加入)(?:は|も)?"
           r"(?:して)?(?:いません|いない|済みでない|済みではない|できていない|できていません))")

    hits = []
    for key, state, src in assets:
        for m in re.finditer(re.escape(key), text):
            window = text[max(0, m.start() - 60): m.end() + 60]
            if re.search(GAP, window):
                hits.append((key, state, src, " ".join(window.split())))
                break
    if not hits:
        return 0

    out = ["", "🛑 資産台帳ガード — 「当社は持っていない」と書こうとしています。台帳では保有済みです。", ""]
    for key, state, src, window in hits:
        out.append(f"  ● {key}")
        out.append(f"      台帳: {state}" + (f"（根拠 {src}）" if src else ""))
        out.append(f"      書こうとした箇所: …{window}…")
        out.append("")
    out += ["対応:",
            "  1. workspace/asset-ledger.md を読み、実際の保有状態を確認する",
            "  2. 記述を事実に直す（多くは外部のチェックリストを検索せずに当てはめている）",
            "  3. 本当に手放した/失効したのなら、先に台帳を更新してから書き直す",
            "",
            "※ 2026-09-21、同型の事故が3回目だったため新設。memory への記録だけでは止まらなかった。",
            ""]
    sys.stderr.write("\n".join(out))
    return 2

if __name__ == "__main__":
    sys.exit(main())
