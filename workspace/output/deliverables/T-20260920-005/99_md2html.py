#!/usr/bin/env python3
"""md → html の小さな変換器（T-20260914-006/02_md2html.py の複製）。見出し・表・箇条書き・引用・太字・コードだけ。標準ライブラリのみ。"""
import html, re, sys, pathlib

CSS = ("body{font-family:-apple-system,'Hiragino Sans','Noto Sans JP',sans-serif;max-width:1150px;margin:2em auto;padding:0 1em;line-height:1.65;color:#222;font-size:14.5px}"
       "table{border-collapse:collapse;margin:.8em 0;font-size:.92em}th,td{border:1px solid #bbb;padding:.35em .6em;vertical-align:top}th{background:#eef2f8}"
       "tr:nth-child(even) td{background:#fafafa}h1{font-size:1.5em;border-bottom:2px solid #444}h2{font-size:1.25em;border-left:5px solid #25b;padding-left:8px;margin-top:1.8em}"
       "h3{font-size:1.05em;margin-top:1.4em}blockquote{border-left:4px solid #ccc;margin:.8em 0;padding:.2em 1em;color:#444}code{background:#f3f3f3;padding:1px 4px;border-radius:3px}"
       "hr{border:0;border-top:1px solid #ccc;margin:1.6em 0}")


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t


def convert(md):
    out, lines, i = [], md.splitlines(), 0
    title = next((l[2:] for l in lines if l.startswith("# ")), "")
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head = [c.strip() for c in l.strip().strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        m = re.match(r"^(#{1,4}) (.*)", l)
        if m:
            n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if l.strip() == "---":
            out.append("<hr>"); i += 1; continue
        if l.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(inline(lines[i].lstrip("> "))); i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>"); continue
        if re.match(r"^\s*([-*]|\d+\.) ", l):
            ordered = bool(re.match(r"^\s*\d+\. ", l))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                item = re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i])
                indent = len(lines[i]) - len(lines[i].lstrip())
                out.append(f"<li style='margin-left:{indent * 0.6}em'>{inline(item)}</li>"); i += 1
            out.append(f"</{tag}>"); continue
        if l.startswith("```"):
            i += 1; buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i])); i += 1
            i += 1; out.append("<pre>" + "\n".join(buf) + "</pre>"); continue
        if l.strip():
            out.append(f"<p>{inline(l)}</p>")
        i += 1
    return (f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>\n" + "\n".join(out) + "\n</body></html>\n")


if __name__ == "__main__":
    here = pathlib.Path(__file__).resolve().parent
    src = here / (sys.argv[1] if len(sys.argv) > 1 else "01_T3_ブランド未登録メーカー.md")
    dst = src.with_suffix(".html")
    dst.write_text(convert(src.read_text()))
    print(dst)
