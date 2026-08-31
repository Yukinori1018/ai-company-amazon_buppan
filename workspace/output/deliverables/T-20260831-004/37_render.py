"""Markdown → HTML の簡易レンダラ（T-20260831-004 / タカシ）.

    python3 37_render.py 36_規模判定レポート.md

社内資料を「テキスト + HTML」で併出力する社長の既定に合わせるためのもの。
外部ライブラリを入れたくない（このリポには markdown が無い）ので、
自分たちが実際に書く記法だけを対応する。汎用の Markdown 実装ではない。

対応する記法: 見出し / 表 / 箇条書き / 番号付き / 引用 / 水平線 /
コードブロック / 段落 / **強調** / `コード`
CSS は 14_*.html と揃えてある（同じチケットの資料が別デザインだと読みにくい）。
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

CSS = """
:root{--fg:#1a1a1a;--mut:#666;--line:#e0e0e0;--accent:#0b5fa5;--bg-alt:#f7f9fb}
*{box-sizing:border-box}
body{font-family:-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,sans-serif;
 line-height:1.75;color:var(--fg);max-width:1080px;margin:0 auto;padding:32px 24px 96px;font-size:15px}
h1{font-size:1.85em;border-bottom:3px solid var(--accent);padding-bottom:.4em;margin-top:0}
h2{font-size:1.35em;margin-top:2.2em;border-left:5px solid var(--accent);padding-left:.55em}
h3{font-size:1.1em;margin-top:1.8em;color:#333}
table{border-collapse:collapse;width:100%;margin:1.1em 0;font-size:.9em}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--bg-alt);font-weight:600;white-space:nowrap}
tbody tr:nth-child(even){background:#fbfcfd}
code{background:#f0f2f5;padding:1px 5px;border-radius:3px;font-size:.9em;
 font-family:"SF Mono",Menlo,Consolas,monospace}
pre{background:#1e2430;color:#e6edf3;padding:14px 16px;border-radius:6px;overflow-x:auto;font-size:.85em}
pre code{background:none;color:inherit;padding:0}
blockquote{border-left:4px solid #f0a500;background:#fffbf0;margin:1.1em 0;padding:.7em 1em;color:#5a4a20}
hr{border:0;border-top:1px solid var(--line);margin:2.2em 0}
strong{color:#0a4d8c}
ul,ol{padding-left:1.5em}
@media print{body{max-width:none;font-size:11pt}h2{page-break-after:avoid}table{page-break-inside:avoid}}
"""


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def render(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    list_tag: str | None = None

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    while i < n:
        ln = lines[i]

        if ln.startswith("```"):
            close_list()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            i += 1
            continue

        # 表: ヘッダ行 + 区切り行 + 本文
        if ln.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            close_list()
            cells = [c.strip() for c in ln.strip("|").split("|")]
            out.append("<table><thead><tr>"
                       + "".join(f"<th>{inline(c)}</th>" for c in cells)
                       + "</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].startswith("|"):
                cs = [c.strip() for c in lines[i].strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cs) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        if m := re.match(r"^(#{1,4})\s+(.*)$", ln):
            close_list()
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
        elif re.match(r"^---+$", ln):
            close_list()
            out.append("<hr>")
        elif ln.startswith("> "):
            close_list()
            buf = []
            while i < n and lines[i].startswith("> "):
                buf.append(inline(lines[i][2:]))
                i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>")
            continue
        elif m := re.match(r"^\s*[-*]\s+(.*)$", ln):
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>")
        elif m := re.match(r"^\s*\d+\.\s+(.*)$", ln):
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{inline(m.group(1))}</li>")
        elif ln.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{inline(ln)}</p>")
        i += 1

    close_list()
    return "\n".join(out)


def main() -> int:
    src = Path(sys.argv[1])
    md = src.read_text(encoding="utf-8")
    title = next(
        (l[2:].strip() for l in md.split("\n") if l.startswith("# ")), src.stem
    )
    body = render(md)
    out = src.with_suffix(".html")
    out.write_text(
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>\n"
        f"{body}\n</body></html>",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
