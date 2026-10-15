#!/usr/bin/env python3
"""カズヨの実画面確認（browser_results_<日付>.tsv）を、人の確認の証跡ファイルに変換する。

なぜ要るか（2026-10-15 タカシ）
------------------------------
`unknown_stages.py` が出す「実画面で見る ASIN」（needs_browser_<日付>.txt）を、カズヨが
社長の Chrome で見て TSV に書き戻してくる。判定に効かせるには `screen_checks.py` が読む
証跡ファイル（ledger20261010/gate_check_*.csv・cart_check_*.csv）の形に揃える必要がある。
10/12 は手で転記していた（cart_check_20261012_z_browser.csv）ので、ここで道具にした。

  - 台帳のセルに直書きはしない。証跡ファイルに置き、`ledger_refresh.py` が引き直すたびに
    人の値で上書き合流させる（＝機械が人の値を上書きしない・§3.3-16）
  - あわせて発注ゲートの確認記録（_sourcing_checks/<ASIN>.json）にも同じ値を入れる
    （gate_type・listing_button・buybox_seller・new_offer_count）

入力 TSV の列（カズヨ形式）
  ASIN / 見る項目 / #1-2ゲート / #5カート / #7内訳 / ブランド(画面) / 卸サイト / 購入元 / 商品名
  #1-2ゲート: PASS（新品出品可）｜PASS（申請で開く・書類10点）｜FAIL（新品の申請経路なし）
  #5カート  : PASS（第三者：<販売元>）｜FAIL（Amazon本体…）｜UNKNOWN（カートなし…）
  #7内訳    : 新品n件・本体なし|本体あり・カート出荷FBA|自己発送/不明

やらないこと
  - #7 の FBA／即納の自己発送／取り寄せの内訳は TSV に無いので offer_check は作らない
    （推測で埋めない。#10 の分母は Keepa の buyBoxEligibleOfferCounts のまま）
  - カート価格・過去1か月表示も TSV に無いので空欄のまま

使い方
  python3 browser_results_import.py <browser_results.tsv> --tag 20261015_browser \
      --checked-at "2026-10-15 22:00" [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import screen_checks as SC  # noqa: E402

REPO = SC.REPO
sys.path.insert(0, str(REPO / "scripts/sourcing_gate"))
import gate  # noqa: E402

CART_COLS = ["ASIN", "カートあり", "カート保持者(実画面)", "カート価格", "過去1か月(実画面・下限)",
             "確認時刻", "確認者", "注意", "アマゾン直販(キーゾン)",
             "新品出品者数(出品一覧)", "Amazon本体(出品一覧)"]
GATE_COLS = ["ASIN", "新品の出品可否", "判定方法", "確認時刻", "確認者"]
GATE_URL = ("https://sellercentral-japan.amazon.com/hz/approvalrequest/restrictions/approve"
            "?asin={a}&itemcondition=New")


def parse_gate(s: str) -> tuple[str, str]:
    """(gate_check の『新品の出品可否』, 区分 open/docs/closed)。"""
    s = s.strip()
    if s.startswith("PASS") and "書類" in s:
        return "OK(出品許可が必要＝書類申請・10点)", "docs"
    if s.startswith("PASS"):
        return "OK", "open"
    if s.startswith("FAIL"):
        return "NG(新品の申請経路なし＝「受け付けていません」に「その他の商品」)", "closed"
    raise ValueError(f"ゲート欄が読めない: {s!r}")


def parse_cart(s: str) -> tuple[str, str]:
    """(カートあり Y/N, 保持者)。"""
    s = s.strip()
    m = re.match(r"PASS（第三者：(.+?)）?$", s)
    if m:
        return "Y", m.group(1).rstrip("）")
    if s.startswith("FAIL") and "Amazon" in s:
        return "Y", "Amazon.co.jp"
    if s.startswith("UNKNOWN") and "カートなし" in s:
        return "N", "カートなし"
    raise ValueError(f"カート欄が読めない: {s!r}")


def parse_offers(s: str) -> dict:
    m = re.match(r"新品(\d+)件・(本体なし|本体あり)・カート出荷(.+)$", s.strip())
    if not m:
        return {}
    return {"n": int(m.group(1)), "amazon": m.group(2), "ship": m.group(3)}


def build(rows: list[dict], checked_at: str, by: str, src_name: str):
    carts, gates, recs, warn = [], [], {}, []
    for r in rows:
        a = r["ASIN"].strip()
        g_txt, g_kind = parse_gate(r["#1-2ゲート"])
        if g_kind == "docs" and r.get("ブランド(画面)", "").strip():
            g_txt = f"OK(ブランド {r['ブランド(画面)'].strip()} 出品許可が必要＝書類申請・10点)"
        gates.append({"ASIN": a, "新品の出品可否": g_txt,
                      "判定方法": "restrictions/approve?itemcondition=New",
                      "確認時刻": checked_at, "確認者": f"{by}(セラーセントラル実画面)"})
        yn, holder = parse_cart(r["#5カート"])
        off = parse_offers(r["#7内訳"])
        note = f"{src_name} から転記（タカシ）"
        if off:
            note += f"。出品一覧：新品{off['n']}件・{off['amazon']}・カート出荷{off['ship']}"
        # カズヨは「第三者」と読んだが、名前がブランドと重なる行は疑いとして残す（確定は人）
        sus = SC.maker_suspect(holder, r.get("ブランド(画面)", ""), "") if yn == "Y" else ""
        if sus:
            note += f"。メーカー本人の疑い：{sus}"
            warn.append((a, sus))
        carts.append({"ASIN": a, "カートあり": yn, "カート保持者(実画面)": holder, "カート価格": "",
                      "過去1か月(実画面・下限)": "", "確認時刻": checked_at,
                      "確認者": f"{by}(Chrome実画面)", "注意": note, "アマゾン直販(キーゾン)": "",
                      "新品出品者数(出品一覧)": off.get("n", ""),
                      "Amazon本体(出品一覧)": {"本体なし": "なし", "本体あり": "あり"}.get(off.get("amazon"), "")})
        recs[a] = (g_kind, yn, holder, off, sus)
    return carts, gates, recs, warn


def write_records(recs: dict, day: str, by_id: str) -> int:
    """_sourcing_checks/<ASIN>.json に4項目を書く（前の値は history へ・check_record.py と同じ流儀）。"""
    n = 0
    for a, (g_kind, yn, holder, off, sus) in recs.items():
        url = GATE_URL.format(a=a)
        gt = {"open": ("なし（新品出品可）", "PASS"),
              "docs": ("書類申請（ブランド出品許可・請求書10点）", "PASS"),
              "closed": ("受付停止（新品の申請経路なし）", "FAIL")}[g_kind]
        lb = {"open": ("新品で出品できる（restrictions/approve）", "PASS"),
              "docs": ("申請で開く（restrictions/approve）", "PASS"),
              "closed": ("申請できない（「その他の商品」が受け付けていません）", "FAIL")}[g_kind]
        if yn == "N":
            bb = ("カートなし（おすすめ出品が出ていない）", "UNKNOWN")
        elif "Amazon.co.jp" in holder:
            bb = ("Amazon.co.jp", "FAIL")
        elif sus:
            bb = (f"第三者 {holder}（メーカー本人の疑い）", "UNKNOWN")
        else:
            bb = (f"第三者 {holder}", "PASS")
        items = {"gate_type": (*gt, url), "listing_button": (*lb, url),
                 "buybox_seller": (*bb, f"https://www.amazon.co.jp/dp/{a}")}
        if off:
            items["new_offer_count"] = (
                f"計{off['n']}＝{off['amazon']}／カート出荷{off['ship']}"
                "（FBA・即納の自己発送・取り寄せの本数は未計数）", "UNKNOWN",
                f"https://www.amazon.co.jp/gp/offer-listing/{a}/?f_new=true")
        rec = gate.load_record(a)
        cur = rec.setdefault("items", {})
        for k, (v, res, src) in items.items():
            if k in cur:
                rec.setdefault("history", []).append({"item_id": k, **cur[k]})
            cur[k] = {"value": v, "result": res, "source": src, "checked_at": day,
                      "checked_by": by_id, "note": "browser_results_import.py（カズヨ実画面の転記）"}
        rec["asin"] = a
        p = gate.record_path(a)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tsv", type=Path)
    ap.add_argument("--tag", required=True, help="出力ファイル名の後ろ（例 20261015_browser）")
    ap.add_argument("--checked-at", required=True, help="確認日時 YYYY-MM-DD HH:MM")
    ap.add_argument("--by", default="カズヨ")
    ap.add_argument("--by-id", default="kazuyo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(a.tsv.open(encoding="utf-8"), delimiter="\t"))
    carts, gates, recs, warn = build(rows, a.checked_at, a.by, a.tsv.name)
    both = sum(1 for g, y, h, o, s in recs.values() if g != "closed" and y == "Y"
               and "Amazon" not in h and not s)
    print(json.dumps({"行": len(rows), "ゲート": Counter(v[0] for v in recs.values()),
                      "カート": Counter(v[1] for v in recs.values()),
                      "ゲート可かつ第三者カート": both, "メーカー疑い": warn},
                     ensure_ascii=False, default=str))
    if a.dry_run:
        return 0
    for name, cols, data in (("cart_check", CART_COLS, carts), ("gate_check", GATE_COLS, gates)):
        p = SC.OUT / f"{name}_{a.tag}.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
        print("書きました", p)
    print("確認記録", write_records(recs, a.checked_at[:10], a.by_id), "件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
