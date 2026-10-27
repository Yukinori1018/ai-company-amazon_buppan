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
    # フックとそのテストは、止めるべき文例そのものを書く場所（source-terms-guard と同じ扱い）
    if "/.claude/hooks/" in fp.replace(os.sep, "/"):
        return 0
    # CSV はメーカー・商品のデータ行であって「当社は〜」という主張を書く場所ではない
    # （2026-10-27：残った誤検知の大半が連絡先 CSV の「会社概要なし」「独自ドメインなし」＝相手の話）
    if fp.lower().endswith((".csv", ".tsv", ".jsonl", ".json")):
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

    # ★ 2026-10-27（T-20261027-001）に判定を締め直した。
    #   このフックは 8/21〜10/27 のあいだ settings.json の引用符の欠落で一度も動いておらず、
    #   旧判定（キーの前後60字のどこかに「なし」「無い」等）を直近の実ファイル492本に当てると
    #   156本（32%）を止めた。ほぼ全部が誤検知だった：
    #     「NETSEA に1件も存在せず…」「キーゾン表示なし」「製品サイトに会社概要が無い」（＝メーカーの話）
    #     「ロゴス(LOGOS)…」（キー「ロゴ」の部分一致）
    #   守りたいのは「当社は X を持っていない」という主張だけなので、次の3点で絞る。
    #   1. 否定はキーの**直後**（助詞と副詞を挟んで12字以内・句読点をまたがない）に限る
    #      「なし／無い／ありません」のような弱い否定は、キー＋助詞の直後のときだけ
    #   2. キーの直前に第三者を指す語（メーカー・同社・先方・公式・楽天…）があれば当社の話ではない
    #   3. キーが別の語の一部なら数えない（ロゴ→ロゴス、HP→HPLC、Exa→Example）
    #   9/21 の元の事故文（「独自ドメインなし・HPなし・会社概要なし」「キーゾンは導入していません」）は
    #   引き続き止まる（tests/test_forgetting_hooks.sh と下の自己テストで確認）。
    STRONG = (r"(?:持って(?:い)?(?:ません|ない)|未整備|未保有|未提出|未取得|未契約|未導入|未登録|未開設|"
              r"用意が必要|用意する必要|揃って(?:いません|いない)|整えて(?:いません|いない)|"
              r"(?:導入|契約|取得|保有|用意|準備|開設|登録|作成|申込|加入|提出)(?:は|も)?"
              r"(?:して)?(?:いません|いない|済みでない|済みではない|できていない|できていません))")
    WEAK = r"(?:なし|無し|無い|ない|ありません|がない|もない)"
    PARTICLE = r"(?:は|が|も|を|の用意が|がまだ|はまだ|もまだ)?"
    # キーの直後: 助詞・副詞（まだ・特に・一切 等）を挟んで STRONG、または助詞だけ挟んで WEAK
    AFTER = re.compile(r"^\s*(?:" + PARTICLE + r"[^\n。、，,．.・／/|（）()]{0,8}?" + STRONG
                       + r"|" + PARTICLE + r"\s*" + WEAK + r"(?!\s*(?:メーカー|会社|企業|店|社|先|場合|ところ|ケース|[）)]?\s*でも|[）)]?\s*で(?:可|OK|出店|登録))))")
    # ↑「HPがないメーカー」「会社概要が無い場合は」は相手の話なので止めない
    THIRD = re.compile(r"(?:メーカー|同社|先方|相手|各社|社の|店の|サプライヤー|出品者|出展社|製品サイト|"
                       r"公式|楽天|仕入れ?先|卸|ブランド|ショップ|取引先|競合|他社)[^。\n]{0,10}$")

    def is_word_edge(key, before, after):
        """キーが別の語の一部でないか。カタカナ/英字のキーは同じ文字種が続けば別の語。"""
        if re.match(r"[A-Za-z]", key[-1]) and re.match(r"[A-Za-z]", after[:1] or " "):
            return False
        if re.match(r"[A-Za-z]", key[0]) and re.match(r"[A-Za-z]", before[-1:] or " "):
            return False
        if re.match(r"[ァ-ヶー]", key[-1]) and re.match(r"[ァ-ヶー]", after[:1] or " "):
            return False
        return True

    hits = []
    for key, state, src in assets:
        for m in re.finditer(re.escape(key), text):
            before = text[max(0, m.start() - 30): m.start()]
            after = text[m.end(): m.end() + 40]
            if not is_word_edge(key, before, after):
                continue
            if THIRD.search(before.split("\n")[-1]):
                continue
            if after.startswith("ページ"):   # 「会社概要ページ未取得」＝相手のサイトを取っていない話
                continue
            if AFTER.search(after):
                window = text[max(0, m.start() - 30): m.end() + 40]
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
