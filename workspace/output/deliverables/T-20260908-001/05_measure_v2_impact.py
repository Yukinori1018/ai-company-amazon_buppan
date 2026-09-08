#!/usr/bin/env python3
"""#1 v1 → v2 の入れ替えで母数がどれだけ戻るかを実測する — T-20260908-001。

入力（いずれも Git 管理外・ローカルに実在）:
    ../T-20260831-006/out/candidates.csv      … 母数 26,942件
    ../T-20260831-006/out/keepa_facts.jsonl   … ブランド・カテゴリ・寸法（JAN で結合）

出力:
    標準出力に**集計値だけ**。商品名・卸値・Keepa の加工値は1つも出さない
    （本リポジトリは PUBLIC。T-20260904-004 の E / E2 判定に従う）。

実行:
    python3 05_measure_v2_impact.py
"""

import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1_DIR = HERE.parent / "T-20260904-004"
SCAN = HERE.parent / "T-20260831-006" / "out"

sys.path.insert(0, str(V1_DIR))
import risk_rules as RR                      # noqa: E402  v1（現行の判定）

_spec = importlib.util.spec_from_file_location("pse_rule_v2", HERE / "04_pse_rule_v2.py")
V2 = importlib.util.module_from_spec(_spec)
sys.modules["pse_rule_v2"] = V2
_spec.loader.exec_module(V2)                 # v2（本判定の提案）

csv.field_size_limit(10 ** 9)

# 後段フィルタの閾値。T-20260904-004 の budget_filter / build_order_sets と同じ値
MIN_PROFIT_RATE = 5.0
SKU_MIN_YEN, SKU_MAX_YEN = 5000, 10000
MIN_DROPS30 = 1


def load_facts() -> dict:
    facts = {}
    with open(SCAN / "keepa_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("found"):
                facts[d["jan"]] = d
    return facts


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def main():
    facts = load_facts()
    c = Counter()

    # candidates.csv は BOM 付き。utf-8 で開くと先頭列名が壊れて判定が静かに狂う
    with open(SCAN / "candidates.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            c["S0_母数"] += 1
            d = facts.get(r.get("JAN", ""), {})
            sellers = r.get("出品者数", "")
            v1 = RR.judge(
                netsea_name=r.get("商品名", ""),
                amazon_title=r.get("Amazon商品名", ""),
                brand=d.get("brand", ""),
                category_names=d.get("category_names"),
                description="",
                supplier_name=r.get("サプライヤー名", ""),
                description_available=False,
                package_mm=d.get("package_mm"),
                package_g=d.get("package_g"),
                seller_count=int(sellers) if str(sellers).strip().isdigit() else None,
            )
            pse = [x for x in v1.reasons if x.startswith("#1 ")]
            if not pse:
                continue
            c["v1_#1発火"] += 1
            if v1.rule_id.startswith("#1"):
                c["v1_#1が最初に触れた"] += 1
            if [x for x in v1.reasons if not x.startswith("#1 ")]:
                c["v1_#1以外にも触れている（#1が無くても落ちる）"] += 1
                continue
            c["v1_#1だけで落ちた（#1が支えていた分）"] += 1

            v2 = V2.judge_pse(
                netsea_name=r.get("商品名", ""),
                amazon_title=r.get("Amazon商品名", ""),
                brand=d.get("brand", ""),
                category_names=d.get("category_names"),
                supplier_name=r.get("サプライヤー名", ""),
            )
            c[f"v2_{v2.verdict}"] += 1
            if v2.verdict == "HARD":
                continue
            c[f"v2_非HARD_内訳_{v2.rule_id or '（規則に触れない）'}"] += 1

            rate = _f(r.get("利益率%"))
            buy = _f(r.get("NETSEA卸値(税込)"))
            drops = _f(r.get("月間販売数(30日ランク下落数)"))
            if not (rate >= MIN_PROFIT_RATE):
                continue
            if not (SKU_MIN_YEN <= buy <= SKU_MAX_YEN):
                continue
            c["最終_採算と単価帯を通過"] += 1
            if drops >= MIN_DROPS30:
                c["最終_回転も通過（発注候補に戻る件数）"] += 1
                c[f"最終_内訳_{v2.rule_id}"] += 1

    # ■検算: v1 の #1 発火は「他にも触れている」＋「#1だけ」に必ず割れる
    a = c["v1_#1以外にも触れている（#1が無くても落ちる）"] + c["v1_#1だけで落ちた（#1が支えていた分）"]
    if a != c["v1_#1発火"]:
        raise SystemExit(f"検算不一致: {a} != {c['v1_#1発火']}")
    lanes = c["v2_HARD"] + c["v2_REVIEW"] + c["v2_PASS"]
    if lanes != c["v1_#1だけで落ちた（#1が支えていた分）"]:
        raise SystemExit(f"検算不一致（レーン合計）: {lanes}")

    print(json.dumps(c, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
