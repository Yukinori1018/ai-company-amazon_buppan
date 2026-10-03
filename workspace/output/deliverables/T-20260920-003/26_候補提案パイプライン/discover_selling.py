#!/usr/bin/env python3
"""B案：**売れている棚から入り、NETSEA で買えるかを突合する**。

    python3 discover_selling.py --asins 200 --tokens 400

向きの違い（これが本体）
----------------------
A案（`discover.py`）は **NETSEA → Amazon**。「卸にあるものが Amazon で売れているか？」
→ 生存ゲート導入後の実測で、**落ちた理由の85%が「市場が無い」**。
　 卸の棚のほとんどは Amazon に市場が無く、**後段で捨てるためにトークンを払っていた**。

B案（このファイル）は **Amazon → NETSEA**。「売れている棚を、NETSEA で買えるか？」
→ **生存が入口の条件になる**ので、85%を捨てる工程そのものが消える。

A案は無駄ではありませんでした。A案が無ければ「85%が市場なしで落ちる」という数字が出ず、
向きが逆だと分からなかったし、**JAN 索引という突合先**も手に入りませんでした。

段取り（落とせる場所のうち一番早いところで落とす）
------------------------------------------------
| 段 | やること | トークン |
|---|---|---|
| 1 | Product Finder で「売れている棚」を抽出（月販50個以上・ランク10万位以内・オファー6社以下・規制カテゴリ除外） | **10 + 件数/100** |
| 2 | 商品を安く引いて JAN を得る（`offers` は付けない） | **1 / ASIN** |
| 3 | **JAN を NETSEA に突合**（索引優先・無ければライブ照会） | **0** |
| 4 | 採算（セット数を掛けてから）で赤字を落とす | **0** |
| 5 | 残ったものだけ §3.3 の本判定へ（`candidate_pipeline.py`・`offers` 付き） | 6 / ASIN |

**突合できなければ NO-GO ではなく UNKNOWN 相当**（買える先が他にあるかもしれない）。
このファイルは「NETSEA で買える候補」だけをプールに入れ、突合できなかった ASIN は
`agent_output/.../unmatched_selling.json` に残します（別の仕入れ先を探す材料）。

公開の注意: 卸値・卸サイトURL は戻り値と `agent_output/` のキャッシュにだけ入ります。
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import discover                                    # noqa: E402 - NETSEA 側は A案の実装を再利用
import product_finder                              # noqa: E402
import profit                                      # noqa: E402
import set_count                                   # noqa: E402
from candidate_pipeline import ALIVE_RANK, DEAD_RANK  # noqa: E402
from candidate_sources import REPO, Candidate, _int  # noqa: E402
from keepa_client import KEEPA_DOMAIN_JP, load_api_key  # noqa: E402

WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
UNMATCHED = WORK / "unmatched_selling.json"
# Finder＋安い取得の生レスポンス。**索引が育つたびに0トークンで突合し直せる**ようにする
# （memory: 条件変更のたびに Keepa を叩き直す設計にしてはいけない）。
RAW = WORK / "selling_raw.json"

# 1リクエストに載せる ASIN 数（Keepa の上限）。
ASIN_BATCH = 100

JAN_RE = re.compile(r"^\d{12,13}$")


def _get(url: str, timeout: int = 300) -> dict:
    raw = urllib.request.urlopen(url, timeout=timeout).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def fetch_cheap(asins: list[str], token_budget: int, api_key: str | None = None,
                log=print) -> tuple[list[dict], int]:
    """JAN と値段を得るための**安い**取得（`offers` を付けない＝1トークン/ASIN）。

    `offers` を付けると6トークン/ASIN になります。§3.3 の本判定は後段でやるので、
    ここでは「NETSEA に在るか」を調べるための最小限だけ取ります。
    """
    key = api_key or load_api_key()
    out: list[dict] = []
    consumed = 0
    i = 0
    while i < len(asins):
        room = token_budget - consumed
        allowed = int(room / 1.2)                  # 安全率（1件1トークンだが端数を見る）
        if allowed < 1:
            log(f"  トークン上限（{token_budget}）に達したので止めます（消費 {consumed}）")
            break
        chunk = asins[i:i + min(ASIN_BATCH, allowed)]
        i += len(chunk)
        url = ("https://api.keepa.com/product?"
               + urllib.parse.urlencode({"key": key, "domain": KEEPA_DOMAIN_JP,
                                         "asin": ",".join(chunk), "stats": 90}))
        data = _get(url)
        if data.get("error"):
            log(f"  Keepa エラー: {data['error']}")
            break
        out.extend(data.get("products") or [])
        consumed += data.get("tokensConsumed") or 0
        log(f"  商品 {i}/{len(asins)} 取得（累計 {consumed}トークン・残 {data.get('tokensLeft')}）")
        if i < len(asins):
            time.sleep(1.0)
    return out, consumed


def jans_of(product: dict) -> list[str]:
    codes = (product.get("eanList") or []) + (product.get("upcList") or [])
    return [str(c) for c in codes if JAN_RE.match(str(c))]


def match_netsea(products: list[dict], index: dict, client=None,
                 live_lookup_limit: int = 0, log=print) -> tuple[dict, list[dict]]:
    """Amazon の JAN を NETSEA に突合する。**Keepa トークンは使いません。**

    🔴 **突合は索引（`netsea_jan_index.json`）でやります。ライブ照会は使えません。**
    2026-09-30 に実測した結果、NETSEA `/items` の `supplier_ids` は **1件しか受け付けません**
    （3件で `400 too many supplier_ids.`）。承認済みサプライヤーは221社なので、
    **1 JAN の照会に221リクエスト**かかり、実用になりません。

    ⚠️ しかも共有アダプタ `adapters/netsea.py` の `search(jan_code=...)` は
    `_MAX_SUPPLIER_IDS_PER_REQUEST = 10` で投げるため**必ず 400 になり、
    そのまま黙ってサンプルデータへフォールバック**します。
    **NETSEA に確実に存在する JAN でも「0件」が返ってきます**（実測で確認）。
    私はこれを一度「Amazon の売れている棚は NETSEA に1件も無い」と読み違えかけました。
    `--live-lookups` は既定 0 のままにしてください（検証用に残してあります）。

    戻り値: ({asin: 卸情報}, 突合できなかった商品のリスト)
    """
    jan_index = index.get("jans") or {}
    matched: dict[str, dict] = {}
    unmatched: list[dict] = []
    live_used = 0

    for p in products:
        asin = p.get("asin")
        hit = None
        for jan in jans_of(p):
            if jan in jan_index:
                hit = dict(jan_index[jan]); hit["jan"] = jan
                break
        if hit is None and client is not None and live_used < live_lookup_limit:
            for jan in jans_of(p):
                live_used += 1
                try:
                    items = client.search(jan_code=jan, results=5)
                except Exception:                  # noqa: BLE001 - 1件の失敗で止めない
                    items = []
                if items:
                    it = items[0]
                    price = _int(getattr(it, "price", None))
                    if price:
                        hit = {"jan": jan, "unit_price_excl": price, "min_lot_units": 1,
                               "supplier_name": getattr(it, "store_name", "") or "",
                               "supplier_url": getattr(it, "url", "") or "",
                               "stock": None, "shop_id": None}
                    break
                if live_used >= live_lookup_limit:
                    break
        if hit:
            matched[asin] = hit
        else:
            unmatched.append({"asin": asin, "title": (p.get("title") or "")[:80],
                              "jans": jans_of(p),
                              "monthlySold": p.get("monthlySold")})
    log(f"  NETSEA 突合: {len(matched)}件 一致 / {len(unmatched)}件 見つからず"
        f"（索引 {len(jan_index):,} JAN・ライブ照会 {live_used}回）")
    return matched, unmatched


def to_candidates(products: list[dict], matched: dict, log=print) -> tuple[list[Candidate], dict]:
    """突合できた商品を候補にする。**ここで落とすのは赤字と死んだ棚だけ**（0トークン）。"""
    out: list[Candidate] = []
    tally = {"matched": len(matched), "dead": 0, "no_price": 0, "loss": 0,
             "unreadable_set": 0, "kept": 0}

    for p in products:
        asin = p.get("asin")
        w = matched.get(asin)
        if not w:
            continue
        st = p.get("stats") or {}
        cur = st.get("current") or []

        def at(i):
            v = cur[i] if isinstance(cur, list) and i < len(cur) else None
            return None if v in (None, -1) else v

        sell = next((v for v in (st.get("buyBoxPrice"), at(1), at(0))
                     if v and v > 0), None)
        fee_pct = p.get("referralFeePercent")
        if fee_pct in (None, -1):
            fee_pct = p.get("referralFeePercentage")
        fba = (p.get("fbaFees") or {}).get("pickAndPackFee")
        ms = p.get("monthlySold")
        ms = None if ms in (None, -1) else ms

        rank_now = at(3)
        avg90 = st.get("avg90") or []
        rank90 = avg90[3] if isinstance(avg90, list) and len(avg90) > 3 else None
        rank90 = None if rank90 in (None, -1) else rank90
        r = rank90 or rank_now
        if not ms and r and r > DEAD_RANK and not (rank_now and rank_now <= ALIVE_RANK):
            tally["dead"] += 1
            continue

        if not sell or fee_pct in (None, -1) or not fba:
            tally["no_price"] += 1
            continue

        multiplier, _note = set_count.cost_multiplier(p.get("title"))
        if multiplier is None:
            # セット数が読めない＝原価の倍率が確定できない。**落とさず後段で UNKNOWN にする。**
            tally["unreadable_set"] += 1
        else:
            e = profit.compute(sell, fee_pct, fba,
                               profit.unit_cost_incl_tax(w["unit_price_excl"]) * multiplier,
                               qty=1, monthly_sold=ms)
            if e.net_per_unit <= 0:
                tally["loss"] += 1
                continue

        tally["kept"] += 1
        out.append(Candidate(
            asin=asin, jan=w["jan"], title=(p.get("title") or "")[:120],
            brand=p.get("brand") or "", category="",
            sell=sell, monthly_sold=ms, fee_pct=float(fee_pct), fba_yen=int(fba),
            unit_cost_incl=profit.unit_cost_incl_tax(w["unit_price_excl"]),
            pack=w.get("min_lot_units") or 1,
            supplier=w.get("supplier_name") or "", supplier_url=w.get("supplier_url") or "",
            source="discover_selling/finder",
        ))

    log(f"  突合 {tally['matched']}件 → 生きている {tally['matched'] - tally['dead']}件"
        f"（売れていない {tally['dead']}件）→ 売価が付く "
        f"{tally['matched'] - tally['dead'] - tally['no_price']}件 → "
        f"**候補 {tally['kept']}件**（赤字 {tally['loss']}件・"
        f"セット数が読めない {tally['unreadable_set']}件は候補に残して後段で UNKNOWN）")
    return out, tally


def args_from_raw(a) -> bool:
    """`--from-raw` が指定され、かつ生レスポンスが在るか。"""
    return bool(getattr(a, "from_raw", False)) and RAW.exists()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="B案: 売れている棚 → NETSEA で買えるか")
    ap.add_argument("--asins", type=int, default=200, help="Finder から詳細を引く ASIN 数")
    ap.add_argument("--tokens", type=int, default=400, help="Keepa トークンの上限")
    ap.add_argument("--monthly-sold-min", type=int, default=50, help="月販の下限（実売の根拠）")
    ap.add_argument("--rank-max", type=int, default=100_000)
    ap.add_argument("--price-min", type=int, default=500,
                    help="売価の下限（円）。750円以下は販売手数料が5%なので捨てない")
    ap.add_argument("--price-max", type=int, default=20_000)
    ap.add_argument("--max-new-offers", type=int, default=6)
    ap.add_argument("--live-lookups", type=int, default=0,
                    help="（使えません。既定0のまま）共有アダプタの JAN 照会は "
                         "supplier_ids の上限違反で必ず 400 → サンプルへ黙ってフォールバックする")
    ap.add_argument("--sd-friendly", action="store_true",
                    help="**SD が強いカテゴリに絞る**。Amazon 起点で SD に当てるときはこれ。"
                         "2026-09-30 の実測で、絞らないと国内大手の化粧品・日用品に偏り"
                         "SD と一致しません（10件で0件）")
    ap.add_argument("--dry-run", action="store_true", help="件数だけ見て終了")
    ap.add_argument("--from-raw", action="store_true",
                    help="保存済みの生レスポンスで突合だけやり直す（**Keepa トークン0**）。"
                         "NETSEA 索引が育つたびにこれを回せばよい")
    a = ap.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)

    if args_from_raw(a):
        raw = json.loads(RAW.read_text(encoding="utf-8"))
        products = raw.get("products") or []
        print(f"保存済みの生レスポンス {len(products)}件で突合し直します（トークン0）")
        index = discover.load_index()
        matched, unmatched = match_netsea(products, index)
        cands, _tally = to_candidates(products, matched)
        cache = discover.load_cache()
        for c in cands:
            cache.setdefault("candidates", {})[c.asin] = c.__dict__
        discover.save_cache(cache)
        UNMATCHED.write_text(json.dumps(unmatched, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"\n候補 {len(cands)}件 / 消費トークン 0")
        for c in cands[:20]:
            print(f"  {c.asin} 売価{c.sell} 月販{c.monthly_sold} {c.title[:44]}")
        return 0

    # 1. Finder で「売れている棚」を抽出
    build = (product_finder.sd_friendly_shelves if a.sd_friendly
             else product_finder.selling_shelves)
    sel = build(
        monthly_sold_min=a.monthly_sold_min, rank_max=a.rank_max,
        price_min=a.price_min, price_max=a.price_max,
        max_new_offers=a.max_new_offers, per_page=min(a.asins, product_finder.MAX_PER_PAGE))
    # **絞ったつもりで絞れていない**のを黙って通さない（Finder は未知の項目を無視する）
    product_finder.warn_if_unproven(sel)
    asins, total, tok_finder = product_finder.find(sel)
    print(f"Product Finder: 該当 {total:,}件 → 取得 {len(asins)}件（{tok_finder}トークン）")
    if a.dry_run:
        return 0

    # 既に台帳/プールにあるものは除く（冪等）
    cache = discover.load_cache()
    known = set(cache.get("candidates") or {})
    asins = [x for x in asins if x not in known][:a.asins]
    print(f"未判定 {len(asins)}件を対象にします")

    # 2. 安く引いて JAN を得る（生レスポンスは必ず保存する）
    products, tok_cheap = fetch_cheap(asins, a.tokens - tok_finder)
    prev = []
    if RAW.exists():
        try:
            prev = (json.loads(RAW.read_text(encoding="utf-8")) or {}).get("products") or []
        except (OSError, ValueError):
            prev = []
    keep = {p.get("asin"): p for p in prev}
    keep.update({p.get("asin"): p for p in products})
    RAW.write_text(json.dumps({"products": list(keep.values()), "selection": sel},
                              ensure_ascii=False), encoding="utf-8")
    print(f"  生レスポンスを {RAW.name} に保存（累計 {len(keep)}件・--from-raw で0トークン再突合）")

    # 3. NETSEA に突合（0トークン）
    index = discover.load_index()
    client = None
    if a.live_lookups:
        client, why = discover.netsea_client()
        if client is None:
            print(f"ライブ照会は使えません: {why}")
    matched, unmatched = match_netsea(products, index, client, a.live_lookups)

    # 4. 採算と生存で落とす（0トークン）
    cands, tally = to_candidates(products, matched)

    # 5. プールへ（後段の candidate_pipeline.py が §3.3 の本判定をする）
    for c in cands:
        cache.setdefault("candidates", {})[c.asin] = c.__dict__
    discover.save_cache(cache)
    UNMATCHED.write_text(json.dumps(unmatched, ensure_ascii=False, indent=1), encoding="utf-8")

    total_tokens = tok_finder + tok_cheap
    print(f"\n新規候補 {len(cands)}件 / 消費トークン {total_tokens}"
          f"（Finder {tok_finder}＋商品 {tok_cheap}）")
    print(f"突合できなかった {len(unmatched)}件は {UNMATCHED.name} に保存"
          "（別の仕入れ先を探す材料。NO-GO ではありません）")
    for c in cands[:20]:
        print(f"  {c.asin} 売価{c.sell} 月販{c.monthly_sold} {c.title[:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
