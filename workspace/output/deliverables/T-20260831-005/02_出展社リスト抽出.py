#!/usr/bin/env python3
"""
展示会の出展社リスト（PDF）を CSV 化する — T-20260831-005 実測①の再現スクリプト

実測（2026-08-31）:
  入力 https://www.giftshow.co.jp/tigs/102tigs/pdf/list.pdf  (HTTP 200 / 795,244 bytes)
  出力 社名ユニーク 2,353件 / ブース番号ユニーク 2,103件
  所要 約2分（DL + pdftotext + パース）

なぜ CSV 本体をリポジトリに置いていないか:
  当該PDFに「無断掲載及び他のメディアへの加工を禁止します（(C)2026 BUSINESS GUIDE-SHA,INC.）」の
  表示がある。本リポジトリは PUBLIC のため、法務（ハルオ）の判定が出るまで成果CSVは公開しない。
  スクリプトを置くことで、判定後にいつでも2分で再生成できる状態にしてある。
  → 論点は 01_仕入れ先の発見方法_全方位調査.md §5 の #3。

依存: poppler の pdftotext（macOS: brew install poppler）

使い方:
  python3 02_出展社リスト抽出.py <PDF_URL> <出力CSV>
  例) python3 02_出展社リスト抽出.py https://www.giftshow.co.jp/tigs/102tigs/pdf/list.pdf out.csv

注意（法務ハルオ判定 T-20260831-001 B を踏襲）:
  - robots.txt を尊重すること。giftshow.co.jp は robots.txt 自体が存在しない（404）
  - 同一ホストへの連続アクセスは 3 秒以上あける
  - UA は詐称せず、連絡先を含めて名乗る
"""
import csv
import re
import subprocess
import sys
import tempfile
import urllib.request

USER_AGENT = "SatoySelectResearch/1.0 (supplier discovery; contact via repo owner)"

# 東京ビッグサイトのホール表記 + 特設ゾーンの小間番号
BOOTH = re.compile(
    r'((?:東|西|南)\d+-[A-Za-zＡ-Ｚ0-9０-９\-－]+|GLS-\d+|SL\d+|MC\d+)\s+'
)


def download(url: str, path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if not data.startswith(b"%PDF"):
        raise SystemExit(f"PDFではない応答が返りました（{len(data)} bytes）。URLを確認してください。")
    with open(path, "wb") as f:
        f.write(data)


def to_text(pdf_path: str) -> str:
    txt_path = pdf_path + ".txt"
    # -layout: 多段組みのレイアウトを保つ。これが無いと社名と小間番号の対応が崩れる
    subprocess.run(["pdftotext", "-layout", pdf_path, txt_path], check=True)
    return open(txt_path, encoding="utf-8").read()


def parse(text: str):
    """1行 = [pre, booth, name, booth, name, ...] に分割して (booth, name) を拾う。

    既知の欠陥: PDF が多段組みのため、列を跨いだ行で社名が途中で切れることがある
    （例: 社名列が「（株）」だけになる）。実測で数十件。クリーニング1パスが必要。
    """
    pairs = []
    for line in text.split("\n"):
        parts = BOOTH.split(line)
        for i in range(1, len(parts) - 1, 2):
            booth = parts[i]
            name = re.sub(r"\s{2,}.*$", "", parts[i + 1].strip()).strip()
            if name and len(name) < 60:
                pairs.append((booth, name))
    return pairs


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    url, out_csv = sys.argv[1], sys.argv[2]
    with tempfile.TemporaryDirectory() as td:
        pdf = f"{td}/list.pdf"
        download(url, pdf)
        pairs = parse(to_text(pdf))

    uniq = {}
    for booth, name in pairs:
        uniq.setdefault(name, booth)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["booth", "exhibitor"])
        for name, booth in uniq.items():
            w.writerow([booth, name])

    print(f"抽出ペア {len(pairs)} / 社名ユニーク {len(uniq)} -> {out_csv}")


if __name__ == "__main__":
    main()
