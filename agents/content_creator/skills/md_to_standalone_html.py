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
  インライン: [#n] 根拠マーカー, [要確認 #n] 注意バッジ

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

  --box は「見出しに含まれる文字列=スタイル」。スタイルは conclusion / alert の2種。
  該当する h2 節を囲み枠にして視覚的に強調する。

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


def inline(text: str) -> str:
    """インライン変換。エスケープ後に根拠マーカーだけをマークアップする。"""
    out = html.escape(text, quote=False)
    # 順序重要: [要確認 #n] を先に処理しないと [#n] 側に食われる
    out = RE_CHECK.sub(
        lambda m: f'<span class="chk">要確認 #{m.group(1)}</span>', out
    )
    out = RE_REF.sub(lambda m: f'<span class="ref">[#{m.group(1)}]</span>', out)
    return out


# ---------------------------------------------------------------- block

def split_row(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep_row(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:\-|]+\|", line.strip()))


class Builder:
    def __init__(self, lines, boxes=()):
        self.boxes = list(boxes)   # [(見出しに含まれる文字列, "conclusion"|"alert")]
        self.lines = lines
        self.i = 0
        self.out = []
        self.toc = []          # [(level, id, text)]
        self.sec_open = False
        self.h1 = ""
        self.h2n = 0
        self.h3n = 0

    # -- helpers
    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None

    def close_section(self):
        if self.sec_open:
            self.out.append("</section>")
            self.sec_open = False

    def sec_class(self, title: str) -> str:
        for needle, style in self.boxes:
            if needle in title:
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
                self.h1 = line[2:].strip()
                self.i += 1
                continue

            if line.startswith("## "):
                title = line[3:].strip()
                self.h2n += 1
                self.h3n = 0
                hid = f"s{self.h2n}"
                self.close_section()
                self.out.append(f'<section id="{hid}" class="sec{self.sec_class(title)}">')
                self.sec_open = True
                self.out.append(f"<h2>{inline(title)}</h2>")
                self.toc.append((2, hid, title))
                self.i += 1
                continue

            if line.startswith("### "):
                title = line[4:].strip()
                self.h3n += 1
                hid = f"s{self.h2n}-{self.h3n}"
                self.out.append(f'<h3 id="{hid}">{inline(title)}</h3>')
                self.toc.append((3, hid, title))
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
        t = ['<div class="tw" tabindex="0"><table>', "<thead><tr>"]
        t += [f"<th>{inline(c)}</th>" for c in head]
        t.append("</tr></thead><tbody>")
        for r in body:
            t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
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
    buf = ['<nav class="toc" aria-label="目次"><p class="toc-h">目次</p><ol class="toc-l1">']
    open_sub = False
    first = True
    for lv, hid, title in toc:
        if lv == 2:
            if open_sub:
                buf.append("</ul>")
                open_sub = False
            if not first:
                buf.append("</li>")
            buf.append(f'<li><a href="#{hid}">{inline(title)}</a>')
            first = False
        else:
            if not open_sub:
                buf.append('<ul class="toc-l2">')
                open_sub = True
            buf.append(f'<li><a href="#{hid}">{inline(title)}</a></li>')
    if open_sub:
        buf.append("</ul>")
    if not first:
        buf.append("</li>")
    buf.append("</ol></nav>")
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
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#15181c; --surface:#1d2126; --surface2:#252a31;
    --text:#e4e8ec; --muted:#aab4bf; --faint:#949eaa;
    --border:#333a43; --border-strong:#48515c;
    --accent:#79b4dc; --accent-bg:#1a2a36;
    --warn:#f0b866; --warn-bg:#332616; --warn-border:#7a5a2a;
    --alert:#e79a9a; --alert-bg:#331e1e; --alert-border:#6e4040;
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
.toc ol,.toc ul{margin:0; padding:0; list-style:none;}
.toc li{margin:.26em 0; line-height:1.65;}
/* .toc ul より詳細度を上げないと padding:0 に負ける */
.toc ul.toc-l2{padding-left:1.6em; margin:.25em 0 .6em;}
.toc ul.toc-l2 li{font-size:14.5px; color:var(--muted); margin:.16em 0;}
.toc ul.toc-l2 li::before{content:"–"; color:var(--faint); margin-right:.45em;}
.toc a{color:var(--accent); text-decoration:none; border-bottom:1px solid transparent;}
.toc a:hover{border-bottom-color:currentColor;}

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
hr.rule:has(+ .sec-box){display:none;}

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
tbody td{padding:11px 14px; border-bottom:1px solid var(--border); vertical-align:top;}
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
.chk{
  display:inline-block; font-size:.75em; line-height:1.5;
  padding:0 .5em; margin:0 .12em; border-radius:4px;
  background:var(--warn-bg); color:var(--warn);
  border:1px solid var(--warn-border); font-weight:700;
  white-space:nowrap; vertical-align:.09em;
}

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
  .chk{background:#fff; color:#000; border:1pt solid #000;}
  .ref{color:#555; opacity:1;}
  blockquote{background:#fff; border-left:3pt solid #000;}
  h2,h3{break-after:avoid; page-break-after:avoid;}
  .tw,blockquote,tr{break-inside:avoid; page-break-inside:avoid;}
  .toc{border:1px solid #999; background:#fff;}
}
"""


def parse_box(v):
    if "=" not in v:
        raise argparse.ArgumentTypeError('--box は "見出しの一部=conclusion|alert" 形式')
    needle, style = v.rsplit("=", 1)
    if style not in ("conclusion", "alert"):
        raise argparse.ArgumentTypeError("スタイルは conclusion か alert")
    return (needle.strip(), style)


def main():
    ap = argparse.ArgumentParser(
        description="Markdown を単一自己完結HTMLに変換する（内容は改変しない）")
    ap.add_argument("src", type=Path, help="入力 Markdown")
    ap.add_argument("dst", type=Path, help="出力 HTML")
    ap.add_argument("--title", default=None, help="<title>（既定: 原稿のH1）")
    ap.add_argument("--kicker", default="", help="H1 の上に出す小見出し（チケットID等）")
    ap.add_argument("--box", action="append", type=parse_box, default=[],
                    metavar="見出し=conclusion|alert", help="囲み枠で強調する h2 節")
    ap.add_argument("--note", default="", help="末尾に置く出所注記（任意）")
    a = ap.parse_args()

    b = Builder(a.src.read_text(encoding="utf-8").split("\n"), a.box).run()
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
    print(f"OK: {a.dst}  ({len(doc.encode('utf-8')):,} bytes) / 見出し {len(b.toc)}")


if __name__ == "__main__":
    sys.exit(main())
