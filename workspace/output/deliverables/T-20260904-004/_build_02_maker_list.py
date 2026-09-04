#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B1_打診候補_全社_優先度順.csv → 02_メーカー打診候補リスト.html を生成する。

CSV が唯一の正。この道具は表示を作るだけで、値の書き換え・要約・言い換えはしない
（備考の重複表現もそのまま出す。直すなら CSV 側を直して再実行する）。

見た目は 01 と同じ CSS を使うため、コンバータのスキルから CSS/inline を読み込む。
  python3 _build_02_maker_list.py <入力csv> <出力html>
"""
import csv
import html as H
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "agents" / "content_creator" / "skills"))
from md_to_standalone_html import CSS, inline  # noqa: E402

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])

raw = SRC.read_text(encoding="utf-8-sig").split("\n")
HEADER_NOTE = raw[0].lstrip("#").strip()          # CSV 1行目の法務注記（原文のまま使う）
rows = list(csv.DictReader(io.StringIO("\n".join(raw[1:]))))

CH_LABEL = {"form": "フォーム", "mail": "メール", "phone": "電話", "mail_post": "郵送（書面）"}


def channels(r):
    try:
        ch = json.loads(r["allowed_channels"] or "[]")
    except json.JSONDecodeError:
        ch = []
    if not ch:
        return '<span class="chip chip-no">連絡しない</span>'
    return "".join(f'<span class="chip">{H.escape(CH_LABEL.get(c, c))}</span>' for c in ch)


MASK = ('<span class="na">個人事業主の疑いのため、公開リポジトリである本ページでは伏せています'
        '（値は CSV にあります）</span>')


def personal(r):
    """個人事業主の疑いと記録された社。連絡先は本ページに出さない。"""
    return "個人事業主の疑い" in r["備考"]


def txt(s):
    return inline(s or "")


def link(u):
    if not u:
        return '<span class="na">—</span>'
    return f'<a class="url" href="{H.escape(u, quote=True)}">{H.escape(u)}</a>'


def urls(cell):
    parts = [p.strip() for p in re.split(r"[;；]", cell or "") if p.strip()]
    return "<br>".join(link(p) for p in parts) if parts else '<span class="na">—</span>'


def yen(v):
    return f"{int(v):,}円" if v and v.strip().isdigit() else '<span class="na">—</span>'


def kv(label, value_html):
    return f"<tr><th>{H.escape(label)}</th><td>{value_html}</td></tr>"


# ------------------------------------------------------------------ 区分
aplus = [r for r in rows if r["optout_class"] == "A_PLUS"]
plain = [r for r in rows if r["optout_class"] == "A"]
stop = [r for r in rows if r["optout_class"] in ("B", "C", "D", "E")]


def card(r, highlight=False):
    name = txt(r["メーカー名"])
    sub = " ／ ".join(x for x in [r["正式商号"], r["主なカテゴリ"], f'確度 {r["確度"]}'] if x)
    body = [
        kv("取引可否シグナル", txt(r["取引可否シグナル"]) or '<span class="na">—</span>'),
        kv("使ってよい連絡手段", channels(r)),
        kv("電話", MASK if (personal(r) and r["電話"]) else (H.escape(r["電話"]) or '<span class="na">—</span>')),
        kv("問い合わせフォーム", link(r["問い合わせフォームURL"])),
        kv("メール", H.escape(r["メール"]) or '<span class="na">—</span>'),
        kv("所在地", MASK if (personal(r) and r["所在地"]) else (H.escape(r["所在地"]) or '<span class="na">—</span>')),
        kv("法人番号", H.escape(r["法人番号"]) or '<span class="na">—</span>'),
        kv("公式HP", link(r["公式HP"])),
        kv("Amazon で当社が見つけた商品", f'{H.escape(r["該当商品数"])}件 ／ 代表: {txt(r["代表商品名"])}'),
        kv("想定仕入れ ⇢ Amazon（中央値）", f'{yen(r["想定仕入れ金額の中央値"])} ⇢ {yen(r["Amazon価格の中央値"])}'),
        kv("公式サイトの表示（判定の根拠）", txt(r["form_optout_notice"]) or '<span class="na">—</span>'),
        kv("表示を確認したページ", link(r["optout_source_url"])),
        kv("備考（調査時のメモ・原文）", txt(r["備考"])),
        kv("出典", urls(r["出典URL"])),
    ]
    cls = "card card-hi" if highlight else "card"
    return (f'<article class="{cls}" id="m{r["順位"]}">'
            f'<h3 class="cardh"><span class="rank">{H.escape(r["順位"])}</span> {name}'
            f' <span class="chip chip-a">A_PLUS</span></h3>'
            f'<p class="cardsub">{H.escape(sub)}</p>'
            f'<table class="kv"><tbody>{"".join(body)}</tbody></table></article>')


# ------------------------------------------------------------------ A 一覧表
def list_rows(rs):
    out = []
    for r in rs:
        contact = []
        if r["公式HP"]:
            contact.append(f'<span class="ct">公式HP</span> {link(r["公式HP"])}')
        if r["電話"]:
            contact.append(f'<span class="ct">電話</span> '
                           + (MASK if personal(r) else H.escape(r["電話"])))
        if r["問い合わせフォームURL"]:
            contact.append(f'<span class="ct">フォーム</span> {link(r["問い合わせフォームURL"])}')
        if r["メール"]:
            contact.append(f'<span class="ct">メール</span> {H.escape(r["メール"])}')
        if not contact:
            contact = ['<span class="na">連絡先なし（下段の備考を読むこと）</span>']
        note = []
        if personal(r):
            note.append(H.escape(r["正式商号"]) + " ／ 所在地は " + MASK)
        elif r["正式商号"] or r["所在地"]:
            note.append(H.escape(" ".join(x for x in [r["正式商号"], r["所在地"]] if x)))
        if r["法人番号"]:
            note.append("法人番号 " + H.escape(r["法人番号"]))
        if r["取引可否シグナル"]:
            note.append("シグナル: " + txt(r["取引可否シグナル"]))
        if r["form_optout_notice"]:
            note.append("公式サイトの表示: " + txt(r["form_optout_notice"]))
        note.append("Amazon で見つけた商品の代表: " + txt(r["代表商品名"]))
        if r["備考"]:
            note.append(txt(r["備考"]))
        if r["optout_source_url"]:
            note.append("表示を確認したページ: " + link(r["optout_source_url"]))
        flag = ""
        if r["optout_needs_review"].strip().lower() == "true":
            flag = ' <span class="pill pill-warn">要確認</span>'
            note.append("<strong>要確認の理由: " + txt(r["optout_review_reason"]) + "</strong>")
        out.append(
            f'<tr id="m{r["順位"]}"><td class="num">{H.escape(r["順位"])}</td>'
            f'<td>{txt(r["メーカー名"])}{flag}</td>'
            f'<td>{H.escape(r["主なカテゴリ"])}</td>'
            f'<td class="num">{H.escape(r["該当商品数"])}</td>'
            f'<td class="num">{yen(r["想定仕入れ金額の中央値"])}<br>⇢ {yen(r["Amazon価格の中央値"])}</td>'
            f'<td>{H.escape(r["確度"])}</td>'
            f'<td class="ctcell">{"<br>".join(contact)}</td></tr>'
            f'<tr class="noterow"><td></td><td colspan="6">{" ／ ".join(note)}'
            f'<div class="src">出典: {urls(r["出典URL"])}</div></td></tr>')
    return "".join(out)


# ------------------------------------------------------------------ 打診不可
def stop_rows(rs):
    label = {"B": "B ＝ 書面のみ", "C": "C ＝ 保留", "D": "D ＝ 打診しない", "E": "E ＝ 打診しない"}
    dash = '<span class="na">—</span>'
    nonotice = '<span class="na">公式サイトに拒否表示はない（別の理由での除外）</span>'

    def sub2(r):
        x = [t for t in (r["optout_e_subclass"], r["optout_decided_by"]) if t.strip()]
        return f'<div class="sub">{H.escape(" ／ ".join(x))}</div>' if x else ""

    out = []
    for r in rs:
        hard = r["optout_class"] in ("D", "E")
        note = []
        if r["所在地"]:
            note.append(MASK if personal(r) else H.escape(r["所在地"]))
        if r["法人番号"]:
            note.append("法人番号 " + H.escape(r["法人番号"]))
        if r["公式HP"]:
            note.append("公式HP: " + link(r["公式HP"]))
        if r["電話"]:
            note.append("電話 " + (MASK if personal(r) else H.escape(r["電話"])))
        if r["問い合わせフォームURL"]:
            note.append("フォーム: " + link(r["問い合わせフォームURL"]))
        if r["メール"]:
            note.append("メール " + H.escape(r["メール"]))
        note.append(f'確度 {H.escape(r["確度"])} ／ シグナル: ' + txt(r["取引可否シグナル"]))
        note.append(f'Amazon で見つけた商品 {H.escape(r["該当商品数"])}件（{H.escape(r["主なカテゴリ"])}） '
                    f'／ 代表: ' + txt(r["代表商品名"])
                    + f' ／ 仕入れ {yen(r["想定仕入れ金額の中央値"])} ⇢ Amazon {yen(r["Amazon価格の中央値"])}')
        if r["optout_source_url"]:
            note.append("表示を確認したページ: " + link(r["optout_source_url"]))
        if hard:
            note.append("<strong>この社には連絡しません。上の連絡先は照合用で、使うためのものではありません。</strong>")
        out.append(
            f'<tr class="{"row-danger" if hard else ""}" id="m{r["順位"]}">'
            f'<td class="num">{H.escape(r["順位"])}</td>'
            f'<td>{txt(r["メーカー名"])}<br><span class="sub">{H.escape(r["正式商号"])}</span></td>'
            f'<td><span class="pill pill-{"danger" if hard else "warn"}">'
            f'{H.escape(label[r["optout_class"]])}</span>{sub2(r)}</td>'
            f'<td>{txt(r["form_optout_notice"]) or nonotice}</td>'
            f'<td>{txt(r["備考"])}</td>'
            f'<td>{H.escape(r["recheck_condition"]) or dash}</td></tr>'
            f'<tr class="noterow"><td></td><td colspan="5">{" ／ ".join(note)}'
            f'<div class="src">出典: {urls(r["出典URL"])}</div></td></tr>')
    return "".join(out)


EXTRA_CSS = """
.warnbox{
  margin:26px 0 8px; padding:20px 24px 18px; border-radius:10px;
  background:var(--alert-bg); border:3px solid var(--alert); border-left:12px solid var(--alert);
}
.warnbox h2{margin:0 0 10px; font-size:20px; border-bottom:2px solid var(--alert); padding-bottom:8px;}
.warnbox p{margin:0 0 .8em;}
.warnbox p:last-child{margin-bottom:0;}
.warnbox .why{font-size:14.5px; color:var(--muted);}
.chip{
  display:inline-block; font-size:12.5px; line-height:1.7; font-weight:700;
  padding:0 .6em; margin:0 .25em .25em 0; border-radius:4px;
  background:var(--surface2); border:1px solid var(--border-strong); color:var(--text);
  white-space:nowrap;
}
.chip-a{background:var(--accent); border-color:var(--accent); color:#fff;}
.chip-no{background:var(--alert); border-color:var(--alert); color:#fff;}
.card{
  margin:0 0 22px; padding:16px 20px 8px; border:1px solid var(--border-strong);
  border-radius:10px; background:var(--surface); break-inside:avoid; page-break-inside:avoid;
}
.card-hi{border:3px solid var(--accent); background:var(--accent-bg);}
.cardh{margin:0 0 2px; font-size:17.5px; font-weight:700;}
.cardh::before{content:none;}
.rank{
  display:inline-block; min-width:1.9em; text-align:center; margin-right:.4em;
  background:var(--text); color:var(--bg); border-radius:4px; font-size:14px;
  padding:0 .3em; vertical-align:.12em;
}
.cardsub{margin:0 0 12px; font-size:14px; color:var(--muted);}
table.kv{border-collapse:collapse; width:100%; font-size:14.5px; line-height:1.75;}
table.kv th{
  width:14em; text-align:left; vertical-align:top; font-weight:700; color:var(--muted);
  padding:7px 12px 7px 0; border-bottom:1px solid var(--border); white-space:nowrap;
}
table.kv td{vertical-align:top; padding:7px 0; border-bottom:1px solid var(--border);
  word-break:break-word;}
table.kv tr:last-child th,table.kv tr:last-child td{border-bottom:0;}
.note{
  margin:0 0 18px; padding:12px 16px; border-left:4px solid var(--accent);
  background:var(--accent-bg); font-size:14.5px; border-radius:0 8px 8px 0;
}
.na{color:var(--faint);}
.url{color:var(--accent); word-break:break-all;}
.num{text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums;}
.ct{font-size:11.5px; color:var(--faint); border:1px solid var(--border); border-radius:3px;
  padding:0 .35em; margin-right:.35em;}
.ctcell{min-width:20em; font-size:13.5px;}
tbody tr.noterow td{
  font-size:13px; line-height:1.7; color:var(--muted); padding-top:0;
  border-bottom:2px solid var(--border-strong);
}
tbody tr.noterow{background:transparent!important;}
.src{margin-top:.3em; font-size:12px; color:var(--faint);}
.sub{font-size:12.5px; color:var(--muted); font-weight:400;}
@media print{
  .warnbox{border:3pt solid #000; border-left:6pt solid #000; background:#fff;}
  .card{border:1pt solid #000; background:#fff;}
  .card-hi{border:2.5pt solid #000;}
  .rank{background:#fff; color:#000; border:1pt solid #000;}
  .chip,.chip-a,.chip-no{background:#fff!important; color:#000!important; border:1pt solid #000!important;}
  .note{background:#fff; border-left:3pt solid #000;}
  .url,a{color:#000;}
}
"""

# ---------------------------------------------------------------- 動的な文言
N = len(rows)
SNAP = datetime.fromtimestamp(SRC.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
review = [r for r in rows if r["optout_needs_review"].strip().lower() == "true"]
review_txt = ""
if review:
    names = "、".join(f'{r["順位"]}位 {r["メーカー名"]}' for r in review)
    review_txt = (f'<p class="note"><strong>{H.escape(names)} は、打診の前に公式サイトを自分の目で'
                  f"確認してください。</strong>自動判定は A（打診してよい）ですが、拒否表現との判別が"
                  f"つききらなかったと記録されています。理由は一覧の該当行に書いてあります。</p>")
masked = [r for r in rows if personal(r)]
masked_txt = ""
if masked:
    names = "、".join(f'{r["順位"]}位 {r["メーカー名"]}' for r in masked)
    masked_txt = (f"個人事業主の疑いがあると記録された社（{H.escape(names)}）の電話・所在地は、"
                  f"本リポジトリが公開であるため本ページでは伏せています（CSV 側には値が残っています）。")

count_tbl = f"""<div class="tw" tabindex="0"><table><thead><tr>
<th>区分</th><th>社数</th><th>この資料での扱い</th></tr></thead><tbody>
<tr><td>A_PLUS</td><td class="num">{len(aplus)}</td><td>OEM・小ロット・B2B窓口のいずれかを公式サイトに明示している社。先頭にカードで置いた。ここから打診する</td></tr>
<tr><td>A</td><td class="num">{len(plain)}</td><td>営業お断りの表示が見つからなかった社。A_PLUS を消化した後、優先度順に</td></tr>
<tr class="row-danger"><td>B・C・D・E</td><td class="num">{len(stop)}</td><td>打診しない／条件付き。理由を1社ずつ併記した（最終節）</td></tr>
</tbody></table></div>"""

doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>メーカー打診候補リスト（{N}社・優先度順）</title>
<meta name="robots" content="noindex, nofollow">
<style>{CSS}{EXTRA_CSS}</style>
</head>
<body id="top">
<div class="wrap">
<p class="kicker">T-20260904-004 ／ メーカー直レーン ／ CSV {SNAP} 時点のスナップショット</p>
<h1>メーカー打診候補リスト（{N}社・優先度順）</h1>
<p class="lead">出典は B1_打診候補_全社_優先度順.csv（{N}社・{SNAP} 時点）。このページは同 CSV の表示版で、値は書き換えていない。CSV はまだ追記が続いているため、社数が増えていたら再生成すること。</p>

<section class="warnbox">
<h2>打診メールに URL を貼らないこと</h2>
<p><strong>メール本文・署名に URL を一切貼らない。</strong>Amazon ストアの URL、自社サイト satoy-select.com、SNS、すべてです。</p>
<p class="why">貼った瞬間に特定電子メール法2条2号の「広告宣伝ウェブサイトへの誘導」に該当し、相手の「営業お断り」表示が法的効力を持ちます。白が黒に転ぶ唯一の分岐点です。<br>
（特定電子メール法＝広告・宣伝目的のメールを規制する法律。URL を貼ると「広告メール」に分類され、相手が拒否している場合は違法になり得ます）</p>
<p><strong>そのほかの絶対条件:</strong> 1社1通・追送しない・断られたら即終了・一斉送信ツール禁止・実績ゼロを正直に書く。</p>
<p class="why">上記は CSV 1行目の法務注記（打診文の絶対条件・法務判定 v1.0）の原文です:<br>{H.escape(HEADER_NOTE)}</p>
</section>

<section class="sec">
<h2>この {N} 社の内訳</h2>
{count_tbl}
{review_txt}
<p class="note">打診の順番は <strong>A_PLUS {len(aplus)}社 → A {len(plain)}社（優先度順）</strong>。C は A・A_PLUS・B を全件消化した後、フォームのみ・1回限り。D・E には連絡しない。</p>
</section>

<h1 class="part" id="p1">A_PLUS ─ 最優先の{len(aplus)}社</h1>
<section class="sec">
<p>公式サイトに <strong>OEM・小ロット・B2B の窓口</strong> を自ら明示している社です。個人事業主でも門前払いにならない可能性が最も高い層で、ここから当たります。</p>
<p class="note"><strong>3位のイガラシは、{N}社で唯一「当社が対象に含まれる」と公式に書いている社です。</strong>法人向けフォームに「※個人事業主・法人の方が対象となります」と明記され、問い合わせ種別に「OEM生産についてのお問い合わせ」「新規の取引についてお問い合わせ」があります。<strong>最初の1通はここに出すのが最も理にかなっています。</strong></p>
{"".join(card(r, highlight=(r["メーカー名"].startswith("イガラシ"))) for r in aplus)}
</section>

<h1 class="part" id="p2">A ─ 打診してよい{len(plain)}社（優先度順）</h1>
<section class="sec">
<p>公式サイトに営業お断りの表示が見つからなかった社です。上の行から順に当たります。各社の下段は、調査時のメモと出典です。</p>
<div class="tw" tabindex="0"><table><thead><tr>
<th>順位</th><th>メーカー名</th><th>カテゴリ</th><th>商品数</th><th>仕入れ ⇢ Amazon<br>（中央値）</th><th>確度</th><th>連絡先</th>
</tr></thead><tbody>
{list_rows(plain)}
</tbody></table></div>
</section>

<h1 class="part" id="p3">B・C・D・E ─ 打診しない／条件付きの{len(stop)}社</h1>
<section class="sec">
<p><strong>D・E は連絡しません。</strong>とくに <strong>愛知電線</strong>はフォームに「セールス・勧誘等があった場合、迷惑メール相談センターに通報します」と通報を明示しています。<strong>すごろくや</strong>は「実店舗をお持ちでないオンライン専売業者さまとのお取引は一律お断り」「Amazon・楽天市場・Yahoo!ショッピング・メルカリなど大手ECモールへの出品をご遠慮いただいております」と明記しており、Amazon 専業・実店舗なしの当社は<strong>構造的に対象外</strong>です。</p>
<div class="tw" tabindex="0"><table><thead><tr>
<th>順位</th><th>メーカー名</th><th>判定</th><th>公式サイトの表示（原文）</th><th>備考（調査時のメモ・原文）</th><th>再打診できる条件</th>
</tr></thead><tbody>
{stop_rows(stop)}
</tbody></table></div>
</section>

<p class="prov">内容の唯一の正は workspace/output/deliverables/T-20260904-004/B1_打診候補_全社_優先度順.csv（{SNAP} 時点・{N}社）です。本ファイルは同 CSV を機械変換した表示版で、値の書き換え・要約はしていません（備考の重複表現も原文のまま出しています）。{masked_txt}</p>
</div>
<a class="top" href="#top" aria-label="先頭へ戻る">&#8593;</a>
</body>
</html>
"""

DST.write_text(doc, encoding="utf-8")
print(f"OK: {DST} ({len(doc.encode('utf-8')):,} bytes) / 全{N}社 "
      f"/ A_PLUS {len(aplus)} / A {len(plain)} / 打診不可等 {len(stop)} / 要確認 {len(review)} / 伏せ {len(masked)}")
