"""候補リストを止めずに積み上げ続ける常駐ジョブ（T-20260831-002）。

    止めたいとき:  touch "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14/STOP"

launchd（`com.aicompany.amazon-buppan.list-builder`）から起動されます。
このプロセスが落ちても launchd の KeepAlive が戻し、Mac を再起動しても RunAtLoad で戻ります。

## やっていること（1周のループ）

    STOP がある？          → 5分寝て見直す（＝止まるが死なない）
    ディスクが少ない？      → 1時間寝る
    自動停止した？          → 何もしない（次のセッションで社長に報告される）
    クールダウン中？        → 明けるまで寝る。明けたら次の周へ
    ↓
    scan_v14.py を6時間ぶん走らせる（掘り切った帯は --skip-bands で飛ばす）
    ↓
    progress.json を読んで周回状態へ畳み込む
    ↓
    日付が変わっていたら日次ロールアップ（0トークン）

## なぜ「6時間のセッション」を繰り返すのか（無制限に走らせない理由）

scan_v14 は起動のたびに各シャードの Finder ページを引き直します（1帯20トークン × 25帯 = 500トークン）。
補充は20/分＝1時間で1,200トークンなので、**1時間セッションだと4割が起動コストで消えます**。
6時間なら7%。一方、まったく再起動しないと日次ロールアップの区切りも自己修復の機会も無くなります。
6時間は「無駄を1割以下に抑えつつ、1日4回は健全性を確かめ直す」ための妥協点です。
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

# ★止める導線はここ1本だけ。scan_v14 と共有している（2つ作ると必ず片方を忘れる）。
STOP_FILE = V14 / "STOP"

STATE_DIR = HERE / "state"
STATE_FILE = STATE_DIR / "cycle.json"
LOCK_FILE = STATE_DIR / ".lock"
LOG = STATE_DIR / "always_on.log"
DAILY_DIR = HERE / "daily"

# --- 設定 -------------------------------------------------------------------
SESSION_HOURS = 6.0          # 1セッションの長さ（上のコメントの理由で6時間）
STOP_POLL_SEC = 300          # STOP がある間、何秒ごとに見直すか
DISK_POLL_SEC = 3600         # ディスク不足で待つ間隔
HALTED_POLL_SEC = 1800       # 自動停止中に寝る間隔
MIN_FREE_GB = 20.0           # 空きがこれを割ったら走らない
RAW_MAX_GB = 10.0            # 生レスポンスの保存上限（超えたら保存だけやめる・削除はしない）
TOKEN_STARVE_MINUTES = 240   # トークンが回復しないまま何分で1セッションを諦めるか
MAX_LOG_BYTES = 2 * 1024 ** 2
MAX_SCAN_LOG_BYTES = 20 * 1024 ** 2

_STOPPING = [False]


def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rotate(path: Path, limit: int) -> None:
    """ログを1本だけ残してローテートする（無人運転で無限に太らせない）。"""
    try:
        if path.exists() and path.stat().st_size > limit:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass


def load_state(now: dt.datetime) -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"WARN 状態ファイルが壊れています（{e}）。新規に作り直します")
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


def free_gb() -> float:
    return shutil.disk_usage(str(REPO)).free / 1024 ** 3


def read_session_result(before_mtime: float, returncode: int) -> dict:
    """スキャナ1セッションの結果を progress.json から読む。

    progress.json が更新されていなければ、スキャナは何も残さず落ちたということ。
    その場合は「異常終了」として数える（連続すると自動停止する）。
    """
    empty = {"ok": False, "exhausted": [], "processed": 0, "go": 0,
             "tokens": 0, "stop_reason": f"progress.json が更新されませんでした(rc={returncode})"}
    try:
        if not PROGRESS.exists() or PROGRESS.stat().st_mtime <= before_mtime:
            return empty
        p = json.loads(PROGRESS.read_text(encoding="utf-8"))
    except Exception as e:
        empty["stop_reason"] = f"progress.json を読めません: {e}"
        return empty
    counts = p.get("counts") or {}
    cursor = p.get("cursor") or {}
    return {
        "ok": returncode == 0,
        "exhausted": list(cursor.get("exhausted") or []),
        "processed": int(counts.get("processed") or 0),
        "go": int(counts.get("go") or 0),
        "tokens": int((p.get("keepa") or {}).get("tokens_consumed") or 0),
        "stop_reason": p.get("stop_reason") or "",
    }


def run_scanner(skip: list) -> dict:
    """scan_v14 を1セッション走らせる。戻り値は read_session_result の形。"""
    rotate(SCAN_LOG, MAX_SCAN_LOG_BYTES)
    before = PROGRESS.stat().st_mtime if PROGRESS.exists() else 0.0
    cmd = [sys.executable, str(SCANNER),
           "--max-hours", str(SESSION_HOURS),
           "--raw-max-gb", str(RAW_MAX_GB),
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

    deadline = time.time() + (SESSION_HOURS + 1) * 3600
    while proc.poll() is None:
        if _STOPPING[0]:
            log("SIGTERM を受けたのでスキャナを止めます")
            proc.terminate()
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        if time.time() > deadline:
            log("WARN スキャナが想定時間を1時間超えました。強制終了します")
            proc.terminate()
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        time.sleep(20)

    rc = proc.returncode if proc.returncode is not None else -1
    result = read_session_result(before, rc)
    log(f"スキャナ終了: rc={rc} 新規{result['processed']}件 候補{result['go']}件 "
        f"消費{result['tokens']}tok 理由「{result['stop_reason']}」")
    return result


def run_rollup() -> None:
    """日次ロールアップ（0トークン）。失敗しても本体は止めない。"""
    try:
        r = subprocess.run([sys.executable, str(HERE / "daily_rollup.py")],
                           cwd=str(HERE), capture_output=True, text=True, timeout=1800)
        log(f"日次ロールアップ rc={r.returncode} {（r.stdout or '').strip()[-300:] if False else (r.stdout or '').strip()[-300:]}")
        if r.returncode != 0:
            log(f"WARN ロールアップ stderr: {(r.stderr or '').strip()[-500:]}")
    except Exception as e:
        log(f"WARN ロールアップに失敗: {e}")


def sleep_interruptible(seconds: float) -> None:
    """SIGTERM で即座に抜けられる sleep（launchd の停止を待たせない）。"""
    end = time.time() + seconds
    while time.time() < end and not _STOPPING[0]:
        time.sleep(min(10, max(0.5, end - time.time())))


def on_term(signum, frame):  # noqa: ARG001
    _STOPPING[0] = True


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

        gb = free_gb()
        if gb < MIN_FREE_GB:
            log(f"WARN 空き容量が {gb:.1f}GB しかありません（下限 {MIN_FREE_GB}GB）。走りません")
            if once:
                return 0
            sleep_interruptible(DISK_POLL_SEC)
            continue

        if cs.maybe_start_new_cycle(state, now):
            log(f"クールダウンが明けました。{state['cycle']}周目を開始します"
                f"（掘り切り済みの印をリセット。seen_asins は残すので新規だけ積まれます）")
            save_state(state)

        reason = cs.pause_reason(state, now)
        if reason:
            log(reason)
            maybe_rollup(state, now)
            if once:
                return 0
            sleep_interruptible(HALTED_POLL_SEC)
            continue

        skip = cs.skip_bands(state, bands)
        result = run_scanner(skip)
        cs.note_session(state, result, bands, now=dt.datetime.now())
        save_state(state)

        warn = cs.yield_warning(state)
        if warn:
            log(f"WARN {warn}")
        if state.get("halted"):
            log(f"!! 自動停止しました: {state['halted']}")

        maybe_rollup(state, dt.datetime.now())
        if once:
            return 0
        sleep_interruptible(30)

    log("=== 停止シグナルを受けたので終了します（launchd が必要なら戻します）===")
    return 0


def maybe_rollup(state: dict, now: dt.datetime) -> None:
    today = now.strftime("%Y-%m-%d")
    if state.get("last_rollup_date") == today:
        return
    run_rollup()
    state["last_rollup_date"] = today
    save_state(state)


def main() -> int:
    ap = argparse.ArgumentParser(description="候補リスト常時稼働ジョブ")
    ap.add_argument("--once", action="store_true", help="1セッションだけ回して終わる（検証用）")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    # 多重起動防止。launchd は1本しか起こさないが、手動起動と衝突すると
    # Keepa のトークンを二重に食う（＝取得速度が半分になる）。
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("すでに別のプロセスが走っています。何もしません")
        return 0
    lock.write(str(os.getpid()))
    lock.flush()

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    return loop(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
