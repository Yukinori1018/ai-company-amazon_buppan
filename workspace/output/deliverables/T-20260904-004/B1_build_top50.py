#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-1 本走行：上位50社の結果を「連絡先 × 利益が取れそう」の1枚にまとめる。

カズヨ発注（2026-09-04）の指示③「社長が次に見るのは連絡先が分かった × 利益が取れそうの交差点」への回答。
B1_work_queue.csv（利益ヒューリスティック順）と exa_lookups.jsonl（実取得）を結合する。
"""
from __future__ import annotations
import csv, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.dirname(HERE)
QUEUE = os.path.join(HERE, "B1_work_queue.csv")
JSONL = os.path.join(DELIV, "T-20260831-001", "pipeline", "data", "exa_lookups.jsonl")
OUT = os.path.join(HERE, "B1_contacts_top50.csv")

CONTACT = ("電話", "問い合わせフォームURL", "メール")

COLS = ["順位","スコア","メーカー名","正式商号","法人番号","所在地","公式HP","電話",
        "問い合わせフォームURL","メール","確度","取引可否シグナル","備考","出典URL",
        "該当商品数","主なカテゴリ","想定仕入れ金額の中央値","Amazon価格の中央値","代表商品名"]


def load_lookups():
    idx = {}
    with io.open(JSONL, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            idx[e["メーカー名"]] = e   # 後勝ち
    return idx


def signal(entry, note):
    """備考から取引可否のシグナルを1語に落とす。**判定材料であって結論ではない。**"""
    if not entry:
        return "未処理"
    if "名寄せの取りこぼし" in note:
        return "重複(同一法人の別行)"
    if entry.get("form_optout_notice") == "true":
        return "要注意(拒否表示あり)"
    if not any((entry.get(k) or "").strip() for k in CONTACT):
        return "連絡不可"
    if "本丸" in note or "OEM" in note or "少量" in note or "B2B" in note or "卸取引" in note:
        return "有望(小ロット/OEM/B2Bの明示あり)"
    for w in ("大手", "直取引の相手ではない", "取次", "仕入れ先ではない",
              "上場", "ライセンス管理", "配給", "レコード会社", "直販は行わない",
              "直販窓口ではない", "消費者向け窓口"):
        if w in note:
            return "対象外(大手/流通構造)"
    return "連絡可"


def main():
    lookups = load_lookups()
    with io.open(QUEUE, encoding="utf-8-sig") as fp:
        queue = list(csv.DictReader(fp))[:50]

    rows = []
    for q in queue:
        e = lookups.get(q["メーカー名"]) or {}
        note = e.get("備考", "")
        row = {c: "" for c in COLS}
        row.update({k: q.get(k, "") for k in
                    ("順位","スコア","メーカー名","該当商品数","主なカテゴリ",
                     "想定仕入れ金額の中央値","Amazon価格の中央値","代表商品名")})
        for k in ("正式商号","法人番号","所在地","公式HP","電話",
                  "問い合わせフォームURL","メール","確度","備考","出典URL"):
            row[k] = e.get(k, "")
        row["取引可否シグナル"] = signal(e if e else None, note)
        rows.append(row)

    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)

    # --- 数字 ---
    n = len(rows)
    def cnt(pred): return sum(1 for r in rows if pred(r))
    print("処理: %d社" % n)
    for k in ("正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール"):
        c = cnt(lambda r, k=k: r[k].strip())
        print("  %-18s %2d/%d (%3.0f%%)" % (k, c, n, 100.0*c/n))
    reach = cnt(lambda r: any(r[k].strip() for k in CONTACT))
    print("  %-18s %2d/%d (%3.0f%%)" % ("連絡手段1つ以上", reach, n, 100.0*reach/n))
    print()
    import collections
    for k, v in collections.Counter(r["取引可否シグナル"] for r in rows).most_common():
        print("  %-30s %d" % (k, v))
    print()
    print("--- 有望・連絡可の社 ---")
    for r in rows:
        if r["取引可否シグナル"].startswith(("有望", "連絡可")):
            print("  %3s %-24s %-14s %s / %s" % (r["順位"], r["メーカー名"][:24],
                  r["主なカテゴリ"][:14], r["電話"] or "-", r["メール"] or "-"))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
