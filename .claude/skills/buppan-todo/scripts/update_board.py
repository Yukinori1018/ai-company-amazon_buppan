#!/usr/bin/env python3
"""03_process-board.html の「数字だけ」を集計値で差し替える。

    python3 update_board.py <board.html> <counts.json> [--check]

なぜ作り直さずに書き換えるのか
------------------------------
ボードの中身は、機械で出せる数字（済/着手中/未着手）と、人が書いた文章
（現在地の解説・Next の一手・社長タスクの表・確度の注記）が混ざっています。
毎回ゼロから生成すると、後者が書き直されて社長の指摘の積み重ねが消えます。
実際このボードには社長の指摘が3件入っています。

  - 図を画面幅いっぱいに、拡大/縮小/幅に合わせる/全画面のボタンつきで
  - 大項目 → 中項目は「順序」ではないので矢印にしない（矢じりなしの細い線）
  - 数字が何を指すのか凡例を出す

これらは HTML と Mermaid の書き方そのものに埋まっているので、触りません。
差し替えるのは数字のパターンに一致した箇所だけです。

--check を付けると書き換えず、ズレている箇所を一覧して終了コード1を返します。
"""

from __future__ import annotations

import json
import re
import sys

# 「3 / 2 / 1」のような3つ組。区切りの空白は原文の書き方に合わせて温存する。
TRIPLE = r"(\d+)(\s*/\s*)(\d+)(\s*/\s*)(\d+)"


def pct(done: int, doing: int, todo: int) -> tuple[float, float, float]:
    """帯グラフの幅。合計が必ず 100 になるよう最後の1本で辻褄を合わせる。"""
    total = done + doing + todo
    if total == 0:
        return (0.0, 0.0, 0.0)
    d = round(done / total * 100, 1)
    g = round(doing / total * 100, 1)
    return (d, g, round(100 - d - g, 1))


def num(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def bar(done: int, doing: int, todo: int) -> str:
    d, g, t = pct(done, doing, todo)
    parts = []
    if done:
        parts.append(f'<i class="d" style="width:{num(d)}%"></i>')
    if doing:
        parts.append(f'<i class="g" style="width:{num(g)}%"></i>')
    if todo:
        parts.append(f'<i class="t" style="width:{num(t)}%"></i>')
    return "".join(parts)


def apply(html: str, counts: dict) -> tuple[str, list[str]]:
    mids = {m["id"]: m for m in counts["mid"]}
    majors = {m["no"]: m for m in counts["major"]}
    tot = counts["total"]
    notes: list[str] = []

    def note(what: str, before: str, after: str) -> None:
        if before != after:
            notes.append(f"{what}: {before} -> {after}")

    # A章の3つの大きい数字
    for cls, key in (("done", "done"), ("doing", "doing"), ("todo", "todo")):
        pat = re.compile(rf'(<span class="n {cls}">)(\d+)(</span>)')
        m = pat.search(html)
        if m:
            note(f"totals.{cls}", m.group(2), str(tot[key]))
            html = pat.sub(rf"\g<1>{tot[key]}\g<3>", html, count=1)

    # Mermaid 図1: 大項目ノード S1〜S8 の "<br/><br/>10 / 10 / 11"
    def stage_node(m: re.Match[str]) -> str:
        mj = majors.get(m.group(1))
        if not mj:
            return m.group(0)
        after = f'{mj["done"]} / {mj["doing"]} / {mj["todo"]}'
        note(f"mermaid.S{m.group(1)}", m.group(2), after)
        return m.group(0).replace(m.group(2), after)

    html = re.sub(r'S([1-8])\["[^"]*?<br/><br/>(' + TRIPLE + r')"\]', stage_node, html)

    # Mermaid 図2/3: 中項目ノード '1-1 事業体・税務の届出<br/>(3 / 2 / 1)'
    def mid_node(m: re.Match[str]) -> str:
        mid = mids.get(m.group(1))
        if not mid:
            return m.group(0)
        after = f'({mid["done"]} / {mid["doing"]} / {mid["todo"]})'
        note(f"mermaid.{m.group(1)}", m.group(2), after)
        return m.group(0).replace(m.group(2), after)

    html = re.sub(r'"([1-8]-[0-9]+) [^"]*?(\(' + TRIPLE + r'\))"\]', mid_node, html)

    # C章のカード見出し: '中6 ／ 小31 ・ 済10 着手10 未11'
    def card_head(m: re.Match[str]) -> str:
        no = str(int(m.group(1)))
        mj = majors.get(no)
        if not mj:
            return m.group(0)
        items = mj["done"] + mj["doing"] + mj["todo"]
        after = (
            f'中{mj["mids"]} ／ 小{items} ・ 済{mj["done"]} '
            f'着手{mj["doing"]} 未{mj["todo"]}'
        )
        note(f"card{no}.head", m.group(2), after)
        return m.group(0).replace(m.group(2), after)

    html = re.sub(
        r'<span class="stage-no">(\d+)</span>.*?'
        r'<span class="s">(中\d+ ／ 小\d+ ・ 済\d+ 着手\d+ 未\d+)</span>',
        card_head,
        html,
        flags=re.S,
    )

    # C章のカード帯グラフ。<div class="bar">…</div> をカード順に置き換える。
    order = [m["no"] for m in counts["major"]]
    bars = iter(order)

    def card_bar(m: re.Match[str]) -> str:
        try:
            mj = majors[next(bars)]
        except StopIteration:
            return m.group(0)
        after = bar(mj["done"], mj["doing"], mj["todo"])
        note(f'card{mj["no"]}.bar', m.group(1), after)
        return f'<div class="bar">{after}</div>'

    html = re.sub(r'<div class="bar">(.*?)</div>', card_bar, html, flags=re.S)

    # C章の中項目行: <span class="ct"><b>3</b>/<i>2</i>/1</span>
    def card_mid(m: re.Match[str]) -> str:
        mid = mids.get(m.group(1))
        if not mid:
            return m.group(0)
        after = f'<b>{mid["done"]}</b>/<i>{mid["doing"]}</i>/{mid["todo"]}'
        note(f"card.{m.group(1)}", m.group(2), after)
        return m.group(0).replace(m.group(2), after)

    html = re.sub(
        r'<span class="id">([1-8]-[0-9]+)</span>.*?'
        r'<span class="ct">(<b>\d+</b>/<i>\d+</i>/\d+)</span>',
        card_mid,
        html,
        flags=re.S,
    )

    # F章の地の文: 「小項目208件の内訳（済49 / 着手43 / 未116）」
    def prose(m: re.Match[str]) -> str:
        after = (
            f'小項目{tot["items"]}件の内訳（済{tot["done"]} / '
            f'着手{tot["doing"]} / 未{tot["todo"]}）'
        )
        note("prose.totals", m.group(0), after)
        return after

    html = re.sub(r"小項目\d+件の内訳（済\d+ / 着手\d+ / 未\d+）", prose, html)

    return html, notes


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--check"]
    check = "--check" in sys.argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    board_path, counts_path = args
    with open(board_path, encoding="utf-8") as f:
        html = f.read()
    with open(counts_path, encoding="utf-8") as f:
        counts = json.load(f)

    updated, notes = apply(html, counts)

    if check:
        if notes:
            print(f"NG: {board_path} の数字が集計とズレています（{len(notes)}件）")
            for n in notes:
                print("  " + n)
            return 1
        print(f"OK: {board_path} の数字は集計と一致しています")
        return 0

    if notes:
        with open(board_path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"updated: {board_path}（{len(notes)}件）")
        for n in notes:
            print("  " + n)
    else:
        print(f"no change: {board_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
