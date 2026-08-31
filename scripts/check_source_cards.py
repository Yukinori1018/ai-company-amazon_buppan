#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出所カード検査 — 「規約で用途が縛られたデータ」が無記名で置かれていないかを見張る。

背景（2026-08-31 / T-20260831-005）:
    NETSEA バイヤー会員規約は、当社に「NETSEA 内で完結する仕入れ実務」以外の用途を
    禁じています（第7条2項5号・第19条3項。違反時は違約金200万円＋代金の50%）。
    ところが当社の CSV / JSON / ログには「どこから取ったデータか」を書く欄がなく、
    数か月後には出所が分からなくなります。分からないデータは、いつか必ず別の用途へ流れます。

この検査がやること（それだけ）:
    workspace/output/ 配下のデータファイルを走査し、
    **用途制限のあるソース名（NETSEA 等）に言及するファイルが置かれたディレクトリに
    SOURCE.md（出所カード）があるか**を確かめる。無ければ非ゼロ終了する。

やらないこと（YAGNI）:
    - 中身の正誤判定。人間が SOURCE.md に嘘を書けば止められません。これは
      「出所を書き忘れる」事故を止めるためのもので、悪意を止めるものではありません。
    - 自動修正。カードは人が書くもの。

使い方:
    python3 scripts/check_source_cards.py          # 検査（NG があれば exit 1）
    python3 scripts/check_source_cards.py --list   # 検出したファイルを全部並べる
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 走査対象。deliverables（公開）と agent_output（非公開）の両方を見る。
SCAN_ROOTS = [
    REPO / "workspace/output/deliverables",
    REPO / "workspace/output/agent_output",
]

# データとみなす拡張子。.md / .html は「文書」なので対象外（言及して当然のため）。
DATA_SUFFIXES = {".csv", ".json", ".log", ".txt", ".tsv"}

# 用途が規約で縛られているソース。増えたらここに足すだけ。
# key = ソース名 / value = そのソースを示す検出語（小文字で比較）
RESTRICTED_SOURCES = {
    "NETSEA": ("netsea", "ネッシー"),
}

# 出所カードのファイル名。
CARD_NAME = "SOURCE.md"

# 検査から外すファイル（理由を必ず添えること）。
EXCLUDED = {
    # 成果物カタログは全成果物の索引。行タイトルにソース名が出るのは当然で、
    # カタログ自体は NETSEA 由来データではない。
    REPO / "workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv",
}

# 巨大ファイルは読まない（Keepa の生レスポンス等）。
MAX_READ_BYTES = 40 * 1024 * 1024


def mentions_restricted(path: Path) -> list[str]:
    """このファイルが用途制限ソースに言及しているか。該当ソース名のリストを返す。"""
    found = []
    name = path.name.lower()
    try:
        text = path.read_text("utf-8", errors="ignore").lower()
    except OSError:
        text = ""
    for source, needles in RESTRICTED_SOURCES.items():
        if any(n in name or n in text for n in needles):
            found.append(source)
    return found


def has_card(directory: Path) -> bool:
    """このディレクトリ、または走査ルートまでの祖先に出所カードがあるか。"""
    for root in SCAN_ROOTS:
        if root in directory.parents or root == directory:
            cur = directory
            while True:
                if (cur / CARD_NAME).is_file():
                    return True
                if cur == root:
                    return False
                cur = cur.parent
    return False


def scan() -> tuple[dict[Path, list[tuple[Path, list[str]]]], int]:
    """(カード欠落ディレクトリ -> [(ファイル, ソース名)], 検出ファイル総数) を返す。"""
    missing: dict[Path, list[tuple[Path, list[str]]]] = {}
    total = 0
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in DATA_SUFFIXES:
                continue
            if path in EXCLUDED:
                continue
            try:
                if path.stat().st_size > MAX_READ_BYTES:
                    continue
            except OSError:
                continue
            sources = mentions_restricted(path)
            if not sources:
                continue
            total += 1
            if not has_card(path.parent):
                missing.setdefault(path.parent, []).append((path, sources))
    return missing, total


def main(argv: list[str]) -> int:
    missing, total = scan()
    print(f"用途制限ソースに言及するデータファイル: {total} 件")

    if "--list" in argv:
        for root in SCAN_ROOTS:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in DATA_SUFFIXES:
                    if path in EXCLUDED:
                        continue
                    try:
                        if path.stat().st_size > MAX_READ_BYTES:
                            continue
                    except OSError:
                        continue
                    src = mentions_restricted(path)
                    if src:
                        mark = "OK " if has_card(path.parent) else "NG "
                        print(f"  {mark} [{','.join(src)}] {path.relative_to(REPO)}")

    if not missing:
        print(f"出所カード（{CARD_NAME}）欠落: 0 件。OK")
        return 0

    print(f"\n出所カード（{CARD_NAME}）が無いディレクトリ: {len(missing)} 件")
    for directory, files in sorted(missing.items()):
        print(f"\n  {directory.relative_to(REPO)}/  ← ここに {CARD_NAME} を置いてください")
        for path, sources in files[:10]:
            print(f"      - {path.name}  [{','.join(sources)}]")
        if len(files) > 10:
            print(f"      … 他 {len(files) - 10} 件")
    print(
        "\n書くこと: 取得元URL・取得日・許可されている用途・禁止されている用途・根拠条文。"
        "\nひな型: workspace/output/deliverables/T-20260705-001/SOURCE.md"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
