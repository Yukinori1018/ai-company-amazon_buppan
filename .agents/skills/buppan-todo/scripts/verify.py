#!/usr/bin/env python3
"""マスターToDoリストの機械検算。落ちたら納品しない。

    python3 verify.py <deliverables_dir>

見るのは7点です。

1. 骨格の同一性 — 01 の小項目本文が 02（標準チェックリスト）と1文字も違わないか。
   02 はサトルが一次情報で裏を取った原本で、進捗更新のたびに本文が書き換わると
   数値やしきい値が静かに壊れます。ここが一番大事な検査です。
2. 件数 — 大項目の見出しに書いた「中項目M / 小項目K」が実際の数と合っているか。
3. A章サマリ表 — 表の数字が awk 集計と一致するか。前回、集計と本文がズレて
   説明が必要になりました。人が表を手で直すと必ず起きます。
4. マークの記法 — [x] [~] [ ] 以外が紛れ込んでいないか。
5. 個人特定情報 — このリポジトリは PUBLIC です。利用者識別番号・受付番号・口座番号・
   電話番号・メールアドレス・サポートのケース番号を成果物に書くと、コミットした瞬間に
   公開されます。
6. 根拠の実在・鮮度・整合（evidence.py）— 根拠IDのチケットが実在するか、資料の更新日
   より新しいチケットが無いか、prepare 以降に本文が変わっていないか。2026-08-31 の
   誤判定10件・不整合14件・日付凍結は、ここが無かったから通ってしまいました。
7. ボードの数字（update_board.py --check）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE_TASK = re.compile(r"^- \[([x~ ])\] (.*)$")
RE_BAD_MARK = re.compile(r"^- \[([^x~ ])\] ")
RE_TICKET_SUFFIX = re.compile(r"\s*〔[^〕]*〕\s*$")
RE_MAJOR = re.compile(r"^## ([1-8])\. (.+?)（中項目(\d+) / 小項目(\d+)）\s*$")

# 公開リポに出してはいけないもの。値そのものではなくラベルで拾う（値は書かない）。
# 2026-08-31 追加: メールアドレスとサポートのケース番号。ヒデアキが目視で見つけたのに
# ここが拾えていなかった＝検査をすり抜けた実績があります。
PII_PATTERNS = [
    (r"利用者識別番号", "e-Tax の利用者識別番号"),
    (r"受付番号\s*[:：]?\s*\d", "e-Tax の受付番号"),
    (r"\b\d{3,4}-\d{2,4}-\d{4}\b", "電話番号らしき数字列"),
    (r"口座番号\s*[:：]?\s*\d", "銀行口座番号"),
    (r"マイナンバー\s*[:：]?\s*\d", "マイナンバー"),
    # メールアドレス。TLD のドットを必須にして `@sellonamazonjp`（公式LINE ID）や
    # Google Fonts の `wght@500`、CSS の `@media` を巻き込まないようにする。
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", "メールアドレス"),
    (r"(?:ケース|案件|問い合わせ|お問い合わせ|Case|CASE)\s*(?:番号|ID|#)?\s*[:：]?\s*\d{5,}",
     "サポートのケース番号"),
    (r"(?:Case|CASE|ケース)\s*ID\s*[:：]?\s*\S+", "サポートのケースID"),
    # 桁の長い裸の数字列。Amazon のケース番号・注文番号・口座番号はここに落ちる。
    # 政策ID（G201808410 等）は英字が前に付くので除外される。
    (r"(?<![A-Za-z0-9\-])\d{9,}(?![0-9\-])", "9桁以上の裸の数字列（ケース番号・注文番号の疑い）"),
]


def tasks(path: str) -> list[tuple[str, str]]:
    out = []
    for line in open(path, encoding="utf-8"):
        m = RE_TASK.match(line.rstrip("\n"))
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def body_of(text: str) -> str:
    """進捗マークと根拠チケットの注記を落とし、骨格の本文だけを残す。"""
    return RE_TICKET_SUFFIX.sub("", text).strip()


def check_skeleton(master: str, checklist: str, fail) -> None:
    a = [body_of(t) for _, t in tasks(master)]
    b = [body_of(t) for _, t in tasks(checklist)]
    if len(a) != len(b):
        fail(f"小項目の件数が違う: 01={len(a)} / 02={len(b)}")
        return
    diffs = [(i, x, y) for i, (x, y) in enumerate(zip(a, b), 1) if x != y]
    for i, x, y in diffs[:10]:
        fail(f"小項目 {i} の本文が原本と違う\n      01: {x[:80]}\n      02: {y[:80]}")
    if len(diffs) > 10:
        fail(f"（ほか {len(diffs) - 10} 件）")
    if not diffs:
        print(f"  OK 骨格 {len(a)} 項目が 02 と完全一致")


def check_headings(master: str, counts: dict, fail) -> None:
    majors = {m["no"]: m for m in counts["major"]}
    found = 0
    bad = 0
    for line in open(master, encoding="utf-8"):
        m = RE_MAJOR.match(line)
        if not m:
            continue
        found += 1
        no, mids, items = m.group(1), int(m.group(3)), int(m.group(4))
        mj = majors.get(no)
        if not mj:
            fail(f"大項目 {no} が集計に無い")
            bad += 1
            continue
        real_items = mj["done"] + mj["doing"] + mj["todo"]
        if mids != mj["mids"] or items != real_items:
            fail(
                f"大項目 {no} の見出し表記が実数と違う: "
                f"見出し=中{mids}/小{items} 実数=中{mj['mids']}/小{real_items}"
            )
            bad += 1
    if found != len(majors):
        fail(f"大項目の見出しが {found} 個しか無い（期待 {len(majors)}）")
    elif not bad:
        print(f"  OK 大項目 {found} 件の見出し表記が実数と一致")


def check_summary_table(master: str, counts: dict, fail) -> None:
    """A章のサマリ表を集計と突き合わせる。"""
    majors = {m["no"]: m for m in counts["major"]}
    tot = counts["total"]
    seen = set()
    bad = 0
    for line in open(master, encoding="utf-8"):
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 3:
            continue
        head = cols[0].replace("*", "")
        triple = re.fullmatch(r"\**\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\**", cols[2])
        if not triple:
            continue
        got = tuple(int(g) for g in triple.groups())
        if head == "合計":
            want = (tot["done"], tot["doing"], tot["todo"])
            label = "合計"
        else:
            m = re.match(r"([1-8])\.", head)
            if not m:
                continue
            mj = majors[m.group(1)]
            want = (mj["done"], mj["doing"], mj["todo"])
            label = f"大項目 {m.group(1)}"
        seen.add(label)
        if got != want:
            fail(f"A章サマリ表の {label} が集計と違う: 表={got} 集計={want}")
            bad += 1
    missing = {f"大項目 {n}" for n in majors} | {"合計"}
    missing -= seen
    if missing:
        fail("A章サマリ表に行が無い: " + ", ".join(sorted(missing)))
    elif not bad:
        print(f"  OK A章サマリ表 {len(seen)} 行が集計と一致")


def check_marks(master: str, fail) -> None:
    bad = [
        (i, line.rstrip())
        for i, line in enumerate(open(master, encoding="utf-8"), 1)
        if RE_BAD_MARK.match(line)
    ]
    for i, line in bad[:5]:
        fail(f"{i}行目のマークが [x]/[~]/[ ] 以外: {line[:70]}")
    if not bad:
        print("  OK マークは [x]/[~]/[ ] のみ")


def check_pii(paths: list[str], fail) -> None:
    hits = 0
    for p in paths:
        text = open(p, encoding="utf-8").read()
        for pat, label in PII_PATTERNS:
            for m in re.finditer(pat, text):
                hits += 1
                fail(f"{os.path.basename(p)} に {label} らしき記載: …{m.group(0)[:20]}…")
    if not hits:
        print("  OK 個人特定情報の検出なし")


def run_evidence_check(deliv: str, fail) -> None:
    """根拠の実在・鮮度・整合を evidence.py に委ねる（update_board.py --check と同じ作法）。

    作業場は `agent_output/<ticket_id>/`。prepare が作った索引と今のチケットを突き合わせ、
    ズレていれば NG になる。抜粋を読まずに判定する経路を塞ぐための検査です。
    """
    tid = os.path.basename(deliv.rstrip("/"))
    repo = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
    work = os.path.join(repo, "workspace", "output", "agent_output", tid)
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "evidence.py"), "check", deliv, work],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(r.stdout)
    if r.stderr.strip():
        print(r.stderr.strip())
    if r.returncode != 0:
        fail("根拠の実在・鮮度・整合が通らない（上の NG を参照）")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    d = sys.argv[1]
    master = os.path.join(d, "01_master-todo.md")
    checklist = os.path.join(d, "02_lifecycle-checklist.md")
    board = os.path.join(d, "03_process-board.html")

    errors: list[str] = []

    def fail(msg: str) -> None:
        errors.append(msg)
        print(f"  NG {msg}")

    for p in (master, checklist):
        if not os.path.exists(p):
            print(f"  NG {p} が無い")
            return 1

    counts = json.loads(
        subprocess.run(
            ["awk", "-f", os.path.join(HERE, "aggregate.awk"), master],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )

    print("検算:")
    check_skeleton(master, checklist, fail)
    check_headings(master, counts, fail)
    check_summary_table(master, counts, fail)
    check_marks(master, fail)
    # ボードも見る。narrative は人が手で書き足す場所で、PII が混ざるならここです。
    check_pii([p for p in (master, checklist, board) if os.path.exists(p)], fail)
    run_evidence_check(d, fail)

    if os.path.exists(board):
        r = subprocess.run(
            [
                sys.executable,
                os.path.join(HERE, "update_board.py"),
                board,
                "/dev/stdin",
                "--check",
            ],
            input=json.dumps(counts),
            capture_output=True,
            text=True,
        )
        print("  " + r.stdout.strip().replace("\n", "\n  "))
        if r.returncode != 0:
            errors.append("ボードの数字が集計とズレている")

    t = counts["total"]
    print(
        f'\n集計: 済 {t["done"]} / 着手中 {t["doing"]} / 未着手 {t["todo"]}'
        f'（小項目 {t["items"]} ・ 中項目 {t["mids"]} ・ 大項目 {t["majors"]}）'
    )
    if errors:
        print(f"\n検算 NG: {len(errors)} 件。直すまで納品しないこと。")
        return 1
    print("\n検算 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
