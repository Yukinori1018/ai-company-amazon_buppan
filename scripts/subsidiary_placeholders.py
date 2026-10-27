#!/usr/bin/env python3
"""子会社リポのプレースホルダー置換（create-subsidiary.sh の Step C の実体）。

置換の定義は docs/rules/subsidiary-placeholders.md にある（表と §B1 のひな形）。
CLAUDE.md の本文には {{ }} を置かない方針（2026-10-27 T-20261027-001）なので、
「このリポに今書かれている値」を新しい値に置き換える作りにしている。

使い方:
  python3 scripts/subsidiary_placeholders.py <対象ディレクトリ> \
      --business-name 事業名 --mission ミッション --kpi KPI \
      --products 主力商品 --customers 想定顧客 [--dry-run]

終了コード: 0=置換して検査も通った / 1=検査で置き残しが見つかった / 2=定義ファイルの不備
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SPEC_REL = Path("docs/rules/subsidiary-placeholders.md")
TARGET_SUFFIXES = (".md", ".json", ".json.example")
SKIP_DIRS = {".git"}
SKIP_PREFIXES = ("docs/reference/",)
# 旧テンプレの {{ }} を説明として載せている文書。置き残し検査から外す。
LEGACY_DOCS = {"docs/subsidiary-onboarding.md", "scripts/README.md", str(SPEC_REL)}
LEGACY_TOKENS = ("{{ 事業名 }}", "{{ ミッション }}", "{{ 最重要KPI }}",
                 "{{ 主力商品/サービス }}", "{{ 想定顧客 }}")

TABLE_RE = re.compile(r"<!-- placeholders:begin -->\n(.*?)<!-- placeholders:end -->", re.S)
B1_TPL_RE = re.compile(r"<!-- b1-template:begin -->\n```\n(.*?)```\n<!-- b1-template:end -->", re.S)
B1_SECTION_RE = re.compile(r"(^### §B1[^\n]*\n)(.*?)(?=^#{2,3} )", re.S | re.M)


@dataclass
class Row:
    key: str       # 例: 事業名
    option: str    # 例: --business-name
    current: str   # このリポでの値
    mode: str      # 全文置換 / §B1


class SpecError(Exception):
    pass


def load_spec(root: Path) -> tuple[list[Row], str, str]:
    """(表の行, §B1 のひな形, 定義ファイルの全文) を返す。"""
    path = root / SPEC_REL
    if not path.exists():
        raise SpecError(f"定義ファイルがありません: {path}")
    text = path.read_text(encoding="utf-8")
    m = TABLE_RE.search(text)
    t = B1_TPL_RE.search(text)
    if not m or not t:
        raise SpecError(f"表かひな形の目印（<!-- ...:begin/end -->）が見つかりません: {path}")
    rows = []
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("キー", "---") or set(cells[0]) <= {"-"}:
            continue
        rows.append(Row(*cells))
    if not rows:
        raise SpecError("表に行がありません")
    return rows, t.group(1), text


def iter_targets(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith(SKIP_PREFIXES) or rel == SPEC_REL.as_posix():
            continue
        if p.name.endswith(TARGET_SUFFIXES):
            yield p, rel


def render_b1(template: str, values: dict[str, str]) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{ " + key + " }}", val)
    return out


def apply(root: Path, values: dict[str, str], dry_run: bool = False) -> list[str]:
    """置換して、検査で見つかった問題（置き残し）の一覧を返す。空なら成功。"""
    rows, b1_tpl, spec_text = load_spec(root)
    missing = [r.key for r in rows if not values.get(r.key)]
    if missing:
        raise SpecError(f"値が渡されていません: {', '.join(missing)}")

    # 1) 全文置換（旧テンプレの {{ }} も一緒に埋める。残っている文書があるため）
    pairs = [(r.current, values[r.key]) for r in rows if r.mode == "全文置換" and r.current != values[r.key]]
    pairs += [("{{ " + r.key + " }}", values[r.key]) for r in rows]
    changed = 0
    for p, rel in iter_targets(root):
        if rel in LEGACY_DOCS:
            continue  # 手順書の説明文は {{ }} のまま残す（説明として意図的）
        try:
            s = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = s
        for old, val in pairs:
            new = new.replace(old, val)
        if new != s:
            changed += 1
            if not dry_run:
                p.write_text(new, encoding="utf-8")
    print(f"全文置換: {changed} ファイル")

    # 2) CLAUDE.md §B1 を書き直す
    claude = root / "CLAUDE.md"
    s = claude.read_text(encoding="utf-8")  # dry-run でなければ 1) で事業名が変わった後の本文
    b1 = render_b1(b1_tpl, values)
    s2, n = B1_SECTION_RE.subn(lambda m: m.group(1) + b1 + "\n", s, count=1)
    if n != 1:
        raise SpecError("CLAUDE.md に `### §B1` の節が見つかりません")
    if not dry_run:
        claude.write_text(s2, encoding="utf-8")
    print("CLAUDE.md §B1: 書き直し")

    # 3) 定義ファイルの「このリポでの値」を新しい値にする（孫会社も同じ手順で作れるように）
    def fix_row(m: re.Match) -> str:
        body = m.group(1)
        for r in rows:
            body = body.replace(f"| {r.key} | {r.option} | {r.current} |",
                                f"| {r.key} | {r.option} | {values[r.key]} |")
        return "<!-- placeholders:begin -->\n" + body + "<!-- placeholders:end -->"
    new_spec = TABLE_RE.sub(fix_row, spec_text, count=1)
    if not dry_run:
        (root / SPEC_REL).write_text(new_spec, encoding="utf-8")
    print(f"{SPEC_REL}: 「このリポでの値」を更新")

    return [] if dry_run else verify(root, rows, values)


def verify(root: Path, rows: list[Row], values: dict[str, str]) -> list[str]:
    problems = []
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    m = B1_SECTION_RE.search(claude)
    b1 = m.group(2) if m else ""
    for r in rows:
        if r.mode == "§B1" and values[r.key] not in b1:
            problems.append(f"CLAUDE.md §B1 に {r.key} が入っていない")
    for p, rel in iter_targets(root):
        if rel in LEGACY_DOCS:
            continue
        s = p.read_text(encoding="utf-8", errors="ignore")
        for r in rows:
            if r.mode == "全文置換" and r.current not in values[r.key] and r.current in s:
                problems.append(f"{rel}: 旧{r.key}「{r.current}」が残っている")
        for tok in LEGACY_TOKENS:
            if tok in s:
                problems.append(f"{rel}: {tok} が残っている")
    rows2, _, _ = load_spec(root)
    for r in rows2:
        if r.current != values[r.key]:
            problems.append(f"{SPEC_REL}: {r.key} の値が更新されていない")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--business-name", required=True)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--kpi", required=True)
    ap.add_argument("--products", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    values = {"事業名": a.business_name, "ミッション": a.mission, "最重要KPI": a.kpi,
              "主力商品/サービス": a.products, "想定顧客": a.customers}
    try:
        problems = apply(a.root.resolve(), values, a.dry_run)
    except SpecError as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"[NG] {p}", file=sys.stderr)
    print("検査: " + ("OK" if not problems else f"置き残し {len(problems)} 件"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
