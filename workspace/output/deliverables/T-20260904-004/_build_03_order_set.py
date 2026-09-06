#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D_初回仕入れ_発注候補セット.csv ほか → 03_初回仕入れ_発注セットと全体まとめ.html を生成する。

CSV / JSON が唯一の正。この道具は表示を作るだけで、値の書き換え・要約・言い換えはしない。
セルに出す数字はすべて入力ファイルから読む（桁区切りの付与だけが加工。検証は数字列で照合する）。

  python3 _build_03_order_set.py

入力（すべて同じフォルダ）
  D_初回仕入れ_発注候補セット.csv   … 発注セット3案の全SKU（23行）
  D_サプライヤー別サマリ.csv        … 送料・送料無料ライン（NETSEA GET /tariffs 実データ）
  D_filter_stats.json               … 歩留まり
  B1_打診候補_全社_優先度順.csv     … メーカー打診候補（第5部のサマリ用）

⚠️ 出力の 03 HTML は **Git 追跡外**（同フォルダの .gitignore に登録）。
   商品名・JAN・NETSEA サプライヤー社名を含むため、D_*.csv と同じ扱いにしてある。
"""
import csv
import html as H
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "agents" / "content_creator" / "skills"))
from md_to_standalone_html import CSS, inline  # noqa: E402

SETS_CSV = HERE / "D_初回仕入れ_発注候補セット.csv"
SUP_CSV = HERE / "D_サプライヤー別サマリ.csv"
STATS = HERE / "D_filter_stats.json"
MAKERS_CSV = HERE / "B1_打診候補_全社_優先度順.csv"
DST = HERE / "03_初回仕入れ_発注セットと全体まとめ.html"


def read_csv(p, skip_first_line=False):
    raw = p.read_text(encoding="utf-8-sig").split("\n")
    if skip_first_line:
        raw = raw[1:]
    return list(csv.DictReader(io.StringIO("\n".join(raw))))


rows = read_csv(SETS_CSV)
sups = {r["サプライヤー名"]: r for r in read_csv(SUP_CSV)}
stats = json.loads(STATS.read_text(encoding="utf-8"))
makers = read_csv(MAKERS_CSV, skip_first_line=True)

SNAP = datetime.fromtimestamp(SETS_CSV.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
MSNAP = datetime.fromtimestamp(MAKERS_CSV.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

# ---------------------------------------------------------------- 小道具
def esc(s):
    return H.escape(s or "")


def yen(v):
    """CSV の数値をそのまま桁区切りにする。値は変えない。"""
    s = (v or "").strip()
    return f"{int(s):,}円" if s.lstrip("-").isdigit() else '<span class="na">—</span>'


def num(v):
    s = (v or "").strip()
    return f"{int(s):,}" if s.lstrip("-").isdigit() else '<span class="na">—</span>'


def dash(v):
    return esc(v) if (v or "").strip() else '<span class="na">—</span>'


def link(u, label=None):
    if not (u or "").strip():
        return '<span class="na">—</span>'
    return f'<a class="url" href="{H.escape(u, quote=True)}">{esc(label or u)}</a>'


def isum(rs, col):
    return sum(int(r[col]) for r in rs if r[col].strip())


# ---------------------------------------------------------------- セット分解
by_set = OrderedDict()
for r in rows:
    by_set.setdefault(r["セットID"], []).append(r)

B1 = by_set["B1"]
A1 = by_set["A1"]
A2 = by_set["A2"]


def set_suppliers(rs):
    return list(OrderedDict.fromkeys(r["サプライヤー名"] for r in rs))


def shipping(rs):
    """このセットの送料 = 各サプライヤーの『この注文額での送料』の合計。

    サマリ CSV の送料はそのサプライヤーの候補SKU全部を買った場合の注文額に対する値。
    B1 は分割発注なので、注文額を積み直して送料無料ラインと突き合わせる。
    """
    total = 0
    detail = []
    for name in set_suppliers(rs):
        s = sups[name]
        amount = isum([r for r in rs if r["サプライヤー名"] == name], "★仕入れ額(税込)")
        line = s["送料無料ライン"].strip()
        if line.isdigit() and amount >= int(line):
            fee = 0
        else:
            fee = int(s["この注文額での送料"] or 0)
        total += fee
        detail.append((name, amount, fee, line, s))
    return total, detail


# ---------------------------------------------------------------- 検算（合わなければ出力しない）
B1_AMOUNT = isum(B1, "★仕入れ額(税込)")
B1_PROFIT = isum(B1, "★このSKUの見込み粗利")
B1_SHIP, B1_DETAIL = shipping(B1)
CHECKS = [
    ("B1 のSKU数", len(B1), 8),
    ("B1 の社数", len(set_suppliers(B1)), 2),
    ("B1 の仕入れ額(税込)", B1_AMOUNT, 46188),
    ("B1 の見込み粗利", B1_PROFIT, 14736),
    ("B1 の送料", B1_SHIP, 0),
    ("A1 のSKU数", len(A1), 9),
    ("A1 の仕入れ額(税込)", isum(A1, "★仕入れ額(税込)"), 48916),
    ("A1 の見込み粗利", isum(A1, "★このSKUの見込み粗利"), 16499),
    ("A2 のSKU数", len(A2), 6),
    ("A2 の仕入れ額(税込)", isum(A2, "★仕入れ額(税込)"), 36300),
    ("A2 の見込み粗利", isum(A2, "★このSKUの見込み粗利"), 7637),
    ("候補の全行数", len(rows), 23),
]
for label, got, want in CHECKS:
    if got != want:
        raise SystemExit(f"検算に失敗: {label} = {got}（社長決定の値は {want}）。CSV が入れ替わっている可能性があります")
used = sorted({r["★中古品表記の有無"] for r in rows})
if used != ["該当なし"]:
    raise SystemExit(f"検算に失敗: 中古品表記の値が『該当なし』以外を含みます: {used}")
if not all(r["★ブランド判定"] == "B(要実機確認)" for r in rows):
    raise SystemExit("検算に失敗: ブランド判定に B(要実機確認) 以外が混じっています")

# ---------------------------------------------------------------- 第1部 SKU 表
def sku_rows(rs, n0=1):
    out = []
    for i, r in enumerate(rs, n0):
        note = [
            f'<span class="ct">FBAサイズ</span>{esc(r["FBAサイズ"])}',
            f'<span class="ct">中古表記</span><span class="pill pill-ok">{esc(r["★中古品表記の有無"])}</span>',
            f'<span class="ct">ブランド判定</span><span class="pill pill-warn">{esc(r["★ブランド判定"])}</span>',
            f'<span class="ct">4群</span>{esc(r["★4群"])}',
            f'<span class="ct">Amazon本体</span>{esc(r["Amazon本体の有無"])}',
            f'<span class="ct">出品者数の出所</span>{dash(r["出品者数の出所"])}',
        ]
        out.append(
            f'<tr><td class="num">{i}</td>'
            f'<td><strong>{esc(r["商品名"])}</strong>'
            f'<div class="sub">ASIN {esc(r["ASIN"])} ／ JAN {esc(r["JAN"])}<br>'
            f'仕入れ先: {esc(r["サプライヤー名"])}</div></td>'
            f'<td class="num">{yen(r["NETSEA卸値(税込)"])}<br>⇢ {yen(r["Amazon価格"])}</td>'
            f'<td class="num">{yen(r["実費込み純利益"])}<br>{esc(r["利益率%"])}%</td>'
            f'<td class="num">{dash(r["月間販売数(30日ランク下落数)"])}個<br>'
            f'<span class="sub">出品者 {dash(r["出品者数"])}</span></td>'
            f'<td class="num">{yen(r["★仕入れ額(税込)"])}<br>'
            f'<span class="sub">{esc(r["★仕入れ口数"])}口 / {esc(r["★出品可能数(Amazon単位)"])}個</span></td>'
            f'<td class="num"><strong>{yen(r["★このSKUの見込み粗利"])}</strong></td></tr>'
            f'<tr class="noterow"><td></td><td colspan="6">{" ／ ".join(note)}'
            f'<div class="chk">リスク判定: {esc(r["★リスク判定"])}</div>'
            f'<div class="chk"><strong>発注前に必ず確認: {esc(r["発注前に必ず確認"])}</strong></div>'
            f'<div class="src">発注 {link(r["発注先URL"])} ／ '
            f'{link(r["Amazonページ"], "Amazon")} ／ {link(r["Keepaリンク"], "Keepa")}</div>'
            f'</td></tr>')
    return "".join(out)


SKU_HEAD = """<thead><tr>
<th>#</th><th>商品名 / ASIN / JAN / 仕入れ先</th><th>卸値(税込)<br>⇢ Amazon価格</th>
<th>実費込み<br>純利益 / 率</th><th>月間販売数<br>/ 出品者数</th><th>仕入れ額(税込)<br>/ 口数・個数</th>
<th>見込み粗利</th></tr></thead>"""


def supplier_block(name, amount, fee, line, s, rs, start):
    freeline = f'{int(line):,}円以上で無料' if line.isdigit() else "段階設定なし"
    return f"""
<h3>{esc(name)} ─ {len(rs)}SKU / {amount:,}円（送料 {fee:,}円）</h3>
<table class="kv"><tbody>
<tr><th>NETSEA 店舗ページ</th><td>{link(s["NETSEA店舗ページ"])}</td></tr>
<tr><th>送料の段階</th><td>{esc(s["送料の段階"])}（{freeline}）</td></tr>
<tr><th>送料の出所</th><td>{esc(s["送料の出所"])}</td></tr>
</tbody></table>
<div class="tw" tabindex="0"><table class="skutbl">{SKU_HEAD}<tbody>
{sku_rows(rs, start)}
<tr class="totalrow"><td></td><td>この社の小計</td><td></td><td></td><td></td>
<td class="num">{amount:,}円</td><td class="num">{isum(rs, "★このSKUの見込み粗利"):,}円</td></tr>
</tbody></table></div>"""


b1_blocks = []
start = 1
for name, amount, fee, line, s in B1_DETAIL:
    rs = [r for r in B1 if r["サプライヤー名"] == name]
    b1_blocks.append(supplier_block(name, amount, fee, line, s, rs, start))
    start += len(rs)

# ---------------------------------------------------------------- 3案の比較表
def case_row(sid, rs, adopted):
    ship, _ = shipping(rs)
    amount = isum(rs, "★仕入れ額(税込)")
    profit = isum(rs, "★このSKUの見込み粗利")
    cls = ' class="adopted"' if adopted else ""
    mark = '<span class="pill pill-ok">採用</span>' if adopted else '<span class="pill pill-muted">不採用</span>'
    return (f"<tr{cls}><td>{sid}</td><td class='num'>{len(set_suppliers(rs))}</td>"
            f"<td class='num'>{len(rs)}</td><td class='num'>{amount:,}円</td>"
            f"<td class='num'>{ship:,}円</td><td class='num'>{profit:,}円</td><td>{mark}</td></tr>")


compare = (case_row("B1", B1, True) + case_row("A1", A1, False) + case_row("A2", A2, False))


def slim_rows(rs):
    out = []
    for r in rs:
        out.append(f"<tr><td>{esc(r['商品名'])}<div class='sub'>ASIN {esc(r['ASIN'])} ／ "
                   f"{esc(r['サプライヤー名'])}</div></td>"
                   f"<td class='num'>{yen(r['★仕入れ額(税込)'])}</td>"
                   f"<td class='num'>{yen(r['★このSKUの見込み粗利'])}</td>"
                   f"<td class='num'>{esc(r['利益率%'])}%</td>"
                   f"<td class='num'>{dash(r['月間販売数(30日ランク下落数)'])}個</td></tr>")
    return "".join(out)


SLIM_HEAD = ("<thead><tr><th>商品名 / ASIN / 仕入れ先</th><th>仕入れ額(税込)</th>"
             "<th>見込み粗利</th><th>利益率</th><th>月間販売数</th></tr></thead>")

# ---------------------------------------------------------------- 第3部 歩留まり
S2 = stats["S2_除外内訳"]
S2_TOTAL = sum(S2.values())
S2_NOTAMAZON = S2["利益率が計算できていない（Amazon未出品・価格が取れない）"] + S2["赤字"]
S2_BUDGET = S2["1SKU単価レンジ 5,000〜10,000円 に収まらない（1口が上限10,000円を超える）"]
S2_SHARE = round(S2_NOTAMAZON / S2_TOTAL * 100)
FUNNEL = [
    ("全候補（Keepa 検証100%完走）", stats["S0_母数"], ""),
    ("条件1 買ってはいけないリスト", stats["S1_残"], f'−{stats["S0_母数"] - stats["S1_残"]:,}'),
    ("条件2 予算5万円", stats["S2_残"], f'−{stats["S1_残"] - stats["S2_残"]:,}'),
    ("中古の実データ確認（NETSEA 商品説明を実読）", stats["S3_残"], f'−{stats["S2_残"] - stats["S3_残"]:,}'),
    ("初回に向く4群", stats["S4_残"], f'−{stats["S3_残"] - stats["S4_残"]:,}'),
    ("回転あり（30日で1個以上）", stats["S5_残"], f'−{stats["S4_残"] - stats["S5_残"]:,}'),
]
ADOPTED = ' class="adopted"'
funnel_rows = "".join(
    "<tr{}><td>{}</td><td class=\"num\">{:,}</td><td class=\"num\">{}</td></tr>".format(
        ADOPTED if i == len(FUNNEL) - 1 else "", esc(k), v, esc(d))
    for i, (k, v, d) in enumerate(FUNNEL))
N_SUP = stats["条件3_サプライヤー"]["4群通過SKUを持つサプライヤー数"]

s2_rows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v:,}</td></tr>'
                  for k, v in sorted(S2.items(), key=lambda x: -x[1]))

# ---------------------------------------------------------------- 第5部 メーカー
M_N = len(makers)
M_AP = [r for r in makers if r["optout_class"] == "A_PLUS"]
M_A = [r for r in makers if r["optout_class"] == "A"]
M_STOP = [r for r in makers if r["optout_class"] in ("B", "C", "D", "E")]
M_OK = M_AP + M_A
M_CHECKED = [r for r in M_OK if r["optout_notice_status"] in ("注記あり", "確認済み_表示なし")]
M_UNKNOWN = [r for r in M_OK if r["optout_notice_status"] == "未取得"]
IGA = [r for r in makers if r["メーカー名"].startswith("イガラシ")][0]

EXTRA_CSS = """
.warnbox{margin:26px 0 8px; padding:20px 24px 18px; border-radius:10px;
  background:var(--alert-bg); border:3px solid var(--alert); border-left:12px solid var(--alert);}
.warnbox h2{margin:0 0 10px; font-size:20px; border-bottom:2px solid var(--alert); padding-bottom:8px;}
.warnbox h3{margin:18px 0 6px; font-size:17px;}
.warnbox p{margin:0 0 .8em;}
.warnbox p:last-child{margin-bottom:0;}
.warnbox .why{font-size:14.5px; color:var(--muted);}
.note{margin:0 0 18px; padding:12px 16px; border-left:4px solid var(--accent);
  background:var(--accent-bg); font-size:14.5px; border-radius:0 8px 8px 0;}
.na{color:var(--faint);}
.url{color:var(--accent); word-break:break-all;}
.num{text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums;}
.sub{font-size:12.5px; color:var(--muted); font-weight:400; line-height:1.6; margin-top:.2em;}
.ct{font-size:11.5px; color:var(--faint); border:1px solid var(--border); border-radius:3px;
  padding:0 .35em; margin-right:.35em;}
.src{margin-top:.35em; font-size:12px; color:var(--faint);}
table.kv{border-collapse:collapse; width:100%; font-size:14px; line-height:1.7; margin:0 0 10px;}
table.kv th{width:11em; text-align:left; vertical-align:top; font-weight:700; color:var(--muted);
  padding:5px 12px 5px 0; border-bottom:1px solid var(--border); white-space:nowrap;}
table.kv td{vertical-align:top; padding:5px 0; border-bottom:1px solid var(--border);
  word-break:break-word;}
table.kv tr:last-child th,table.kv tr:last-child td{border-bottom:0;}
table.skutbl{table-layout:fixed; min-width:720px;}
table.skutbl th:nth-child(1),table.skutbl td:nth-child(1){width:2.6em;}
table.skutbl th:nth-child(2),table.skutbl td:nth-child(2){width:auto;}
table.skutbl th:nth-child(3),table.skutbl td:nth-child(3){width:8.2em;}
table.skutbl th:nth-child(4),table.skutbl td:nth-child(4){width:7.4em;}
table.skutbl th:nth-child(5),table.skutbl td:nth-child(5){width:7.4em;}
table.skutbl th:nth-child(6),table.skutbl td:nth-child(6){width:8.6em;}
table.skutbl th:nth-child(7),table.skutbl td:nth-child(7){width:7.4em;}
table.skutbl thead th{white-space:normal;}
table.slim{table-layout:fixed; min-width:600px;}
table.slim th:nth-child(1),table.slim td:nth-child(1){width:auto;}
table.slim th:nth-child(n+2),table.slim td:nth-child(n+2){width:7em;}
table.slim thead th{white-space:normal;}
tbody tr.noterow td{word-break:break-word; font-size:13px; line-height:1.75; color:var(--muted);
  padding-top:0; border-bottom:2px solid var(--border-strong);}
tbody tr.noterow{background:transparent!important;}
tbody tr.noterow .chk{margin-top:.3em;}
tbody tr.totalrow td{font-weight:700; background:var(--surface2); border-top:2px solid var(--border-strong);}
tbody tr.adopted td{background:var(--ok-bg);}
tbody tr.adopted td:first-child{box-shadow:inset 4px 0 0 var(--ok);}
.grand{margin:18px 0 0; padding:16px 20px; border:3px solid var(--accent); border-radius:10px;
  background:var(--accent-bg);}
.grand table{width:100%; border-collapse:collapse; font-size:16px;}
.grand td{padding:6px 0; border:0;}
.grand td:last-child{text-align:right; font-weight:700; font-variant-numeric:tabular-nums;}
.grand .big td{font-size:20px; padding-top:12px; border-top:2px solid var(--accent);}
.chk{font-size:13px;}
h1.part{scroll-margin-top:10px;}
@media print{
  /* 印刷は table-layout:auto に戻るので min-width を残すと紙幅を超え、
     .tw{overflow:hidden} で黙って切れる（画面では気づけない） */
  table.skutbl,table.slim{min-width:0; table-layout:auto;}
  table.skutbl th:nth-child(n),table.skutbl td:nth-child(n),
  table.slim th:nth-child(n),table.slim td:nth-child(n){width:auto;}
  /* .num の nowrap が7列ぶん積み上がると紙幅を超える。印刷では折り返しを許す */
  table.skutbl .num,table.slim .num{white-space:normal;}
  table.skutbl{font-size:7.8pt;}
  table.skutbl thead th{overflow-wrap:anywhere;}
  table.skutbl .ct{border:0; padding:0 .2em 0 0;}
  /* 基本CSSの td:first-child{min-width:7.5em} が「#」列に効いて紙幅を押し広げる */
  table.skutbl th:first-child,table.skutbl td:first-child,
  table.slim th:first-child,table.slim td:first-child{min-width:0;}
  table.skutbl .sub,table.slim .sub{overflow-wrap:anywhere;}
  table.skutbl tbody td,table.skutbl thead th{padding:5px 4px;}
  .warnbox{border:3pt solid #000; border-left:6pt solid #000; background:#fff;}
  .note,.grand{background:#fff; border-color:#000;}
  .grand{border:2pt solid #000;}
  tbody tr.adopted td{background:#fff;}
  tbody tr.adopted td:first-child{box-shadow:inset 3pt 0 0 #000;}
  tbody tr.totalrow td{background:#fff;}
  .url,a{color:#000;}
  .pill{background:#fff!important; color:#000!important; border:1pt solid #000!important;}
}
"""

TOC = """
<nav class="toc" aria-label="目次">
<p class="toc-h">目次</p>
<ul class="toc-list">
<li class="toc-lv1"><a href="#p1">第1部 発注セット B1 ─ これを買う</a></li>
<li class="toc-lv1"><a class="toc-danger" href="#p2">第2部 発注前に必ず潰すこと（2件・未了）</a></li>
<li class="toc-lv1"><a href="#p3">第3部 26,942件がどう8SKUになったか</a></li>
<li class="toc-lv1"><a href="#p4">第4部 確定した方針</a></li>
<li class="toc-lv1"><a href="#p5">第5部 メーカー打診候補 {M_N}社（サマリ）</a></li>
<li class="toc-lv1"><a class="toc-alert" href="#p6">第6部 この資料の限界</a></li>
</ul>
</nav>
""".replace("{M_N}", str(M_N))

doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>初回仕入れ 発注セット B1 と全体まとめ</title>
<meta name="robots" content="noindex, nofollow">
<style>{CSS}{EXTRA_CSS}</style>
</head>
<body id="top">
<div class="wrap">
<p class="kicker">T-20260904-004 ／ 社長決定 2026-09-06 ／ 発注データ {SNAP} 時点</p>
<h1>初回仕入れ 発注セット B1 と全体まとめ</h1>
<p class="lead">NETSEA の 26,942件を Keepa で100%検証し、3条件（買ってはいけないリスト → 予算5万円 → 仕入れ先の集約）で
{len(B1)}SKU まで絞った結果です。<strong>発注セットは B1（{len(set_suppliers(B1))}社・{len(B1)}SKU・{B1_AMOUNT:,}円）で確定しています。</strong>
ただし<strong>出品制限（ゲート）が1件も確認できていません</strong>。第2部を読まずに発注しないでください。</p>

{TOC}

<h1 class="part" id="p1">第1部 発注セット B1 ─ これを買う</h1>

<section class="sec sec-box sec-conclusion">
<h2>結論</h2>
<p><strong>{len(set_suppliers(B1))}社に {len(B1)}SKU を分けて発注します。仕入れ {B1_AMOUNT:,}円・送料 {B1_SHIP:,}円・見込み粗利 {B1_PROFIT:,}円。</strong>
どちらの社も送料無料ラインを実額で超えているため、送料は掛かりません。</p>
<p>粗利が最大なのは A1（{isum(A1, "★このSKUの見込み粗利"):,}円）ですが、採らないと決めました。
<strong>A1 は {len(A1)}SKU すべてが同一ブランド1社の商品で、そのブランドのゲートが1回閉じれば {len(A1)}SKU が同時に死にます。</strong>
B1 は2社2系統に割れているので、片方が出品できなくても片方は動きます。
初回の目的は利益ではなく「仕入れ→出品→FBA納品→販売→入金」を1周完走することなので、
粗利 {isum(A1, "★このSKUの見込み粗利") - B1_PROFIT:,}円の差より全滅しないことを優先しました。</p>
<p class="why">（ゲート＝Amazon の出品制限。ブランドやカテゴリごとに「請求書を出せば売ってよい」という審査が掛かる仕組みで、
閉じているとそのブランドの商品を1点も出品できません。）</p>
</section>

<section class="sec">
<h2>発注する {len(B1)}SKU（サプライヤーごと・この単位で1回ずつ発注する）</h2>
{"".join(b1_blocks)}

<div class="grand">
<table><tbody>
<tr><td>仕入れ額（税込）</td><td>{B1_AMOUNT:,}円</td></tr>
<tr><td>送料</td><td>{B1_SHIP:,}円</td></tr>
<tr><td>予算5万円に対する残り</td><td>{50000 - B1_AMOUNT - B1_SHIP:,}円</td></tr>
<tr class="big"><td>見込み粗利（実測コストモデルによる試算）</td><td>{B1_PROFIT:,}円</td></tr>
</tbody></table>
</div>
</section>

<section class="sec">
<h2>採らなかった A1・A2（なぜ蹴ったかを残す）</h2>
<div class="tw" tabindex="0"><table><thead><tr>
<th>案</th><th>社数</th><th>SKU</th><th>仕入れ額(税込)</th><th>送料</th><th>見込み粗利</th><th>判定</th>
</tr></thead><tbody>
{compare}
</tbody></table></div>
<p class="note"><strong>A1 を蹴った理由は粗利ではありません。</strong>{len(A1)}SKU が同一ブランド1社に集中しているためです。
<strong>A2 を蹴った理由も粗利ではありません。</strong>1社完結で、同じく分散が効きません
（結果として粗利も {isum(A2, "★このSKUの見込み粗利"):,}円と最も小さくなります）。
なお B1 の {len(B1)}SKU は A1・A2 から選び直したものではなく、同じ32SKUの母集団から2社に割り付け直したものです。</p>

<h3>A1 ─ 1社完結・{len(A1)}SKU・{isum(A1, "★仕入れ額(税込)"):,}円</h3>
<div class="tw" tabindex="0"><table class="slim">{SLIM_HEAD}<tbody>{slim_rows(A1)}</tbody></table></div>

<h3>A2 ─ 1社完結・{len(A2)}SKU・{isum(A2, "★仕入れ額(税込)"):,}円</h3>
<div class="tw" tabindex="0"><table class="slim">{SLIM_HEAD}<tbody>{slim_rows(A2)}</tbody></table></div>
</section>

<h1 class="part" id="p2">第2部 発注前に必ず潰すこと（2件・未了）</h1>

<section class="warnbox">
<h2>候補が出た＝買ってよい、ではありません</h2>
<p>この {len(B1)}SKU は<strong>機械が絞った候補</strong>です。下の2件は人が目で確認するまで埋まりません。
どちらも、外すとアカウントか許認可に直接跳ね返ります。</p>

<h3>1. 出品制限（ゲート）が1件も確認できていない</h3>
<p>セラーセントラルにログインできないためです（アカウントは3か国とも停止中 / T-20260826-004）。
リスク判定の4軸のうち、許認可・危険物・知財の3軸は当てましたが、<strong>ゲート軸だけが未判定</strong>です。</p>
<p><strong>復旧後、発注前に、候補{len(rows)}行すべてをセラーセントラルの「商品登録」で実機確認してください。</strong>
出品できないブランドを仕入れると、在庫が1点も売れないまま残ります。</p>
<p class="why">候補は全行が<strong>ブランド判定 B（要実機確認）</strong>です。ブランド名は Amazon 側に登録済みで、
ゲートが開いているかどうかだけが不明という状態です。</p>

<h3>2. 中古の確認はテキスト判定までしか済んでいない</h3>
<p>2段で見ています。商品名で26件、<strong>NETSEA の商品説明本文を実際に読んで</strong>2件（いずれも「アウトレット」）を除外しました。
最終候補{len(rows)}行はすべて「中古品表記 該当なし」で、「要目視」は0件です。</p>
<p><strong>ただし機械が読んだのは文字だけです。商品ページの画像と「販売条件」タブは未確認です。</strong>
発注前に全SKUの商品ページを1点ずつ開いて目で確認してください。</p>
<p class="why">当社は古物商許可を持っていません。<strong>新品だけを扱う限り不要ですが、1点でも中古が混じった瞬間に無許可営業になります。</strong>
機械判定はこの目視の手間を減らすためのもので、代わりにはなりません。</p>
</section>

<h1 class="part" id="p3">第3部 26,942件がどう{len(B1)}SKUになったか</h1>

<section class="sec">
<h2>歩留まり</h2>
<div class="tw" tabindex="0"><table><thead><tr>
<th>段階</th><th>残り</th><th>落とした</th></tr></thead><tbody>
{funnel_rows}
</tbody></table></div>
<p>最後に残った {stats["S5_残"]}SKU は {N_SUP}社に散っていました。ここから「1社で5SKU以上を組めて、送料無料ラインに乗る」組み合わせを探し、
3案（B1・A1・A2）を作っています。</p>
<p class="note">各段階で「落とした件数の合計 == 減った行数」を機械で検算しており、合わなければ処理が異常終了します。
今回は全段一致しました。</p>
</section>

<section class="sec sec-box sec-warn">
<h2>この表の誤読に注意 ─ 予算で落ちたのは44件だけ</h2>
<p>予算の段階（{stats["S1_残"]:,} → {stats["S2_残"]}）で {S2_TOTAL:,}件が落ちています。
これを見て「予算5万円が厳しすぎる」と読むのは誤りです。</p>
<div class="tw" tabindex="0"><table><thead><tr><th>落とした理由</th><th>件数</th></tr></thead><tbody>
{s2_rows}
</tbody></table></div>
<p><strong>落選の{S2_SHARE}%（{S2_NOTAMAZON:,}件）は「そもそも Amazon に商品が無い／赤字」で、予算とは無関係です。</strong>
1口の単価が上限を超えて落ちたのは <strong>{S2_BUDGET}件</strong>だけでした。
予算を10万円に上げても、候補が2倍になるわけではありません。</p>
</section>

<h1 class="part" id="p4">第4部 確定した方針</h1>

<section class="sec">
<h2>この調査で決まったこと</h2>
<div class="tw" tabindex="0"><table><thead><tr><th>論点</th><th>確定内容</th></tr></thead><tbody>
<tr><td>買う商材</td><td>電気を使わない・電池を含まない・ブランドが付いていない・期限がない・割れない<strong>新品雑貨</strong>。
①文房具・オフィス用品／②ホーム＆キッチン(非電気)／③DIY・工具(非電動)／④季節雑貨(電池なし) の4群</td></tr>
<tr><td>買わない商材</td><td>電気用品・ブランド品・化粧品・中古品は<strong>例外なく</strong>。食品・書籍も初回は除外</td></tr>
<tr><td>ブランド除外の運用</td><td><strong>2段階で運用する。</strong>Tier A（著名ブランド {stats["S1_除外内訳_最初に触れた項目"]["#2 ブランド"]:,}件）は機械で除外。
Tier B（それ以外）は残し、全SKUに「ゲート未確認」の印を付ける。<br>
理由: Keepa の brand は99.9%が埋まっており、ノーブランド雑貨にも卸元の社名がブランドとして入る。
<strong>「ブランドが付いた商品を全除外」を文字どおり適用すると候補は0件</strong>になる</td></tr>
<tr><td>仕入れ先の集約</td><td><strong>送料単独で黒字候補の63%が消える。</strong>1〜2社に集約して送料無料ラインに乗せる。
今回は2社とも実額でラインを超え、送料0円で組めた</td></tr>
<tr><td>古物商許可</td><td><strong>不要</strong>（新品のみを扱う限り）。反転条件は3つ ─ 中古が1点でも混じる／消費者から買い取る／
一度消費者の手に渡った品を仕入れる。1つでも当たれば取得が必須</td></tr>
<tr><td>出品プラン</td><td>小口ではカートを取れず、広告も出せない。<strong>復旧後・FBA納品の直前に大口へ切り替える。</strong>
いま触ると KYC（本人確認）の再認証を誘発するため、今は触らない</td></tr>
<tr><td>打診メール</td><td><strong>URL を一切貼らない。</strong>貼った瞬間に特定電子メール法の広告メールに転化し、
相手サイトの「営業お断り」表示が法的効力を持つ</td></tr>
</tbody></table></div>
</section>

<h1 class="part" id="p5">第5部 メーカー打診候補 {M_N}社（サマリ）</h1>

<section class="sec">
<h2>内訳</h2>
<div class="tw" tabindex="0"><table><thead><tr><th>区分</th><th>社数</th><th>扱い</th></tr></thead><tbody>
<tr class="adopted"><td>A_PLUS</td><td class="num">{len(M_AP)}</td>
<td>OEM・小ロット・B2B窓口のいずれかを公式サイトに明示している社。<strong>ここから打診する</strong></td></tr>
<tr><td>A</td><td class="num">{len(M_A)}</td><td>営業お断りの表示が見つからなかった社。A_PLUS を消化した後、優先度順に</td></tr>
<tr class="row-danger"><td>B・C・D・E</td><td class="num">{len(M_STOP)}</td><td>打診しない／条件付き</td></tr>
</tbody></table></div>

<p class="note"><strong>「打診可能 {len(M_OK)}社」を単独で読まないでください。</strong>
このうち<strong>お断り表示の有無を実際に確認したのは {len(M_CHECKED)}社だけ</strong>で、
残り <strong>{len(M_UNKNOWN)}社は未確認</strong>（窓口ページを検分した記録が無い）です。
未確認は「表示が無いと確認した」という意味ではありません。<strong>打診の直前に、その社の窓口ページを必ず自分の目で開いてください。</strong></p>

<h3>特筆 ─ {esc(IGA["メーカー名"])}（{esc(IGA["順位"])}位）</h3>
<p>{M_N}社で<strong>唯一、当社が対象に含まれると公式に書いている社</strong>です。法人向けフォームに次の表示があります。</p>
<blockquote><p>{esc(IGA["form_optout_notice"])}</p></blockquote>
<p><strong>「※個人事業主・法人の方が対象となります」</strong>と明記され、問い合わせ種別に「OEM生産についてのお問い合わせ」
「新規の取引についてお問い合わせ」があります。<strong>最初の1通はここに出すのが最も理にかなっています。</strong></p>
<table class="kv"><tbody>
<tr><th>正式商号</th><td>{esc(IGA["正式商号"])}</td></tr>
<tr><th>取引可否シグナル</th><td>{esc(IGA["取引可否シグナル"])}</td></tr>
<tr><th>表示を確認したページ</th><td>{link(IGA["optout_source_url"])}</td></tr>
</tbody></table>

<p class="src">{M_N}社の全リスト（連絡先・判定根拠・出典つき）は
<a class="url" href="02_メーカー打診候補リスト.html">02_メーカー打診候補リスト.html</a> にあります（{MSNAP} 時点）。</p>
</section>

<h1 class="part" id="p6">第6部 この資料の限界</h1>

<section class="sec sec-box sec-alert">
<h2>信じてよい範囲</h2>
<ol>
<li><strong>出品制限（ゲート）は未確認です。</strong>セラーセントラルにログインできないためで、ログイン後に埋まります（第2部）</li>
<li><strong>中古かどうかの判定は、機械によるテキスト判定までです。</strong>画像と「販売条件」タブは読んでいません（第2部）</li>
<li><strong>見込み粗利 {B1_PROFIT:,}円は試算であって、確定利益ではありません。</strong>
経理の実測コストモデル（小口基本成約料110円/点・販売手数料の消費税10%・FBA納品代行12円/点・納品送料37.5円/点・保管1.5ヶ月・返品率3%引当）で計算した値です。
低在庫レベル手数料（5〜30円/点）は値が取れず、計上していません</li>
<li><strong>出品者数が空欄の行があります。</strong>Keepa の COUNT_NEW が取れていない行で、推測では埋めていません。
なお COUNT_NEW は新品オファーの本数であって出品者数ではありません（1社が FBA と FBM に出すだけで2になります）</li>
<li><strong>4群への割り当ては Keepa のルートカテゴリ1階層による近似です。</strong>「ホビー」「産業・研究開発用品」を④季節雑貨に寄せており、
原稿の定義と完全には一致しません</li>
<li><strong>送料は NETSEA の API 実データですが、「1円以上で無料」という設定の社が1社あります。</strong>
文字どおり読めば常に無料ですが、これは値の解釈です。発注画面で実額を確認してください</li>
</ol>
</section>

<section class="sec">
<h2>目視で初めて出た不具合5件（機械の検算では出なかった）</h2>
<p>この候補は、出力を人が1行ずつ読んで5件の不具合を見つけ、直した後のものです。
<strong>5件とも自動テストは通っていました。</strong>次に同じ処理を回すときも、目視は省けません。</p>
<div class="tw" tabindex="0"><table><thead><tr><th>症状</th><th>原因</th></tr></thead><tbody>
<tr><td>電池駆動の置き時計（プロジェクター機能付）が候補に残った</td><td>電気用品のキーワードに時計・クロック等が無く、フィルタを素通りした</td></tr>
<tr><td>壁掛けミラー（鏡）が候補に残った</td><td>割れ物のキーワードに「鏡」が無かった</td></tr>
<tr><td>あるセットの9SKU中8SKUが30日で0個だった</td><td>回転の下限が無く、供給元の候補数だけで枠を埋めていた（回転条件を追加）</td></tr>
<tr><td>中古「該当なし」の行に「機械判定できない」という矛盾した注記が残っていた</td><td>暫定注記を確定時に消していなかった</td></tr>
<tr><td>統計「候補を持つサプライヤー数」が {N_SUP}社 → 2社 に化けていた</td><td>2社合算セットの実装で、外側の変数を上書きしていた</td></tr>
</tbody></table></div>
</section>

<p class="prov">内容の唯一の正は D_初回仕入れ_発注候補セット.csv（{SNAP} 時点・{len(rows)}行）／ D_サプライヤー別サマリ.csv ／
D_filter_stats.json ／ B1_打診候補_全社_優先度順.csv（{MSNAP} 時点・{M_N}社）です。
本ファイルはそれらを機械変換した表示版で、値の書き換え・要約・言い換えはしていません。再生成は <code>python3 _build_03_order_set.py</code>。<br>
<strong>このファイルは Git 追跡外です。</strong>商品名・JAN・NETSEA のサプライヤー社名を含むため、元の D_*.csv と同じ扱いにしてあります
（本リポジトリは公開されているため）。</p>
</div>
<a class="top" href="#top" aria-label="先頭へ戻る">&#8593;</a>
</body>
</html>
"""

DST.write_text(doc, encoding="utf-8")
print(f"OK: {DST.name} ({len(doc.encode('utf-8')):,} bytes) / B1 {len(B1)}SKU {B1_AMOUNT:,}円 "
      f"送料{B1_SHIP}円 粗利{B1_PROFIT:,}円 / 検算 {len(CHECKS)}件すべて一致 / メーカー {M_N}社")
