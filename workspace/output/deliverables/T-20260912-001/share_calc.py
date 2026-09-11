#!/usr/bin/env python3
"""S3: 出品ゲートで落ちた12件（＋出品可1件）の「取り分」と10点ロットの回転月数。T-20260912-001

    取り分(個/月) = 30日ドロップ数 ÷ (新品オファー数 + 1)
    回転月数      = 10 ÷ 取り分

- 入力は既存データの再計算のみ。
  ・スキャン時点の値: T-20260831-006/out/candidates.csv（order_set.py の「月販見込(推定)」と同値になる）
  ・親子関係と Amazon 公表の月間購入数: agent_output/T-20260912-001/gate13_raw.json（2026-09-12・13 token）
- 金額・Keepa 加工値はこのファイルに書かない（PUBLIC リポ）。結果は out/ にだけ出す。

読むときの注意（memory: keepa_salesrankdrops_is_polling_not_sales / keepa_count_new_is_not_seller_count）
- ドロップ数は販売数ではなく Keepa の観測回数に近い。量の推定としては弱い。足切りの目安にだけ使う。
- 新品オファー数は出品者数の上限（1社が FBA/FBM で2本出すと2）。実セラー数はこれ以下なので、
  ここで出す取り分は「控えめ側」の値。
- バリエーションの子は兄弟とランキングを共有する。子のドロップ数は兄弟の売上で動くので信用しない。
"""
import csv, html, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCAN = REPO / "workspace/output/deliverables/T-20260831-006/out/candidates.csv"
RAW = REPO / "workspace/output/agent_output/T-20260912-001/gate13_raw.json"
OUT = HERE / "out"

LOT = 10            # 10点ロット（出品単位で10）
CUT = 6.0           # タケシ案の足切り: 取り分 月6個以上
GATE_OPEN = {"B01N5Q71SY"}   # 2026-09-12 実機確認で出品可だった1件（比較用に並べる）
GATE13 = ("B0BKZFXC4P B001CNJKOG B0CH7PQNZY B0CH7XM4HT B0DYNG386S B01M3Z3Z9A "
          "B01N5Q71SY B003B6QSOW B00AIFX5D6 B00W8XO8MS B08YY1WD7T B00EL3KAUW B08MT316P9").split()


def share(drops, offers):
    return drops / (offers + 1) if drops else 0.0


def months(sh):
    return LOT / sh if sh > 0 else float("inf")


def main():
    scan = {r["ASIN"]: r for r in csv.DictReader(open(SCAN, encoding="utf-8-sig"))}
    live = {p["asin"]: p for p in json.load(open(RAW))["products"]}
    rows = []
    for a in GATE13:
        s, p = scan[a], live[a]
        st = p.get("stats") or {}
        cur = st.get("current") or []
        drops, offers = int(s["月間販売数(30日ランク下落数)"] or 0), int(s["出品者数"] or 0)
        drops_now, offers_now = st.get("salesRankDrops30") or 0, (cur[11] if len(cur) > 11 else 0) or 0
        sh, sh_now = share(drops, offers), share(drops_now, offers_now)
        parent = p.get("parentAsin")
        ms = p.get("monthlySold")
        sh_ms = ms / (offers_now + 1) if ms else None
        rows.append({
            "ASIN": a, "商品名": s["商品名"][:40], "ゲート": "出品可" if a in GATE_OPEN else "ブランド許可が必要",
            "バリエーション": f"子（親 {parent}・兄弟{len(p.get('variations') or [])}）" if parent else "単体",
            "ドロップ数の信用": "×（子なので兄弟の売上でも動く）" if parent else "○（単体）",
            "出品の入数": s["出品の入数"],
            "30日ドロップ(スキャン時)": drops, "新品オファー数(スキャン時)": offers,
            "取り分(個/月)": round(sh, 2), "10点の回転月数": round(months(sh), 1),
            "足切り6以上": "残る" if sh >= CUT else "落ちる",
            "30日ドロップ(9/12)": drops_now, "新品オファー数(9/12)": offers_now,
            "取り分_9/12": round(sh_now, 2), "10点の回転月数_9/12": round(months(sh_now), 1),
            "Amazon公表の月間購入数": ms if ms else "表示なし",
            "公表値ベースの取り分(参考)": round(sh_ms, 1) if sh_ms else "",
        })
    OUT.mkdir(exist_ok=True)
    with open(OUT / "01_S3_ゲート13件_取り分.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    write_html(rows)
    pas = [r for r in rows if r["足切り6以上"] == "残る"]
    print(f"足切り6以上: {len(pas)}件 / 13件（うち単体 {sum(1 for r in pas if r['ドロップ数の信用'].startswith('○'))}件）")
    for r in rows:
        print(r["ASIN"], r["取り分(個/月)"], r["10点の回転月数"], r["足切り6以上"], r["バリエーション"], r["Amazon公表の月間購入数"])


def write_html(rows):
    head = "".join(f"<th>{html.escape(k)}</th>" for k in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in rows)
    (OUT / "01_S3_ゲート13件_取り分.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>S3 取り分と回転月数</title>
<style>body{{font:14px/1.6 -apple-system,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;font-size:12.5px}}td,th{{border:1px solid #ccc;padding:4px 6px;white-space:nowrap}}
th{{background:#f3f3f3}}.f{{background:#f7f7f2;border-left:4px solid #999;padding:8px 12px;font-family:monospace}}
.w{{overflow-x:auto}}</style>
<h1>S3 出品ゲート13件の取り分と10点ロットの回転月数</h1>
<div class="f">取り分(個/月) ＝ 30日ドロップ数 ÷ (新品オファー数 + 1)<br>
回転月数 ＝ 10 ÷ 取り分　　足切り: 取り分 ≧ {CUT:g}（＝回転 {LOT/CUT:.2f}ヶ月以内）</div>
<p>主の列はスキャン時点の値（order_set.py の「月販見込(推定)」と同じ）。9/12 の列は同じ式を当日の値で再計算したもの。<br>
<b>ドロップ数は販売数ではありません</b>（Keepa の観測回数に近い）。新品オファー数は出品者数の上限なので、取り分は控えめ側です。<br>
バリエーションの子は兄弟とランキングを共有するため、ドロップ数を信用しない（列「ドロップ数の信用」）。<br>
「Amazon公表の月間購入数」は商品ページの「過去1か月で◯点購入」の下限値。子の場合、親子共有かどうかは未検証。</p>
<div class="w"><table><tr>{head}</tr>{body}</table></div>""", encoding="utf-8")


if __name__ == "__main__":
    main()
