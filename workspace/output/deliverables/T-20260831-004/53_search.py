#!/usr/bin/env python3
"""53_search.py — 52_video_scan.sh が作った OCR コーパスを正規表現で検索する。

使い方:
    python3 53_search.py <作業ディレクトリ> <正規表現> [正規表現...]
    python3 53_search.py work 'ランキング' '万位' '50,?000'

    --timeline を渡すと、検索ではなく画面遷移の一覧を出す（走査範囲の証拠になる）。

10秒間隔フレームは f_NNNNN.jpg の NNNNN から録画内秒数と実時刻を復元できる。
シーン検出フレームは時刻を持たない（順序のみ）ので、ヒットしたら本文で
10秒間隔コーパス側を引き直して時刻を確定すること。
"""
import sys, re, datetime, difflib
from pathlib import Path


def load(tsv: Path):
    rows = []
    for line in tsv.open(encoding="utf-8"):
        name, _, text = line.rstrip("\n").partition("\t")
        rows.append((name, text))
    return rows


def clock_of(name: str, interval: int, start: datetime.datetime):
    """f_00123.jpg → (経過秒, 実時刻文字列)。時刻を持たないフレームは None。"""
    m = re.match(r"f_(\d+)\.", name)
    if not m:
        return None, None
    sec = int(m.group(1)) * interval
    return sec, (start + datetime.timedelta(seconds=sec)).strftime("%H:%M:%S")


def signature(text: str) -> str:
    return " / ".join([l for l in text.split("\\n") if len(l) >= 4][:4])


def main():
    work = Path(sys.argv[1])
    interval = int((work / "interval.txt").read_text().strip())
    h, m, s = (work / "start_clock.txt").read_text().strip().split(":")
    start = datetime.datetime(2000, 1, 1, int(h), int(m), int(s))

    args = sys.argv[2:]
    if "--timeline" in args:
        merged = []
        for name, text in sorted(load(work / "frames.tsv")):
            sig = signature(text)
            if merged and difflib.SequenceMatcher(None, merged[-1][2], sig).ratio() > 0.72:
                merged[-1][1] = name
            else:
                merged.append([name, name, sig])
        for a, b, sig in merged:
            print(f"{clock_of(a, interval, start)[1]}–{clock_of(b, interval, start)[1]}  {sig[:110]}")
        return

    pats = args
    for tsv in ("frames.tsv", "scene.tsv"):
        path = work / tsv
        if not path.exists():
            continue
        print(f"########## {tsv} ##########")
        for name, text in sorted(load(path)):
            hits = [p for p in pats if re.search(p, text)]
            if not hits:
                continue
            sec, wall = clock_of(name, interval, start)
            when = f"経過{sec//60:02d}:{sec%60:02d} 実{wall}" if wall else "（時刻なし）"
            print(f"### {name} {when} hit={hits}")
            print("    " + text.replace("\\n", " | ")[:600])


if __name__ == "__main__":
    main()
