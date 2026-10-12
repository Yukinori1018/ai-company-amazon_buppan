#!/usr/bin/env python3
"""ログイン延命と「切れた」検知（T-20260920-003 / 2026-10-12 社長指示）

社長の Chrome に「延命専用ウィンドウ」を1枚置き、その中のタブ（セラセン・Gmail・卸サイト）を
サイトごとの間隔で読み込み直す。読み込み直したあとの URL がログイン画面なら ALERT を書く。

やること
  - 専用ウィンドウ（1枚目のタブが keepalive_window.html）の中のタブだけを触る
  - 期限が来たタブを reload。ログイン画面に飛んでいたら ALERT_<site>.txt と macOS 通知
  - ログインが戻ったら ALERT を resolved/ へ移す（「何時間もったか」を残す＝セッション寿命の実測）

やらないこと（ここが肝）
  - パスワード入力・Cookie 読み取り・認証情報の保存。ログインそのものは社長の一手
  - 専用ウィンドウ以外のタブの URL・タイトルを読むこと（AppleScript 側で絞る）
  - Chrome が起動していないときに起動すること
  - URL のクエリ文字列をログに残すこと（トークンが入ることがある）

呼び方
  login_keepalive.py run      launchd から10分ごと（既定）
  login_keepalive.py setup    専用ウィンドウを作る（無ければ）＋全サイトを即チェック
  login_keepalive.py status   いまの状態を表示
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SITES_JSON = HERE / "sites.json"
MARKER_FILE = HERE / "keepalive_window.html"
MARKER_NAME = MARKER_FILE.name  # ウィンドウを見分ける印（1枚目のタブの URL に含まれる）

WATCH = REPO / "workspace/output/agent_output/T-20260920-003/login_watch"  # gitignore 対象
STATE = WATCH / "state.json"
LOG = WATCH / "keepalive.log.jsonl"
STATUS_MD = WATCH / "STATUS.md"
HEARTBEAT = WATCH / "heartbeat.txt"
STOP = WATCH / "STOP"
RESOLVED = WATCH / "resolved"

ERROR_TITLE_RE = re.compile(
    r"(^\s*(429|500|502|503|504)\b|\b(Error|エラー)\s*(429|500|502|503|504)\b|Too Many Requests|Service Unavailable|Bad Gateway|"
    r"アクセスが集中|メンテナンス|サイト障害|ただいま大変混み合って)", re.I)
MAX_BACKOFF = 8          # エラーが続いたら間隔を最大8倍まで広げる（§3.3-18 の安全側）
LOAD_TIMEOUT_S = 40


# ---------------------------------------------------------------- 純ロジック（テスト対象）

@dataclass
class Site:
    id: str
    name: str
    url: str
    host: str
    every_min: int
    hours: tuple[int, int]
    logout_url_re: str
    expect_in_title: str | None = None
    enabled: bool = True
    detectable: bool = True   # False＝URL でもタイトルでも切れが分からない（延命だけする）


def load_sites(path: Path = SITES_JSON) -> list[Site]:
    raw = json.loads(path.read_text(encoding="utf-8"))["sites"]
    return [Site(id=s["id"], name=s["name"], url=s["url"], host=s["host"],
                 every_min=int(s["every_min"]), hours=tuple(s.get("hours", [0, 24])),
                 logout_url_re=s["logout_url_re"], expect_in_title=s.get("expect_in_title"),
                 enabled=bool(s.get("enabled", True)),
                 detectable=bool(s.get("detectable", True)))
            for s in raw]


def host_path(url: str) -> str:
    """クエリとフラグメントを落とした host+path。ログに残すのはこれだけ。"""
    p = urllib.parse.urlsplit(url or "")
    host = p.hostname or ""
    return host + p.path


def in_hours(site: Site, now: datetime) -> bool:
    start, end = site.hours
    return start <= now.hour < end


def is_due(site: Site, last_reload_iso: str | None, backoff: int, now: datetime) -> bool:
    if not in_hours(site, now):
        return False
    if not last_reload_iso:
        return True
    last = datetime.fromisoformat(last_reload_iso)
    return now - last >= timedelta(minutes=site.every_min * max(1, backoff))


def classify(site: Site, url: str, title: str) -> str:
    """読み込み後の状態を1語で返す。

    logged_out    … ログイン画面に飛ばされた（URL で判定）
    wrong_account … Gmail などで、期待したアカウントでない
    error         … 503/429 などの応答（タイトルで判定）
    off_site      … 想定外のドメインにいる（社長がこのタブで別サイトを開いた等）
    unknown       … ログイン画面も同じ URL で出すサイト（国分）。延命はするが判定できない
    ok            … 上のどれでもない
    """
    hp = host_path(url)
    if re.search(site.logout_url_re, hp):
        return "logged_out"
    if title and ERROR_TITLE_RE.search(title):
        return "error"
    if not hp.startswith(site.host):
        return "off_site"
    if site.expect_in_title and "@" in (title or "") and site.expect_in_title not in title:
        return "wrong_account"
    if not site.detectable:
        return "unknown"   # 「OK」と書くと嘘になる。延命はしている
    return "ok"


def next_backoff(status: str, backoff: int) -> int:
    if status == "error":
        return min(MAX_BACKOFF, max(1, backoff) * 2)
    if status == "ok":
        return 1
    return max(1, backoff)


# ---------------------------------------------------------------- Chrome（AppleScript ラッパー）

def _osa(script: str, *args: str, timeout: int = 60) -> str:
    r = subprocess.run(["osascript", "-e", script, *args],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def chrome_running() -> bool:
    return subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True).returncode == 0


def chrome_pid() -> str:
    r = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True, text=True)
    return r.stdout.split()[0] if r.stdout.split() else ""


def find_marker_window() -> int | None:
    # 社長の他のウィンドウは「1枚目のタブの URL に印があるか」だけを見て、中身は Python に返さない
    out = _osa('''on run argv
  set marker to item 1 of argv
  tell application "Google Chrome"
    repeat with w in windows
      try
        if (URL of tab 1 of w) contains marker then return (id of w) as text
      end try
    end repeat
  end tell
  return ""
end run''', MARKER_NAME)
    return int(out) if out else None


def create_marker_window() -> int:
    out = _osa('''on run argv
  tell application "Google Chrome"
    set w to make new window
    set URL of active tab of w to (item 1 of argv)
    return (id of w) as text
  end tell
end run''', MARKER_FILE.as_uri())
    return int(out)


def list_tabs(win: int) -> list[dict]:
    out = _osa('''on run argv
  set out to ""
  tell application "Google Chrome"
    set w to window id ((item 1 of argv) as integer)
    repeat with t in tabs of w
      set ttl to title of t
      set out to out & (id of t) & (ASCII character 31) & (URL of t) & (ASCII character 31) & ttl & (ASCII character 31) & (loading of t) & (ASCII character 30)
    end repeat
  end tell
  return out
end run''', str(win))
    tabs = []
    for rec in out.split("\x1e"):
        parts = rec.split("\x1f")
        if len(parts) == 4:
            tabs.append({"id": int(parts[0]), "url": parts[1], "title": parts[2],
                         "loading": parts[3].strip() == "true"})
    return tabs


def new_tab(win: int, url: str) -> int:
    return int(_osa('''on run argv
  tell application "Google Chrome"
    set w to window id ((item 1 of argv) as integer)
    set t to make new tab at end of tabs of w with properties {URL:(item 2 of argv)}
    return (id of t) as text
  end tell
end run''', str(win), url))


def goto(win: int, tab: int, url: str | None) -> None:
    """url=None なら reload、あれば URL を開き直す（ログイン画面に居るタブを元のページへ戻す）。"""
    _osa('''on run argv
  tell application "Google Chrome"
    set t to tab id ((item 2 of argv) as integer) of window id ((item 1 of argv) as integer)
    if (count of argv) > 2 then
      set URL of t to (item 3 of argv)
    else
      reload t
    end if
  end tell
end run''', str(win), str(tab), *([url] if url else []))


def wait_loaded(win: int, tab: int) -> dict | None:
    time.sleep(3)
    deadline = time.time() + LOAD_TIMEOUT_S
    while time.time() < deadline:
        t = next((x for x in list_tabs(win) if x["id"] == tab), None)
        if t is None:
            return None
        if not t["loading"]:
            time.sleep(2)  # リダイレクトの2段目を待つ
            return next((x for x in list_tabs(win) if x["id"] == tab), t)
        time.sleep(2)
    return next((x for x in list_tabs(win) if x["id"] == tab), None)


def notify(title: str, body: str) -> None:
    subprocess.run(["osascript", "-e", f'display notification {json.dumps(body)} with title {json.dumps(title)} sound name "Ping"'],
                   capture_output=True)


# ---------------------------------------------------------------- 状態・ALERT

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"sites": {}}


def save_state(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def log(event: dict) -> None:
    event = {"at": datetime.now().isoformat(timespec="seconds"), **event}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def alert_path(key: str) -> Path:
    return WATCH / f"ALERT_{key}.txt"


def raise_alert(key: str, name: str, what: str, todo: str, last_ok: str | None) -> None:
    p = alert_path(key)
    if p.exists():
        return  # 同じ ALERT を書き直さない（通知も1回だけ）
    p.write_text(
        f"サイト: {name}\n状態: {what}\n検知: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"最後に OK だった時刻: {last_ok or '記録なし'}\n"
        f"社長の一手: {todo}\n"
        f"（ログインが戻れば、このファイルは次の巡回で resolved/ に移ります）\n",
        encoding="utf-8")
    notify("ログインが切れました", f"{name}：{what}")


def clear_alert(key: str) -> None:
    p = alert_path(key)
    if p.exists():
        RESOLVED.mkdir(exist_ok=True)
        p.rename(RESOLVED / f"{p.stem}_{datetime.now():%Y%m%d-%H%M}.txt")


def write_status(sites: list[Site], st: dict) -> None:
    lines = ["# ログイン延命の状態（自動生成・T-20260920-003）", "",
             f"更新: {datetime.now():%Y-%m-%d %H:%M}", "",
             "| サイト | 状態 | 最後に確認 | 最後に OK | 間隔 |", "|---|---|---|---|---|"]
    for s in sites:
        if not s.enabled:
            continue
        x = st["sites"].get(s.id, {})
        lines.append(f"| {s.name} | {LABEL.get(x.get('status'), '未確認')} | {x.get('checked_at', '-')} | "
                     f"{x.get('last_ok', '-')} | {s.every_min * x.get('backoff', 1)}分 |")
    alerts = sorted(p.name for p in WATCH.glob("ALERT_*.txt"))
    lines += ["", "ALERT: " + (", ".join(alerts) if alerts else "なし")]
    STATUS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 本体

TODO = {
    "logged_out": "延命ウィンドウのそのタブでログインし直す（『ログイン状態を保持』にチェック）",
    "wrong_account": "Gmail の u/1 が satoyselect でない。アカウントの並びを確認",
    "window": "延命ウィンドウが閉じられた。秘書に『延命ウィンドウを作り直して』と言う（setup）",
    "automation": "システム設定 > プライバシーとセキュリティ > オートメーション で Google Chrome を許可",
}
LABEL = {"ok": "OK", "logged_out": "🔴切れている", "wrong_account": "🔴別アカウント", "error": "相手側エラー（間隔を広げ中）",
         "off_site": "別ページ表示中", "unknown": "延命のみ（判定不可）"}
JP = {"logged_out": "ログイン画面に戻された", "wrong_account": "別のアカウントが開いている"}


def run(force_all: bool = False, allow_create: bool = False) -> int:
    WATCH.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
    if STOP.exists():
        return 0
    if not chrome_running():
        log({"event": "chrome_not_running"})
        return 0  # Chrome を勝手に起動しない

    sites = [s for s in load_sites() if s.enabled]
    st = load_state()
    now = datetime.now()

    try:
        win = find_marker_window()
    except RuntimeError as e:
        log({"event": "automation_error", "detail": str(e)[:200]})
        raise_alert("automation", "Chrome の自動操作", "Chrome を操作する許可がない", TODO["automation"], None)
        return 0
    clear_alert("automation")

    if win is None:
        # 社長が自分で閉じた場合に、10分ごとに出し直して邪魔をしない。
        # 作り直すのは setup のときと、Chrome が再起動した（pid が変わった）ときだけ。
        pid = chrome_pid()
        if allow_create or st.get("created_for_pid") != pid:
            win = create_marker_window()
            st["created_for_pid"] = pid
            log({"event": "window_created"})
        else:
            raise_alert("window", "延命ウィンドウ", "延命ウィンドウが見つからない", TODO["window"], None)
            save_state(st)
            return 0
    clear_alert("window")

    tabs = list_tabs(win)
    for s in sites:
        x = st["sites"].setdefault(s.id, {"backoff": 1})
        tab = next((t for t in tabs if host_path(t["url"]).startswith(s.host)
                    or (t["id"] == x.get("tab_id"))), None)
        if tab is None:
            tid = new_tab(win, s.url)
            x["tab_id"] = tid
            x["last_reload"] = now.isoformat(timespec="seconds")
            t = wait_loaded(win, tid)
        elif force_all or is_due(s, x.get("last_reload"), x.get("backoff", 1), now):
            x["tab_id"] = tab["id"]
            # ログイン画面や想定外のページに居るなら、元のページを開き直す（reload では戻れない）
            back = s.url if classify(s, tab["url"], tab["title"]) not in ("ok", "unknown") else None
            goto(win, tab["id"], back)
            x["last_reload"] = datetime.now().isoformat(timespec="seconds")
            t = wait_loaded(win, tab["id"])
        else:
            # 期限前は読み込み直さない（通信しない）。いまの URL だけ見て、
            # 社長がこのタブでログインし直した直後なら ALERT を早く下ろす。
            x["tab_id"] = tab["id"]
            t = tab

        if t is None:
            log({"site": s.id, "status": "tab_missing"})
            continue
        status = classify(s, t["url"], t["title"])
        if t is tab and status == x.get("status"):
            continue  # 読み込み直しておらず状態も同じ＝記録することがない
        x["status"] = status
        x["checked_at"] = datetime.now().strftime("%m-%d %H:%M")
        x["backoff"] = next_backoff(status, x.get("backoff", 1))
        log({"site": s.id, "status": status, "path": host_path(t["url"]), "backoff": x["backoff"]})
        if status == "ok":
            x["last_ok"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            clear_alert(s.id)
        elif status in ("logged_out", "wrong_account"):
            raise_alert(s.id, s.name, JP[status], TODO[status], x.get("last_ok"))
        # error / off_site は ALERT にしない（相手の障害・社長の操作）。STATUS.md には出る

    save_state(st)
    write_status(sites, st)
    return 0


def status() -> int:
    print(STATUS_MD.read_text(encoding="utf-8") if STATUS_MD.exists() else "まだ一度も走っていません")
    print("心拍:", HEARTBEAT.read_text().strip() if HEARTBEAT.exists() else "なし",
          "／停止中" if STOP.exists() else "")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        if cmd == "setup":
            sys.exit(run(force_all=True, allow_create=True))
        if cmd == "check":
            sys.exit(run(force_all=True))
        if cmd == "status":
            sys.exit(status())
        sys.exit(run())
    except Exception as e:  # launchd に異常終了を返さない（knowledge_launchd_always_on_jobs §2）
        WATCH.mkdir(parents=True, exist_ok=True)
        log({"event": "crash", "detail": f"{type(e).__name__}: {str(e)[:300]}"})
        sys.exit(0)
