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
- 予算は総額5万円（送料込み・社長決定 2026-09-04）
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
BF_DIR = REPO / "workspace/output/deliverables/T-20260904-004"
SUPPLIERS_CSV = REPO / "workspace/output/deliverables/T-20260831-006/out/suppliers.csv"
OUT = HERE / "out"

# ── 社長決定（2026-09-04）。触るのはここだけ ────────────────────────────
TOTAL_BUDGET_YEN = 50_000
# 在庫を何ヶ月分まで持つか。これを超える買い方は「積み増し」ではやらない。
# 最小発注数が既にこれを超えている SKU は、超えたまま候補に残して警告を出す
# （落とすと候補が消えるだけで、判断材料にならない）。
STOCK_MONTHS_CAP = 6.0
PREF = "東京都"


# ── 入力 ───────────────────────────────────────────────────────────────
def load_pool(path: Path) -> list[dict]:
    """供給が生きていると確認できた ASIN だけを返す。"""
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["供給ステータス"] == "現行"]


def load_facts(asins: set[str]) -> dict[str, dict]:
    with open(SCAN_CSV, encoding="utf-8-sig") as f:
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
def build_sku(pool_row: dict, fact: dict) -> dict:
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
    }


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


def topup(lines: list[dict], skus: dict, tariffs: dict, sup_ids: dict) -> list[dict]:
    """予算の余りを、回転が速い SKU から順に積み増す。

    積む条件は2つだけ。
      1. 在庫が STOCK_MONTHS_CAP ヶ月分を超えない（最小発注数で既に超えている SKU は積まない）
      2. 総額が予算を超えない
    送料無料ラインをまたげるなら、そのぶん実質の単価が下がるので優先する。
    """
    lines = [dict(l) for l in lines]
    for _ in range(400):
        best, best_gain = None, 0.0
        for i, ln in enumerate(lines):
            sku = skus[ln["ASIN"]]
            if not sku["月販見込"]:
                continue
            nxt = ln["口数"] + sku["入数"]
            months = (nxt // sku["入数"]) / sku["月販見込"]
            if months > STOCK_MONTHS_CAP:
                continue
            trial = list(lines)
            trial[i] = order_line(sku, nxt)
            priced = price_set(trial, tariffs, sup_ids)
            if priced["総額"] > TOTAL_BUDGET_YEN:
                continue
            # 1円あたりどれだけ手残りが増えるか。送料の段が下がる手はここで自然に勝つ。
            base = price_set(lines, tariffs, sup_ids)
            spend = priced["総額"] - base["総額"]
            gain = (priced["手残り"] - base["手残り"]) / spend if spend > 0 else 999
            if gain > best_gain:
                best, best_gain = (i, trial[i]), gain
        if best is None:
            break
        lines[best[0]] = best[1]
    return lines


def enumerate_sets(skus: dict, tariffs: dict, sup_ids: dict) -> list[dict]:
    """全部の組み合わせを最小発注数で試し、予算に入るものだけ残して積み増す。

    SKU が十数件の世界なので総当たりで十分（YAGNI）。50件を超えたら考え直す。
    """
    keys = list(skus)
    out = []
    for n in range(1, len(keys) + 1):
        for combo in itertools.combinations(keys, n):
            base = [order_line(skus[k], skus[k]["最小口数"]) for k in combo]
            priced = price_set(base, tariffs, sup_ids)
            if priced["総額"] > TOTAL_BUDGET_YEN:
                continue
            out.append(price_set(topup(base, skus, tariffs, sup_ids), tariffs, sup_ids))
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
        parts.append(f"1社（{top}）に全額。この社の取引が止まる／出荷が遅れると"
                     f"{s['SKU数']}SKU が同時に死ぬ")
    elif n_top > 1:
        parts.append(f"{top} に {n_top}SKU・仕入額の{share:.0%}。"
                     f"この社が止まると同時に{n_top}SKU 失う（残り{s['SKU数'] - n_top}SKU は生きる）")
    else:
        parts.append(f"1社1SKU に分散済み。1社止まっても失うのは1SKU（最大{share:.0%}）")

    if s["SKU数"] == 1:
        parts.append("SKU が1本しかないので、出品制限に当たった時点で在庫全部が動かせない")
    if s["最長回転月数"] and s["最長回転月数"] > STOCK_MONTHS_CAP:
        worst = max(s["明細"], key=lambda l: l["回転月数"] or 0)
        parts.append(f"最長 {worst['回転月数']:.0f}ヶ月分の在庫（{worst['商品名'][:18]}）。"
                     f"想定より売れなければ長期保管手数料が乗り、値下げ競争にも巻き込まれる")
    return " / ".join(parts)


# ── 出力 ───────────────────────────────────────────────────────────────
def pick_plans(sets: list[dict]) -> list[tuple[str, str, dict]]:
    """目的の違う案を並べる。1つに絞らない（決めるのは社長）。"""
    plans = []
    seen = set()

    def add(label, aim, s):
        key = tuple(sorted((l["ASIN"], l["口数"]) for l in s["明細"]))
        if key in seen:
            return
        seen.add(key)
        plans.append((label, aim, s))

    add("案A", "SKU 数を最大に（分散を優先）",
        max(sets, key=lambda s: (s["SKU数"], s["サプライヤー数"], s["手残り"])))
    add("案B", "手残りを最大に（送料を引いた後の粗利）",
        max(sets, key=lambda s: s["手残り"]))
    add("案C", "在庫を寝かせない（最長回転月数が最小）",
        min(sets, key=lambda s: (s["最長回転月数"], -s["手残り"])))
    onesup = [s for s in sets if s["サプライヤー数"] == 1 and s["SKU数"] >= 2]
    if onesup:
        add("案D", "1社集中（送料1回・その代わり全部が同じ社にぶら下がる）",
            max(onesup, key=lambda s: s["手残り"]))
    # 「1年以内に捌ける見込みの SKU だけ」で組めるか。最小発注数が回転を大きく
    # 超えている SKU が多いので、この条件を満たす案は少ない。無ければ出さない。
    fresh = [s for s in sets if s["SKU数"] >= 2 and s["最長回転月数"] <= 12]
    if fresh:
        add("案E", "1年で捌ける見込みの SKU だけを2本以上",
            max(fresh, key=lambda s: s["手残り"]))
    return plans


HTML_CSS = """
:root{color-scheme:light dark}
body{font-family:-apple-system,"Hiragino Sans",sans-serif;margin:0;padding:28px;
 line-height:1.7;max-width:1100px;margin-inline:auto}
h1{font-size:1.5rem;margin:0 0 4px} h2{font-size:1.15rem;margin:32px 0 8px;
 border-bottom:2px solid currentColor;padding-bottom:4px}
.lead{opacity:.75;margin:0 0 20px;font-size:.9rem}
table{border-collapse:collapse;width:100%;font-size:.84rem;margin:8px 0 4px}
th,td{border:1px solid rgba(128,128,128,.4);padding:6px 8px;text-align:left;vertical-align:top}
th{background:rgba(128,128,128,.14)} td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.sum td{background:rgba(128,128,128,.1);font-weight:600}
.wrap{overflow-x:auto}
.card{border:1px solid rgba(128,128,128,.4);border-radius:10px;padding:14px 18px;margin:16px 0}
.card h3{margin:0 0 2px;font-size:1.05rem}
.aim{opacity:.75;font-size:.85rem;margin:0 0 10px}
.kv{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:.85rem;margin-bottom:10px}
.kv b{font-variant-numeric:tabular-nums}
.wipe{background:rgba(200,90,60,.13);border-left:4px solid rgba(200,90,60,.8);
 padding:8px 12px;border-radius:0 6px 6px 0;font-size:.85rem}
.warn{background:rgba(220,170,40,.15);border-left:4px solid rgba(200,150,30,.9);
 padding:10px 14px;border-radius:0 6px 6px 0;margin:14px 0;font-size:.9rem}
.note{font-size:.82rem;opacity:.78}
"""


def h(x) -> str:
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def write_html(plans, skus, dropped):
    """社長がこの1枚だけ開けば発注できる状態にする。"""
    p = [f'<!doctype html><meta charset="utf-8"><title>初回発注セット</title>',
         f"<style>{HTML_CSS}</style>",
         "<h1>初回発注セット（T-20260909-002）</h1>",
         f'<p class="lead">予算 {TOTAL_BUDGET_YEN:,}円（送料込み）／送料は NETSEA <code>/tariffs</code> '
         f"の実額・届け先{PREF}／⛔ この資料は組んだだけで、発注はしていません（CLAUDE.md §4.1）</p>"]

    # 最初に「読む前に知っておくべき制約」を出す。あとで気づくと発注をやり直す羽目になる。
    slow = [s for s in skus.values()
            if s["月販見込"] and (s["最小口数"] // s["入数"]) / s["月販見込"] > 12]
    if slow:
        p.append('<div class="warn"><b>先に知っておいてください。</b>'
                 f"5件のうち {len(slow)}件は、<b>最小発注数がそのまま1年分を超える在庫</b>になります。"
                 "回転が遅いのではなく、卸のロットが小さく買わせてくれないだけです。"
                 "下の表の「回転月数」を必ず見てから案を選んでください。</div>")

    p.append("<h2>1. 使える SKU と、その最小ロット</h2>")
    p.append('<div class="wrap"><table><tr><th>ASIN</th><th>商品名</th><th>メーカー</th>'
             "<th>仕入先</th><th>入数</th><th>最小口数</th><th>＝出品数</th>"
             "<th>回転月数</th><th>ランク</th><th>出品者数</th></tr>")
    for s in skus.values():
        lst = s["最小口数"] // s["入数"]
        m = lst / s["月販見込"] if s["月販見込"] else None
        p.append(f'<tr><td>{h(s["ASIN"])}</td><td>{h(s["商品名"])}</td><td>{h(s["メーカー"])}</td>'
                 f'<td>{h(s["仕入先"])}</td><td class="n">{s["入数"]}</td>'
                 f'<td class="n">{s["最小口数"]}</td><td class="n">{lst}</td>'
                 f'<td class="n">{m:.1f}</td><td class="n">{s["ランク"]:,}</td>'
                 f'<td class="n">{s["出品者数"]}</td></tr>')
    p.append("</table></div>")
    p.append('<p class="note">回転月数 = 出品数 ÷（30日のランク下落観測数 ÷ (出品者数+1)）。'
             "ランク下落の観測数は販売数そのものではないので、桁を見る道具として扱ってください。</p>")

    p.append("<h2>2. 案の比較</h2>")
    p.append('<div class="wrap"><table><tr><th>案</th><th>ねらい</th><th>SKU</th><th>社数</th>'
             "<th>出品数</th><th>総額</th><th>うち送料</th><th>送料を引いた手残り</th>"
             "<th>最大1社シェア</th><th>最長回転月数</th></tr>")
    for lbl, aim, s in plans:
        p.append(f'<tr><td><b>{lbl}</b></td><td>{h(aim)}</td><td class="n">{s["SKU数"]}</td>'
                 f'<td class="n">{s["サプライヤー数"]}</td><td class="n">{s["出品数"]}</td>'
                 f'<td class="n">{s["総額"]:,}</td><td class="n">{s["送料"]:,}</td>'
                 f'<td class="n">{s["手残り"]:,}</td>'
                 f'<td class="n">{s["最大社シェア"]:.0%}</td>'
                 f'<td class="n">{s["最長回転月数"]:.1f}</td></tr>')
    p.append("</table></div>")

    p.append("<h2>3. 案ごとの中身と、全滅シナリオ</h2>")
    for lbl, aim, s in plans:
        p.append(f'<div class="card"><h3>{lbl}</h3><p class="aim">{h(aim)}</p>'
                 f'<div class="kv"><span>総額 <b>{s["総額"]:,}円</b></span>'
                 f'<span>送料 <b>{s["送料"]:,}円</b></span>'
                 f'<span>手残り <b>{s["手残り"]:,}円</b></span>'
                 f'<span>{s["SKU数"]}SKU / {s["サプライヤー数"]}社 / 出品{s["出品数"]}点</span></div>')
        p.append('<div class="wrap"><table><tr><th>仕入先</th><th>商品名</th><th>ASIN</th>'
                 "<th>発注口数</th><th>出品数</th><th>仕入額</th><th>この行の粗利</th>"
                 "<th>回転月数</th><th>発注前に確認</th></tr>")
        for l in sorted(s["明細"], key=lambda x: (x["仕入先"], -x["仕入額"])):
            p.append(f'<tr><td>{h(l["仕入先"])}</td><td>{h(l["商品名"])}</td>'
                     f'<td>{h(l["ASIN"])}</td><td class="n">{l["口数"]}</td>'
                     f'<td class="n">{l["出品数"]}</td><td class="n">{l["仕入額"]:,}</td>'
                     f'<td class="n">{l["粗利"]:,}</td>'
                     f'<td class="n">{l["回転月数"]:.1f}</td><td>{h(l["要確認"])}</td></tr>')
        p.append(f'<tr class="sum"><td colspan="5">合計</td>'
                 f'<td class="n">{s["仕入額"]:,}</td><td class="n">{s["粗利"]:,}</td>'
                 f'<td colspan="2">送料 {s["送料"]:,}円を引いて手残り {s["手残り"]:,}円</td></tr>')
        p.append("</table></div>")
        p.append(f'<p class="note">送料の実額: {h(" ｜ ".join(s["送料の内訳"]))}</p>')
        p.append(f'<div class="wipe"><b>全滅シナリオ</b><br>{h(wipeout_note(s))}</div></div>')

    p.append("<h2>4. この資料の更新のしかた</h2>"
             "<p>T-20260908-002 の続報（13〜25位）が届いたら、<code>pool.csv</code> に"
             "「現行」の行を足して <code>python3 order_set.py</code> を実行し直すだけです。"
             "コードは触りません。</p>")
    if dropped:
        p.append(f'<p class="note">元データに見つからなかった ASIN: {h(dropped)}</p>')
    (OUT / "03_発注セット.html").write_text("\n".join(p), encoding="utf-8")


def write_outputs(plans, skus, tariffs, sup_ids, dropped):
    OUT.mkdir(exist_ok=True)

    with open(OUT / "01_発注セット_案別.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["案", "ねらい", "仕入先", "ASIN", "商品名", "メーカー",
                    "入数", "発注口数", "出品数", "仕入額(税込)", "1出品の純利益",
                    "利益率%", "この行の粗利", "回転月数", "ランク", "出品者数",
                    "FBAサイズ", "発注前に確認すること"])
        for lbl, aim, s in plans:
            for l in sorted(s["明細"], key=lambda x: (x["仕入先"], -x["仕入額"])):
                w.writerow([lbl, aim, l["仕入先"], l["ASIN"], l["商品名"], l["メーカー"],
                            l["入数"], l["口数"], l["出品数"], l["仕入額"],
                            round(l["純利益"]), round(l["利益率%"], 1), l["粗利"],
                            f"{l['回転月数']:.1f}" if l["回転月数"] else "",
                            l["ランク"], l["出品者数"], l["FBAサイズ"], l["要確認"]])
            w.writerow([lbl, "＝合計＝", f"{s['サプライヤー数']}社", "", "", "", "",
                        "", s["出品数"], s["仕入額"], "", "", s["粗利"], "", "", "", "",
                        f"送料{s['送料']}円 / 総額{s['総額']}円 / 手残り{s['手残り']}円"])

    with open(OUT / "02_案の比較.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["案", "ねらい", "SKU数", "サプライヤー数", "出品数",
                    "仕入額(税込)", "送料", "総額", "粗利", "送料を引いた手残り",
                    "最大1社シェア", "最長回転月数", "全滅シナリオ", "送料の内訳"])
        for lbl, aim, s in plans:
            w.writerow([lbl, aim, s["SKU数"], s["サプライヤー数"], s["出品数"],
                        s["仕入額"], s["送料"], s["総額"], s["粗利"], s["手残り"],
                        f"{s['最大社シェア']:.0%}", f"{s['最長回転月数']:.1f}",
                        wipeout_note(s), " ｜ ".join(s["送料の内訳"])])

    write_html(plans, skus, dropped)

    json.dump({"予算": TOTAL_BUDGET_YEN, "在庫上限月数": STOCK_MONTHS_CAP,
               "届け先": PREF, "除外": dropped,
               "案": [{"案": lbl, "ねらい": aim, "全滅シナリオ": wipeout_note(s),
                       **{k: v for k, v in s.items() if k != "明細"},
                       "明細": s["明細"]} for lbl, aim, s in plans]},
              open(OUT / "plans.json", "w"), ensure_ascii=False, indent=1, default=str)


def main():
    pool = load_pool(HERE / "pool.csv")
    facts = load_facts({r["ASIN"] for r in pool})
    dropped = [r["ASIN"] for r in pool if r["ASIN"] not in facts]
    skus = {r["ASIN"]: build_sku(r, facts[r["ASIN"]]) for r in pool if r["ASIN"] in facts}

    sup_ids = load_supplier_ids()
    tariffs = load_tariffs([sup_ids[s["仕入先"]] for s in skus.values()
                            if s["仕入先"] in sup_ids])

    print(f"名簿 {len(pool)}件 → 元データあり {len(skus)}件（欠落 {dropped}）")
    for s in skus.values():
        low = s["最小口数"] * s["単価"]
        m = (s["最小口数"] // s["入数"]) / s["月販見込"] if s["月販見込"] else float("inf")
        print(f"  {s['ASIN']} {s['商品名'][:22]:24} 最小 {s['最小口数']:>3}口"
              f" = {low:>7,.0f}円 / 回転 {m:5.1f}ヶ月 / {s['仕入先']}")

    sets = enumerate_sets(skus, tariffs, sup_ids)
    print(f"予算内に収まる組み合わせ {len(sets)}通り")
    if not sets:
        print("⚠ 予算5万円に収まる組み合わせがありません。最小発注数を見直してください")
        return
    plans = pick_plans(sets)
    write_outputs(plans, skus, tariffs, sup_ids, dropped)
    for lbl, aim, s in plans:
        print(f"\n{lbl} {aim}")
        print(f"  {s['SKU数']}SKU / {s['サプライヤー数']}社 / 出品{s['出品数']}点"
              f" / 総額{s['総額']:,}円（送料{s['送料']}円）"
              f" / 手残り{s['手残り']:,}円 / 最長回転{s['最長回転月数']:.1f}ヶ月")
        print(f"  全滅: {wipeout_note(s)}")
    print(f"\n書き出し: {OUT}")


if __name__ == "__main__":
    main()
