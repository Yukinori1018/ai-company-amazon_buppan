"""日次ロールアップ（T-20260831-002）。**Keepa を1回も叩きません＝0トークン。**

    python3 daily_rollup.py

やること:
  1. `scan_v14.py --rebuild` … メーカー名寄せ CSV を作り直す
  2. `build_report_v14.py`   … 00_サマリ.md と 00_候補リスト.html を作り直す
  3. `daily/YYYY-MM-DD.json` と `daily/latest.json` に増分を書く
  4. `v14/STATUS.md` を「常時稼働版」に書き換える（社長が最初に見るファイル）

`daily/latest.json` はセッション開始フック（.claude/hooks/session-start.sh）が読みます。
社長がセッションを開いた瞬間に「昨日 +◯件 / 累計◯件 / メーカー◯社 / 稼働中」が目に入る、
という導線のデータ源です。
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cycle_state as cs  # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
SCANNER_DIR = REPO / "workspace/output/deliverables/T-20260817-005"
V14 = SCANNER_DIR / "v14"
CSV_GO = V14 / "02_候補リスト_社長用.csv"
CSV_ALL = V14 / "01_候補プール_全件.csv"
CSV_MAKER = V14 / "03_メーカー名寄せ.csv"
STOP_FILE = V14 / "STOP"
STATUS = V14 / "STATUS.md"

STATE_FILE = HERE / "state/cycle.json"
DAILY_DIR = HERE / "daily"
LATEST = DAILY_DIR / "latest.json"


def count_rows(path: Path) -> int:
    """CSV の行数（ヘッダを除く）。数万行でも一瞬で、メモリに載せない。"""
    if not path.exists():
        return 0
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return max(0, n - 1)


def run(cmd: list, cwd: Path) -> int:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        print(f"WARN {' '.join(cmd[-2:])} rc={r.returncode}: {(r.stderr or '')[-300:]}")
    return r.returncode


def previous_totals() -> dict:
    if LATEST.exists():
        try:
            return json.loads(LATEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def status_line(state: dict, now: dt.datetime) -> str:
    if STOP_FILE.exists():
        return "停止中（STOP ファイルあり）"
    if state.get("halted"):
        return f"自動停止中: {state['halted']}"
    pause = cs.pause_reason(state, now)
    return pause or "稼働中"


def write_status_md(payload: dict) -> None:
    """社長が最初に開くファイル。**止め方を一番上に置く。**"""
    STATUS.write_text(f"""# 候補リストの現在地（常時稼働）

更新: {payload['generated_at']}

## 止めたいとき

    touch "{STOP_FILE}"

次のバッチの切れ目で安全に止まります。CSV はすべて残ります。再開は `rm` で消すだけです。

## 状態

| | |
|---|---|
| 稼働状態 | **{payload['status']}** |
| 昨日からの増分 | **候補 +{payload['delta']['go']}件 / メーカー +{payload['delta']['makers']}社** |
| 累計 | 候補 **{payload['totals']['go']}件** / メーカー **{payload['totals']['makers']}社** / 検査済 {payload['totals']['all']}件 |
| 周回 | {payload['cycle']}周目（{payload['cycles_completed']}周完了） |
| 掘り切ったシャード | {payload['exhausted']} / {payload['bands']}本 |

## 直近の1日

| 日付 | 新規取得 | 候補 | 消費トークン | 新規獲得率(件/1000tok) |
|---|---|---|---|---|
""" + "\n".join(
        f"| {r['date']} | {r['processed']} | {r['go']} | {r['tokens']} | {r['yield_per_1k']} |"
        for r in payload["recent"]) + f"""

{payload.get('warning') or '（新規獲得率は健全です）'}

## 見るもの

- `v14/00_候補リスト.html` … 並べ替え・絞り込みできる一覧
- `v14/03_メーカー名寄せ.csv` … **連絡はここから**
- `v14/00_サマリ.md` … 件数・分布・正直な注意

運用書: `workspace/output/deliverables/T-20260831-002/README.md`
""", encoding="utf-8")


def main() -> int:
    now = dt.datetime.now()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    # 0トークンの再生成2本。走行中に呼んでも安全（CSV を読むだけ・冪等）。
    run([sys.executable, str(SCANNER_DIR / "scan_v14.py"), "--rebuild"], SCANNER_DIR)
    run([sys.executable, str(SCANNER_DIR / "build_report_v14.py")], SCANNER_DIR)

    state = load_state()
    prev = previous_totals()
    totals = {"go": count_rows(CSV_GO), "all": count_rows(CSV_ALL),
              "makers": count_rows(CSV_MAKER)}
    prev_totals = prev.get("totals") or {}
    delta = {k: totals[k] - int(prev_totals.get(k) or 0) for k in totals}

    payload = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "status": status_line(state, now),
        "totals": totals,
        "delta": delta,
        "since": prev.get("date"),
        "cycle": state.get("cycle", 1),
        "cycles_completed": (state.get("totals") or {}).get("cycles_completed", 0),
        "exhausted": len(state.get("exhausted") or {}),
        "bands": 25,
        "recent": cs.daily_report(state, days=5),
        "warning": cs.yield_warning(state),
        "outputs": {"html": str(V14 / "00_候補リスト.html"), "makers": str(CSV_MAKER)},
    }

    (DAILY_DIR / f"{payload['date']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_status_md(payload)

    print(f"ロールアップ完了: 候補{totals['go']}件(+{delta['go']}) "
          f"メーカー{totals['makers']}社(+{delta['makers']}) 状態={payload['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
