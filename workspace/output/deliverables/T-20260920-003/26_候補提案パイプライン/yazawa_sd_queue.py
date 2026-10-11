#!/usr/bin/env python3
"""ヤザワ（DNライティング ほか）の全 ASIN を、SD で卸価格を引く順に並べる（2026-10-11）。

背景
  NETSEA が 10/7 から停止中。ヤザワはスーパーデリバリー（SD）にも出展しており、SD の卸価格は
  社長の Chrome で見える。カズヨが SD で JAN を引いて卸1点の税抜価格を読み、
  「B 等級に必要な卸1点の上限（税抜）」と比べれば、その場で GO/NO-GO が決まる。

母集団（取得経路つき）
  - 採点済みプール（ledger_refresh.score_netsea。購入元＝ヤザワ）… 卸がヤザワと分かっている行
  - Keepa キャッシュ（sd_queue_big/best.pkl。ブランド＝DNライティング／YAZAWA）… 上に無い ASIN
  Keepa は叩かない（トークン0）。SD にも自動取得しない（§3.3-14・18）。

A 等級の上限は出さない：売り切り月数が実測でない＝推定費目ありで最高 B（§3.5 #18）なので常に0になる。
上限は置かない（§3.3-34）。並びは キーゾン相当の3か月販売数 → 過去1か月(monthlySold) の多い順。

出力: agent_output/T-20260920-003/ledger20261010/yazawa_sd_queue_20261011.csv
      （卸の参考値を含むので agent_output＝Git 除外。PUBLIC リポに置かない）
"""
from __future__ import annotations

import csv
import json
import os
import pickle
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger_refresh as L      # noqa: E402
import fba_cost as fc           # noqa: E402
import price_history as ph      # noqa: E402
import profit                   # noqa: E402

OUT = L.OUT / "yazawa_sd_queue_20261011.csv"
SNAP = L.OUT / "after_20261011_frac_write.json"      # 台帳の最新スナップショット（書き込み後）
BEST = L.WORK / "sd_queue_big/best.pkl"
AMZ = "AN1VRQENFRJN5"
EST = ("保管月数（売り切り月数が実測でない）",)


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def ledger_rows() -> dict[str, dict]:
    d = json.load(SNAP.open())
    h = d[0]
    return {r[2]: dict(zip(h, r + [""] * (len(h) - len(r)))) for r in d[1:] if len(r) > 2}


def grade_at(sell, worst, fba_yen, pct, unit_incl, category):
    e = profit.compute(sell, pct, fba_yen, unit_incl, 10, monthly_sold=None,
                       category=category, unit_decided=True)
    return fc.grade(sell, unit_incl, e.size_tier, category=category, keepa_pct=pct,
                    months_to_sell=3.0, unit_decided=True, sell_worst=worst,
                    estimated=EST).grade


def cap(sell, worst, fba_yen, pct, n, category, want) -> int | None:
    """卸1点あたり上限（税抜・円）。econ_at と同じ式で原価を二分探索する。"""
    if not (sell and fba_yen and n):
        return None
    ok = (lambda g: g == "A") if want == "A" else (lambda g: g in ("A", "B"))
    lo, hi = 1.0, float(sell)
    if not ok(grade_at(sell, worst, fba_yen, pct, lo, category)):
        return 0
    for _ in range(30):
        mid = (lo + hi) / 2
        if ok(grade_at(sell, worst, fba_yen, pct, mid, category)):
            lo = mid
        else:
            hi = mid
    return int(lo / 1.1 / n)


def sellers(txt: str):
    m = re.search(r"FBA\s*(\d+)／自己発送\s*(\d+)", txt or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)社", txt or "")
    return (None, int(m.group(1))) if m else (None, None)


def main() -> int:
    led = ledger_rows()
    rows: dict[str, dict] = {}
    for s in L.score_netsea():
        r = s.get("row") or {}
        if "ヤザワ" not in (r.get("購入元の名前") or ""):
            continue
        a = s["asin"]
        if a in rows and rows[a]["_src"] == "採点済み(ヤザワ)":
            continue
        p = s.get("product") or {}
        lv = s.get("price")
        sell = lv.median90 if lv else None
        worst = (lv.p25_90 or sell) if lv else None
        fba_yen = (p.get("fbaFees") or {}).get("pickAndPackFee") or (s.get("_cand") or {}).get("fba_yen")
        n = s.get("n_set") or 1
        rows[a] = dict(_src="採点済み(ヤザワ)", asin=a, jan=r.get("JAN") or ";".join(p.get("eanList") or []),
                       title=r.get("商品名") or p.get("title") or "", brand=r.get("ブランド") or "",
                       ms=p.get("monthlySold"), sell=sell, worst=worst, fba=fba_yen,
                       pct=p.get("referralFeePercentage"), n=n, decided=s.get("セット数の確度") in ("確定", "単独"),
                       cat=s.get("category"), cart=s.get("カート保持者") or "",
                       ns_pt=(s.get("per_pt") or 0) / 1.1 or None, verdict=s.get("判定"), grade=s.get("等級"))
    best = pickle.load(BEST.open("rb"))
    for b in best.values():
        br = (b.get("brand") or "")
        if not any(k in br.upper() for k in ("DNライ", "YAZAWA", "ヤザワ")) or b["asin"] in rows:
            continue
        csvl = [None] * 19
        csvl[1], csvl[18] = b.get("csv1"), b.get("csv18")
        lv = ph.from_product({"csv": csvl}) if (b.get("csv1") or b.get("csv18")) else None
        sell = lv.median90 if lv else None
        bbs = b.get("bbs") or ((b.get("bbsh") or [None])[-1])
        cart = ("Amazon.co.jp（本体）" if bbs == AMZ or b.get("bbamz")
                else f"第三者({bbs})" if bbs and bbs not in ("-1", "-2") else "不明")
        rows[b["asin"]] = dict(_src="Keepaキャッシュ(ブランド)", asin=b["asin"],
                               jan=";".join(b.get("ean") or []), title=b.get("title") or "", brand=br,
                               ms=b.get("ms"), sell=sell, worst=(lv.p25_90 or sell) if lv else None,
                               fba=b.get("fba"), pct=b.get("refpct"), n=b.get("pq") or 1,
                               decided=(b.get("pq") in (None, 1)), cat=None, cart=cart, ns_pt=None,
                               verdict="台帳外", grade="")
    out = []
    for a, x in rows.items():
        g = led.get(a, {})
        k = [_num(g.get(f"キーゾン 過去{i}ヶ月")) for i in (1, 2, 3)]
        k3 = sum(v for v in k if v is not None) if any(v is not None for v in k) else None
        avg = _num(g.get("キーゾン 平均月販"))
        fba_n, self_n = sellers(g.get("新品出品者数(画面実数)", ""))
        comp = (fba_n or 0) + (self_n or 0) if self_n is not None else None
        share = round(avg / (comp + 1), 1) if (avg is not None and comp is not None) else None
        cart = g.get("カートの販売元") or x["cart"]
        capB = cap(x["sell"], x["worst"], x["fba"], x["pct"], x["n"], x["cat"], "B")
        note = []
        if not x["sell"]:
            note.append("売価の履歴なし→上限計算不可（Amazon価格 " + str(g.get("Amazon価格") or "未確認") + "円は現在値で参考）")
        if not x["fba"]:
            note.append("FBA手数料不明→上限計算不可")
        if not x["decided"]:
            note.append("セット数未確定→Amazon1個＝卸1点で計算")
        if "本体" in cart and "Amazon" in cart:
            note.append("カート＝Amazon本体→発注しない(§3.3-1)")
        if g.get("Amazon本体の有無") == "あり" and "本体" not in cart:
            note.append("本体出品あり(カートは第三者)")
        jan = (x["jan"] or "").split(";")[0]
        out.append({
            "ASIN": a, "JAN": x["jan"], "商品名": x["title"][:70], "ブランド": x["brand"],
            "キーゾン相当 3か月合計": "" if k3 is None else k3,
            "キーゾン 過去1/2/3ヶ月": "/".join("" if v is None else str(int(v)) for v in k) if k3 is not None else "",
            "キーゾンの確認者": g.get("確認者", "") if k3 is not None else "",
            "過去1か月(monthlySold)": x["ms"] or "表示なし",
            "新品出品者(FBA／自己発送)": f"{'' if fba_n is None else fba_n}／{'' if self_n is None else self_n}" if self_n is not None else "未確認",
            "取り分(個/月)": "" if share is None else share,
            "売価90日中央値": "" if not x["sell"] else int(x["sell"]),
            "売価90日下位25%": "" if not x["worst"] else int(x["worst"]),
            "カート保持者": cart,
            "セット数": x["n"],
            "B等級に必要な卸1点上限(税抜)": "" if capB is None else capB,
            "参考:NETSEA卸1点(税抜)": "" if not x["ns_pt"] else int(round(x["ns_pt"])),
            "現在の判定": g.get("判定") or x["verdict"] or "",
            "母集団の出所": x["_src"] + ("・台帳にあり" if g else "・台帳になし"),
            "Amazon URL": f"https://www.amazon.co.jp/dp/{a}",
            "SD検索URL": f"https://www.superdelivery.com/p/do/psl/?word={jan}" if jan else "",
            "注意": "・".join(note),
            "_k": (k3 or -1, _num(x["ms"]) or -1),
        })
    out.sort(key=lambda r: (-r["_k"][0], -r["_k"][1], r["ASIN"]))
    cols = ["順位"] + [c for c in out[0] if c != "_k"]
    tmp = str(OUT) + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, r in enumerate(out, 1):
            r.pop("_k")
            w.writerow({"順位": i, **r})
    os.replace(tmp, OUT)
    print(json.dumps({"rows": len(out),
                      "with_kz": sum(1 for r in out if r["キーゾン相当 3か月合計"] != ""),
                      "with_capB": sum(1 for r in out if r["B等級に必要な卸1点上限(税抜)"] not in ("", 0)),
                      "src": {s: sum(1 for r in out if r["母集団の出所"].startswith(s))
                              for s in ("採点済み", "Keepa")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
