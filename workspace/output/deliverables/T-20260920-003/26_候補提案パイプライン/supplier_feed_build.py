#!/usr/bin/env python3
"""仕入れ先起点の結果を、台帳の引き直し（ledger_refresh.py）とカズヨの Chrome キューに渡す口。通信0。

2026-10-12 サトル（T-20260920-003・NETSEA 停止中に他の経路を厚くする）。

サブコマンド
------------
    python3 supplier_feed_build.py kokubu-input     # 国分の照会結果 → supplier_screen の入力 CSV
    python3 supplier_feed_build.py kokubu-route     # 国分の screen 結果 → kokubu_route_override_<日付>.csv
    python3 supplier_feed_build.py feed <screen CSV ...>   # 台帳外の ASIN → new_supplier_candidates_<日付>.csv
    python3 supplier_feed_build.py sd-queue <screen CSV ...>  # SD 出展企業の行 → sd_queue_<日付>.csv（Chrome 用）

数字の扱い
----------
- 国分の卸1点＝**バラ単価（実測）＋送料の按分（実測の送料表 ÷ 1ケースの入数）**。按分は1ケース
  だけ買う前提＝一番高く付く側。按分前のバラ単価と送料はメモ列に分けて書く（推定値は入れない）
- SD キューの上限値は Keepa 実測の売価（90日中央値・下位25%）と公式手数料からの逆算（sd_score と同じ式）。
  **卸値の推定ではない**。NETSEA の卸値（10/01）は別の経路の実測値として「参考」列に分けて置く

🔴 出力には卸値・購入先URL が入るので **agent_output にだけ置く**（PUBLIC リポ）。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
KOK = WORK / "kokubu"
LED = WORK / "ledger20261010"
SS_DIR = WORK / "supplier_screen"
SDB = WORK / "sd_buylist20261009"
STAMP = date.today().strftime("%Y%m%d")

#: 国分ネット卸の送料（税抜・関東＝おりおん立川あて・1回の注文）。出典 buylist20261009/kokubu_terms_private.md
#: （guide.aspx 2026-10-09 取得）。値は agent_output の写しから読む（リポに額を置かない）
KOKUBU_TERMS = WORK / "buylist20261009/kokubu_terms_private.md"

#: SD で卸値が見える出展企業（2026-10-11 仕入れ先台帳）と NETSEA 上の同じ会社の店名
SD_DEALERS = {
    "Drop ハリマ共和物産（株）顧客直送": ("ハリマ共和物産", "204961"),
    "株式会社 ヤザワコーポレーション": ("ヤザワコーポレーション", "203333"),
    "不二貿易株式会社": ("不二貿易", "未記録"),
}


def kokubu_ship_table() -> list[tuple[int, int]]:
    """[(上限(税抜・未満), 関東の送料)]。表の1列目（関東ほか）だけ読む。"""
    t = KOKUBU_TERMS.read_text()
    out = []
    for m in re.finditer(r"^\|\s*([\d,]+)円未満\s*\|\s*([\d,]+)\s*\|", t, re.M):
        out.append((int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))))
    for m in re.finditer(r"^\|\s*[\d,]+〜([\d,]+)円未満\s*\|\s*([\d,]+)\s*\|", t, re.M):
        out.append((int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))))
    m = re.search(r"^\|\s*([\d,]+)円以上\s*\|\s*([\d,]+)\s*\|", t, re.M)
    if m:
        out.append((10 ** 9, int(m.group(2).replace(",", ""))))
    return sorted(out)


def ship_for(amount: float, table: list[tuple[int, int]]) -> int | None:
    for lim, yen in table:
        if amount < lim:
            return yen
    return None


def kokubu_latest() -> dict[str, dict]:
    out = {}
    for line in (KOK / "lookup.jsonl").open():
        o = json.loads(line)
        out[o["jan"]] = o          # 後勝ち＝新しい取得
    return out


def kokubu_input() -> Path:
    """国分で「有り」の JAN を supplier_screen の標準形に。酒類は入れない（法務判定50 §2.3）。"""
    table = kokubu_ship_table()
    rows = []
    for j, o in kokubu_latest().items():
        if o.get("status") != "有り" or o.get("酒類") or not o.get("販売価格バラ(税抜)"):
            continue
        bara, case = o["販売価格バラ(税抜)"], o.get("販売価格(税抜)") or o["販売価格バラ(税抜)"]
        n = o.get("入数(販売価格÷バラ)") or 1
        ship = ship_for(case, table)
        eff = round(bara + (ship or 0) / n, 1)
        rows.append({
            "JAN": j, "卸単価(税抜)": eff, "入数": "", "最小ロット": n, "卸の商品名": o.get("name") or "",
            "仕入れ先": "問屋 国分ネット卸", "卸サイト": "国分ネット卸",
            "購入先URL": f"https://netton.kokubu.jp/shop/g/g{j}/", "在庫": o.get("在庫") or "不明",
            "上代(税抜)": "", "卸値の確認日": o.get("fetched_day") or "",
            "備考": (f"バラ単価 {bara}円＋送料 {ship}円÷{n}点（1ケース・関東・送料表 2026-10-09）"
                   f"／カテゴリ {o.get('category', '')}／賞味期限 {o.get('賞味期限', '')}"),
        })
    import supplier_inputs as SI
    dst = SS_DIR / f"input_kokubu_{STAMP}.csv"
    SI.write(rows, dst)
    print(f"国分 {len(rows)}行 → {dst}")
    return dst


def kokubu_route(screen: Path) -> Path:
    """screen_kokubu の ASIN ごとに、ledger_refresh が読む経路切り替えの行を書く。"""
    look = kokubu_latest()
    stock_map = {"在庫あり": "在庫あり", "品切れ（在庫お問合せ）": "品切れ", "取り寄せ": "取り寄せ"}
    out = []
    for r in csv.DictReader(screen.open(encoding="utf-8-sig")):
        j = r.get("JAN") or ""
        o = look.get(j)
        if not o:
            continue
        per = float(r["卸の1点あたり原価(税込)"]) / 1.1
        out.append({
            "ASIN": r["ASIN"], "JAN": j, "SD品番": "", "購入先URL": f"https://netton.kokubu.jp/shop/g/g{j}/",
            "卸価格_税抜_1点": round(per, 1), "卸の最小ロット(点)": o.get("入数(販売価格÷バラ)") or 1,
            "在庫": stock_map.get(o.get("在庫") or "", "未確認"), "確認時刻": o.get("fetched") or "",
            "確認者": "サトル（kokubu_lookup.py）", "メモ": r.get("卸の備考") or "",
            "卸サイト": "国分ネット卸", "仕入れ先": "問屋 国分ネット卸", "卸の商品名": o.get("name") or "",
        })
    dst = KOK / f"kokubu_route_override_{STAMP}.csv"
    with dst.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0].keys()) if out else ["ASIN"])
        w.writeheader()
        w.writerows(out)
    print(f"国分の経路切り替え {len(out)}行 → {dst}")
    return dst


def ledger_asins() -> set[str]:
    snaps = sorted(list(LED.glob("after_*.json")) + list(LED.glob("before_*.json")),
                   key=lambda p: p.stat().st_mtime)
    rows = json.loads(snaps[-1].read_text())
    i = rows[0].index("ASIN")
    return {r[i] for r in rows[1:] if len(r) > i}


def feed(screens: list[Path]) -> Path:
    led = ledger_asins()
    seen, out = set(), []
    for p in screens:
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            a = r["ASIN"]
            if a in led or a in seen:
                continue
            seen.add(a)
            out.append({"ASIN": a, "JAN": r.get("JAN") or "", "仕入れ先": r.get("購入元の名前") or "",
                        "卸サイト(入力)": r.get("卸サイト") or "", "screen判定": r.get("判定") or "",
                        "screen落ちた理由": r.get("落ちた理由") or "", "出所": p.name})
    dst = LED / f"new_supplier_candidates_{STAMP}.csv"
    with dst.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(out[0].keys()) if out else ["ASIN"])
        w.writeheader()
        w.writerows(out)
    print(f"台帳外 {len(out)} ASIN → {dst}")
    return dst


#: 卸値が決まれば判定が動く（＝価格以外では落ちていない）とみなす落ちた理由
PRICE_ONLY = ("採算", "仕入れ", "")


def sd_queue(screens: list[Path]) -> Path:
    """SD 出展企業（卸値が見える社）の商品で、価格以外では落ちていない行を Chrome キューにする。"""
    sys.path.insert(0, str(SDB))
    import supplier_screen as SS
    import price_history as PH
    import fba_cost
    import sd_score as SDS
    rows = []
    for p in screens:
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            sup = r.get("購入元の名前") or ""
            if sup not in SD_DEALERS:
                continue
            ff = (r.get("落ちた理由") or "").split("（")[0]
            if ff not in PRICE_ONLY:
                continue
            rows.append(r)
    asins = {r["ASIN"] for r in rows}
    latest, _ = SS.load_by_asin(asins)
    out = []
    for r in rows:
        c = latest.get(r["ASIN"])
        cap = {}
        if c:
            pr = c.product
            lv = PH.from_product(pr)
            sell, bad = lv.sell_for_profit, lv.sell_pessimistic
            fee_pct = pr.get("referralFeePercentage")
            tier = fba_cost.tier_from_fba_fee((pr.get("fbaFees") or {}).get("pickAndPackFee"), sell)
            n = float(r.get("Amazon側のセット数") or 0) or None
            if sell and tier and n:
                cat = SDS.category_of(pr)
                k = dict(category=cat, keepa_pct=fee_pct, months=3.0)
                zero = SDS.max_unit_cost_incl(sell, tier, worst=False, margin=0.0, **k)
                b = SDS.max_unit_cost_incl(sell, tier, worst=False, margin=fba_cost.MIN_MARGIN_B, **k)
                a_mid = SDS.max_unit_cost_incl(sell, tier, worst=False, **k)
                a_bad = SDS.max_unit_cost_incl(bad or sell, tier, worst=True, **k)
                to_pt = lambda x: round(x / 1.1 / n) if x and x > 0 else "成立しない"  # noqa: E731
                cap = {"実績枠の卸1点上限(税抜)": to_pt(zero), "B等級の卸1点上限(税抜)": to_pt(b),
                       "A等級の卸1点上限(税抜)": to_pt(min(a_mid, a_bad)), "売価90日中央値": sell}
        dealer, did = SD_DEALERS[r["購入元の名前"]]
        out.append({
            "ASIN": r["ASIN"], "JAN": r.get("JAN"), "商品名": r.get("商品名"),
            "SD出展企業": dealer, "SD出展ID": did,
            "SD検索URL": f"https://www.superdelivery.com/p/do/psl/?word={r.get('JAN')}",
            **cap,
            "NETSEA卸1点(税抜・10/01・参考)": round(float(r["卸の1点あたり原価(税込)"]) / 1.1)
            if r.get("卸の1点あたり原価(税込)") else "",
            "Amazon側のセット数": r.get("Amazon側のセット数"), "取り分(個/月)": r.get("取り分(個/月)"),
            "3か月平均(Keepa再現)": r.get("キーゾン 平均月販"), "カートの販売元": r.get("カートの販売元"),
            "NETSEA卸値での判定": r.get("判定"), "落ちた理由(NETSEA卸値)": r.get("落ちた理由"),
            "台帳に既存": r.get("台帳に既存"),
            "見てほしいこと": "SD の卸1点(税抜)・最小ロット・在庫。実績枠の上限以下なら GO（実績枠）の候補",
        })
    def key(x):
        try:
            return -float(x.get("取り分(個/月)") or 0)
        except ValueError:
            return 0
    out.sort(key=key)
    for i, x in enumerate(out, 1):
        x["順位"] = i
    dst = SDB / f"sd_queue_{STAMP}.csv"
    cols = ["順位"] + [k for k in (out[0].keys() if out else []) if k != "順位"]
    with dst.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols or ["順位"])
        w.writeheader()
        w.writerows(out)
    print(f"SD キュー {len(out)}行 → {dst}")
    return dst


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), [Path(x) for x in sys.argv[2:]]
    if cmd == "kokubu-input":
        kokubu_input()
    elif cmd == "kokubu-route":
        kokubu_route(args[0])
    elif cmd == "feed":
        feed(args)
    elif cmd == "sd-queue":
        sd_queue(args)
    else:
        print(__doc__)
