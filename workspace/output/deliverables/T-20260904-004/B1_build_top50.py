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
V14 = os.path.join(DELIV, "T-20260817-005", "v14", "03_メーカー名寄せ.csv")
JSONL = os.path.join(DELIV, "T-20260831-001", "pipeline", "data", "exa_lookups.jsonl")
OUT = os.path.join(HERE, "B1_contacts_top50.csv")

CONTACT = ("電話", "問い合わせフォームURL", "メール")

COLS = ["順位","スコア","メーカー名",
        # --- 法務ハルオの A〜E 判定（B1L_optout_rules.json v1.0）---
        "optout_class","contact_priority","action","allowed_channels",
        "optout_hit_terms","optout_rule_ids","form_optout_notice","optout_source_url",
        "optout_checked_at","recheck_condition","optout_needs_review",
        # --- 連絡先 ---
        "正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール","確度",
        "取引可否シグナル","備考","出典URL",
        # --- Amazon 実績（利益が取れそうか）---
        "該当商品数","主なカテゴリ","想定仕入れ金額の中央値","Amazon価格の中央値","代表商品名"]

#: CSV の先頭に置く注記。**打診文を書くヒデアキへの申し送りを、CSV自体に載せる。**
#: 法務判定：本文・署名にURLを貼った瞬間に特定電子メール法2条2号の
#: 「広告宣伝ウェブサイトへの誘導」に当たり、相手の「営業お断り」表示が法的効力を持つ。
HEADER_NOTE = (
    "# 【打診文の絶対条件・法務判定 v1.0】メール本文・署名にURLを一切貼らないこと"
    "（AmazonストアURL・自社サイト satoy-select.com・SNS すべて）。"
    "貼った瞬間に特定電子メール法2条2号の『広告宣伝ウェブサイトへの誘導』に該当し、"
    "相手の『営業お断り』表示が法的効力を持つ。白が黒に転ぶ唯一の分岐点。"
    " ／ 1社1通・追送しない・断られたら即終了・一斉送信ツール禁止・実績ゼロを正直に書く。"
    " ／ optout_class が D・E の社には打診しない。C は A/A_PLUS/B を全件消化した後・フォームのみ・1回限り。")


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


def build_all_rows(lookups, v14, contacts_cls):
    """**両バッチ合計の全社**を、法務の打診優先度順に並べる。B-2（サトル）の入力。"""
    rows = []
    for name, e in lookups.items():
        v = v14.get(name, {})
        row = {c: "" for c in COLS}
        row["メーカー名"] = name
        for k in ("正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール",
                  "確度","備考","出典URL","optout_class","contact_priority","action",
                  "allowed_channels","optout_hit_terms","optout_rule_ids","form_optout_notice",
                  "optout_source_url","optout_checked_at","recheck_condition","optout_needs_review"):
            row[k] = e.get(k, "")
        for k, src in (("該当商品数","該当商品数"), ("主なカテゴリ","主なカテゴリ"),
                       ("想定仕入れ金額の中央値","想定仕入れ金額の中央値"),
                       ("Amazon価格の中央値","Amazon価格の中央値"), ("代表商品名","代表商品名")):
            row[k] = v.get(src, "")
        row["取引可否シグナル"] = signal(e, e.get("備考", ""))
        rows.append(row)
    rows.sort(key=lambda r: (int(r["contact_priority"] or 99), -_int(r["該当商品数"]), r["メーカー名"]))
    for i, r in enumerate(rows, 1):
        r["順位"] = i
    return rows


def _int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


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
                  "問い合わせフォームURL","メール","確度","備考","出典URL",
                  "optout_class","contact_priority","action","allowed_channels",
                  "optout_hit_terms","optout_rule_ids","form_optout_notice",
                  "optout_source_url","optout_checked_at","recheck_condition",
                  "optout_needs_review"):
            row[k] = e.get(k, "")
        row["取引可否シグナル"] = signal(e if e else None, note)
        rows.append(row)

    # 打診優先度順（法務の contact_priority 昇順）にも並べ替えた版を作る
    with io.open(OUT, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)

    prio = sorted(rows, key=lambda r: (int(r["contact_priority"] or 99), int(r["順位"])))
    with io.open(os.path.join(HERE, "B1_打診候補_全社_優先度順.csv"), "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(prio)

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
    print("--- 法務 A〜E 判定 ---")
    for c in ("A_PLUS", "A", "B", "C", "D", "E"):
        n = sum(1 for r in rows if r["optout_class"] == c)
        if n:
            print("  %-7s %2d" % (c, n))
    ng = [r for r in rows if r["optout_class"] in ("D", "E")]
    print("  → 打診対象から除外: %d社" % len(ng))
    print()
    print("--- 有望・連絡可の社 ---")
    for r in rows:
        if r["取引可否シグナル"].startswith(("有望", "連絡可")):
            print("  %3s %-24s %-14s %s / %s" % (r["順位"], r["メーカー名"][:24],
                  r["主なカテゴリ"][:14], r["電話"] or "-", r["メール"] or "-"))
    # --- 全社版（両バッチ 115社）---
    with io.open(V14, encoding="utf-8-sig") as fp:
        v14 = {r["メーカー/ブランド"]: r for r in csv.DictReader(fp)}
    all_rows = build_all_rows(lookups, v14, None)
    ALL = os.path.join(HERE, "B1_打診候補_全社_優先度順.csv")
    with io.open(ALL, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(all_rows)
    print("\n=== 全社版（両バッチ合計 %d社）===" % len(all_rows))
    for c in ("A_PLUS", "A", "B", "C", "D", "E"):
        n = sum(1 for r in all_rows if r["optout_class"] == c)
        if n:
            print("  %-7s %3d" % (c, n))
    reach = sum(1 for r in all_rows
                if r["optout_class"] not in ("D", "E")
                and any(r[k].strip() for k in CONTACT))
    print("  → **打診可能（D/E以外 かつ 連絡手段あり）: %d社**" % reach)
    print("\nwrote", OUT)
    print("wrote", ALL)


if __name__ == "__main__":
    main()
