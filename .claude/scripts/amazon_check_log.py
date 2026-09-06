#!/usr/bin/env python3
"""Amazon 日次チェックログ（workspace/monitoring/amazon-daily-check.md）の判定ロジック。

このファイルは「実行された日／されなかった日」を決める **唯一の場所** です。
SessionStart フック（リマインダー⑤）と watchdog（launchd）の両方がここを呼びます。
判定を2箇所に書くと必ずズレるので、増やさないでください。

判定の原則（2026-08-31 の設計をそのまま引き継ぐ）:
  - スケジューラの内部状態は見ない。**ログに行が増えたことだけが、動いた証拠**。
  - 見出し `## YYYY-MM-DD` があっても、その本文に「未実行」とあれば **実行されていない** と数える。
    （2026-09-06 に手で足した「## 2026-09-05 未実行」が、旧実装では検知を黙らせていた）
  - 最新日は「ファイルの先頭の見出し」ではなく **全見出しの最大値** を採る。
    並び順は人が手で書くので、いつか必ず崩れる（実際 9/5 が 9/6 の上にあった）。

CLI:
  python3 amazon_check_log.py status            人が読む1行サマリ
  python3 amazon_check_log.py status --json     機械が読む JSON
  python3 amazon_check_log.py fill              欠測日に「未実行」行を挿入する（過去日のみ）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})")

# 「この日は動かなかった」と判定する印。本文の先頭付近に出る。
NOT_RUN_MARK = "未実行"


def repo_root() -> Path:
    """このスクリプトは <repo>/.claude/scripts/ に置かれている前提。"""
    return Path(__file__).resolve().parents[2]


def default_log_path() -> Path:
    return repo_root() / "workspace" / "monitoring" / "amazon-daily-check.md"


class Entry:
    """ログ1エントリ（`## YYYY-MM-DD` 見出しとその本文）。"""

    def __init__(self, date: dt.date, line_no: int, executed: bool):
        self.date = date
        self.line_no = line_no  # 0-origin。見出し行そのものの位置
        self.executed = executed

    def __repr__(self) -> str:  # デバッグ用
        return f"Entry({self.date}, line={self.line_no}, executed={self.executed})"


def parse(text: str) -> list[Entry]:
    """ログ本文を Entry のリストにする。ファイル内の出現順のまま返す。"""
    lines = text.splitlines()
    heads: list[tuple[dt.date, int]] = []
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        try:
            heads.append((dt.date.fromisoformat(m.group(1)), i))
        except ValueError:
            continue  # 日付として壊れている見出しは無視する

    entries: list[Entry] = []
    for idx, (date, line_no) in enumerate(heads):
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(lines)
        body = "\n".join(lines[line_no:end])
        entries.append(Entry(date, line_no, NOT_RUN_MARK not in body))
    return entries


def status(text: str, today: dt.date, now: dt.time, deadline_hour: int = 12) -> dict:
    """ログの状態を1つの dict にまとめる。

    deadline_hour: 巡回の予定時刻（12:00）。今日ぶんの欠測は、この時刻を過ぎるまで
                   「まだ来ていない」であって「落ちた」ではない。誤検知を避けるための境界。
    """
    entries = parse(text)
    ok_dates = {e.date for e in entries if e.executed}
    all_dates = {e.date for e in entries}

    result = {
        "log_exists": True,
        "entry_count": len(entries),
        "last_ok": max(ok_dates).isoformat() if ok_dates else None,
        "today": today.isoformat(),
        "today_done": today in ok_dates,
        # 今日の分がまだ来ていないだけの時間帯か（12:00 前）
        "before_deadline": now.hour < deadline_hour,
        "missing": [],          # 実行されなかった過去日（今日は含めない）
        "missing_unlogged": [],  # そのうち、ログに行すら無い日（＝ fill の対象）
    }

    if not all_dates:
        result["missing"] = []
        return result

    # 「いつから数えるか」＝ログにある最古の日付。運用開始前の日を欠測とは呼ばない。
    start = min(all_dates)
    day = start
    yesterday = today - dt.timedelta(days=1)
    while day <= yesterday:
        if day not in ok_dates:
            result["missing"].append(day.isoformat())
            if day not in all_dates:
                result["missing_unlogged"].append(day.isoformat())
        day += dt.timedelta(days=1)

    return result


def _entry_block(date: str) -> str:
    """欠測日に挿入する本文。空白は見逃されるが、明示された欠測は見逃されにくい。"""
    return (
        f"## {date}\n"
        "\n"
        "**未実行。** 12:00 のスケジュールタスクが発火しませんでした"
        "（Claude アプリが起動していなかった可能性が高い）。\n"
        "この行は watchdog（`.claude/scripts/amazon-check-watchdog.sh`）が自動挿入しました。"
        "巡回そのものは行われていません。\n"
        "\n"
        "---\n"
        "\n"
    )


def fill(path: Path, today: dt.date, now: dt.time) -> list[str]:
    """欠測している過去日に「未実行」エントリを挿入する。挿入した日付を返す。

    今日ぶんは絶対に書かない。12:00 に遅れて走ることがあり、先回りして「未実行」と
    書くと嘘になるため（このツールが嘘をつくと、ログ全体の価値が消える）。
    """
    text = path.read_text(encoding="utf-8")
    st = status(text, today, now)
    targets = st["missing_unlogged"]
    if not targets:
        return []

    lines = text.splitlines(keepends=True)
    # 新しい順に挿入していく（後ろから挿すと行番号がずれないので、日付は昇順で処理し
    # 毎回パースし直す方が単純。件数は多くて数件なので素直に書く）
    for date_str in targets:
        date = dt.date.fromisoformat(date_str)
        body = "".join(lines)
        heads = [(e.date, e.line_no) for e in parse(body)]
        insert_at = None
        for d, ln in heads:
            if d < date:  # 自分より古い最初の見出しの直前に入れる＝新しい順を保つ
                insert_at = ln
                break
        if insert_at is None:
            insert_at = len(lines)
            if lines and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
        lines.insert(insert_at, _entry_block(date_str))

    path.write_text("".join(lines), encoding="utf-8")
    return targets


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["status", "fill"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", default=None, help="ログのパス（既定: workspace/monitoring/...）")
    ap.add_argument("--today", default=None, help="テスト用に今日の日付を上書き（YYYY-MM-DD）")
    ap.add_argument("--now", default=None, help="テスト用に現在時刻を上書き（HH:MM）")
    args = ap.parse_args(argv)

    path = Path(args.log) if args.log else default_log_path()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    now = dt.time.fromisoformat(args.now) if args.now else dt.datetime.now().time()

    if not path.exists():
        out = {"log_exists": False, "path": str(path)}
        print(json.dumps(out, ensure_ascii=False) if args.json else f"ログがありません: {path}")
        return 0

    if args.command == "fill":
        added = fill(path, today, now)
        if args.json:
            print(json.dumps({"added": added}, ensure_ascii=False))
        else:
            print("挿入した欠測日: " + (", ".join(added) if added else "なし"))
        return 0

    st = status(path.read_text(encoding="utf-8"), today, now)
    if args.json:
        print(json.dumps(st, ensure_ascii=False))
    else:
        print(
            f"最後に実行できた日={st['last_ok']} / 今日は{'済' if st['today_done'] else '未'} / "
            f"欠測{len(st['missing'])}日: {', '.join(st['missing']) or 'なし'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
