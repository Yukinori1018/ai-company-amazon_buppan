#!/usr/bin/env python3
"""候補プールを PDF のゲート（G1改〜G5）と当社ルールで切り直す — T-20260914-001。

Keepa も NETSEA も叩きません（既存 raw だけ。トークン 0）。

入力（すべて既存の raw）:
    ../T-20260831-006/out/candidates.csv      … 母数 26,942（卸値・売値・入数・最小発注数・ドロップ数）
    ../T-20260831-006/out/keepa_facts.jsonl   … ブランド・寸法・重量・カテゴリ・オファー本数
    ../T-20260906-003/out/verified.jsonl      … 回転検証（②カート最終獲得・③カート不在率）の結果
    ../T-20260907-001/out/all_candidates.csv  … PSE 判定（法務 v2.1）
    ../T-20260909-002/pool.csv                … 生産終了チェックの結果（人手）
    ../../agent_output/T-20260909-002/buybox90.jsonl … カート価格90日平均（221 ASIN・取得済み）
    本ファイル GATE_KNOWN                     … 出品ゲートの実機確認（カズヨ 2026-09-12・13件）

出力（out/ ＝ Git 追跡外。金額を含む）:
    out/01_単品_ゲート適用_全件.csv   … 入数が解けた全件に PDF ゲートを当てた明細
    out/02_セット候補.csv            … 同一サプライヤー×同一ブランド 2〜3点のセット
    out/03_N個パック候補.csv         … 同一商品 N 個パック
    out/04_8SKU候補.csv              … リアルオプション型 1回転目の候補
    out/05_規模の上限.csv            … 仕入れ枠140万で積んだときの SKU 数・月商・粗利
    out/01_候補プール切り直し_金額入り.html
    stats_漏斗.csv（追跡・件数のみ）／ out/summary.json

━━ 数字の前提（表の頭にも出す）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 大口プラン（基本成約料 0）。販売手数料は 2026-04 改定（750円超は +0.4pt 込み）。請求は消費税 ×1.1
- FBA 配送代行はサイズ区分の固定額（1,000円超の列）。寸法不明は標準2で仮置き
- 保管料 1.5ヶ月（繁忙期）・納品 49.5円/点・返品引当 3%・広告 売価の10%（PDF G3）
- 売値＝カート価格90日平均（取得済み 221 ASIN）、無ければ新品最安（送料込）。両者は全体で ≒ 同値
  （T-20260909-002 実測: 中央値の比 1.000）
- 月販見込（取り分）＝ 30日ランク下落数 ÷ (新品オファー本数 + 1)。**観測回数であって販売数ではない**。
  桁を見る道具。オファー本数は出品者数の上限（社数ではない）
- 回転月数 ＝ 発注ロット ÷ 取り分。ロット ＝ max(最小発注数を入数で割り上げた出品数, 10)

━━ 社長の固定ルール（緩めない）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 回転6ヶ月超は候補に並べない（落選理由としてだけ残す）
- 取り分が月数個（<6）の SKU は根拠にしない
- ゲート（ブランド許可）は落とさない。「要解除（10点以上の請求書）」の印で残す
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DELIV = REPO / "workspace/output/deliverables"
AGENT = REPO / "workspace/output/agent_output"
OUT = HERE / "out"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(DELIV / "T-20260521-005/code"))
import profit2026 as P  # noqa: E402
from adapters.amazon_data import _CATEGORY_NAME_MAP  # noqa: E402

CANDIDATES = DELIV / "T-20260831-006/out/candidates.csv"
FACTS = DELIV / "T-20260831-006/out/keepa_facts.jsonl"
VERIFIED = DELIV / "T-20260906-003/out/verified.jsonl"
PSE_CSV = DELIV / "T-20260907-001/out/all_candidates.csv"
POOL = DELIV / "T-20260909-002/pool.csv"
BUYBOX = AGENT / "T-20260909-002/buybox90.jsonl"
ORDER_SET_PY = DELIV / "T-20260909-002/order_set.py"   # HTML の CSS を再利用

# ── PDF のゲート（数値）と当社ルール ────────────────────────────────────
PRICE_MIN, PRICE_MAX = 2000, 5000          # G4 単価
MIN_NET, MIN_MARGIN = 500, 0.20            # G3
FBA_SHARE_CAP = 0.25                       # G3 FBA配送代行 ≤ 利益の25%
AD_RATE = P.AD_RATE_PDF                    # G3 広告10%
MAX_OFFERS_G2 = 3                          # G2 出品者 ≤ 3（オファー本数で代用＝安全側）
TURN_FAST = 0.5                            # G4 回転月2回 ＝ ロットが0.5ヶ月で捌ける
TURN_CAP = 6.0                             # 当社ルール 回転上限6ヶ月
SHARE_FLOOR = 6.0                          # 当社ルール 取り分 ≥ 月6個
TEST_LOT_MIN = 10                          # リアルオプション型 1SKU 10〜20個
SET_MULTS = (1.3, 1.5)                     # 打ち手A セット価格＝単品合計 × 1.3〜1.5
DROPS_SINGLE_SELLS = 3                     # 「構成品が単品でも売れる」の下限（30日3個）
BUDGET_PURCHASE = 1_400_000                # PDF §8 仕入れ枠
SKU_TEST_BUDGET = (50_000, 80_000)         # 1SKU 5〜8万円

# 出品ゲートの実機確認（カズヨ 2026-09-12 / T-20260909-002 ログ）。金額は含まない。
GATE_KNOWN = {
    "B0BKZFXC4P": "要解除", "B001CNJKOG": "要解除(ブランド=ぷるんと蒟蒻)", "B0CH7PQNZY": "要解除",
    "B0CH7XM4HT": "要解除", "B0DYNG386S": "要解除(10点以上の請求書)", "B01M3Z3RSY": "要解除",
    "B01M3Z3Z9A": "要解除(申請受付停止中)", "B01N5Q71SY": "制限なし", "B003B6QSOW": "要解除",
    "B00AIFX5D6": "要解除", "B00W8XO8MS": "要解除", "B08YY1WD7T": "要解除", "B00EL3KAUW": "要解除",
    "B08MT316P9": "要解除", "B0FK4GBFQP": "要解除", "B07TTMR12H": "制限なし", "B0DF74DMH2": "要解除",
    "B07L9T2CYT": "要解除", "B00BD1LETG": "要解除",
}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def category_key(names: list) -> str:
    for name in names or []:
        for needle, key in _CATEGORY_NAME_MAP:
            if needle in name:
                return key
    return "default"


# ── 読み込み ────────────────────────────────────────────────────────────
def load_all():
    facts = {}
    with open(FACTS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            facts[d["jan"]] = d
    verified = {}
    with open(VERIFIED, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            verified.setdefault(d["asin"], {})[d["stage"]] = d
    pse = {}
    if PSE_CSV.exists():
        with open(PSE_CSV, encoding="utf-8-sig") as f:
            pse = {r["ASIN"]: r for r in csv.DictReader(f)}
    pool = {}
    with open(POOL, encoding="utf-8-sig") as f:
        pool = {r["ASIN"]: r["供給ステータス"] for r in csv.DictReader(f)}
    bb = {}
    if BUYBOX.exists():
        with open(BUYBOX, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d.get("bb_avg90"):
                    bb[d["asin"]] = d["bb_avg90"]
    with open(CANDIDATES, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows, facts, verified, pse, pool, bb


def turnover_label(v: dict | None) -> str:
    if not v:
        return "未検証"
    if 2 in v:
        return "通過" if v[2]["ok"] else f"不通過({v[2].get('why') or '②③'})"
    if 1 in v:
        return "①通過・②③未" if v[1]["ok"] else f"不通過({v[1].get('why') or '①'})"
    return "未検証"


# ── 単品の評価 ──────────────────────────────────────────────────────────
def build_skus(rows, facts, verified, pse, pool, bb) -> list[dict]:
    """入数が解けて売値がある全件を、2026 手数料・大口・広告10%で引き直す。"""
    skus = []
    for r in rows:
        st = r["状態"]
        if not st.startswith("計算済み"):
            continue
        if r["要確認理由"]:
            continue
        fa = facts.get(r["JAN"], {})
        pack = int(fnum(r["出品の入数"]) or 1)
        w_ex = fnum(r["NETSEA卸値(税抜)"]) or 0.0
        wholesale_incl = w_ex * pack * 1.1
        price_src = "新品最安(送料込)"
        price = fnum(r["Amazon価格"])
        if r["ASIN"] in bb:
            price, price_src = float(bb[r["ASIN"]]), "カート90日平均"
        if not price:
            continue
        ck = category_key(fa.get("category_names"))
        dims, g = fa.get("package_mm") or [], fa.get("package_g")
        p10 = P.breakdown(price=price, wholesale_incl=wholesale_incl, category_key=ck,
                          package_mm=dims, package_g=g, ad_rate=AD_RATE)
        p0 = P.breakdown(price=price, wholesale_incl=wholesale_incl, category_key=ck,
                         package_mm=dims, package_g=g, ad_rate=0.0)
        drops = fnum(r["月間販売数(30日ランク下落数)"])
        offers = fnum(r["出品者数"])
        share = (drops / (offers + 1)) if (drops is not None and offers is not None) else None
        moq_units = int(fnum(r["最小発注数"]) or 1)
        moq_listing = max(1, math.ceil(moq_units / pack))
        lot = max(moq_listing, TEST_LOT_MIN)
        turn = (lot / share) if share else None
        s = {
            "ASIN": r["ASIN"], "JAN": r["JAN"], "商品名": r["商品名"], "Amazon商品名": r["Amazon商品名"],
            "サプライヤー": r["サプライヤー名"], "ブランド": (fa.get("brand") or "").strip(),
            "カテゴリ": ck, "売値": round(price), "売値の出どころ": price_src,
            "卸値(税込・1出品)": round(wholesale_incl), "入数": pack,
            "純利益(広告10%)": round(p10.net), "利益率%(広告10%)": round(p10.margin * 100, 1),
            "純利益(広告0)": round(p0.net), "利益率%(広告0)": round(p0.margin * 100, 1),
            "販売手数料": round(p10.referral_fee), "FBA配送代行": round(p10.fba_fee),
            "FBA÷利益%": round(p10.fba_fee / p10.net * 100, 1) if p10.net > 0 else None,
            "FBAサイズ": p10.size_label, "広告": round(p10.ad),
            "30日ドロップ": drops, "オファー本数": offers, "取り分/月": round(share, 2) if share is not None else None,
            "最小発注数(卸)": moq_units, "最小ロット出品数": moq_listing, "ロット(≥10)": lot,
            "ロット金額": round(lot * wholesale_incl), "回転月数": round(turn, 1) if turn else None,
            "Amazon本体": r["Amazon本体の有無"], "回転検証": turnover_label(verified.get(r["ASIN"])),
            "PSE": (pse.get(r["ASIN"]) or {}).get("PSE判定", "未判定"),
            "PSE要書類": (pse.get(r["ASIN"]) or {}).get("要書類確認", ""),
            "ゲート": GATE_KNOWN.get(r["ASIN"], "未確認(要解除前提)"),
            "供給": pool.get(r["ASIN"], "終売チェック未実施"),
            "法令要確認": r["法令要確認"], "同一JANのASIN数": r["同一JANのASIN数"],
            "Amazonページ": r["Amazonページ"], "NETSEA商品ページ": r["NETSEA商品ページ"],
            "_dims": dims, "_g": g, "_p10": p10, "_p0": p0,
        }
        skus.append(s)
    return skus


def gate_flags(s: dict) -> dict:
    """PDF ゲートと当社ルールを1つずつ判定（落とさず印を付ける）。"""
    p = s["_p10"]
    g3a, g3b = P.passes_g3(p, min_net=MIN_NET, min_margin=MIN_MARGIN, fba_share_cap=FBA_SHARE_CAP)
    share, turn = s["取り分/月"], s["回転月数"]
    return {
        "G4価格": PRICE_MIN <= s["売値"] <= PRICE_MAX,
        "G3利益": g3a,
        "G3FBA25": g3b,
        "回転≤6ヶ月": turn is not None and turn <= TURN_CAP,
        "月2回転": turn is not None and turn <= TURN_FAST,
        "取り分≥6": share is not None and share >= SHARE_FLOOR,
        "G2出品者≤3": s["オファー本数"] is not None and s["オファー本数"] <= MAX_OFFERS_G2,
        "本体なし": s["Amazon本体"] == "なし",
    }


# ── 漏斗 ────────────────────────────────────────────────────────────────
def funnel(rows, skus) -> list[dict]:
    n0 = len(rows)
    n_exists = sum(1 for r in rows if r["状態"].startswith(("計算済み", "要確認")))
    n_body = sum(1 for r in rows if r["状態"].startswith(("計算済み", "要確認")) and r["Amazon本体の有無"] == "なし")
    steps = [("S0 母数（NETSEA 26,942 JAN）", n0, "T-20260831-006 harvest"),
             ("S1 Amazon に同一JANの ASIN があり売値がある", n_exists, "状態=計算済み/要確認"),
             ("S2 Amazon 本体が出品していない", n_body, "availability_amazon = -1")]
    cur = [s for s in skus if s["Amazon本体"] == "なし"]
    steps.append(("S3 入数が解けて要確認なし（利益を計算できる）", len(cur), "pack.resolve_multiplier"))
    fl = {s["ASIN"]: gate_flags(s) for s in cur}

    def step(name, pred, note):
        nonlocal cur
        cur = [s for s in cur if pred(fl[s["ASIN"]], s)]
        steps.append((name, len(cur), note))

    step("S4 G4 単価 2,000〜5,000円", lambda f, s: f["G4価格"], "売値（カート90日平均 or 最安）")
    step("S5 G3 利益率20%・利益額500円（大口・広告10%込み）", lambda f, s: f["G3利益"], "profit2026.breakdown")
    step("S6 G3 FBA配送代行 ≤ 利益の25%", lambda f, s: f["G3FBA25"], "FBA÷純利益")
    base_after_g3 = list(cur)
    step("S7a 回転 ≤ 6ヶ月（ロット=max(最小ロット,10)÷取り分）", lambda f, s: f["回転≤6ヶ月"], "当社ルール")
    step("S7b 取り分 ≥ 月6個", lambda f, s: f["取り分≥6"], "当社ルール（月数個は根拠にしない）")
    s7 = list(cur)
    step("S7c 回転 月2回（0.5ヶ月）", lambda f, s: f["月2回転"], "PDF G4")
    steps.append(("S8 G2 出品者 ≤3（S7b 通過のうち）", sum(1 for s in s7 if fl[s["ASIN"]]["G2出品者≤3"]), "オファー本数≤3"))
    # 回転検証（②③）のオーバーレイ
    steps.append(("参考: S6 通過のうち T-20260906-003 回転検証＝通過", sum(1 for s in base_after_g3 if s["回転検証"] == "通過"), "verified.jsonl stage2"))
    steps.append(("参考: S6 通過のうち 30日ドロップ ≥ 3", sum(1 for s in base_after_g3 if (s["30日ドロップ"] or 0) >= 3), "売れた形跡"))
    return steps


def sensitivity(skus) -> list[dict]:
    """利益率の線・広告・価格帯を動かしたとき、S3 の母数から何件残るか（社長が線を引くための表）。"""
    base = [s for s in skus if s["Amazon本体"] == "なし"]
    out = []
    for band, lo, hi in (("2,000〜5,000", PRICE_MIN, PRICE_MAX), ("全価格帯", 0, 10**9)):
        for ad_key in ("_p10", "_p0"):
            for m in (0.20, 0.15, 0.10, 0.05):
                sel = [s for s in base if lo <= s["売値"] <= hi
                       and s[ad_key].net >= MIN_NET and s[ad_key].margin >= m]
                fba = [s for s in sel if s[ad_key].fba_fee <= FBA_SHARE_CAP * s[ad_key].net]
                t6 = [s for s in sel if s["回転月数"] is not None and s["回転月数"] <= TURN_CAP
                      and (s["取り分/月"] or 0) >= SHARE_FLOOR]
                t05 = [s for s in t6 if s["回転月数"] <= TURN_FAST]
                out.append({"価格帯": band, "広告": "10%" if ad_key == "_p10" else "0%",
                            "利益率の線": f"{int(m*100)}%", "G3利益": len(sel), "+FBA≤25%": len(fba),
                            "+回転≤6ヶ月・取り分≥6": len(t6), "+月2回転": len(t05),
                            "+G2出品者≤3": sum(1 for s in t6 if (s["オファー本数"] or 99) <= MAX_OFFERS_G2)})
    return out


# ── セット組み（打ち手A）────────────────────────────────────────────────
def build_sets(skus) -> tuple[list[dict], list[dict]]:
    """同一サプライヤー×同一ブランドの 2〜3点。構成品は「単品でも売れる」（30日ドロップ≥3）。"""
    base = [s for s in skus if s["Amazon本体"] == "なし" and (s["30日ドロップ"] or 0) >= DROPS_SINGLE_SELLS
            and s["ブランド"]]
    groups = defaultdict(list)
    for s in base:
        groups[(s["サプライヤー"], s["ブランド"])].append(s)
    sets, group_rows = [], []
    for (sup, brand), items in groups.items():
        if len(items) < 2:
            continue
        # 2点の合計×1.3 が 5,000 を超えるなら単品 3,846 円超は組めない
        items = sorted([s for s in items if s["売値"] <= PRICE_MAX / min(SET_MULTS)], key=lambda s: s["売値"])
        n_pass = 0
        best = None
        for k in (2, 3):
            for combo in itertools.combinations(items, k):
                base_sum = sum(s["売値"] for s in combo)
                if base_sum * min(SET_MULTS) > PRICE_MAX or base_sum * max(SET_MULTS) < PRICE_MIN:
                    continue
                wholesale = sum(s["卸値(税込・1出品)"] for s in combo)
                dims, g = P.combine_packages([(s["_dims"], s["_g"]) for s in combo])
                ck = combo[0]["カテゴリ"]
                row = {"サプライヤー": sup, "ブランド": brand, "点数": k,
                       "構成ASIN": " / ".join(s["ASIN"] for s in combo),
                       "構成品": " ／ ".join(s["Amazon商品名"][:40] for s in combo),
                       "単品合計": base_sum, "卸値合計(税込)": round(wholesale),
                       "構成品の単品利益率%": " / ".join(str(s["利益率%(広告10%)"]) for s in combo),
                       "構成品の取り分/月": " / ".join(str(s["取り分/月"]) for s in combo),
                       "取り分の最小(上限の目安・推測)": min((s["取り分/月"] or 0) for s in combo),
                       "構成品の最小30日ドロップ": min((s["30日ドロップ"] or 0) for s in combo),
                       "最小発注額合計(卸)": sum(s["最小発注数(卸)"] * s["卸値(税込・1出品)"] // s["入数"] for s in combo),
                       "ゲート": " / ".join(s["ゲート"] for s in combo),
                       "PSE": " / ".join(s["PSE"] for s in combo),
                       "供給": " / ".join(s["供給"] for s in combo),
                       "回転検証": " / ".join(s["回転検証"] for s in combo)}
                ok_any = False
                for mult in SET_MULTS:
                    price = round(base_sum * mult)
                    if not (PRICE_MIN <= price <= PRICE_MAX):
                        row[f"セット価格×{mult}"] = price
                        row[f"利益率%×{mult}"] = None
                        row[f"純利益×{mult}"] = None
                        continue
                    p = P.breakdown(price=price, wholesale_incl=wholesale, category_key=ck,
                                    package_mm=dims, package_g=g, n_units=k, ad_rate=AD_RATE,
                                    material_yen=P.BUNDLE_MATERIAL_YEN)
                    a, b = P.passes_g3(p, min_net=MIN_NET, min_margin=MIN_MARGIN, fba_share_cap=FBA_SHARE_CAP)
                    row[f"セット価格×{mult}"] = price
                    row[f"利益率%×{mult}"] = round(p.margin * 100, 1)
                    row[f"純利益×{mult}"] = round(p.net)
                    row[f"G3×{mult}"] = "通過" if a else "不通過"
                    row[f"FBA≤25%×{mult}"] = "通過" if b else "不通過"
                    row["FBAサイズ(セット)"] = p.size_label
                    row["_net13" if mult == 1.3 else "_net15"] = p.net
                    row["_m13" if mult == 1.3 else "_m15"] = p.margin
                    ok_any = ok_any or a
                if ok_any:
                    n_pass += 1
                    sets.append(row)
                    if best is None or (row.get("_m13") or 0) > (best.get("_m13") or 0):
                        best = row
        if items:
            group_rows.append({"サプライヤー": sup, "ブランド": brand, "単品で売れる構成品の数": len(items),
                               "G3を通るセット数": n_pass,
                               "最高利益率%(×1.3)": round((best.get("_m13") or 0) * 100, 1) if best else None,
                               "構成品のゲート(既知)": Counter(s["ゲート"] for s in items).most_common(1)[0][0]})
    sets.sort(key=lambda r: -(r.get("_m13") or r.get("_m15") or 0))
    group_rows.sort(key=lambda r: (-r["G3を通るセット数"], -r["単品で売れる構成品の数"]))
    return sets, group_rows


# ── 大口梱包（同一商品 N 個パック）──────────────────────────────────────
def build_npacks(skus) -> list[dict]:
    base = [s for s in skus if s["Amazon本体"] == "なし" and (s["30日ドロップ"] or 0) >= DROPS_SINGLE_SELLS]
    out = []
    for s in base:
        for n in range(2, 13):
            for disc in (1.0, 0.9):
                price = round(s["売値"] * n * disc)
                if not (PRICE_MIN <= price <= PRICE_MAX):
                    continue
                dims, g = P.combine_packages([(s["_dims"], s["_g"])] * n)
                p = P.breakdown(price=price, wholesale_incl=s["卸値(税込・1出品)"] * n,
                                category_key=s["カテゴリ"], package_mm=dims, package_g=g,
                                n_units=n, ad_rate=AD_RATE, material_yen=P.BUNDLE_MATERIAL_YEN)
                a, b = P.passes_g3(p, min_net=MIN_NET, min_margin=MIN_MARGIN, fba_share_cap=FBA_SHARE_CAP)
                if not a:
                    continue
                out.append({"ASIN": s["ASIN"], "Amazon商品名": s["Amazon商品名"][:60], "サプライヤー": s["サプライヤー"],
                            "ブランド": s["ブランド"], "N": n, "割引": f"{int((1-disc)*100)}%",
                            "単品売値": s["売値"], "単品利益率%(広告10%)": s["利益率%(広告10%)"],
                            "パック価格": price, "パック純利益": round(p.net), "パック利益率%": round(p.margin * 100, 1),
                            "FBA≤25%": "通過" if b else "不通過", "FBAサイズ(パック)": p.size_label,
                            "単品の30日ドロップ": s["30日ドロップ"], "単品の取り分/月": s["取り分/月"], "単品の回転検証": s["回転検証"],
                            "ゲート": s["ゲート"], "PSE": s["PSE"], "供給": s["供給"],
                            "_m": p.margin})
                break  # 同じ N で割引なしが通れば 10% 引きは出さない（表を短く）
    out.sort(key=lambda r: -r["_m"])
    # 1 ASIN につき最良 N だけ残す
    seen, dedup = set(), []
    for r in out:
        if r["ASIN"] in seen:
            continue
        seen.add(r["ASIN"])
        dedup.append(r)
    return dedup


# ── 規模の上限（仕入れ枠140万）────────────────────────────────────────
def scale(cands: list[dict], months: float, budget: int = BUDGET_PURCHASE) -> dict:
    """利益率順に積む。1SKU のロット＝ max(最小ロット, 取り分×months)。月商＝Σ 取り分×売値。"""
    cands = sorted(cands, key=lambda c: -c["margin"])
    cap, n, rev, gp, per_turn = 0, 0, 0.0, 0.0, 0.0
    for c in cands:
        lot = max(c["moq"], math.ceil(c["share"] * months))
        cost = lot * c["wholesale"]
        if cap + cost > budget:
            continue
        cap += cost
        n += 1
        rev += c["share"] * c["price"]
        gp += c["share"] * c["net"]
        per_turn += cost
    return {"SKU数": n, "1回転あたり仕入額": round(cap), "月商": round(rev), "月粗利(広告10%込み後)": round(gp),
            "候補数": len(cands)}


def scale_table(skus, sets) -> list[dict]:
    rows = []
    fl = {s["ASIN"]: gate_flags(s) for s in skus}

    def single_pool(min_margin, price_band, need_fba):
        out = []
        for s in skus:
            f = fl[s["ASIN"]]
            p = s["_p10"]
            if not f["本体なし"] or s["取り分/月"] is None:
                continue
            if price_band and not f["G4価格"]:
                continue
            if p.net < MIN_NET or p.margin < min_margin:
                continue
            if need_fba and not f["G3FBA25"]:
                continue
            if s["取り分/月"] < SHARE_FLOOR:
                continue
            out.append({"margin": p.margin, "moq": s["最小ロット出品数"], "share": s["取り分/月"],
                        "wholesale": s["卸値(税込・1出品)"], "price": s["売値"], "net": p.net})
        return out

    def set_pool(min_margin):
        out = []
        for r in sets:
            m = r.get("_m13")
            if m is None or m < min_margin or (r.get("_net13") or 0) < MIN_NET:
                continue
            share = r["取り分の最小(上限の目安・推測)"]
            if share < SHARE_FLOOR:
                continue
            out.append({"margin": m, "moq": 1, "share": share, "wholesale": r["卸値合計(税込)"],
                        "price": r["セット価格×1.3"], "net": r["_net13"]})
        return out

    for label, mm, band, fba in (("PDF どおり（20%・2,000〜5,000・FBA≤25%）", 0.20, True, True),
                                  ("20%・2,000〜5,000（FBA25%なし）", 0.20, True, False),
                                  ("20%・全価格帯", 0.20, False, False),
                                  ("15%・全価格帯", 0.15, False, False),
                                  ("10%・全価格帯", 0.10, False, False)):
        sp = single_pool(mm, band, fba)
        for months, mlabel in ((TURN_FAST, "月2回転"), (TURN_CAP, "6ヶ月")):
            pool_turn = [c for c in sp if max(c["moq"], 1) / c["share"] <= months]
            r1 = scale(pool_turn, months)
            rows.append({"条件": label, "回転": mlabel, "セット": "なし", **r1})
            r2 = scale(pool_turn + set_pool(mm), months)
            rows.append({"条件": label, "回転": mlabel, "セット": "あり(取り分は構成品の最小＝推測)", **r2})
    return rows


# ── 8SKU（リアルオプション型 1回転目）────────────────────────────────
def pick_8(skus) -> list[dict]:
    fl = {s["ASIN"]: gate_flags(s) for s in skus}
    strict = [s for s in skus if fl[s["ASIN"]]["本体なし"] and fl[s["ASIN"]]["G3利益"]
              and fl[s["ASIN"]]["回転≤6ヶ月"] and fl[s["ASIN"]]["取り分≥6"]]
    # PDF どおり（20%）で 8 件に届かないときは、利益率の線だけ 5% まで下げた「次善」を続けて出す。
    # 回転6ヶ月・取り分≥6 は社長の固定ルールなので緩めない（緩めた案は生成しない）。
    loose = [s for s in skus if fl[s["ASIN"]]["本体なし"] and s["_p10"].net > 0 and s["_p10"].margin >= 0.05
             and fl[s["ASIN"]]["回転≤6ヶ月"] and fl[s["ASIN"]]["取り分≥6"] and s not in strict]
    # 並べ順は利益ではなく回転の安全側（回転月数の昇順）。利益率順は終売品を上に出す
    strict.sort(key=lambda s: (s["回転月数"], -s["_p10"].margin))
    loose.sort(key=lambda s: (s["回転月数"], -s["_p10"].margin))
    rows = []
    for s in (strict + loose)[:8]:
        units = max(s["最小ロット出品数"], TEST_LOT_MIN)
        units = min(20, max(units, math.ceil(SKU_TEST_BUDGET[0] / s["卸値(税込・1出品)"])))
        rows.append({"区分": "PDFどおり(20%)" if s in strict else "次善(利益率の線を5%まで下げた)",
                     "ASIN": s["ASIN"], "Amazon商品名": s["Amazon商品名"][:60], "サプライヤー": s["サプライヤー"],
                     "ブランド": s["ブランド"], "売値": s["売値"], "卸値(税込・1出品)": s["卸値(税込・1出品)"],
                     "利益率%(広告10%)": s["利益率%(広告10%)"], "純利益(広告10%)": s["純利益(広告10%)"],
                     "G4価格帯": "○" if fl[s["ASIN"]]["G4価格"] else "×(帯外)",
                     "FBA≤25%": "○" if fl[s["ASIN"]]["G3FBA25"] else "×",
                     "30日ドロップ": s["30日ドロップ"], "オファー本数": s["オファー本数"], "取り分/月": s["取り分/月"],
                     "テスト数量(10〜20)": units, "テスト仕入額": round(units * s["卸値(税込・1出品)"]),
                     "テスト仕入額≤8万": "○" if units * s["卸値(税込・1出品)"] <= SKU_TEST_BUDGET[1] else "×(最小ロットが大きい)",
                     "回転月数(テスト数量)": round(units / s["取り分/月"], 1),
                     "回転検証": s["回転検証"], "ゲート": s["ゲート"], "PSE": s["PSE"], "供給": s["供給"],
                     "Amazonページ": s["Amazonページ"], "NETSEA商品ページ": s["NETSEA商品ページ"]})
    return rows


# ── 出力 ────────────────────────────────────────────────────────────────
def write_csv(path: Path, rows: list[dict]):
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def h(x) -> str:
    return str(x if x is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(rows: list[dict], cols=None, limit=None) -> str:
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    if not rows:
        return "<p class='muted'>該当なし</p>"
    cols = cols or list(rows[0].keys())
    body = []
    for r in rows[: limit or len(rows)]:
        body.append("<tr>" + "".join(f"<td>{h(r.get(c))}</td>" for c in cols) + "</tr>")
    return ("<div class='tw'><table><thead><tr>" + "".join(f"<th>{h(c)}</th>" for c in cols)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def css() -> str:
    m = re.search(r'HTML_CSS = """(.*?)"""', ORDER_SET_PY.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else "body{font-family:sans-serif}"


def write_html(steps, sens, sets, groups, npacks, scale_rows, eight, n_skus):
    parts = [f"<style>{css()}</style><div class='wrap'>",
             "<p class='kicker'>T-20260914-001 ／ IT タカシ ／ 2026-09-14 ／ 金額入り（Git 追跡外）</p>",
             "<h1>候補プールの切り直し — PDF のゲート（G1改〜G5）× 運転資金200万</h1>",
             "<p class='lead'>前提: 大口・2026-04 手数料・広告10%・FBA 1,000円超の列・保管1.5ヶ月・納品49.5円/点・返品3%。"
             "売値はカート90日平均（221 ASIN）か新品最安。取り分＝30日ドロップ÷(オファー本数+1)（観測回数・桁の道具）。"
             "回転＝max(最小ロット,10)÷取り分。</p>",
             "<h1 class='part'>第1部 漏斗</h1>",
             table([{"段": a, "件数": b, "根拠": c} for a, b, c in steps]),
             "<h2>感応度（利益率の線・広告・価格帯を動かす）</h2>", table(sens),
             "<h1 class='part'>第2部 セット組み（同一サプライヤー×同一ブランド 2〜3点）</h1>",
             f"<p>G3（20%・500円・広告10%）を ×1.3 か ×1.5 で通るセット: <b>{len(sets)}</b> 通り。"
             f"ブランド別の集計（上位）:</p>", table(groups, limit=40),
             "<h2>セット候補（構成品の最小30日ドロップ ≥ 20 ＝ 需要の根拠がある順・上位60）</h2>",
             table(sorted([r for r in sets if r["構成品の最小30日ドロップ"] >= 20],
                          key=lambda r: (-r["構成品の最小30日ドロップ"], -(r.get("_m13") or 0))), limit=60),
             "<h2>セット候補（利益率×1.3 の降順・上位40。需要の根拠は薄い）</h2>", table(sets, limit=40),
             "<h1 class='part'>第3部 同一商品 N 個パック（法人向け大口梱包）</h1>",
             f"<p>G3 を通る N 個パック: <b>{len(npacks)}</b> ASIN（各 ASIN の最良 N）。</p>", table(npacks, limit=60),
             "<h1 class='part'>第4部 仕入れ枠140万で回せる規模</h1>",
             "<p>利益率順に積む。1SKU のロット＝max(最小ロット, 取り分×回転月数)。月商＝Σ取り分×売値（取り分の上限で見た月商＝上限）。"
             "セットの取り分は構成品の最小を上限として置いた推測。</p>", table(scale_rows),
             "<h1 class='part'>第5部 リアルオプション型 1回転目の候補（最大8）</h1>",
             "<p>条件: Amazon本体なし・G3利益（20%・500円・広告10%）・回転≤6ヶ月・取り分≥6。並びは回転月数の昇順（利益順ではない）。</p>",
             table(eight),
             f"<p class='muted'>単品の明細（{n_skus}件）は out/01_単品_ゲート適用_全件.csv。</p></div>"]
    (OUT / "01_候補プール切り直し_金額入り.html").write_text(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>候補プールの切り直し（金額入り）</title></head><body>" + "".join(parts) + "</body></html>",
        encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    rows, facts, verified, pse, pool, bb = load_all()
    skus = build_skus(rows, facts, verified, pse, pool, bb)
    for s in skus:
        s.update({f"判定:{k}": ("○" if v else "×") for k, v in gate_flags(s).items()})
    steps = funnel(rows, skus)
    sens = sensitivity(skus)
    sets, groups = build_sets(skus)
    npacks = build_npacks(skus)
    scale_rows = scale_table(skus, sets)
    eight = pick_8(skus)

    write_csv(OUT / "01_単品_ゲート適用_全件.csv", skus)
    # 全通りは組み合わせの数で膨らむだけ（数万通り）。需要の根拠がある順に2本へ分ける。
    write_csv(OUT / "02_セット候補_需要根拠あり.csv",
              sorted([r for r in sets if r["構成品の最小30日ドロップ"] >= 10],
                     key=lambda r: (-r["構成品の最小30日ドロップ"], -(r.get("_m13") or 0))))
    write_csv(OUT / "02_セット候補_利益率上位2000.csv", sets[:2000])
    write_csv(OUT / "02b_セット_ブランド別.csv", groups)
    write_csv(OUT / "03_N個パック候補.csv", npacks)
    write_csv(OUT / "04_8SKU候補.csv", eight)
    write_csv(OUT / "05_規模の上限.csv", scale_rows)
    write_csv(HERE / "stats_漏斗.csv", [{"段": a, "件数": b} for a, b, _ in steps])
    write_html(steps, sens, sets, groups, npacks, scale_rows, eight, len(skus))

    summary = {
        "funnel": [{"step": a, "n": b, "note": c} for a, b, c in steps],
        "sensitivity": sens,
        "sets": {"n_pass": len(sets), "n_groups_with_pass": sum(1 for g in groups if g["G3を通るセット数"] > 0),
                 "n_groups": len(groups),
                 "n_pass_13": sum(1 for r in sets if r.get("G3×1.3") == "通過"),
                 "n_pass_15": sum(1 for r in sets if r.get("G3×1.5") == "通過"),
                 "n_pass_13_fba": sum(1 for r in sets if r.get("FBA≤25%×1.3") == "通過"),
                 "n_share6_13": sum(1 for r in sets if r.get("G3×1.3") == "通過" and r["取り分の最小(上限の目安・推測)"] >= SHARE_FLOOR),
                 "n_drops20_13": sum(1 for r in sets if r.get("G3×1.3") == "通過" and r["構成品の最小30日ドロップ"] >= 20),
                 "brands_drops20_13": sorted({(r["サプライヤー"], r["ブランド"]) for r in sets if r.get("G3×1.3") == "通過" and r["構成品の最小30日ドロップ"] >= 20}),
                 "n_drops10_13": sum(1 for r in sets if r.get("G3×1.3") == "通過" and r["構成品の最小30日ドロップ"] >= 10),
                 "top_groups": groups[:15]},
        "npacks": {"n": len(npacks), "n_fba": sum(1 for r in npacks if r["FBA≤25%"] == "通過"),
                   "n_share6": sum(1 for r in npacks if (r["単品の取り分/月"] or 0) >= SHARE_FLOOR),
                   "n_drops20": sum(1 for r in npacks if (r["単品の30日ドロップ"] or 0) >= 20),
                   "n_verified": sum(1 for r in npacks if r["単品の回転検証"] == "通過"),
                   "top": [{k: v for k, v in r.items() if k in ("ブランド", "N", "パック利益率%", "単品利益率%(広告10%)", "単品の取り分/月", "ゲート")} for r in npacks[:15]]},
        "scale": scale_rows,
        "eight": [{k: v for k, v in r.items() if k in ("区分", "ブランド", "テスト仕入額≤8万", "サプライヤー", "利益率%(広告10%)", "取り分/月", "回転月数(テスト数量)", "G4価格帯", "FBA≤25%", "回転検証", "ゲート", "供給", "PSE")} for r in eight],
        "n_skus": len(skus),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
