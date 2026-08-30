# -*- coding: utf-8 -*-
"""逐次保存・冪等・再開可能な保管層。

T-20260804-001（3,282社スキャン）は電源断で中断し、後から再開対応に作り直した。
同じ轍を踏まないよう、**最初から**次を満たす:

  - 1社処理するたびに追記して flush + fsync（途中で落ちてもそこまで残る）
  - 処理済み（raw_name）は次回スキップ
  - 進捗は STATUS.json に随時書き出す
  - CSV はいつでも state から再生成できる（CSVは派生物であって正ではない）

正 = state/records.jsonl（追記のみ）。最後の行が勝つ（再取得時の上書きができる）。
"""
from __future__ import annotations

import io
import json
import os
import time
from typing import Dict, Iterable, List

from .schema import CSV_COLUMNS, FILL_FIELDS


class ContactStore:
    def __init__(self, out_dir: str, state_dirname: str = "state"):
        self.out_dir = out_dir
        self.state_dir = os.path.join(out_dir, state_dirname)
        os.makedirs(self.state_dir, exist_ok=True)
        self.records_path = os.path.join(self.state_dir, "records.jsonl")
        self.raw_results_path = os.path.join(self.state_dir, "raw_results.jsonl")
        self.status_path = os.path.join(self.state_dir, "STATUS.json")
        self._records: Dict[str, Dict[str, str]] = {}
        self._order: List[str] = []
        self.load()

    # --- 読み込み（再開の要） ---------------------------------------------
    def load(self) -> Dict[str, Dict[str, str]]:
        self._records.clear()
        self._order = []
        if not os.path.exists(self.records_path):
            return self._records
        with io.open(self.records_path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    # 電源断で最終行が欠けることがある。壊れた行は捨てて続行する
                    continue
                key = rec.get("メーカー名")
                if key is None:
                    continue
                if key not in self._records:
                    self._order.append(key)
                self._records[key] = rec  # 後勝ち
        return self._records

    def is_done(self, raw_name: str) -> bool:
        return raw_name in self._records

    def done_count(self) -> int:
        return len(self._records)

    def records(self) -> List[Dict[str, str]]:
        return [self._records[k] for k in self._order]

    # --- 書き込み（1件ずつ） -----------------------------------------------
    def append(self, csv_row: Dict[str, str], raw_results=None) -> None:
        key = csv_row["メーカー名"]
        if key not in self._records:
            self._order.append(key)
        self._records[key] = csv_row
        _append_jsonl(self.records_path, csv_row)
        if raw_results:
            _append_jsonl(
                self.raw_results_path,
                {"メーカー名": key, "results": raw_results, "ts": time.time()},
            )

    def write_status(self, **fields) -> None:
        payload = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        payload.update(fields)
        payload.update(self.fill_stats())
        _write_json(self.status_path, payload)

    # --- 集計 ---------------------------------------------------------------
    def fill_stats(self) -> Dict[str, object]:
        rows = self.records()
        total = len(rows)
        filled = sum(1 for r in rows if any((r.get(c) or "").strip() for c in FILL_FIELDS))
        per_field = {
            c: sum(1 for r in rows if (r.get(c) or "").strip()) for c in FILL_FIELDS
        }
        by_class: Dict[str, Dict[str, int]] = {}
        for r in rows:
            bucket = by_class.setdefault(r.get("分類", "?"), {"件数": 0, "埋まり": 0})
            bucket["件数"] += 1
            if any((r.get(c) or "").strip() for c in FILL_FIELDS):
                bucket["埋まり"] += 1
        return {
            "処理済み件数": total,
            "連絡先が1つ以上埋まった件数": filled,
            "埋まり率": round(filled / total, 4) if total else 0.0,
            "列別埋まり件数": per_field,
            "分類別": by_class,
        }

    # --- CSV 出力（state からの派生物） -------------------------------------
    def write_csv(self, path: str, order: Iterable[str] = None) -> str:
        import csv

        rows = self.records()
        if order is not None:
            index = {name: i for i, name in enumerate(order)}
            rows = sorted(rows, key=lambda r: index.get(r["メーカー名"], 10 ** 9))
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({c: r.get(c, "") for c in CSV_COLUMNS})
        os.replace(tmp, path)
        return path


def _append_jsonl(path: str, obj) -> None:
    with io.open(path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
        fp.flush()
        os.fsync(fp.fileno())


def _write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fp:
        json.dump(obj, fp, ensure_ascii=False, indent=2)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)
