#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown -> 単一自己完結HTML コンバータ（コンテンツ制作ヒデアキ / 汎用スキル）

社長の常設ルール「分量のある資料はテキスト + HTML の併出力」を満たすための道具。
原稿(.md)を唯一の正とし、加筆・削除・言い換えを一切せずに HTML 化する。

対応する Markdown サブセット:
  h1 / h2 / h3, 段落, 表, 箇条書き(2階層), 番号付きリスト, 引用, 水平線
  インライン: **強調**, `コード`, [#n] 根拠マーカー, [要確認 #n] 注意バッジ

出力の性質:
  - 外部CSS/JS/フォント/画像を一切読み込まない（オフラインで開ける）
  - ライト/ダーク両対応（prefers-color-scheme）、印刷用スタイル同梱
  - 目次を自動生成、表は横スクロール可能なコンテナに格納

使い方:
  python3 md_to_standalone_html.py 入力.md 出力.html \
      --title "ブラウザのタブに出すタイトル" \
      --kicker "T-XXXXXXXX-XXX" \
      --box "1. 結論=conclusion" --box "わからなかったこと=alert" --box "信頼度=alert" \
      --note "HTML版。内容の唯一の正は ... です。"

  --box は「見出しの完全一致 or 前方一致=スタイル」。該当する h2 節を囲み枠にして強調する。
  スタイルは conclusion / alert / danger / warn / checklist の5種。
  --cellmark は「語=danger|warn」。表セル内のその語だけを色付きピルにする（本文は触らない）。

注意（実際に踏んだ失敗）:
  - 段落判定でリスト記号を「記号のみ」で弾くと `**強調で始まる段落**` が消える。
    必ず「記号＋空白」で判定する。
  - 区切り線 `---` は節を閉じてから出す。閉じずに出すと囲み枠の内側に線が引かれる。
  - 目次の入れ子は `.toc ul`（詳細度0,2,1）が `.toc-l2`（0,1,0）に勝つ。詳細度に注意。
  - 生成後は必ず (1) 原稿の全行がHTMLに在るか機械照合し、(2) headless Chrome で描画して目で見る。
"""
import argparse
import html
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- inline

RE_CHECK = re.compile(r"\[要確認\s*#(\d+)\]")
RE_REF = re.compile(r"\[#(\d+)\]")
RE_CODE = re.compile(r"`([^`]+)`")
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_PH = re.compile(r"\x00C(\d+)\x00")

# 表セル内だけで働く語ハイライト。[(語, スタイル, 先頭限定か)]
CELLMARKS = []

# --reftable で拾った出典番号。[#n] をこの表の行へリンクするために使う
REFIDS = set()


def _markers(s: str) -> str:
    # 順序重要: [要確認 #n] を先に処理しないと [#n] 側に食われる
    s = RE_CHECK.sub(lambda m: f'<span class="chk">要確認 #{m.group(1)}</span>', s)

    def _ref(m):
        n = m.group(1)
        # 出典表に該当行があるときだけリンクにする。無い番号を飛ばすと迷子になる
        if int(n) in REFIDS:
            return f'<a class="ref" href="#src-{n}">[#{n}]</a>'
        return f'<span class="ref">[#{n}]</span>'

    return RE_REF.sub(_ref, s)


def inline(text: str) -> str:
    """インライン変換。エスケープ後に記法と根拠マーカーだけをマークアップする。

    処理順は コード → 強調 → マーカー。コードは先に退避し、中では強調をかけない
    （原稿の `[要確認 #1]` はコード内でもバッジにしたいのでマーカーだけ通す）。
    """
    out = html.escape(text, quote=False)
    codes = []

    def _stash(m):
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    out = RE_CODE.sub(_stash, out)
    out = RE_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _markers(out)
    return RE_PH.sub(lambda m: f"<code>{_markers(codes[int(m.group(1))])}</code>", out)


RE_TAG = re.compile(r"<[^>]+>")


def cell(text: str):
    """表セル用。inline に加えて CELLMARKS の語を色付きピルにする。

    戻り値は (HTML, 付与したスタイルの集合)。呼び出し側が行の強調に使う。

    語の先頭に `^` を付けると「セルの文頭にある時だけ」1個目を置換する（先頭限定）。
    判定語（一致/不一致/未実施 等）は他のセルの文中にも出るため、
    素の部分一致だと無関係な行を塗ってしまう（実際に「購買者情報の不一致」で踏んだ）。
    """
    out = inline(text)
    hits = set()
    for word, style, head_only in CELLMARKS:
        if head_only:
            plain = RE_TAG.sub("", out).lstrip()
            if not plain.startswith(word):
                continue
            hits.add(style)
            out = out.replace(word, f'<span class="pill pill-{style}">{word}</span>', 1)
        elif word in out:
            hits.add(style)
            out = out.replace(word, f'<span class="pill pill-{style}">{word}</span>')
    return out, hits


# ---------------------------------------------------------------- block

def split_row(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:\-|]+\|", line.strip()))


class Builder:
    def __init__(self, lines, boxes=(), reftable="", refwidths=()):
        self.boxes = list(boxes)   # [(見出しに含まれる文字列, "conclusion"|"alert")]
        self.reftable = reftable   # この h2 節の表を「出典一覧」として扱う
        self.refwidths = list(refwidths)
        self.in_reftable = False
        self.lines = lines
        self.i = 0
        self.out = []
        self.toc = []          # [(level, id, text)]
        self.sec_open = False
        self.h1 = ""
        self.h2n = 0
        self.h3n = 0
        self.partn = 0

    # -- helpers
    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None

    def close_section(self):
        if self.sec_open:
            self.out.append("</section>")
            self.sec_open = False

    def sec_class(self, title: str) -> str:
        """--box の照合は 完全一致 → 前方一致 の順。部分一致は取らない。

        部分一致にすると "結論" が「1-A. 一覧（先に結論）」まで巻き込み、
        意図しない節が囲み枠になる（実際に踏んだ）。
        """
        for needle, style in self.boxes:
            if needle == title:
                return " sec-box sec-" + style
        for needle, style in self.boxes:
            if title.startswith(needle):
                return " sec-box sec-" + style
        return ""

    # -- main
    def run(self):
        while self.i < len(self.lines):
            line = self.lines[self.i]
            s = line.strip()

            if not s:
                self.i += 1
                continue

            if s == "---":
                # 区切り線は節の「間」に置く。閉じずに出すと囲み枠の内側に線が引かれる
                self.close_section()
                self.out.append('<hr class="rule">')
                self.i += 1
                continue

            if line.startswith("# "):
                title = line[2:].strip()
                if not self.h1:
                    self.h1 = title           # 最初の h1 だけが文書タイトル
                else:
                    # 2つ目以降の h1 は「部」の区切り。捨てると本文が消える
                    self.partn += 1
                    hid = f"p{self.partn}"
                    self.in_reftable = False
                    self.close_section()
                    self.out.append(f'<h1 class="part" id="{hid}">{inline(title)}</h1>')
                    self.toc.append((1, hid, title, "part"))
                self.i += 1
                continue

            if line.startswith("## "):
                title = line[3:].strip()
                self.h2n += 1
                self.h3n = 0
                hid = f"s{self.h2n}"
                self.in_reftable = bool(self.reftable) and title == self.reftable
                self.close_section()
                scls = self.sec_class(title)
                self.out.append(f'<section id="{hid}" class="sec{scls}">')
                self.sec_open = True
                self.out.append(f"<h2>{inline(title)}</h2>")
                self.toc.append((2, hid, title, scls.replace(" sec-box sec-", "")))
                self.i += 1
                continue

            if line.startswith("### "):
                title = line[4:].strip()
                self.h3n += 1
                hid = f"s{self.h2n}-{self.h3n}"
                self.out.append(f'<h3 id="{hid}">{inline(title)}</h3>')
                self.toc.append((3, hid, title, ""))
                self.i += 1
                continue

            if s.startswith("|"):
                self.table()
                continue

            if s.startswith("> "):
                self.quote()
                continue

            if re.match(r"^\s*-\s", line):
                self.ulist()
                continue

            if re.match(r"^\d+\.\s", line):
                self.olist()
                continue

            self.para()
        self.close_section()
        return self

    def table(self):
        rows = []
        while self.i < len(self.lines) and self.lines[self.i].strip().startswith("|"):
            rows.append(self.lines[self.i])
            self.i += 1
        head = split_row(rows[0])
        body = [split_row(r) for r in rows[1:] if not is_sep_row(r)]
        ref = self.in_reftable
        t = ['<div class="tw" tabindex="0"><table' + (' class="reftable"' if ref else "") + ">"]
        if ref and len(self.refwidths) == len(head):
            # 列幅を指定しないと、自動計算が URL 列に幅を持っていかれて
            # 要旨の列が縦長の1文字帯になる（実際にそうなった）
            t.append("<colgroup>"
                     + "".join(f'<col style="width:{w}">' for w in self.refwidths)
                     + "</colgroup>")
        t.append("<thead><tr>")
        t += [f"<th>{inline(c)}</th>" for c in head]
        t.append("</tr></thead><tbody>")
        for r in body:
            tds, hits = [], set()
            for c in r:
                h, hit = cell(c)
                tds.append(f"<td>{h}</td>")
                hits |= hit
            attr = ' class="row-danger"' if "danger" in hits else ""
            # 出典表は1列目の番号を id にして、本文の [#n] から飛べるようにする
            if ref and r and r[0].strip().isdigit():
                attr += f' id="src-{r[0].strip()}"'
            t.append(f"<tr{attr}>" + "".join(tds) + "</tr>")
        t.append("</tbody></table></div>")
        self.out.append("".join(t))

    def quote(self):
        parts = []
        while self.i < len(self.lines) and self.lines[self.i].strip().startswith(">"):
            parts.append(self.lines[self.i].strip().lstrip(">").strip())
            self.i += 1
        self.out.append("<blockquote><p>" + "<br>".join(inline(p) for p in parts) + "</p></blockquote>")

    def ulist(self):
        items = []  # (level, text)
        while self.i < len(self.lines):
            m = re.match(r"^(\s*)-\s+(.*)$", self.lines[self.i])
            if not m:
                break
            items.append((len(m.group(1)) // 2, m.group(2).rstrip()))
            self.i += 1
        buf = ["<ul>"]
        depth = 0
        for lv, txt in items:
            while lv > depth:
                buf.append("<ul>")
                depth += 1
            while lv < depth:
                buf.append("</ul>")
                depth -= 1
            buf.append(f"<li>{inline(txt)}</li>")
        while depth > 0:
            buf.append("</ul>")
            depth -= 1
        buf.append("</ul>")
        self.out.append("".join(buf))

    def olist(self):
        buf = ["<ol>"]
        while self.i < len(self.lines):
            m = re.match(r"^\d+\.\s+(.*)$", self.lines[self.i])
            if not m:
                break
            buf.append(f"<li>{inline(m.group(1).rstrip())}</li>")
            self.i += 1
        buf.append("</ol>")
        self.out.append("".join(buf))

    def para(self):
        parts = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            s = line.strip()
            if (not s) or s == "---" or s.startswith(("#", "|", ">")) \
               or re.match(r"^\s*-\s", line) or re.match(r"^\d+\.\s", line):
                break
            parts.append(s)
            self.i += 1
        if parts:
            self.out.append("<p>" + "<br>".join(inline(p) for p in parts) + "</p>")


def render_toc(toc):
    """見出しは自前で採番されているので ol は使わない（二重採番の事故を避ける）。"""
    buf = ['<nav class="toc" aria-label="目次"><p class="toc-h">目次</p><ul class="toc-list">']
    for lv, hid, title, style in toc:
        cls = f"toc-lv{lv}"
        acls = f' class="toc-{style}"' if style and style != "part" else ""
        buf.append(f'<li class="{cls}"><a href="#{hid}"{acls}>{inline(title)}</a></li>')
    buf.append("</ul></nav>")
    return "".join(buf)


CSS = """
:root{
  color-scheme: light dark;
  --bg:#ffffff; --surface:#f5f7f9; --surface2:#eceff3;
  --text:#1b1f24; --muted:#525b66; --faint:#6c7681;
  --border:#d5dae1; --border-strong:#b8c0ca;
  --accent:#1c5b86; --accent-bg:#eef5fa;
  --warn:#8a4b00; --warn-bg:#fdf1df; --warn-border:#dd9a3c;
  --alert:#7d2b2b; --alert-bg:#fbeeee; --alert-border:#d08b8b;
  --ok:#1b6144; --ok-bg:#eaf4ef; --ok-border:#8ab9a3;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#15181c; --surface:#1d2126; --surface2:#252a31;
    --text:#e4e8ec; --muted:#aab4bf; --faint:#949eaa;
    --border:#333a43; --border-strong:#48515c;
    --accent:#79b4dc; --accent-bg:#1a2a36;
    --warn:#f0b866; --warn-bg:#332616; --warn-border:#7a5a2a;
    --alert:#e79a9a; --alert-bg:#331e1e; --alert-border:#6e4040;
    --ok:#84cfa9; --ok-bg:#17281f; --ok-border:#3c6450;
  }
}
*{box-sizing:border-box;}
html{ -webkit-text-size-adjust:100%; }
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic Medium","Yu Gothic",
              "Noto Sans JP","Meiryo",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:16px; line-height:1.85;
  font-feature-settings:"palt" 1;
  text-align:left;
}
.wrap{max-width:900px; margin:0 auto; padding:32px 20px 96px;}

/* ---------- header ---------- */
.kicker{
  font-size:12px; letter-spacing:.14em; color:var(--faint);
  margin:0 0 10px; font-variant-numeric:tabular-nums;
}
h1{
  font-size:27px; line-height:1.5; margin:0 0 20px;
  letter-spacing:.01em; font-weight:700; text-wrap:balance;
}
.lead{
  margin:0; color:var(--muted); font-size:15px; line-height:1.8;
  border-left:3px solid var(--border-strong); padding:2px 0 2px 14px;
}

/* ---------- toc ---------- */
.toc{
  margin:30px 0 8px; padding:18px 22px 20px;
  background:var(--surface); border:1px solid var(--border); border-radius:10px;
}
.toc-h{
  margin:0 0 10px; font-size:13px; font-weight:700;
  letter-spacing:.1em; color:var(--muted);
}
.toc ul.toc-list{margin:0; padding:0; list-style:none;}
.toc li{margin:.26em 0; line-height:1.65;}
.toc li.toc-lv1{margin:.85em 0 .3em; font-weight:700;}
.toc li.toc-lv1:first-child{margin-top:0;}
.toc li.toc-lv2{padding-left:1.1em;}
.toc li.toc-lv3{padding-left:2.5em; font-size:14.5px; color:var(--muted); margin:.16em 0;}
.toc li.toc-lv3::before{content:"–"; color:var(--faint); margin-right:.45em;}
.toc a{color:var(--accent); text-decoration:none; border-bottom:1px solid transparent;}
.toc a:hover{border-bottom-color:currentColor;}

/* ---------- part ---------- */
h1.part{
  font-size:24px; line-height:1.5; font-weight:700; letter-spacing:.02em;
  margin:64px 0 8px; padding:14px 0 0; border-top:4px solid var(--text);
  scroll-margin-top:16px;
}

/* ---------- sections ---------- */
.sec{margin:0;}
.sec>*:last-child{margin-bottom:0;}
h2{
  font-size:21px; line-height:1.5; margin:46px 0 16px; padding-bottom:9px;
  border-bottom:2px solid var(--border-strong); font-weight:700;
  scroll-margin-top:16px;
}
h3{
  font-size:17px; line-height:1.6; margin:32px 0 12px; font-weight:700;
  color:var(--text); scroll-margin-top:16px;
}
h3::before{content:""; display:inline-block; width:4px; height:1em;
  background:var(--accent); margin-right:9px; vertical-align:-.13em; border-radius:2px;}
p{margin:0 0 1.1em;}
ul,ol{margin:0 0 1.2em; padding-left:1.6em;}
li{margin:.4em 0;}
li>ul{margin:.45em 0 .2em;}
blockquote{
  margin:0 0 1.2em; padding:14px 18px;
  background:var(--surface); border-left:4px solid var(--accent); border-radius:0 8px 8px 0;
}
blockquote p{margin:0;}
hr.rule{
  border:0; border-top:1px solid var(--border);
  margin:40px 0 0; opacity:.55;
}
hr.rule:has(+ .sec-box),hr.rule:has(+ h1.part){display:none;}

/* ---------- tables ---------- */
.tw{
  overflow-x:auto; -webkit-overflow-scrolling:touch;
  margin:0 0 1.4em; border:1px solid var(--border); border-radius:9px;
  background:
    linear-gradient(to right, var(--bg) 30%, rgba(0,0,0,0)) left / 28px 100% no-repeat local,
    linear-gradient(to left,  var(--bg) 30%, rgba(0,0,0,0)) right / 28px 100% no-repeat local,
    radial-gradient(farthest-side at 0 50%, rgba(90,110,130,.28), rgba(0,0,0,0)) left / 12px 100% no-repeat scroll,
    radial-gradient(farthest-side at 100% 50%, rgba(90,110,130,.28), rgba(0,0,0,0)) right / 12px 100% no-repeat scroll;
}
.tw:focus{outline:2px solid var(--accent); outline-offset:2px;}
table{border-collapse:collapse; width:100%; font-size:14.5px; line-height:1.72;}
thead th{
  background:var(--surface2); text-align:left; font-weight:700;
  padding:11px 14px; border-bottom:2px solid var(--border-strong);
  white-space:nowrap; vertical-align:bottom;
}
tbody td{padding:11px 14px; border-bottom:1px solid var(--border); vertical-align:top;
  overflow-wrap:anywhere;}
tbody tr:last-child td{border-bottom:0;}
tbody tr:nth-child(even){background:color-mix(in srgb, var(--surface) 55%, transparent);}
tbody td:first-child{font-weight:600;}
thead th:first-child,tbody td:first-child{min-width:7.5em;}
thead th:last-child,tbody td:last-child{white-space:normal;}

/* ---------- inline markers ---------- */
.ref{
  font-size:.75em; color:var(--faint); margin-left:.15em;
  white-space:nowrap; font-variant-numeric:tabular-nums;
  letter-spacing:.01em; vertical-align:.06em;
}
/* [#n] は出典表に行がある時だけリンクになる。見た目は span と同じにして
   本文の印象を変えない（追加したのは移動手段だけで、文字は足していない） */
a.ref{text-decoration:none;}
a.ref:hover,a.ref:focus{color:var(--accent); text-decoration:underline;}
.chk{
  display:inline-block; font-size:.75em; line-height:1.5;
  padding:0 .5em; margin:0 .12em; border-radius:4px;
  background:var(--warn-bg); color:var(--warn);
  border:1px solid var(--warn-border); font-weight:700;
  white-space:nowrap; vertical-align:.09em;
}

/* ---------- inline emphasis ---------- */
strong{font-weight:700; color:var(--text);}
td strong,th strong{font-weight:700;}
code{
  font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
  font-size:.9em; padding:.05em .35em; border-radius:4px;
  background:var(--surface2); border:1px solid var(--border);
}
code .chk{font-family:inherit;}

/* ---------- 表セル内の語ハイライト ---------- */
.pill{
  display:inline-block; padding:0 .45em; border-radius:4px;
  font-weight:700; white-space:nowrap;
}
.pill-danger{background:var(--alert); color:#fff; border:1px solid var(--alert);}
.pill-warn{background:var(--warn-bg); color:var(--warn); border:1px solid var(--warn-border);}
.pill-ok{background:var(--ok-bg); color:var(--ok); border:1px solid var(--ok-border);}
.pill-info{background:var(--accent-bg); color:var(--accent); border:1px solid var(--accent);}
/* muted は「検証していない」を表す。塗らず・破線で、済んだものと視覚的に別系統にする */
.pill-muted{background:transparent; color:var(--faint);
  border:1px dashed var(--border-strong); font-weight:600;}
tbody tr.row-danger td:first-child{box-shadow:inset 4px 0 0 var(--alert);}
tbody tr.row-danger td{background:color-mix(in srgb, var(--alert-bg) 70%, transparent);}

/* ---------- 出典一覧（--reftable） ---------- */
table.reftable:has(colgroup){table-layout:fixed; min-width:600px;}
/* 狭い画面で列が1〜2文字幅に潰れるのを防ぐ。溢れは .tw の横スクロールが受ける */
table.reftable td:first-child{
  min-width:2.6em; width:2.6em; text-align:right; white-space:nowrap;
  font-variant-numeric:tabular-nums; color:var(--muted);
}
table.reftable th:first-child{min-width:2.6em; width:2.6em; text-align:right;}
tbody tr[id]{scroll-margin-top:14px;}
tbody tr[id]:target td{background:var(--accent-bg);}
tbody tr[id]:target td:first-child{box-shadow:inset 4px 0 0 var(--accent); color:var(--accent);}

/* ---------- emphasised sections ---------- */
.sec-box{
  margin:28px 0 0; padding:6px 26px 20px;
  border:1px solid var(--border-strong); border-radius:10px;
}
.sec-box h2{margin-top:26px;}
.sec-box .tw{background-color:var(--bg);}
.sec-conclusion{background:var(--accent-bg); border-left:6px solid var(--accent);}
.sec-conclusion h2{border-bottom-color:var(--accent);}
.sec-alert{background:var(--alert-bg); border-color:var(--alert-border);
  border-left:6px solid var(--alert);}
.sec-alert h2{border-bottom-color:var(--alert-border);}
.sec-danger{background:var(--alert-bg); border:2px solid var(--alert);
  border-left:10px solid var(--alert);}
.sec-danger h2{border-bottom-color:var(--alert);}
.sec-warn{background:var(--warn-bg); border-color:var(--warn-border);
  border-left:6px solid var(--warn-border);}
.sec-warn h2{border-bottom-color:var(--warn-border);}
.sec-checklist{background:var(--surface); border:2px solid var(--border-strong);
  border-left:10px solid var(--accent);}
.sec-checklist h2{border-bottom-color:var(--accent);}
/* チェックリストは印刷して手元で使う。番号は原稿どおり残し、記入欄だけ CSS で足す */
.sec-checklist ol{list-style:decimal; padding-left:1.9em;}
.sec-checklist ol>li{margin:.7em 0; padding-left:2.1em; position:relative;}
.sec-checklist ol>li::before{
  content:""; position:absolute; left:0; top:.25em;
  width:1.15em; height:1.15em; border:1.5px solid var(--border-strong);
  border-radius:3px; background:var(--bg);
}

/* ---------- toc: 囲み枠の節は目次でも色を付ける ---------- */
.toc a.toc-danger,.toc a.toc-alert{color:var(--alert); font-weight:700;}
.toc a.toc-warn{color:var(--warn); font-weight:700;}
.toc a.toc-checklist{color:var(--accent); font-weight:700;}

/* ---------- footer / nav ---------- */
.prov{
  margin:56px 0 0; padding-top:16px; border-top:1px solid var(--border);
  font-size:12.5px; line-height:1.8; color:var(--faint); word-break:break-all;
}
.top{
  position:fixed; right:18px; bottom:18px; z-index:5;
  display:block; width:42px; height:42px; line-height:40px; text-align:center;
  border-radius:50%; text-decoration:none; font-size:17px;
  background:var(--surface); color:var(--muted);
  border:1px solid var(--border-strong);
  box-shadow:0 2px 8px rgba(0,0,0,.14);
}
.top:hover{color:var(--accent); border-color:var(--accent);}

/* ---------- narrow screens ---------- */
@media (max-width:640px){
  body{font-size:15.5px;}
  .wrap{padding:22px 14px 88px;}
  h1{font-size:22px;}
  h1.part{font-size:20px; margin-top:46px;}
  h2{font-size:19px;}
  h3{font-size:16.5px;}
  .toc{padding:14px 16px 16px;}
  .sec-box{padding:4px 14px 14px;}
  table{font-size:14px;}
  thead th,tbody td{padding:9px 11px;}
}

/* ---------- print ---------- */
@media print{
  :root{
    --bg:#fff; --surface:#fff; --surface2:#fff; --text:#000; --muted:#333; --faint:#555;
    --border:#999; --border-strong:#555; --accent:#000; --accent-bg:#fff;
    --warn:#000; --warn-bg:#fff; --warn-border:#000;
    --alert:#000; --alert-bg:#fff; --alert-border:#000;
  }
  body{background:#fff; color:#000; font-size:10.5pt; line-height:1.7;}
  .wrap{max-width:none; padding:0;}
  a{color:#000; text-decoration:none;}
  .top{display:none;}
  .tw{overflow:visible; background:none; border:1px solid #999;}
  table{font-size:9pt;}
  thead th{background:#fff; border-bottom:1.5pt solid #000;}
  tbody tr:nth-child(even){background:#fff;}
  .sec-box{background:#fff; border:1.5pt solid #000;}
  .sec-danger{border:2.5pt solid #000; border-left:2.5pt solid #000;}
  .chk{background:#fff; color:#000; border:1pt solid #000;}
  code{background:#fff; border:1px solid #999;}
  .pill{background:#fff!important; color:#000!important; border:1.2pt solid #000!important;}
  /* 未検証は印刷でも「済んだもの」と別に見えなければ意味がない。
     モノクロでは色が消えるので、破線と濃度で差を残す */
  .pill-muted{border:1pt dashed #666!important; color:#555!important; font-weight:400!important;}
  /* 長いURLは印刷で紙幅を超える。折り返しを許可して溢れを止める */
  .tw{overflow:hidden;}
  table{table-layout:auto; width:100%;}
  tbody td{overflow-wrap:anywhere; word-break:break-word;}
  thead th{white-space:normal;}
  table.reftable{font-size:7.6pt; line-height:1.5;}
  table.reftable thead th,table.reftable tbody td{padding:5px 6px;}
  tbody tr[id]:target td{background:#fff;}
  tbody tr.row-danger td{background:#fff;}
  tbody tr.row-danger td:first-child{box-shadow:inset 3pt 0 0 #000;}
  /* チェックリストは1枚で手元に置けるよう独立ページにする */
  .sec-checklist{break-before:page; page-break-before:always;
    border:1.5pt solid #000; border-left:1.5pt solid #000;}
  .sec-checklist ol>li::before{border:1.2pt solid #000;}
  .ref{color:#555; opacity:1;}
  blockquote{background:#fff; border-left:3pt solid #000;}
  h1.part{break-before:page; page-break-before:always; border-top:2.5pt solid #000;
    font-size:15pt; margin-top:0;}
  h1.part,h2,h3{break-after:avoid; page-break-after:avoid;}
  .tw,blockquote,tr{break-inside:avoid; page-break-inside:avoid;}
  .toc{border:1px solid #999; background:#fff;}
}
"""


def parse_box(v):
    if "=" not in v:
        raise argparse.ArgumentTypeError('--box は "見出しの一部=スタイル" 形式')
    needle, style = v.rsplit("=", 1)
    if style not in BOX_STYLES:
        raise argparse.ArgumentTypeError("スタイルは " + " / ".join(BOX_STYLES))
    return (needle.strip(), style)


BOX_STYLES = ("conclusion", "alert", "danger", "warn", "checklist")


CELL_STYLES = ("danger", "warn", "ok", "muted", "info")


def parse_cellmark(v):
    if "=" not in v:
        raise argparse.ArgumentTypeError('--cellmark は "語=' + "|".join(CELL_STYLES) + '" 形式')
    word, style = v.rsplit("=", 1)
    if style not in CELL_STYLES:
        raise argparse.ArgumentTypeError("cellmark のスタイルは " + " / ".join(CELL_STYLES))
    word = word.strip()
    head_only = word.startswith("^")
    return (word.lstrip("^"), style, head_only)


def scan_reftable(lines, title):
    """--reftable で指定した h2 節の表から、1列目の番号を集める。

    本文の [#n] をリンクにしてよいかは「行が実在するか」でしか判定できない。
    存在しない番号にリンクを張ると、押しても何も起きない死んだリンクになる。
    """
    ids, inside, intable = set(), False, False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip() == title
            intable = False
            continue
        if line.startswith("# "):
            inside = False
            continue
        if not inside:
            continue
        s = line.strip()
        if s.startswith("|"):
            if is_sep_row(s):
                intable = True
                continue
            if intable:
                c = split_row(s)[0]
                if c.isdigit():
                    ids.add(int(c))
        else:
            intable = False
    return ids


def main():
    ap = argparse.ArgumentParser(
        description="Markdown を単一自己完結HTMLに変換する（内容は改変しない）")
    ap.add_argument("src", type=Path, help="入力 Markdown")
    ap.add_argument("dst", type=Path, help="出力 HTML")
    ap.add_argument("--title", default=None, help="<title>（既定: 原稿のH1）")
    ap.add_argument("--kicker", default="", help="H1 の上に出す小見出し（チケットID等）")
    ap.add_argument("--box", action="append", type=parse_box, default=[],
                    metavar="見出し=conclusion|alert", help="囲み枠で強調する h2 節")
    ap.add_argument("--cellmark", action="append", type=parse_cellmark, default=[],
                    metavar="語=danger|warn|ok|muted|info",
                    help="表セル内でハイライトする語（先頭に ^ でセル文頭限定）")
    ap.add_argument("--reftable", default="",
                    help="出典一覧として扱う h2 見出し（本文の [#n] が該当行へリンクする）")
    ap.add_argument("--reftable-widths", default="",
                    help="出典表の列幅をカンマ区切りで指定（例 3em,28%,22%,15%,8%,23%）")
    ap.add_argument("--note", default="", help="末尾に置く出所注記（任意）")
    a = ap.parse_args()

    CELLMARKS[:] = a.cellmark

    lines = a.src.read_text(encoding="utf-8").split("\n")
    REFIDS.clear()
    if a.reftable:
        REFIDS.update(scan_reftable(lines, a.reftable))

    widths = [w.strip() for w in a.reftable_widths.split(",") if w.strip()]
    b = Builder(lines, a.box, a.reftable, widths).run()
    body = b.out

    # 先頭の1段落を lead に格上げし、H1 直下（目次の前）へ移す
    for idx, chunk in enumerate(body):
        if chunk.startswith("<p>"):
            body[idx] = '<p class="lead">' + chunk[3:]
            break
        if chunk.startswith("<section"):
            break
    lead_html = ""
    for idx, chunk in enumerate(body):
        if chunk.startswith('<p class="lead">'):
            lead_html = body.pop(idx)
            break
    while body and body[0].startswith("<hr"):
        body.pop(0)

    kicker = f'<p class="kicker">{html.escape(a.kicker)}</p>' if a.kicker else ""
    note = f'<p class="prov">{html.escape(a.note)}</p>' if a.note else ""

    doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(a.title or b.h1)}</title>
<meta name="robots" content="noindex, nofollow">
<style>{CSS}</style>
</head>
<body id="top">
<div class="wrap">
{kicker}
<h1>{inline(b.h1)}</h1>
{lead_html}
{render_toc(b.toc)}
{chr(10).join(body)}
{note}
</div>
<a class="top" href="#top" aria-label="先頭へ戻る">&#8593;</a>
</body>
</html>
"""
    a.dst.parent.mkdir(parents=True, exist_ok=True)
    a.dst.write_text(doc, encoding="utf-8")
    print(f"OK: {a.dst}  ({len(doc.encode('utf-8')):,} bytes) / 見出し {len(b.toc)}"
          + (f" / 出典 {len(REFIDS)} 行" if REFIDS else ""))


if __name__ == "__main__":
    sys.exit(main())
