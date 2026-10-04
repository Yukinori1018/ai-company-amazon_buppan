#!/usr/bin/env python3
"""仕入れ前チェックの記録を付ける・見る・検査する CLI（T-20261004-001）。

    # 1項目を記録する（同じ項目を打ち直すと上書き。前の値は history に残る）
    python3 scripts/sourcing_gate/check_record.py set B01DBGGW8S gate_type \\
        --value "ブランド型・書類申請で開く" --result PASS \\
        --source "https://sellercentral-japan.amazon.com/productsearch/keywords/search?q=B01DBGGW8S" \\
        --by kazuyo [--date 2026-10-04] [--note "…"]

    # 記録を見る（spec の全項目を並べ、未記録・期限切れも表示）
    python3 scripts/sourcing_gate/check_record.py show B01DBGGW8S

    # 発注してよいか（全 required 項目が PASS かつ鮮度内なら exit 0、そうでなければ 1）
    python3 scripts/sourcing_gate/check_record.py verify B01DBGGW8S B008FIPMP2

    # 項目の一覧（id と取り方）
    python3 scripts/sourcing_gate/check_record.py items

記録の置き場は workspace/output/agent_output/_sourcing_checks/<ASIN>.json（.gitignore 済み）。
卸値・購入先 URL など会員限定の情報を value/source に書いてよいのはこのためです。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402


def cmd_items(_a) -> int:
    for it in gate.load_spec():
        print(f"{it.get('no', '-'):>2}. {it['id']:<22} {it['name']}（鮮度 {it['max_age_days']}日）")
        print(f"      取り方: {it.get('how', '')}")
        print(f"      落とす: {it.get('fail_if', '')}")
    return 0


def cmd_set(a) -> int:
    spec = {it["id"]: it for it in gate.load_spec()}
    if a.item_id not in spec:
        print(f"未知の項目 id です: {a.item_id}\n使える id: {', '.join(spec)}", file=sys.stderr)
        return 2
    asin = gate.normalize_asin(a.asin)
    day = a.date or date.today().isoformat()
    if gate._parse_day(day) is None:
        print(f"--date は YYYY-MM-DD で: {day}", file=sys.stderr)
        return 2
    if a.result == "PASS" and gate.UNRESOLVED_RE.search(a.value):
        print(f"値が「{a.value}」なのに PASS にはできません。UNKNOWN で記録してください。",
              file=sys.stderr)
        return 2
    rec = gate.load_record(asin)
    items = rec.setdefault("items", {})
    if a.item_id in items:
        rec.setdefault("history", []).append({"item_id": a.item_id, **items[a.item_id]})
    entry = {"value": a.value, "result": a.result, "source": a.source,
             "checked_at": day, "checked_by": a.by}
    if a.note:
        entry["note"] = a.note
    items[a.item_id] = entry
    rec["asin"] = asin
    p = gate.record_path(asin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"記録しました: {asin} [{a.item_id}] {spec[a.item_id]['name']} = {a.result}（{p}）")
    return 0


def cmd_show(a) -> int:
    spec = gate.load_spec()
    for asin in a.asins:
        asin = gate.normalize_asin(asin)
        rec = gate.load_record(asin)
        res = gate.evaluate(asin, spec=spec)
        bad = {p.item_id: p for p in res.problems}
        print(f"== {asin}  {'発注可' if res.ok else f'発注不可（{len(res.problems)}項目）'}")
        for it in spec:
            e = (rec.get("items") or {}).get(it["id"])
            mark = "OK " if it["id"] not in bad else "NG "
            if not e:
                print(f"  {mark}{it['id']:<22} {it['name']}: 未記録")
                continue
            why = f" ← {bad[it['id']].reason}" if it["id"] in bad else ""
            print(f"  {mark}{it['id']:<22} {it['name']}: {e.get('result')} "
                  f"「{e.get('value')}」 {e.get('checked_at')} {e.get('checked_by')}{why}")
            print(f"        出典: {e.get('source')}")
    return 0


def cmd_verify(a) -> int:
    spec = gate.load_spec()
    ng = 0
    for asin in a.asins:
        r = gate.evaluate(asin, spec=spec)
        if r.ok:
            print(f"OK  {r.asin}")
            continue
        ng += 1
        print(f"NG  {r.asin}（{len(r.problems)}項目）")
        for p in r.problems:
            print(f"      [{p.item_id}] {p.name}: {p.reason}" + (f"（{p.detail}）" if p.detail else ""))
    return 1 if ng else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="仕入れ前チェックの記録（T-20261004-001）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("set", help="1項目を記録する")
    s.add_argument("asin")
    s.add_argument("item_id")
    s.add_argument("--value", required=True)
    s.add_argument("--result", required=True, choices=gate.RESULTS)
    s.add_argument("--source", required=True, help="画面URLやデータ源（出典必須）")
    s.add_argument("--by", required=True, help="確認者（例: kazuyo / owner / takashi）")
    s.add_argument("--date", help="確認日 YYYY-MM-DD（既定: 今日）")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_set)

    for name, fn in (("show", cmd_show), ("verify", cmd_verify)):
        p = sub.add_parser(name)
        p.add_argument("asins", nargs="+")
        p.set_defaults(fn=fn)
    sub.add_parser("items").set_defaults(fn=cmd_items)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
