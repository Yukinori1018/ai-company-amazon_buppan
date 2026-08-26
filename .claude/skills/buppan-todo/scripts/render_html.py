#!/usr/bin/env python3
"""01_master-todo.md -> 01_master-todo.html.

社長の既定「分量のある資料はテキスト + HTML の併出力」を満たすための描画器です。
Markdown 全般のコンバータではなく、マスターToDoリストが実際に使っている記法だけを
扱います（見出し / 箇条書き / チェックリスト / 表 / 引用 / 水平線 / 太字 / コード）。
足りない記法が出てきたら、汎用ライブラリを入れるより、ここに1ケース足すほうが安全です。

使い方:
    python3 render_html.py <input.md> <output.html> [--title T] [--footer F]

設計メモ:
- スタイルは全部インライン。社長が Finder からダブルクリックで開く単体ファイルなので、
  外部 CSS もフォントも読ませない（オフラインで確実に同じ見た目になる）。
- 進捗マークで行の色が変わる。✓緑 / ●オレンジ / □グレー。⚠️ を含む行は左の帯だけ赤系。
"""

from __future__ import annotations

import html
import re
import sys

# ---------------------------------------------------------------- スタイル定義
S = {
    "body": (
        "margin:0;padding:0;background:#eef1f5;color:#1f2933;\n"
        "font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Noto Sans JP',"
        "'Yu Gothic',sans-serif;\nfont-size:15px;-webkit-text-size-adjust:100%"
    ),
    "outer": "max-width:1020px;margin:0 auto;padding:26px 18px 70px",
    "card": "background:#fff;border:1px solid #dde3ea;border-radius:6px;padding:26px 26px 34px",
    "h1": "margin:0 0 6px;font-size:1.5em;color:#16324f;line-height:1.45",
    "h2": "margin:40px 0 10px;padding:10px 14px;background:#16324f;color:#fff;font-size:1.12em;border-radius:4px",
    "h3": "margin:26px 0 6px;font-size:1.02em;color:#16324f;border-bottom:1px solid #dfe5ec;padding-bottom:5px",
    "p": "margin:10px 0;line-height:1.85",
    "hr": "border:0;border-top:1px solid #e3e8ee;margin:26px 0",
    "bullet": "margin:5px 0 5px 1.1em;line-height:1.75",
    "tocbox": "margin:6px 0 20px;padding:12px 14px;background:#f7f9fc;border:1px solid #e0e6ec;border-radius:4px",
    "toclabel": "font-size:.8em;color:#6b7885;margin-bottom:6px;font-weight:700;letter-spacing:.04em",
    "toclink": (
        "display:inline-block;margin:3px 6px 3px 0;padding:4px 10px;border:1px solid #ccd6e2;"
        "border-radius:14px;background:#fff;color:#2b4a72;text-decoration:none;font-size:.84em"
    ),
    "table": "width:100%;border-collapse:collapse;margin:14px 0;font-size:.92em",
    "th": (
        "text-align:left;padding:8px 10px;background:#eef2f7;border:1px solid #d5dde6;"
        "font-weight:700;color:#22303f;white-space:nowrap"
    ),
    "td": "padding:7px 10px;border:1px solid #e0e6ec;vertical-align:top;line-height:1.65",
    "strong": "font-weight:700;color:#0f172a",
    "code": (
        "background:#eef1f5;border:1px solid #dde3ea;border-radius:3px;padding:1px 5px;"
        "font-size:.88em;font-family:ui-monospace,SFMono-Regular,Menlo,monospace"
    ),
    "role": (
        "display:inline-block;margin-left:4px;padding:1px 7px;border-radius:10px;"
        "background:#eaf0f8;color:#2b4a72;font-size:.78em;font-weight:600"
    ),
    "approval": (
        "display:inline-block;padding:0 5px;border-radius:3px;background:#fdecea;"
        "color:#a3251b;font-size:.82em;font-weight:700"
    ),
    "ticket": (
        "display:inline-block;margin-left:6px;padding:1px 7px;border:1px solid #c7d2e0;"
        "border-radius:10px;background:#f4f7fb;color:#42536b;font-size:.78em;white-space:nowrap"
    ),
    "quote_now": (
        "margin:10px 0 8px;padding:8px 12px;background:#f7f9fc;border-left:3px solid #6b86a8;"
        "color:#33455c;font-size:.93em;line-height:1.7"
    ),
    "quote_note": (
        "margin:10px 0;padding:10px 12px;background:#fff8ec;border-left:3px solid #d9a441;"
        "color:#4a3a1c;font-size:.93em;line-height:1.7"
    ),
    "quote_label": "color:#22303f",
    "foot": "text-align:center;color:#8b95a3;font-size:.8em;margin:18px 0 0",
}

# チェック状態ごとの見た目。alert は行に ⚠️ がある場合の左帯の上書き。
MARK = {
    "x": {"glyph": "&#10003;", "ink": "#0f7a4d", "bg": "#e7f6ee", "bar": "#bfe3d0"},
    "~": {"glyph": "&#9679;", "ink": "#a2650a", "bg": "#fdf3e2", "bar": "#f0dcb4"},
    " ": {"glyph": "&#9633;", "ink": "#8b95a3", "bg": "#f5f6f8", "bar": "#e2e6ec"},
}
ALERT_BAR = "#e8b4ae"

ROLES = ("社長+AI", "社長", "AI")
RE_TICKET = re.compile(r"〔([^〕]+)〕")
RE_CODE = re.compile(r"`([^`]+)`")
RE_BOLD = re.compile(r"\*\*([^*]+)\*\*")
RE_TASK = re.compile(r"^- \[([x~ ])\] (.*)$")
RE_H3ID = re.compile(r"^([0-9A-Za-z-]*)")


# ---------------------------------------------------------------- インライン変換
def inline(text: str) -> str:
    """太字・コード・役割バッジ・チケットチップ・§4.1 バッジを HTML にする。"""
    out = html.escape(text)

    def code_sub(m: re.Match[str]) -> str:
        inner = m.group(1)
        # `[社長]` `[AI]` `[社長+AI]` は誰の手が要るかの印。バッジで出す。
        role = inner.strip()
        if role.startswith("[") and role.endswith("]") and role[1:-1] in ROLES:
            inner = f'<span style="{S["role"]}">{role[1:-1]}</span>'
        return f'<code style="{S["code"]}">{inner}</code>'

    out = RE_CODE.sub(code_sub, out)
    out = RE_BOLD.sub(lambda m: f'<strong style="{S["strong"]}">{m.group(1)}</strong>', out)
    # §4.1 は「社長承認が要る」の合図。見落とされると事故るので赤バッジで浮かせる。
    out = out.replace("§4.1", f'<span style="{S["approval"]}">&sect;4.1</span>')
    out = RE_TICKET.sub(lambda m: f'<span style="{S["ticket"]}">{m.group(1)}</span>', out)
    return out


def cell(text: str) -> str:
    return inline(text.strip())


# ---------------------------------------------------------------- ブロック変換
def h3_id(title: str) -> str:
    return "h" + RE_H3ID.match(title).group(1).lower()


def render(md: str, title_override: str = "", footer: str = "") -> str:
    lines = md.split("\n")
    body: list[str] = []
    title = "ドキュメント"
    toc: list[tuple[str, str]] = []
    sec = 0
    last_head = ""  # 直前の見出しレベル（引用の色分けに使う）
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.rstrip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            body.append(f'<hr style="{S["hr"]}">')
            i += 1
            continue

        if stripped.startswith("# "):
            title = stripped[2:].strip()
            body.append(f'<h1 style="{S["h1"]}">{inline(title)}</h1>')
            i += 1
            continue

        if stripped.startswith("## "):
            text = stripped[3:].strip()
            anchor = f"sec{sec}"
            sec += 1
            toc.append((anchor, text))
            body.append(f'<h2 id="{anchor}" style="{S["h2"]}">{inline(text)}</h2>')
            last_head = "h2"
            i += 1
            continue

        if stripped.startswith("### "):
            text = stripped[4:].strip()
            body.append(f'<h3 id="{h3_id(text)}" style="{S["h3"]}">{inline(text)}</h3>')
            last_head = "h3"
            i += 1
            continue

        if stripped.startswith("> "):
            text = stripped[2:].strip()
            # 中項目直下の「現在地：…」は進捗の要約。ラベルを立てて読み飛ばせるようにする。
            if text.startswith("現在地：") and last_head == "h3":
                rest = inline(text[len("現在地："):])
                body.append(
                    f'<p style="{S["quote_now"]}">'
                    f'<strong style="{S["quote_label"]}">現在地</strong>　{rest}</p>'
                )
            else:
                body.append(f'<p style="{S["quote_note"]}">{inline(text)}</p>')
            i += 1
            continue

        if stripped.startswith("|"):
            block: list[str] = []
            while i < n and lines[i].lstrip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            body.append(render_table(block))
            continue

        m = RE_TASK.match(stripped)
        if m:
            body.append(render_task(m.group(1), m.group(2)))
            i += 1
            continue

        if stripped.startswith("- "):
            body.append(f'<li style="{S["bullet"]}">{inline(stripped[2:])}</li>')
            i += 1
            continue

        body.append(f'<p style="{S["p"]}">{inline(stripped)}</p>')
        i += 1

    toc_html = "".join(
        f'<a href="#{a}" style="{S["toclink"]}">{html.escape(t)}</a>' for a, t in toc
    )
    # 目次は h1 の直後・最初の hr の後ろに差し込む（元レイアウトと同じ位置）。
    for idx, chunk in enumerate(body):
        if chunk.startswith("<hr"):
            body.insert(
                idx + 1,
                f'<div style="{S["tocbox"]}">\n'
                f'<div style="{S["toclabel"]}">目次</div>{toc_html}\n</div>',
            )
            body.insert(idx + 2, "")  # 目次と本文のあいだの1行あき
            break

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="ja"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            f"<title>{html.escape(title_override or title)}</title></head>",
            f'<body style="{S["body"]}">',
            f'<div style="{S["outer"]}">',
            f'<div style="{S["card"]}">',
            *body,
            "</div>",
            f'<p style="{S["foot"]}">\n{html.escape(footer)}</p>',
            "</div></body></html>",
            "",
        ]
    )


def render_task(mark: str, text: str) -> str:
    style = MARK[mark]
    bar = ALERT_BAR if "⚠️" in text else style["bar"]
    return (
        f'<li style="list-style:none;display:flex;gap:10px;align-items:flex-start;margin:0;'
        f'padding:8px 10px;border-left:3px solid {bar};background:{style["bg"]};'
        f'border-bottom:1px solid #eef1f4">'
        f'<span style="flex:0 0 auto;width:1.5em;text-align:center;color:{style["ink"]};'
        f'font-weight:700">{style["glyph"]}</span>'
        f'<span style="flex:1 1 auto;line-height:1.75">{inline(text)}</span></li>'
    )


def render_table(block: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [c for c in row.strip().strip("|").split("|")]

    header = cells(block[0])
    rows = [cells(r) for r in block[2:]] if len(block) > 2 else []
    head = "".join(f'<th style="{S["th"]}">{cell(c)}</th>' for c in header)
    bodyrows = "".join(
        "<tr>" + "".join(f'<td style="{S["td"]}">{cell(c)}</td>' for c in r) + "</tr>\n"
        for r in rows
    )
    return (
        f'<table style="{S["table"]}"><thead><tr>{head}</tr></thead><tbody>\n'
        f"{bodyrows}</tbody></table>"
    )


def main() -> int:
    args = sys.argv[1:]
    opts = {"--title": "", "--footer": ""}
    positional: list[str] = []
    while args:
        a = args.pop(0)
        if a in opts:
            opts[a] = args.pop(0) if args else ""
        else:
            positional.append(a)
    if len(positional) != 2:
        print(__doc__)
        return 2
    src, dst = positional
    with open(src, encoding="utf-8") as f:
        md = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(render(md, opts["--title"], opts["--footer"]))
    print(f"rendered: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
