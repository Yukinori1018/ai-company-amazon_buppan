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

#: **重要な穴だった点。** contacts_v1.csv には entity_type 列が無い（schema.ContactFields に
#: 無いため）。そのため「個人事業主の疑い」を CSV だけでは検知できなかった。
#: resolver の入力である JSONL 側を直接読んで補う。
EXA_JSONL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "pipeline", "data", "exa_lookups.jsonl")


def load_entity_types():
    import json
    types = {}
    if os.path.exists(EXA_JSONL):
        with io.open(EXA_JSONL, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("entity_type"):
                    types[e.get("メーカー名", "")] = e["entity_type"]
    return types

#: 居宅を示しやすい表記。オフィスビル名にも「◯号室」は出るので、
#: ヒットしたら人が地図で確認すること（自動では白黒つけない）。
RESIDENCE_HINTS = re.compile(r"マンション|ハイツ|アパート|コーポ|[０-９0-9]+荘|レジデンス|(?<!工業)(?<!産業)(?<!流通)団地")
# ※「つくば明野工業団地」のような**産業用地**を居宅と誤判定した実例があるため除外している
#   （2026-09-04 / 旭化成ワッカーシリコンの所在地で発火）
ROOM_NUMBER = re.compile(r"[0-9０-９]+号室")

#: 成果物CSVで伏せた欄に入る印の先頭。これは連絡先の実データではない。
REDACTED_MARK_PREFIX = "【非掲載】"


class GateCannotRead(Exception):
    """検査対象を読めなかった。**「抵触0件」と区別するために例外にしている。**

    2026-09-04、B1_打診候補_全社_優先度順.csv に対してゲートが
    「連絡先が1つ以上ある行: 0 / 抵触0件 → commit してよい」と**緑を返した**。
    実際には同ファイルは全行が連絡先の一覧である。原因は先頭にある `#` の注記行を
    csv.DictReader がヘッダ行として食っていたこと（列名が1つも一致しなくなる）。

    「読めなかった」が「問題なし」に化けるのは、このゲートで**最も危険な壊れ方**。
    entity_type 列が存在せず個人事業主が素通りしていた事故と同じ型で、これで2件目。
    したがって黙って 0 件を返さず、必ず落とす。
    """


def _read_rows(path: str):
    """CSV を読む。先頭の `#` 注記行は読み飛ばす。

    B1_打診候補_全社_優先度順.csv は打診文の禁止事項をヘッダ行の前に `#` で書いている
    （ファイルを開けば必ず目に入るように、という意図的な設計）。ゲートはそれを飛ばす。
    """
    with io.open(path, encoding="utf-8-sig") as fp:
        lines = fp.read().splitlines(True)
    while lines and lines[0].lstrip("﻿").startswith("#"):
        lines.pop(0)
    if not lines:
        raise GateCannotRead("%s: 注記行を除くと中身が無い" % path)
    return list(csv.DictReader(io.StringIO("".join(lines))))


def check(path: str):
    rows = _read_rows(path)

    # ★読めたことを先に確かめる。列名が1つも無ければ「問題なし」ではなく「読めていない」。
    if rows:
        cols = set(rows[0].keys())
        if not (cols & set(CONTACT_COLS)):
            raise GateCannotRead(
                "%s: 連絡先の列（%s）が1つも見つからない。ヘッダ行の取り違えを疑うこと。"
                "検出した列: %s" % (path, "/".join(CONTACT_COLS),
                                  ", ".join(list(cols)[:8])))

    entity_types = load_entity_types()

    def _contact(r, c):
        """連絡先の実データだけを返す。伏せ字は連絡先として数えない。

        成果物CSVでは、伏せた欄を空にせず「【非掲載】…」と書いている
        （空欄だと『調べたが取れなかった』と区別がつかないため）。
        この印を連絡先とみなすと、伏せたはずの社が延々とゲートに引っかかり続け、
        本当に見るべきヒットが埋もれる。**印は連絡先ではない。**
        """
        v = (r.get(c) or "").strip()
        return "" if v.startswith(REDACTED_MARK_PREFIX) else v

    filled = [r for r in rows if any(_contact(r, c) for c in CONTACT_COLS)]
    hits = []

    for r in filled:
        name = r.get("メーカー名", "")

        # 1) 個人事業主 / 2) ノーブランド・個人らしき に連絡先が入った
        et = (r.get("entity_type") or entity_types.get(name) or "").strip()
        if et.startswith("個人事業主"):   # 「個人事業主」「個人事業主の疑い」の両方を拾う
            hits.append((et, name, ""))
        if (r.get("分類") or "").strip() == "ノーブランド・個人らしき":
            hits.append(("ノーブランド・個人らしきに連絡先", name, ""))

        # 3) メールのローカル部が姓名パターン
        mail = _contact(r, "メール")
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
    try:
        rows, filled, hits = check(path)
    except GateCannotRead as e:
        # **緑にしない。** 読めないゲートは、通っていないゲートと同じ。
        print("commit 前ゲート: 検査できませんでした → commit しない")
        print("  %s" % e)
        return 2
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
