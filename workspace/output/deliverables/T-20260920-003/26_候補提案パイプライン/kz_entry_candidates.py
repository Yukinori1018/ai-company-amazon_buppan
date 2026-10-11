#!/usr/bin/env python3
"""kz 入口の段3：NETSEA 索引に当たる ASIN を kz（キーゾン再現の3か月販売数）で選び、採点して CSV にする。

2026-10-11 タカシ（T-20260920-003）。
  python3 kz_entry_candidates.py queue   # 足切り（kz 平均≥6・本体カートでない）→ queue_full.json
  python3 kz_entry_candidates.py build   # full 取得済みの ASIN を採点 → new_kz_candidates_20261011.csv

入口の条件（monthlySold は問わない）
  1. NETSEA 索引（pipeline/netsea_jan_index.json）に JAN が当たる
  2. kz 式（kz_entry_harvest.kz_months）の3か月平均が月 KZ_MIN 個以上
     ＝最新のランク履歴で数える（full > hist > キャッシュ の順に新しいものを使う）
  3. カート保持者が Amazon 本体でない（buyBoxSellerId。outOfStockPercentage365 は補助で列に書くだけ）
採点：score_20261004.build()（台帳と同じゲート・同じ費用モデル）をそのまま呼び、
  「実売」ゲートだけ kz の結果に差し替える（build は monthlySold／ランクで見るため）。
出す行：等級 A/B かつ 取り分（kz平均 ÷ (カート対象FBA＋自己発送＋1)）≥ 3。
  台帳に既にある ASIN は別ファイル（kz_candidates_in_ledger_20261011.csv）に分ける。
卸値・購入先URL を含むので出力は agent_output にだけ置く（PUBLIC リポ）。
"""
from __future__ import annotations

import csv
import json
import math
import pickle
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))
import score_20261004 as S          # noqa: E402
import set_family                   # noqa: E402
import profit                       # noqa: E402
import fba_cost                     # noqa: E402
import price_history as PH          # noqa: E402
from kz_entry_harvest import kz_months, T0, kday   # noqa: E402
from ledger_sheet import COLUMNS    # noqa: E402

WORK = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003")
KZ = WORK / "kz_entry"
LED = WORK / "ledger20261010"
IDX = WORK / "pipeline/netsea_jan_index.json"
NAMES = WORK / "pipeline/seller_names.json"
TODAY = "2026-10-11"
TICKET = "T-20260920-003"
KZ_MIN = 6           # 入口：3か月平均 月6個（カズヨ指定。§3.1 の変数）
MIN_SHARE = 3        # §3.5 #10
TARGET_MONTHS, MAX_MONTHS = 3, 6
AMAZON = "AN1VRQENFRJN5"
IDX_DAY = "2026-10-01"
EXTRA_COLS = ["3か月販売数", "取り分(個/月)"]


def load_jsonl(p: Path) -> dict[str, tuple[dict, int]]:
    out = {}
    if p.exists():
        for line in p.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("asin") and o.get("product"):
                out[o["asin"]] = (o["product"], o.get("fetched") or 0)
    return out


def kz_of(p: dict, fetched: int) -> tuple[list[int], list[int]] | None:
    c = p.get("csv") or []
    if len(c) < 4 or not c[3]:
        return None
    return kz_months(c[3], fetched // 60 - T0)


def amazon_cart(p: dict) -> bool | None:
    st = p.get("stats") or {}
    if "buyBoxSellerId" not in st and "buyBoxIsAmazon" not in st:
        return None
    return st.get("buyBoxIsAmazon") is True or st.get("buyBoxSellerId") == AMAZON


def netsea_hits(ean: list[str], idx: dict) -> list[tuple[str, dict]]:
    return [(e, idx[e]) for e in ean if e in idx]


def queue() -> int:
    h = pickle.load((KZ / "harvest.pkl").open("rb"))
    B, H = h["best"], h["hist"]
    idx = json.loads(IDX.read_text())["jans"]
    hist, full = load_jsonl(KZ / "keepa_hist.jsonl"), load_jsonl(KZ / "keepa_full.jsonl")
    hit = [a for a, r in B.items() if netsea_hits(r["ean"], idx)]
    n = Counter()
    q = []
    for a in hit:
        r = B[a]
        stock = {w["stock"] for _, w in netsea_hits(r["ean"], idx)}
        if "在庫あり" not in stock:
            n["索引で品切れ"] += 1
            continue
        src = full.get(a) or hist.get(a)
        if src:
            k = kz_of(*src)
        elif a in H:
            k = (H[a]["m"], H[a]["obs"])
        else:
            k = None
        if k is None:
            n["ランク履歴なし"] += 1
            continue
        if sum(k[0]) / 3 < KZ_MIN:
            n[f"kz平均<{KZ_MIN}"] += 1
            continue
        # カートは「いま」で見るので full 取得で確定する。ここでは既知の本体カートだけ落とす
        known = amazon_cart(full[a][0]) if a in full else (
            r["bbamz"] is True or r["bbs"] == AMAZON if r.get("has_bb") else None)
        if known:
            n["既知の本体カート"] += 1
            continue
        n["通過"] += 1
        q.append(a)
    json.dump(q, (KZ / "queue_full.json").open("w"))
    print(f"NETSEA 索引に当たる ASIN {len(hit)} →", dict(n))
    return 0


def gate_checks() -> dict[str, tuple[str, str]]:
    out = {}
    for f, kcol, ok in ((WORK / "buylist20261009/gate_check_20261009.csv", "ゲート判定", "OK"),
                        (LED / "gate_check_20261011.csv", "新品の出品可否", "OK"),
                        (LED / "gate_check_20261011_b.csv", "新品の出品可否", "OK")):
        if f.exists():
            for r in csv.DictReader(f.open(encoding="utf-8-sig")):
                when = r.get("確認日") or r.get("確認時刻") or ""
                out[r["ASIN"]] = ("可（新品）" if r[kcol] == ok else "不可（新品の申請経路なし）",
                                  f"restrictions/approve（{when}）")
    return out


def ledger_asins() -> set[str]:
    snaps = sorted(LED.glob("before_20261011_final_dry*.json"), key=lambda p: p.stat().st_mtime)
    if not snaps:
        return set()
    rows = json.loads(snaps[-1].read_text())
    i = rows[0].index("ASIN")
    return {r[i] for r in rows[1:] if len(r) > i}


def build_row(asin: str, p: dict, idx: dict, share: float | None, min_lot: int) -> dict | None:
    """score_new.build_row と同じ形（agent_output のスクリプトを import しないため複製）。"""
    hit = netsea_hits([str(c) for c in (p.get("eanList") or []) + (p.get("upcList") or [])], idx)
    hit = [(j, w) for j, w in hit if w.get("stock") == "在庫あり"] or hit
    if not hit:
        return None
    jan, w = min(hit, key=lambda t: t[1].get("unit_price_excl") or 10 ** 9)
    sc = set_family.resolve(p.get("title"), p.get("packageQuantity"), p.get("numberOfItems"))
    per_pt = profit.unit_cost_incl_tax(w["unit_price_excl"])
    pack = max(1, int(w.get("min_lot_units") or 1))
    # 発注点数は取り分から（screen_checks.share_gate と同じ：3か月分・最小ロット以上）
    if share:
        rec = max(pack, math.floor(share * TARGET_MONTHS))
        months = round(rec / share, 1)
    else:
        rec, months = pack, ""
    fee = (p.get("fbaFees") or {}).get("pickAndPackFee")
    fba_src = "Keepa fbaFees"
    if not fee:
        lv = PH.from_product(p)
        tier = fba_cost.tier_from_dimensions(p.get("packageLength"), p.get("packageWidth"),
                                             p.get("packageHeight"), p.get("packageWeight"))
        fee = fba_cost.fba_fee_yen(tier, lv.sell_for_profit) if (tier and lv.sell_for_profit) else None
        fba_src = f"寸法から区分{tier}→公式料金表" if fee else "寸法なし"
    return {
        "ASIN": asin, "商品名": p.get("title") or "", "ブランド": p.get("brand") or "",
        "AmazonURL": f"https://www.amazon.co.jp/dp/{asin}", "JAN": jan,
        "Amazon側のセット数(Amazon1個=卸何点か)": sc.n or "",
        "セット数の確度": sc.confidence,
        "セット数の情報源": json.dumps(sc.sources, ensure_ascii=False),
        "卸の1点あたり原価(税込)": per_pt,
        "Amazon1個あたり原価(税込)": (per_pt * sc.n) if (sc.n and sc.is_decided()) else "",
        "発注点数(Amazon何個)": rec, "売り切る月数": months, "ゲート種別": "未確認",
        "購入元の名前": w.get("supplier_name") or "",
        "_fba_yen": fee or "", "_fba_src": fba_src, "_supplier_url": w.get("supplier_url") or "",
    }


def build() -> int:
    idx = json.loads(IDX.read_text())["jans"]
    names = json.loads(NAMES.read_text()) if NAMES.exists() else {}
    full = load_jsonl(KZ / "keepa_full.jsonl")
    queue_ = json.loads((KZ / "queue_full.json").read_text())
    gates, in_led = gate_checks(), ledger_asins()
    legal = {}
    lf = LED / "legal_flags_20261011.csv"
    if lf.exists():
        legal = {r["ASIN"]: r for r in csv.DictReader(lf.open(encoding="utf-8-sig"))}
    rc: Counter = Counter()
    for p, _ in full.values():
        cur = (p.get("stats") or {}).get("current") or []
        if len(cur) > 3 and cur[3] and cur[3] > 0:
            rc[cur[3]] += 1
    n = Counter()
    out_new, out_led = [], []
    for a in queue_:
        if a not in full:
            n["full 未取得"] += 1
            continue
        p, fetched = full[a]
        k = kz_of(p, fetched)
        if not k or sum(k[0]) / 3 < KZ_MIN:
            n[f"最新で kz平均<{KZ_MIN}"] += 1
            continue
        m, obs = k
        avg = round(sum(m) / 3, 1)
        if amazon_cart(p):
            n["本体カート"] += 1
            continue
        bb = p.get("buyBoxEligibleOfferCounts") or []
        fba, fbm = (max(bb[0], 0), max(bb[1], 0)) if len(bb) >= 2 else (None, None)
        share = avg / (fba + fbm + 1) if fba is not None else None
        row = build_row(a, p, idx, share, 1)
        if not row:
            n["JAN 不一致"] += 1
            continue
        s = S.build(row, {"fba_yen": row.get("_fba_yen") or None}, p, idx, names, IDX_DAY,
                    None, dict(rc))
        # 実売ゲートを kz に差し替える（monthlySold は問わない入口）
        note = []
        if p.get("parentAsin"):
            note.append("バリエーション子＝family合計（この ASIN 単独の実数ではない）")
        if any(o < 10 for o in obs):
            note.append("観測少(" + "/".join(map(str, obs)) + ")")
        if max(m) > 13:
            note.append("月13個超は未検算・過小の可能性")
        kz_txt = f"{m[0]}/{m[1]}/{m[2]}（平均{avg:g}個）"
        sale_st = "UNKNOWN" if p.get("parentAsin") else "PASS"
        s["gates"] = [g for g in s["gates"] if g[0] != "実売"] + [(
            "実売", sale_st,
            f"キーゾン再現値 3か月 {kz_txt}（Keepa ランク改善3%超・§3.3-16）"
            + (f"。注意：{'・'.join(note)}" if note else ""))]
        if share is None:
            s["gates"].append(("取り分", "UNKNOWN", "カート対象の出品者数が取れない"))
        elif share < MIN_SHARE:
            s["gates"].append(("取り分", "FAIL", f"取り分 {share:.1f}個/月（基準3個）＝{avg:g}÷({fba}+{fbm}+1)"))
        else:
            s["gates"].append(("取り分", "PASS", f"取り分 {share:.1f}個/月＝{avg:g}÷({fba}+{fbm}+1)"))
        e = s.get("econ")
        grade = s.get("等級")
        if grade not in ("A", "B"):
            n[f"等級{grade}"] += 1
            continue
        if share is None or share < MIN_SHARE:
            n["取り分<3"] += 1
            continue
        n["出力"] += 1
        sts = [g[1] for g in s["gates"]]
        if "FAIL" in sts:
            verdict = "NO-GO"
        else:
            verdict = "UNKNOWN"     # 機械が全部通しても GO にしない（§3.3-16：人の実画面確認待ち）
        fails = [f"{g[0]}：{g[2]}" for g in s["gates"] if g[1] != "PASS"]
        passed = [g[0] for g in s["gates"] if g[1] == "PASS"]
        reason = (("未達：" + " ／ ".join(fails) + " ／ ") if fails else
                  "機械判定は全項目通過・実画面確認待ち ／ ")
        reason += (f"通過：{'・'.join(passed)} ／ 入口＝kz（monthlySold を問わない・{TODAY}） ／ "
                   f"人が見る項目：#5 カートの実画面・#7 出品一覧の実数・#9 キーゾン実画面・"
                   f"#1-2 restrictions/approve・#4 卸の注意事項・#17 卸の在庫と価格の取り直し")
        lg = legal.get(a)
        if lg:
            verdict = lg.get("区分") or verdict
            reason = lg.get("判定理由に書く文", "") + " ／ " + reason
        st = p.get("stats") or {}
        oos = st.get("outOfStockPercentage365")
        oos = oos[0] if isinstance(oos, list) and oos else None
        amz_now = (st.get("current") or [None])[0]
        gate = gates.get(a)
        lv = s.get("price")
        cells = {h: "未確認" for h in COLUMNS}
        cells.update({
            "判定日": TODAY, "チケットID": TICKET, "ASIN": a,
            "商品名": (row["商品名"] or "")[:80], "ブランド": row["ブランド"] or "未確認",
            "Amazon URL": row["AmazonURL"],
            "Amazon価格": lv.sell_for_profit if lv and lv.sell_for_profit else "未確認",
            "キーゾン 平均月販": f"{avg:g}（Keepa 再現値）",
            "キーゾン 過去1ヶ月": m[0], "キーゾン 過去2ヶ月": m[1], "キーゾン 過去3ヶ月": m[2],
            "新品出品者数(画面実数)": f"未確認（Keepa カート対象：FBA {fba}／自己発送 {fbm}）",
            "Amazon本体の有無": ("いま本体の在庫あり（カートは第三者）" if amz_now and amz_now > 0
                              else "いま本体の在庫なし") + "・実画面未確認",
            "カートの販売元": s.get("カート保持者") or "未確認",
            "本体365日在庫率": (f"{100 - oos}%" if isinstance(oos, int) and 0 <= oos <= 100
                             else "本体の記録なし"),
            "ゲート種別": gate[1] if gate else "未確認",
            "ゲート可否": gate[0] if gate else "未確認",
            "購入元の名前": row["購入元の名前"] or "未確認", "卸サイト": "NETSEA",
            "購入先URL": row["_supplier_url"] or "未確認",
            "卸率(売価比)": e.cost_ratio_pct, "発注点数": e.qty, "発注額(円・税込)": e.order_total,
            "1個粗利(円)": e.net_per_unit, "利益率(%)": e.net_margin_pct,
            "売り切る月数": row["売り切る月数"], "半値処分時の損失(円)": e.half_disposal_loss,
            "判定": verdict, "判定理由": f"【等級 {grade}】" + reason[:1700],
            "確認方法": f"Keepa stats=90&history=1&buybox=1（{kday(fetched // 60 - T0)}）＋NETSEA 索引（{IDX_DAY}）で機械判定",
            "確認者": "タカシ（機械判定・実画面未確認）", "発注状況": "未発注",
            "3か月販売数": kz_txt + (f"／{'・'.join(note)}" if note else ""),
            "取り分(個/月)": round(share, 1),
        })
        cells["_sort"] = (verdict != "UNKNOWN", -(e.net_per_unit or 0) * share)
        (out_led if a in in_led else out_new).append(cells)
    cols = COLUMNS + EXTRA_COLS
    for rows, name in ((out_new, "new_kz_candidates_20261011.csv"),
                       (out_led, "kz_candidates_in_ledger_20261011.csv")):
        rows.sort(key=lambda r: r["_sort"])
        with (LED / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    print(f"queue {len(queue_)} →", dict(n))
    print(f"新規 {len(out_new)}（台帳に既存 {len(out_led)} は別ファイル）")
    print("新規の判定:", dict(Counter(r["判定"] for r in out_new)),
          "等級:", dict(Counter(r["判定理由"][:6] for r in out_new)))
    return 0


if __name__ == "__main__":
    raise SystemExit({"queue": queue, "build": build}[sys.argv[1]]())
