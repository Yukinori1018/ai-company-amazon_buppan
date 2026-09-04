#!/usr/bin/env python3
"""初回仕入れ（総額5万円）の制約で候補を絞る — T-20260904-004 / A-2。

入力: T-20260831-006 のスキャン成果 `out/candidates.csv`（Keepa 検証済みの行だけが入っている）
出力: A_初回仕入れ候補_卸レーン.csv / A_サプライヤー別サマリ.csv

なぜ別スクリプトにしたか:
    スキャン本体（netsea_scan.py）は「利益が出るか」を計算する道具で、
    予算の制約は**その日の社長の都合**です。混ぜるとスキャンを回すたびに
    予算前提が固まってしまう。予算が変わったら、こちらの定数だけ直せば済む形にします。

━━ 社長の決定（2026-09-04 / T-20260904-004）━━━━━━━━━━━━━━━━━━━
    総額 5万円以下 / 目的は「1周回すこと」/ 利益率5%でも可・赤字は不可 / 5〜10 SKU

━━ この5万円で一番効くのは「送料」です ━━━━━━━━━━━━━━━━━━━━━
    卸は「◯円以上で送料無料」が標準です。5社に分けて買えば送料が5回掛かり、
    1回1,000円なら5,000円＝予算の1割が消えます。利益率5%の商材でそれは致命傷です。
    だから**サプライヤー別サマリのほうが商品リストより重要**です。

⛔ 発注・購入・会員登録は一切しません（CLAUDE.md §4.1）。読んで数えるだけです。
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCAN_DIR = REPO / "workspace" / "output" / "deliverables" / "T-20260831-006"
LEGACY_CODE = REPO / "workspace" / "output" / "deliverables" / "T-20260521-005" / "code"
for p in (str(LEGACY_CODE),):
    if p not in sys.path:
        sys.path.insert(0, p)

CANDIDATES_CSV = SCAN_DIR / "out" / "candidates.csv"
TARIFF_CACHE = HERE / "_tariffs_cache.json"

# =============================================================================
# 予算の制約（社長決定 2026-09-04）。**触るのはここだけ**で足りるようにする。
# =============================================================================
TOTAL_BUDGET_YEN = 50_000        # 初回仕入れの総額上限
SKU_SPEND_MIN_YEN = 5_000        # 1SKU あたりの仕入れ額の下限（＝薄すぎて1周にならない帯を外す）
SKU_SPEND_MAX_YEN = 10_000       # 1SKU あたりの仕入れ額の上限（＝1点に寄せない）
MIN_MARGIN_RATE_PCT = 5.0        # 利益率の下限（社長決定。赤字は当然不可）
EXCLUDE_FBA_SIZES = {"大型"}      # 5万円の枠に大型は見合わない（送料・保管料）

# 売れるたびに1点あたり必ず乗る固定費（売価に関係しない）。経理ハジメ実測 2026-09-04。
#   小口プラン基本成約料 110円 ＋ 納品代行 12円 ＋ FBA納品送料 37.5円 ＝ 159.5円
# ⚠️ **これが低単価品を食い潰します。** 仕入単価500円の商品なら、単価の32%が
#    売れた瞬間に消えます。だから予算5万円は「安いものを多数」ではなく
#    「単価の高いものを少数」に寄せるべき、というのが経理の逆算結果です。
#    （販売手数料の消費税は売価連動なのでここには入れず、利益計算側で乗せています）
FIXED_COST_PER_UNIT_YEN = 110 + 12 + 37.5

# 仕入単価に対して固定費が占める割合。これを超えたら「低単価すぎる」と警告する。
# 除外はしません（判定材料として残す・社長が線を引けるように）。
FIXED_COST_RATIO_WARN = 0.20

# 消費税。NETSEA の set[].price は税抜、set_price は税込（公式スキーマ）。
TAX = 1.10

# 送料の目安を出す届け先。**社長の住所は使いません**（このリポは PUBLIC）。
# 実額は発注時に届け先で確定します。ここは「桁を見るための代表値」です。
TARIFF_REFERENCE_PREFECTURE = "東京都"


def _int(value, default=0) -> int:
    try:
        s = str(value).strip().replace(",", "")
        return int(float(s)) if s else default
    except (TypeError, ValueError):
        return default


def _float(value, default=None):
    try:
        s = str(value).strip().replace(",", "")
        return float(s) if s else default
    except (TypeError, ValueError):
        return default


# =============================================================================
# 1SKU あたりいくら積むか
# =============================================================================
def plan_purchase(row: dict) -> dict:
    """1候補について「いくらで何個買うことになるか」を出す。

    ⚠️ 単位が2つあるので混ぜないこと。
        NETSEA単位 … 卸で1個と数えるもの。最小発注数(set_num)はこの単位
        Amazon単位 … 1つの ASIN として売るもの。まとめ売り ASIN なら NETSEA 単位の入数倍

    「最小発注額(税込)」列は **その商品を1口買うときの金額**（NETSEA set_price）です。
    **サプライヤーの最低仕入れ金額ではありません。** 後者は Buyer API に存在しません。
    """
    lot_qty = max(_int(row.get("最小発注数"), 1), 1)          # NETSEA単位／1口
    lot_cost = _int(row.get("最小発注額(税込)"))               # 1口ぶんの税込額
    unit_ex_tax = _int(row.get("NETSEA卸値(税抜)"))
    if lot_cost <= 0:
        # set_price が空の商品は珍しくない。卸値×数量から組み立て直す（出所を残す）。
        lot_cost = round(unit_ex_tax * TAX * lot_qty)
        cost_source = "卸値(税抜)×最小発注数×1.10（最小発注額が空欄のため算出）"
    else:
        cost_source = "NETSEA 最小発注額(税込) の実額"

    pack = max(_int(row.get("出品の入数"), 1), 1)              # Amazon1出品＝NETSEA何個ぶん

    if lot_cost <= 0:
        return {"error": "仕入れ額を計算できません（卸値も最小発注額も空欄）"}
    if lot_cost > SKU_SPEND_MAX_YEN:
        return {"error": f"1口 {lot_cost:,}円 が1SKUの上限 {SKU_SPEND_MAX_YEN:,}円 を超えます",
                "lot_cost": lot_cost}

    # 予算レンジに収まる最大の口数。下限に届かないなら、届く最小の口数を採る。
    lots = max(SKU_SPEND_MAX_YEN // lot_cost, 1)
    spend = lot_cost * lots
    if spend < SKU_SPEND_MIN_YEN:
        return {"error": f"上限まで積んでも {spend:,}円 で下限 {SKU_SPEND_MIN_YEN:,}円 に届きません",
                "lot_cost": lot_cost}

    qty_netsea = lot_qty * lots
    qty_amazon = qty_netsea // pack
    if qty_amazon < 1:
        return {"error": f"入数{pack}に対し仕入れ{qty_netsea}個では1出品ぶんに足りません",
                "lot_cost": lot_cost}

    return {
        "lot_qty": lot_qty, "lot_cost": lot_cost, "cost_source": cost_source,
        "lots": lots, "spend": spend,
        "qty_netsea": qty_netsea, "qty_amazon": qty_amazon, "pack": pack,
    }


def velocity_cap(row: dict, plan: dict) -> tuple:
    """回転から見た「1ヶ月で捌ける見込み数」。**買いすぎの歯止め**。

    利益率だけで並べると、利益は出るが30日で1個も売れていない商品が上位に来ます
    （memory: feedback_profit_without_velocity_is_a_lie）。在庫は現金です。

    ⚠️ 分母に使う「出品者数」は既定では Keepa の COUNT_NEW ＝**新品オファー本数**で、
       出品者数ではありません（1社が FBA/FBM に出すだけで2）。
       `--verify-sellers` を通した行だけが実セラー数です。CSV に出所列をそのまま運びます。
    """
    drops = _int(row.get("月間販売数(30日ランク下落数)"), -1)
    if drops < 0:
        return None, "販売実績が取れず（Keepa にランク下落の記録なし）"
    sellers = _int(row.get("出品者数"), 0)
    share = drops / (sellers + 1) if drops else 0
    cap = max(int(share), 0)
    note = (f"30日ドロップ{drops} ÷ (出品者数{sellers}+1) = 約{share:.1f}個/月"
            f"（出所: {row.get('出品者数の出所', '')}）")
    return cap, note


# =============================================================================
# 送料無料ライン（NETSEA /tariffs の実データ）
# =============================================================================
def fetch_tariffs(supplier_ids: list, use_cache: bool = True) -> dict:
    """サプライヤーの送料設定を取る。取れなければ**空のまま返す**（推測で埋めない）。"""
    cache = {}
    if use_cache and TARIFF_CACHE.exists():
        try:
            cache = {int(k): v for k, v in json.loads(
                TARIFF_CACHE.read_text(encoding="utf-8")).items()}
        except (ValueError, OSError):
            cache = {}
    missing = [s for s in supplier_ids if s and int(s) not in cache]
    if missing:
        # シークレットは .env / ~/.config から読む（Git には置かない）。
        # 読み込みはスキャン側と同じ1本の実装を使い回す（2箇所に書かない）。
        sys.path.insert(0, str(SCAN_DIR))
        from pipeline import keepa_verify  # noqa: E402
        keepa_verify.load_env()

        from adapters.netsea import (  # noqa: E402
            PURPOSE_PROCUREMENT, NetseaClient, assert_procurement_use,
        )
        assert_procurement_use(PURPOSE_PROCUREMENT)
        client = NetseaClient()
        if client.is_live:
            cache.update(client.list_tariffs(missing))
            TARIFF_CACHE.write_text(
                json.dumps({str(k): v for k, v in cache.items()}, ensure_ascii=False),
                encoding="utf-8")
        else:
            print(f"⚠ NETSEA に接続できません（{client._why_not_live()}）。送料は空欄になります")
    return cache


def read_tariff(tariff: dict, prefecture: str = TARIFF_REFERENCE_PREFECTURE) -> dict:
    """送料設定 → 人が読める形。**「段階金額＝送料無料ライン」ではありません。**

    公式スキーマ（2026-09-04 実取得）:
        gradual_flag=false          … 段階なし。常に price1
        購入金額 <  gradual_border_price … price1
        購入金額 >= gradual_border_price … price2
    したがって **price2 が 0 のときだけ「その金額以上で送料無料」**です。
    price2 が正なら「その金額以上で送料が安くなる」であって無料ではありません。
    """
    out = {"送料無料ライン": "", "送料の段階": "", "送料(下段)": "", "送料(上段)": "",
           "送料の出所": ""}
    if not tariff:
        out["送料の出所"] = "NETSEA /tariffs に設定なし（未取得ではなく、この社に設定が無い）"
        return out
    prices = tariff.get("prices") or []
    hit = next((p for p in prices if p.get("prefecture") == prefecture), None)
    if hit is None:
        out["送料の出所"] = f"{prefecture} の料金設定なし（対象都道府県外）"
        return out
    p1, p2 = hit.get("price1"), hit.get("price2")
    border = tariff.get("gradual_border_price")
    out["送料(下段)"] = p1 if p1 is not None else ""
    out["送料の出所"] = f"NETSEA /tariffs 実データ・届け先{prefecture}の値"
    if not tariff.get("gradual_flag") or border is None:
        out["送料の段階"] = "段階設定なし（金額を積んでも送料は変わりません）"
        return out
    out["送料(上段)"] = p2 if p2 is not None else ""
    out["送料の段階"] = f"{int(border):,}円以上で送料 {p1}円 → {p2}円"
    if p2 == 0:
        out["送料無料ライン"] = int(border)
    return out


def order_shipping(tariff: dict, order_total_yen: int,
                   prefecture: str = TARIFF_REFERENCE_PREFECTURE):
    """この注文額のとき、実際にいくら送料が掛かるか。取れなければ **None**（空欄）。

    段階設定があるなら、注文額が切り替え金額**以上**なら price2、未満なら price1。
    推測はしません。設定が取れなければ None を返し、呼び出し側で空欄にします。
    """
    if not tariff:
        return None
    hit = next((p for p in (tariff.get("prices") or [])
                if p.get("prefecture") == prefecture), None)
    if hit is None:
        return None
    p1, p2 = hit.get("price1"), hit.get("price2")
    border = tariff.get("gradual_border_price")
    if not tariff.get("gradual_flag") or border is None or p2 is None:
        return p1
    return p2 if order_total_yen >= int(border) else p1


# =============================================================================
# 本体
# =============================================================================
KEEP_COLUMNS = [
    "商品名", "Amazon商品名", "JAN", "ASIN", "サプライヤー名", "業態",
    "NETSEA卸値(税抜)", "NETSEA卸値(税込)", "Amazon価格",
    "純利益", "利益率%", "利益率区分", "ROI%",
    "月間販売数(30日ランク下落数)", "出品者数", "出品者数の出所", "Amazon本体の有無",
    "FBAサイズ", "出品の入数", "入数の根拠", "最小発注数", "最小発注額(税込)",
    "ネット販売可否", "総合判定", "法令要確認", "発注前に必ず確認",
    "Amazonページ", "Keepaリンク", "NETSEA商品ページ",
]

OUT_COLUMNS = KEEP_COLUMNS + [
    "★仕入れ額(税込)", "★仕入れ口数", "★仕入れ個数(NETSEA単位)", "★出品可能数(Amazon単位)",
    "★仕入れ額の出所", "★見込み粗利(この仕入れ額ぶん)",
    "★仕入れ単価(税込)", "★1点あたり固定費", "★固定費が仕入れ単価に占める割合%", "★単価帯の警告",
    "★1ヶ月で捌ける見込み(個)", "★回転の根拠", "★予算内で買える理由",
]


def load_rows(path: Path) -> list:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def filter_rows(rows: list) -> tuple:
    """予算5万円の制約を通す。落とした理由を必ず数える（歩留まりを説明できるように）。"""
    kept, reasons = [], {}

    def drop(why):
        reasons[why] = reasons.get(why, 0) + 1

    for row in rows:
        margin = _float(row.get("利益率%"))
        if margin is None:
            drop("利益率が計算できていない（Amazon未出品・価格なし等）")
            continue
        if margin < 0:
            drop("赤字")
            continue
        if margin < MIN_MARGIN_RATE_PCT:
            drop(f"利益率が {MIN_MARGIN_RATE_PCT}% 未満")
            continue
        if row.get("要確認理由"):
            # 入数の読み落とし疑いなど。**「儲かる」と言い切れない行を候補に混ぜない。**
            drop("要確認（入数など未確定のため利益を保証できない）")
            continue
        size = str(row.get("FBAサイズ") or "")
        if any(size.startswith(bad) for bad in EXCLUDE_FBA_SIZES):
            drop("FBA大型（5万円の枠に見合わない）")
            continue
        if str(row.get("ネット販売可否") or "") != "可":
            drop("ネット販売不可（deal_net_shop_flag≠Y）")
            continue

        plan = plan_purchase(row)
        if "error" in plan:
            drop(f"仕入れ額が1SKUのレンジ外: {plan['error'].split('（')[0][:40]}")
            continue

        cap, cap_note = velocity_cap(row, plan)
        profit_per_unit = _float(row.get("純利益"), 0) or 0

        # 1点あたり固定費が仕入単価をどれだけ食うか。**低単価品の足切りではなく警告**。
        unit_incl = plan["spend"] / max(plan["qty_amazon"], 1)
        ratio = FIXED_COST_PER_UNIT_YEN / unit_incl if unit_incl else 0
        if ratio >= FIXED_COST_RATIO_WARN:
            warn = (f"低単価。1点あたり固定費{FIXED_COST_PER_UNIT_YEN:.0f}円が"
                    f"仕入単価{unit_incl:.0f}円の{ratio*100:.0f}%を食います"
                    f"（経理ハジメ: 予算5万円は単価の高いものを少数に寄せるべき）")
        else:
            warn = ""

        out = {k: row.get(k, "") for k in KEEP_COLUMNS}
        out.update({
            "★仕入れ単価(税込)": round(unit_incl),
            "★1点あたり固定費": round(FIXED_COST_PER_UNIT_YEN),
            "★固定費が仕入れ単価に占める割合%": round(ratio * 100, 1),
            "★単価帯の警告": warn,
            "★仕入れ額(税込)": plan["spend"],
            "★仕入れ口数": plan["lots"],
            "★仕入れ個数(NETSEA単位)": plan["qty_netsea"],
            "★出品可能数(Amazon単位)": plan["qty_amazon"],
            "★仕入れ額の出所": plan["cost_source"],
            "★見込み粗利(この仕入れ額ぶん)": round(profit_per_unit * plan["qty_amazon"]),
            "★1ヶ月で捌ける見込み(個)": "" if cap is None else cap,
            "★回転の根拠": cap_note,
            "★予算内で買える理由": (
                f"1口{plan['lot_cost']:,}円 × {plan['lots']}口 = {plan['spend']:,}円"
                f"（総額{TOTAL_BUDGET_YEN:,}円のうち{plan['spend']/TOTAL_BUDGET_YEN*100:.0f}%）"
            ),
        })
        kept.append(out)

    # 粗利の降順。ただし**低単価警告のある行は下げる**（経理ハジメ 2026-09-04）。
    # 1点160円の固定費に対して単価が薄い組み合わせは、少し数字がぶれるだけで赤字に落ちます。
    kept.sort(key=lambda r: (
        1 if r.get("★単価帯の警告") else 0,
        -(_float(r.get("★見込み粗利(この仕入れ額ぶん)"), 0) or 0),
    ))
    return kept, reasons


def supplier_summary(kept: list, tariffs: dict, supplier_ids: dict) -> list:
    """**この成果物で一番大事な表。** 送料を1回で済ませられる相手を探すためのもの。"""
    agg = {}
    for row in kept:
        name = row["サプライヤー名"]
        s = agg.setdefault(name, {
            "サプライヤー名": name, "supplier_id": supplier_ids.get(name, ""),
            "業態": row.get("業態", ""), "候補SKU数": 0,
            "合計仕入れ額(税込)": 0, "合計見込み粗利": 0,
            "最小の仕入れ額": None, "最安SKUのJAN": "",
        })
        s["候補SKU数"] += 1
        s["合計仕入れ額(税込)"] += _int(row["★仕入れ額(税込)"])
        s["合計見込み粗利"] += _int(row["★見込み粗利(この仕入れ額ぶん)"])
        spend = _int(row["★仕入れ額(税込)"])
        if s["最小の仕入れ額"] is None or spend < s["最小の仕入れ額"]:
            s["最小の仕入れ額"] = spend
            s["最安SKUのJAN"] = row["JAN"]

    out = []
    for s in agg.values():
        sid = s["supplier_id"]
        t = read_tariff(tariffs.get(int(sid)) if sid else None)
        s.update(t)

        # 「この社だけで 5〜10SKU を組めるか」＝送料を1回に集約できるか。
        n = s["候補SKU数"]
        if n >= 5:
            s["集約可能性"] = f"◎ この社だけで{n}SKU組めます（送料1回で完結）"
        elif n >= 2:
            s["集約可能性"] = f"△ {n}SKU。単独では5SKUに届かず、もう1社と組む必要があります"
        else:
            s["集約可能性"] = "× 1SKUのみ。この社のためだけに送料を払うことになります"

        # ── NETSEA送料を「注文単位」で実額計上する ─────────────────────
        # ⚠️ **利益計算に入っていなかった最大の穴です。**
        #    `/items` の ship_fee に値があるのは 257,067件中951件（0.37%）だけで、
        #    99.6%の商品は「送料ゼロ」で利益が出ていました（経理ハジメ実測 2026-09-04）。
        #    送料は**商品ではなく注文**に掛かるので、按分できるのはここだけです。
        total = s["合計仕入れ額(税込)"]
        ship = order_shipping(tariffs.get(int(sid)) if sid else None, total)
        s["この注文の送料(実費)"] = "" if ship is None else ship
        s["送料込みの見込み粗利"] = (
            "" if ship is None else s["合計見込み粗利"] - ship)
        # NETSEA は初回注文送料無料特集を開催中（〜2026/10/1 12:00・コメント欄に
        # 「送料無料」入力が必須）。**発注は §4.1 かつアカウント停止中なので実行しません。**
        # 社長判断のためのシナリオとしてだけ持ちます。
        s["初回送料無料を使えた場合の粗利"] = s["合計見込み粗利"]

        # 送料無料ラインに届くか。**届かない場合、いくら足りないかまで出す。**
        line = s["送料無料ライン"]
        if line == "":
            s["送料無料ラインに届くか"] = "（判定できません）" + (
                "この社は /tariffs に段階設定が無く、金額を積んでも送料は変わりません"
                if "段階設定なし" in str(s["送料の段階"])
                else "送料設定を取得できていません"
            )
        else:
            if total >= line:
                s["送料無料ラインに届くか"] = (
                    f"○ 届きます（{total:,}円 ≧ {line:,}円）")
            else:
                s["送料無料ラインに届くか"] = (
                    f"× あと {line - total:,}円 必要（現在 {total:,}円 / ライン {line:,}円）")
        out.append(s)

    # 集約できる社を上に。次に粗利。
    out.sort(key=lambda r: (-r["候補SKU数"], -r["合計見込み粗利"]))
    return out


SUPPLIER_COLUMNS = [
    "サプライヤー名", "supplier_id", "業態", "候補SKU数", "集約可能性",
    "合計仕入れ額(税込)", "合計見込み粗利",
    "この注文の送料(実費)", "送料込みの見込み粗利", "初回送料無料を使えた場合の粗利",
    "送料無料ライン", "送料無料ラインに届くか", "送料の段階", "送料(下段)", "送料(上段)",
    "送料の出所", "最小の仕入れ額", "最安SKUのJAN",
]


def write_csv(path: Path, columns: list, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", default=str(CANDIDATES_CSV))
    ap.add_argument("--outdir", default=str(HERE))
    ap.add_argument("--no-tariffs", action="store_true",
                    help="NETSEA /tariffs を叩かない（送料列は空欄になります）")
    args = ap.parse_args()

    rows = load_rows(Path(args.candidates))
    print(f"入力: {len(rows)}件（Keepa 検証済みの行のみ）")

    kept, reasons = filter_rows(rows)
    print(f"予算{TOTAL_BUDGET_YEN:,}円の制約を通過: {len(kept)}件")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    落とした: {why} … {n}件")

    # サプライヤーIDは商品ページURL（https://www.netsea.jp/shop/<id>/...）から拾う。
    supplier_ids = {}
    for row in rows:
        url = str(row.get("NETSEA商品ページ") or "")
        name = row.get("サプライヤー名")
        if name and name not in supplier_ids and "/shop/" in url:
            tail = url.split("/shop/", 1)[1].split("/")[0]
            if tail.isdigit():
                supplier_ids[name] = int(tail)

    ids = sorted({supplier_ids[r["サプライヤー名"]] for r in kept
                  if r["サプライヤー名"] in supplier_ids})
    tariffs = {} if args.no_tariffs else fetch_tariffs(ids)
    print(f"送料設定を取得: {len(tariffs)} / {len(ids)}社")

    summary = supplier_summary(kept, tariffs, supplier_ids)

    outdir = Path(args.outdir)
    write_csv(outdir / "A_初回仕入れ候補_卸レーン.csv", OUT_COLUMNS, kept)
    write_csv(outdir / "A_サプライヤー別サマリ.csv", SUPPLIER_COLUMNS, summary)
    stats = {
        "input_rows": len(rows), "kept": len(kept), "drop_reasons": reasons,
        "suppliers_with_candidate": len(summary),
        "suppliers_with_5plus_sku": sum(1 for s in summary if s["候補SKU数"] >= 5),
        "tariffs_fetched": len(tariffs), "tariff_targets": len(ids),
        "budget": {"total": TOTAL_BUDGET_YEN, "sku_min": SKU_SPEND_MIN_YEN,
                   "sku_max": SKU_SPEND_MAX_YEN, "min_margin_pct": MIN_MARGIN_RATE_PCT},
    }
    (outdir / "A_filter_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {outdir / 'A_初回仕入れ候補_卸レーン.csv'}")
    print(f"→ {outdir / 'A_サプライヤー別サマリ.csv'}")


if __name__ == "__main__":
    main()
