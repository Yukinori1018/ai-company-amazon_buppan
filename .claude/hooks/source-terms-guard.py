#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — 会員限定の取引条件を PUBLIC リポへ書くのを止める。

背景: 2026-09-21、SD（会員限定卸）の卸値・送料無料ライン・決済手数料が成果物に書かれたまま
      push された。3チケット・15ファイルに広がるまで誰も気づかず、伏せ字化の1回目も
      不完全だった（漢数字表記の送料ライン・4列の卸値分布表・地の文の中央値が残存）。
      人の注意力では止まらないと確定したので機構にした。
仕様: workspace/output/deliverables/T-20260920-003/16_公開リポに残る取引条件の公開可否_法務判定.md §5 対策2
      （法務ハルオ 2026-09-21）。除外条件もこの判定書に仕様として書かれている。
参照: workspace/source-ledger.md の `SOURCE:` 行のみ。

思想:
  - **ラベル＋数値の共起だけを見る。** 数字が付かない議論（「卸値が高い」「卸率で判断する」）は通す。
  - **率（%）は通し、実額を止める。** 法務の判断は「卸率55%以下が何点、という形なら可」。
  - **実額の正しい置き場は workspace/output/agent_output/**（.gitignore 対象）。だから対象は
    deliverables と tickets（どちらも Git 追跡＝公開）だけに絞ってある。
  - **バイパス手段はメッセージに書かない。** 書けば常態化する（法務判定 §5）。
    正当な公開ページ由来の金額には、台帳経由の出口が1つだけ用意してある。
"""
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
LEDGER = os.path.join(ROOT, "workspace", "source-ledger.md")
VERDICT = ("workspace/output/deliverables/T-20260920-003/"
           "16_公開リポに残る取引条件の公開可否_法務判定.md")

# 対象パス。agent_output は実額の正しい退避先なので**入れない**。
WATCHED = ("workspace/output/deliverables/", "workspace/tickets/")

# 除外パス。法務の判定書・基準書は検知語そのものを引用するが金額は書かない運用。
SKIP_PATH = ("workspace/output/agent_output/", "agents/legal/",
             ".claude/hooks/", "workspace/source-ledger.md")
SKIP_NAME = ("法務判定", "公開基準", "source-terms-guard", "source-ledger")

# --- 検知パターン ------------------------------------------------------------
# ラベル: 会員限定の取引条件を指す語だけ。Amazon の売価・販売手数料・FBA 手数料・
# 自社の外注費はここに無いので、自然に素通りする（＝落としてはいけないものを落とさない）。
# 「卸率」は率のままなら可なので、`卸率…実額` の形のときだけラベルになる。
LABEL = (r"(?:卸値|卸価格|卸単価|下代|上代|仕入単価|仕入値|仕入れ値|"
         r"卸率[^\n]{0,4}実額|掛け率|"
         r"最小ロット|最低ロット|最小発注|最低発注|発注ロット|ロット数|ミニマム|"
         r"送料無料ライン|代引手数料|決済手数料|振込手数料|"
         r"SD ?品番|gradual_border_price|apply_type|wholesale_price)")

# 数値: 算用数字（カンマ有無）・全角・漢数字・「◯万」の混在表記まで拾う。
# 2026-09-21 の漏れは「二万円」「2万円」を拾えなかったことが直接の原因。
NUM = r"(?:[0-9０-９][0-9,，０-９.．]*|[一二三四五六七八九十百千]+)\s*(?:万)?"
MONEY = r"(?:[0-9０-９][0-9,，０-９.．]*|[一二三四五六七八九十百千]+)\s*(?:万)?\s*円"

RE_LABEL_NUM = re.compile(LABEL + r"[^\n]{0,15}?(" + NUM + r")")
# 「◯◯円以上で送料無料」の形。ラベルが後ろに来るのでこれだけ別建て。
RE_FREE_SHIP = re.compile(MONEY + r"[^\n]{0,12}?(?:送料|配送料)[^\n]{0,6}?無料")
RE_LABEL_ONLY = re.compile(LABEL)

# 伏せ字済み・注記済みの行は数えない（保護効果ゼロの印を出さないため）。
RE_SAFE = re.compile(r"非公開|非掲載|伏せ|〔|規約上の理由でリポジトリから除外|マスク|<!-- *public-source:")
# 件数は取引条件ではない（ASIN 数・バリエーション数・商標の保有件数）。
RE_COUNT_UNIT = re.compile(r"^\s*(?:件|社|名|商標|ASIN)")
RE_PUBLIC_SRC = re.compile(r"<!-- *public-source: *https?://([^/\s]+)[^>]*verified: *\d{4}-\d{2}-\d{2} *-->")
# 表のセル: 数字だけ（3桁以上か「◯万」）のセルを実額とみなす。率（%）と小さな数（件数）は除く。
RE_NUM_CELL = re.compile(r"^[¥￥]?(?:[0-9０-９][0-9,，０-９.．]{2,}|[0-9０-９一二三四五六七八九十百千]+\s*万)"
                         r"\s*(?:円|円台)?$")
RE_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


def public_hosts():
    """出所台帳の「公開」区分のホスト名。ここに載っているホストだけが出口を使える。"""
    hosts = set()
    if not os.path.exists(LEDGER):
        return hosts
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("SOURCE:"):
                    continue
                cols = [c.strip() for c in line[len("SOURCE:"):].split("|")]
                if len(cols) >= 2 and cols[1].startswith("公開"):
                    hosts.add(cols[0].lower())
    except OSError:
        pass
    return hosts


def member_only_lines():
    """止めたときに出す「会員限定」区分の台帳行。"""
    out = []
    if not os.path.exists(LEDGER):
        return out
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                if line.startswith("SOURCE:") and "会員限定" in line:
                    out.append(line.rstrip())
    except OSError:
        pass
    return out


def code_spans(line):
    """`…` で囲まれた範囲。検索語そのものを code 引用している箇所は検知しない。"""
    return [(m.start(), m.end()) for m in re.finditer(r"`[^`\n]*`", line)]


def in_code(line, pos):
    return any(s <= pos < e for s, e in code_spans(line))


def has_public_source(lines, i, hosts):
    """直前3行以内に public-source 注記があり、ホストが台帳の「公開」区分か。"""
    for j in range(max(0, i - 3), i + 1):
        m = RE_PUBLIC_SRC.search(lines[j])
        if m and m.group(1).lower() in hosts:
            return True
    return False


def numeric_cells(line):
    """markdown の表行／HTML の <td> から、実額らしいセルを数える。"""
    cells = []
    s = line.strip()
    if s.startswith("|"):
        cells = [c.strip() for c in s.strip("|").split("|")]
    elif RE_TD.search(line):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in RE_TD.findall(line)]
    return [c for c in cells if RE_NUM_CELL.match(c)]


def scan(text, hosts):
    """検知した (行番号, 理由, 行の抜粋) を返す。"""
    lines = text.split("\n")
    hits = []
    for i, line in enumerate(lines):
        if RE_SAFE.search(line) or has_public_source(lines, i, hosts):
            continue

        reason = None
        m = RE_LABEL_NUM.search(line)
        if m and not in_code(line, m.start()):
            tail = line[m.end():]
            if not RE_COUNT_UNIT.match(tail):     # 「3件」「10社」は件数であって取引条件ではない
                reason = "取引条件のラベルの直後に実額があります"
        if reason is None and RE_FREE_SHIP.search(line):
            reason = "送料無料ラインの実額があります"
        if reason is None:
            cells = numeric_cells(line)
            if len(cells) >= 2:
                # 表の中・ヘッダ・直前5行のどこかにラベルがあれば、その表は取引条件の表。
                ctx = "\n".join(lines[max(0, i - 5): i + 1])
                if RE_LABEL_ONLY.search(ctx):
                    reason = "取引条件の表に実額のセルが並んでいます（%s）" % " / ".join(cells[:4])
        if reason:
            hits.append((i + 1, reason, " ".join(line.split())[:120]))
    return hits


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    ti = payload.get("tool_input") or {}
    fp = (ti.get("file_path") or "").replace(os.sep, "/")
    rel = fp[len(ROOT) + 1:] if fp.startswith(ROOT + "/") else fp
    if not any(w in rel for w in WATCHED):
        return 0
    if any(s in rel for s in SKIP_PATH) or any(s in os.path.basename(rel) for s in SKIP_NAME):
        return 0

    parts = [ti.get("content", ""), ti.get("new_string", "")]
    for e in (ti.get("edits") or []):
        parts.append(e.get("new_string", ""))
    text = "\n".join(p for p in parts if isinstance(p, str))
    if not text.strip():
        return 0

    hits = scan(text, public_hosts())
    if not hits:
        return 0

    out = ["", "🛑 出所ガード — 会員限定の取引条件を PUBLIC リポに書こうとしています。", "",
           f"  ファイル: {rel}", ""]
    for lineno, reason, excerpt in hits[:10]:
        out.append(f"  ● 書き込み{lineno}行目: {reason}")
        out.append(f"      …{excerpt}…")
        out.append("")
    if len(hits) > 10:
        out.append(f"  （ほか {len(hits) - 10} 件）")
        out.append("")

    ledger = member_only_lines()
    if ledger:
        out.append("出所台帳（workspace/source-ledger.md）— 会員限定の出所:")
        out += [f"  {line}" for line in ledger]
        out.append("")

    out += ["対応:",
            "  1. 実額は workspace/output/agent_output/<ticket_id>/ に置く（.gitignore 対象＝公開されない）",
            "  2. 成果物には結論と率だけ書く",
            "       例: 「卸率55%以下が12点／全40点」「境目を越えると送料無料。値は非公開（出所の規約による）」",
            "  3. 出所が公開ページなら、workspace/source-ledger.md の「公開」区分に載せたうえで",
            "     金額の直前3行以内に <!-- public-source: https://ホスト/... verified:YYYY-MM-DD --> を書く",
            "",
            f"法務判定: {VERDICT}",
            "※ 2026-09-21、伏せ字化の1回目が不完全（漢数字の送料ライン・4列の分布表・地の文の中央値が残存）",
            "   だったため新設。人の注意力に置かない。",
            ""]
    sys.stderr.write("\n".join(out))
    return 2


if __name__ == "__main__":
    sys.exit(main())
