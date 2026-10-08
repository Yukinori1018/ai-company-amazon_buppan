#!/usr/bin/env python3
"""候補 CSV から、仕入れ前チェックの「機械で決まる項目」だけを自動で記録する。

なぜ要るか
  確認記録は 2026-10-09 時点で **2 ASIN 分しかありませんでした**（候補は648件）。
  21項目 × 全SKU を人が手で打つ前提では、§3.5 は永久に回りません。
  **機械で決まる項目を機械が埋め、人の時間を「人しか見られない12項目」に寄せる**のが目的です。

やらないこと（ここが肝心）
  1. **human 項目を PASS にしません。**`checklist_spec.json` の `decidable` を見て、
     `human` は `UNKNOWN` ＋ 取り方だけを書きます。**空欄で埋めません。**
  2. **partial 項目は「落とす側」だけ機械で決めます。**カートの販売元が Amazon 本体なら FAIL、
     本体でなければ UNKNOWN（メーカー本人かどうかは人が見る）。
     **機械の GO は「買ってよい」ではなく「人が実画面で見る価値がある」の意味**（§3.3-16）。
  3. 🔴 **人が付けた記録を機械が上書きしません。**`checked_by` が autofill 以外の記録は
     触りません（§3.3-16「人が実画面で確認した結果は機械が上書きしない仕組みにする」）。
  4. **整合性検査が NG の行は、採算の項目を PASS にしません。**`consistency.py` を通します。

使い方
    python3 scripts/sourcing_gate/autofill.py <candidates.csv> \\
        [--private <private.csv>] [--only B0XXXXXXXX ...] [--dry-run] [--today 2026-10-09]

    # 埋まり具合を見る
    python3 scripts/sourcing_gate/autofill.py <candidates.csv> --coverage
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as K  # noqa: E402
import gate  # noqa: E402

BY = "autofill"                  # この名前の記録だけを上書きしてよい
SOURCE_PREFIX = "候補CSV"

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


# ── 機械判定の本体 ────────────────────────────────────────────────────────
# どの関数も (値の文字列, 判定, 補足) を返す。判定できないときは UNKNOWN と「なぜ決まらないか」。

def _amazon_stock_history(row: dict, ctx: dict):
    v = K.get(row, "Amazon本体の有無").strip()
    if not v:
        return None
    # 落とす判断には使わない補助情報（§3.3-22／成果物の実測で79%を誤って落としていた）。
    return (f"本体の出品: {v}（補助情報。落とす判断はカート保持者だけで行う）", PASS, "")


def _season_window(row: dict, ctx: dict):
    w = K.get(row, "季節の窓").strip()
    k = K.get(row, "季節(ランク12ヶ月履歴)").strip()
    if not w:
        return None
    val = f"季節の窓 {w}（ランク12ヶ月履歴: {k or '不明'}）"
    if w.startswith("×"):
        return (val, FAIL, "販売開始日が季節のピークを過ぎます")
    if w.startswith("○"):
        return (val, PASS, "")
    return (val, UNKNOWN, "季節の窓が ○ か × に決まっていません")


def _price_median90(row: dict, ctx: dict):
    m = K.num(K.get(row, K.COLS.sell))
    w = K.num(K.get(row, K.COLS.sell_worst))
    src = K.get(row, K.COLS.price_src).strip()
    if m is None:
        return ("90日中央値が取れていません", UNKNOWN,
                f"価格の出どころ: {src or 'なし'}。履歴が無い棚は採算を出せません")
    val = f"90日中央値 {m:,.0f}円・下位25% {w:,.0f}円" if w is not None else f"90日中央値 {m:,.0f}円"
    return (f"{val}（出どころ: {src or '不明'}）", PASS, "")


def _price_trend(row: dict, ctx: dict):
    judge = K.get(row, "価格の判定").strip()
    slope = K.get(row, "価格の傾き(%/30日)").strip()
    swing = K.get(row, "価格の振れ幅").strip()
    if not judge or judge == "判定不能":
        return ("価格の傾きが出せません", UNKNOWN, "90日の履歴が足りません")
    val = f"判定「{judge}」・傾き {slope or '不明'}・振れ幅 {swing or '不明'}"
    if judge == "使える":
        return (val, PASS, "")
    if judge == "下落トレンド":
        return (val, FAIL, "売る頃にはもっと安くなります")
    return (val, UNKNOWN, f"「{judge}」は読めない価格です")


def _profit_grade(row: dict, ctx: dict):
    g = K.get(row, K.COLS.grade).strip()
    res: K.RowResult = ctx["consistency"]
    if res.blocking:
        return (f"等級 {g or '不明'}（整合性検査 NG）", UNKNOWN,
                "整合性検査で落ちています: " + "; ".join(f.check for f in res.blocking))
    net, mar = K.num(K.get(row, K.COLS.net)), K.num(K.get(row, K.COLS.margin))
    if g not in ("A", "B", "C") or net is None or mar is None:
        return (f"等級 {g or '不明'}", UNKNOWN, "採算が計算されていません")
    val = f"等級 {g}・中央の手残り {net:,.0f}円・{mar:.1f}%"
    if g == "C":
        return (val, FAIL, "C 等級は落とします")
    return (val, PASS, "等級Bは最小ロットで1回だけ" if g == "B" else "")


def _timeline(row: dict, ctx: dict):
    res: K.RowResult = ctx["consistency"]
    bad = [f for f in res.findings if f.check in ("timeline", "timeline_stale")]
    cols = (K.COLS.d_order, K.COLS.d_arrive, K.COLS.d_fba, K.COLS.d_start, K.COLS.d_target)
    vals = [K.get(row, c) for c in cols]
    if not any(vals):
        return None
    val = " → ".join(v or "？" for v in vals)
    ng = [f for f in bad if f.severity == K.NG]
    if ng:
        return (val, FAIL, ng[0].message)
    warn = [f for f in bad if f.severity == K.WARN]
    if warn:
        return (val, UNKNOWN, warn[0].message)
    return (val, PASS, "")


def _buybox_seller(row: dict, ctx: dict):
    """partial。本体なら機械で FAIL。本体でなければ UNKNOWN（メーカー本人は人が見る）。"""
    v = K.get(row, K.COLS.buybox).strip()
    if not v:
        return ("カートの販売元が取れていません", UNKNOWN, "誰がカートを持っているかが第0問です")
    if "Amazon.co.jp" in v or v.strip() in ("Amazon", "アマゾン"):
        return (f"カート保持者: {v}", FAIL, "Amazon 本体がカートを持つ棚は値下げしても取れません")
    return (f"カート保持者: {v}", UNKNOWN,
            "本体ではありません。**メーカー本人・ブランド公式でないかを人が実画面で確かめてください**"
            "（§3.3-5。オファーが少ないのはメーカーが1社で売っているサインのことがあります）")


def _amazon_set_count(row: dict, ctx: dict):
    """partial。確度が『確定・単独』なら通す。それ以外は 1 と決め打たない。"""
    conf = K.get(row, K.COLS.set_conf).strip()
    n = K.num(K.get(row, K.COLS.set_count))
    if not conf:
        return None
    if conf in ("確定", "単独") and n is not None:
        return (f"Amazon1個 = 卸 {n:g}点（確度: {conf}）", PASS, "")
    return (f"セット数の確度「{conf}」・値 {n if n is not None else '不明'}", UNKNOWN,
            "Amazon の1個が卸の何点かが決まりません。**1 と決め打たず、人が卸と Amazon の"
            "両方の画面を見てください**（§3.3-17 単位ずれは「幅」ではなく「真偽」）")


def _my_share(row: dict, ctx: dict):
    """partial。入力（実売・出品者の内訳）がどちらも人なので、ここでは埋められない。"""
    months = K.get(row, K.COLS.months).strip()
    return (f"取り分が出せません（売り切る月数の表示: {months or '空欄'}）", UNKNOWN,
            "月販 ÷（FBA＋即納の自己発送＋1）で出しますが、月販は actual_sales、"
            "出品者の内訳は new_offer_count ＝どちらも人が実画面で見る項目です")


MACHINE = {
    "amazon_stock_history": _amazon_stock_history,
    "season_window": _season_window,
    "price_median90": _price_median90,
    "price_trend": _price_trend,
    "profit_grade": _profit_grade,
    "timeline": _timeline,
    "buybox_seller": _buybox_seller,
    "amazon_set_count": _amazon_set_count,
    "my_share": _my_share,
}


def plan_for_row(row: dict, spec: list[dict], *, today: date,
                 base_date: Optional[date] = None,
                 wholesale: Optional[dict] = None) -> tuple[str, dict, K.RowResult]:
    """1行ぶんの「こう記録する」案と、整合性検査の結果を返す。"""
    asin = K.get(row, K.COLS.asin).strip().upper()
    res = K.check_row(row, today=today, base_date=base_date, wholesale=wholesale)
    ctx = {"consistency": res}
    out: dict[str, dict] = {}
    for it in spec:
        iid, kind = it["id"], it.get("decidable", "human")
        entry: Optional[tuple[str, str, str]] = None
        if kind in ("machine", "partial") and iid in MACHINE:
            entry = MACHINE[iid](row, ctx)
        if entry is None:
            # human、または機械の入力が無い。**空欄にせず UNKNOWN と取り方を書く。**
            note = ("人が実画面・書類・現物で確認する項目です。" if kind == "human"
                    else "機械の入力が候補CSVに無く決まりません。")
            entry = (f"未確認（{it['name']}）", UNKNOWN,
                     f"{note} 取り方: {it.get('how', '')}".strip())
        value, result, note = entry
        # source は apply_plan が入力 CSV のパスで埋める（記録の出典は呼び出し側が知っている）
        e = {"value": value, "result": result, "source": SOURCE_PREFIX,
             "checked_at": today.isoformat(), "checked_by": BY}
        if note:
            e["note"] = note
        out[iid] = e
    return asin, out, res


def apply_plan(asin: str, plan: dict, *, source: str, dry_run: bool = False,
               consistency: Optional[K.RowResult] = None,
               today: Optional[date] = None) -> dict:
    """記録ファイルへ反映する。**人の記録は上書きしない。**変更の内訳を返す。

    整合性検査の結果も `consistency` キーに書く。gate.evaluate がこれを見て、
    21項目が全部 PASS でも NG なら発注案を止める。
    """
    rec = gate.load_record(asin)
    items = rec.setdefault("items", {})
    wrote, kept, same = [], [], []
    for iid, entry in plan.items():
        entry = dict(entry)
        entry["source"] = source
        cur = items.get(iid)
        if cur and str(cur.get("checked_by", "")) != BY:
            kept.append(iid)          # 🔴 人が見た結果。機械は触らない
            continue
        if cur and all(cur.get(k) == entry.get(k) for k in ("value", "result", "note")):
            same.append(iid)          # 中身が同じ＝書かない（2回目で0件にするため）
            continue
        if cur:
            rec.setdefault("history", []).append({"item_id": iid, **cur})
        items[iid] = entry
        wrote.append(iid)
    rec["asin"] = asin

    cons_changed = False
    if consistency is not None:
        entry = {
            "result": "NG" if consistency.blocking else ("WARN" if consistency.of(K.WARN) else "OK"),
            "detail": " ／ ".join(f.line() for f in consistency.findings),
            "checked_at": (today or date.today()).isoformat(),
            "checked_by": BY,
        }
        if {k: rec.get("consistency", {}).get(k) for k in ("result", "detail")} != \
           {k: entry[k] for k in ("result", "detail")}:
            rec["consistency"] = entry
            cons_changed = True

    if (wrote or cons_changed) and not dry_run:
        p = gate.record_path(asin)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"書いた": wrote, "人の記録を残した": kept, "同じなので触らない": same,
            "整合性検査を更新": cons_changed}


# ── CLI ───────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="候補CSVから機械で決まる項目だけを記録する")
    ap.add_argument("csv")
    ap.add_argument("--private", help="卸値・最小発注数を持つ CSV（agent_output 専用）")
    ap.add_argument("--only", nargs="*", help="この ASIN だけ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--coverage", action="store_true", help="埋まり具合だけ出す")
    ap.add_argument("--today", type=date.fromisoformat)
    ap.add_argument("--base-date", dest="base_date", type=date.fromisoformat)
    a = ap.parse_args(argv)

    today = a.today or date.today()
    spec = gate.load_spec()
    src = Path(a.csv)
    cols, rows = K.read_rows(src)
    wh = K.load_private(Path(a.private) if a.private else None)
    only = {s.upper() for s in (a.only or [])}

    kinds = {}
    for it in spec:
        kinds.setdefault(it.get("decidable", "human"), []).append(it["id"])
    print(f"項目の仕分け: " + " / ".join(f"{k} {len(v)}件" for k, v in sorted(kinds.items())))

    tally = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
    n_rows = n_written = n_kept = 0
    gate_ok = []
    for row in rows:
        asin = K.get(row, K.COLS.asin).strip().upper()
        if not asin or (only and asin not in only):
            continue
        n_rows += 1
        asin, plan, cons = plan_for_row(row, spec, today=today, base_date=a.base_date,
                                        wholesale=wh.get(asin))
        for e in plan.values():
            tally[e["result"]] = tally.get(e["result"], 0) + 1
        if a.coverage:
            continue
        r = apply_plan(asin, plan, source=f"{SOURCE_PREFIX}: {src}", dry_run=a.dry_run,
                       consistency=cons, today=today)
        if r["書いた"]:
            n_written += 1
        if r["人の記録を残した"]:
            n_kept += 1
    print(f"対象 {n_rows} ASIN × {len(spec)}項目 = {n_rows * len(spec)}件の判定")
    print("  " + " / ".join(f"{k} {v}件" for k, v in tally.items()))
    if not a.coverage:
        print(f"記録を書いた ASIN: {n_written}件"
              + ("（--dry-run なのでファイルは書いていません）" if a.dry_run else ""))
        print(f"人の記録があって機械が触らなかった ASIN: {n_kept}件")
    print("\n※ PASS は「買ってよい」ではなく「人が実画面で見る価値がある」の意味です（§3.3-16）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
