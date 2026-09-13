#!/usr/bin/env python3
"""T-20260912-002 採算チェック（経理ハジメ・2026-09-13）
固定費3段階・損益分岐月商・1周目10万円・キャッシュ最薄月・800万の在庫原価を決定論で検算する。
乱数は使わない。月0=2026-09、月12=2027-09。金額は円。
置き値の出典は 03_複合戦略_採算チェック.md §9 を参照。
"""

# ---- 為替（仮定・2026-09-12 の報道値。日々動く）----
FX_EUR = 178.2   # 円/€（仮定）
FX_USD = 150.0   # 円/$（仮定）

# ---- 固定費（月額）----
FIXED_NOW = {
    "大口出品 月額（税込）": 5390,                     # 実測（2026-06 実請求）
    "Keepa API €49": round(49 * FX_EUR),               # 実測€49 × 仮定FX
    "HP ドメイン $10.46/年": round(10.46 * FX_USD / 12),  # 実測$ × 仮定FX
}
COND = {
    "セラースプライト（成立2社以上）": 13998,          # 実測（2026-08-14 申込ガイド）
    "会計ソフト（青色65万・未契約なら）": 900,          # 二次（MF パーソナル 年払い換算）
    "GS1 事業者コード 17,050円/年（セット組み時）": round(17050 / 12),  # 一次（GS1 Japan）
    "商標1区分 44,900円（10年・成立2社以上）": round(44900 / 120),      # 一次（特許庁料金）月換算
}
ONEOFF_TRADEMARK = 44900
ONEOFF_GS1 = 17050

stage1 = sum(FIXED_NOW.values())
stage2 = stage1 + COND["セラースプライト（成立2社以上）"] + COND["会計ソフト（青色65万・未契約なら）"]
stage3 = stage2 + COND["GS1 事業者コード 17,050円/年（セット組み時）"]

print("=== 固定費（月額）===")
for k, v in FIXED_NOW.items(): print(f"  {k:36s} {v:>8,}")
print(f"  {'段階1 今（成立0〜1社）':36s} {stage1:>8,}  年 {stage1*12:,}")
print(f"  {'段階2 成立3社後（スプライト＋会計）':36s} {stage2:>8,}  年 {stage2*12:,} ＋商標 {ONEOFF_TRADEMARK:,}（一回）")
print(f"  {'段階3 成立6社後（＋GS1）':36s} {stage3:>8,}  年 {stage3*12:,} ＋GS1 {ONEOFF_GS1:,}/年")
print(f"  Keepa Pro €29 が別請求なら各段階 +{round(29*FX_EUR):,}（未確認）")

# ---- 損益分岐月商 = 固定費 ÷ レーン利益率 ----
print("\n=== 損益分岐月商（固定費 ÷ レーン利益率）===")
margins = [0.06, 0.08, 0.09, 0.12, 0.15, 0.20, 0.25, 0.30]
print("  利益率   " + "".join(f"{m:>7.0%}" for m in margins))
for name, f in [("段階1", stage1), ("段階2", stage2), ("段階3", stage3)]:
    print(f"  {name} {f:>7,} " + "".join(f"{f/m/1e4:>6.1f}万" for m in margins))

# 「月商45万・営業利益率+7%」に要るレーン利益率
rev = 450_000
need = 0.07 + stage2 / rev
print(f"\n  月商45万・営業利益率+7% に要るレーン利益率 = 7% + {stage2:,}/{rev:,} = {need:.1%}")
for r in [200_000, 300_000, 450_000, 800_000, 1_200_000, 8_000_000]:
    print(f"  月商{r/1e4:>5.0f}万: 固定費（段階2）の売上比 {stage2/r:.1%} → レーン利益率20%なら営業利益率 {0.20 - stage2/r:.1%}")

# ---- 1周目 10万円の使途 ----
print("\n=== 1周目 10万円の使途 ===")
amino_units, amino_sets = 12, 4
amino_cost = 12_720                       # 実測（T-20260909-002）
amino_prep = amino_units * 12 + amino_sets * 50   # 納品代行12円/点（実測）＋セット組み50円/セット（推定）
amino_ship = 750                          # 代行→FC 140サイズ（実測 e-fba）
netsea_ship = (0, 1500)                   # 初回送料無料特集（〜10/1）／実測中央値
amino_total = (amino_cost + amino_prep + amino_ship + netsea_ship[0], amino_cost + amino_prep + amino_ship + netsea_ship[1])
print(f"  アミノ 4セット: 仕入 {amino_cost:,} ＋ 代行 {amino_prep:,} ＋ 送料 {amino_ship:,} ＋ NETSEA送料 {netsea_ship[0]}〜{netsea_ship[1]:,} ＝ {amino_total[0]:,}〜{amino_total[1]:,}")
honmaru_cap = 100_000 - amino_total[1]
print(f"  本丸 初回発注の枠（仕入＋外注＋送料込み）: {honmaru_cap:,}（1社5万円以内×1〜2社）")
sale = 4570; margin_amino = 0.08; floor = 4420; margin_floor = 0.05
disposal = 242.5
scen = {
    "楽観": dict(sold=4, price=sale, m=margin_amino, disp=0),
    "中央": dict(sold=2.5, price=sale, m=margin_amino, disp=0),
    "悲観": dict(sold=1, price=floor, m=margin_floor, disp=3),
}
print("  アミノ 6ヶ月（〜2027-03-15）の損益（固定費除く）")
for k, s in scen.items():
    prof = s["sold"] * s["price"] * s["m"]
    loss = s["disp"] * (amino_cost / amino_sets) + s["disp"] * 3 * disposal
    held = (amino_sets - s["sold"] - s["disp"]) * (amino_cost / amino_sets)
    print(f"    {k}: 売れた {s['sold']}セット → 利益 {prof:,.0f} ／ 廃棄 {s['disp']}セット → 損失 {loss:,.0f} ／ 在庫で残る原価 {held:,.0f} → 差引 {prof-loss:,.0f}")
fixed_1st = stage1 * 4   # 9〜12月
fixed_6m = stage1 * 6    # 9月〜2027-03
print(f"  別枠の固定費: 1周目（9〜12月）{fixed_1st:,} ／ 6ヶ月（〜2027-03）{fixed_6m:,}")
print(f"  最悪の現金流出（在庫10万全損＋廃棄＋固定費6ヶ月）: {100_000 + 12*disposal + fixed_6m:,.0f}")

# ---- キャッシュ最薄月（3シナリオ・決定論）----
print("\n=== キャッシュ（社長が投入していなければならない現金の最大値）===")
COST_RATE = 0.53      # 原価率（推定：1 − 経費35% − レーン利益12%）
INV_MULT = 1.5        # 在庫倍率（二次・EC STARs 1.2〜1.5 の上側）
paths = {
    # 月商（万円）月0〜12。タケシ2周目 B の 3M/6M/12M 中央・楽観・悲観を補間（推定）
    "中央": dict(rev=[0, 0, 0, 0.5, 1.5, 3, 8, 12, 17, 23, 30, 37, 45], lane=0.12, m2=5, m3=7, honmaru=5),
    "楽観": dict(rev=[0, 0, 0, 1, 5, 15, 32, 50, 75, 105, 135, 160, 186], lane=0.13, m2=3, m3=4, honmaru=3),
    "悲観": dict(rev=[0, 0, 0, 0, 0.3, 0.6, 1, 1.5, 2, 2.5, 3, 3.5, 4], lane=0.06, m2=9, m3=None, honmaru=9),
}
MONTH_LABEL = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08", "2027-09"]
for name, p in paths.items():
    cum_fixed = 0; cum_lane = 0; oneoff = 0; cum_rev = 0
    pos = []; loan_month = None
    for mo in range(13):
        sprite_on = p["m2"] is not None and mo >= p["m2"]
        fixed = stage1 + (COND["セラースプライト（成立2社以上）"] if sprite_on else 0) + (COND["会計ソフト（青色65万・未契約なら）"] if mo >= 4 else 0)
        cum_fixed += fixed
        if p["m2"] is not None and mo == p["m2"]: oneoff += ONEOFF_TRADEMARK
        r = p["rev"][mo] * 1e4
        cum_rev += r; cum_lane += r * p["lane"]
        if loan_month is None and cum_rev >= 1_000_000: loan_month = mo
        nxt = p["rev"][min(mo + 1, 12)] * 1e4
        inv = max(nxt * COST_RATE * INV_MULT, 13_000 + (87_000 if (p["honmaru"] is not None and mo >= p["honmaru"]) else 0))
        net = cum_lane - cum_fixed - oneoff - inv
        pos.append(net)
    worst = min(pos); wm = pos.index(worst)
    inj = 100_000 + (300_000 if p["m3"] is not None and wm >= max(3, p["m3"]) else 0) + (1_000_000 if p["m3"] is not None and wm >= max(8, p["m3"]) else 0)
    m8 = pos[8]; inj8 = 100_000 + (300_000 if p["m3"] is not None and 8 >= max(3, p["m3"]) else 0)
    print(f"  {name}: 最薄月 {MONTH_LABEL[wm]} 必要現金 {-worst/1e4:.1f}万（固定費累計 {cum_fixed/1e4:.1f}万・商標 {oneoff/1e4:.1f}万 ／ 12M末の純ポジション {pos[-1]/1e4:+.1f}万 ／ 累計売上100万到達 {MONTH_LABEL[loan_month] if loan_month is not None else '12ヶ月内に未達'}）")
    print(f"        月別純ポジション（万）: " + " ".join(f"{x/1e4:+.0f}" for x in pos))
    print(f"        タケシ案の投入（最薄月まで・条件付き）{inj/1e4:.0f}万 → {'足りる' if inj >= -worst else '不足 ' + f'{(-worst-inj)/1e4:.1f}万'}　／　100万投入の直前（2027-05）: 必要 {-m8/1e4:.1f}万 vs 投入済 {inj8/1e4:.0f}万 → {'足りる' if inj8 >= -m8 else '不足 ' + f'{(-m8-inj8)/1e4:.1f}万'}")

# ---- 800万に要る在庫原価 ----
print("\n=== 月商800万に要る在庫原価（原価率 × 在庫倍率）===")
print("  原価率＼倍率 " + "".join(f"{m:>8.1f}" for m in [1.2, 1.5, 2.0, 3.0]))
for cr, label in [(0.45, "0.45（利益率20%・経費35%）"), (0.53, "0.53（利益率12%・経費35%）"), (0.60, "0.60（タケシ置き値）")]:
    print(f"  {label:28s}" + "".join(f"{8e6*cr*m/1e4:>7.0f}万" for m in [1.2, 1.5, 2.0, 3.0]))
