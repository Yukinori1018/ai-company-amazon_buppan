"""Keepa の「実セラー数（distinct seller）」を数える小さなモジュール（T-20260817-005）。

## なぜ必要か（2026-08-24 社長指摘）

Keepa の `COUNT_NEW`（= `stats.current[11]`）は **「新品オファー数」であって「出品者数」ではない。**
1社が FBA と FBM の両方に同一商品を出すと、セラーは1社でも `COUNT_NEW = 2` になる。

実例 ASIN `B0DWMPV656`（seathestars 小型洗濯機）:
  COUNT_NEW = 2 / offerCountFBA = 1 / offerCountFBM = 1
  → 生きているオファーは2本だが sellerId は `A37CWH39G3AT5D` の1つだけ（＝1社の独占）。

v1.3 の「出品者数 2〜6」はメーカーが**実際に卸している証拠**を取るための条件なので、
「オファーが2本ある」では代理変数にならない。**必ず sellerId の distinct 数で数えること。**

## 正しい数え方

`GET /product?asin=...&offers=N` を叩き、

  1. `liveOffersOrder`（現在生きているオファーの index 配列）で **生存オファーだけ**に絞る
     （`offers` 配列には過去の死んだオファーも入っている）
  2. `condition == 1`（NEW）だけを残す（中古セラーを混ぜない）
  3. `sellerId` を set に入れて数える

トークン単価: `offers=20` で **約5.6トークン/商品**（実測 2026-08-24 / 5件28トークン）。
素の product は1トークンなので、offers は約6倍の贅沢品。**必要な分だけ叩くこと。**
"""
from __future__ import annotations

# Keepa の condition コード（公式）。1 = 新品。
CONDITION_NEW = 1

# Keepa がオファーに付ける「Amazon 本体」フラグ
def _is_amazon(offer: dict) -> bool:
    return bool(offer.get("isAmazon"))


def live_new_offers(product: dict) -> list:
    """product から「今生きている新品オファー」だけを返す。

    `liveOffersOrder` が無い商品（offers を要求しなかった等）は空リストを返す。
    """
    offers = product.get("offers") or []
    order = product.get("liveOffersOrder")
    if not order:
        return []
    live = [offers[i] for i in order if isinstance(i, int) and 0 <= i < len(offers)]
    return [o for o in live if o.get("condition") == CONDITION_NEW]


def distinct_sellers(product: dict) -> list:
    """生存新品オファーの distinct sellerId を返す（Amazon 本体は除く）。

    これが v1.3 の言う「出品者数」の正しい実装。COUNT_NEW を使ってはいけない。
    """
    seen = []
    for o in live_new_offers(product):
        sid = o.get("sellerId")
        if sid and not _is_amazon(o) and sid not in seen:
            seen.append(sid)
    return seen


def seller_profile(product: dict) -> dict:
    """1商品ぶんの実セラー情報。CSV の列にそのまま流し込める形。

    返り値:
      real_sellers   : 実セラー数（distinct sellerId）
      seller_ids     : sellerId のリスト
      offer_count_new: COUNT_NEW（＝オファー数。比較用に残す）
      fba_offers/fbm_offers: 生存新品オファーのうち FBA / FBM の本数
      dup_fba_fbm    : 同一セラーが FBA と FBM を二重に出しているか（COUNT_NEW 水増しの主因）
    """
    live = live_new_offers(product)
    ids = distinct_sellers(product)
    stats = product.get("stats") or {}
    cur = stats.get("current") or []
    count_new = cur[11] if len(cur) > 11 and isinstance(cur[11], int) and cur[11] >= 0 else None
    by_seller = {}
    for o in live:
        by_seller.setdefault(o.get("sellerId"), set()).add(bool(o.get("isFBA")))
    return {
        "real_sellers": len(ids),
        "seller_ids": ids,
        "offer_count_new": count_new,
        "live_new_offers": len(live),
        "fba_offers": sum(1 for o in live if o.get("isFBA")),
        "fbm_offers": sum(1 for o in live if not o.get("isFBA")),
        "dup_fba_fbm": any(len(v) > 1 for v in by_seller.values()),
    }
