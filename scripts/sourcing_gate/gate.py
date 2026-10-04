#!/usr/bin/env python3
"""仕入れ前チェックの判定（発注ゲート）— フック・スクリプト・pre-commit の共通部品。

背景（T-20261004-001 / 2026-10-04）
  ナレッジ（「Amazon 本体がいる棚は買わない」「仕入れ前に出品制限を確認する」）は
  CLAUDE.md §3.3／§3.5 に文章で書いてあるのに、発注案を作る瞬間に照合する仕組みが
  無かった。その日の成果物36 でも、蛍光灯 B008FIPMP2 のゲートが「要確認」のまま推奨に入り、
  売価は90日中央値ではなく現在価格だった。**文章ではなく機械で止める**ためのモジュール。

判定ルール（これ以上のことはしない）
  発注可 ＝ checklist_spec.json の required 全項目について
           記録が存在し、result が PASS で、checked_at が max_age_days 以内。
  それ以外（欠落・FAIL・UNKNOWN・期限切れ・値が「要確認」等）はすべて不可。
  閾値はコードに持たない。項目も日数も spec が正。

置き場
  spec    : <repo>/scripts/sourcing_gate/checklist_spec.json（Git 追跡）
  記録    : <main worktree>/workspace/output/agent_output/_sourcing_checks/<ASIN>.json
            （.gitignore 済み＝卸値など会員限定情報を書いてよい。PUBLIC リポには出ない）
            ★ worktree ごとに agent_output が分かれるので、記録は **メインの作業ツリー** に
              1か所だけ置く。どの worktree から見ても同じ記録を読む。
  上書き  : 環境変数 SOURCING_SPEC / SOURCING_CHECKS_DIR（テスト用）

CLI
  python3 gate.py check-file <path> [--stdin]   発注案ファイルを判定（pre-commit 用）
                                                exit 0=通す / 1=止める
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

HERE = Path(__file__).resolve().parent
RESULTS = ("PASS", "FAIL", "UNKNOWN")
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")

# 発注案の印。<!-- order-asins: B0XXXXXXXX, B0YYYYYYYY -->
MARKER_RE = re.compile(r"<!--\s*order-asins\s*:(.*?)-->", re.S)
# 「まだ決まっていない」を表す語。表の行・値に残っていたら発注させない。
UNRESOLVED_RE = re.compile(r"要確認|未確認|UNKNOWN|不明", re.I)
# パスでの発注案判定に使う語（「発注案」「発注」は「発注」で両方拾える）
PATH_WORDS = ("発注", "order_proposal")
DOC_EXT = (".md", ".html", ".htm", ".csv", ".tsv", ".txt")


# ---------------------------------------------------------------- 置き場の解決
def repo_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else HERE.parent.parent


def main_worktree_root(root: Path) -> Path:
    """worktree から見ても、メインの作業ツリーの根を返す（git が使えなければ root）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            common = Path(out.stdout.strip())
            if common.name == ".git":
                return common.parent
    except Exception:
        pass
    return root


def spec_path() -> Path:
    env = os.environ.get("SOURCING_SPEC")
    return Path(env) if env else repo_root() / "scripts/sourcing_gate/checklist_spec.json"


def checks_dir() -> Path:
    env = os.environ.get("SOURCING_CHECKS_DIR")
    if env:
        return Path(env)
    return (main_worktree_root(repo_root())
            / "workspace/output/agent_output/_sourcing_checks")


# ---------------------------------------------------------------- spec / 記録
def load_spec(path: Optional[Path] = None) -> List[dict]:
    """spec の items を返す。壊れていたら例外（呼び出し側で fail-closed にする）。"""
    p = path or spec_path()
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    items = data["items"]
    ids = [it["id"] for it in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"spec に重複した id があります: {ids}")
    return items


def normalize_asin(asin: str) -> str:
    a = (asin or "").strip().upper()
    if not ASIN_RE.match(a):
        raise ValueError(f"ASIN の形ではありません: {asin!r}（英大文字・数字10桁）")
    return a


def record_path(asin: str) -> Path:
    return checks_dir() / f"{normalize_asin(asin)}.json"


def load_record(asin: str) -> dict:
    p = record_path(asin)
    if not p.exists():
        return {"asin": normalize_asin(asin), "items": {}, "history": []}
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 判定
@dataclass
class Problem:
    item_id: str
    name: str
    reason: str          # 欠落 / FAIL / UNKNOWN / 期限切れ / 値が未確認 / 日付不正
    detail: str = ""


@dataclass
class GateResult:
    asin: str
    problems: List[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _parse_day(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def evaluate(asin: str, today: Optional[date] = None,
             spec: Optional[List[dict]] = None) -> GateResult:
    """1 ASIN を spec の全 required 項目で判定する。"""
    today = today or date.today()
    spec = spec if spec is not None else load_spec()
    try:
        a = normalize_asin(asin)
    except ValueError as e:
        return GateResult(asin, [Problem("-", "ASIN", "ASIN不正", str(e))])
    try:
        rec = load_record(a)
    except Exception as e:  # 記録ファイルが壊れている＝確認していないのと同じ
        return GateResult(a, [Problem("-", "記録ファイル", "読めない", str(e))])
    items = rec.get("items") or {}
    res = GateResult(a)
    for it in spec:
        if not it.get("required", True):
            continue
        iid, name = it["id"], it["name"]
        e = items.get(iid)
        if not e:
            res.problems.append(Problem(iid, name, "欠落"))   # 取り方は `check_record.py items`
            continue
        result = str(e.get("result", "")).upper()
        if result != "PASS":
            reason = result if result in ("FAIL", "UNKNOWN") else f"result不正({result or '空'})"
            res.problems.append(Problem(iid, name, reason, str(e.get("value", ""))))
            continue
        if UNRESOLVED_RE.search(str(e.get("value", ""))):
            res.problems.append(Problem(iid, name, "値が未確認",
                                        f"PASS なのに値が「{e.get('value')}」"))
            continue
        d = _parse_day(e.get("checked_at", ""))
        if d is None or d > today:
            res.problems.append(Problem(iid, name, "日付不正",
                                        f"checked_at={e.get('checked_at')!r}"))
            continue
        age = (today - d).days
        max_age = int(it.get("max_age_days", 0))
        if age > max_age:
            res.problems.append(Problem(iid, name, "期限切れ",
                                        f"{d.isoformat()} 確認・{age}日経過（上限 {max_age}日）"))
    return res


# ---------------------------------------------------------------- 発注案の文書
def norm_path(path: str) -> str:
    return (path or "").replace("\\", "/")


def rel_path(path: str) -> str:
    """リポ根からの相対パスにする。worktree（.claude/worktrees/<名前>/）の接頭辞も外す。

    ★ worktree の絶対パスには `/.claude/` が含まれるので、相対化せずに除外判定すると
      worktree で書いた発注案が丸ごと素通りする。
    """
    p = norm_path(path)
    m = re.search(r"/\.claude/worktrees/[^/]+/(.*)$", p)
    if m:
        return m.group(1)
    root = norm_path(str(repo_root())).rstrip("/") + "/"
    if p.startswith(root):
        return p[len(root):]
    return p


def is_excluded_path(path: str) -> bool:
    """ゲートの部品・説明書・人格ファイルは対象外（自分で自分を止めないため）。"""
    p = rel_path(path)
    return p.startswith((".claude/", "scripts/sourcing_gate/", "agents/")) \
        or p == "CLAUDE.md"


def is_doc(path: str) -> bool:
    return norm_path(path).lower().endswith(DOC_EXT)


def path_says_order(path: str) -> bool:
    """workspace/output/ 配下で、パスに「発注」「order_proposal」を含む文書。"""
    p = rel_path(path)
    return p.startswith("workspace/output/") and any(w in p for w in PATH_WORDS)


def is_order_proposal(path: str, text: str) -> bool:
    if is_excluded_path(path) or not is_doc(path):
        return False
    return path_says_order(path) or bool(MARKER_RE.search(text or ""))


def extract_order_asins(text: str) -> Optional[List[str]]:
    """マーカーの ASIN を返す。マーカーが無ければ None、あるが空なら []。"""
    ms = MARKER_RE.findall(text or "")
    if not ms:
        return None
    out: List[str] = []
    for body in ms:
        for tok in re.split(r"[\s,，、]+", body.strip()):
            if tok and tok.upper() not in out:
                out.append(tok.upper())
    return out


def unresolved_rows(path: str, text: str, asins: Iterable[str]) -> List[str]:
    """発注する ASIN を含む表の行に「要確認／未確認／UNKNOWN／不明」が残っていれば返す。

    表の行 = .md は `|` で始まる行、.html は `</tr>` で区切った <td> を含む塊、
    .csv/.tsv/.txt は全行。地の文の注意書きは止めない（そこに書くのは正当）。
    """
    asins = [a for a in asins if a]
    if not asins:
        return []
    low = norm_path(path).lower()
    if low.endswith((".html", ".htm")):
        chunks = [c for c in re.split(r"</tr\s*>", text, flags=re.I) if "<td" in c.lower()]
    elif low.endswith(".md"):
        chunks = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    else:
        chunks = text.splitlines()
    hits = []
    for c in chunks:
        if any(a in c.upper() for a in asins) and UNRESOLVED_RE.search(c):
            hits.append(" ".join(re.sub(r"<[^>]+>", " ", c).split())[:200])
    return hits


def set_command(asin: str, item_id: str) -> str:
    return (f"python3 scripts/sourcing_gate/check_record.py set {asin} {item_id} "
            f"--value \"…\" --result PASS --source \"<画面URL/データ源>\" --by <確認者>")


def check_document(path: str, text: str, today: Optional[date] = None) -> List[str]:
    """発注案の文書を判定し、止める理由の行リストを返す（空なら通す）。

    発注案でなければ常に空。spec が読めない等で判定できなければ止める（fail-closed）。
    """
    if not is_order_proposal(path, text):
        return []
    msgs: List[str] = []
    asins = extract_order_asins(text)
    if asins is None:
        return ["発注案に `<!-- order-asins: B0XXXXXXXX, B0YYYYYYYY -->` のマーカーがありません。",
                "  どの ASIN を発注するのか機械が読めないので、照合できません。",
                "  発注する ASIN をすべてマーカーに書いてください。"]
    if not asins:
        return ["`order-asins` マーカーに ASIN が1つもありません。"]
    try:
        spec = load_spec()
    except Exception as e:
        return [f"チェックリスト定義が読めないため判定できません（{spec_path()}: {e}）。"]

    for a in asins:
        r = evaluate(a, today=today, spec=spec)
        if r.ok:
            continue
        msgs.append(f"● {r.asin} — {len(r.problems)}項目が未充足")
        for p in r.problems:
            msgs.append(f"    - [{p.item_id}] {p.name}: {p.reason}"
                        + (f"（{p.detail}）" if p.detail else ""))
        first = next((p.item_id for p in r.problems if p.item_id != "-"), None)
        if first:
            msgs.append(f"    記録のしかた: {set_command(r.asin, first)}")
    rows = unresolved_rows(path, text, asins)
    if rows:
        msgs.append("● 発注表の行に「要確認／未確認／UNKNOWN／不明」が残っています:")
        msgs += [f"    {h}" for h in rows]
    return msgs


# ---------------------------------------------------------------- CLI（pre-commit 用）
def _cli(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] == "check-file":
        path = argv[1]
        if "--stdin" in argv:
            text = sys.stdin.read()
        else:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        msgs = check_document(path, text)
        if msgs:
            sys.stderr.write(f"\n発注ゲート: {path}\n" + "\n".join(msgs) + "\n")
            return 1
        return 0
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
