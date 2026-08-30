#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""エントリポイント。

  python3 run.py                 # config.json の設定で全件（処理済みはスキップ）
  python3 run.py --limit 20      # 動作確認用に20社だけ
  python3 run.py --resolvers A,B # config を無視して resolver を指定
  python3 run.py --list          # 登録済み resolver 一覧
  python3 run.py --rebuild-csv   # state から CSV を作り直すだけ（再取得しない）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import resolvers as resolver_pkg  # noqa: E402
from pipeline.runner import load_config, load_input, run, OUT_DIR  # noqa: E402
from pipeline.store import ContactStore  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="メーカー連絡先エンリッチメント")
    ap.add_argument("--limit", type=int, default=None, help="今回処理する最大件数")
    ap.add_argument("--resolvers", default=None, help="カンマ区切りで resolver を指定")
    ap.add_argument("--list", action="store_true", help="登録済み resolver 一覧")
    ap.add_argument("--rebuild-csv", action="store_true", help="state から CSV 再生成のみ")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    if args.list:
        for name in resolver_pkg.available():
            r = resolver_pkg.get(name)
            print("%-32s priority=%-4s network=%s applies_to=%s"
                  % (name, r.priority, r.needs_network, r.applies_to or "全分類"))
        return

    config = load_config(args.config)
    if args.resolvers:
        config["enabled"] = [s.strip() for s in args.resolvers.split(",") if s.strip()]

    if args.rebuild_csv:
        rows = load_input(
            os.path.normpath(os.path.join(OUT_DIR, config["input_csv"])),
            config["input_name_column"],
        )
        store = ContactStore(OUT_DIR)
        store.write_csv(os.path.join(OUT_DIR, config["output_csv"]),
                        order=[r.raw_name for r in rows])
        print(json.dumps(store.fill_stats(), ensure_ascii=False, indent=2))
        return

    run(config, limit=args.limit)


if __name__ == "__main__":
    main()
