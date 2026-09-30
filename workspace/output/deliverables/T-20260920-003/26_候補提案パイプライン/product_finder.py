#!/usr/bin/env python3
"""Keepa Product Finder のラッパー — **B案（Amazon → NETSEA）の入口**。

なぜ向きを変えたか（2026-09-30 の実測）
--------------------------------------
A案は **NETSEA → Amazon**（「卸にあるものが Amazon で売れているか？」）だった。
生存ゲート導入後の55行で、**落ちた理由の85%が「市場が無い」**。
卸の棚のほとんどは Amazon に市場が無いので、**後段で捨てるためにトークンを払っていた**。

B案は **Amazon → NETSEA**（「売れている棚を、NETSEA で買えるか？」）。
**生存が入口の条件になる**ので、85%を捨てる工程そのものが消える。

⚠️ このモジュールでいちばん大事な注意
------------------------------------
**Keepa Product Finder は、知らないフィールドをエラーにせず黙って無視します。**
`{"bogusField_gte":1}` を投げても HTTP 200・`error:null` で返り、`totalResults` は
無条件検索と同じ件数になります。**綴りを1文字間違えると、フィルタが効かないまま
「条件どおり抽出できた」と誤認します。**（memory: knowledge_keepa_product_finder_fields）

だから `probe()` を置いてあります。**新しいフィールドを使う前に必ず通してください。**
1プローブ約11トークンで、数百トークンの無駄打ちと誤った結論を防げます。

トークン
--------
Finder の課金は **10 + 件数/100**。`perPage` は **1000 まで**通るので、
perPage=50 で20ページ回すのは perPage=1000 の1発に対して11倍の無駄です。
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

from keepa_client import KEEPA_DOMAIN_JP, KeepaError, load_api_key  # noqa: E402

QUERY_URL = "https://api.keepa.com/query"

# perPage の上限（実測で1000まで通る）。
MAX_PER_PAGE = 1000

# 除外するルートカテゴリ（規制・期限管理・危険物が絡むもの）。
# 本・DVD・ソフトウェア・ゲーム・食品・ドラッグストア・アルコール・ベビーフード。
# 期限管理と出品制限は後段のゲートでも見ますが、**入口で落とせるものは入口で落とす**。
EXCLUDE_ROOT_CATEGORIES = [
    465392,      # 本
    562002,      # ミュージック
    561958,      # DVD
    637394,      # ソフトウェア
    637630,      # テレビゲーム
    57239051,    # 食品・飲料・お酒
    160384011,   # ドラッグストア
    161669011,   # ビューティー（化粧品は期限・薬機法が絡む）
]


def _get(url: str, timeout: int = 300) -> dict:
    raw = urllib.request.urlopen(url, timeout=timeout).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def _call(selection: dict, api_key: str, domain: int = KEEPA_DOMAIN_JP) -> dict:
    url = (QUERY_URL + "?"
           + urllib.parse.urlencode({"key": api_key, "domain": domain,
                                     "selection": json.dumps(selection)}))
    data = _get(url)
    if data.get("error"):
        raise KeepaError(str(data["error"]))
    return data


def probe(field: str, value, baseline: dict | None = None,
          api_key: str | None = None) -> dict:
    """フィールドが**本当に効いているか**を確かめる。

    ベースラインの `totalResults` と、フィールドを1つ足したときの `totalResults` を比べます。
    **件数が動かなければ、そのフィールドは無視されています**（綴り違い・存在しない）。

    戻り値: {"field", "effective"(bool), "baseline", "with_field", "tokens"}
    """
    key = api_key or load_api_key()
    base = dict(baseline or {"productType": [0], "perPage": 50})
    base.setdefault("perPage", 50)
    b = _call(base, key)
    tokens = b.get("tokensConsumed") or 0

    probed = dict(base)
    probed[field] = value
    p = _call(probed, key)
    tokens += p.get("tokensConsumed") or 0

    return {
        "field": field,
        "baseline": b.get("totalResults"),
        "with_field": p.get("totalResults"),
        "effective": b.get("totalResults") != p.get("totalResults"),
        "tokens": tokens,
    }


def find(selection: dict, api_key: str | None = None,
         domain: int = KEEPA_DOMAIN_JP) -> tuple[list[str], int, int]:
    """Finder を1回叩く。戻り値は (ASIN リスト, totalResults, 消費トークン)。"""
    key = api_key or load_api_key()
    sel = dict(selection)
    sel["perPage"] = min(int(sel.get("perPage") or MAX_PER_PAGE), MAX_PER_PAGE)
    data = _call(sel, key, domain)
    return (data.get("asinList") or [],
            data.get("totalResults") or 0,
            data.get("tokensConsumed") or 0)


def selling_shelves(
    *,
    monthly_sold_min: int | None = 50,
    rank_max: int = 100_000,
    price_min: int = 2_000,
    price_max: int = 20_000,
    max_new_offers: int = 6,
    amazon_absent: bool = False,
    per_page: int = MAX_PER_PAGE,
    sort_field: str = "monthlySold",
) -> dict:
    """**売れている棚**の抽出条件を組む。B案の入口。

    順番に意味があります。**いちばん強い条件（実売がある）を入口に置く**。

    | 条件 | 何のためか | 後段で再判定するか |
    |---|---|---|
    | `monthlySold_gte` | **実売の積極的な根拠**（唯一の積極条件） | する（生存ゲート） |
    | `current_SALES_lte` | 死んでいないことの確認 | する |
    | `current_NEW` の帯 | 社長の単価下限・上限 | する（採算） |
    | `current_COUNT_NEW_lte` | 競合が少ない棚 | **必ずする**（Finder の索引と product の現在値は更新時刻が違う） |
    | ~~`current_AMAZON_lte=-1`~~ | **使わない**（実測で該当0件） | 本体の有無は後段の `outOfStockPercentage365` で判定 |
    | `categories_exclude` | 規制・期限管理・危険物 | する（要期限管理ゲート） |

    🔴 `current_AMAZON_lte=-1` は**使いません**（既定 `amazon_absent=False`）。
    2026-09-30 に実測したところ、このフィルタは **該当0件**を返します
    （Keepa は -1 を「データなし」の印に使っており、価格として比較できない）。
    **私の過去メモに「`current_AMAZON_gte/_lte=-1`（本体不在）」と書いてあったのは誤りでした。**
    プローブで気づけました。本体の有無は**後段の `outOfStockPercentage365`** で判定します
    （それが正しい方法でもある。memory: knowledge_amazon_presence_is_history_not_snapshot）。

    ⚠️ `monthly_sold_min` は **`monthlySold_gte` が有効だと実測できている場合だけ**使ってください。
    無効なら黙って無視されるので、`probe()` で確認してから。
    """
    sel: dict = {
        "productType": [0],                  # 0 = 通常商品（バリエーション親などを除く）
        "current_SALES_gte": 1,              # ランクが付いている＝売れた記録がある
        "current_SALES_lte": rank_max,
        "current_NEW_gte": price_min,        # domain=5 は円そのまま（×100 ではない）
        "current_NEW_lte": price_max,
        "current_COUNT_NEW_lte": max_new_offers,
        "categories_exclude": EXCLUDE_ROOT_CATEGORIES,
        "isAdultProduct": False,
        # 上限で丸める。`find()` 側でも丸めているが、**組み立てた時点で正しい値**にしておく
        # （selection を JSON に落として人が読む／保存することがあるため）。
        "perPage": min(int(per_page), MAX_PER_PAGE),
        "sort": [[sort_field, "desc"]],
    }
    if monthly_sold_min is not None:
        sel["monthlySold_gte"] = monthly_sold_min
    if amazon_absent:
        sel["current_AMAZON_lte"] = -1       # 本体のオファーが今は無い（前段フィルタ）
    return sel


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Keepa Product Finder の下調べ")
    ap.add_argument("--probe", nargs="*", default=[],
                    help="フィールドを field=value の形で並べる（有効かどうかを確かめる）")
    ap.add_argument("--count", action="store_true", help="抽出条件の該当件数だけ見る")
    a = ap.parse_args()

    if a.probe:
        total = 0
        for item in a.probe:
            f, _, v = item.partition("=")
            try:
                val = json.loads(v)
            except ValueError:
                val = v
            r = probe(f, val)
            total += r["tokens"]
            mark = "有効" if r["effective"] else "★無視されている★"
            print(f'{f:28} {mark}  baseline {r["baseline"]:,} → {r["with_field"]:,}')
        print(f"消費トークン {total}")
    if a.count:
        sel = selling_shelves(per_page=50)
        asins, total, tok = find(sel)
        print(f"該当 {total:,}件 / 取得 {len(asins)}件 / 消費 {tok}")
        print(json.dumps(sel, ensure_ascii=False))
