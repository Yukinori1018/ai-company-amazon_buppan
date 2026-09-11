#!/usr/bin/env python3
"""初回発注セットを組む — T-20260909-002。

日本ストアが再開した（T-20260909-001）ので、実際に発注できる形まで落とします。
**発注はしません**（CLAUDE.md §4.1）。組んで並べるところまでです。

入力:
    ./pool.csv                                   … 供給が生きている ASIN の名簿（人が更新する）
    ../T-20260831-006/out/candidates.csv         … 卸値・最小発注数・利益・回転の元データ
    ../T-20260904-004/budget_filter.py           … 送料の読み方（/tariffs）を1本に保つため再利用
    NETSEA GET /tariffs                          … 送料無料ラインの一次情報（推定しない）

出力（すべて out/ ＝ Git 追跡外。金額は NETSEA 卸値そのものなので追跡できない）:
    out/01_発注セット_案別.csv     … 案 × SKU の明細。社長が見る本命
    out/02_案の比較.csv            … 案どうしの比較（総額・粗利・SKU数・全滅シナリオ）
    out/03_発注セット.html         … 上2つを1枚にした閲覧用
    out/plans.json                 … 機械可読版

━━ 続報で組み直すには ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T-20260908-002 の 13〜25位のチェックが届いたら、**pool.csv に行を足して再実行するだけ**です。
コードは触りません。`供給ステータス` が「現行」の行だけを使います。

━━ 前提（すべて事実。推定にはその旨を書く）━━━━━━━━━━━━━━━━━━━
- 予算は総額10万円（送料込み・社長決定 2026-09-12。旧5万円）。回転上限6ヶ月はハード制約（下の定数ブロック参照）
- 送料は東京都宛の値。本リポは PUBLIC なので社長の住所は使わない。実額は発注時に確定
- 「回転月数」は 30日のランク下落観測数 ÷ (出品者数+1) を1ヶ月の販売見込みとした割り算。
  ランク下落の観測数は販売数そのものではない（memory: keepa_salesrankdrops_is_polling_not_sales）
  ので、**桁を見る道具**であって精度を主張する数字ではない
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCAN_CSV = REPO / "workspace/output/deliverables/T-20260831-006/out/candidates.csv"
# PSE 判定（電気用品安全法）は選定条件側の成果物にある。ここでは読むだけ。
PSE_CSV = REPO / "workspace/output/deliverables/T-20260907-001/out/all_candidates.csv"
BF_DIR = REPO / "workspace/output/deliverables/T-20260904-004"
SUPPLIERS_CSV = REPO / "workspace/output/deliverables/T-20260831-006/out/suppliers.csv"
OUT = HERE / "out"

# ── 社長の固定ルール（2026-09-12・T-20260909-002）。**緩めないこと** ─────────────
# 以前このファイルは、回転46.7ヶ月の案を「手残り最大」という理由で案A/B/D として出していました。
# 社長の言葉:「46か月も回転しない商品に関しては、買うだけ無駄です。言わなくても分かってください」
# 二度と出さないために、ルールをコードの定数とガード（assert_rules）で固定しています。
#
# ルール1  回転上限6ヶ月は**ハード制約**。最小ロットで買った時点でこれを超える SKU は
#          案に入れない・生成しない・「参考」としても出さない。
#          （第4部の落選表にだけ「なぜ落ちたか」として残す。候補としては扱わない）
# ルール2  予算は10万円（送料込み）。旧5万円（2026-09-04）から変更。
# ルール3  手残り・粗利で案を順位付けしない。1周目は「完走して学ぶ」テストで、
#          社長は10万円を失ってもよいと明言している。順位の軸は
#          「6ヶ月以内に確実に捌ける見込み」と「出品制限・供給停止で全滅しにくいか」。
# ルール4  2社以上への分散は望ましいが、ルール1より下位。両立しなければ1社でよい
#          （その場合は全滅シナリオに明記する）。
TOTAL_BUDGET_YEN = 100_000
TURNOVER_CAP_MONTHS = 6.0
# 月販見込はドロップ数からの推定で、**実際より大きく出る向き**の誤差がある
# （ポーリング回数であって販売数ではない／バリエーション兄弟のランク共有）。
# 推定が2倍外れても上限内で捌けるよう、**積み増しは上限の半分まで**にする。
ESTIMATE_SAFETY_FACTOR = 2.0
TOPUP_TARGET_MONTHS = TURNOVER_CAP_MONTHS / ESTIMATE_SAFETY_FACTOR
# 案は多くても2つ。社長は選択肢の多さを求めていない（2026-09-12）。
MAX_PLANS = 2
PREF = "東京都"

# ── 1点あたりの納品コストの内訳（経理ハジメ C1_費目一覧.csv / T-20260904-004）──
# 元データ candidates.csv の列「納品送料(FBA+納品代行)」＝ 50円 は、この3つの合計です。
#   ・納品代行 作業費   12.0円/点 … 検品・ラベル貼付・**梱包資材込み**（e-fba 公開料金）
#   ・FBA 納品送料      37.5円/点 … 納品代行 → FBA 750円/箱(140サイズ) ÷ 20点
#   ・NETSEA 送料の按分  ほぼ0円   … /items の ship_fee は 257,067件中 99.6% が 0
#
# ⚠️ **作業費は 2026-09-04（commit bf44b59）から純利益に入っています。**
#    経理の CSV に残る「【現行モデルに欠落】」は、その修正より前に書かれた注記です。
#    ここでやるのは**表示を分けることだけ**で、純利益は1円も動きません。
#    もう一度引くと二重計上になります（資材費 materials_cost=0 も同じ理由）。
PREP_SERVICE_YEN = 12.0
FBA_INBOUND_YEN = 37.5

# 社長が案から外すと決めた SKU。**候補から消さずに、外した理由ごと残す**
# （消すと「なぜ無いのか」が半年後に読めなくなる）。
EXCLUDED_ASINS = {
    # ⚠️ 金額はここに書きません（このファイルは Git 追跡対象・PUBLIC リポ）。
    #    実額は元データから引いて out/ の HTML に出します。
    "B00HHIGOU8": ("社長判断 2026-09-09。利益率が薄く、送料や資材が数十円ずれるだけで赤字になる。"
                   "FBAサイズが「不明（寸法・重量なし）」で、実サイズ次第では FBA配送代行手数料が"
                   "上振れする。案Eの粗利に対する寄与も小さい"),
}


# ── 入力 ───────────────────────────────────────────────────────────────
def load_pool(path: Path) -> list[dict]:
    """供給が生きていると確認できた ASIN だけを返す。"""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["供給ステータス"] == "現行"]


def load_facts(asins: set[str]) -> dict[str, dict]:
    with open(SCAN_CSV, encoding="utf-8-sig") as f:
        return {r["ASIN"]: r for r in csv.DictReader(f) if r["ASIN"] in asins}


def load_pse(asins: set[str]) -> dict[str, dict]:
    """PSE 判定など、選定条件側で付いた印。無ければ空で返す（推定で埋めない）。"""
    if not PSE_CSV.exists():
        return {}
    with open(PSE_CSV, encoding="utf-8-sig") as f:
        return {r["ASIN"]: r for r in csv.DictReader(f) if r["ASIN"] in asins}


def load_supplier_ids() -> dict[str, int]:
    with open(SUPPLIERS_CSV, encoding="utf-8-sig") as f:
        return {r["サプライヤー名"]: int(r["supplier_id"])
                for r in csv.DictReader(f) if r["supplier_id"]}


def load_tariffs(supplier_ids: list[int]) -> dict:
    """送料設定。取れなければ空のまま返す（推定で埋めない）。"""
    sys.path.insert(0, str(BF_DIR))
    import budget_filter as BF  # noqa: E402
    return BF.fetch_tariffs(supplier_ids)


def read_shipping(tariff: dict | None, order_total: int) -> tuple[int | None, str]:
    """この注文額のとき実際にいくら送料が掛かるか。

    ⚠️ `gradual_border_price` は送料無料ラインではない。**price2 == 0 のときだけ**
    「その金額以上で無料」。正の値なら「安くなる」だけ。
    （memory: knowledge_netsea_tariffs_api。名前が意味を語るフィールドの罠）
    """
    if not tariff:
        return None, "この社は /tariffs に設定が無い（未取得ではない）"
    hit = next((p for p in (tariff.get("prices") or []) if p.get("prefecture") == PREF), None)
    if hit is None:
        return None, f"{PREF} の設定なし（対象都道府県外）"
    p1, p2 = hit.get("price1"), hit.get("price2")
    border = tariff.get("gradual_border_price")
    if not tariff.get("gradual_flag") or border is None:
        note = ("常に無料" if p1 == 0
                else f"常に {p1}円（段階設定なし＝積んでも変わらない）")
        return int(p1), note
    if order_total >= int(border):
        note = (f"{int(border):,}円以上なので無料" if p2 == 0
                else f"{int(border):,}円以上なので {p2}円")
        return int(p2), note
    tail = "以上で無料" if p2 == 0 else f"以上で {p2}円"
    return int(p1), f"{p1}円（あと{int(border) - order_total:,}円積めば{int(border):,}円{tail}）"


# ── SKU の採算 ─────────────────────────────────────────────────────────
def _i(fact: dict, key: str) -> int:
    """CSV の数値セル。空文字は 0 にする（欠測と 0 の区別は別途 fact を見る）。"""
    v = (fact.get(key) or "").strip()
    return int(float(v)) if v else 0


# 保管料の前提。`T-20260831-006/pipeline/config.py` の storage_months=1.5 と同値。
# 「3ヶ月で線形に売り切る＝平均在庫は初期数量の半分＝実効1.5ヶ月」という置き方。
# ここを二重定義したくないが、依存を増やさない方（YAGNI）を採った。ズレたら気づけるよう
# 数字の意味を書いておく。
STORAGE_MONTHS_ASSUMED = 1.5


def build_sku(pool_row: dict, fact: dict, pse: dict | None = None) -> dict:
    """1 SKU 分の発注パラメータ。金額は税込。

    NETSEA の1口（unit）と Amazon の1出品（listing）は別物。
    Amazon 側がケース売りなら listing = unit × 入数 になる。ここを混ぜると口数が狂う。
    """
    pack = int(fact["出品の入数"] or 1)                 # 1出品 = NETSEA 何口か
    moq_units = int(fact["最小発注数"] or 1)
    moq_yen = int(fact["最小発注額(税込)"] or 0)
    unit_price = moq_yen / moq_units if moq_units else 0

    drops = int(fact["月間販売数(30日ランク下落数)"] or 0)
    sellers = int(fact["出品者数"] or 0)
    per_month = drops / (sellers + 1) if drops else 0.0   # 1ヶ月に自分が捌ける見込み

    # 最小発注数は「入数の倍数」に切り上げる。端数の口は出品にならず在庫として死ぬ。
    min_units = int(math.ceil(moq_units / pack) * pack)

    return {
        "ASIN": pool_row["ASIN"],
        "商品名": pool_row["商品名"],
        "メーカー": pool_row["メーカー"],
        "仕入先": pool_row["仕入先"],
        "入数": pack,
        "単価": unit_price,
        "最小口数": min_units,
        "純利益": float(fact["純利益"] or 0),          # 1出品あたり
        "利益率%": float(fact["利益率%"] or 0),
        "ランク": int(fact["ランキング"] or 0),
        "出品者数": sellers,
        "月販見込": per_month,
        "FBAサイズ": fact["FBAサイズ"],
        "要確認": fact.get("発注前に必ず確認", "") or fact.get("要確認理由", ""),
        "状態注記": fact.get("状態", ""),

        # ── ここから下は「計算過程を画面に出す」ための素材。計算には使わない ──
        "Amazon商品名": fact.get("Amazon商品名") or pool_row["商品名"],
        "JAN": fact.get("JAN", ""),
        "業態": fact.get("業態", ""),
        "卸値税抜": _i(fact, "NETSEA卸値(税抜)"),
        "卸値税込": _i(fact, "NETSEA卸値(税込)"),
        "Amazon価格": _i(fact, "Amazon価格"),
        "価格の出所": fact.get("価格の出所", ""),
        "ROI%": float(fact.get("ROI%") or 0),
        "利益率区分": fact.get("利益率区分", ""),
        "ドロップ30": drops,
        "ドロップ90平均": _i(fact, "月間販売数(90日ドロップ÷3)"),
        "出品者数の出所": fact.get("出品者数の出所", ""),
        "Amazon本体": fact.get("Amazon本体の有無", ""),
        "手数料内訳": fact.get("手数料内訳", ""),
        "販売手数料": _i(fact, "販売手数料(消費税込)"),
        "FBA配送料": _i(fact, "FBA配送料"),
        "保管料": _i(fact, "保管料"),
        "納品送料": _i(fact, "納品送料(FBA+納品代行)"),
        "基本成約料": _i(fact, "基本成約料"),
        "返品引当": _i(fact, "返品引当"),
        "入数の根拠": fact.get("入数の根拠", ""),
        "最小発注数raw": moq_units,
        "最小発注額raw": moq_yen,
        "他サプライヤー数": _i(fact, "他サプライヤー数"),
        "同一JANのASIN数": _i(fact, "同一JANのASIN数"),
        "ネット販売可否": fact.get("ネット販売可否", ""),
        "総合判定": fact.get("総合判定", ""),
        "法令要確認": fact.get("法令要確認", ""),
        "備考": fact.get("備考", ""),
        "Amazonページ": fact.get("Amazonページ", ""),
        "Keepaリンク": fact.get("Keepaリンク", ""),
        "NETSEA商品ページ": fact.get("NETSEA商品ページ", ""),
        "PSE判定": (pse or {}).get("PSE判定", ""),
        "要書類確認": (pse or {}).get("要書類確認", ""),
        "その他の印": (pse or {}).get("その他の印", ""),
        "供給ステータス": pool_row.get("供給ステータス", ""),
        "供給判定日": pool_row.get("判定日", ""),
        "供給根拠": pool_row.get("根拠チケット", ""),
    }


def sensitivity(sku: dict, months: float | None) -> dict:
    """「何が起きるとこの行が赤字になるか」を数字で出す。

    2つだけ。多く出しても社長は使わない（読むのは値下げと保管）。

    1. 値下げ耐性 — 売価を Δ 下げると、販売手数料もそのぶん減るので
       利益の減りは Δ × (1 − 販売手数料率)。利益がゼロになる Δ を出す。
       （返品引当も微減するが無視。無視した分だけ**保守側＝耐性を低めに**出る）
    2. 保管料の膨張 — 見積の保管料は「3ヶ月で売り切る＝実効1.5ヶ月」前提。
       実際に N ヶ月かかるなら平均在庫は N/2 ヶ月分で、保管料は (N/2)/1.5 倍になる。
       寸法が取れず保管料 0 の SKU は計算しない（0 を掛けて安く見せない）。
    """
    price = sku["Amazon価格"]
    fee_rate = (sku["販売手数料"] / price) if price else 0.0
    marginal = 1.0 - fee_rate                      # 1円値下げしたときの利益の減り
    drop_to_zero = (sku["純利益"] / marginal) if marginal > 0 else None

    out = {
        "販売手数料率": fee_rate,
        "値下げ耐性円": drop_to_zero,
        "値下げ耐性率": (drop_to_zero / price) if (drop_to_zero and price) else None,
        "保管料実効月数": None, "保管料補正": None, "保管増": None, "保管後純利益": None,
    }
    if months and sku["保管料"] > 0:
        eff = months / 2.0
        corrected = sku["保管料"] * eff / STORAGE_MONTHS_ASSUMED
        out.update({"保管料実効月数": eff, "保管料補正": corrected,
                    "保管増": corrected - sku["保管料"],
                    "保管後純利益": sku["純利益"] - (corrected - sku["保管料"])})
    return out


def inbound_parts(sku: dict) -> tuple[int, int, int]:
    """「納品送料(FBA+納品代行)」を、社長が読める3つに割り戻す。

    足し直すと元の列と必ず一致します（`その他` は丸めと NETSEA 送料按分の残り）。
    **割り戻すだけで、純利益からもう一度引いてはいけません。**
    """
    total = sku["納品送料"]
    prep = round(PREP_SERVICE_YEN)
    fba = round(FBA_INBOUND_YEN)
    return prep, fba, total - prep - fba


def order_line(sku: dict, units: int) -> dict:
    listings = units // sku["入数"]
    cost = round(sku["単価"] * units)
    gross = round(sku["純利益"] * listings)
    months = (listings / sku["月販見込"]) if sku["月販見込"] else None
    return {**sku, "口数": units, "出品数": listings, "仕入額": cost, "粗利": gross,
            "回転月数": months}


# ── セットを組む ───────────────────────────────────────────────────────
def price_set(lines: list[dict], tariffs: dict, sup_ids: dict) -> dict:
    """サプライヤーごとに送料を1回だけ掛ける。1社にまとめる意味はここにしか無い。"""
    by_sup: dict[str, list[dict]] = {}
    for ln in lines:
        by_sup.setdefault(ln["仕入先"], []).append(ln)

    ship_total, ship_notes = 0, []
    for name, lns in by_sup.items():
        sub = sum(l["仕入額"] for l in lns)
        sid = sup_ids.get(name)
        fee, note = read_shipping(tariffs.get(sid) if sid else None, sub)
        if fee is None:
            ship_notes.append(f"{name}: 送料不明（{note}）")
        else:
            ship_total += fee
            ship_notes.append(f"{name}: {fee}円 … {note}")

    goods = sum(l["仕入額"] for l in lines)
    gross = sum(l["粗利"] for l in lines)
    worst = max((l["回転月数"] or 0) for l in lines) if lines else 0
    return {
        "明細": lines,
        "仕入額": goods,
        "送料": ship_total,
        "総額": goods + ship_total,
        "粗利": gross,
        "手残り": gross - ship_total,   # 送料は原価。粗利から引かないと嘘になる
        "SKU数": len(lines),
        "出品数": sum(l["出品数"] for l in lines),
        "サプライヤー数": len(by_sup),
        "最大社シェア": max(sum(l["仕入額"] for l in v) for v in by_sup.values()) / goods if goods else 0,
        "最長回転月数": worst,
        "送料の内訳": ship_notes,
    }


def topup(lines: list[dict], skus: dict, tariffs: dict, sup_ids: dict,
          target: float = TOPUP_TARGET_MONTHS) -> list[dict]:
    """予算の余りを、在庫が薄い（何ヶ月分かが短い）SKU から順に1出品ずつ積む。

    積む条件は2つだけ。
      1. 積んだ後の在庫が target ヶ月分を超えない（既定は上限6ヶ月の半分＝3ヶ月）
      2. 総額が予算を超えない
    **手残りの増え方では選ばない**（ルール3）。在庫の月数をそろえる方向にだけ積む。
    """
    lines = [dict(l) for l in lines]
    for _ in range(1000):
        best = None
        for i, ln in enumerate(lines):
            sku = skus[ln["ASIN"]]
            if not sku["月販見込"]:
                continue
            nxt = ln["口数"] + sku["入数"]
            months = (nxt // sku["入数"]) / sku["月販見込"]
            if months > target:
                continue
            trial = list(lines)
            trial[i] = order_line(sku, nxt)
            if price_set(trial, tariffs, sup_ids)["総額"] > TOTAL_BUDGET_YEN:
                continue
            if best is None or months < best[2]:
                best = (i, trial[i], months)
        if best is None:
            break
        lines[best[0]] = best[1]
    return lines


def assert_rules(s: dict) -> dict:
    """ルール1・2のガード。**破る案は作った時点で落とす**（表示まで行かせない）。"""
    for l in s["明細"]:
        m = l["回転月数"]
        if m is None or m > TURNOVER_CAP_MONTHS:
            raise AssertionError(f"回転上限違反: {l['ASIN']} {m} ヶ月 > {TURNOVER_CAP_MONTHS}")
    if s["総額"] > TOTAL_BUDGET_YEN:
        raise AssertionError(f"予算超過: {s['総額']} > {TOTAL_BUDGET_YEN}")
    return s


def enumerate_sets(skus: dict, tariffs: dict, sup_ids: dict) -> list[dict]:
    """ルールを通った SKU の全組み合わせを最小ロットで試し、予算に入るものだけ返す。

    SKU が十数件の世界なので総当たりで十分（YAGNI）。50件を超えたら考え直す。
    """
    keys = list(skus)
    out = []
    for n in range(1, len(keys) + 1):
        for combo in itertools.combinations(keys, n):
            base = [order_line(skus[k], skus[k]["最小口数"]) for k in combo]
            priced = price_set(base, tariffs, sup_ids)
            if priced["総額"] <= TOTAL_BUDGET_YEN:
                out.append(assert_rules(priced))
    return out


def wipeout_note(s: dict) -> str:
    """この案が「全滅」する筋書き。ここを書かない案は社長に出せない。"""
    by_sup: dict[str, float] = {}
    for l in s["明細"]:
        by_sup[l["仕入先"]] = by_sup.get(l["仕入先"], 0) + l["仕入額"]
    top, top_amt = max(by_sup.items(), key=lambda kv: kv[1])
    share = top_amt / s["仕入額"] if s["仕入額"] else 0
    n_top = sum(1 for l in s["明細"] if l["仕入先"] == top)

    parts = []
    if share >= 0.99 and s["SKU数"] > 1:
        parts.append(f"1社（{top}）に全額。回転6ヶ月以内で買える2社目が無いため、"
                     f"ルール4（分散はルール1より下位）で1社にしている。この社の取引停止・欠品・"
                     f"出荷遅れで{s['SKU数']}SKU が同時に止まる")
    elif n_top > 1:
        parts.append(f"{top} に {n_top}SKU・仕入額の{share:.0%}。"
                     f"この社が止まると同時に{n_top}SKU 失う（残り{s['SKU数'] - n_top}SKU は生きる）")
    else:
        parts.append(f"1社1SKU に分散済み。1社止まっても失うのは1SKU（最大{share:.0%}）")

    if s["SKU数"] == 1:
        parts.append("SKU が1本しかないので、出品制限に当たった時点で在庫全部が動かせない")
    parts.append("出品制限（ゲート）は未確認。同じカテゴリの SKU ばかりなら、1つのゲートで全部が同時に止まる")
    return " / ".join(parts)


# ── 案を選ぶ（ルール3: 手残りでは選ばない）──────────────────────────────
def _safety_key(s: dict) -> tuple:
    """「全滅しにくく、確実に捌ける」順の並べ方。**手残り・粗利はキーに入れない。**

    1. SKU 数が多い（出品制限に1本当たっても残りが動く）
    2. 仕入先が多い（1社止まっても残りが動く）
    3. 最長の在庫月数が短い（推定が外れても上限内に収まる余裕が大きい）
    """
    return (-s["SKU数"], -s["サプライヤー数"], s["最長回転月数"])


def pick_plans(sets: list[dict], skus: dict, tariffs: dict, sup_ids: dict) -> list[tuple[str, str, dict]]:
    """最大 MAX_PLANS 案。案1＝最小ロットで全部、案2＝同じSKUを安全側の月数まで積む。"""
    if not sets:
        return []
    base = min(sets, key=_safety_key)
    plans = [("案1", "最小ロットだけで完走する（在庫を最小にして、1周を確実に回す）", base)]

    lines = topup(base["明細"], skus, tariffs, sup_ids)
    more = assert_rules(price_set(lines, tariffs, sup_ids))
    if more["出品数"] > base["出品数"] and len(plans) < MAX_PLANS:
        plans.append(("案2",
                      f"同じSKUを各 {TOPUP_TARGET_MONTHS:.0f}ヶ月分まで積む"
                      f"（月販見込が{ESTIMATE_SAFETY_FACTOR:.0f}倍外れても{TURNOVER_CAP_MONTHS:.0f}ヶ月で捌ける量）",
                      more))
    return plans


# ── ①② 回転検証を通過した全件への機械ふるい ─────────────────────────────
def load_passed_candidates() -> list[dict]:
    """選定条件側（T-20260907-001）で「回転検証＝通過」になった全件。"""
    with open(PSE_CSV, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r.get("回転検証") == "通過"]


def screen(passed: list[dict], pool_all: dict[str, dict]) -> list[dict]:
    """ルール1・2を、生産終了チェック済みか否かを問わず全件に当てる。

    ここで機械的に落とせるものを先に落とし、サトルの手作業（生産終了チェック）を最小にする。
    最小ロット金額は商品代だけで判定する（送料は仕入先の組み合わせで変わるので、案の段で足す）。
    """
    facts = load_facts({r["ASIN"] for r in passed})
    pse = load_pse({r["ASIN"] for r in passed})
    out = []
    for r in passed:
        a = r["ASIN"]
        fact = facts.get(a)
        prow = pool_all.get(a)
        entry = {"ASIN": a, "供給": (prow or {}).get("供給ステータス") or "未チェック",
                 "sku": None, "落選理由": [], "通過": False}
        if fact is None:
            entry["落選理由"].append("元データ（candidates.csv）に行が無い")
            out.append(entry)
            continue
        # pool.csv の仕入先が空の行がある（人手の名簿なので）。空なら元データの仕入先で埋める。
        if prow and not prow.get("仕入先"):
            prow = {**prow, "仕入先": fact.get("サプライヤー名") or r.get("サプライヤー", "")}
        row = prow or {"ASIN": a, "商品名": fact.get("商品名") or r.get("Amazon商品名", ""),
                       "メーカー": "", "仕入先": fact.get("サプライヤー名") or r.get("サプライヤー", "")}
        sku = build_sku(row, fact, pse.get(a))
        m = min_lot_months(sku)
        lot_yen = round(sku["単価"] * sku["最小口数"])
        if m is None:
            entry["落選理由"].append("月販見込が出せない（ドロップ数0）")
        elif m > TURNOVER_CAP_MONTHS:
            entry["落選理由"].append(f"最小ロットで {m:.1f}ヶ月分（上限 {TURNOVER_CAP_MONTHS:.0f}ヶ月超）")
        if lot_yen > TOTAL_BUDGET_YEN:
            entry["落選理由"].append(f"最小ロット単独で {lot_yen:,}円（予算 {TOTAL_BUDGET_YEN:,}円超）")
        entry.update(sku=sku, 最小ロット金額=lot_yen, 最小ロット月数=m,
                     通過=not entry["落選理由"])
        out.append(entry)
    return out



HTML_CSS = """
:root{
  color-scheme:light dark;
  --bg:#fff; --surface:#f5f7f9; --surface2:#eceff3;
  --text:#1b1f24; --muted:#525b66; --faint:#6c7681;
  --border:#d5dae1; --border-strong:#b8c0ca;
  --accent:#1c5b86; --accent-bg:#eef5fa;
  --warn:#8a4b00; --warn-bg:#fdf1df; --warn-border:#dd9a3c;
  --alert:#7d2b2b; --alert-bg:#fbeeee; --alert-border:#d08b8b;
  --ok:#1b6144; --ok-bg:#eaf4ef; --ok-border:#8ab9a3;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#15181c; --surface:#1d2126; --surface2:#252a31;
    --text:#e4e8ec; --muted:#aab4bf; --faint:#949eaa;
    --border:#333a43; --border-strong:#48515c;
    --accent:#79b4dc; --accent-bg:#1a2a36;
    --warn:#f0b866; --warn-bg:#332616; --warn-border:#7a5a2a;
    --alert:#e79a9a; --alert-bg:#331e1e; --alert-border:#6e4040;
    --ok:#84cfa9; --ok-bg:#17281f; --ok-border:#3c6450;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
 font-family:"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic Medium","Noto Sans JP",
 system-ui,-apple-system,sans-serif;font-size:16px;line-height:1.8;font-feature-settings:"palt" 1}
.wrap{max-width:1080px;margin:0 auto;padding:30px 20px 90px}
.kicker{font-size:12px;letter-spacing:.14em;color:var(--faint);margin:0 0 10px}
h1{font-size:26px;line-height:1.5;margin:0 0 18px;font-weight:700}
.lead{margin:0;color:var(--muted);font-size:14.5px;line-height:1.8;
 border-left:3px solid var(--border-strong);padding:2px 0 2px 14px}
h1.part{font-size:23px;font-weight:700;margin:60px 0 8px;padding:14px 0 0;
 border-top:4px solid var(--text);scroll-margin-top:14px}
h2{font-size:20px;margin:40px 0 14px;padding-bottom:8px;
 border-bottom:2px solid var(--border-strong);font-weight:700;scroll-margin-top:14px}
h3{font-size:16.5px;margin:30px 0 10px;font-weight:700;scroll-margin-top:14px}
h3::before{content:"";display:inline-block;width:4px;height:1em;background:var(--accent);
 margin-right:9px;vertical-align:-.13em;border-radius:2px}
h4{font-size:14.5px;font-weight:700;color:var(--muted);letter-spacing:.04em;
 margin:16px 0 6px;padding-bottom:3px;border-bottom:1px solid var(--border)}
p{margin:0 0 1.05em}
ul,ol{margin:0 0 1.1em;padding-left:1.6em}
li{margin:.35em 0}
.toc{margin:28px 0 8px;padding:16px 22px 18px;background:var(--surface);
 border:1px solid var(--border);border-radius:10px}
.toc-h{margin:0 0 8px;font-size:13px;font-weight:700;letter-spacing:.1em;color:var(--muted)}
.toc ul{margin:0;padding:0;list-style:none}
.toc li{margin:.25em 0}
.toc a{color:var(--accent);text-decoration:none}
.toc a:hover{text-decoration:underline}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 1.2em;
 border:1px solid var(--border);border-radius:9px}
table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.7}
thead th{background:var(--surface2);text-align:left;font-weight:700;padding:9px 12px;
 border-bottom:2px solid var(--border-strong);white-space:nowrap;vertical-align:bottom}
tbody td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top;
 overflow-wrap:anywhere}
tbody tr:last-child td{border-bottom:0}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--surface) 55%,transparent)}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
tr.sum td{background:var(--surface2);font-weight:700}
tr.noterow td{background:var(--surface);border-bottom:2px solid var(--border-strong)}
table.kv{border:0;font-size:13.5px;margin:0 0 12px}
table.kv th{width:12em;text-align:left;vertical-align:top;font-weight:700;color:var(--muted);
 padding:4px 12px 4px 0;border-bottom:1px solid var(--border);white-space:nowrap;background:none}
table.kv td{padding:4px 0;border-bottom:1px solid var(--border)}
.card{border:1px solid var(--border-strong);border-radius:10px;padding:14px 20px 18px;margin:18px 0}
.card h3{margin-top:6px}
.aim{color:var(--muted);font-size:14px;margin:0 0 10px}
.kvline{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:14px;margin:0 0 12px}
.kvline b{font-variant-numeric:tabular-nums}
.wipe{background:var(--alert-bg);border:1px solid var(--alert-border);
 border-left:5px solid var(--alert);padding:9px 14px;border-radius:0 7px 7px 0;font-size:14px}
.warn{background:var(--warn-bg);border:1px solid var(--warn-border);border-left:6px solid var(--warn-border);
 padding:14px 18px;border-radius:0 9px 9px 0;margin:22px 0}
.alertbox{background:var(--alert-bg);border:2px solid var(--alert);border-left:10px solid var(--alert);
 padding:14px 20px;border-radius:0 9px 9px 0;margin:22px 0}
.note{font-size:13.5px;color:var(--muted);margin:0 0 1em}
.formula{font-family:"SFMono-Regular",Menlo,monospace;font-size:13px;background:var(--surface2);
 border:1px solid var(--border);border-radius:6px;padding:8px 12px;margin:6px 0 10px;
 white-space:pre-wrap;line-height:1.7;overflow-x:auto}
code{font-family:"SFMono-Regular",Menlo,monospace;font-size:.9em;padding:.05em .35em;
 border-radius:4px;background:var(--surface2);border:1px solid var(--border)}
.ct{font-size:11.5px;color:var(--faint);border:1px solid var(--border);border-radius:3px;
 padding:0 .35em;margin-right:.3em;white-space:nowrap}
.pill{display:inline-block;padding:0 .45em;border-radius:4px;font-weight:700;
 font-size:.85em;white-space:nowrap}
.pill-ok{background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok-border)}
.pill-warn{background:var(--warn-bg);color:var(--warn);border:1px solid var(--warn-border)}
.pill-danger{background:var(--alert);color:#fff;border:1px solid var(--alert)}
.pill-info{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent)}
.pill-muted{background:transparent;color:var(--faint);border:1px dashed var(--border-strong);font-weight:600}
.chips{margin:.4em 0 .2em;line-height:2.1}
.sub{font-size:12.5px;color:var(--muted);line-height:1.6}
.src{margin-top:.4em;font-size:12.5px;color:var(--faint)}
a{color:var(--accent)}
.url{word-break:break-all}
.na{color:var(--faint)}
.est{background:var(--accent-bg);border:1px solid var(--accent);border-radius:6px;
 padding:8px 12px;font-size:13.5px;margin:6px 0 10px}
@media (max-width:640px){
  body{font-size:15px}.wrap{padding:20px 12px 80px}
  h1{font-size:21px}h1.part{font-size:19px}h2{font-size:18px}
  table{font-size:13px}thead th,tbody td{padding:7px 9px}
}
@media print{
  :root{--bg:#fff;--surface:#fff;--surface2:#fff;--text:#000;--muted:#333;--faint:#555;
   --border:#999;--border-strong:#555;--accent:#000;--accent-bg:#fff}
  body{font-size:9.5pt}.wrap{max-width:none;padding:0}
  .tw{overflow:visible}table{font-size:8pt}
  h1.part{break-before:page}
  .card,.tw,tr{break-inside:avoid}
}
"""


def h(x) -> str:
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def yen(x) -> str:
    return f"{round(x):,}円"


def _pill(text: str, kind: str) -> str:
    return f'<span class="pill pill-{kind}">{h(text)}</span>'


def chips(s: dict) -> str:
    """1行で読める判定の並び。値が無いものは「未取得」と書く（黙って消さない）。"""
    out = []
    size = s["FBAサイズ"] or "不明"
    out.append(f'<span class="ct">FBAサイズ</span>'
               + (_pill(size, "warn") if "不明" in size else h(size)))

    pse = s.get("PSE判定") or ""
    out.append('<span class="ct">PSE</span>'
               + (_pill("対象外(PASS)", "ok") if pse == "PASS"
                  else _pill(pse or "未判定", "warn")))

    out.append('<span class="ct">知財ブランド</span>'
               + (_pill(s["法令要確認"], "warn") if s["法令要確認"]
                  else _pill("印なし(要実機確認)", "muted")))

    mark = s.get("その他の印") or ""
    out.append('<span class="ct">中古表記</span>'
               + (_pill(mark, "warn") if mark else _pill("該当なし", "ok")))

    out.append(f'<span class="ct">Amazon本体</span>'
               + (_pill("あり", "warn") if s["Amazon本体"] == "あり" else h(s["Amazon本体"] or "不明")))

    out.append(f'<span class="ct">総合判定</span>{h(s["総合判定"] or "—")}')
    out.append(f'<span class="ct">ネット販売可否</span>{h(s["ネット販売可否"] or "—")}')
    return '<div class="chips">' + " ／ ".join(out) + "</div>"


def links(s: dict) -> str:
    parts = []
    if s["NETSEA商品ページ"]:
        parts.append(f'発注 <a class="url" href="{h(s["NETSEA商品ページ"])}">NETSEA 商品ページ</a>')
    if s["Amazonページ"]:
        parts.append(f'<a class="url" href="{h(s["Amazonページ"])}">Amazon 商品ページ</a>')
    if s["Keepaリンク"]:
        parts.append(f'<a class="url" href="{h(s["Keepaリンク"])}">Keepa</a>')
    return '<div class="src">' + " ／ ".join(parts) + "</div>"


def min_lot_months(s: dict) -> float | None:
    lst = s["最小口数"] // s["入数"]
    return (lst / s["月販見込"]) if s["月販見込"] else None


def sku_card(i: int, s: dict) -> str:
    """1 SKU の全数字。ここを読めば、なぜこの利益になるかが最後まで追える。"""
    lst = s["最小口数"] // s["入数"]
    months = min_lot_months(s)
    sen = sensitivity(s, months)
    p = [f'<div class="card"><h3>{i}. {h(s["Amazon商品名"])}</h3>',
         f'<p class="aim">ASIN {h(s["ASIN"])} ／ JAN {h(s["JAN"])} ／ '
         f'メーカー {h(s["メーカー"])} ／ 仕入先 {h(s["仕入先"])}（{h(s["業態"])}）</p>',
         chips(s)]

    # ── 販売見込 ────────────────────────────────────────────────
    p.append("<h4 >売れる見込み（すべて推定）</h4>")
    p.append('<div class="tw"><table><thead><tr>'
             "<th>30日ドロップ数</th><th>90日ドロップ÷3</th><th>出品者数</th>"
             "<th>月販見込</th><th>ランキング</th><th>最小ロットは何ヶ月分か</th>"
             "</tr></thead><tbody><tr>"
             f'<td class="num">{s["ドロップ30"]}</td>'
             f'<td class="num">{s["ドロップ90平均"]}</td>'
             f'<td class="num">{s["出品者数"]}</td>'
             f'<td class="num">{s["月販見込"]:.2f} 個/月</td>'
             f'<td class="num">{s["ランク"]:,}</td>'
             + (f'<td class="num">{lst}個 ÷ {s["月販見込"]:.2f} ＝ <b>{months:.1f}ヶ月</b></td>'
                if months else '<td class="na">算出不能（ドロップ0）</td>')
             + "</tr></tbody></table></div>")
    p.append('<div class="formula">'
             f'月販見込 ＝ 30日ドロップ数 ÷ (出品者数 + 1) ＝ {s["ドロップ30"]} ÷ '
             f'({s["出品者数"]} + 1) ＝ {s["月販見込"]:.2f} 個/月\n'
             + (f'回転月数 ＝ 出品数 ÷ 月販見込 ＝ {lst} ÷ {s["月販見込"]:.2f} ＝ {months:.1f} ヶ月'
                if months else '回転月数 ＝ 算出不能')
             + "</div>")
    p.append('<div class="est"><b>この2つの数字は推定です。</b>'
             'ドロップ数は Keepa が売れ筋ランクの下落を観測した回数であって、販売数そのものではありません'
             '（観測の頻度に強く相関することを検証済み）。<b>「月◯個売れる」とは読まないでください。</b>'
             '使い道は「1ヶ月に1個も動かない候補を落とす」という<b>下限の足切り</b>だけです。'
             f'出品者数の出所も {h(s["出品者数の出所"] or "不明")} で、実セラー数とは限りません。</div>')

    # ── 利益の内訳 ──────────────────────────────────────────────
    p.append("<h4 >1個売れたときの利益（引き算の全部）</h4>")
    price = s["Amazon価格"]
    prep_in, fba_in, other_in = inbound_parts(s)
    rows = [("Amazon 販売価格", price, f'＋ {h(s["価格の出所"])}'),
            ("仕入原価（卸値・税込）", -s["卸値税込"],
             f'− 税抜 {s["卸値税抜"]:,}円 ×1.1。免税事業者なので税込が実コスト'),
            ("販売手数料（消費税込）", -s["販売手数料"],
             f'− 売価の {sen["販売手数料率"]:.1%}（Amazon のカテゴリ料率 × 消費税1.1）'),
            ("FBA 配送代行手数料", -s["FBA配送料"], f'− {h(s["FBAサイズ"])}'),
            ("基本成約料", -s["基本成約料"], "− 小口プランのため1点ごとに発生（大口には無い）"),
            ("保管料", -s["保管料"],
             "− 3ヶ月で売り切る前提＝実効1.5ヶ月分" if s["保管料"] else "− 寸法が取れず未計上"),
            ("FBA 納品送料", -fba_in,
             "− 納品代行 → FBA 750円/箱(140サイズ) ÷ 20点 ＝ 37.5円（表示は四捨五入）。実測（e-fba 公開料金）"),
            ("納品代行 作業費", -prep_in,
             "− <b>検品・ラベル貼付・梱包資材込み</b>で12円/点（e-fba 公開料金・実測）。"
             "社長は物理作業を外注する方針なので、必ず掛かります。"
             "<b>資材費はここに入っているので別立てしません</b>（二重計上になります）"),
            ("納品まわりのその他", -other_in,
             "− NETSEA 送料の按分と丸めの残り。ship_fee は99.6%が0で入っているため、ほぼ0円")
            if other_in else None,
            ("返品引当", -s["返品引当"], "− 返品率3%×(FBA手数料＋返金処理＋原価の50%)")]
    rows = [r for r in rows if r]
    p.append('<div class="tw"><table><thead><tr><th>項目</th><th>金額</th><th>内訳・根拠</th>'
             "</tr></thead><tbody>")
    for label, v, why in rows:
        em = "納品代行" in label
        p.append(f'<tr><td>{"<b>" if em else ""}{h(label)}{"</b>" if em else ""}</td>'
                 f'<td class="num">{"<b>" if em else ""}{v:+,}円{"</b>" if em else ""}</td>'
                 f"<td>{why}</td></tr>")
    p.append(f'<tr class="sum"><td>＝ 実費込み純利益</td><td class="num">{s["純利益"]:+,.0f}円</td>'
             f'<td>利益率 {s["利益率%"]:.1f}%（売価に対して） ／ '
             f'ROI {s["ROI%"]:.1f}%（仕入原価に対して）</td></tr>')
    p.append("</tbody></table></div>")
    checksum = (price - s["卸値税込"] - s["販売手数料"] - s["FBA配送料"] - s["基本成約料"]
                - s["保管料"] - s["納品送料"] - s["返品引当"])
    p.append(f'<p class="note">検算: {price:,} − {s["卸値税込"]:,} − {s["販売手数料"]:,} − '
             f'{s["FBA配送料"]:,} − {s["基本成約料"]:,} − {s["保管料"]:,} − {s["納品送料"]:,} − '
             f'{s["返品引当"]:,} ＝ <b>{checksum:,}円</b>'
             f'（納品 {s["納品送料"]:,}円 ＝ FBA納品送料 {fba_in}円 ＋ 納品代行 作業費 {prep_in}円'
             + (f' ＋ その他 {other_in}円）' if other_in else "）")
             + (f'（表の純利益 {s["純利益"]:,.0f}円 と {checksum - s["純利益"]:+,.0f}円。'
                "各項目を円未満で丸めた分の差です）" if checksum != s["純利益"]
                else "（表の純利益と一致）")
             + f' ／ 元データの手数料内訳: {h(s["手数料内訳"] or "—")}</p>')

    # ── 仕入れの内訳 ────────────────────────────────────────────
    p.append("<h4 >仕入れの単位（NETSEA の1口と Amazon の1出品は別物）</h4>")
    p.append('<div class="tw"><table><thead><tr>'
             "<th>入数</th><th>1口の卸値</th><th>卸の最小発注数</th><th>入数に切り上げた最小口数</th>"
             "<th>＝出品できる数</th><th>最小ロットの実額</th><th>最小ロットの粗利</th>"
             "</tr></thead><tbody><tr>"
             f'<td class="num">{s["入数"]}</td>'
             f'<td class="num">{s["単価"]:,.0f}円</td>'
             f'<td class="num">{s["最小発注数raw"]}口</td>'
             f'<td class="num">{s["最小口数"]}口</td>'
             f'<td class="num">{lst}点</td>'
             f'<td class="num"><b>{round(s["単価"] * s["最小口数"]):,}円</b></td>'
             f'<td class="num">{round(s["純利益"] * lst):,}円</td>'
             "</tr></tbody></table></div>")
    p.append(f'<div class="formula">出品数 ＝ 口数 × 1 ÷ 入数 ＝ {s["最小口数"]} ÷ {s["入数"]} ＝ {lst} 点\n'
             f'（入数の根拠: {h(s["入数の根拠"] or "—")}）</div>')

    # ── 感応度 ──────────────────────────────────────────────────
    p.append("<h4 >何が起きるとこの行が赤字になるか</h4><ul>")
    if sen["値下げ耐性円"]:
        p.append(f'<li><b>売価が {sen["値下げ耐性円"]:,.0f}円（{sen["値下げ耐性率"]:.1%}）下がると利益ゼロ。</b>'
                 f'{price:,}円 → {price - sen["値下げ耐性円"]:,.0f}円 が損益分岐。'
                 f'値下げ1円につき利益は {1 - sen["販売手数料率"]:.2f}円 減ります'
                 f'（販売手数料 {sen["販売手数料率"]:.1%} も一緒に減るため）。'
                 f'いま同じ商品に出品者が {s["出品者数"]}者います。</li>')
    if sen["保管増"] is not None:
        p.append(f'<li><b>回転が見込みどおり {months:.0f}ヶ月かかると、保管料は '
                 f'{s["保管料"]:,}円 → {sen["保管料補正"]:,.0f}円/個。</b>'
                 f'1個あたり {sen["保管増"]:+,.0f}円、純利益は '
                 f'{s["純利益"]:,.0f}円 → <b>{sen["保管後純利益"]:,.0f}円</b>。'
                 + ("<b>この時点で赤字です。</b>" if sen["保管後純利益"] < 0 else "")
                 + f'（見積は「3ヶ月で売り切る＝実効1.5ヶ月」前提。'
                 f'{months:.0f}ヶ月なら平均在庫は {sen["保管料実効月数"]:.1f}ヶ月分）</li>')
    elif s["保管料"] == 0:
        p.append('<li>保管料が未計上です（寸法・重量が取れていない）。'
                 '<b>実サイズが大きければ、上の純利益はそのぶん減ります。</b></li>')
    if s["Amazon本体"] == "あり":
        p.append("<li>Amazon 本体が同じ商品を売っています。カートを取れない期間が長くなり、"
                 "回転は上の見込みより遅くなる方向に効きます。</li>")
    if s["同一JANのASIN数"] > 1:
        p.append(f'<li>同じ JAN に ASIN が {s["同一JANのASIN数"]}本あります。'
                 "相乗り先を間違えると、売れないページに在庫を置くことになります。</li>")
    p.append("</ul>")

    if s["要確認"]:
        p.append(f'<div class="wipe"><b>発注前に必ず確認</b><br>{h(s["要確認"])}</div>')
    if s["備考"]:
        p.append(f'<p class="note">備考: {h(s["備考"])}</p>')
    p.append(f'<p class="note">供給: <b>{h(s["供給ステータス"])}</b>'
             f'（{h(s["供給判定日"])} / {h(s["供給根拠"])} で生産終了チェック済み）'
             f' ／ 状態: {h(s["状態注記"] or "—")}</p>')
    p.append(links(s))
    p.append("</div>")
    return "\n".join(p)


def write_html(plans, skus, dropped, screened=()):
    """社長がこの1枚だけ開けば発注できる状態にする。

    「どういう計算をしたのか分からない」と言われたので、**式と引き算を画面に出す**。
    ここは Git 追跡外（out/）なので、金額もドロップ数もそのまま書いてよい。
    **回転上限（ルール1）を超える SKU は第3部に出さない。** 第4部の落選表にだけ理由として残す。
    """
    ordered = sorted(skus.values(), key=lambda s: (min_lot_months(s) or 1e9))
    used = {l["ASIN"] for _, _, s in plans for l in s["明細"]}
    passed = [e for e in screened if e["通過"]]
    to_check = [e for e in passed if e["供給"] == "未チェック"]

    p = ['<!doctype html><html lang="ja"><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1">'
         "<title>初回発注セット T-20260909-002</title>"
         '<meta name="robots" content="noindex,nofollow">',
         f"<style>{HTML_CSS}</style>", '<body><div class="wrap">',
         '<p class="kicker">T-20260909-002 ／ 2026-09-12 版（回転上限6ヶ月・予算10万円） ／ '
         '社外秘（NETSEA 卸値を含むため Git 追跡外）</p>',
         "<h1>初回発注セット ─ 回転6ヶ月以内だけで組み直した版</h1>",
         f'<p class="lead">予算 {TOTAL_BUDGET_YEN:,}円（送料込み）。'
         f'回転検証を通過した <b>{len(screened)}件</b> 全部に「最小ロットで6ヶ月以内・'
         f'最小ロット{TOTAL_BUDGET_YEN // 10_000}万円以内」を当て、残ったのは <b>{len(passed)}件</b>。'
         f'そのうち生産終了チェックで「現行」と確認済みで案に使える SKU が <b>{len(skus)}件</b>、'
         f'組んだ案は <b>{len(plans)}案</b> です。送料は NETSEA <code>/tariffs</code> の実額'
         f'（届け先{PREF}）。<br>'
         "<b>この資料は組んだだけで、発注は一切していません（CLAUDE.md §4.1）。</b></p>",
         '<div class="alertbox"><b>この版の固定ルール（社長指示 2026-09-12）</b><br>'
         f'1. 最小ロットで買って <b>{TURNOVER_CAP_MONTHS:.0f}ヶ月を超える SKU は案に入れません</b>。'
         '参考としても出しません（第4部に落選理由として残すだけです）。<br>'
         f'2. 予算は <b>{TOTAL_BUDGET_YEN:,}円</b>。<br>'
         '3. <b>手残り・粗利では案を並べていません。</b>並べる軸は'
         '「6ヶ月以内に確実に捌けるか」と「出品制限・供給停止で全滅しにくいか」です。<br>'
         '4. 2社への分散は望ましいが、1. より下位。両立しなければ1社にして、全滅シナリオに書きます。</div>',
         '<nav class="toc"><p class="toc-h">目次</p><ul>'
         '<li><a href="#p1">第1部 案（最大2案）</a></li>'
         '<li><a href="#p1b">第1部B ふるいの結果と、生産終了チェックが要る SKU</a></li>'
         '<li><a href="#p2">第2部 案ごとの中身と全滅シナリオ</a></li>'
         '<li><a href="#p3">第3部 1SKUずつの全数字（計算はここで追えます）</a></li>'
         '<li><a href="#p4">第4部 最小ロットの実額と何ヶ月分か（全件・落選理由つき）</a></li>'
         '<li><a href="#p5">第5部 この資料の限界</a></li>'
         "</ul></nav>"]

    p.append('<div class="est"><b>納品代行の作業費</b>（1点 '
             f'{PREP_SERVICE_YEN:.0f}円・検品/ラベル/梱包資材込み）は、元データの'
             f'「納品送料(FBA+納品代行)」＝ FBA納品送料 {FBA_INBOUND_YEN:.0f}円 ＋ 作業費 '
             f'{PREP_SERVICE_YEN:.0f}円 として<b>純利益に入っています</b>（2026-09-04 以降）。'
             '第3部で1行に分けて見せているだけで、二重には引いていません。</div>')

    # ── 第1部 ───────────────────────────────────────────────────
    p.append('<h1 class="part" id="p1">第1部 案</h1>')
    if not plans:
        p.append('<div class="warn"><b>いまの「現行」確認済み SKU では、ルールを満たす案が組めません。</b>'
                 '第1部B の生産終了チェックが済むのを待ってください。</div>')
    p.append('<div class="tw"><table><thead><tr><th>案</th><th>ねらい</th><th>SKU</th><th>社数</th>'
             "<th>出品数</th><th>最長回転月数</th><th>仕入額</th><th>送料</th><th>総額</th>"
             "<th>予算の残り</th><th>粗利（参考）</th>"
             "</tr></thead><tbody>")
    for lbl, aim, s in plans:
        p.append(f'<tr><td><b>{lbl}</b></td><td>{h(aim)}</td>'
                 f'<td class="num">{s["SKU数"]}</td><td class="num">{s["サプライヤー数"]}</td>'
                 f'<td class="num">{s["出品数"]}</td>'
                 f'<td class="num"><b>{s["最長回転月数"]:.1f}</b></td>'
                 f'<td class="num">{s["仕入額"]:,}</td>'
                 f'<td class="num">{s["送料"]:,}</td><td class="num"><b>{s["総額"]:,}</b></td>'
                 f'<td class="num">{TOTAL_BUDGET_YEN - s["総額"]:,}</td>'
                 f'<td class="num">{s["粗利"]:,}</td></tr>')
    p.append("</tbody></table></div>")
    p.append('<p class="note"><b>並び順は手残りではありません</b>（ルール3）。'
             "案1は在庫を最小にして1周を確実に回す案、案2は同じSKUを"
             f"「月販見込が{ESTIMATE_SAFETY_FACTOR:.0f}倍外れても{TURNOVER_CAP_MONTHS:.0f}ヶ月で捌ける量」"
             f"（各 {TOPUP_TARGET_MONTHS:.0f}ヶ月分）まで積んだ案です。"
             "粗利は全部売れた場合の数字で、参考として置いているだけです。</p>")
    if plans and plans[0][2]["総額"] < TOTAL_BUDGET_YEN * 0.3:
        p.append('<div class="warn"><b>予算の大半が残ります。</b>'
                 "これは使える SKU が少ないためで、予算を使い切るために回転の遅い SKU を足すことはしません。"
                 f"第1部B の <b>{len(to_check)}件</b>の生産終了チェックが済めば、"
                 "<code>pool.csv</code> に行を足して再実行するだけで案が厚くなります。</div>")

    # ── 第1部B ─────────────────────────────────────────────────
    p.append('<h1 class="part" id="p1b">第1部B ふるいの結果と、生産終了チェックが要る SKU</h1>')
    by_state: dict[str, list] = {}
    for e in passed:
        by_state.setdefault(e["供給"], []).append(e)
    p.append(f'<p>回転検証を通過した <b>{len(screened)}件</b> → 最小ロットで'
             f'{TURNOVER_CAP_MONTHS:.0f}ヶ月以内・最小ロット{TOTAL_BUDGET_YEN:,}円以内 → '
             f'<b>{len(passed)}件</b>。生産終了チェックの状況で分けるとこうなります。</p>')
    p.append('<div class="tw"><table><thead><tr><th>生産終了チェック</th><th>件数</th><th>扱い</th>'
             "</tr></thead><tbody>")
    meaning = {"現行": "案に使える（社長判断で外したものを除く）",
               "未チェック": "<b>サトルに回す</b>（下の表）",
               "販売終了": "使えない（供給が止まっている）"}
    for st, es in sorted(by_state.items(), key=lambda kv: -len(kv[1])):
        p.append(f'<tr><td>{h(st)}</td><td class="num">{len(es)}</td>'
                 f'<td>{meaning.get(st, "チェックはしたが結論が出ていない。再確認が要る")}</td></tr>')
    p.append("</tbody></table></div>")
    p.append(f"<h2>サトルに回す {len(to_check)}件（pool.csv にまだ無い）</h2>")
    p.append('<div class="tw"><table><thead><tr><th>商品名 / ASIN</th><th>仕入先</th>'
             "<th>最小ロット</th><th>実額</th><th>何ヶ月分か</th><th>月販見込</th></tr></thead><tbody>")
    for e in sorted(to_check, key=lambda x: x["最小ロット月数"]):
        s = e["sku"]
        p.append(f'<tr><td><b>{h(s["商品名"])}</b><div class="sub">ASIN {h(s["ASIN"])}</div></td>'
                 f'<td>{h(s["仕入先"])}</td><td class="num">{s["最小口数"]}口</td>'
                 f'<td class="num">{e["最小ロット金額"]:,}円</td>'
                 f'<td class="num">{e["最小ロット月数"]:.1f}</td>'
                 f'<td class="num">{s["月販見込"]:.2f}</td></tr>')
    p.append("</tbody></table></div>")
    undecided = [e for e in passed if e["供給"] not in ("現行", "未チェック", "販売終了")]
    if undecided:
        p.append("<h2>チェックはしたが結論が出ていないもの（再確認の候補）</h2><ul>"
                 + "".join(f'<li>{h(e["sku"]["商品名"])}（{h(e["ASIN"])}）─ {h(e["供給"])}／'
                           f'最小ロット {e["最小ロット金額"]:,}円・{e["最小ロット月数"]:.1f}ヶ月分</li>'
                           for e in undecided) + "</ul>")



    # ── 第2部 ───────────────────────────────────────────────────
    p.append('<h1 class="part" id="p2">第2部 案ごとの中身と全滅シナリオ</h1>')
    for lbl, aim, s in plans:
        p.append(f'<div class="card"><h3>{lbl} ─ {h(aim)}</h3>'
                 f'<div class="kvline"><span>総額 <b>{s["総額"]:,}円</b></span>'
                 f'<span>うち送料 <b>{s["送料"]:,}円</b></span>'
                 f'<span>粗利（参考） {s["粗利"]:,}円</span>'
                 f'<span>最長回転 <b>{s["最長回転月数"]:.1f}ヶ月</b></span>'
                 f'<span>{s["SKU数"]}SKU / {s["サプライヤー数"]}社 / 出品{s["出品数"]}点</span>'
                 f'<span>予算の残り {TOTAL_BUDGET_YEN - s["総額"]:,}円</span>'
                 f'<span>納品代行 作業費 <b>{round(s["出品数"] * PREP_SERVICE_YEN):,}円</b>'
                 f'（{s["出品数"]}点 × {PREP_SERVICE_YEN:.0f}円・粗利に反映済み）</span></div>')

        by_sup: dict[str, list[dict]] = {}
        for ln in s["明細"]:
            by_sup.setdefault(ln["仕入先"], []).append(ln)
        note_by_sup = {n.split(":", 1)[0]: n.split(":", 1)[1].strip()
                       for n in s["送料の内訳"] if ":" in n}

        for sup, lns in sorted(by_sup.items(), key=lambda kv: -sum(l["仕入額"] for l in kv[1])):
            sub = sum(l["仕入額"] for l in lns)
            p.append(f"<h4 >{h(sup)} ─ {len(lns)}SKU / {sub:,}円</h4>")
            p.append('<table class="kv"><tbody>'
                     f'<tr><th>この社への注文額</th><td>{sub:,}円</td></tr>'
                     f'<tr><th>送料の実額と段階</th><td>{h(note_by_sup.get(sup, "—"))}</td></tr>'
                     '<tr><th>送料の出所</th><td>NETSEA <code>GET /tariffs</code> の実データ'
                     f'（届け先{PREF}）。推定値ではありません</td></tr></tbody></table>')
            p.append('<div class="tw"><table><thead><tr>'
                     "<th>商品名 / ASIN</th><th>卸値(税込)<br>⇢ Amazon価格</th>"
                     "<th>実費込み<br>純利益 / 率 / ROI</th>"
                     "<th>30日ドロップ<br>/ 出品者数</th><th>月販見込<br>（推定）</th>"
                     "<th>仕入額<br>/ 口数・出品数</th><th>この行の粗利</th><th>回転月数<br>（推定）</th>"
                     "</tr></thead><tbody>")
            for l in sorted(lns, key=lambda x: -x["仕入額"]):
                p.append(f'<tr><td><b>{h(l["商品名"])}</b>'
                         f'<div class="sub">ASIN {h(l["ASIN"])} ／ {h(l["メーカー"])}</div></td>'
                         f'<td class="num">{l["卸値税込"]:,}円<br>⇢ {l["Amazon価格"]:,}円</td>'
                         f'<td class="num">{l["純利益"]:,.0f}円<br>{l["利益率%"]:.1f}% / ROI {l["ROI%"]:.0f}%</td>'
                         f'<td class="num">{l["ドロップ30"]}回<br>出品者 {l["出品者数"]}</td>'
                         f'<td class="num">{l["月販見込"]:.2f}個/月</td>'
                         f'<td class="num">{l["仕入額"]:,}円<br>'
                         f'<span class="sub">{l["口数"]}口 / {l["出品数"]}点</span></td>'
                         f'<td class="num"><b>{l["粗利"]:,}円</b></td>'
                         + (f'<td class="num">{l["回転月数"]:.1f}</td>' if l["回転月数"]
                            else '<td class="na">—</td>')
                         + "</tr>")
                p.append(f'<tr class="noterow"><td colspan="8">{chips(l)}'
                         + (f'<div class="sub"><b>発注前に必ず確認:</b> {h(l["要確認"])}</div>'
                            if l["要確認"] else "")
                         + links(l) + "</td></tr>")
            p.append(f'<tr class="sum"><td>この社の小計</td><td></td><td></td><td></td><td></td>'
                     f'<td class="num">{sub:,}円</td>'
                     f'<td class="num">{sum(l["粗利"] for l in lns):,}円</td><td></td></tr>')
            p.append("</tbody></table></div>")

        p.append(f'<div class="wipe"><b>全滅シナリオ</b><br>{h(wipeout_note(s))}</div></div>')

    # ── 第3部 ───────────────────────────────────────────────────
    p.append('<h1 class="part" id="p3">第3部 1SKUずつの全数字</h1>')
    p.append('<p class="note">案に使える SKU（回転上限内・「現行」確認済み）だけを、在庫が薄い順に載せています。'
             "回転上限を超える SKU はここには出しません（ルール1）。</p>")
    for i, s in enumerate(ordered, 1):
        card = sku_card(i, s)
        tag = (' <span class="pill pill-ok">案に採用</span>' if s["ASIN"] in used
               else ' <span class="pill pill-muted">どの案にも入っていない</span>')
        p.append(card.replace("</h3>", tag + "</h3>", 1))

    # ── 第4部 ───────────────────────────────────────────────────
    p.append('<h1 class="part" id="p4">第4部 最小ロットの実額と、それが何ヶ月分か（全件）</h1>')
    p.append(f"<p>回転検証を通過した <b>{len(screened)}件</b> すべてです。"
             "<b>赤い理由が付いた行は候補ではありません。</b>なぜ落ちたかを残すために載せています。</p>")
    p.append('<div class="tw"><table><thead><tr><th>商品名 / ASIN</th><th>仕入先</th>'
             "<th>入数</th><th>最小口数</th><th>＝出品数</th><th>最小ロットの実額</th>"
             "<th>月販見込<br>（推定）</th><th>何ヶ月分か<br>（推定）</th>"
             "<th>生産終了チェック</th><th>扱い</th></tr></thead><tbody>")
    def _rank(e):
        return (0 if e["通過"] else 1, e.get("最小ロット月数") or 1e9)
    for e in sorted(screened, key=_rank):
        s = e["sku"]
        if s is None:
            p.append(f'<tr><td>{h(e["ASIN"])}</td><td colspan="8"></td>'
                     f'<td>{_pill(" / ".join(e["落選理由"]), "danger")}</td></tr>')
            continue
        m = e["最小ロット月数"]
        if not e["通過"]:
            verdict = _pill("落選: " + " / ".join(e["落選理由"]), "danger")
        elif s["ASIN"] in EXCLUDED_ASINS:
            verdict = _pill("ルール内だが社長判断で除外", "warn")
        elif e["供給"] == "未チェック":
            verdict = _pill("ルール内・生産終了チェック待ち（サトル）", "warn")
        elif e["供給"] != "現行":
            verdict = _pill(f"ルール内だが供給が「{e['供給']}」", "muted")
        elif s["ASIN"] in used:
            verdict = _pill("案に採用", "ok")
        else:
            verdict = _pill("ルール内・予算に入らず案に入らない", "muted")
        p.append(f'<tr><td><b>{h(s["商品名"])}</b>'
                 f'<div class="sub">ASIN {h(s["ASIN"])}</div></td>'
                 f'<td>{h(s["仕入先"])}</td><td class="num">{s["入数"]}</td>'
                 f'<td class="num">{s["最小口数"]}口</td><td class="num">{s["最小口数"] // s["入数"]}点</td>'
                 f'<td class="num"><b>{e["最小ロット金額"]:,}円</b></td>'
                 f'<td class="num">{s["月販見込"]:.2f}</td>'
                 + (f'<td class="num"><b>{m:.1f}ヶ月</b></td>' if m else '<td class="na">—</td>')
                 + f'<td>{h(e["供給"])}</td><td>{verdict}</td></tr>')
    p.append("</tbody></table></div>")
    p.append('<p class="note">「何ヶ月分か」＝ 最小ロットの出品数 ÷ 月販見込。'
             "月販見込はドロップ数 ÷ (出品者数+1) の推定値なので、この列も推定です。"
             "<b>桁を見る道具</b>として扱ってください。"
             "最小ロットの実額は商品代だけで、送料は含みません（送料は案の段で仕入先ごとに足しています）。</p>")


    # ── 第5部 ───────────────────────────────────────────────────
    p.append('<h1 class="part" id="p5">第5部 この資料の限界</h1>')
    p.append('<div class="alertbox"><b>候補が出た＝買ってよい、ではありません。</b>'
             "下の項目は、人が目で見るまで埋まりません。</div>")
    p.append('<div class="tw"><table><thead><tr><th>項目</th><th>いまの状態</th><th>なぜ</th>'
             "</tr></thead><tbody>"
             "<tr><td>出品制限（ゲート）</td><td>1件も確認していない</td>"
             "<td>セラーセントラルの商品登録画面でしか分かりません。"
             "日本ストアは再開したので、発注前に全SKUを実機確認してください</td></tr>"
             "<tr><td>カート最終獲得日・カート不在率</td><td><b>取得していない</b></td>"
             "<td>今回のスキャンは BuyBox 履歴を取っていません（Keepa の offers パラメータを"
             "付けていないため、取れば取れます）。無い数字を推定で埋めることはしませんでした</td></tr>"
             "<tr><td>バリエーション子かどうか</td><td><b>取得していない</b></td>"
             "<td>同上。バリエーション兄弟はランクを共有するので、"
             "子だとドロップ数が兄弟の売上で膨らみます。<b>上の月販見込が実際より大きく出る向きの誤差</b>です</td></tr>"
             "<tr><td>商品ページの「販売条件」タブ</td><td>未読</td>"
             "<td>Amazon 不可・モール不可・売価厳守の記載は API では取れません。"
             "1SKUずつ NETSEA の商品ページを開いて読んでください</td></tr>"
             "<tr><td>中古・アウトレット表記</td><td>テキスト判定のみ</td>"
             "<td>画像と販売条件タブは未確認です。当社は古物商許可を持っていないので、"
             "1点でも中古が混じると無許可営業になります</td></tr>"
             "<tr><td>送料の届け先</td><td>東京都で計算</td>"
             "<td>本リポは PUBLIC なので社長の住所を使っていません。実額は発注画面で確定します</td></tr>"
             "<tr><td>返品率3%</td><td>自社実績ゼロ</td>"
             "<td>販売実績が無いため業界一般値です。初回販売後に実績へ差し替えてください</td></tr>"
             "</tbody></table></div>")
    p.append("<h2>更新のしかた</h2>"
             "<p>生産終了チェックの続報が届いたら、<code>pool.csv</code> に「現行」の行を足して "
             "<code>python3 order_set.py</code> を実行し直すだけです。コードは触りません。</p>")
    if dropped:
        p.append(f'<p class="note">元データに見つからなかった ASIN: {h(dropped)}</p>')
    p.append("</div></body></html>")
    (OUT / "03_発注セット.html").write_text("\n".join(p), encoding="utf-8")


def write_outputs(plans, skus, tariffs, sup_ids, dropped, screened=()):
    OUT.mkdir(exist_ok=True)

    with open(OUT / "01_発注セット_案別.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["案", "ねらい", "仕入先", "ASIN", "商品名", "メーカー",
                    "入数", "発注口数", "出品数", "仕入額(税込)", "1出品の純利益",
                    "利益率%", "ROI%", "この行の粗利",
                    "30日ドロップ数", "出品者数", "月販見込(推定)", "回転月数(推定)",
                    "ランク", "Amazon価格", "卸値(税込)", "販売手数料", "FBA配送料",
                    "基本成約料", "保管料", "納品送料計", "うちFBA納品送料", "うち納品代行作業費",
                    "返品引当",
                    "FBAサイズ", "PSE判定", "Amazon本体", "発注前に確認すること"])
        for lbl, aim, s in plans:
            for l in sorted(s["明細"], key=lambda x: (x["仕入先"], -x["仕入額"])):
                w.writerow([lbl, aim, l["仕入先"], l["ASIN"], l["商品名"], l["メーカー"],
                            l["入数"], l["口数"], l["出品数"], l["仕入額"],
                            round(l["純利益"]), round(l["利益率%"], 1), round(l["ROI%"], 1),
                            l["粗利"],
                            l["ドロップ30"], l["出品者数"], f'{l["月販見込"]:.2f}',
                            f"{l['回転月数']:.1f}" if l["回転月数"] else "",
                            l["ランク"], l["Amazon価格"], l["卸値税込"], l["販売手数料"],
                            l["FBA配送料"], l["基本成約料"], l["保管料"], l["納品送料"],
                            inbound_parts(l)[1], inbound_parts(l)[0],
                            l["返品引当"], l["FBAサイズ"], l["PSE判定"], l["Amazon本体"],
                            l["要確認"]])
            w.writerow([lbl, "＝合計＝", f"{s['サプライヤー数']}社", "", "", "", "",
                        "", s["出品数"], s["仕入額"], "", "", "", s["粗利"],
                        "", "", "", f"{s['最長回転月数']:.1f}", "", "", "", "", "", "", "", "",
                        "", "", "", "", "", "",
                        f"送料{s['送料']}円 / 総額{s['総額']}円"])

    with open(OUT / "02_案の比較.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["案", "ねらい", "SKU数", "サプライヤー数", "出品数", "最長回転月数",
                    "仕入額(税込)", "送料", "総額", "予算の残り", "粗利(参考・全部売れた場合)",
                    "最大1社シェア", "全滅シナリオ", "送料の内訳"])
        for lbl, aim, s in plans:
            w.writerow([lbl, aim, s["SKU数"], s["サプライヤー数"], s["出品数"],
                        f"{s['最長回転月数']:.1f}", s["仕入額"], s["送料"], s["総額"],
                        TOTAL_BUDGET_YEN - s["総額"], s["粗利"],
                        f"{s['最大社シェア']:.0%}", wipeout_note(s), " ｜ ".join(s["送料の内訳"])])

    # ①② のふるい結果。落選行は理由つきで残す（候補ではない）。
    with open(OUT / "04_回転ふるい_全件.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["判定", "落選理由", "生産終了チェック", "サトルに回す", "ASIN", "商品名", "仕入先",
                    "入数", "最小口数", "最小ロット出品数", "最小ロット金額(税込)",
                    "月販見込(推定)", "最小ロットの回転月数(推定)"])
        for e in screened:
            s = e["sku"] or {}
            w.writerow(["通過" if e["通過"] else "落選", " / ".join(e["落選理由"]), e["供給"],
                        "○" if (e["通過"] and e["供給"] == "未チェック") else "",
                        e["ASIN"], s.get("商品名", ""), s.get("仕入先", ""),
                        s.get("入数", ""), s.get("最小口数", ""),
                        (s["最小口数"] // s["入数"]) if s else "",
                        e.get("最小ロット金額", ""), f'{s["月販見込"]:.2f}' if s else "",
                        f'{e["最小ロット月数"]:.1f}' if e.get("最小ロット月数") else ""])

    write_html(plans, skus, dropped, screened)

    json.dump({"予算": TOTAL_BUDGET_YEN, "回転上限月数": TURNOVER_CAP_MONTHS,
               "積み増し上限月数": TOPUP_TARGET_MONTHS, "届け先": PREF, "除外": dropped,
               "案": [{"案": lbl, "ねらい": aim, "全滅シナリオ": wipeout_note(s),
                       **{k: v for k, v in s.items() if k != "明細"},
                       "明細": s["明細"]} for lbl, aim, s in plans]},
              open(OUT / "plans.json", "w"), ensure_ascii=False, indent=1, default=str)


def main():
    with open(HERE / "pool.csv", encoding="utf-8-sig") as f:
        pool_all = {r["ASIN"]: r for r in csv.DictReader(f)}

    # ① 回転検証を通過した全件に、ルール1・2を機械で当てる（生産終了チェックの有無は問わない）
    screened = screen(load_passed_candidates(), pool_all)
    passed = [e for e in screened if e["通過"]]
    print(f"① 回転検証通過 {len(screened)}件 → 回転{TURNOVER_CAP_MONTHS:.0f}ヶ月以内・"
          f"最小ロット{TOTAL_BUDGET_YEN:,}円以内 {len(passed)}件")
    for e in sorted(passed, key=lambda x: x["最小ロット月数"]):
        s = e["sku"]
        print(f"   {e['ASIN']} {s['商品名'][:22]:24} {e['最小ロット月数']:4.1f}ヶ月"
              f" {e['最小ロット金額']:>7,}円 [{e['供給']}] {s['仕入先']}")

    # ② 生産終了チェックが要るもの（pool.csv にまだ無い）
    to_check = [e for e in passed if e["供給"] == "未チェック"]
    print(f"② 生産終了チェックが要る（pool.csv 未掲載） {len(to_check)}件")

    # ③ 「現行」かつ①通過かつ社長除外でないものだけで組む
    skus = {e["ASIN"]: e["sku"] for e in passed
            if e["供給"] == "現行" and e["ASIN"] not in EXCLUDED_ASINS}
    dropped = [e["ASIN"] for e in screened if e["sku"] is None]
    sup_ids = load_supplier_ids()
    tariffs = load_tariffs([sup_ids[s["仕入先"]] for s in skus.values()
                            if s["仕入先"] in sup_ids])

    sets = enumerate_sets(skus, tariffs, sup_ids)
    plans = pick_plans(sets, skus, tariffs, sup_ids)
    print(f"③ 使える SKU {len(skus)}件 / 予算内の組み合わせ {len(sets)}通り / 案 {len(plans)}")
    if not plans:
        print("⚠ ルールを満たす案が組めません（②のチェック待ち）")

    write_outputs(plans, skus, tariffs, sup_ids, dropped, screened)
    for lbl, aim, s in plans:
        print(f"\n{lbl} {aim}")
        print(f"  {s['SKU数']}SKU / {s['サプライヤー数']}社 / 出品{s['出品数']}点"
              f" / 総額{s['総額']:,}円（送料{s['送料']}円） / 最長回転{s['最長回転月数']:.1f}ヶ月")
        print(f"  全滅: {wipeout_note(s)}")
    print(f"\n書き出し: {OUT}")


if __name__ == "__main__":
    main()
