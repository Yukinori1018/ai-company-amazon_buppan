#!/usr/bin/env python3
"""原価モデル v2 のテスト（2026-10-04 / 成果物33・34 を受けて）。

    python3 test_cost_v2.py

固定する不変条件は4つ。**どれも実際に間違えた**ので、文章ではなくテストで止めます。

1. **750円の崖** — 売上の合計が750円以下なら販売手数料5%（段階制ではなく閾値・最低30円税抜）。
   売価751〜900円と1,001〜1,100円は「下げた方が手残りが増える」死に帯
2. **区分別の原価** — その他固定費を一律206円にしない。小型63円・標準7 460円・標準8 739円
3. **カート保持者判定** — 落とすのは「本体がカートを持っている」行だけ。
   本体が出品していることでは落とさない（在庫履歴・出品一覧は補助情報）
4. **A/B/C 等級** — 誤差幅（売価7%＋200円）を費用に足さない。
   セット数が未確定の行は金額を膨らませず UNKNOWN
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import fba_cost as F                       # noqa: E402
import profit                              # noqa: E402
import set_family                          # noqa: E402
import verdict as V                        # noqa: E402

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  NG {name}: {got!r} ≠ {want!r}")
    else:
        print(f"  ok {name}")


def near(name: str, got, want, tol=1.0) -> None:
    if got is None or abs(float(got) - float(want)) > tol:
        FAILS.append(f"{name}: got {got!r}, want ≈{want!r}")
        print(f"  NG {name}: {got!r} ≉ {want!r}")
    else:
        print(f"  ok {name}（{got}）")


# ── 1. 750円の崖 ──────────────────────────────────────────────────────────
print("1. 750円の崖（閾値判定・最低30円税抜）")

check("750円は5%", F.referral_pct(750, "ホーム&キッチン"), 5.0)
check("751円は15.4%（段階制ではない＝全額に15.4%）", F.referral_pct(751, "ホーム&キッチン"), 15.4)
check("749円も5%", F.referral_pct(749, "ホーム&キッチン"), 5.0)
# 750円 × 5% = 37.5円（税抜）→ 最低30円を超えるので率が効く。×1.1 = 41円
near("750円の販売手数料は41円", F.referral_yen(750, "ホーム&キッチン"), 41)
# 500円 × 5% = 25円 < 最低30円 → 30円 × 1.1 = 33円
near("500円は最低手数料が効いて33円", F.referral_yen(500, "ホーム&キッチン"), 33)
near("751円は127円（5%なら41円。86円の崖）", F.referral_yen(751, "ホーム&キッチン"), 127)

# 崖の向き: 751円の手残りは 750円より小さい
oth = F.other_costs("小型", 3.0).total
def net(sell):
    return sell - F.referral_yen(sell, "ホーム&キッチン") - F.fba_fee_yen("小型", sell) - 220 - oth
check("751円の手残りは750円より小さい", net(751) < net(750), True)
check("900円でやっと750円の水準に戻る", net(900) >= net(750), True)
check("1,001円の手残りは1,000円より小さい（FBAの列が変わる）", net(1001) < net(1000), True)

# 死に帯の助言が出る／帯の外では出ない
check("売価800円は死に帯の助言が出る", "750円に下げる" in F.cliff_advice(800, 220, "小型", category="ホーム&キッチン"), True)
check("売価1,050円も死に帯", "1,000円に下げる" in F.cliff_advice(1050, 220, "小型", category="ホーム&キッチン"), True)
check("売価1,500円は助言なし", F.cliff_advice(1500, 220, "小型", category="ホーム&キッチン"), "")
check("売価700円は助言なし", F.cliff_advice(700, 220, "小型", category="ホーム&キッチン"), "")

# 旧モデルは「8.4%を全商品」で甘かった。ホーム&キッチンは15.4%でなければならない。
check("Keepa の 15.0% は公式の段 15.4% へ切り上げる", F.referral_pct(2000, None, 15.0), 15.4)
check("Keepa の 10.0% は 10.4% へ", F.referral_pct(2000, None, 10.0), 10.4)
check("Keepa の 8.0% は 8.4% へ", F.referral_pct(2000, None, 8.0), 8.4)
check("率が不明なら最高段 15.4%（甘くしない）", F.referral_pct(2000, None, None), 15.4)


# ── 2. 区分別の原価 ───────────────────────────────────────────────────────
print("\n2. 区分別の原価（一律206円を廃止）")

check("profit に OTHER_UNIT_COSTS_YEN は無い", hasattr(profit, "OTHER_UNIT_COSTS_YEN"), False)
check("set_family に DEFAULT_FBA_YEN=415 は無い", hasattr(set_family, "DEFAULT_FBA_YEN"), False)
check("set_family に誤差幅 BAND_FIXED は無い", hasattr(set_family, "BAND_FIXED"), False)

# ハジメの成果物33 表A と一致すること（1箱30個・消化3ヶ月・通常期）
near("小型のその他固定費は63円（旧206円）", F.other_costs("小型", 3.0).total, 63, 1.0)
near("標準1は75円", F.other_costs("標準1", 3.0).total, 75, 1.0)
near("標準3は65円", F.other_costs("標準3", 3.0).total, 65, 1.0)
near("標準7は460円（鍋。ここは旧206円より重い）", F.other_costs("標準7", 3.0).total, 460, 1.0)
near("標準8は739円", F.other_costs("標準8", 3.0).total, 739, 1.0)
check("小型のほうが標準7より安い（体積比例が効いている）",
      F.other_costs("小型", 3.0).total < F.other_costs("標準7", 3.0).total, True)

# FBA配送代行は売価1,000円を境に変わる
check("小型・1,000円以下は222円", F.fba_fee_yen("小型", 999), 222)
check("小型・1,000円超は288円", F.fba_fee_yen("小型", 1001), 288)
check("1,000円ちょうどは安い列", F.fba_fee_yen("小型", 1000), 222)

# Keepa の実測手数料からサイズ区分を逆引きできる
check("222円+売価700 → 小型", F.tier_from_fba_fee(222, 700), "小型")
check("288円+売価1,500 → 小型", F.tier_from_fba_fee(288, 1500), "小型")
check("415円+売価3,000 → 標準3", F.tier_from_fba_fee(415, 3000), "標準3")
check("472円+売価5,000 → 標準7（鍋 L001 の実測）", F.tier_from_fba_fee(472, 5000), "標準7")
check("手数料が無ければ None（推測しない）", F.tier_from_fba_fee(None, 1500), None)
check("表に無い金額なら None", F.tier_from_fba_fee(999, 1500), None)

# 寸法からの区分。立体物は厚みで小型に入れない
check("19×6×1.5cm・30g は小型", F.tier_from_dimensions(190, 60, 15, 30), "小型")
check("12×8×4.0cm（厚み2cm超）は小型でない",
      F.tier_from_dimensions(120, 80, 40, 60) != "小型", True)
check("寸法が欠けていれば None", F.tier_from_dimensions(-1, 60, 15, 30), None)

# 卸178円のたわし。旧モデルは必要売価1,214円と言っていた
near("卸178円の単品の損益分岐は約514円（旧1,214円）", set_family.required_sell(178, 1), 514, 5)


# ── 3. カート保持者判定（本体の存在では落とさない）───────────────────────
print("\n3. カート保持者判定")

AMZ = V.AMAZON_JP_SELLER_ID


def product(*, buybox_is_amazon=False, buybox_seller="A3RDWORDSELLER",
            oos365=100, oos90=100, amazon_in_offers=False, buybox_stats=None,
            count_new=3):
    offers = [{"sellerId": "A3RDWORDSELLER", "condition": 1, "isFBA": True}]
    if amazon_in_offers:
        offers.append({"sellerId": AMZ, "condition": 1, "isFBA": True, "isAmazon": True})
    return {
        "asin": "B000TEST01", "title": "テスト",
        "offers": offers, "liveOffersOrder": list(range(len(offers))),
        "buyBoxSellerIdHistory": [1, buybox_seller],
        "stats": {
            "buyBoxIsAmazon": buybox_is_amazon,
            "buyBoxSellerId": buybox_seller,
            "buyBoxStats": buybox_stats or {},
            "outOfStockPercentage365": [oos365] + [-1] * 20,
            "outOfStockPercentage90": [oos90] + [-1] * 20,
            "current": [-1] * 11 + [count_new] + [-1] * 10,
        },
    }


# 🔴 本題。本体が出品していて在庫も持っているが、カートは第三者。
p = product(oos365=0, oos90=0, amazon_in_offers=True)
j = V.judge(p, offers_requested=20)
check("本体が出品・在庫100%でも、カートが第三者なら NO-GO にしない", j.verdict, V.GO)
check("  チェック2（在庫履歴）は FAIL を出さない",
      next(c.status for c in j.checks if c.number == 2) != V.FAIL, True)
check("  チェック3（出品一覧）は FAIL を出さない",
      next(c.status for c in j.checks if c.number == 3) != V.FAIL, True)
check("  それでも本体の存在は理由文に残る（隠さない）",
      "Amazon 本体が混ざっています" in next(c.reason for c in j.checks if c.number == 3), True)

# カートを本体が持っていたら、これは落とす
j2 = V.judge(product(buybox_is_amazon=True, buybox_seller=AMZ), offers_requested=20)
check("カート保持者が本体なら NO-GO", j2.verdict, V.NO_GO)
check("  カート保持者の表示は Amazon 本体", "Amazon.co.jp" in j2.cart_holder, True)

# 統計期間中に本体が過半を取っていたら落とす。1〜2%では落とさない
j3 = V.judge(product(buybox_stats={AMZ: {"percentageWon": 60.0}}), offers_requested=20)
check("本体が期間の60%カートを取っていたら NO-GO", j3.verdict, V.NO_GO)
j4 = V.judge(product(buybox_stats={AMZ: {"percentageWon": 1.9}}), offers_requested=20)
check("本体が期間の1.9%だけなら落とさない（旧実装は1%で FAIL だった）", j4.verdict, V.GO)
check("  ただし注記は残る", "⚠️" in next(c.reason for c in j4.checks if c.number == 1), True)

# カート保持者が決まらない行は今も UNKNOWN（fail-closed は緩めない）
p5 = product(buybox_seller="-1")
p5["stats"]["buyBoxIsAmazon"] = None
p5["buyBoxSellerIdHistory"] = []
check("カート保持者が決まらなければ UNKNOWN（GO に畳まない）",
      V.judge(p5, offers_requested=20).verdict, V.UNKNOWN)

# 一覧の打ち切りは、カート保持者の判定には関係しない
j6 = V.judge(product(count_new=50), offers_requested=20)
check("オファー一覧が打ち切られていても NO-GO/UNKNOWN にしない", j6.verdict, V.GO)
check("  セラー数が下限値である旨は注記する",
      "下限値" in next(c.reason for c in j6.checks if c.number == 3), True)


# ── 4. A / B / C 等級 ─────────────────────────────────────────────────────
print("\n4. A/B/C 等級（誤差幅の撤去）")

a = F.grade(1500, 396, "標準1", category="ホーム&キッチン")
check("中央30.5%・悲観24.3% は A", a.grade, "A")
check("  A は発注候補", a.is_candidate, True)

b = F.grade(750, 220, "小型", category="ホーム&キッチン")
check("中央27%・悲観18% は B（落とさない）", b.grade, "B")
check("  B も候補（最小ロットで1回実測）", b.is_candidate, True)
check("  B の理由に『最小ロット』が入る", "最小ロット" in b.reason, True)

c = F.grade(500, 220, "小型", category="ホーム&キッチン")
check("中央で赤字なら C", c.grade, "C")
check("  C は候補でない", c.is_candidate, False)

u = F.grade(1500, 396, "小型", unit_decided=False)
check("セット数が未確定なら UNKNOWN", u.grade, "UNKNOWN")
check("  金額を膨らませず『計算しません』と言う", "計算しません" in u.reason, True)
check("  UNKNOWN は候補でない", u.is_candidate, False)
check("サイズ区分が決まらなければ UNKNOWN", F.grade(1500, 396, None).grade, "UNKNOWN")

# 悲観の当て方: 区分1段上・料率15.4%・保管2倍・箱7割
w = F.grade(2000, 400, "小型", category="エレクトロニクス")
check("悲観はサイズ区分を1段上にする", w.worst["サイズ区分"], "標準1")
check("悲観の料率はカテゴリー最高段（エレクトロニクス8.4%→15.4%）",
      w.worst["販売手数料"] > w.mid["販売手数料"], True)
check("悲観の手残りは中央より小さい", w.worst["手残り"] < w.mid["手残り"], True)

# 旧「誤差幅 売価7%＋200円」が低単価帯を狙い撃ちで落としていたことの再現防止。
# 売価750円・原価220円の手残りは204円で、旧の誤差幅（752円）を下回る＝旧は UNKNOWN。
old_band = round(750 * 0.07) + 200
check("旧の誤差幅は売価750円で売価の33%以上だった", old_band / 750 > 0.33, True)
check("新モデルでは同じ行が B（候補）になる", b.grade, "B")

# profit.compute は区分を自動で逆引きし、等級を返す
e = profit.compute(1500, 15.0, 288, 396, 10)
check("compute がサイズ区分を逆引きする", e.size_tier, "小型")
check("compute が等級を返す", e.grade in ("A", "B", "C", "UNKNOWN"), True)
near("compute のその他固定費は区分別（206円ではない）", e.other_unit_costs, 63, 1.0)


# ── 5. セット組の向き（体積が理由・単価ではない）─────────────────────────
print("\n5. セット組は「体積が大きいから」")

n_small, why_small = F.bundle_advice("小型", 700, 200)
check("小型・750円以下の商品はセットの崖を警告する", "5%→15.4%" in why_small, True)
n_big, why_big = F.bundle_advice("標準7", 3000, 800)
check("体積が大きい商品ではセットが有利に出る", n_big > 1, True)
# 体積から区分を引くときは **代表体積の昇順**で探す。`FBA` の並び順で探すと、
# 標準2（280cm³）が小型（600cm³）より小さいせいで間違える。
check("体積280cm³ は標準2（いちばん小さい代表体積）", F.tier_from_volume(280), "標準2")
check("体積500cm³ は小型（標準2 には入らない）", F.tier_from_volume(500), "小型")
check("体積6,000cm³ は標準6", F.tier_from_volume(6000), "標準6")


print()
if FAILS:
    print(f"NG {len(FAILS)}件")
    raise SystemExit(1)
print("全部 ok")
