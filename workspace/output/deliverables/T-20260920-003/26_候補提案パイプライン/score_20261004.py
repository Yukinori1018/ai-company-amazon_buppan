#!/usr/bin/env python3
"""2026-10-04 の再採点 — 価格履歴・カート保持者・カレンダーを入れて上位30件を出す。

    python3 score_20261004.py                 # 全件を採点して CSV と内訳を書く
    python3 score_20261004.py --asin B0xxxxx  # 1件だけ計算過程を全部出す
    python3 score_20261004.py --relax         # 条件を緩めたときに何件増えるかの感度表

何を変えたか（`regrade.py` との差）
----------------------------------
| # | 変えたところ | 旧 | 新 |
|---|---|---|---|
| ① | **採算の売価** | 台帳の売価（スキャン時点の現在価格・最大4日前） | **90日中央値**（`price_history`）。悲観は**90日の下位25%** |
| ② | 価格の動き | 見ていない | **下落トレンド・振れ幅・高値掴み**を判定に入れる |
| ③ | カート保持者 | 10/01 の値 | **今日取り直した `stats.buyBoxSellerId`** |
| ④ | 実売 | 台帳の値 | 今日の `monthlySold` とランク |
| ⑤ | 等級 | 費目だけ悲観 | **売価も悲観**（下位25%）。率20% **または** 手残り400円 |
| ⑥ | カレンダー | 無し | **発注日→着荷→FBA→販売開始→売り切り目標月**と**季節の窓** |
| ⑦ | 在庫 | 見ていない | NETSEA 索引の `在庫あり` を要求（`品切れ` は買えない） |

**落ちた理由は必ず集計します**（CLAUDE.md §3.3-21）。「0件でした」で止めないため。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fba_cost                       # noqa: E402
import price_history as PH            # noqa: E402
import profit                         # noqa: E402
import schedule as SC                 # noqa: E402
import seasonality                    # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
POOL = WORK / "pipeline/buy_list_private.csv"
DISCOVERED = WORK / "pipeline/discovered.json"
NETSEA_IDX = WORK / "pipeline/netsea_jan_index.json"
SELLER_NAMES = WORK / "pipeline/seller_names.json"
RAW = WORK / "refetch20261004/raw.jsonl"
OUT = WORK / "score20261004"

# 🔴 実行日を起点にする。固定値にすると予定表が腐ったまま出続ける
#    （2026-10-09 実測：648行すべての発注日が 10/04 のままで、全行の予定が過去だった）。
#    再現が要るときだけ SCORE_TODAY=YYYY-MM-DD で固定する。
TODAY = (date.fromisoformat(os.environ["SCORE_TODAY"])
         if os.environ.get("SCORE_TODAY") else date.today())
MAX_ORDER_TOTAL_YEN = 80_000        # 1 SKU の発注額の上限（残枠）
# 実売の代理：ランクがこれ以内なら「売れている」とみなす。
# 🔴 **300,000 は当社のプールを作ったときの基準そのものです**（memory
# `project_research_criteria_v13`「ランク30万」）。2026-10-04 に私が 100,000 へ締めたら
# **候補が0件**になりました。母数を 30万位で集めておいて 10万位で判定するのは、
# 自分のコードが条件を壊している例です（CLAUDE.md §3.3-19）。
# 緩めた/締めたときの件数は `--relax` で出ます。
RANK_OK = 300_000
TOP_N = 30

AMAZON_SELLER_IDS = {"AN1VRQENFRJN5"}   # Amazon.co.jp 本体

# 人が実画面で見た売価（2026-10-04 カズヨ）。**機械で上書きしない**（§3.3-16）。
SCREEN_PRICES = {
    "B003181XQ8": 8318, "B00ZW7OO0I": 1300, "B01N5Q61K6": 3250,
    "B004PXZAFI": 5017, "B086LB3LH6": 1580,
}
# 2026-10-01 にカズヨが実画面で確認して NO-GO にした行。
SCREEN_CHECKED_NO_GO = ("B0FNWB76NG", "B001LOOR4E", "B0FN3NWKYZ", "B0015XNJMW")

MIN_PLAUSIBLE_COST_RATIO = 15.0     # 卸率がこれ未満＝単位ずれ/終売/仕入れ不存在の疑い

# カテゴリー名は Keepa の categoryTree の根を fba_cost の料率表の名前へ寄せる。
CATEGORY_ALIAS = {
    "ホーム&キッチン": "ホーム&キッチン", "文房具・オフィス用品": "文房具・オフィス用品",
    "DIY・工具・ガーデン": "DIY・工具", "産業・研究開発用品": "産業・研究開発用品",
    "ドラッグストア": "ビューティ・ヘルス・パーソナルケア",
    "ビューティー": "ビューティ・ヘルス・パーソナルケア",
    "食品・飲料・お酒": "食品&飲料", "ペット用品": "ペット用品",
    "ベビー&マタニティ": "ベビー&マタニティ", "服&ファッション小物": "服&ファッション小物",
    "おもちゃ": "おもちゃ&ホビー", "ホビー": "おもちゃ&ホビー",
    "スポーツ&アウトドア": "スポーツ&アウトドア", "車&バイク": "カー&バイク用品",
    "家電&カメラ": "エレクトロニクス", "パソコン・周辺機器": "パソコン・周辺機器",
    "楽器・音響機器": "楽器",
}


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").replace("円", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ── 読み込み ─────────────────────────────────────────────────────────────


def load_all() -> tuple[list[dict], dict, dict, dict, dict, str]:
    rows = list(csv.DictReader(POOL.open(encoding="utf-8-sig")))
    cands = json.loads(DISCOVERED.read_text())["candidates"]
    idx = json.loads(NETSEA_IDX.read_text())["jans"]
    names = json.loads(SELLER_NAMES.read_text()) if SELLER_NAMES.exists() else {}
    fresh: dict[str, dict] = {}
    if RAW.exists():
        for line in RAW.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("asin"):
                fresh[o["asin"]] = o["product"]
    idx_day = datetime.fromtimestamp(os.path.getmtime(NETSEA_IDX)).strftime("%Y-%m-%d")
    return rows, cands, idx, names, fresh, idx_day


# ── 1件ぶんの組み立て ────────────────────────────────────────────────────


def category_of(product: dict) -> str | None:
    tree = product.get("categoryTree") or []
    if not tree:
        return None
    return CATEGORY_ALIAS.get(tree[0].get("name") or "")


def set_count_of(row: dict, product: dict) -> tuple[float | None, str, str]:
    """セット数（Amazon 1個 ＝ 卸の何点か）と確度。

    🔴 **`packageQuantity` を黙って信じません。**台帳の値（商品名から読んだ数）と
    突き合わせて、**一致したら確度を上げ、食い違ったら UNKNOWN に落とします**
    （CLAUDE.md §3.3-17「2つのデータ源をつなぐ口は単位を渡させる」）。
    """
    led = _num(row.get("Amazon側のセット数(Amazon1個=卸何点か)"))
    conf = (row.get("セット数の確度") or "").strip()
    pq = product.get("packageQuantity")
    pq = int(pq) if isinstance(pq, int) and pq > 0 else None

    if led and pq:
        if int(led) == pq:
            return led, "確定", f"商品名と Keepa packageQuantity が一致（{pq}）"
        return (None, "食い違い",
                f"台帳 {int(led)} と Keepa packageQuantity {pq} が食い違います。"
                f"**人が卸サイトと Amazon の両方の画面を見てください。**")
    if led and conf in ("確定", "単独"):
        return led, conf, row.get("セット数の情報源") or "商品名"
    return (led, conf or "不明", row.get("セット数の情報源") or "")


def cart_of(product: dict, names: dict) -> tuple[str, str, str]:
    """(判定, カート保持者の表示名, 理由)。落とすのは**本体がカートを持つ行だけ**。"""
    s = product.get("stats") or {}
    sid = s.get("buyBoxSellerId")
    is_amz = s.get("buyBoxIsAmazon")
    if is_amz is True or (sid and sid in AMAZON_SELLER_IDS):
        return ("FAIL", "Amazon.co.jp（本体）",
                "カート保持者が Amazon.co.jp 本体です。値下げしてもカートは取れません。")
    if not sid or sid == "-1":
        return ("UNKNOWN", "不明",
                "いまカートが立っていません（おすすめ出品なし）。"
                "**実画面で確認してください。**")
    nm = names.get(sid) or sid
    return ("PASS", f"{nm}（{sid}）", f"カート保持者は第三者（{nm}）です。")


def velocity_of(product: dict, shared_ranks: dict[int, int] | None = None
                ) -> tuple[str, str, int | None, int | None]:
    """(判定, 理由, monthlySold, 現在ランク)。積極条件＝「売れている根拠」。

    🔴 **同じランク値を複数の ASIN が持っていたら、そのランクはバリエーション family の
    共有値です。**その場合ランクは「この ASIN が売れている」根拠になりません
    （memory: `knowledge_keepa_dropcount_is_polling`「兄弟ASINはランク共有＝死んだ子も
    兄弟の売上でランクが付く」）。2026-10-04、DNライティングの蛍光灯で
    **8 ASIN が 223,802位／239,411位／278,883位 を共有**していました。
    `shared_ranks` は {ランク値: その値を持つ ASIN 数}。
    """
    s = product.get("stats") or {}
    cur = s.get("current") or []
    rank = cur[3] if len(cur) > 3 and cur[3] and cur[3] > 0 else None
    ms = product.get("monthlySold")
    ms = int(ms) if isinstance(ms, int) and ms > 0 else None
    if ms:
        return ("PASS", f"過去1ヶ月に {ms}個 売れています（Keepa monthlySold）。", ms, rank)
    n_share = (shared_ranks or {}).get(rank or -1, 1)
    if n_share > 1 and rank and rank > RANK_OK:
        # 共有ランクでも、**その値そのものが遅い**なら family 全体が売れていません。
        # 兄弟の誰かが売れていればランクは上がるので、605,794位 の共有ランクは
        # 「この子が売れていないかもしれない」ではなく「**一族が売れていない**」。
        return ("FAIL",
                f"売れ筋ランク {rank:,}位 を他の {n_share - 1} ASIN と共有していますが、"
                f"**その共有ランク自体が {RANK_OK:,}位より下**です。"
                f"兄弟の誰かが売れていればランクは上がるので、**一族ごと売れていません。**",
                None, rank)
    if n_share > 1:
        return ("UNKNOWN",
                f"売れ筋ランク {rank:,}位 を**他の {n_share - 1} ASIN と共有**しています"
                f"＝バリエーションの family 共有ランクです。**この ASIN が売れている根拠に"
                f"なりません**（兄弟の売上でもランクは付く）。販売数の表示も無いので、"
                f"キーゾンで3か月の実数を人が見てください。", None, rank)
    if rank and rank <= RANK_OK:
        return ("PASS", f"販売数の表示はありません（月50個未満）が、売れ筋ランク {rank:,}位 "
                        f"＝ {RANK_OK:,}位以内で、他 ASIN と共有していません。"
                        f"**根拠はランクだけ（弱）**で、実数はキーゾンで人が見てください。",
                None, rank)
    if rank:
        return ("FAIL", f"販売数の表示がなく、売れ筋ランクも {rank:,}位（{RANK_OK:,}位より下）"
                        f"です。**売れている根拠がありません。**", None, rank)
    return ("UNKNOWN", "販売数もランクも取れていません。", None, None)


def build(row: dict, cand: dict, product: dict, idx: dict, names: dict,
          idx_day: str, now: datetime | None = None,
          shared_ranks: dict | None = None) -> dict:
    """1行ぶんの採点。`gates` に (名前, 判定, 理由) を順に積む。"""
    asin = row["ASIN"]
    g: list[tuple[str, str, str]] = []

    if not product:
        return {"asin": asin, "row": row, "gates": [("取り直し", "UNKNOWN",
                "今日の値を取り直せていません（Keepa の残トークン待ち）。")],
                "判定": "UNKNOWN", "等級": "UNKNOWN"}

    # ── 価格履歴（採算の土台）
    lv = PH.from_product(product, screen_price=SCREEN_PRICES.get(asin), now=now)
    if lv.verdict in ("下落トレンド",):
        g.append(("価格の動き", "FAIL", lv.note))
    elif lv.verdict in ("振れ幅が大きい", "判定不能"):
        g.append(("価格の動き", "UNKNOWN", lv.note))
    else:
        g.append(("価格の動き", "PASS", lv.note))

    # ── カート保持者
    cart_st, cart_who, cart_why = cart_of(product, names)
    g.append(("カート保持者", cart_st, cart_why))

    # ── 実売（積極条件）
    vel_st, vel_why, ms, rank = velocity_of(product, shared_ranks)
    g.append(("実売", vel_st, vel_why))

    # ── 季節
    season = seasonality.from_product(product, now=now)

    # ── 仕入れ（在庫と鮮度）
    ni = idx.get(row.get("JAN") or "") or {}
    stock = ni.get("stock")
    if stock == "品切れ":
        g.append(("仕入れ", "FAIL", "NETSEA の索引で**品切れ**です（買えません）。"))
    elif stock == "在庫あり":
        age = (TODAY - date.fromisoformat(idx_day)).days
        g.append(("仕入れ", "PASS", f"NETSEA で在庫あり（索引の取得日 {idx_day}・{age}日前）。"
                                    f"**発注直前に卸値を引き直してください。**"))
    else:
        g.append(("仕入れ", "UNKNOWN", "卸の在庫が索引で確認できません（SD 由来の行など）。"))

    # ── セット数（単位ずれは真偽）
    n_set, conf, src = set_count_of(row, product)
    # 確度が「確定/単独」でも**数が入っていなければ確定していません**（2026-10-04 に
    # 台帳の確度だけを見て None を int() に渡して落ちました）。両方そろって初めて確定。
    decided = conf in ("確定", "単独") and bool(n_set)
    if not decided:
        g.append(("セット数", "UNKNOWN",
                  f"Amazon の1個が卸の何点かが決まりません（{conf}）。{src}"))
    else:
        g.append(("セット数", "PASS", f"Amazon 1個 ＝ 卸 {int(n_set)}点（{conf}・{src}）"))

    # ── 採算
    sell = lv.sell_for_profit
    sell_bad = lv.sell_pessimistic
    # 🔴 **原価は「卸の1点あたり × セット数」からだけ作る**（CLAUDE.md §3.3-17）。
    #    当社はこの単位ずれで赤字を黒字と誤認したことが3回ある。Amazon 1個あたりの原価だけを
    #    受け取ると、それが「卸1点ぶん」なのか「セットぶん」なのか**後から検算できない**。
    #    卸の1点あたりの値段が無い行は、原価があっても採算を計算しない（＝候補に出さない）。
    per_pt = _num(row.get("卸の1点あたり原価(税込)"))
    per_pt_src = "台帳"
    if not per_pt and ni.get("unit_price_excl"):
        per_pt = float(ni["unit_price_excl"]) * 1.1
        per_pt_src = f"索引（取得日 {idx_day}）"
    if not per_pt:
        per_pt_src = ""
    min_lot = _num(row.get("卸の最小ロット(点)")) or _num(ni.get("min_lot_units"))
    ledger_unit = _num(row.get("Amazon1個あたり原価(税込)"))
    unit_cost, unit_note = None, ""
    if per_pt and n_set:
        unit_cost = per_pt * n_set
        # 台帳の Amazon1個あたり原価と食い違うなら、**どちらが正しいか決めずに計算を止める**。
        # 黙ってどちらかを採ると、辻褄だけ合って嘘が一段深くなる。
        if ledger_unit and abs(ledger_unit - unit_cost) > 1.5:
            unit_note = (f"台帳の Amazon1個あたり原価 {ledger_unit:,.0f}円 と、"
                         f"卸の1点 {per_pt:,.0f}円 × セット数 {n_set:g} = {unit_cost:,.0f}円 が"
                         f"食い違います。**単位ずれは「幅」ではなく「真偽」です。**")
            unit_cost = None
    elif ledger_unit:
        unit_note = ("Amazon1個あたりの原価はありますが、**卸の1点あたりの値段が無く"
                     "「Amazon 1個 ＝ 卸 何点」の検算ができません**（§3.3-17）。"
                     "単位の出どころが無い原価は使いません。")
    qty = int(_num(row.get("発注点数(Amazon何個)")) or 0) or 10
    fba_yen = (product.get("fbaFees") or {}).get("pickAndPackFee") or cand.get("fba_yen")
    fee_pct = product.get("referralFeePercentage") or cand.get("fee_pct")
    cat = category_of(product)

    e = None
    if not (sell and unit_cost and fba_yen and decided):
        miss = [n for n, v in (("売価", sell), ("原価", unit_cost),
                               ("FBA配送代行", fba_yen), ("セット数", decided)) if not v]
        g.append(("採算", "UNKNOWN",
                  f"計算しません（{' / '.join(miss)} が決まっていない）。"
                  f"**金額を膨らませず UNKNOWN にします。**"
                  + (f" {unit_note}" if unit_note else "")))
    else:
        months = _num(row.get("売り切る月数"))
        ms_for_qty = ms or (int(round(qty / months)) if months else None)
        e = profit.compute(sell, fee_pct, fba_yen, unit_cost, qty,
                           monthly_sold=ms_for_qty, category=cat, unit_decided=True)
        # 悲観側の売価（90日の下位25%）を効かせて等級を引き直す。
        gr = fba_cost.grade(sell, unit_cost, e.size_tier, category=cat, keepa_pct=fee_pct,
                            months_to_sell=e.months_to_sell or 3.0,
                            unit_decided=True, sell_worst=sell_bad)
        e.grade, e.grade_reason = gr.grade, gr.reason
        e.worst_net_per_unit = gr.worst.get("手残り")
        e.worst_margin_pct = gr.worst.get("利益率(%)")

        if e.cost_ratio_pct < MIN_PLAUSIBLE_COST_RATIO:
            g.append(("採算", "UNKNOWN",
                      f"卸率が売価の {e.cost_ratio_pct}% しかありません。"
                      f"**単位ずれ・終売・仕入れ不存在のサイン**で、人が両方の画面を"
                      f"見るまで候補にしません。{e.grade_reason}"))
        elif e.grade == "C":
            g.append(("採算", "FAIL", e.grade_reason))
        elif e.order_total > MAX_ORDER_TOTAL_YEN:
            g.append(("採算", "FAIL",
                      f"発注額 {e.order_total:,}円 が残枠 {MAX_ORDER_TOTAL_YEN:,}円 を"
                      f"超えます。{e.grade_reason}"))
        elif e.grade not in ("A", "B"):
            # 🔴 等級が UNKNOWN（寸法が取れずサイズ区分が決まらない等）の行を PASS に
            #    していた（2026-10-09 サトル報告・43件中6件）。**判定できないものを可にしない。**
            g.append(("採算", "UNKNOWN",
                      f"等級が {e.grade} です。サイズ区分や単位が決まらないと固定費が"
                      f"222円〜1,756円まで動くので、**推測で埋めません。**{e.grade_reason}"))
        else:
            g.append(("採算", "PASS", f"【等級 {e.grade}】{e.grade_reason}"))

    # ── カレンダーと季節の窓
    channel = "NETSEA" if ni else "スーパーデリバリー"
    gate_needed = (row.get("ゲート種別") or "未確認") != "不要"
    plan = SC.build(TODAY, channel=channel, gate_needed=gate_needed,
                    months_to_sell=(e.months_to_sell if e else None) or 3.0,
                    peak_months=season.peak_months, season_verdict=season.verdict)
    if plan.season_window == SC.MISSED:
        g.append(("季節の窓", "FAIL", plan.season_note))
    elif plan.season_window == SC.EDGE:
        g.append(("季節の窓", "UNKNOWN", plan.season_note))
    else:
        g.append(("季節の窓", "PASS", plan.season_note))

    sts = [s for _, s, _ in g]
    verdict = "NO-GO" if "FAIL" in sts else ("UNKNOWN" if "UNKNOWN" in sts else "GO")
    pinned = ""
    if asin in SCREEN_CHECKED_NO_GO:
        verdict, pinned = "NO-GO", "人が実画面で確認して NO-GO にした行（機械で上書きしない）"

    return {"asin": asin, "row": row, "product": product, "price": lv, "season": season,
            "plan": plan, "econ": e, "gates": g, "判定": verdict,
            "等級": e.grade if e else "UNKNOWN", "カート保持者": cart_who,
            "monthlySold": ms, "rank": rank,
            "rank_shared": (shared_ranks or {}).get(rank or -1, 1),
            "n_set": n_set, "セット数の確度": conf,
            # 単位ずれの検算に要る値。**full=True のCSV（agent_output）にだけ書く。**
            "per_pt": per_pt, "per_pt_src": per_pt_src, "min_lot": min_lot,
            "category": cat, "idx_day": idx_day,
            "pinned": pinned, "在庫": stock or "索引なし", "channel": channel,
            "手残り合計": (e.net_per_unit * e.qty) if e else None}


# ── 全件 ─────────────────────────────────────────────────────────────────


def score_all(now: datetime | None = None) -> list[dict]:
    rows, cands, idx, names, fresh, idx_day = load_all()
    # 同じランク値を持つ ASIN を数える（family 共有ランクの検出。§velocity_of 参照）。
    rc: Counter = Counter()
    for p in fresh.values():
        cur = (p.get("stats") or {}).get("current") or []
        if len(cur) > 3 and cur[3] and cur[3] > 0:
            rc[cur[3]] += 1
    return [build(r, cands.get(r["ASIN"]) or {}, fresh.get(r["ASIN"]) or {},
                  idx, names, idx_day, now, dict(rc)) for r in rows]


def first_fail(sc: dict) -> str:
    """最初に落とした（または決まらなかった）ゲートの名前。内訳の集計に使う。"""
    for name, st, _ in sc["gates"]:
        if st == "FAIL":
            return f"{name}（FAIL）"
    for name, st, _ in sc["gates"]:
        if st == "UNKNOWN":
            return f"{name}（UNKNOWN）"
    return "—"


REQUIRED_GATES = ("価格の動き", "カート保持者", "実売", "仕入れ", "セット数",
                  "採算", "季節の窓")


def gate_status(s: dict, name: str) -> str:
    for n, st, _ in s["gates"]:
        if n == name:
            return st
    return "PASS"

# 🔴 **人が実画面を見れば決まるゲート。**ここが UNKNOWN の行は「落とす」のではなく
# 「**人の確認待ち**」です。機械判定の GO は「買ってよい」ではなく
# 「**人が実画面で見る価値がある**」の意味（CLAUDE.md §3.3-16）なので、
# 候補リストの目的からすると**この行こそ渡すべき**ものです。
#
# 2026-10-04 の実測：プールの `monthlySold` が取れるのは2%、ランクは194件が兄弟 ASIN と
# 共有＝ASIN単位の根拠にならない。**つまり実売は機械では決まりません。**
# 閾値をどこに置いても候補は2件のままで、**緩める/締めるの問題ではありません**。
SCREEN_RESOLVABLE = ("実売",)


def candidates(scored: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """(機械判定 GO, 人の確認待ち) を手残りの大きい順で返す。

    「人の確認待ち」＝ **実売以外のすべてのゲートを通っていて、実売だけが UNKNOWN** の行。
    `monthlySold` が非表示でランクが兄弟共有だと機械ではこれ以上進めないので、
    キーゾンで3か月の実数を人が見る1手で GO/NO-GO が決まります。
    """
    def key(s):
        return -(s["手残り合計"] or 0)

    go = [s for s in scored if s["判定"] == "GO" and s["等級"] in ("A", "B")]
    pend = [s for s in scored
            if s["判定"] == "UNKNOWN" and s["等級"] in ("A", "B")
            and all(gate_status(s, g) == "PASS"
                    for g in REQUIRED_GATES if g not in SCREEN_RESOLVABLE)
            and all(gate_status(s, g) == "UNKNOWN" for g in SCREEN_RESOLVABLE)]
    kept, over = split_by_family(sorted(pend, key=key))
    return sorted(go, key=key), kept, over


# 同じブランド×購入元の行を、1リストにこれ以上入れない。
MAX_PER_FAMILY = 4


def split_by_family(rows: list[dict], cap: int = MAX_PER_FAMILY
                    ) -> tuple[list[dict], dict[tuple, list[dict]]]:
    """(上限まで残した行, 溢れた行をブランド×購入元でまとめたもの) を返す。

    🔴 **溢れた行は「落ちた行」ではありません。**
    2026-10-04 の実測で、候補26件のうち **18件が DNライティングの直管蛍光灯1本**でした
    （仕入れ先も1社）。しかもこの18件は**売れ筋ランクを共有しています**。

    → つまり **1件キーゾンで見れば18件まとめて決まります。**
    人の30手を同じ棚に18回使わせるのは無駄なので、代表を `cap` 件だけ上のリストに出し、
    残りは「同じ1手で決まる兄弟」として別表に出します。
    """
    seen: Counter = Counter()
    kept: list[dict] = []
    over: dict[tuple, list[dict]] = {}
    for s in rows:
        k = (s["row"].get("ブランド") or "", s["row"].get("購入元の名前") or "")
        if seen[k] >= cap:
            over.setdefault(k, []).append(s)
            continue
        seen[k] += 1
        kept.append(s)
    return kept, over


def cap_per_family(rows: list[dict], cap: int = MAX_PER_FAMILY) -> list[dict]:
    """🔴 **同じブランド×購入元の行でリストを埋めない。**

    2026-10-04、上位30件のうち25件が「DNライティング の直管蛍光灯・仕入れ先は
    ヤザワコーポレーション1社・カート保持者も同一」になりました。これは
    **人が実画面で見る30手のうち25手を、ほぼ同じ1つの棚に使わせる**ことで、
    発注案の分散（社長要求）も作れません。上位 `cap` 件だけ残し、残りは切ります
    （切った行は消えたのではなく、**同じ判定の兄弟がリストに載っている**という意味です）。
    """
    seen: Counter = Counter()
    out: list[dict] = []
    for s in rows:
        k = (s["row"].get("ブランド") or "", s["row"].get("購入元の名前") or "")
        if seen[k] >= cap:
            continue
        seen[k] += 1
        out.append(s)
    return out


def relax_table(scored: list[dict]) -> list[str]:
    """🔴 「条件をこう緩めればN件増える」を**数字で**出す（CLAUDE.md §3.1）。

    1ゲートだけを無視したときの件数（leave-one-out）を出します。これが
    「どの条件が候補をゼロにしているか」の答えで、**原価や売価を積み直す前に見る表**です
    （§3.3-21）。
    """
    live = [s for s in scored if s.get("product")]
    full = [s for s in live
            if all(gate_status(s, n) == "PASS" for n in REQUIRED_GATES)]
    out = [f"今日の値で取り直せた {len(live)}件のうち、全ゲート PASS は {len(full)}件。",
           "",
           "| 無視する条件 | 候補数 | その条件だけで落ちている件数 |",
           "|---|---:|---:|"]
    for n in REQUIRED_GATES:
        k = [s for s in live
             if all(gate_status(s, m) == "PASS" for m in REQUIRED_GATES if m != n)]
        out.append(f"| {n} | {len(k)}件 | {len(k) - len(full)}件 |")

    n_shared = sum(1 for s in live if s.get("rank_shared", 1) > 1)
    out += ["",
            f"**実売（ランクの上限）を動かしたとき**（他の条件はそのまま／"
            f"**兄弟 ASIN とランクを共有している {n_shared}件は、どの上限でも"
            f"根拠として数えません**）", "",
            "| ランク上限 | 候補数 | 想定手残り合計 |", "|---|---:|---:|"]
    base = [s for s in live
            if all(gate_status(s, m) == "PASS" for m in REQUIRED_GATES if m != "実売")]
    # ⚠️ ここは**実際のゲートと同じ規則**で数えます（`velocity_of` と同じ）。
    # 共有ランクを根拠として数えると、感度表だけが甘く出て人を誤解させます
    # （2026-10-04 に一度「30万位で17件」と出したが、実際の判定は2件だった）。
    for lim in (100_000, 150_000, 200_000, 300_000, 500_000):
        k = [s for s in base
             if s.get("monthlySold")
             or (s.get("rank") and s["rank"] <= lim
                 and s.get("rank_shared", 1) <= 1)]
        tot = sum(x["手残り合計"] or 0 for x in k)
        mark = " ←いまここ" if lim == RANK_OK else ""
        out.append(f"| {lim:,}位以内 | {len(k)}件 | {tot:,}円{mark} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asin")
    ap.add_argument("--relax", action="store_true")
    a = ap.parse_args(argv)

    scored = score_all()
    if a.relax:
        print("\n".join(relax_table(scored)))
        return 0
    if a.asin:
        for s in scored:
            if s["asin"] != a.asin:
                continue
            print(f"=== {a.asin} / {s['row']['商品名'][:60]}")
            lv = s.get("price")
            if lv:
                print(f"価格: 現在 {lv.current}・90日中央 {lv.median90}・下位25% {lv.p25_90}"
                      f"・{lv.verdict}（{lv.source}）")
            print(f"カート: {s.get('カート保持者')}　実売: monthlySold={s.get('monthlySold')}"
                  f" rank={s.get('rank')}")
            if s.get("season"):
                print(f"季節: {s['season'].verdict} peak={s['season'].peak_months}")
            if s.get("plan"):
                print(f"カレンダー: {s['plan'].as_row()}")
            if s.get("econ"):
                e = s["econ"]
                print(f"採算: 区分{e.size_tier} 手残り{e.net_per_unit}円/個 "
                      f"{e.net_margin_pct}% 悲観{e.worst_net_per_unit}円 "
                      f"{e.worst_margin_pct}% 等級{e.grade} 発注{e.qty}個 {e.order_total:,}円")
            for n, st, why in s["gates"]:
                print(f"  [{st:7s}] {n}: {why}")
            print(f"→ 判定 {s['判定']}")
            return 0
        print(f"{a.asin} は台帳にありません。")
        return 1

    done = sum(1 for s in scored if s.get("product"))
    print(f"台帳 {len(scored)}件 / 今日の値で取り直せた {done}件")
    print("\n── 総合判定")
    for k, c in Counter(s["判定"] for s in scored).most_common():
        print(f"   {k:8s} {c:4d}件")
    print("\n── 等級（採算だけ）")
    for k in ("A", "B", "C", "UNKNOWN"):
        print(f"   {k:8s} {sum(1 for s in scored if s['等級'] == k):4d}件")
    print("\n── 🔴 どのゲートで何件落ちたか（最初の非PASS・§3.3-21）")
    for k, c in Counter(first_fail(s) for s in scored if s["判定"] != "GO").most_common():
        print(f"   {k:22s} {c:4d}件")
    print("\n── ゲート別の内訳（全件・重複あり）")
    for name in ("価格の動き", "カート保持者", "実売", "仕入れ", "セット数", "採算", "季節の窓"):
        c = Counter(st for s in scored for n, st, _ in s["gates"] if n == name)
        print(f"   {name:10s} PASS {c['PASS']:4d} / UNKNOWN {c['UNKNOWN']:4d} / "
              f"FAIL {c['FAIL']:4d}")

    go, pend, over = candidates(scored)
    cands = (go + pend)[:TOP_N]
    print(f"\n🔴 人が実画面で見る価値のある候補: {len(go) + len(pend)}件")
    print(f"   うち機械判定 GO（実売の根拠もある）      {len(go):4d}件")
    print(f"   うち実売だけ人の確認待ち（キーゾン1手）  {len(pend):4d}件")
    if over:
        n = sum(len(v) for v in over.values())
        print(f"   ＋ 同じブランド×購入元の兄弟（代表1件を見れば決まる） {n:4d}件")
        for (b, sup), v in sorted(over.items(), key=lambda kv: -len(kv[1])):
            print(f"      {b} / {sup}: 他 {len(v)}件")

    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(cands[:TOP_N], OUT / "top30.csv")
    write_csv(scored, OUT / "all.csv", full=True)
    json.dump({"総数": len(scored), "取り直し済み": done,
               "判定": dict(Counter(s["判定"] for s in scored)),
               "等級": dict(Counter(s["等級"] for s in scored)),
               "落ちた内訳": dict(Counter(first_fail(s) for s in scored
                                       if s["判定"] != "GO")),
               "候補": len(cands)},
              (OUT / "summary.json").open("w"), ensure_ascii=False, indent=1)
    print(f"書き出し: {OUT}")
    run_consistency(OUT / "all.csv", OUT / "consistency_report.json")
    return 0


def run_consistency(csv_path: Path, report_path: Path) -> None:
    """候補表を書いたら、**その場で整合性検査に通して是正する**（CLAUDE.md §3.3-17）。

    「候補表は必ず検算済み」にするための締めの一手（2026-10-09 カズヨ判断で常設化）。
    崩れている行は数字を直さず**採算欄を空にして NG の印を立てる**。捨てた値は
    `consistency_report.json` に原本ごと残るので、何を落としたかは後から読めます。

    検査が落ちても候補表の書き出し自体は成功扱いにします（表はもう書けている）。
    ただし**何行を空にしたかは必ず画面に出す**。黙って直すのが一番まずい。
    """
    gate_dir = REPO / "scripts/sourcing_gate"
    if not (gate_dir / "consistency.py").exists():
        print(f"⚠️ 整合性検査が見つかりません（{gate_dir}）。**検算していない表です。**")
        return
    cmd = [sys.executable, str(gate_dir / "consistency.py"), "fix", str(csv_path),
           "--out", str(csv_path), "--report", str(report_path)]
    print("\n── 整合性検査（§3.3-17）" + "─" * 46)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.rstrip() or r.stderr.rstrip())
    # 2回目を走らせて 0行（収束）を確認する。ここが崩れると是正が暴れている合図。
    r2 = subprocess.run(cmd[:-2] + ["--out", str(csv_path)], capture_output=True, text=True)
    if "書き換えた行: 0行" not in r2.stdout:
        print("🔴 2回目の是正が0行になりません。consistency.py の収束が壊れています "
              "（§3.3-17）。表の採算欄を信用しないでください。")
    else:
        print("検算: 2回目は0行（収束を確認）")


COLS = ["ASIN", "商品名", "ブランド", "AmazonURL", "判定", "等級",
        "過去1ヶ月の販売数", "セラー数", "Amazon本体の有無", "カートの販売元",
        "売れ筋ランク", "販売価格(90日中央値)", "販売価格(180日中央値)",
        "保守値(90日の下位25%)", "上位25%", "現在価格", "現在価格÷90日中央値",
        # 🔴 **採算をどの売価で計算したかを必ず渡す。**列名に「90日中央値」と書いてあるのに
        #    実画面で見た価格で計算していると、読む人も検査も食い違いを誤解する
        #    （§3.3-19「2つのデータ源をつなぐ口は、単位を渡させる設計にする」）。
        "採算の基準売価", "基準売価の出どころ",
        "価格の振れ幅", "価格の傾き(%/30日)", "価格の判定", "価格の出どころ",
        "サイズ区分", "販売手数料", "FBA配送代行", "その他固定費",
        "Amazon1個あたり原価(税込)", "Amazon側のセット数(Amazon1個=卸何点か)",
        "セット数の確度", "1個手残り", "利益率(%)", "悲観の手残り", "悲観の利益率(%)",
        "発注点数(Amazon何個)", "発注額(円・税込)", "手残り合計", "売り切る月数",
        "半値処分の損失", "発注日", "着荷の見込み", "FBA納品完了の見込み", "販売開始日",
        "売り切り目標月", "季節の窓", "季節(ランク12ヶ月履歴)", "発注→販売開始",
        "卸の在庫", "卸値の鮮度", "購入元の名前", "ゲート種別", "判定理由"]


#: `full=True` のときだけ足す列。**会員限定の取引条件と Keepa のカテゴリーを含む。**
#: 置き場は `workspace/output/agent_output/`（.gitignore 済み）だけ。
#: このリポジトリは PUBLIC なので、**追跡されるCSVには絶対に足さないこと**（CLAUDE.md §6）。
COLS_PRIVATE = ["卸の1点あたり原価(税込)", "卸の1点の出どころ", "卸の最小ロット(点)",
                "カテゴリー", "索引の取得日"]


def write_csv(scored: list[dict], path: Path, full: bool = False) -> None:
    """`full=True` で単位ずれの検算に要る列（卸の1点あたり・最小発注数・カテゴリー）も書く。

    ★ 以前は `full` を受け取るだけで**使っていなかった**ので、全件CSVにも卸の1点あたりの
      値段が載らず、`consistency.py` の単位ずれ検査が 648行中12行にしか効いていなかった
      （2026-10-09 実測）。「値が無いから検査できない」を作らないために、ここで必ず書く。
    """
    cols = COLS + COLS_PRIVATE if full else COLS
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for s in scored:
            w.writerow(as_row(s, full=full))


def as_row(s: dict, full: bool = False) -> dict:
    r, lv, e, pl = s["row"], s.get("price"), s.get("econ"), s.get("plan")
    out = {
        "ASIN": s["asin"], "商品名": r["商品名"][:70], "ブランド": r.get("ブランド"),
        "AmazonURL": r.get("AmazonURL"), "判定": s["判定"], "等級": s["等級"],
        "過去1ヶ月の販売数": (f"{s['monthlySold']}個" if s.get("monthlySold")
                              else "表示なし（月50個未満）"),
        "セラー数": r.get("セラー数"), "Amazon本体の有無": r.get("Amazon本体の有無"),
        "カートの販売元": s.get("カート保持者"),
        "売れ筋ランク": (f"{s['rank']:,}位" if s.get("rank") else "未取得"),
        "Amazon側のセット数(Amazon1個=卸何点か)": (int(s["n_set"]) if s.get("n_set") else ""),
        "セット数の確度": s.get("セット数の確度"),
        "季節(ランク12ヶ月履歴)": (s["season"].verdict if s.get("season") else ""),
        "卸の在庫": s.get("在庫"), "購入元の名前": r.get("購入元の名前"),
        "ゲート種別": r.get("ゲート種別"),
        "判定理由": " ／ ".join(f"{n}. {why}" for n, st, why in s["gates"]
                               if st != "PASS")[:900] or "全ゲート PASS",
    }
    if lv:
        # ⚠️ 価格が1つも取れていない行に「現在価格」と書かない。**出どころを偽らない。**
        #    （2026-10-09：146行が「現在価格」と表示されたが、現在価格すら空の行だった）
        if not lv.sell_for_profit:
            basis_src = "価格が取れていない（採算を計算しない）"
        elif lv.screen_price:
            basis_src = "実画面（人が見た価格・機械で上書きしない）"
        elif lv.median90:
            basis_src = "90日中央値"
        elif lv.median180:
            basis_src = "180日中央値"
        else:
            # ここに来たら 90日/180日の中央値が無く現在価格しか無い＝§3.3-28 違反。
            # 生成側では止めず、宣言だけして consistency.py に落としてもらう
            # （「宣言する側」と「止める側」を分ける。両方で止めると理由が二重になる）。
            basis_src = "現在価格"
        out.update({
            "採算の基準売価": lv.sell_for_profit, "基準売価の出どころ": basis_src,
            "販売価格(90日中央値)": lv.median90, "販売価格(180日中央値)": lv.median180,
            "保守値(90日の下位25%)": lv.p25_90, "上位25%": lv.p75_90,
            "現在価格": lv.current, "現在価格÷90日中央値": lv.current_over_median,
            "価格の振れ幅": lv.spread, "価格の傾き(%/30日)": lv.slope_pct_per_30d,
            "価格の判定": lv.verdict, "価格の出どころ": lv.source,
        })
    # 🔴 **等級が UNKNOWN の行には金額を書かない**（2026-10-09）。
    #    等級 UNKNOWN ＝ サイズ区分や単位が決まらず採算を判定できない行。それでも
    #    `profit.compute` は数字を返すので、素朴に書くと「判定できなかった行」が
    #    利益率つきで表に並ぶ。**印を付けることと、数字を出さないことは別**
    #    （2026-09-07 の事故：印だけ付けて数字を出し、まぼろしの利益率が上位を独占した）。
    #    等級 C は「計算できた上での不合格」なので数字を残す。
    if e and s.get("等級") in ("A", "B", "C"):
        out.update({
            "サイズ区分": e.size_tier, "販売手数料": e.referral_fee_yen,
            "FBA配送代行": e.fba_yen, "その他固定費": e.other_unit_costs,
            "Amazon1個あたり原価(税込)": e.unit_cost_incl,
            "1個手残り": e.net_per_unit, "利益率(%)": e.net_margin_pct,
            "悲観の手残り": e.worst_net_per_unit, "悲観の利益率(%)": e.worst_margin_pct,
            "発注点数(Amazon何個)": e.qty, "発注額(円・税込)": e.order_total,
            "手残り合計": s.get("手残り合計"),
            # 🔴 月販が取れていない行は「3ヶ月」と**書かない**。仮置きだと明示する
            #    （`schedule` と保管料の計算では 3.0 を使っているが、それは前提であって
            #     観測値ではない。列に数字だけ出すと観測値に見える）。
            "売り切る月数": (f"{e.months_to_sell}ヶ月" if e.months_to_sell
                             else "未確定（月販非表示・3ヶ月で仮置き）"),
            "半値処分の損失": e.half_disposal_loss,
        })
    if pl:
        out.update(pl.as_row())
        out["卸値の鮮度"] = pl.as_row().get("カレンダーの前提", "")
    if full:
        # 単位ずれの検算（Amazon1個あたり原価 ＝ 卸の1点 × セット数）に要る値。
        # 無い行は空にする＝`consistency.py` が「対象外」ではなく**原価そのものが空**になる。
        out.update({
            "卸の1点あたり原価(税込)": (round(s["per_pt"], 1) if s.get("per_pt") else ""),
            "卸の1点の出どころ": s.get("per_pt_src") or "",
            "卸の最小ロット(点)": (int(s["min_lot"]) if s.get("min_lot") else ""),
            "カテゴリー": s.get("category") or "",
            "索引の取得日": s.get("idx_day") or "",
        })
    return out


if __name__ == "__main__":
    raise SystemExit(main())
