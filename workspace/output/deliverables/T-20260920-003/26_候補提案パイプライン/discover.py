#!/usr/bin/env python3
"""供給の蛇口 — NETSEA の承認済みサプライヤーの商品を JAN で引き、Keepa で ASIN に当てる。

なぜこれが要るか（2026-09-30 の実走で判ったこと）
------------------------------------------------
既存の候補プール483件は、過去に作られた「その時の価格」の残りかすです。実走したら
**1回の10件中8件が今の価格では赤字**でした。判定は1件6トークン・90秒で回るのに、
判定に値する候補が尽きます。**詰まっているのは判定ではなく供給**です。

だからここで母数を作ります。順番は「NETSEA（0トークン）で絞ってから Keepa に投げる」。

トークンの実測（T-20260831-006）
--------------------------------
課金の単位は **「返ってきた商品数」× 1トークン**。投げた JAN の数ではありません。

| 投げた JAN | 返った商品 | tokensConsumed |
|---|---|---|
| 70件（全部ハズレ） | 0件 | **1** |
| 150件 | 95件 | 95 |

つまり **「NETSEA にあるが Amazon に無い商品」の仕分けは実質無料**です。
逆に、1つの JAN が複数 ASIN を返せば**その数だけ課金**されます（実測で残高がマイナスまで落ちた前例あり）。
だから走りながら実測レートで見積もり直し、上限で必ず止めます。

⛔ 用途制限（NETSEA バイヤー会員規約・法務判定 2026-08-31）
-----------------------------------------------------------
このモジュールは **NETSEA 内で買う商品を選ぶため**にだけ使います。
サプライヤーの社名を名簿化して外部で連絡・契約すれば第7条2項5号／第19条3項違反で、
違約金200万円＋代金の50%＋事業者名の公表の対象です。**企業名は「購入元の名前」欄止まり**。

公開の注意: 卸値・卸率・ロット・卸サイトの商品URL は**このモジュールの戻り値と
`agent_output/` のキャッシュにだけ**存在します。リポ内の成果物には書きません。
"""

from __future__ import annotations

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

import profit                                    # noqa: E402
import set_count                                 # noqa: E402
import seasonality                               # noqa: E402
import set_family                                # noqa: E402
from candidate_sources import REPO, Candidate, _int  # noqa: E402
from keepa_client import KEEPA_DOMAIN_JP, load_api_key  # noqa: E402

# Keepa の `code` パラメータの上限（1リクエストに載せる JAN 数）。
CODE_BATCH = 100

# JAN13 / UPC12。これ以外は投げない（ハズレでも1トークンは減る）。
JAN_RE = re.compile(r"^\d{12,13}$")

CACHE = REPO / "workspace/output/agent_output/T-20260920-003/pipeline/discovered.json"


# ── NETSEA 側（0トークン）────────────────────────────────────────────────


def netsea_client():
    """NETSEA クライアントを用途宣言つきで作る。繋がらなければ (None, 理由)。"""
    sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260521-005/code"))
    sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260831-006"))
    try:
        from adapters.netsea import (NetseaClient, PURPOSE_PROCUREMENT,
                                     assert_procurement_use)
        from pipeline.keepa_verify import load_env
    except ImportError as e:
        return None, f"NETSEA アダプタを読めません: {e}"
    assert_procurement_use(PURPOSE_PROCUREMENT)
    load_env()
    c = NetseaClient()
    if not c.is_live:
        return None, "NETSEA API に繋がりません（NETSEA_API_TOKEN 未設定）"
    return c, None


def scan_suppliers(client, shop_ids: list[int], max_items: int = 5000,
                   log=print) -> dict[str, dict]:
    """サプライヤーの商品を JAN 単位に畳む。**Keepa トークンは1つも使いません。**

    ここで落とすもの（0トークンで落とせるものは全部ここで落とす）:
      - ネットショップ販売不可（`deal_net_shop_flag != 'Y'`）＝ Amazon に出せない
      - JAN が無い／形が違う
      - 卸値が取れない
    同じ JAN が複数の口にあれば**安い方**を採ります。
    """
    found: dict[str, dict] = {}
    for shop_id in shop_ids:
        try:
            items, cov = client.list_supplier_items_raw(shop_id, max_items=max_items)
        except Exception as e:                       # noqa: BLE001 - 1社で全体を止めない
            log(f"  shop {shop_id}: 取得失敗 {e}")
            continue
        added = 0
        for it in items:
            if (it.get("deal_net_shop_flag") or "").upper() != "Y":
                continue
            for st in (it.get("set") or [{}]):
                jan = str(st.get("jan_code") or it.get("jan_code") or "").strip()
                if not JAN_RE.match(jan):
                    continue
                price = _int(st.get("price") or it.get("price"))
                if not price:
                    continue
                prev = found.get(jan)
                if prev and prev["unit_price_excl"] <= price:
                    continue
                # 🔴 2026-09-30 修正: フィールド名を2つ間違えていました。
                #    `item_url` → 正しくは **`product_url`**（公式スキーマ）。
                #    そのため `supplier_url` が全件空になり、§3.3-6（購入先URL が未確認なら
                #    GO にしない）で**全件が UNKNOWN に落ちていました**。
                #    `stock_quantity` → 正しくは **`set[].sold_out_flag`**（Y=品切れ/N=在庫あり）。
                #    在庫も全件 None でした。**列名から意味を推測した典型**
                #    （memory: knowledge_verify_field_semantics_not_names）。
                sold_out = (st.get("sold_out_flag") or it.get("sold_out_flag") or "").upper()
                found[jan] = {
                    "jan": jan,
                    "unit_price_excl": price,                       # ※1個の値段（税抜）
                    "min_lot_units": _int(st.get("set_num") or it.get("set_num")) or 1,
                    "stock": {"N": "在庫あり", "Y": "品切れ"}.get(sold_out, "未確認"),
                    "title": (it.get("product_name") or "").strip(),
                    "tax_class": st.get("consumption_tax_class",
                                        it.get("consumption_tax_class")),
                    "reference_price": _int(st.get("reference_price")),   # 上代（税抜）
                    "supplier_name": it.get("shop_name") or it.get("supplier_name") or "",
                    "supplier_url": it.get("product_url") or "",
                    "shop_id": shop_id,
                }
                added += 1
        log(f"  shop {shop_id}: 取得{cov.get('fetched', len(items))}件 → "
            f"ネット販売可でJANあり {added}件（累計 {len(found)}）")
    return found


# ── Keepa 側（JAN → ASIN）────────────────────────────────────────────────


def _get(url: str, timeout: int = 300) -> dict:
    raw = urllib.request.urlopen(url, timeout=timeout).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def resolve_to_asins(jans: list[str], token_budget: int, api_key: str | None = None,
                     log=print) -> tuple[dict[str, list[dict]], int]:
    """JAN を Keepa の `code` で逆引きして ASIN を得る。

    `offers` は付けません（§3.3 の判定は後段で改めて取るため。ここは当てるだけ）。
    戻り値は ({jan: [product, ...]}, 消費トークン)。

    **走りながら消費レートを測り、次のバッチが上限を超えるなら投げません。**
    固定値を信じてバッチを投げ続けると、残高がマイナスまで落ちます（実測の前例あり）。
    """
    key = api_key or load_api_key()
    codes = [j for j in dict.fromkeys(jans) if JAN_RE.match(j)]
    by_jan: dict[str, list[dict]] = {}
    consumed = 0
    rate = 1.0                                     # 1コードあたりの消費（走りながら更新）

    i = 0
    while i < len(codes):
        # 1つの JAN が複数 ASIN を返すので **1コード1トークンを上限だと思ってはいけない**
        # （実測: 100コードで149トークン ＝ 1.49/コード）。安全率を 1.6 で置き、
        # 走りながら実測レートに置き換える。**バッチの大きさを予算に合わせて縮める**のが要点で、
        # 「投げる前に判定するだけ」では 100件バッチが予算を飛び越えます（9/30 に一度やった）。
        room = token_budget - consumed
        safe_rate = max(rate, 1.6)
        allowed = int(room / safe_rate)
        if allowed < 1:
            log(f"  トークン上限（{token_budget}）に達したので止めます（消費 {consumed}）")
            break
        chunk = codes[i:i + min(CODE_BATCH, allowed)]
        i += len(chunk)
        url = ("https://api.keepa.com/product?"
               + urllib.parse.urlencode({"key": key, "domain": KEEPA_DOMAIN_JP,
                                         "code": ",".join(chunk), "stats": 90,
                                         # ⚠️ `history=1`。**課金は「返ってきた商品数」なので
                                         # トークンは増えません**（レスポンスは重くなる）。
                                         # これで `csv[3]`＝ランクの12ヶ月履歴が入り、
                                         # 「死んでいる棚」と「今が季節外の棚」を
                                         # **この段（追加トークン0）で区別できます**。
                                         # 入れないと、栽培キット型の棚をここで捨てます。
                                         "history": 1}))
        data = _get(url)
        if data.get("error"):
            log(f"  Keepa エラー: {data['error']}")
            break
        products = data.get("products") or []
        spent = data.get("tokensConsumed") or 0
        consumed += spent
        rate = max(0.1, consumed / max(1, i))
        for p in products:
            for code in (p.get("eanList") or []) + (p.get("upcList") or []):
                by_jan.setdefault(str(code), []).append(p)
        log(f"  JAN {i}/{len(codes)} → 商品 {len(products)}件 / "
            f"消費 {spent}（累計 {consumed}・実測 {rate:.2f}/コード・"
            f"残 {data.get('tokensLeft')}）")
        if i < len(codes):
            time.sleep(1.0)
    return by_jan, consumed


def _pick_best(products: list[dict]) -> dict:
    """1つの JAN に複数 ASIN がぶら下がったときに1件だけ選ぶ（**もう本線では使いません**）。

    🔴 2026-10-01: この関数が**まとめ売り突合を壊していた犯人**でした。
    JAN は単品とセット品で同一なので、`code` 逆引きは「×1 / ×3 / ×10 / ×200」の
    **ファミリを全部返しています**（実測: 4901670106107 の1リクエストで10 ASIN）。
    ここで1件だけ採ると、**固定費を割れる大きい口を全部捨てる**ことになります。
    しかも課金は「返ってきた商品数」なので、捨てた9件もすでに払っています。

    `to_candidates()` は `set_family.family_members()` で**全員を候補にします**。
    この関数はランク順の参考値が要る場所のために残してあるだけです。
    """
    def key(p):
        st = p.get("stats") or {}
        cur = st.get("current") or []
        rank = cur[3] if isinstance(cur, list) and len(cur) > 3 else -1
        return (0 if rank and rank > 0 else 1, rank if rank and rank > 0 else 10 ** 9)
    return sorted(products, key=key)[0]


def to_candidates(netsea: dict[str, dict], by_jan: dict[str, list[dict]],
                  log=print) -> tuple[list[Candidate], dict[str, int]]:
    """JAN×商品 → Candidate。**セット品ファミリの全員を候補にします。**

    🔴 2026-10-01 の作り直し。それまでは `_pick_best()` で **1 JAN = 1 ASIN** に絞っていました。
    ところが JAN は単品とセットで同一なので、絞った先はいつも単品でした。
    しかも「ランクが一番上位の1件」を採る実装で、**まとめ売りの口を全部捨てていました。**

    ⚠️ 2026-10-04 訂正: ここに「日用消耗品の単品は構造的に赤字（固定費821円/個）」と
    書いていましたが、**821円が間違い**でした（成果物33）。小型区分の実額は351円で、
    卸178円のたわしの損益分岐は約514円。**単品の方がむしろ成立しやすい**（体積が小さいので
    保管・納品送料・資材が安い）。口を全部見る理由は「単品が赤字だから」ではなく、
    **口ごとに売れ方も採算も違うから**です。

    `code` 逆引きの1レスポンスにファミリ全員が入っていて、**課金もすでに済んでいます**。
    だから `set_family.family_members()` で全員を候補にし、ゲートは**口ごとに**掛けます
    （単品が売れていてもセット品が売れていないことがあり、逆もあるため）。

    ここで落とすのは **0 追加トークンで落とせるものだけ**:
      - 生存（90日平均ランクが 50万位より下で月販も無い）… その口は死んでいる
      - 売価が付いていない（誰も売っていない）
      - 今の売価 × 今の卸値 × その口のセット数で**赤字**
    ①②（カート保持者・本体）は `offers` が要るので後段（cart_guard）です。
    """
    from candidate_pipeline import DEAD_RANK, ALIVE_RANK  # noqa: E402 - 定数の単一情報源

    out: list[Candidate] = []
    tally = {"jan": 0, "asin": 0, "no_price": 0, "loss": 0, "dead": 0, "kept": 0,
             "set_members": 0, "set_unknown": 0, "season_saved": 0}

    for jan, w in netsea.items():
        group = by_jan.get(jan)
        if not group:
            continue
        tally["jan"] += 1
        members = set_family.family_members(group)
        tally["set_members"] += max(0, len(members) - 1)
        unit_cost_1pt = profit.unit_cost_incl_tax(w["unit_price_excl"])

        for m in members:
            tally["asin"] += 1
            r = m.rank_avg90 or m.rank_now
            if (not m.monthly_sold and r and r > DEAD_RANK
                    and not (m.rank_now and m.rank_now <= ALIVE_RANK)):
                # 直近3ヶ月の販売実績が実質ゼロの口。**消極条件だけでは落ちない**ので、ここで落とす。
                # 🔴 ただし**「今が季節外」なだけの棚を混ぜない**（2026-10-01 カズヨ）。
                # ランクの12ヶ月履歴でピークが11〜1月なら、残して後段の人の確認に回す。
                sea = m.season
                if (sea is not None and sea.verdict == seasonality.SEASONAL
                        and sea.peaks_in_target()):
                    tally["season_saved"] += 1
                else:
                    tally["dead"] += 1
                    continue
            if not m.sell or m.fee_pct is None or not m.fba_yen:
                # 商品ページはあるが**誰も売っていない**口（売価・手数料・FBA のどれかが空）。
                # ⚠️ 手数料と FBA は**推定で埋めません**。埋めると採算が嘘になります。
                tally["no_price"] += 1
                continue

            sc = m.set_count
            if sc.n is None:
                tally["set_unknown"] += 1
            else:
                # **単位を揃えてから採算を見る。**Amazon の1個が卸の n 点なら原価は n 倍。
                e = profit.compute(m.sell, m.fee_pct, m.fba_yen,
                                   unit_cost_1pt * sc.n, qty=1,
                                   monthly_sold=m.monthly_sold)
                if e.net_per_unit <= 0 and sc.is_decided():
                    # 倍率が確定していて、なお赤字。ここは落としてよい。
                    tally["loss"] += 1
                    continue

            tally["kept"] += 1
            out.append(Candidate(
                asin=m.asin, jan=jan, title=m.title[:120],
                brand="", category="",
                sell=m.sell, monthly_sold=m.monthly_sold,
                fee_pct=float(m.fee_pct), fba_yen=int(m.fba_yen),
                unit_cost_incl=unit_cost_1pt, pack=w["min_lot_units"],
                supplier=w["supplier_name"], supplier_url=w["supplier_url"],
                source="discover/netsea",
                extra={"rank_now": m.rank_now, "rank_avg90": m.rank_avg90,
                       "amazon_set_count": sc.n,
                       "set_confidence": sc.confidence,
                       "set_sources": sc.sources,
                       "package_quantity": m.package_quantity,
                       "number_of_items": m.number_of_items,
                       "season": (m.season.verdict if m.season else None),
                       "season_peaks": (list(m.season.peak_months) if m.season else []),
                       "season_label": (m.season.label() if m.season else ""),
                       "review_count": m.review_count,
                       "family_jan": jan, "family_size": len(members),
                       "parent_asin": m.parent_asin,
                       "wholesale_per_point_incl": unit_cost_1pt},
            ))

    log(f"  JAN が Amazon に当たった {tally['jan']}件 → "
        f"セット品ファミリを含む口 {tally['asin']}件（単品以外 {tally['set_members']}件）→ "
        f"生きている口 {tally['asin'] - tally['dead']}件（死んでいる {tally['dead']}件）→ "
        f"売価が付く {tally['asin'] - tally['dead'] - tally['no_price']}件"
        f"（出品なし {tally['no_price']}件）→ "
        f"**候補 {tally['kept']}件**（赤字で落とした {tally['loss']}件・"
        f"セット数が読めず人に回す {tally['set_unknown']}件・"
        f"🔴季節外として残した {tally['season_saved']}件）")
    return out, tally


# ── キャッシュ（走るたびに続きから）──────────────────────────────────────


def load_cache(path: Path = CACHE) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"scanned_shops": [], "candidates": {}}


def save_cache(cache: dict, path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def cached_candidates(cache: dict) -> list[Candidate]:
    return [Candidate(**c) for c in cache.get("candidates", {}).values()]


def discover(shops_per_run: int = 8, token_budget: int = 150,
             cache_path: Path = CACHE, log=print) -> tuple[list[Candidate], int, dict]:
    """1回ぶんの発掘。**前回の続きのサプライヤーから**スキャンします。

    戻り値は (新しく見つかった候補, 消費トークン, サマリ)。
    """
    cache = load_cache(cache_path)
    client, why = netsea_client()
    if client is None:
        log(f"発掘をスキップ: {why}")
        return [], 0, {"error": why}

    suppliers = client.list_suppliers()
    all_ids = [int(s["id"]) for s in suppliers if str(s.get("id", "")).isdigit()]
    done = set(cache.get("scanned_shops") or [])
    todo = [i for i in all_ids if i not in done][:shops_per_run]
    log(f"承認済みサプライヤー {len(all_ids)}社（済 {len(done)}社）→ 今回 {len(todo)}社をスキャン")
    if not todo:
        log("全サプライヤーをスキャン済みです（キャッシュを消せば再スキャンします）。")
        return [], 0, {"exhausted": True}

    netsea = scan_suppliers(client, todo, log=log)
    known_jans = {c.get("jan") for c in cache.get("candidates", {}).values()}
    fresh = {j: w for j, w in netsea.items() if j not in known_jans}
    log(f"NETSEA から JAN {len(netsea)}件（うち未判定 {len(fresh)}件）")

    by_jan, tokens = resolve_to_asins(list(fresh), token_budget, log=log)
    cands, tally = to_candidates(fresh, by_jan, log=log)

    cache["scanned_shops"] = sorted(done | set(todo))
    for c in cands:
        cache.setdefault("candidates", {})[c.asin] = c.__dict__
    save_cache(cache, cache_path)

    return cands, tokens, {"shops": todo, "jans": len(fresh), **tally}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NETSEA → Keepa で候補 ASIN を発掘する")
    ap.add_argument("--shops", type=int, default=8, help="今回スキャンするサプライヤー数")
    ap.add_argument("--tokens", type=int, default=150, help="Keepa トークンの上限")
    a = ap.parse_args()
    cands, tokens, summary = discover(a.shops, a.tokens)
    print(f"\n新規候補 {len(cands)}件 / 消費トークン {tokens}")
    for c in cands[:20]:
        print(f"  {c.asin} 売価{c.sell} 月販{c.monthly_sold} {c.title[:44]}")


# ── NETSEA の JAN 索引（B案の突合先）──────────────────────────────────────

# ⚠️ 2026-09-30 の反省: `discover()` は JAN 14,672件を集めたのに、**保存していなかった**
# （`candidates` だけ保存していた）。B案（Amazon → NETSEA）では、この JAN 索引が突合先そのもの。
# 集めたものは捨てない。Keepa トークンは1つも使わないので、作り直しは時間だけで済む。
INDEX = REPO / "workspace/output/agent_output/T-20260920-003/pipeline/netsea_jan_index.json"


def load_index(path: Path = INDEX) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"indexed_shops": [], "jans": {}}


def build_netsea_index(shops_per_run: int = 30, path: Path = INDEX, log=print) -> dict:
    """承認済みサプライヤーを順に回り、JAN → 卸情報の索引を作る（Keepa トークン0）。

    前回の続きから走ります。`jans` には卸値が入るので **`agent_output/` にだけ**置きます
    （このリポは PUBLIC）。
    """
    idx = load_index(path)
    client, why = netsea_client()
    if client is None:
        log(f"索引づくりをスキップ: {why}")
        return idx

    all_ids = [int(s["id"]) for s in client.list_suppliers() if str(s.get("id", "")).isdigit()]
    done = set(idx.get("indexed_shops") or [])
    todo = [i for i in all_ids if i not in done][:shops_per_run]
    log(f"承認済みサプライヤー {len(all_ids)}社（索引済 {len(done)}社）→ 今回 {len(todo)}社")
    if not todo:
        log("全社を索引済みです。")
        return idx

    # **1社ごとに保存する。**60社を回してから最後に1回だけ保存する設計にしていたため、
    # 途中で止めると30分ぶんの NETSEA 取得が丸ごと消えました（2026-09-30）。
    # 「あとでまとめて保存」は、途中で止まる可能性を無視した設計です。
    path.parent.mkdir(parents=True, exist_ok=True)
    for shop_id in todo:
        found = scan_suppliers(client, [shop_id], log=log)
        idx.setdefault("jans", {}).update(found)
        done.add(shop_id)
        idx["indexed_shops"] = sorted(done)
        path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    log(f"索引: JAN {len(idx['jans']):,}件 / {len(idx['indexed_shops'])}社ぶん → {path.name}")
    return idx
