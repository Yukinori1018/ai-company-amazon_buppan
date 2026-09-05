#!/usr/bin/env python3
"""初回仕入れ（5〜10SKU・総額5万円）の**発注セット**を組む — T-20260904-004 / A-2 本番適用。

入力:
    ../T-20260831-006/out/candidates.csv     … Keepa 検証済み 26,942件（100%完走・2026-09-06 04:41）
    ../T-20260831-006/out/keepa_facts.jsonl  … ブランド・カテゴリ・寸法（JAN で結合）
    ../T-20260831-006/out/netsea_items.jsonl … 商品説明（中古表記の確認に使う。911MB を1回だけ舐める）
    ./C1_cost_assumptions.json               … 経理ハジメ実測版のコスト前提
    NETSEA GET /tariffs                      … 送料無料ラインの一次情報

出力:
    D_初回仕入れ_発注候補セット.csv   … 社長が見る本命。**発注単位**で並べる
    D_サプライヤー別サマリ.csv        … 送料を1回で済ませられる相手を探す表
    D_絞り込みログ.md                 … 26,942件がどう減ったか。落とした理由の内訳つき
    D_filter_stats.json               … 上記の機械可読版

━━ 絞り込みの順番（社長指示 2026-09-06）━━━━━━━━━━━━━━━━━━━━━
    条件1 買ってはいけないリスト（risk_rules.py）… ここで落ちたら利益が出ていても除外
    条件2 予算5万円（単価帯・利益率下限・FBAサイズ）
    条件3 サプライヤー集約（送料無料ラインに届く組み合わせ）

⛔ 発注・購入・会員登録は一切しません（CLAUDE.md §4.1）。読んで数えるだけです。
   Amazon アカウントは3か国とも停止中で、そもそも発注してはいけない状態です。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import budget_filter as BF          # noqa: E402  予算の定数と送料の読み方は1本に保つ
import risk_rules as RR             # noqa: E402

SCAN_DIR = HERE.parent / "T-20260831-006"
CANDIDATES_CSV = SCAN_DIR / "out" / "candidates.csv"
KEEPA_FACTS = SCAN_DIR / "out" / "keepa_facts.jsonl"
NETSEA_ITEMS = SCAN_DIR / "out" / "netsea_items.jsonl"
DESC_CACHE = HERE / "_netsea_desc_cache.json"

# 発注セットの形（社長決定 2026-09-04）
SET_SKU_MIN = 5
SET_SKU_MAX = 10
TOTAL_BUDGET = BF.TOTAL_BUDGET_YEN          # 50,000円
SKU_MIN = BF.SKU_SPEND_MIN_YEN              # 5,000円
SKU_MAX = BF.SKU_SPEND_MAX_YEN              # 10,000円


def _int(v, default=0):
    return BF._int(v, default)


def _float(v, default=None):
    return BF._float(v, default)


def uid_from_url(url: str) -> str:
    """NETSEA 商品ページ URL → netsea_items.jsonl の _uid。

    https://www.netsea.jp/shop/<supplier_id>/<product_id>  →  "<supplier_id>-<product_id>"
    """
    parts = [p for p in str(url or "").split("/") if p]
    if len(parts) < 2:
        return ""
    return f"{parts[-2]}-{parts[-1]}"


# =============================================================================
# 読み込み
# =============================================================================
def load_keepa_facts() -> dict:
    """JAN → Keepa の事実。**found=false の行は入れない**（空を事実として扱わない）。"""
    facts = {}
    with open(KEEPA_FACTS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("found"):
                facts[d["jan"]] = d
    return facts


def load_descriptions(uids: set, use_cache: bool = True) -> dict:
    """必要な商品だけの `description`。911MB を1回だけ順に読む。

    なぜ description が要るか:
        中古表記の確認です。商品名だけでは「アウトレット」「訳あり」が説明文にしか
        書かれていない商品を見逃します。NETSEA には中古品が実在します
        （draft #4 反転条件③ / 2026-08-31 実測212件）。
    """
    if use_cache and DESC_CACHE.exists():
        cached = json.loads(DESC_CACHE.read_text(encoding="utf-8"))
        if uids <= set(cached):
            return cached
    out = {}
    with open(NETSEA_ITEMS, encoding="utf-8") as f:
        for line in f:
            # json.loads は重い。要る uid の文字列が行に無ければ即捨てる。
            if '"_uid"' not in line:
                continue
            d = json.loads(line)
            uid = d.get("_uid")
            if uid in uids:
                out[uid] = {
                    "description": d.get("description") or "",
                    "spec_size": d.get("spec_size") or "",
                    "shop_name": d.get("shop_name") or "",
                }
    DESC_CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# =============================================================================
# 条件2: 予算5万円
# =============================================================================
def plan_min_spend(row: dict) -> dict:
    """**下限 5,000円に届く最小の口数**で買う計画。

    budget_filter.plan_purchase は「上限10,000円まで積む」計画を出します。
    発注セットを組むときは逆で、1SKU に使う額を絞ったほうが SKU 数を増やせます。
    5〜10SKU を組むのが今回の目的なので、こちらを使います。
    """
    lot_qty = max(_int(row.get("最小発注数"), 1), 1)
    lot_cost = _int(row.get("最小発注額(税込)"))
    unit_ex = _int(row.get("NETSEA卸値(税抜)"))
    if lot_cost <= 0:
        lot_cost = round(unit_ex * BF.TAX * lot_qty)
        source = "卸値(税抜)×最小発注数×1.10（最小発注額が空欄のため算出）"
    else:
        source = "NETSEA 最小発注額(税込) の実額"
    if lot_cost <= 0:
        return {"error": "仕入れ額を計算できない（卸値も最小発注額も空欄）"}
    if lot_cost > SKU_MAX:
        return {"error": f"1口 {lot_cost:,}円 が1SKU上限 {SKU_MAX:,}円 を超える"}

    lots = 1
    while lot_cost * lots < SKU_MIN:
        lots += 1
    spend = lot_cost * lots
    if spend > SKU_MAX:
        return {"error": f"下限 {SKU_MIN:,}円 に届けると {spend:,}円 で上限 {SKU_MAX:,}円 を超える"}

    pack = max(_int(row.get("出品の入数"), 1), 1)
    qty_netsea = lot_qty * lots
    return {
        "lot_cost": lot_cost, "lots": lots, "spend": spend,
        "qty_netsea": qty_netsea,
        "qty_amazon": max(qty_netsea // pack, 1),
        "cost_source": source,
    }


# =============================================================================
# 本体: 3条件を順に当てる
# =============================================================================
STAGES = [
    "S0 母数（Keepa 検証済み）",
    "S1 条件1 買ってはいけないリスト",
    "S2 条件2 予算5万円",
    "S3 中古の実データ確認（商品説明）",
    "S4 4群適合（初回に向くカテゴリ）",
    "S5 回転（30日で1個以上売れている）",
]

# 30日で最低これだけ売れていること。**利益だけで並べてはいけない**という社内の学び
# （memory: feedback_profit_without_velocity_is_a_lie）を、線として引いた値です。
# 今回の目的は「仕入れ→出品→FBA納品→販売→入金の1周を完走すること」なので、
# 売れていない商品を買うと目的そのものが達成できません。
#   1 = 30日で1個でも売れた実績がある（最低ライン）
#   3 = run_stats.json が「回転もある」と数えている基準（670件）
MIN_DROPS30 = 1


def run_filters(rows, facts, verbose=True):
    """26,942件を段階ごとに落とす。**落ちた理由を必ず数える。**"""
    stats = {
        "S0_母数": len(rows),
        "S1_除外内訳_最初に触れた項目": {},
        "S1_発火件数_ルール別_重複あり": {},
        "S1_残": 0,
        "S2_除外内訳": {},
        "S2_残": 0,
        "S3_除外内訳": {},
        "S3_残": 0,
        "S4_除外内訳": {},
        "S4_残": 0,
        "S5_除外内訳": {},
        "S5_残": 0,
    }

    # ── S1 条件1: 買ってはいけないリスト ────────────────────────────────
    # この時点では商品説明を持っていないので description_available=False。
    # 「中古かどうか機械判定できない」を「要目視」として持ち回り、S3 で確定させます。
    s1 = []
    for r in rows:
        d = facts.get(r["JAN"]) or {}
        v = RR.judge(
            netsea_name=r.get("商品名", ""),
            amazon_title=r.get("Amazon商品名", ""),
            brand=d.get("brand", ""),
            category_names=d.get("category_names"),
            description="",
            supplier_name=r.get("サプライヤー名", ""),
            description_available=False,
            package_mm=d.get("package_mm"),
            package_g=d.get("package_g"),
            seller_count=_int(r.get("出品者数"), None) if r.get("出品者数") else None,
        )
        for reason in v.reasons:
            key = reason.split(":")[0]
            stats["S1_発火件数_ルール別_重複あり"][key] = \
                stats["S1_発火件数_ルール別_重複あり"].get(key, 0) + 1
        if v.blocked:
            stats["S1_除外内訳_最初に触れた項目"][v.rule_id] = \
                stats["S1_除外内訳_最初に触れた項目"].get(v.rule_id, 0) + 1
            continue
        s1.append((r, v, d))
    stats["S1_残"] = len(s1)

    # ── S2 条件2: 予算5万円 ─────────────────────────────────────────
    def drop2(why):
        stats["S2_除外内訳"][why] = stats["S2_除外内訳"].get(why, 0) + 1

    s2 = []
    for r, v, d in s1:
        margin = _float(r.get("利益率%"))
        if margin is None:
            drop2("利益率が計算できていない（Amazon未出品・価格が取れない）")
            continue
        if margin < 0:
            drop2("赤字")
            continue
        if margin < BF.MIN_MARGIN_RATE_PCT:
            drop2(f"利益率が {BF.MIN_MARGIN_RATE_PCT}% 未満")
            continue
        if r.get("要確認理由"):
            drop2("要確認（入数など未確定で利益を保証できない）")
            continue
        size = str(r.get("FBAサイズ") or "")
        if any(size.startswith(bad) for bad in BF.EXCLUDE_FBA_SIZES):
            drop2("FBA大型（5万円の枠に見合わない）")
            continue
        if size.startswith("不明"):
            drop2("FBAサイズ不明（寸法・重量が取れず小型/標準と言い切れない）")
            continue
        if str(r.get("ネット販売可否") or "") != "可":
            drop2("ネット販売不可（deal_net_shop_flag≠Y）")
            continue
        plan = plan_min_spend(r)
        if "error" in plan:
            # 個別の金額まで理由に含めると内訳が1件ずつに散るので、原因の型でまとめる
            kind = "1口が上限10,000円を超える" if "上限" in plan["error"] else plan["error"][:40]
            drop2(f"1SKU単価レンジ 5,000〜10,000円 に収まらない（{kind}）")
            continue
        s2.append((r, v, d, plan))
    stats["S2_残"] = len(s2)

    return s1, s2, stats


def apply_used_check(s2, descs, stats):
    """S3: 商品説明を当てて中古表記を確定させる。**「たぶん新品」で通さない。**"""
    out = []
    for r, v, d, plan in s2:
        uid = uid_from_url(r.get("NETSEA商品ページ", ""))
        info = descs.get(uid) or {}
        desc = info.get("description", "")
        has_desc = bool(desc.strip())
        status, hit = RR.check_used(
            r.get("商品名", ""), r.get("Amazon商品名", ""), desc,
            description_available=has_desc,
        )
        if status == "該当":
            key = f"中古系表記「{hit}」を商品説明で検出"
            stats["S3_除外内訳"][key] = stats["S3_除外内訳"].get(key, 0) + 1
            continue
        v.used_status = status if status == "該当なし" else "要目視"
        v.used_hit = ""
        # S1 は商品説明を持たずに判定していたので「機械判定できない」注記が付いています。
        # ここで説明を当てて確定させたので、古い注記は必ず捨てる（矛盾した2文を残さない）。
        v.notes = [n for n in v.notes if "機械判定できない" not in n]
        if status == "要目視":
            v.notes.append("NETSEA の商品説明が空欄。中古かどうかは発注前に商品ページを目視すること")
        out.append((r, v, d, plan, desc))
    stats["S3_残"] = len(out)
    return out


def apply_fit_group(s3, stats, require_group=True):
    """S4: 初回に向く4群に入るか（draft 2-B）。"""
    out = []
    for r, v, d, plan, desc in s3:
        if require_group and not v.fit_group:
            root = (d.get("category_names") or ["(カテゴリ不明)"])[0]
            key = f"初回に向く4群の外（ルートカテゴリ: {root}）"
            stats["S4_除外内訳"][key] = stats["S4_除外内訳"].get(key, 0) + 1
            continue
        out.append((r, v, d, plan, desc))
    stats["S4_残"] = len(out)
    return out


def apply_velocity(rows4, stats, min_drops=MIN_DROPS30):
    """S5: 30日で売れている実績があるか。**利益だけで選ばない**ための線。

    ここを入れる前の出力では、A2 セットの9SKU中8SKUが「30日で0個」でした。
    利益率は出ているのに1個も動いていない商品で、1周は完走しません。
    """
    out = []
    for item in rows4:
        drops = _int(item[0].get("月間販売数(30日ランク下落数)"), -1)
        if drops < min_drops:
            key = (f"30日の販売実績が {min_drops}個 未満"
                   f"（{'実績なし' if drops <= 0 else str(drops) + '個'}）")
            stats["S5_除外内訳"][key] = stats["S5_除外内訳"].get(key, 0) + 1
            continue
        out.append(item)
    stats["S5_残"] = len(out)
    return out


# =============================================================================
# 条件3: サプライヤー集約と発注セット
# =============================================================================
def score(row, plan) -> float:
    """発注セットに入れる順番。**回転を最優先**にする。

    利益率だけで並べると「利益は出るが30日で1個も売れていない商品」が上位に来ます
    （memory: feedback_profit_without_velocity_is_a_lie）。在庫は現金です。
    今回の目的は「1周回すこと」なので、売れないものを買うと目的そのものが達成できません。
    """
    drops = _int(row.get("月間販売数(30日ランク下落数)"), 0)
    profit = _float(row.get("純利益"), 0) or 0
    sellers = max(_int(row.get("出品者数"), 1), 1)
    # 30日で何個売れているか ÷ 競合、× 1個あたり利益
    return (drops / (sellers + 1)) * max(profit, 0)


def build_supplier_sets(rows4, tariffs, supplier_ids):
    """サプライヤーごとに「このセットを買えばよい」を1つ作る。"""
    by_supplier = {}
    for item in rows4:
        by_supplier.setdefault(item[0]["サプライヤー名"], []).append(item)

    sets = []
    for name, items in by_supplier.items():
        items = sorted(items, key=lambda it: -score(it[0], it[3]))
        # 同一 ASIN を2口買っても在庫が増えるだけなので、1セットに1 ASIN 1回まで。
        picked, seen, spend = [], set(), 0
        for it in items:
            asin = it[0].get("ASIN")
            if asin in seen:
                continue
            if len(picked) >= SET_SKU_MAX:
                break
            if spend + it[3]["spend"] > TOTAL_BUDGET:
                continue
            picked.append(it)
            seen.add(asin)
            spend += it[3]["spend"]
        if not picked:
            continue

        sid = supplier_ids.get(name)
        tariff = tariffs.get(int(sid)) if sid else None
        read = BF.read_tariff(tariff or {})
        ship = BF.order_shipping(tariff or {}, spend)
        free_line = read.get("送料無料ライン")
        gap = ""
        if isinstance(free_line, int):
            gap = max(free_line - spend, 0)

        sets.append({
            "サプライヤー名": name,
            "supplier_id": sid or "",
            "SKU数": len(picked),
            "合計仕入れ額(税込)": spend,
            "合計見込み粗利": round(sum(
                (_float(it[0].get("純利益"), 0) or 0) * it[3]["qty_amazon"] for it in picked)),
            "この注文額での送料": "" if ship is None else ship,
            "送料無料ライン": free_line if isinstance(free_line, int) else "",
            "送料無料まであと": gap,
            "送料の段階": read.get("送料の段階", ""),
            "送料の出所": read.get("送料の出所", ""),
            "5〜10SKUを組めるか": "組める" if len(picked) >= SET_SKU_MIN else
                                f"組めない（このサプライヤー単独では {len(picked)}SKU）",
            "_items": picked,
        })

    sets.sort(key=lambda s: (-s["SKU数"], -s["合計見込み粗利"]))
    return sets


# =============================================================================
# 出力
# =============================================================================
OUT_COLUMNS = [
    "セットID", "セットの説明",
    "商品名", "ASIN", "JAN", "サプライヤー名",
    "NETSEA卸値(税込)", "Amazon価格", "実費込み純利益", "利益率%",
    "月間販売数(30日ランク下落数)", "出品者数", "出品者数の出所", "Amazon本体の有無",
    "FBAサイズ",
    "★中古品表記の有無", "★リスク判定", "★ブランド判定", "★4群",
    "★仕入れ額(税込)", "★仕入れ口数", "★仕入れ個数(NETSEA単位)", "★出品可能数(Amazon単位)",
    "★仕入れ額の出所", "★このSKUの見込み粗利",
    "発注前に必ず確認",
    "発注先URL", "Amazonページ", "Keepaリンク",
]

SUPPLIER_COLUMNS = [
    "サプライヤー名", "supplier_id", "候補SKU数", "セットに組んだSKU数",
    "合計仕入れ額(税込)", "合計見込み粗利",
    "この注文額での送料", "送料無料ライン", "送料無料まであと", "送料の段階", "送料の出所",
    "5〜10SKUを組めるか", "NETSEA店舗ページ",
]


def set_rows(order_set, set_id, description):
    for r, v, d, plan, desc in order_set["_items"]:
        yield {
            "セットID": set_id,
            "セットの説明": description,
            "商品名": r.get("商品名", ""),
            "ASIN": r.get("ASIN", ""),
            "JAN": r.get("JAN", ""),
            "サプライヤー名": r.get("サプライヤー名", ""),
            "NETSEA卸値(税込)": r.get("NETSEA卸値(税込)", ""),
            "Amazon価格": r.get("Amazon価格", ""),
            "実費込み純利益": r.get("純利益", ""),
            "利益率%": r.get("利益率%", ""),
            "月間販売数(30日ランク下落数)": r.get("月間販売数(30日ランク下落数)", ""),
            "出品者数": r.get("出品者数", ""),
            "出品者数の出所": r.get("出品者数の出所", ""),
            "Amazon本体の有無": r.get("Amazon本体の有無", ""),
            "FBAサイズ": r.get("FBAサイズ", ""),
            "★中古品表記の有無": v.used_status,
            "★リスク判定": v.risk_label,
            "★ブランド判定": v.brand_tier,
            "★4群": v.fit_group,
            "★仕入れ額(税込)": plan["spend"],
            "★仕入れ口数": plan["lots"],
            "★仕入れ個数(NETSEA単位)": plan["qty_netsea"],
            "★出品可能数(Amazon単位)": plan["qty_amazon"],
            "★仕入れ額の出所": plan["cost_source"],
            "★このSKUの見込み粗利": round((_float(r.get("純利益"), 0) or 0) * plan["qty_amazon"]),
            "発注前に必ず確認": "; ".join(v.notes),
            "発注先URL": r.get("NETSEA商品ページ", ""),
            "Amazonページ": r.get("Amazonページ", ""),
            "Keepaリンク": r.get("Keepaリンク", ""),
        }


def write_csv(path: Path, columns, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  → {path.name}（{len(rows)}行）")


def assert_columns_not_all_empty(rows, columns):
    """**宣言した列が全行空なら異常終了。**

    `optout_notice_status` で3度踏んだ型です。列は作ったが値が入っていない CSV を
    「できました」と渡すのが一番たちが悪い。ここで止めます。
    ただし「その列が空であること自体が事実」の列（Amazon本体の有無など）は除きます。
    """
    if not rows:
        return
    must_have = [
        "★中古品表記の有無", "★リスク判定", "★仕入れ額(税込)",
        "実費込み純利益", "利益率%", "ASIN", "JAN", "発注先URL",
    ]
    for col in must_have:
        if all(not str(r.get(col, "")).strip() for r in rows):
            raise SystemExit(f"❌ 列「{col}」が全 {len(rows)} 行で空です。出力を中止します。")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-tariffs", action="store_true", help="NETSEA /tariffs を叩かない（送料は空欄）")
    ap.add_argument("--allow-outside-groups", action="store_true",
                    help="初回に向く4群の外も残す（母数が足りないときの緩和策）")
    ap.add_argument("--min-drops", type=int, default=MIN_DROPS30,
                    help="30日の最低販売数。既定1。run_stats が『回転もある』と数える基準は3")
    args = ap.parse_args()

    print("■ 読み込み")
    rows = BF.load_rows(CANDIDATES_CSV)
    facts = load_keepa_facts()
    print(f"  候補 {len(rows):,}件 / Keepa 事実 {len(facts):,}件")

    print("■ 条件1・条件2")
    s1, s2, stats = run_filters(rows, facts)
    print(f"  S1 買ってはいけないリスト: {stats['S0_母数']:,} → {stats['S1_残']:,}")
    print(f"  S2 予算5万円            : {stats['S1_残']:,} → {stats['S2_残']:,}")

    print("■ S3 中古の実データ確認（商品説明を取りに行きます）")
    uids = {uid_from_url(r.get("NETSEA商品ページ", "")) for r, _, _, _ in s2}
    uids.discard("")
    descs = load_descriptions(uids)
    print(f"  必要 {len(uids):,}件 / 説明を取得 {len(descs):,}件 / "
          f"うち本文あり {sum(1 for v in descs.values() if v['description'].strip()):,}件")
    s3 = apply_used_check(s2, descs, stats)
    print(f"  S3: {stats['S2_残']:,} → {stats['S3_残']:,}")

    print("■ S4 初回に向く4群")
    s4 = apply_fit_group(s3, stats, require_group=not args.allow_outside_groups)
    print(f"  S4: {stats['S3_残']:,} → {stats['S4_残']:,}")

    print(f"■ S5 回転（30日で {args.min_drops}個以上）")
    s4 = apply_velocity(s4, stats, min_drops=args.min_drops)
    print(f"  S5: {stats['S4_残']:,} → {stats['S5_残']:,}")

    print("■ 条件3 サプライヤー集約（送料無料ライン）")
    supplier_ids = {}
    with open(SCAN_DIR / "out" / "suppliers.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            supplier_ids[r["サプライヤー名"]] = r["supplier_id"]
    names = sorted({it[0]["サプライヤー名"] for it in s4})
    sids = [int(supplier_ids[n]) for n in names if supplier_ids.get(n)]
    tariffs = {} if args.no_tariffs else BF.fetch_tariffs(sids)
    print(f"  対象サプライヤー {len(names)}社 / 送料設定を取得 {len(tariffs)}社")

    sets = build_supplier_sets(s4, tariffs, supplier_ids)
    print(f"  発注セット候補 {len(sets)}件")

    # ── 出力 ─────────────────────────────────────────────────────
    out_rows = []
    # A: 1社で完結するセット（送料1回）。SKU数の多い順に上位3社ぶん出す。
    single = [s for s in sets if s["SKU数"] >= SET_SKU_MIN]
    for i, s in enumerate(single[:3], 1):
        desc = (f"【A{i}】1社完結・{s['SKU数']}SKU・仕入れ {s['合計仕入れ額(税込)']:,}円"
                f"（送料1回）")
        out_rows.extend(set_rows(s, f"A{i}", desc))
    # B: 上位2社を足すセット（送料2回）。1社完結が組めているときも出します。
    #    「1社で足りているのに2社案も要るのか」ですが、1社完結セットは予算を余らせる
    #    ことがあり（例: 36,300円で6SKU＝13,700円の余り）、社長が SKU 数を取るか
    #    送料回数を取るかを選べるようにしておくためです。判断材料は並べて渡す。
    if len(sets) >= 2:
        combo, spend, per_supplier = [], 0, {}
        # 2社から交互に取る。片方だけで枠を使い切ると「2社案」の意味が消えるため。
        queues = [list(s["_items"]) for s in sets[:2]]
        # ⚠️ 変数名に注意: 外側の `names`（4群を通ったサプライヤー全体）を潰さないこと。
        #    一度潰して統計値が 12社 → 2社 に化けました（2026-09-06 に修正）。
        combo_names = [s["サプライヤー名"] for s in sets[:2]]
        while any(queues) and len(combo) < SET_SKU_MAX:
            for name, q in zip(combo_names, queues):
                if not q or len(combo) >= SET_SKU_MAX:
                    continue
                it = q.pop(0)
                if spend + it[3]["spend"] > TOTAL_BUDGET:
                    continue
                combo.append((name, it))
                spend += it[3]["spend"]
                per_supplier[name] = per_supplier.get(name, 0) + it[3]["spend"]
        # 2社ぶんの送料を、それぞれの注文額で実額計算する（合算額では計算しない）
        ship_total, ship_detail = 0, []
        for name in combo_names:
            sid = supplier_ids.get(name)
            tariff = tariffs.get(int(sid)) if sid else None
            amount = per_supplier.get(name, 0)
            fee = BF.order_shipping(tariff or {}, amount)
            if fee is None:
                ship_detail.append(f"{amount:,}円→送料不明")
            else:
                ship_total += fee
                ship_detail.append(f"{amount:,}円→{fee:,}円")
        desc = (f"【B1】2社合算・{len(combo)}SKU・仕入れ {spend:,}円"
                f"・送料計 {ship_total:,}円（内訳: {' / '.join(ship_detail)}）")
        for supplier_name, it in combo:
            out_rows.extend(set_rows({"_items": [it]}, "B1", desc))

    assert_columns_not_all_empty(out_rows, OUT_COLUMNS)
    write_csv(HERE / "D_初回仕入れ_発注候補セット.csv", OUT_COLUMNS, out_rows)

    cand_counts = {}
    for it in s4:
        cand_counts[it[0]["サプライヤー名"]] = cand_counts.get(it[0]["サプライヤー名"], 0) + 1
    sup_rows = []
    for s in sets:
        sup_rows.append({
            **{k: s[k] for k in s if k != "_items"},
            "候補SKU数": cand_counts.get(s["サプライヤー名"], 0),
            "セットに組んだSKU数": s["SKU数"],
            "NETSEA店舗ページ": f"https://www.netsea.jp/shop/{s['supplier_id']}" if s["supplier_id"] else "",
        })
    write_csv(HERE / "D_サプライヤー別サマリ.csv", SUPPLIER_COLUMNS, sup_rows)

    stats["条件3_サプライヤー"] = {
        "4群通過SKUを持つサプライヤー数": len(names),
        "送料設定を取得できた社数": len(tariffs),
        "5SKU以上を1社で組める社数": len(single),
        "発注セット数": len(sets),
    }
    stats["出力"] = {"発注候補セット行数": len(out_rows), "サプライヤー行数": len(sup_rows)}
    (HERE / "D_filter_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → D_filter_stats.json")

    print("\n■ 検算")
    # 「落とした件数の合計 == 減った行数」。歩留まりの説明に穴があれば、ここで落ちます。
    for label, dropped, before, after in [
        ("S1", sum(stats["S1_除外内訳_最初に触れた項目"].values()), stats["S0_母数"], stats["S1_残"]),
        ("S2", sum(stats["S2_除外内訳"].values()), stats["S1_残"], stats["S2_残"]),
        ("S3", sum(stats["S3_除外内訳"].values()), stats["S2_残"], stats["S3_残"]),
        ("S4", sum(stats["S4_除外内訳"].values()), stats["S3_残"], stats["S4_残"]),
        ("S5", sum(stats["S5_除外内訳"].values()), stats["S4_残"], stats["S5_残"]),
    ]:
        diff = before - after
        print(f"  {label}: 落とした {dropped:,} == 減った {diff:,} → {'OK' if dropped == diff else 'NG'}")
        if dropped != diff:
            raise SystemExit(f"❌ {label} の内訳が合いません（{dropped} != {diff}）。"
                             "理由を数え損ねた行があります。")

    total_by_set = {}
    for r in out_rows:
        total_by_set.setdefault(r["セットID"], []).append(r)
    for sid, rs in total_by_set.items():
        total = sum(_int(r["★仕入れ額(税込)"]) for r in rs)
        ok_budget = total <= TOTAL_BUDGET
        ok_count = SET_SKU_MIN <= len(rs) <= SET_SKU_MAX
        ok_used = all(r["★中古品表記の有無"] in ("該当なし", "要目視") for r in rs)
        print(f"  {sid}: {len(rs)}SKU / {total:,}円 / 予算内={ok_budget} "
              f"SKU数={ok_count} 中古なし={ok_used}")
        if not (ok_budget and ok_count and ok_used):
            raise SystemExit(f"❌ セット {sid} が制約を満たしていません。出力を見直してください。")
    print("  ✅ 全セットが 5〜10SKU・総額5万円以内・中古表記なし")


if __name__ == "__main__":
    main()
