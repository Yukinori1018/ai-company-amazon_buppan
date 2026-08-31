"""逐次保存と再開 — 電源断で成果物を失わないための層。

過去に電源断でスキャンを丸ごと失っています（T-20260804-001）。そこで学んだ形をそのまま使う:

    - 1件ごとに **append → flush() → os.fsync()**。バッファに溜めない
    - **壊れた最終行は読み飛ばして続行**。電源断は行の途中で切れる
    - **JSONL が正、CSV は派生物。** CSV はいつでも再生成できる
    - 「取得済み」に入れるのは **書き切ってから**（先に記録すると穴が空いて二度と拾えない）
"""

import csv
import json
import os
from pathlib import Path


class JsonlStore:
    """追記専用の JSONL。同じキーの行を後から追記すれば「後勝ち」で上書きになる。"""

    def __init__(self, path: Path, key: str):
        self.path = Path(path)
        self.key = key
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        """key → 行 の dict を返す。壊れた行は黙って飛ばす（電源断の名残）。"""
        out: dict = {}
        if not self.path.exists():
            return out
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # 途中で切れた最終行。ここで止まらないことが大事
                k = row.get(self.key)
                if k is not None:
                    out[str(k)] = row
        return out

    def append(self, rows) -> int:
        """行を追記して fsync する。戻り値は書いた件数。"""
        rows = list(rows)
        if not rows:
            return 0
        with open(self.path, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return len(rows)


def write_csv(path: Path, columns: list, rows: list) -> int:
    """CSV を書き出す（毎回まるごと再生成する。JSONL が正なので何度でも作り直せる）。

    Excel で開けるよう BOM 付き UTF-8。社長は Finder からダブルクリックで開きます。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
