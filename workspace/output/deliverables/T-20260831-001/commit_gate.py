#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contacts_v1.csv を PUBLIC リポに commit してよいか判定する。

法務ハルオの判定 B §8-5「commit 前ゲート（実装必須）」の実装です。
**このリポジトリは PUBLIC で30分ごとに自動 push される**ため、
commit した瞬間に全世界へ公衆送信されます。個人情報が1行でも混ざったら
取り下げには force push（＝CLAUDE.md §4.1 の不可逆操作）が要ります。

    python3 commit_gate.py            # contacts_v1.csv を検査
    python3 commit_gate.py <path>     # 任意のCSVを検査

終了コード 0 = 抵触ゼロ（commit 可）／ 1 = 要人手確認（commit しない）。

**ヒットしても即NGではありません。** ハルオの設計意図は「人が読むまで止める」。
判定した人と理由をチケットに残してから進めてください。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.optout import is_personal_local_part  # noqa: E402

CONTACT_COLS = ("公式HP", "電話", "問い合わせフォームURL", "メール")

#: 居宅を示しやすい表記。オフィスビル名にも「◯号室」は出るので、
#: ヒットしたら人が地図で確認すること（自動では白黒つけない）。
RESIDENCE_HINTS = re.compile(r"マンション|ハイツ|アパート|コーポ|[０-９0-9]+荘|レジデンス|団地")
ROOM_NUMBER = re.compile(r"[0-9０-９]+号室")


def check(path: str):
    with io.open(path, encoding="utf-8-sig") as fp:
        rows = list(csv.DictReader(fp))

    filled = [r for r in rows if any((r.get(c) or "").strip() for c in CONTACT_COLS)]
    hits = []

    for r in filled:
        name = r.get("メーカー名", "")

        # 1) 個人事業主 / 2) ノーブランド・個人らしき に連絡先が入った
        if (r.get("entity_type") or "").strip() == "個人事業主":
            hits.append(("個人事業主", name, ""))
        if (r.get("分類") or "").strip() == "ノーブランド・個人らしき":
            hits.append(("ノーブランド・個人らしきに連絡先", name, ""))

        # 3) メールのローカル部が姓名パターン
        mail = (r.get("メール") or "").strip()
        if mail and is_personal_local_part(mail):
            hits.append(("個人名らしいメール", name, mail))

        # 4) 代表者・担当者の氏名列
        for col, val in r.items():
            if val and ("代表者" in col or "担当者" in col or "氏名" in col):
                hits.append(("氏名列に値がある", name, col))

        # 5) 居宅を示す所在地
        addr = (r.get("所在地") or "").strip()
        if addr and RESIDENCE_HINTS.search(addr):
            hits.append(("居宅の疑いがある所在地", name, addr))
        elif addr and ROOM_NUMBER.search(addr):
            hits.append(("号室つき所在地（ビル名を人が確認すること）", name, addr))

    return rows, filled, hits


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "contacts_v1.csv")
    rows, filled, hits = check(path)
    print("対象: %s" % path)
    print("行数: %d / 連絡先が1つ以上ある行: %d" % (len(rows), len(filled)))
    if not hits:
        print("commit 前ゲート: 抵触0件 → PUBLIC リポへ commit してよい")
        return 0
    print("commit 前ゲート: %d 件ヒット。**人が読むまで commit しない**" % len(hits))
    for kind, name, detail in hits:
        print("  - [%s] %s %s" % (kind, name, detail))
    return 1


if __name__ == "__main__":
    sys.exit(main())
