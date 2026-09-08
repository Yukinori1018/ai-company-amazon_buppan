#!/usr/bin/env python3
"""入数の修正を、既存の母数とT-20260906-003の通過分に**再適用**する。

Keepa も NETSEA も叩き直しません。キャッシュ（keepa_facts.jsonl / candidates.csv）と
修正後の pipeline/pack.py・evaluate.py で**計算し直すだけ**です。

★ T-20260906-003 の out/ は**読むだけ**。走行中のジョブなので絶対に書きません。
"""
import csv, json, sys
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
SCAN = REPO / "workspace/output/deliverables/T-20260831-006"
RUN = REPO / "workspace/output/deliverables/T-20260906-003"   # 読み取り専用
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SCAN))

from pipeline import config, evaluate, keepa_verify, screen, pack  # noqa: E402

sys.path.insert(0, str(HERE))
import selection_rules as SEL  # noqa: E402

CFG = config.ScanConfig()
csv.field_size_limit(10 ** 9)


def load_facts():
    d = {}
    for line in (SCAN / "out/keepa_facts.jsonl").open():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("asin"):
            d[r["asin"]] = r
    return d


def to_facts(r):
    # AmazonFacts.package_mm の既定は () であって None ではない。
    # None を渡すと fba_size_key の sorted() が落ちる。
    mm = r.get("package_mm") or ()
    return keepa_verify.AmazonFacts(
        jan=r.get("jan") or "", asin=r.get("asin") or "",
        title=r.get("title") or "", found=bool(r.get("found")),
        price_yen=r.get("price_yen"), price_source=r.get("price_source") or "",
        sales_rank=r.get("sales_rank"), drops30=r.get("drops30"),
        drops90=r.get("drops90"), offer_count=r.get("offer_count"),
        availability_amazon=r.get("availability_amazon"),
        category_names=r.get("category_names") or [],
        package_mm=tuple(mm), package_g=r.get("package_g"),
    )


def to_cand(row):
    def i(x):
        try:
            return int(float((x or "0").replace(",", "")))
        except Exception:
            return 0
    return screen.Candidate(
        jan=row.get("JAN") or "", product_name=row.get("商品名") or "",
        supplier_id=i(row.get("サプライヤーID")) or 0,
        supplier_name=row.get("サプライヤー名") or "",
        product_url=row.get("NETSEA商品ページ") or "",
        wholesale_ex_tax=i(row.get("NETSEA卸値(税抜)")),
    )


def main():
    facts = load_facts()
    rows = list(csv.DictReader((SCAN / "out/candidates.csv").open(encoding="utf-8-sig")))
    print(f"母数 {len(rows):,} 行を再評価します")

    # T-20260906-003 の通過 ASIN（回転の検証を通ったもの）。**読むだけ。書かない。**
    #
    # ★ passed.jsonl を直接読む。summarize.py が作る candidates.csv は
    #   「最後に summarize を打った時点」のスナップショットなので、
    #   走行中はすぐ古くなる（915件時点のデータで作ったリストを出してしまった前科あり）。
    #   append-only なので重複しうる。asin で潰す。
    passed = set()
    pj = RUN / "out/passed.jsonl"
    if pj.exists():
        for line in pj.open():
            try:
                r = json.loads(line)
            except Exception:
                continue          # 走行中に読むので、最終行が千切れていることがある
            if r.get("ok") and r.get("asin"):
                passed.add(r["asin"])
    print(f"T-20260906-003 の通過 ASIN: {len(passed):,} 件（読み取りのみ・最新）")

    # ★②③通過（回転検証済み）だけを見た歩留まり。社長への報告はこちらが本筋。
    funnel = {}
    def drop(asin, why):
        if asin in passed:
            funnel[why] = funnel.get(why, 0) + 1

    before = {"利益率あり": 0, "入数未解決なのに数字が出ていた": 0}
    after = {"利益率あり": 0, "入数未解決で除外": 0, "要確認で除外": 0,
             "倍率が変わった": 0, "Amazon未出品/価格なし": 0, "赤字": 0}
    out = []
    for row in rows:
        asin = row.get("ASIN")
        f = facts.get(asin)
        if not f:
            continue
        # --- before（既存 CSV の値）------------------------------------------
        old_margin = (row.get("利益率%") or "").strip()
        old_reason = row.get("入数の根拠") or ""
        unresolved_old = ("確定できません" in old_reason) or ("食い違います" in old_reason)
        if old_margin not in ("", "-"):
            before["利益率あり"] += 1
            if unresolved_old:
                before["入数未解決なのに数字が出ていた"] += 1

        # --- after（修正後のロジックで計算し直す）-----------------------------
        ev = evaluate.evaluate(to_cand(row), to_facts(f), CFG)
        verdict = evaluate.overall_verdict(ev)
        if ev.result is None:
            if ev.review_reason:
                after["入数未解決で除外"] += 1
                drop(asin, "入数が解けない")
            else:
                after["Amazon未出品/価格なし"] += 1
                drop(asin, "Amazon未出品/価格なし")
            continue
        if ev.review_reason:            # 比率ガード等（数字は残るが並べ替えからは外す）
            after["要確認で除外"] += 1
            drop(asin, "要確認（売価が仕入の4倍超など）")
            continue
        after["利益率あり"] += 1

        # ── 選定条件（蛍光灯/Amazon本体/知財フラグ/PSE v2）────────────────
        sel = SEL.judge(
            netsea_name=row.get("商品名") or "",
            amazon_title=f.get("title") or "",
            brand=f.get("brand") or "",
            category_names=f.get("category_names") or [],
            supplier_name=row.get("サプライヤー名") or "",
            availability_amazon=f.get("availability_amazon"),
        )
        if sel.excluded:
            for why in sel.exclude_reasons:
                key = "選定除外: " + why.split("（")[0]
                after[key] = after.get(key, 0) + 1
            drop(asin, "選定除外: " + sel.exclude_reasons[0].split("（")[0])
            continue
        try:
            old_pack = int(float(row.get("出品の入数") or 1))
        except Exception:
            old_pack = 1
        if ev.pack_size != old_pack:
            after["倍率が変わった"] += 1
        if ev.result.net_profit <= 0:
            after["赤字"] += 1
            drop(asin, "赤字")
            continue
        out.append({
            "asin": asin, "jan": row.get("JAN") or "",
            "netsea_name": row.get("商品名") or "",
            "amazon_title": f.get("title") or "",
            "pack": ev.pack_size, "pack_reason": ev.pack_reason,
            "margin": ev.result.margin_rate, "net": ev.result.net_profit,
            "verdict": verdict, "supplier": row.get("サプライヤー名") or "",
            "url": row.get("Amazonページ") or "",
            "in_run": asin in passed,
            "flags": sel.flags,
            "pse_verdict": sel.pse_verdict,
            "pse_rule_id": sel.pse_rule_id,
            "pse_review_note": sel.pse_review_note,
            # ★通過＝発注可ではない。書類が揃うまで発注しない印。
            "requires_document_check": sel.requires_document_check,
        })

    print("\n■ before（既存 candidates.csv）")
    for k, v in before.items():
        print(f"  {k}: {v:,}")
    print("\n■ after（入数の修正後）")
    for k, v in after.items():
        print(f"  {k}: {v:,}")

    print(f"\n■ ②③通過 {len(passed):,} 件の歩留まり（社長報告はこちら）")
    tot = 0
    for k, v in sorted(funnel.items(), key=lambda x: -x[1]):
        print(f"  除外 {v:6,d}  {k}")
        tot += v
    print(f"  ---- 除外合計 {tot:,} / 母数に無い(Keepa未取得) "
          f"{len(passed) - tot - sum(1 for r in out if r['in_run']):,}")

    out.sort(key=lambda r: -r["margin"])
    json.dump(out, (HERE / "out/reevaluated.json").open("w"), ensure_ascii=False)
    print(f"\n利益が出て、かつ入数が解けている行: {len(out):,}")
    inrun = [r for r in out if r["in_run"]]
    print(f"  うち T-20260906-003 の回転検証も通っているもの: {len(inrun):,}")
    return out, inrun


if __name__ == "__main__":
    main()
