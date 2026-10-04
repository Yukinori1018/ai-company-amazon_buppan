#!/usr/bin/env python3
"""メーカー連絡先台帳の「採算列」を代表ASIN単位で計算する（T-20260930-001 / 経理ハジメ / 2026-10-04）。

社長がメーカーに電話・メールする前に「いくらで卸してもらえれば儲かるか」を一目で分かるようにする。
式・前提・置き値の根拠は同フォルダ 41_採算列の計算式.md。

入力（agent_output/T-20260930-001/。Git 除外）
  30_最終_50社.csv / 22_連絡先_印付き.csv / 24_連絡先_*.csv  … 列「代表ASIN(タカシ)」「新品出品数(実画面)」
                                                              「過去1ヶ月の販売数(実画面9/30)」
  raw/prod_*.json.gz（Keepa product・stats=365）               … 既存キャッシュ。無い ASIN だけ取得
出力
  agent_output/T-20260930-001/40_採算列.csv（キー＝代表ASIN。Keepa の値を含むので Git 除外）

実行
  python3 workspace/output/deliverables/T-20260930-001/40_profit_cols.py            # 不足分は取得（上限300）
  python3 workspace/output/deliverables/T-20260930-001/40_profit_cols.py --offline  # 取得しない
  --max-fetch N で取得上限を変える。取得は1 token/ASIN（stats=365・history=0・offers なし）。
  取得したものは raw/prod_profit_<hash>.json.gz に保存し、二度と取らない。
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in [HERE, *HERE.parents] if (p / "CLAUDE.md").exists())
WORK = REPO / "workspace/output/agent_output/T-20260930-001"
RAW = WORK / "raw"
OUT = WORK / "40_採算列.csv"
INPUTS = ["30_最終_50社.csv", "22_連絡先_印付き.csv"]  # ＋ 24_連絡先_*.csv（glob）

TAX = 1.1

# ── 前提（置き値）。変えるときはここだけ直し、41_採算列の計算式.md も直す ──────────────
TARGET_KPI = 0.20          # 会社KPI 利益率20%
TARGET_FIRST = 0.10        # 初回の妥協ライン（中村本：初回5〜8%でも可 → 10%で置く）
TARGET_TEST = 0.05         # テスト仕入れの基準（CLAUDE.md §3.5：見積りが利益率5%以上なら5〜10個）
MIN_FIRST_LOT = 5          # 初回の最小個数
# 納品・その他（1個あたり・税込）。§3.4：初回は自宅検品→社長宅から FBA へ発送
INBOUND_BOX_YEN = 608      # FBAパートナーキャリア ヤマト 140サイズ1箱（関東→関東の実測・cost_model_v2）
BOX_MATERIAL_YEN = 250     # 段ボール1枚（推定）
UNIT_MATERIAL_YEN = 4.5    # OPP袋＋α（推定）
LABEL_YEN = {"小型標準": 22, "大型": 51}  # Amazon 商品ラベル貼付サービス（公式・税込）
BOX_VOL_CM3 = 94500        # 140サイズの内容積
FILL_RATE = 0.70           # 箱の実装率（仮定）
OTHER_FLOOR_YEN = 100      # 置き値の下限（初回ロット＝少数の箱で送る前提を丸めた値）
# 保管料（公式・税込・円/1,000cm³/月）。10〜12月（繁忙期）単価で置く＝初回在庫は年内に置かれるため
STORAGE_RATE = {"小型標準": 10.087, "大型": 6.984}

# FBA配送代行（公式・税込。1,000円超 / 1,000円以下）。Keepa の pickAndPackFee から区分を逆引きする
FBA = {
    "小型": (288, 222), "標準1": (318, 252), "標準2": (410, 344), "標準3": (415, 358),
    "標準4": (420, 371), "標準5": (425, 379), "標準6": (430, 391), "標準7": (472, 427),
    "標準8": (532, 466), "大型1": (589, 523), "大型2": (624, 558), "大型3": (675, 609),
    "大型4": (781, 715), "大型5": (1020, 954), "大型6": (1100, 1034), "大型7": (1532, 1466),
    "大型8": (1756, 1690),
}
REF_TIERS = [5.0, 8.4, 10.4, 12.4, 15.4, 45.4]   # 公式の販売手数料率（税抜表示）

OUT_COLS = [
    "代表ASIN", "正式社名", "出典CSV", "判定", "カテゴリ(Keepa)",
    "平時売価(円・税込)", "平時売価の出典", "現在価格(円・税込)", "価格の安定(現在÷90日平均)", "価格の状態",
    "販売手数料率(%・税抜表示)", "販売手数料率の出典", "販売手数料(円・税込)",
    "FBA配送代行(円・税込)", "FBAサイズ区分", "FBAの出典",
    "保管料(円/個・10-12月単価)", "納品・その他(円/個)", "Amazon側コスト計(円/個)",
    "利益率20%の上限卸値(円・税込)",
    "利益率20%の上限卸値_税抜換算(円)",
    "利益率10%の上限卸値(円・税込)",
    "利益率5%の上限卸値(円・税込)",
    "損益分岐の卸値(円・税込)",
    "20%が取れる掛け(目標)",
    "月販下限(個/月)", "月販の出典", "新品出品者数", "出品者数の出典",
    "想定月販(個/月)", "1個利益_20%時(円)", "想定月利益_20%時(円/月)",
    "初回仕入れ個数", "初回仕入れ金額_20%上限(円・税込)", "採算メモ",
]


# ── 入力 ────────────────────────────────────────────────────────────────────────
def load_rows() -> list[dict]:
    files = [WORK / f for f in INPUTS] + [Path(p) for p in sorted(glob.glob(str(WORK / "24_連絡先_*.csv")))]
    rows, seen = [], set()
    for f in files:
        if not f.exists():
            continue
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            a = (r.get("代表ASIN(タカシ)") or r.get("代表ASIN") or "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", a) or a in seen:
                continue
            seen.add(a)
            r["_asin"], r["_src"] = a, f.name
            rows.append(r)
    return rows


def load_cache() -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for f in sorted(RAW.glob("prod*.json.gz")):
        try:
            d = json.loads(gzip.decompress(f.read_bytes()))
        except Exception:
            continue
        for p in (d.get("products") or []):
            if p and p.get("asin"):
                idx[p["asin"]] = p
    return idx


def fetch_missing(asins: list[str], max_fetch: int) -> int:
    """キャッシュに無い代表ASINだけを取る。残量を確認してから、上限 max_fetch token まで。"""
    sys.path.insert(0, str(HERE))
    import keepa_io  # noqa: E402  （同フォルダの薄いラッパー。API キーはリポ外）
    left = keepa_io.tokens_left()
    budget = min(max_fetch, max(0, left - 5))
    print(f"Keepa 残量 {left} token / 不足 {len(asins)} ASIN / 今回の上限 {budget}")
    got = 0
    todo = asins[:budget]
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        d = keepa_io._get("product", {"domain": 5, "asin": ",".join(chunk),
                                      "stats": 365, "history": 0})
        if d.get("error"):
            raise RuntimeError(d["error"])
        h = hashlib.sha1(",".join(chunk).encode()).hexdigest()[:10]
        (RAW / f"prod_profit_{h}.json.gz").write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False).encode()))
        got += len(d.get("products") or [])
        print(f"  取得 {len(chunk)}件 consumed {d.get('tokensConsumed')} left {d.get('tokensLeft')}")
    return got


# ── 計算部品 ────────────────────────────────────────────────────────────────────
def first_int(s: str) -> int | None:
    m = re.search(r"(\d[\d,]*)", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def snap_rate(x: float) -> float:
    """Keepa の率は小数点以下が揺れる（10.39/10.41 等）。公式の段へ寄せる。"""
    return min(REF_TIERS, key=lambda t: abs(t - x))


def category_rate(cat: str, price: float) -> float | None:
    """価格で料率が変わるカテゴリだけ、平時売価で引き直す（Keepa の率は現在価格で計算されているため）。"""
    if price <= 750:
        return 5.0
    if cat in ("ビューティー", "ドラッグストア", "食品・飲料・お酒"):
        return 8.4 if price <= 1500 else 10.4
    if cat in ("ペット用品", "ベビー＆マタニティ", "ベビー&マタニティ"):
        return 8.4 if price <= 1500 else 15.4
    return None


def fba_lookup(pick: int | None, price: float) -> tuple[float | None, str, str]:
    if not pick or pick <= 0:
        return None, "", "Keepa値なし"
    for tier, (hi, lo) in FBA.items():
        if pick in (hi, lo):
            return float(hi if price > 1000 else lo), tier, "Keepa実測→区分逆引き→平時売価の列"
    return float(pick), "逆引き不可", "Keepa実測そのまま（料金表に無い額）"


def to_yen(x):
    return "" if x is None else int(round(x))


def compute(r: dict, p: dict | None) -> dict:
    o = {c: "" for c in OUT_COLS}
    o["代表ASIN"], o["出典CSV"] = r["_asin"], r["_src"]
    o["正式社名"] = r.get("正式社名") or r.get("メーカー名(タカシ)", "")
    o["判定"] = r.get("判定", "")
    if not p:
        o["採算メモ"] = "Keepa未取得（--offline または取得上限）→ 計算しない"
        return o
    s = p.get("stats") or {}
    a90, cur = s.get("avg90") or [], s.get("current") or []
    g = lambda arr, i: arr[i] if len(arr) > i and arr[i] is not None and arr[i] > 0 else None  # noqa: E731
    cat = ((p.get("categoryTree") or [{}])[0] or {}).get("name", "")
    o["カテゴリ(Keepa)"] = cat

    # 1. 平時売価：90日平均カート価格 → 無ければ新品最安の90日平均（現在価格は使わない）
    P, src = g(a90, 18), "カート価格90日平均"
    if P is None:
        P, src = g(a90, 1), "新品最安90日平均（カート90日平均が無い）"
    now = g(cur, 18) or g(cur, 1)
    if P is None:
        o["採算メモ"] = "平時売価が取れない → 計算しない"
        return o
    o["平時売価(円・税込)"], o["平時売価の出典"], o["現在価格(円・税込)"] = to_yen(P), src, to_yen(now)
    if now:
        st = now / P
        o["価格の安定(現在÷90日平均)"] = f"{st:.2f}"
        o["価格の状態"] = "値下がり中" if st < 0.95 else ("値上がり中" if st > 1.05 else "安定")

    # 2. 販売手数料：Keepa 実測率（公式の段へ寄せる）。価格帯で率が変わるカテゴリは平時売価で引き直し、高い方
    kr = p.get("referralFeePercentage") or p.get("referralFeePercent")
    rate, rsrc = (snap_rate(float(kr)), "Keepa実測") if kr else (None, "")
    cr = category_rate(cat, P)
    if cr is not None and (rate is None or P <= 750 or cr != rate):
        if P <= 750:
            rate, rsrc = 5.0, "750円以下は一律5%（公式）"
        elif rate is None or cr > rate:
            rate, rsrc = cr, f"平時売価で引き直し（Keepa {kr}）"
    if rate is None:
        rate, rsrc = 15.4, "不明→最高段15.4%で置く"
    ref_yen = max(P * rate / 100, 30) * TAX
    o["販売手数料率(%・税抜表示)"], o["販売手数料率の出典"], o["販売手数料(円・税込)"] = rate, rsrc, to_yen(ref_yen)

    # 3. FBA 配送代行
    fba, tier, fsrc = fba_lookup((p.get("fbaFees") or {}).get("pickAndPackFee"), P)
    if fba is None:
        o["採算メモ"] = "FBA手数料が取れない → 計算しない"
        o["FBAの出典"] = fsrc
        return o
    o["FBA配送代行(円・税込)"], o["FBAサイズ区分"], o["FBAの出典"] = to_yen(fba), tier, fsrc
    large = tier.startswith("大型") or (tier == "逆引き不可" and fba >= 589)

    # 8. 想定月販 = 月販下限 ÷（新品出品者数＋1）
    ms_raw = r.get("過去1ヶ月の販売数(実画面9/30)", "")
    ms, msrc = first_int(ms_raw), "実画面（階級の下限）"
    if ms is None and p.get("monthlySold"):
        ms, msrc = int(p["monthlySold"]), "Keepa monthlySold（実画面欄が空）"
    n_raw = (r.get("新品出品数(実画面)") or "").strip()
    n, nsrc = first_int(n_raw), "実画面"
    if n is None:
        c11 = g(cur, 11)
        n, nsrc = (int(c11), "Keepa COUNT_NEW（実画面は未確認）") if c11 else (None, "不明")
    o["月販下限(個/月)"], o["月販の出典"] = ms if ms is not None else "", msrc if ms is not None else "不明"
    o["新品出品者数"], o["出品者数の出典"] = n if n is not None else "", nsrc
    my = (ms / (n + 1)) if (ms is not None and n is not None) else None
    o["想定月販(個/月)"] = f"{my:.1f}" if my is not None else ""

    # 10. 初回個数（保管・納品の按分に使うので先に出す）
    lot = max(MIN_FIRST_LOT, math.ceil(my)) if my else MIN_FIRST_LOT

    # 保管料：実寸（パッケージ）×繁忙期単価×計上月数（＝消化月数÷2）
    L, W, H = (p.get("packageLength") or 0), (p.get("packageWidth") or 0), (p.get("packageHeight") or 0)
    vol = L * W * H / 1000 if L and W and H else None  # mm³→cm³
    months = (lot / my) / 2 if my else 3.0  # 月販不明は消化6ヶ月と置く
    stor = (STORAGE_RATE["大型" if large else "小型標準"] * (vol or 7280) / 1000 * months)
    o["保管料(円/個・10-12月単価)"] = to_yen(stor)

    # 3'. 納品・その他：初回ロットを1箱で送る前提（箱に入りきらなければ容量で割る）。下限100円
    cap = max(1, int(BOX_VOL_CM3 * FILL_RATE // (vol or 7280)))
    q = max(1, min(lot, cap))
    other = max(OTHER_FLOOR_YEN, INBOUND_BOX_YEN / q + BOX_MATERIAL_YEN / q + UNIT_MATERIAL_YEN
                + LABEL_YEN["大型" if large else "小型標準"])
    o["納品・その他(円/個)"] = to_yen(other)

    amz = ref_yen + fba + stor + other
    o["Amazon側コスト計(円/個)"] = to_yen(amz)

    # 4-6. 上限卸値（＝着値。卸→自宅の送料は卸値に含めて読む）。免税事業者なので税込で比較する
    cap20 = P * (1 - TARGET_KPI) - amz
    cap10 = P * (1 - TARGET_FIRST) - amz
    cap5 = P * (1 - TARGET_TEST) - amz
    be = P - amz
    o["利益率20%の上限卸値(円・税込)"] = to_yen(cap20)
    o["利益率20%の上限卸値_税抜換算(円)"] = to_yen(cap20 / TAX)
    o["利益率10%の上限卸値(円・税込)"] = to_yen(cap10)
    o["利益率5%の上限卸値(円・税込)"] = to_yen(cap5)
    o["損益分岐の卸値(円・税込)"] = to_yen(be)
    kake = cap20 / P
    o["20%が取れる掛け(目標)"] = f"{kake:.3f}"

    unit_profit = P * TARGET_KPI
    o["1個利益_20%時(円)"] = to_yen(unit_profit)
    if my is not None:
        o["想定月利益_20%時(円/月)"] = to_yen(my * unit_profit)
    o["初回仕入れ個数"] = lot
    o["初回仕入れ金額_20%上限(円・税込)"] = to_yen(lot * cap20) if cap20 > 0 else ""

    # 12. 採算メモ
    memo = []
    if cap20 <= 0:
        memo.append("20%不可（タダで仕入れても20%に届かない）")
    elif kake >= 0.6:
        memo.append(f"6掛けでも20%可（{kake*10:.1f}掛け以下）")
    elif kake >= 0.5:
        memo.append(f"5掛け台が必要（{kake*10:.1f}掛け以下）")
    else:
        memo.append(f"5掛け未満が必要（{kake*10:.1f}掛け以下）＝卸値交渉は困難")
    if P < 2200:
        memo.append("単価2,200円未満")
    if o["価格の状態"] == "値下がり中":
        memo.append("値下がり中＝現在価格で再計算要")
    if my is not None and my < 5:
        memo.append(f"取り分が月{my:.1f}個（小）")
    if tier == "逆引き不可":
        memo.append("FBA区分不明")
    if "引き直し" in rsrc or "750円以下" in rsrc:
        memo.append("料率を平時売価で補正")
    o["採算メモ"] = "／".join(memo)
    return o


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--max-fetch", type=int, default=300)
    a = ap.parse_args()
    rows = load_rows()
    idx = load_cache()
    miss = [r["_asin"] for r in rows if r["_asin"] not in idx]
    if miss and not a.offline:
        fetch_missing(miss, a.max_fetch)
        idx = load_cache()
    out = [compute(r, idx.get(r["_asin"])) for r in rows]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(out)
    done = sum(1 for o in out if o["利益率20%の上限卸値(円・税込)"] != "")
    print(f"{OUT.name}: {len(out)}行（計算できた {done} 行・Keepa 未取得 {len(miss)} 件）")


if __name__ == "__main__":
    main()
