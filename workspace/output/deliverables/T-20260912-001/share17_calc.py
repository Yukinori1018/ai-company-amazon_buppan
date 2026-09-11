#!/usr/bin/env python3
"""S3（本丸）: 第一陣20社のうち Amazon にブランドが実在する17社の取り分と10点ロットの回転月数。T-20260912-001

入力: agent_output/T-20260912-001/raw17/<社名>.json（Keepa 生レスポンス・Git 追跡外・2026-09-12 取得）
      取得スクリプトは agent_output/T-20260912-001/code/fetch17.py
代表のさせ方: ブランド（3社は製造元）完全一致で Product Finder → 売れ筋ランク順の上位10件（ランク無しは除く）
出力: out/02_S3_第一陣17社_取り分.csv / .html（Git 追跡外。数値はここにだけ出す）

物差しは3つ並べる（どれで足切りするかは社長とタケシが決める）
  ① 取り分(ドロップ)  = 30日ドロップ数 ÷ (新品オファー数 + 1)   … 既存出品者と並ぶ前提
  ② 月販総量(ドロップ) = 30日ドロップ数（割らない）              … 独占が取れた場合の上限寄り
  ③ Amazon 公表の「過去1か月で◯点購入」（monthlySold）          … 取れない行は空欄。推定で埋めない
  回転月数 = 10 ÷ 各物差し

注意（memory: keepa_salesrankdrops_is_polling_not_sales / keepa_product_finder_fields の monthlySold 節）
- ドロップ数は販売数ではなく観測回数に近い。
- バリエーションの子は兄弟とランクを共有するので、子の値は「兄弟合計の上限」扱い。
- monthlySold は階級の下限値（50 は 50〜99）で、値はバリエーション単位。
"""
import csv, html, json, statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[3] / "workspace/output/agent_output/T-20260912-001/raw17"
OUT = HERE / "out"
LOT, CUT = 10, 6.0
ORDER = ["大橋量器", "木村硝子店", "楠橋紋織", "七福タオル", "金野タオル", "北尾化粧品部", "高柳製茶", "北陸製菓",
         "宇野刷毛ブラシ製作所", "廣田硝子", "守田漆器", "池本刷子工業", "木内籐材工業", "朝倉染布", "河野製紙",
         "小野甚味噌醤油醸造", "田中帽子店"]


def mon(x):
    return round(LOT / x, 1) if x else ""


def rows_for(d):
    out = []
    for p in d["products"]:
        st = p.get("stats") or {}
        cur = st.get("current") or []
        rank = cur[3] if len(cur) > 3 else None
        drops = st.get("salesRankDrops30") or 0
        offers = max((cur[11] if len(cur) > 11 else 0) or 0, 0)
        ms = p.get("monthlySold")
        parent = p.get("parentAsin")
        sh = drops / (offers + 1)
        out.append({
            "社": d["company"], "ASIN": p["asin"], "商品名": (p.get("title") or "")[:40],
            "brand": p.get("brand") or "", "売れ筋ランク": rank if rank and rank > 0 else "",
            "バリエーション": f"子（親 {parent}）※値は兄弟合計の上限" if parent else "単体",
            "30日ドロップ": drops, "新品オファー数": offers,
            "①取り分(ドロップ÷(オファー+1))": round(sh, 2), "①10点の回転月数": mon(sh),
            "②月販総量(ドロップ・割らない)": drops, "②10点の回転月数": mon(drops),
            "③Amazon公表の月間購入数": ms if ms else "",
            "③÷(オファー+1)(参考)": round(ms / (offers + 1), 1) if ms else "",
            "③10点の回転月数": mon(ms) if ms else "",
            "①≧6": "○" if sh >= CUT else "", "②≧6": "○" if drops >= CUT else "", "③≧6": "○" if ms and ms >= CUT else "",
        })
    return out


def summary(d, rs):
    sh = [r["①取り分(ドロップ÷(オファー+1))"] for r in rs]
    dr = [r["②月販総量(ドロップ・割らない)"] for r in rs]
    return {
        "社": d["company"],
        "代表のさせ方": f"{d['field']}＝「{d['value']}」",
        "該当ASIN数(ランクあり)": d["totalResults"] if d["field"] in ("brand", "manufacturer") else f"search20件中 {len(rs)}",
        "取った件数": len(rs),
        "うち子": sum(r["バリエーション"] != "単体" for r in rs),
        "①取り分 中央値": round(statistics.median(sh), 2) if sh else "", "①取り分 最大": max(sh) if sh else "",
        "①≧6 件数": sum(r["①≧6"] == "○" for r in rs),
        "②月販総量 中央値": statistics.median(dr) if dr else "", "②月販総量 合計": sum(dr),
        "②≧6 件数": sum(r["②≧6"] == "○" for r in rs),
        "③公表値あり件数": sum(r["③Amazon公表の月間購入数"] != "" for r in rs),
        "③≧6 件数": sum(r["③≧6"] == "○" for r in rs),
        "①≧6 かつ単体": sum(r["①≧6"] == "○" and r["バリエーション"] == "単体" for r in rs),
    }


def table(rows):
    head = "".join(f"<th>{html.escape(k)}</th>" for k in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in rows)
    return f'<div class="w"><table><tr>{head}</tr>{body}</table></div>'


def main():
    detail, summ = [], []
    for name in ORDER:
        d = json.load(open(RAW / f"{name}.json", encoding="utf-8"))
        rs = rows_for(d)
        detail += rs
        summ.append(summary(d, rs))
    OUT.mkdir(exist_ok=True)
    with open(OUT / "02_S3_第一陣17社_取り分.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0])); w.writeheader(); w.writerows(detail)
    with open(OUT / "02_S3_第一陣17社_社別集計.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
    (OUT / "02_S3_第一陣17社_取り分.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>S3 第一陣17社の取り分</title>
<style>body{{font:14px/1.6 -apple-system,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;font-size:12.5px}}td,th{{border:1px solid #ccc;padding:4px 6px;white-space:nowrap}}
th{{background:#f3f3f3}}.f{{background:#f7f7f2;border-left:4px solid #999;padding:8px 12px;font-family:monospace}}
.w{{overflow-x:auto}}</style>
<h1>S3 本丸 第一陣17社の取り分と10点ロットの回転月数（2026-09-12 Keepa 取得）</h1>
<div class="f">① 取り分 ＝ 30日ドロップ数 ÷ (新品オファー数 + 1)　… 既存の出品者と並ぶ前提<br>
② 月販総量 ＝ 30日ドロップ数（割らない）　… 独占が取れた場合。本丸はこちら寄り<br>
③ Amazon 公表の「過去1か月で◯点購入」　… 取れない行は空欄（推定で埋めていない）<br>
回転月数 ＝ 10 ÷ 各物差し　　足切り候補: 各物差し ≧ {CUT:g}（＝回転 {LOT/CUT:.2f}ヶ月以内）</div>
<p><b>ドロップ数は販売数ではありません</b>（Keepa の観測回数に近い）。新品オファー数は出品者数の上限なので①は控えめ側です。<br>
<b>バリエーションの子の値は「兄弟合計の上限」</b>です。兄弟を別 SKU と数えると同じ需要を二重に数えます。<br>
③は階級の下限値（50 は 50〜99）で、値はバリエーション単位です。<br>
代表のさせ方: ブランド（宇野・守田・木内は製造元）の完全一致で Product Finder を引き、売れ筋ランク順の上位10件（ランク無しは除外）。
宇野刷毛・守田漆器は製造元一致の出品が全件ランク無し（＝販売が観測されていない）ため0件です（/search 20件で確認）。</p>
<h2>社別の集計</h2>{table(summ)}
<h2>ASIN ごとの値（{len(detail)}件）</h2>{table(detail)}""", encoding="utf-8")
    for s in summ:
        print(s)


if __name__ == "__main__":
    main()
