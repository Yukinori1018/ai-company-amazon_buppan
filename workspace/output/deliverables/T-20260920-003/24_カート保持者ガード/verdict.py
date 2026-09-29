#!/usr/bin/env python3
"""CLAUDE.md §3.3「発注前のカート保持者確認」の判定ロジック（純関数）。

このモジュールは **Keepa API を知りません**。入力は「Keepa の product オブジェクト相当の dict」
だけで、ネットワークにも環境変数にも触りません。だから test_verdict.py で全分岐をテストできます。
外部 API の差し替え（SP-API など）は keepa_client.py 側だけを書き換えれば済みます。

設計の芯（2026-09-30 の事故から）
--------------------------------
商品ページの `#merchant-info` という **1つの要素だけ**を読んで「販売元＝第三者」と判定し、
Amazon 本体がカートを持つ ASIN を発注させました。だからこのモジュールは:

1. **1つの根拠で PASS を出しません。** カート保持者は独立した3つの根拠が必要で、
   そのうち **2つ以上が一致して初めて** PASS になります。1つでも食い違えば UNKNOWN。
2. **判定不能は NO-GO ではなく UNKNOWN。** 「データが無いから安全」は最悪の誤りです。
   UNKNOWN も GO ではないので発注は止まりますが、「調べれば分かる」と「調べて駄目だった」を
   混ぜません。混ぜると、次に何をすればいいのかが分からなくなります。
3. **オファー一覧が打ち切られていたら UNKNOWN。** `offers=20` で21件目以降は返りません。
   「返ってきた20件に本体が居ない」は「本体が居ない」ではありません。

用語
----
`outOfStockPercentage365[0]` は **Amazon 本体**の365日間の在庫切れ率（%）です。
100 ＝ 1年間ずっと在庫なし ＝ 本体不在。0 ＝ 1年間ずっと在庫あり。-1 ＝ データなし。
スナップショットの `availabilityAmazon` は使いません（既知の罠：候補が93%過大に出る）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Amazon.co.jp 本体のセラーID。Keepa の sellerId / buyBoxSellerId と直接突き合わせる。
AMAZON_JP_SELLER_ID = "AN1VRQENFRJN5"

# Keepa の stats.current / csv の添字（公式フィールド定義）。
# 列名から意味を推測せず、番号で持つ（memory: verify_field_semantics_not_names）。
IDX_AMAZON = 0       # Amazon 本体の価格
IDX_SALES_RANK = 3   # 売れ筋ランク
IDX_COUNT_NEW = 11   # 新品オファー「本数」（出品者数ではない）

# 判定の3値。
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

# 総合判定。
GO = "GO"
NO_GO = "NO-GO"

# Amazon 本体の年間在庫率がこの%を超えたら FAIL。
# 0 より大きく閾値以下なら「警告つき PASS」。棚卸し・短期の直販テストで
# 数日だけ本体が出ることはあり、それで全件 NO-GO にすると使い物にならないため。
AMAZON_INSTOCK_FAIL_PCT = 2.0

# 直近90日に本体の在庫が1%でもあれば FAIL（現役で本体が動いている棚）。
AMAZON_INSTOCK_90D_FAIL_PCT = 1.0

# buyBoxStats に本体が居て、この%以上カートを取っていたら FAIL。
AMAZON_BUYBOX_WON_FAIL_PCT = 1.0


@dataclass
class Check:
    """3点チェックの1つぶんの結果。"""

    number: int
    name: str
    status: str                                   # PASS / FAIL / UNKNOWN
    reason: str                                   # 社長がそのまま読める1行
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Judgment:
    """1 ASIN ぶんの総合判定。"""

    asin: str
    title: str
    verdict: str                                  # GO / NO-GO / UNKNOWN
    cart_holder: str                              # 「誰がカートを持っているか」= 報告の1行目
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_go(self) -> bool:
        return self.verdict == GO


# --- 小さなヘルパ -----------------------------------------------------------


def _stats(product: dict) -> dict:
    return product.get("stats") or {}


def _at(seq: Any, i: int) -> Any:
    """リストの i 番目。無ければ None。Keepa は -1 を「データなし」に使う。"""
    if not isinstance(seq, list) or i >= len(seq):
        return None
    v = seq[i]
    return None if v == -1 else v


def _who(seller_id: Any) -> str:
    """セラーIDを AMAZON / THIRD_PARTY / UNKNOWN に畳む。

    Keepa は buyBox が無い・確定できない状態を "-1" "-2" という**文字列**で返す。
    数値の -1 と混ざるので、文字列化してから見る。
    """
    if seller_id is None:
        return UNKNOWN
    s = str(seller_id)
    if s.startswith("-") or s == "":
        return UNKNOWN
    return "AMAZON" if s == AMAZON_JP_SELLER_ID else "THIRD_PARTY"


def _live_new_offers(product: dict) -> list[dict] | None:
    """いま生きている新品オファーだけを返す。取れなければ None。

    `liveOffersOrder` は「現在ライブなオファーの添字」で、Keepa が返す offers には
    過去に消えたオファーも混ざっている。ここを混ぜると出品者数が水増しされる。
    condition は 0=不明 / 1=新品 / 2以上=中古系。
    """
    offers = product.get("offers")
    order = product.get("liveOffersOrder")
    if not isinstance(offers, list) or not isinstance(order, list):
        return None
    live = []
    for i in order:
        if isinstance(i, int) and 0 <= i < len(offers):
            o = offers[i]
            if o.get("condition") in (0, 1, None):
                live.append(o)
    return live


# --- チェック1: カートの販売元 ----------------------------------------------


def check_cart_holder(product: dict) -> tuple[Check, str]:
    """誰がいまカートを持っているか。独立した3根拠 + 履歴の4本立て。

    戻り値は (Check, カート保持者の表示文字列)。
    """
    st = _stats(product)

    # 根拠A: stats.buyBoxIsAmazon（Keepa が直接くれる真偽値）
    is_amazon = st.get("buyBoxIsAmazon")
    ev_a = "AMAZON" if is_amazon is True else ("THIRD_PARTY" if is_amazon is False else UNKNOWN)

    # 根拠B: stats.buyBoxSellerId（セラーIDそのもの）
    bb_seller = st.get("buyBoxSellerId")
    ev_b = _who(bb_seller)

    # 根拠C: buyBoxSellerIdHistory の最後のエントリ
    #        [timestamp, sellerId, timestamp, sellerId, ...] という平坦な配列。
    hist = product.get("buyBoxSellerIdHistory") or []
    last_hist = hist[-1] if len(hist) >= 2 else None
    ev_c = _who(last_hist)

    votes = {"stats.buyBoxIsAmazon": ev_a, "stats.buyBoxSellerId": ev_b,
             "buyBoxSellerIdHistory[-1]": ev_c}
    known = [v for v in votes.values() if v != UNKNOWN]

    # 根拠D: buyBoxStats（統計期間中に誰が何%カートを取ったか）。
    #        いま第三者でも、本体が期間中にカートを取っていれば「本体の棚」。
    bstats = st.get("buyBoxStats") or {}
    amazon_won = None
    if isinstance(bstats, dict) and AMAZON_JP_SELLER_ID in bstats:
        amazon_won = (bstats[AMAZON_JP_SELLER_ID] or {}).get("percentageWon")

    evidence = {"votes": votes, "buyBoxSellerId": bb_seller,
                "amazon_buybox_won_pct": amazon_won}

    if "AMAZON" in votes.values():
        return (Check(1, "カートの販売元", FAIL,
                      "カート保持者が Amazon.co.jp 本体です。値下げしてもカートは取れません。",
                      evidence), "Amazon.co.jp（本体）")

    if amazon_won is not None and amazon_won >= AMAZON_BUYBOX_WON_FAIL_PCT:
        return (Check(1, "カートの販売元", FAIL,
                      f"いまは第三者ですが、統計期間中に本体がカートを {amazon_won:.1f}% 取っています。",
                      evidence), "第三者（ただし本体が出入りしている）")

    if len(known) < 2:
        return (Check(1, "カートの販売元", UNKNOWN,
                      f"根拠が {len(known)} 本しか取れませんでした（2本以上の一致が必要）。",
                      evidence), "不明")

    if len(set(known)) > 1:
        return (Check(1, "カートの販売元", UNKNOWN,
                      "根拠どうしが食い違っています。実画面で確認してください。",
                      evidence), "不明（根拠が食い違い）")

    warn = ""
    if amazon_won is not None:
        warn = f"（本体の期間カート獲得 {amazon_won:.1f}%）"
    return (Check(1, "カートの販売元", PASS,
                  f"根拠 {len(known)} 本が一致して第三者です{warn}。",
                  evidence), f"第三者セラー（{bb_seller}）")


# --- チェック2: Amazon 本体の在庫履歴 ---------------------------------------


def check_amazon_stock_history(product: dict) -> Check:
    """`outOfStockPercentage365` で本体の在庫履歴を見る。90日も突き合わせる。"""
    st = _stats(product)
    oos365 = _at(st.get("outOfStockPercentage365"), IDX_AMAZON)
    oos90 = _at(st.get("outOfStockPercentage90"), IDX_AMAZON)

    evidence = {"outOfStockPercentage365[AMAZON]": oos365,
                "outOfStockPercentage90[AMAZON]": oos90}

    if oos365 is None:
        return Check(2, "本体の在庫履歴", UNKNOWN,
                     "365日の在庫切れ率が取得できませんでした（stats=365 を付けて再取得）。",
                     evidence)

    instock365 = 100.0 - float(oos365)
    instock90 = None if oos90 is None else 100.0 - float(oos90)
    evidence["amazon_instock_365_pct"] = round(instock365, 2)
    evidence["amazon_instock_90_pct"] = None if instock90 is None else round(instock90, 2)

    if instock365 > AMAZON_INSTOCK_FAIL_PCT:
        return Check(2, "本体の在庫履歴", FAIL,
                     f"本体が直近1年の {instock365:.1f}% の期間で在庫を持っています。",
                     evidence)

    if instock90 is not None and instock90 > AMAZON_INSTOCK_90D_FAIL_PCT:
        return Check(2, "本体の在庫履歴", FAIL,
                     f"直近90日に本体の在庫があります（{instock90:.1f}%）。現役の本体棚です。",
                     evidence)

    if instock365 > 0:
        return Check(2, "本体の在庫履歴", PASS,
                     f"本体はほぼ不在ですが、1年で {instock365:.1f}% だけ在庫がありました（要注意）。",
                     evidence)

    return Check(2, "本体の在庫履歴", PASS,
                 "本体は直近1年ずっと在庫なしです。", evidence)


# --- チェック3: 出品一覧の実数 ----------------------------------------------


def check_offer_listing(product: dict, offers_requested: int) -> Check:
    """ライブの新品オファーを数え、本体が混ざっていないかの内訳を出す。

    `offers_requested` は API に投げた offers パラメータ（返る上限）。
    上限に張り付いていたら一覧は打ち切られており、「本体が居ない」と言い切れない。
    """
    st = _stats(product)
    count_new = _at(st.get("current"), IDX_COUNT_NEW)
    live = _live_new_offers(product)

    evidence = {"stats.current[COUNT_NEW]": count_new, "offers_requested": offers_requested}

    if live is None:
        return Check(3, "出品一覧の実数", UNKNOWN,
                     "オファー一覧が取得できませんでした（offers パラメータを付けて再取得）。",
                     evidence)

    seller_ids = {str(o.get("sellerId")) for o in live if o.get("sellerId")}
    amazon_ids = {s for s in seller_ids if s == AMAZON_JP_SELLER_ID}
    amazon_flagged = any(o.get("isAmazon") for o in live)
    fba = sum(1 for o in live if o.get("isFBA"))

    evidence.update({
        "live_new_offer_count": len(live),
        "distinct_sellers": len(seller_ids),
        "amazon_among_sellers": bool(amazon_ids) or amazon_flagged,
        "fba_offers": fba,
        "fbm_offers": len(live) - fba,
    })

    if amazon_ids or amazon_flagged:
        return Check(3, "出品一覧の実数", FAIL,
                     f"ライブの新品オファー {len(live)} 本に Amazon 本体が混ざっています。",
                     evidence)

    # 一覧が打ち切られていないか。上限ちょうどは「もっとある」可能性が高い。
    if count_new is not None and count_new > offers_requested:
        return Check(3, "出品一覧の実数", UNKNOWN,
                     f"新品オファー {count_new} 本に対し {offers_requested} 本しか取得していません。"
                     "一覧が打ち切られており、本体不在と言い切れません。",
                     evidence)
    if len(live) >= offers_requested:
        return Check(3, "出品一覧の実数", UNKNOWN,
                     f"取得上限 {offers_requested} 本に張り付いています。一覧が打ち切られている可能性。",
                     evidence)

    return Check(3, "出品一覧の実数", PASS,
                 f"ライブの新品オファー {len(live)} 本（出品者 {len(seller_ids)} / "
                 f"FBA {fba}・自己発送 {len(live) - fba}）。本体は含まれません。",
                 evidence)


# --- 総合 -------------------------------------------------------------------


def judge(product: dict, offers_requested: int = 20) -> Judgment:
    """3点すべてを実行して総合判定を出す。

    優先順位:
      - 1つでも FAIL があれば **NO-GO**（調べた結果、駄目だと分かった）
      - FAIL は無いが UNKNOWN があれば **UNKNOWN**（調べきれていない。GO ではない）
      - 3点すべて PASS で初めて **GO**
    """
    c1, cart_holder = check_cart_holder(product)
    c2 = check_amazon_stock_history(product)
    c3 = check_offer_listing(product, offers_requested)
    checks = [c1, c2, c3]

    statuses = {c.status for c in checks}
    if FAIL in statuses:
        verdict = NO_GO
    elif UNKNOWN in statuses:
        verdict = UNKNOWN
    else:
        verdict = GO

    warnings = [f"チェック{c.number}: {c.reason}" for c in checks
                if c.status == PASS and "要注意" in c.reason]

    return Judgment(
        asin=product.get("asin", ""),
        title=(product.get("title") or "")[:80],
        verdict=verdict,
        cart_holder=cart_holder,
        checks=checks,
        warnings=warnings,
    )


def judge_missing(asin: str) -> Judgment:
    """API が返さなかった ASIN。存在しない・取得失敗のどちらでも GO にはしない。"""
    return Judgment(
        asin=asin, title="", verdict=UNKNOWN, cart_holder="不明",
        checks=[Check(n, name, UNKNOWN, "Keepa が商品を返しませんでした。", {})
                for n, name in ((1, "カートの販売元"), (2, "本体の在庫履歴"), (3, "出品一覧の実数"))],
    )
