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
  python3 amazon_check_log.py hook              SessionStart 用の警告本文（平常時は空）

2026-10-16 追記（T-20261016-002）:
  - **ログは2本**になりました。書き手ごとに1ファイルにして、Mac とクラウドが同じ行を
    同時に書き換えて git が分岐（＝github-sync が永久停止）するのを避けるためです。
      amazon-daily-check.md        … Mac の巡回（セラーセントラル画面＋Gmail）。従来どおり
      amazon-daily-check-cloud.md  … クラウドの巡回（Gmail 通知のみ。画面は見られない）
    「欠測」は従来どおり **Mac の巡回（フル）** で数えます。クラウドは代替ではなく保険です。
  - 「今日」は **日本時間** で数えます。クラウドのコンテナは UTC なので、素の date.today()
    だと 0:00〜9:00 JST の間、前日扱いになり誤判定します。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})")

# 「この日は動かなかった」と判定する印。本文の先頭付近に出る。
NOT_RUN_MARK = "未実行"

# SessionStart で警告する欠測の範囲（日）。これより古い欠測は status には出すが、警告はしない。
RECENT_DAYS = 7


def repo_root() -> Path:
    """このスクリプトは <repo>/.claude/scripts/ に置かれている前提。"""
    return Path(__file__).resolve().parents[2]


def default_log_path() -> Path:
    return repo_root() / "workspace" / "monitoring" / "amazon-daily-check.md"


def cloud_log_path() -> Path:
    """クラウド巡回（Gmail のみ）の記録。書き手を分けるため別ファイル。"""
    return repo_root() / "workspace" / "monitoring" / "amazon-daily-check-cloud.md"


def now_jst() -> dt.datetime:
    """巡回は日本時間 12:00 予定。判定は常に日本時間で行う（コンテナは UTC のことがある）。"""
    return dt.datetime.now(JST)


def summarize_dates(dates: list[str]) -> str:
    """['2026-09-07', '2026-09-08', ...] を '2026-09-07〜2026-10-15' のような区間表記に縮める。

    40日ぶん日付を並べると警告が読まれなくなる（2026-10-16 の実例）ので、連続は畳む。
    """
    if not dates:
        return "なし"
    ds = sorted(dt.date.fromisoformat(d) for d in dates)
    spans: list[tuple[dt.date, dt.date]] = []
    start = prev = ds[0]
    for d in ds[1:]:
        if d == prev + dt.timedelta(days=1):
            prev = d
            continue
        spans.append((start, prev))
        start = prev = d
    spans.append((start, prev))
    return ", ".join(a.isoformat() if a == b else f"{a.isoformat()}〜{b.isoformat()}" for a, b in spans)


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


def read_mac_log(ref: str | None, path: Path) -> tuple[str | None, str]:
    """Mac 版ログの本文と、どこから読んだかの説明を返す。

    ref=None   … 作業ツリーのファイル（従来どおり）
    ref="auto" … 最新の自動同期が載っているブランチ（sync_liveness.sh --branch）から読む。
                 Mac が main 以外のブランチに居ると、main のファイルは古いまま止まって見える
                 （2026-10-16 に実際そうなって「40日停止」と誤認した）。main ならファイルを読む。
    それ以外   … そのブランチ名（origin/<ref>）から読む。
    """
    if ref == "auto":
        env = dict(os.environ, SYNC_LIVENESS_NOFETCH=os.environ.get("SYNC_LIVENESS_NOFETCH", "1"))
        try:
            ref = subprocess.run(
                ["bash", str(repo_root() / ".claude" / "scripts" / "sync_liveness.sh"), "--branch"],
                capture_output=True, text=True, timeout=30, env=env,
            ).stdout.strip() or None
        except Exception:
            ref = None
        if ref in (None, "main", "不明"):
            ref = None
    if ref is None:
        return (path.read_text(encoding="utf-8") if path.exists() else None), str(path)
    rel = path.resolve().relative_to(repo_root()).as_posix()
    r = subprocess.run(["git", "-C", str(repo_root()), "show", f"origin/{ref}:{rel}"],
                       capture_output=True, text=True)
    return (r.stdout if r.returncode == 0 else None), f"origin/{ref}:{rel}"


def cloud_summary(today: dt.date, now: dt.time) -> dict:
    """クラウド巡回ログの要約。ファイルが無ければ log_exists=False。"""
    path = cloud_log_path()
    if not path.exists():
        return {"log_exists": False}
    return status(path.read_text(encoding="utf-8"), today, now)


def hook_body(main_st: dict, cloud_st: dict) -> str:
    """SessionStart リマインダー⑤の本文。**平常時は空文字**（無風時は1行も出さない）。"""
    # 鳴らすのは「直近7日」の欠測だけ。過去の欠測は取り返せない（Amazon の画面は今しか見せない）ので、
    # 永遠に警告し続けると、いずれ誰も読まなくなる（2026-10-16 に31日ぶんが並んで実際そうなった）。
    all_missing = main_st.get("missing") or []
    recent_from = (dt.date.fromisoformat(main_st["today"]) - dt.timedelta(days=RECENT_DAYS)).isoformat()
    missing = [d for d in all_missing if d >= recent_from]
    older_n = len(all_missing) - len(missing)
    today_pending = (not main_st.get("today_done")) and (not main_st.get("before_deadline"))
    # クラウド巡回そのものが止まった時も鳴らす（保険が黙って死ぬのが一番まずい）。
    # クラウドは 11:56 頃に走るので、今日ぶんの判定は Mac と同じ 12:00 境界でよい。
    cloud_missing = (cloud_st.get("missing") or []) if cloud_st.get("log_exists") else []
    cloud_pending = bool(cloud_st.get("log_exists")) and (not cloud_st.get("today_done")) \
        and (not cloud_st.get("before_deadline"))
    if not missing and not today_pending and not cloud_missing and not cloud_pending:
        return ""
    out = []
    if cloud_missing or cloud_pending:
        out.append(f"**クラウド巡回（スケジュールタスク）も止まっています**: 欠測 {summarize_dates(cloud_missing)}"
                   + ("／今日ぶん未" if cloud_pending else ""))
    if missing:
        out.append(f"**直近{RECENT_DAYS}日で Mac での巡回（セラーセントラル画面）が実行されなかった日: "
                   f"{summarize_dates(missing)}**" + (f"（それより前の欠測 {older_n} 日は記録済み）" if older_n else ""))
    if today_pending:
        out.append(f"**今日（{main_st['today']}）の Mac 巡回がまだです**（12:00 予定を過ぎています）。")
    last = main_st.get("last_ok")
    out.append(f"Mac で最後に巡回できたのは {last} です。" if last else "**Mac では一度も巡回できていません。**")
    if cloud_st.get("log_exists"):
        c_last = cloud_st.get("last_ok")
        c_today = "済" if cloud_st.get("today_done") else "未"
        out.append(f"クラウド巡回（Gmail 通知のみ・画面は見ていない）: 最終 {c_last or 'なし'} / 今日={c_today}"
                   "（workspace/monitoring/amazon-daily-check-cloud.md）")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["status", "fill", "hook"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", default=None, help="ログのパス（既定: workspace/monitoring/...）")
    ap.add_argument("--today", default=None, help="テスト用に今日の日付を上書き（YYYY-MM-DD）")
    ap.add_argument("--now", default=None, help="テスト用に現在時刻を上書き（HH:MM）")
    ap.add_argument("--ref", default=None,
                    help="Mac 版ログを git のブランチから読む（auto=最新の自動同期が載っているブランチ）。status/hook 用")
    args = ap.parse_args(argv)

    path = Path(args.log) if args.log else default_log_path()
    jst = now_jst()
    today = dt.date.fromisoformat(args.today) if args.today else jst.date()
    now = dt.time.fromisoformat(args.now) if args.now else jst.time()

    if args.ref and args.command != "fill":
        text, source = read_mac_log(args.ref, path)
    else:
        text, source = (path.read_text(encoding="utf-8") if path.exists() else None), str(path)
    if text is None:
        out = {"log_exists": False, "path": source}
        print(json.dumps(out, ensure_ascii=False) if args.json else f"ログがありません: {source}")
        return 0

    if args.command == "fill":
        added = fill(path, today, now)
        if args.json:
            print(json.dumps({"added": added}, ensure_ascii=False))
        else:
            print("挿入した欠測日: " + (", ".join(added) if added else "なし"))
        return 0

    st = status(text, today, now)
    st["source"] = source
    cloud = cloud_summary(today, now) if not args.log else {"log_exists": False}
    if args.command == "hook":
        print(hook_body(st, cloud))
        return 0
    if args.json:
        st["cloud"] = cloud
        print(json.dumps(st, ensure_ascii=False))
    else:
        print(f"（Mac 版ログの読み元: {source}）")
        print(
            f"[Mac巡回] 最後に実行できた日={st['last_ok']} / 今日は{'済' if st['today_done'] else '未'} / "
            f"欠測{len(st['missing'])}日: {summarize_dates(st['missing'])}"
        )
        if cloud.get("log_exists"):
            print(
                f"[クラウド巡回・Gmailのみ] 最終={cloud['last_ok']} / 今日は{'済' if cloud['today_done'] else '未'} / "
                f"開始以降の欠測{len(cloud['missing'])}日: {summarize_dates(cloud['missing'])}"
            )
        else:
            print("[クラウド巡回・Gmailのみ] ログなし")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
