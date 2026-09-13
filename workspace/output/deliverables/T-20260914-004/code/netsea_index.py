#!/usr/bin/env python3
"""NETSEA raw (T-20260831-006/out/netsea_items.jsonl, 2026-08-31 harvest) を規格単位の軽い索引にする。0 API call。"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
SRC = REPO / "workspace/output/deliverables/T-20260831-006/out/netsea_items.jsonl"
OUT = Path(__file__).parent / "netsea_specs.jsonl"
n_prod = n_spec = n_jan = 0
with open(SRC, encoding="utf-8") as f, open(OUT, "w", encoding="utf-8") as w:
    for line in f:
        d = json.loads(line); n_prod += 1
        top_jan = (d.get("jan_code") or "").strip()
        for s in d.get("set") or [{}]:
            jan = (s.get("jan_code") or "").strip() or top_jan
            n_spec += 1; n_jan += bool(jan)
            w.write(json.dumps({
                "sid": d.get("supplier_id"), "shop": d.get("shop_name"), "pid": d.get("product_id"),
                "url": d.get("product_url"), "name": d.get("product_name"), "label": s.get("label"),
                "spec": d.get("spec_size"), "jan": jan, "price": s.get("price"), "set_num": s.get("set_num"),
                "set_price": s.get("set_price"), "ref": s.get("reference_price"), "sold_out": s.get("sold_out_flag"),
                "net_ok": d.get("deal_net_shop_flag"), "direct": d.get("direct_send_flag"),
                "cat": d.get("category_id"), "upd": d.get("update_date"),
            }, ensure_ascii=False) + "\n")
print(n_prod, n_spec, n_jan)
