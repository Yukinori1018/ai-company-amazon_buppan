"""夜間無人フロー: スキャン完了(または締切)を検知して自動でGoogleシートを生成する。

判定:
  - shiire_summary.json が出現 → スキャン完走。シート生成して終了。
  - 締切 2026-08-04 09:30 を過ぎた → その時点のCSVでシート生成して終了(3000件は確保済み前提)。
  - どちらも未達 → 300秒スリープして再チェック。
sheet_url.txt にURLを残す。ログは watch.log。
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260803-001")
AGENT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260803-001")
SUMMARY = OUT / "shiire_summary.json"
CSV = OUT / "shiire_list_3000.csv"
WATCHLOG = OUT / "watch.log"
BUILDER = AGENT / "build_sheet_v3.py"
DEADLINE = datetime(2026, 8, 4, 9, 30, 0)


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(WATCHLOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def csv_rows():
    try:
        with open(CSV, encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except FileNotFoundError:
        return 0


def build():
    log("シート生成開始 …")
    r = subprocess.run([sys.executable, str(BUILDER)], capture_output=True, text=True)
    log("stdout:\n" + r.stdout)
    if r.returncode != 0:
        log("stderr:\n" + r.stderr)
        log("シート生成 失敗")
        return False
    log("シート生成 完了")
    return True


def main():
    log(f"watcher起動。締切={DEADLINE:%Y-%m-%d %H:%M} 監視対象={SUMMARY.name}")
    while True:
        rows = csv_rows()
        if SUMMARY.exists():
            log(f"スキャン完走を検知(CSV {rows}行)。")
            build()
            return
        if datetime.now() >= DEADLINE:
            log(f"締切到達(CSV {rows}行)。現時点のCSVでシート生成する。")
            build()
            return
        log(f"待機中: CSV {rows}行 / summary未出現。300秒スリープ。")
        time.sleep(300)


if __name__ == "__main__":
    main()
