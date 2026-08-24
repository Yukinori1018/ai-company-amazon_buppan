"""scan_v14 の見張り役（無人2段フローの2段目）。Keepa は一切叩かない。

やること3つだけ:

1. `v14/STATUS.md` を定期更新する（今どうなっているか・あと何時間で自動停止するか）
2. `build_report_v14.py` を定期実行する（走行中でも社長がリストを見られる）
3. スキャナが終わったら最終レポートを作り、`v14/FINISHED` を置いて自分も終わる

見張り自身にも締切がある（既定 `--deadline-hours 14`）。スキャナが12時間で止まる想定なので、
2時間の余裕を持たせている。見張りが永久に居座らないようにするための保険。

    python3 watch_v14.py --pid 12345
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import build_report_v14 as report

HERE = Path(__file__).resolve().parent
OUT = HERE / "v14"
PROGRESS = OUT / "progress.json"
STATUS = OUT / "STATUS.md"
FINISHED = OUT / "FINISHED"
LOG = OUT / "watch_v14.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def alive(pid: int) -> bool:
    """プロセスが生きているか。pid=0 なら「知らない」＝生きている扱い。"""
    if not pid:
        return True
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def write_status(pid: int, running: bool, max_hours: float) -> dict:
    prog = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    c = prog.get("counts") or {}
    k = prog.get("keepa") or {}
    elapsed = prog.get("elapsed_sec") or 0
    remain_h = max(max_hours - elapsed / 3600, 0)
    lines = [
        "# scan_v14 の現在地",
        "",
        f"更新: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 状態: **{'走行中' if running else '停止'}**（PID {pid or '不明'}）",
        f"- 停止理由: {prog.get('stop_reason') or '（まだ走っています）'}",
        f"- 経過: {prog.get('elapsed_hhmm', '—')} / 自動停止まで残り 約{remain_h:.1f}時間",
        "",
        "## 積み上がったもの",
        "",
        f"- 処理した商品: **{c.get('processed', 0)}件**",
        f"- 社長が連絡できる候補: **{c.get('go', 0)}件**",
        f"- メーカー: **{prog.get('makers_listed', 0)}社**",
        f"- 実セラー数を実測した商品: {c.get('offers_verified', 0)}件",
        f"- 安い判定で落とした: {c.get('rejected_cheap', 0)}件 / "
        f"実セラー1社で落とした: {c.get('rejected_seller', 0)}件",
        "",
        "## Keepa トークン",
        "",
        f"- 消費: **{k.get('tokens_consumed', 0)}** / 残: {k.get('tokens_left', '—')}",
        "- 上限1200・補充20/分。これが母数の天井を決めています。",
        "",
        "## 止めたいとき",
        "",
        f"    touch {OUT / 'STOP'}",
        "",
        "次のバッチの切れ目で安全に止まり、それまでの CSV はすべて残ります。",
        f"再開するときは STOP を消してから `python3 scan_v14.py`（取得済み ASIN は飛ばします）。",
        "",
        "## 見るもの",
        "",
        "- `v14/00_候補リスト.html` … 並べ替え・絞り込みできる一覧",
        "- `v14/00_サマリ.md` … 件数・分布・正直な注意",
        "- `v14/03_メーカー名寄せ.csv` … **連絡はここから**",
    ]
    STATUS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prog


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=0, help="見張るスキャナの PID")
    ap.add_argument("--interval", type=int, default=300, help="更新間隔（秒）")
    ap.add_argument("--deadline-hours", type=float, default=14.0,
                    help="見張り自身の締切（スキャナの12時間 + 余裕2時間）")
    ap.add_argument("--max-hours", type=float, default=12.0,
                    help="スキャナ側の自動停止時間（残り時間の表示に使う）")
    args = ap.parse_args()

    if FINISHED.exists():
        FINISHED.unlink()
    t0 = time.time()
    log(f"見張り開始 pid={args.pid} 間隔={args.interval}秒 締切={args.deadline_hours}時間")

    while True:
        running = alive(args.pid)
        prog = write_status(args.pid, running, args.max_hours)
        try:
            report.main()
        except Exception as e:                 # レポート生成の失敗で見張りを落とさない
            log(f"レポート生成でエラー（続行します）: {e}")

        if not running:
            log("スキャナが終了しました。最終レポートを作ります")
            break
        if time.time() - t0 > args.deadline_hours * 3600:
            log(f"見張りの締切 {args.deadline_hours} 時間に達したので降ります"
                "（スキャナはまだ動いている可能性があります）")
            break
        time.sleep(args.interval)

    write_status(args.pid, False, args.max_hours)
    try:
        report.main()
    except Exception as e:
        log(f"最終レポート生成でエラー: {e}")
    prog = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    FINISHED.write_text(json.dumps({
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stop_reason": prog.get("stop_reason"),
        "counts": prog.get("counts"),
        "keepa": prog.get("keepa"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"完了: {FINISHED}")


if __name__ == "__main__":
    main()
