#!/usr/bin/env python3
"""候補の供給源。「まだ判定していない ASIN」を取り出すところまでを受け持つ。

供給源は2つあります。

1. **既存の候補プール（0トークン・ネットワーク不要）**
   過去に NETSEA × Keepa で作った候補が `agent_output/T-20260920-003/apply21/*.json` と
   `deliverables/T-20260920-003/*.csv` に合計200件近く眠っています。
   ゲート通過率14.3%という実測はここから出た数字で、**まだ判定していない分が大半**です。
   卸値・卸率・卸サイトURL は `agent_output/` 側（Git 追跡外）にしかありません。

2. **NETSEA Buyer API で卸値を今の値に引き直す（0トークン）**
   プールの卸値は取得時点の値です。発注の提案に使うので、判定するぶんだけ引き直します。
   ⚠️ NETSEA で見つけたサプライヤーに NETSEA の外で連絡してはいけません（会員規約 第7条2項5号）。
   このモジュールは**価格の読み取りだけ**で、名簿を作りません。

公開の注意
----------
このリポは PUBLIC です。**卸値・卸率・ロット・卸サイトの商品URL は、このモジュールが
返す dict の中にだけ存在し、リポ内のファイルには書き出しません。**行き先はシートと
`agent_output/` だけです（`candidate_pipeline.py` の `--out-json` も agent_output 限定）。
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
TICKET = "T-20260920-003"
POOL_DIR = REPO / "workspace/output/agent_output" / TICKET
DELIV_DIR = REPO / "workspace/output/deliverables" / TICKET

# プール JSON（agent_output・Git 追跡外）。卸値つき。
# **新しいものを先に読む＝優先**（同じ ASIN は先に読んだ値を使う）。
POOL_JSON_FILES = (
    "apply21/rows_published.json",      # 9/30 発注候補26件（最新・人の目が入っている）
    "apply21/pool22.json",              # 9/30 入口60件
    "apply21/eval3_all.json",           # 9/30 評価80件
    "apply21/entry_pool.json",          # 9/30 入口71件
    "netsea19/relaxed_40.json",         # 9/29 条件を緩めた40件
    "netsea19/all_268.json",            # 9/29 NETSEA×Keepa 突合の全268件（最大の母数）
    "shoplist/final_rows.json",
    "shoplist/built.json",
)

# 成果物 CSV（Git 追跡下）。ASIN の供給だけに使う。
POOL_CSV_FILES = (
    ("19_今すぐ買える候補_NETSEA起点.csv", "ASIN"),
    ("21_申請前提の仕入れ候補リスト.csv", "ASIN"),
    ("22_発注する3SKU_入口60件.csv", "ASIN"),
    ("04_候補ASIN_ゲート実機確認リスト.csv", "ASIN"),
)


@dataclass
class Candidate:
    """1候補。Keepa に投げる前に分かっていること。"""

    asin: str
    jan: str = ""
    title: str = ""
    brand: str = ""
    category: str = ""
    sell: int | None = None              # 取得時点の Amazon 価格
    monthly_sold: int | None = None
    fee_pct: float | None = None         # 販売手数料率（税抜表示・Keepa 実測）
    fba_yen: int | None = None
    unit_cost_incl: int | None = None    # 1個あたり原価（税込）※シート/agent_output 限定
    pack: int = 1
    supplier: str = ""                   # 購入元の名前（企業名は公開可）
    supplier_url: str = ""               # ※シート/agent_output 限定
    source: str = ""                     # どのファイル由来か
    extra: dict = field(default_factory=dict)


def _int(v) -> int | None:
    try:
        if v in (None, "", "-"):
            return None
        return int(round(float(str(v).replace(",", "").replace("円", ""))))
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        if v in (None, "", "-"):
            return None
        return float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")


def _from_pool_row(r: dict, source: str) -> Candidate | None:
    asin = (r.get("asin") or "").strip()
    if not ASIN_RE.match(asin):
        return None
    return Candidate(
        asin=asin,
        jan=str(r.get("jan") or ""),
        title=r.get("title") or "",
        brand=r.get("brand") or "",
        category=r.get("cat") or "",
        sell=_int(r.get("sell")),
        monthly_sold=_int(r.get("ms") or r.get("monthlySold")),
        # 手数料率のキーは作った時期で `pct` / `fee_pct` に分かれている。両方見る。
        fee_pct=_float(r.get("pct") if r.get("pct") is not None else r.get("fee_pct")),
        fba_yen=_int(r.get("fba")),
        unit_cost_incl=_int(r.get("cost")),
        pack=_int(r.get("pack")) or 1,
        supplier=r.get("supplier") or r.get("supplier_name") or "",
        supplier_url=r.get("netsea_url") or "",
        source=source,
    )


def load_pool(pool_dir: Path = POOL_DIR, deliv_dir: Path = DELIV_DIR) -> list[Candidate]:
    """プール全部を読み、ASIN で重複排除して返す（先に読んだものを優先）。"""
    out: dict[str, Candidate] = {}

    for name in POOL_JSON_FILES:
        path = pool_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = data.values() if isinstance(data, dict) else data
        for r in rows:
            if not isinstance(r, dict):
                continue
            c = _from_pool_row(r, name)
            if c and c.asin not in out:
                out[c.asin] = c

    for name, col in POOL_CSV_FILES:
        path = deliv_dir / name
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except OSError:
            continue
        for r in rows:
            asin = (r.get(col) or r.get("asin") or "").strip()
            if not ASIN_RE.match(asin) or asin in out:
                continue
            out[asin] = Candidate(
                asin=asin,
                jan=str(r.get("JAN") or ""),
                title=r.get("商品名") or "",
                brand=r.get("ブランド") or "",
                category=r.get("カテゴリ") or "",
                sell=_int(r.get("Amazon現在価格") or r.get("現在の実売価格")),
                monthly_sold=_int(r.get("monthlySold")),
                fee_pct=_float(r.get("販売手数料率(実測)") or r.get("販売手数料率(税抜表示)")
                               or r.get("販売手数料率_税抜表示")),
                fba_yen=_int(r.get("FBA配送代行(円)")),
                supplier=r.get("卸元(NETSEA出展企業)") or r.get("仕入れ先") or "",
                source=name,
            )

    return list(out.values())


def refresh_wholesale_from_netsea(candidates: list[Candidate]) -> dict[str, dict]:
    """判定する候補だけ、NETSEA で卸値・在庫・ネット販売可否を今の値に引き直す。

    Keepa トークンは消費しません（別 API）。トークン／接続が無ければ空 dict を返し、
    プールの値をそのまま使います（**黙って落とさず、呼び出し側でログに出す**）。
    """
    import sys

    sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260521-005/code"))
    sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260831-006"))
    try:
        from adapters.netsea import (NetseaClient, PURPOSE_PROCUREMENT,  # noqa: E402
                                     assert_procurement_use)
        from pipeline.keepa_verify import load_env  # noqa: E402
    except ImportError as e:
        return {"_error": f"NETSEA アダプタを読めません: {e}"}

    assert_procurement_use(PURPOSE_PROCUREMENT)     # 用途の明示（法務判定 2026-08-31）
    load_env()
    client = NetseaClient()
    if not client.is_live:
        return {"_error": "NETSEA API に繋がりません（NETSEA_API_TOKEN 未設定）"}

    # shop_id ごとにまとめて1回だけ商品一覧を引く（API 呼び出しを最小に）。
    by_shop: dict[int, set[str]] = {}
    for c in candidates:
        m = re.search(r"/shop/(\d+)/", c.supplier_url or "")
        if m and c.jan:
            by_shop.setdefault(int(m.group(1)), set()).add(c.jan)

    fresh: dict[str, dict] = {}
    for shop_id, jans in by_shop.items():
        try:
            items, _cov = client.list_supplier_items_raw(shop_id, max_items=5000)
        except Exception as e:                       # noqa: BLE001 - 1社の失敗で全体を止めない
            fresh.setdefault("_warnings", []).append(f"shop {shop_id}: {e}")
            continue
        for it in items:
            for st in (it.get("set") or [{}]):
                jan = str(st.get("jan_code") or it.get("jan_code") or "").strip()
                if jan not in jans:
                    continue
                price = _int(st.get("price") or it.get("price"))
                if price is None:
                    continue
                prev = fresh.get(jan)
                if prev and prev["unit_price_excl"] <= price:
                    continue
                fresh[jan] = {
                    # NETSEA の price は **1個の値段（税抜）**。set_num は最小発注ロットの倍数。
                    "unit_price_excl": price,
                    "min_lot_units": _int(st.get("set_num") or it.get("set_num")) or 1,
                    "stock": st.get("stock_quantity", it.get("stock_quantity")),
                    "net_shop_ok": it.get("deal_net_shop_flag"),
                    "supplier_name": it.get("supplier_name") or "",
                }
    return fresh
