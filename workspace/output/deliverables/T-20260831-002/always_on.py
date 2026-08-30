"""候補リストを止めずに積み上げ続ける常駐ジョブ（T-20260831-002）。

    止めたいとき:
    touch "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14/STOP"

launchd（`com.aicompany.amazon-buppan.list-builder`）から起動されます。
このプロセスが落ちても KeepAlive が戻し、Mac を再起動しても RunAtLoad で戻ります。

## 設計の下敷き

マサル（シミュレーター）のプレモーテム `A_プレモーテム_常駐スキャナ.md` の
必須要求 M1〜M12・停止条件 S1〜S10 に対応しています。特に効いているのは3つ。

- **M2**: Keepa の障害を「掘り切りました」と記録しない（`scan_v14.py` 側で対応）
- **M3/S5**: 依存が欠けたら再起動ループを作らず、`ALERT` を書いて **exit 0**
- **M6/S7**: Git 追跡ファイルが太ったら追記を止める（会社全体の自動同期を殺さない）

## やっていること（1周のループ）

    起動時に依存チェック（.env / Keepa キー / scan_v14 の import）
      → 欠けていたら ALERT を書いて exit 0（**再起動ループを作らない**）
    ↓
    STOP がある？          → 5分寝て見直す（止まるが死なない）
    ディスクが足りない？    → ALERT を書いて待つ
    Git 追跡ファイルが40MB超？ → ALERT を書いて停止（100MBの壁の手前で止める）
    停止した？              → 走らない。次セッションで秘書が ALERT に気づく
                              （母数の掘り尽くしもここ。**自動では再開しない**）
    ↓
    scan_v14.py を6時間ぶん走らせる（掘り切った帯は --skip-bands で飛ばす）
      心拍が10分止まったら子プロセスを殺す（S10）
    ↓
    progress.json を読んで周回状態へ畳み込む
    ↓
    日付が変わっていたら日次ロールアップ（0トークン）

## なぜ「6時間のセッション」を繰り返すのか（無制限に走らせない理由）

scan_v14 は起動のたびに各シャードの Finder ページを引き直します（1帯20トークン × 25帯 = 500）。
補充は20/分＝1時間で1,200トークンなので、**1時間セッションだと4割が起動コストで消えます**。
6時間なら7%。かといって再起動しないと、日次の区切りも自己修復の機会も無くなります。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cycle_state as cs  # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
SCANNER_DIR = REPO / "workspace/output/deliverables/T-20260817-005"
SCANNER = SCANNER_DIR / "scan_v14.py"
V14 = SCANNER_DIR / "v14"
PROGRESS = V14 / "progress.json"
SCAN_LOG = V14 / "scan_v14.log"
HEARTBEAT = V14 / "heartbeat.json"

# ★止める導線はここ1本だけ。scan_v14 と共有しています（2つ作ると必ず片方を忘れる）。
STOP_FILE = V14 / "STOP"
# ★異常はここ1本に集約。SessionStart フックがこれを拾って社長に見せます。
ALERT_FILE = V14 / "ALERT.md"

STATE_DIR = HERE / "state"
STATE_FILE = STATE_DIR / "cycle.json"
LOCK_FILE = STATE_DIR / ".lock"
LOG = STATE_DIR / "always_on.log"
DAILY_DIR = HERE / "daily"

# --- 設定 -------------------------------------------------------------------
# 1セッションの長さ（上のコメントの理由で6時間）。
# 環境変数で上書きできるのは**動作確認のため**。運用では触りません。
SESSION_HOURS = float(os.environ.get("LIST_BUILDER_SESSION_HOURS", "6.0"))
STOP_POLL_SEC = 300          # STOP がある間、何秒ごとに見直すか
BLOCKED_POLL_SEC = 1800      # 停止中に寝る間隔
MIN_FREE_GB = 50.0           # S6: 空きがこれを割ったら走らない
MAX_V14_GB = 20.0            # S6: v14/ の合計がこれを超えたら走らない
MAX_TRACKED_MB = 40.0        # S7: Git 追跡ファイルの上限（GitHub の100MB上限の手前）
HEARTBEAT_TIMEOUT_SEC = 600  # S10: 心拍が10分止まったら子プロセスを殺す
TOKEN_STARVE_MINUTES = 240   # トークンが回復しないまま何分で1セッションを諦めるか
MAX_LOG_BYTES = 2 * 1024 ** 2
MAX_SCAN_LOG_BYTES = 20 * 1024 ** 2

_STOPPING = [False]


def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def alert(title: str, detail: str) -> None:
    """異常を1ファイルに書く。SessionStart フックがこれを見つけて社長に知らせます。"""
    try:
        V14.mkdir(parents=True, exist_ok=True)
        ALERT_FILE.write_text(
            f"# ALERT — 候補リスト常時稼働ジョブ\n\n"
            f"発生: {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n\n## {title}\n\n{detail}\n\n"
            f"## 対応\n\n"
            f"1. `{LOG}` の末尾を見る\n"
            f"2. 直したら **このファイルを消してから** ジョブを起こし直す\n"
            f"   `launchctl kickstart -k gui/$(id -u)/com.aicompany.amazon-buppan.list-builder`\n"
            f"3. 課金・契約・削除が絡むなら、自分で判断せず秘書カズヨへ差し戻す（CLAUDE.md §4.1）\n",
            encoding="utf-8")
        log(f"!! ALERT: {title}")
    except OSError as e:
        log(f"!! ALERT を書けませんでした: {e}")


def rotate(path: Path, limit: int) -> None:
    """ログを1本だけ残してローテートする（無人運転で無限に太らせない）。"""
    try:
        if path.exists() and path.stat().st_size > limit:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass


# --- 起動前の依存チェック（M3 / S5）------------------------------------------
def preflight() -> list:
    """欠けている依存を列挙する。1つでもあれば走らせずに ALERT を書いて exit 0。

    night-shift.plist は存在しないスクリプトを14日間叩き続けて exit 127 を吐いていました。
    **同じ轍を踏まないための関門がここです。** 直せない依存で無限に再起動しないよう、
    問題があっても異常終了はせず 0 で終わります（KeepAlive の再起動ストームを作らない）。
    """
    problems = []
    if not SCANNER.exists():
        problems.append(f"スキャナがありません: {SCANNER}")
    env_ok = bool(os.environ.get("KEEPA_API_KEY")) or any(
        p.exists() for p in [Path.home() / ".config/ai-company-amazon-buppan/keepa.env",
                             REPO / "workspace/output/agent_output/T-20260521-005/code/.env"])
    if not env_ok:
        problems.append("Keepa の API キーが見つかりません "
                        "（~/.config/ai-company-amazon-buppan/keepa.env か "
                        "agent_output/T-20260521-005/code/.env）")
    if not problems:
        try:
            all_bands()
        except Exception as e:
            problems.append(f"scan_v14 を読み込めません: {type(e).__name__}: {e}")
    return problems


def load_state(now: dt.datetime) -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"WARN 状態ファイルが壊れています（{e}）。作り直します")
    return cs.new_state(now)


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def all_bands() -> list:
    """scan_v14 のシャード定義をそのまま使う（2箇所に書くと必ずズレる）。"""
    sys.path.insert(0, str(SCANNER_DIR))
    import scan_v14  # noqa: E402  import 時に .env を読むので Keepa キーが要る
    return [s[4] for s in scan_v14.shards()]


# --- 資源のガード（S6 / S7）--------------------------------------------------
def free_gb() -> float:
    return shutil.disk_usage(str(REPO)).free / 1024 ** 3


def dir_gb(path: Path) -> float:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total / 1024 ** 3


def oversized_tracked_file() -> str:
    """Git 追跡対象で 40MB を超えたファイル（S7）。

    GitHub の1ファイル100MB上限を超えると push が恒久的に失敗し、
    30分ごとの自動同期が丸ごと止まります（＝他エージェントの成果物も巻き添え）。
    半分の40MBで先に止めます。
    """
    try:
        out = subprocess.run(["git", "ls-files", "-z", "workspace/output/deliverables"],
                             cwd=str(REPO), capture_output=True, timeout=120)
        names = [n for n in out.stdout.decode("utf-8", "replace").split("\0") if n]
    except Exception:
        return ""
    for name in names:
        try:
            mb = (REPO / name).stat().st_size / 1024 ** 2
        except OSError:
            continue
        if mb > MAX_TRACKED_MB:
            return f"{name}（{mb:.1f}MB）"
    return ""


def resource_block() -> str:
    """走らせてはいけない資源上の理由。無ければ空文字。"""
    gb = free_gb()
    if gb < MIN_FREE_GB:
        return f"ディスクの空きが {gb:.1f}GB しかありません（下限 {MIN_FREE_GB}GB / S6）"
    if V14.exists() and dir_gb(V14) > MAX_V14_GB:
        return f"v14/ が {MAX_V14_GB}GB を超えました（S6）"
    big = oversized_tracked_file()
    if big:
        return (f"Git 追跡ファイルが {MAX_TRACKED_MB}MB を超えました: {big}（S7）。"
                "このまま100MBを超えると会社全体の自動同期が止まります")
    return ""


# --- スキャナ1セッション ------------------------------------------------------
def read_session_result(before_mtime: float, returncode: int) -> dict:
    """progress.json から結果を読む。更新されていなければ「異常終了」として扱う。

    ここを甘くすると、落ち続けているのに「正常」と記録され、自動停止が働きません。
    """
    empty = {"ok": False, "exhausted": [], "processed": 0, "go": 0, "tokens": 0,
             "stop_reason": f"progress.json が更新されませんでした(rc={returncode})"}
    try:
        if not PROGRESS.exists() or PROGRESS.stat().st_mtime <= before_mtime:
            return empty
        p = json.loads(PROGRESS.read_text(encoding="utf-8"))
    except Exception as e:
        empty["stop_reason"] = f"progress.json を読めません: {e}"
        return empty
    counts = p.get("counts") or {}
    cursor = p.get("cursor") or {}
    reason = p.get("stop_reason") or ""
    # ALERT が書かれた回は、rc が 0 でも「正常」とは数えない（M2 の締め）。
    ok = returncode == 0 and not ALERT_FILE.exists()
    return {
        "ok": ok,
        "exhausted": list(cursor.get("exhausted") or []),
        "processed": int(counts.get("processed") or 0),
        "go": int(counts.get("go") or 0),
        "tokens": int((p.get("keepa") or {}).get("tokens_consumed") or 0),
        "stop_reason": reason,
    }


def heartbeat_age() -> float:
    try:
        return time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        return 0.0      # まだ無い＝起動直後。ここでは殺さない


def run_scanner(skip: list) -> dict:
    """scan_v14 を1セッション走らせる。心拍が止まったら殺す（S10）。"""
    rotate(SCAN_LOG, MAX_SCAN_LOG_BYTES)
    before = PROGRESS.stat().st_mtime if PROGRESS.exists() else 0.0
    cmd = [sys.executable, str(SCANNER),
           "--max-hours", str(SESSION_HOURS),
           "--token-starve-minutes", str(TOKEN_STARVE_MINUTES)]
    if skip:
        cmd += ["--skip-bands", ",".join(skip)]
    log(f"スキャナ起動: {SESSION_HOURS}時間 / 飛ばす帯 {len(skip)}本")
    try:
        proc = subprocess.Popen(cmd, cwd=str(SCANNER_DIR),
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except Exception as e:
        log(f"ERROR スキャナを起動できません: {e}")
        return {"ok": False, "exhausted": [], "processed": 0, "go": 0,
                "tokens": 0, "stop_reason": f"起動失敗: {e}"}

    started = time.time()
    deadline = started + (SESSION_HOURS + 1) * 3600
    while proc.poll() is None:
        if _STOPPING[0]:
            log("SIGTERM を受けたのでスキャナを止めます")
            _kill(proc)
            break
        if time.time() > deadline:
            log("WARN スキャナが想定時間を1時間超えました。強制終了します")
            _kill(proc)
            break
        age = heartbeat_age()
        if time.time() - started > HEARTBEAT_TIMEOUT_SEC and age > HEARTBEAT_TIMEOUT_SEC:
            log(f"WARN 心拍が {age / 60:.0f}分止まっています。スキャナを止めます（S10）")
            alert("スキャナが応答しなくなりました",
                  f"心拍ファイルが {age / 60:.0f}分更新されていません（上限 "
                  f"{HEARTBEAT_TIMEOUT_SEC // 60}分）。強制終了しました。")
            _kill(proc)
            break
        time.sleep(20)

    rc = proc.returncode if proc.returncode is not None else -1
    result = read_session_result(before, rc)
    log(f"スキャナ終了: rc={rc} 新規{result['processed']}件 候補{result['go']}件 "
        f"消費{result['tokens']}tok 理由「{result['stop_reason']}」")
    return result


def _kill(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_rollup() -> None:
    """日次ロールアップ（0トークン）。失敗しても本体は止めない。"""
    try:
        r = subprocess.run([sys.executable, str(HERE / "daily_rollup.py")],
                           cwd=str(HERE), capture_output=True, text=True, timeout=1800)
        log(f"日次ロールアップ rc={r.returncode} {(r.stdout or '').strip()[-300:]}")
        if r.returncode != 0:
            log(f"WARN ロールアップ stderr: {(r.stderr or '').strip()[-500:]}")
    except Exception as e:
        log(f"WARN ロールアップに失敗: {e}")


def maybe_rollup(state: dict, now: dt.datetime) -> None:
    today = now.strftime("%Y-%m-%d")
    if state.get("last_rollup_date") == today:
        return
    run_rollup()
    state["last_rollup_date"] = today
    save_state(state)


def sleep_interruptible(seconds: float) -> None:
    """SIGTERM で即座に抜けられる sleep（launchd の停止を待たせない）。"""
    end = time.time() + seconds
    while time.time() < end and not _STOPPING[0]:
        time.sleep(min(10, max(0.5, end - time.time())))


def on_term(signum, frame):  # noqa: ARG001
    _STOPPING[0] = True


# --- 本体 -------------------------------------------------------------------
def loop(once: bool = False) -> int:
    bands = all_bands()
    log(f"=== 常時稼働ジョブ開始 シャード{len(bands)}本 / 1セッション{SESSION_HOURS}時間 ===")
    log(f"    止めるとき: touch '{STOP_FILE}'")

    while not _STOPPING[0]:
        rotate(LOG, MAX_LOG_BYTES)
        now = dt.datetime.now()
        state = load_state(now)

        if STOP_FILE.exists():
            log(f"STOP ファイルがあるので待機します（{STOP_POLL_SEC}秒ごとに見直し）")
            if once:
                return 0
            sleep_interruptible(STOP_POLL_SEC)
            continue

        # ALERT が残っている＝前回の異常を誰も見ていない。走らせずに待つ。
        if ALERT_FILE.exists():
            log(f"ALERT が残っています（{ALERT_FILE}）。人が確認して消すまで走りません")
            if once:
                return 0
            sleep_interruptible(BLOCKED_POLL_SEC)
            continue

        block = resource_block()
        if block:
            alert("資源のガードに引っかかりました", block)
            if once:
                return 0
            sleep_interruptible(BLOCKED_POLL_SEC)
            continue

        reason = cs.pause_reason(state, now)
        if reason:
            log(reason)
            maybe_rollup(state, now)
            if once:
                return 0
            sleep_interruptible(BLOCKED_POLL_SEC)
            continue

        result = run_scanner(cs.skip_bands(state, bands))
        cs.note_session(state, result, bands, now=dt.datetime.now())
        save_state(state)

        for warn in (cs.yield_warning(state), cs.intake_warning(state)):
            if warn:
                log(f"WARN {warn}")
        if state.get("halted"):
            title = ("母数を掘り尽くしたのでリサーチを終了しました"
                     if state.get("exhausted_at") else "ジョブが自分で止まりました")
            alert(title, state["halted"] + "\n\n"
                  + ("再開したくなったら `bash .claude/scripts/list-builder.sh resume-research`。"
                     if state.get("exhausted_at") else
                     "原因を直してから ALERT.md を消し、`list-builder.sh start`。"))

        maybe_rollup(state, dt.datetime.now())
        if once:
            return 0
        sleep_interruptible(30)

    log("=== 停止シグナルを受けたので終了します（launchd が必要なら戻します）===")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="候補リスト常時稼働ジョブ")
    ap.add_argument("--once", action="store_true", help="1セッションだけ回して終わる（検証用）")
    ap.add_argument("--preflight", action="store_true", help="依存チェックだけして終わる")
    ap.add_argument("--resume-research", action="store_true",
                    help="母数枯渇で止まった状態から次の周を始める（★社長の指示があるときだけ）")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    # M4/S8: 多重起動防止。launchd は1本しか起こしませんが、手動起動と衝突すると
    # Keepa のトークンを二重に食い、raw のファイル名を上書きし合います。
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("すでに別のプロセスが走っています。何もしません（S8）")
        return 0
    lock.write(str(os.getpid()))
    lock.flush()

    if args.resume_research:
        now = dt.datetime.now()
        state = cs.resume_research(load_state(now), now)
        save_state(state)
        ALERT_FILE.unlink(missing_ok=True)
        log(f"リサーチを再開します（{state['cycle']}周目）。"
            "掘り切りの印だけ消しました。seen_asins は残すので新規だけが積まれます")
        return 0

    problems = preflight()
    if problems:
        alert("依存が欠けているので起動しませんでした",
              "\n".join(f"- {p}" for p in problems)
              + "\n\n再起動ループを作らないよう、異常終了ではなく正常終了しています。")
        return 0        # ★ exit 0。KeepAlive の再起動ストームを作らない（S5）
    if args.preflight:
        log("依存チェック OK")
        return 0

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    try:
        return loop(once=args.once)
    except Exception as e:                       # noqa: BLE001
        import traceback
        alert("想定外の例外で止まりました", f"```\n{traceback.format_exc()[-2000:]}\n```")
        log(f"ERROR {e}")
        return 0        # ★ ここも exit 0


if __name__ == "__main__":
    sys.exit(main())
