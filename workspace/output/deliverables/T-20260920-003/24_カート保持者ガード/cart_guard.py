#!/usr/bin/env python3
"""発注前カート保持者ガード — CLAUDE.md §3.3 の3点チェックを機械で回す。

使い方
------
    # ASIN を直接
    python3 cart_guard.py B0DJNX12KZ B0FN3NWKYZ

    # CSV から（既定の列名は asin）
    python3 cart_guard.py --csv 候補.csv --asin-column ASIN

    # 生レスポンスを保存して、あとでトークン0で再判定
    python3 cart_guard.py B0DJNX12KZ --save-raw raw.json
    python3 cart_guard.py --from-json raw.json

    # 結果を CSV / JSON で出す
    python3 cart_guard.py --csv 候補.csv --out-csv 判定.csv --out-json 判定.json

出力は GO / NO-GO / **UNKNOWN** の3値です。**UNKNOWN は GO ではありません。**
1つでも未確認・判定不能なら GO になりません（fail-closed）。

公開の注意
----------
このリポは PUBLIC です。出力には Keepa の履歴由来の値（在庫切れ率・カート交代履歴）が
入るので、**出力先は `workspace/output/agent_output/` にしてください**。
`deliverables/` 配下への書き出しは既定で止めます（成果物08「Keepa 由来データの公開基準」B クラス）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from keepa_client import KeepaClient, KeepaError, estimate_tokens  # noqa: E402
from verdict import GO, NO_GO, UNKNOWN, Judgment, judge, judge_missing  # noqa: E402

MARK = {GO: "✅ GO", NO_GO: "⛔ NO-GO", UNKNOWN: "❓ UNKNOWN"}
STATUS_MARK = {"PASS": "○", "FAIL": "×", "UNKNOWN": "?"}

# 公開リポの成果物側に履歴由来の値を書かないためのガード。
PUBLIC_DIRS = ("workspace/output/deliverables/", "workspace/tickets/")


def _check_output_path(path: Path, allow_public: bool) -> None:
    p = str(path.resolve())
    if not allow_public and any(d.replace("/", "/") in p.replace("\\", "/") for d in PUBLIC_DIRS):
        raise SystemExit(
            f"出力先 {path} は Git 追跡下（PUBLIC）です。\n"
            "このツールの出力には Keepa の履歴由来の値が入ります。"
            "workspace/output/agent_output/ 配下を指定してください。\n"
            "（承知の上で書くなら --allow-public-output）")


def read_asins_from_csv(path: Path, column: str) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    if column not in rows[0]:
        raise SystemExit(f"CSV に列 '{column}' がありません。列: {list(rows[0])}")
    seen, out = set(), []
    for r in rows:
        a = (r.get(column) or "").strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def render(j: Judgment) -> str:
    lines = [f"{MARK[j.verdict]}  {j.asin}  {j.title}",
             f"    カート保持者: {j.cart_holder}"]          # ← 必ず1行目側に出す（§3.3）
    for c in j.checks:
        lines.append(f"    {STATUS_MARK[c.status]} {c.number}. {c.name}: {c.reason}")
    for w in j.warnings:
        lines.append(f"    ⚠ {w}")
    return "\n".join(lines)


def to_row(j: Judgment) -> dict:
    row = {"asin": j.asin, "verdict": j.verdict, "cart_holder": j.cart_holder,
           "title": j.title}
    for c in j.checks:
        row[f"check{c.number}_status"] = c.status
        row[f"check{c.number}_reason"] = c.reason
    ev3 = next((c.evidence for c in j.checks if c.number == 3), {})
    ev2 = next((c.evidence for c in j.checks if c.number == 2), {})
    row["live_new_offers"] = ev3.get("live_new_offer_count")
    row["distinct_sellers"] = ev3.get("distinct_sellers")
    row["amazon_among_sellers"] = ev3.get("amazon_among_sellers")
    row["fba_offers"] = ev3.get("fba_offers")
    row["fbm_offers"] = ev3.get("fbm_offers")
    row["amazon_instock_365_pct"] = ev2.get("amazon_instock_365_pct")
    row["amazon_instock_90_pct"] = ev2.get("amazon_instock_90_pct")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="発注前カート保持者ガード（CLAUDE.md §3.3）")
    ap.add_argument("asins", nargs="*", help="ASIN（スペース区切り）")
    ap.add_argument("--csv", type=Path, help="ASIN を含む CSV")
    ap.add_argument("--asin-column", default="asin", help="CSV の ASIN 列名（既定: asin）")
    ap.add_argument("--from-json", type=Path, help="保存済みの生レスポンスで再判定（トークン0）")
    ap.add_argument("--save-raw", type=Path, help="生レスポンスの保存先")
    ap.add_argument("--out-csv", type=Path, help="判定結果の CSV 出力先")
    ap.add_argument("--out-json", type=Path, help="判定結果の JSON 出力先（根拠つき）")
    ap.add_argument("--offers", type=int, default=20, help="取得するオファー数の上限（既定20）")
    ap.add_argument("--go-only", action="store_true", help="GO だけ表示する")
    ap.add_argument("--allow-public-output", action="store_true",
                    help="Git 追跡下への書き出しを許可する（既定は禁止）")
    ap.add_argument("--dry-run", action="store_true", help="トークン見積りだけ出して終了")
    args = ap.parse_args(argv)

    for p in (args.out_csv, args.out_json, args.save_raw):
        if p:
            _check_output_path(p, args.allow_public_output)

    asins = list(args.asins)
    if args.csv:
        asins += [a for a in read_asins_from_csv(args.csv, args.asin_column) if a not in asins]

    if args.from_json:
        raw = json.loads(args.from_json.read_text())
        products = raw.get("products", raw) if isinstance(raw, dict) else raw
        offers_requested = (raw.get("_offers_requested") if isinstance(raw, dict) else None) or args.offers
        if asins:
            products = [p for p in products if p.get("asin") in set(asins)]
        consumed, left = 0, None
    else:
        if not asins:
            ap.error("ASIN を指定するか --csv / --from-json を使ってください。")
        est = estimate_tokens(len(asins), args.offers)
        print(f"ASIN {len(asins)} 件 / トークン見積り 約{est}（実測 6/ASIN）", file=sys.stderr)
        if args.dry_run:
            return 0
        try:
            res = KeepaClient().fetch_for_cart_check(asins, offers=args.offers)
        except KeepaError as e:
            print(f"Keepa エラー: {e}", file=sys.stderr)
            return 2
        products, consumed, left = res.products, res.tokens_consumed, res.tokens_left
        offers_requested = res.offers_requested
        print(f"トークン消費 {consumed} / 残 {left}", file=sys.stderr)
        if args.save_raw:
            args.save_raw.parent.mkdir(parents=True, exist_ok=True)
            args.save_raw.write_text(json.dumps(
                {"products": products, "_offers_requested": offers_requested},
                ensure_ascii=False))

    by_asin = {p.get("asin"): p for p in products}
    targets = asins or list(by_asin)
    judgments = [judge(by_asin[a], offers_requested) if a in by_asin else judge_missing(a)
                 for a in targets]

    for j in judgments:
        if args.go_only and j.verdict != GO:
            continue
        print(render(j))
        print()

    tally = {v: sum(1 for j in judgments if j.verdict == v) for v in (GO, NO_GO, UNKNOWN)}
    print(f"— 合計 {len(judgments)} 件: GO {tally[GO]} / NO-GO {tally[NO_GO]} / "
          f"UNKNOWN {tally[UNKNOWN]}", file=sys.stderr)

    if args.out_csv:
        rows = [to_row(j) for j in judgments]
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(
            [{"asin": j.asin, "title": j.title, "verdict": j.verdict,
              "cart_holder": j.cart_holder,
              "checks": [{"number": c.number, "name": c.name, "status": c.status,
                          "reason": c.reason, "evidence": c.evidence} for c in j.checks]}
             for j in judgments], ensure_ascii=False, indent=2))

    # 終了コード: GO 以外が1件でもあれば 1（CI やシェルの && で止められるように）
    return 0 if tally[NO_GO] == 0 and tally[UNKNOWN] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
