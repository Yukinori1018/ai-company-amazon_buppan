# -*- coding: utf-8 -*-
"""パイプライン本体。入力CSV → 正規化 → resolver 群 → マージ → 逐次保存 → CSV。

冪等・再開可能。同じコマンドを何度打っても、処理済みの社は飛ばして続きから走る。
やり直したい社だけ消したいときは state/records.jsonl から該当行を消せばよい
（追記のみのファイルなので、最後の行を足せば上書きにもなる）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
from typing import Dict, List, Optional

from . import resolvers as resolver_pkg
from .merge import merge
from .normalize import duplicate_groups, normalize_row
from .schema import MakerRow, to_csv_row
from .store import ContactStore
from .throttle import Throttle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)


def load_config(path: str = None) -> Dict:
    path = path or os.path.join(HERE, "config.json")
    with io.open(path, encoding="utf-8") as fp:
        return json.load(fp)


def load_input(csv_path: str, name_column: str) -> List[MakerRow]:
    """入力CSVを読んで正規化済み MakerRow の並びにする。"""
    with io.open(csv_path, encoding="utf-8-sig", newline="") as fp:
        raw_rows = list(csv.DictReader(fp))
    if raw_rows and name_column not in raw_rows[0]:
        raise KeyError(
            "列 '%s' が入力CSVにありません。実際の列: %s"
            % (name_column, list(raw_rows[0].keys()))
        )
    return [normalize_row(r[name_column], r) for r in raw_rows]


def select_resolvers(config: Dict) -> List:
    """config の enabled から resolver を取り出す。ネットワーク可否をここで門番する。"""
    chosen = []
    for name in config.get("enabled", []):
        resolver = resolver_pkg.get(name)
        if resolver.needs_network and not config.get("allow_network", False):
            raise RuntimeError(
                "resolver '%s' は外部アクセスを伴いますが allow_network=false です。"
                "法務(ハルオ)の適法性判定が出てから config.json を true にしてください。"
                % name
            )
        chosen.append(resolver)
    return chosen


def run(config: Dict = None, limit: int = None, out_dir: str = None, verbose=True) -> Dict:
    config = config or load_config()
    out_dir = out_dir or OUT_DIR

    input_csv = config["input_csv"]
    if not os.path.isabs(input_csv):
        input_csv = os.path.normpath(os.path.join(out_dir, input_csv))

    rows = load_input(input_csv, config["input_name_column"])
    chosen = select_resolvers(config)
    throttle = Throttle(
        {r.name: config.get("throttle", {}).get(r.name, r.min_interval_sec) for r in chosen},
        default_interval=config.get("default_throttle_sec", 3.0),
    )
    store = ContactStore(out_dir)

    total = len(rows)
    started = time.time()
    processed = skipped = 0
    status_every = int(config.get("status_every", 25))

    try:
        for i, row in enumerate(rows, 1):
            if store.is_done(row.raw_name):
                skipped += 1
                continue
            if limit is not None and processed >= limit:
                break

            results = []
            raw_dump = []
            for resolver in chosen:
                if not resolver.applies(row):
                    continue
                if resolver.needs_network:
                    throttle.wait(resolver.name)
                try:
                    contact = resolver.resolve(row)
                except Exception as exc:  # 1社のこけで全体を止めない
                    if verbose:
                        sys.stderr.write(
                            "[warn] %s / %s: %s\n" % (resolver.name, row.raw_name, exc)
                        )
                    continue
                if contact is None:
                    continue
                results.append((resolver.priority, contact))
                raw_dump.append(contact.to_dict())

            merged = merge(results)
            store.append(to_csv_row(row, merged), raw_results=raw_dump)
            processed += 1

            if verbose and processed % status_every == 0:
                store.write_status(
                    入力件数=total, 今回処理=processed, スキップ=skipped,
                    経過秒=round(time.time() - started, 1), 状態="running",
                )
                sys.stderr.write(
                    "[%d/%d] processed=%d skipped=%d\n" % (i, total, processed, skipped)
                )
    except KeyboardInterrupt:
        sys.stderr.write("\n中断しました。ここまでは保存済みです。再実行で続きから走ります。\n")

    for resolver in chosen:
        resolver.close()

    out_csv = os.path.join(out_dir, config.get("output_csv", "contacts_v1.csv"))
    store.write_csv(out_csv, order=[r.raw_name for r in rows])
    store.write_status(
        入力件数=total, 今回処理=processed, スキップ=skipped,
        経過秒=round(time.time() - started, 1), 状態="finished",
        使用resolver=[r.name for r in chosen], 出力=os.path.basename(out_csv),
        名寄せ取りこぼし=duplicate_groups(rows),
    )
    stats = store.fill_stats()
    if verbose:
        sys.stderr.write(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    return stats
