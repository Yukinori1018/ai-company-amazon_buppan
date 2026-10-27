#!/usr/bin/env python3
"""チケットを全数棚卸しして、進捗判定の根拠台帳を作り直す。

    python3 ticket_inventory.py <tickets_dir> <out.md> [--prev <前回の台帳.md>]

機械で取れる事実（ID・フォルダ・タイトル・担当・更新日・成果物の有無）はここで埋めます。
「ライフサイクル段階 0〜8」と「実質何が終わったか」は事実の要約＝判断なので、
ここでは埋めません。前回の台帳があれば、同じチケットの分類と要約をそのまま引き継ぎ、
新しく増えたぶんと状態が動いたぶんだけを TODO として出力します。

毎回 106 枚を読み直すのは時間の無駄で、しかも読み直すたびに分類が微妙に揺れます。
揺れると進捗の数字も揺れて、社長には「何もしてないのに数字が変わった」と見えます。
"""

from __future__ import annotations

import os
import re
import sys

FOLDERS = ("done", "doing", "waiting", "todo")

# 01_master-todo.md の大項目1〜8に対応。0 だけは「会社そのものの整備」で、
# ToDoリストの本文には現れない（Amazon の業務ではなく社内インフラの整備なので）。
STAGES = [
    ("0", "基盤・会社運営（AIエージェント体制/Notion/自動同期/カタログ）"),
    ("1", "開業・アカウント登録（開業届・古物商・税務・銀行/カード・セラーアカウント・健全性/停止対応）"),
    ("2", "事業戦略・仕入れ手法の選定（せどり/メーカー仕入れ/OEM/無在庫、カテゴリ選定、撤退条件）"),
    ("3", "リサーチ・ツール（Keepa/ERESA/SellerSprite/自作ツール・リサーチ手法・利益計算）"),
    ("4", "仕入れ・サプライヤー開拓（卸/メーカー交渉・NETSEA・仕入れリスト・与信/信用作り）"),
    ("5", "出品・カタログ登録（出品制限解除・SKU/ASIN・商品ページ）"),
    ("6", "FBA納品・在庫オペレーション（梱包・ラベル・納品プラン・代行/外注）"),
    ("7", "販売・価格・広告（カートボックス・価格改定・スポンサー広告・レビュー）"),
    ("8", "顧客対応・クレーム/返品・アカウント維持（返品/返金・評価削除依頼・パフォーマンス指標）"),
]
RE_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def frontmatter(text: str) -> dict[str, str]:
    m = RE_FM.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def section(text: str, name: str) -> str:
    """本文中の '## <name>' セクションの最初の中身を1行で返す。"""
    m = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return ""
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("<!--"):
            return re.sub(r"\s+", " ", line)
    return ""


def load_prev(path: str) -> dict[str, tuple[str, str]]:
    """前回の台帳から {ticket_id: (要約, 段階)} を拾う。"""
    if not path or not os.path.exists(path):
        return {}
    prev: dict[str, tuple[str, str]] = {}
    for line in open(path, encoding="utf-8"):
        if not line.startswith("| T-"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) >= 5:
            prev[cols[0]] = (cols[3], cols[4])
    return prev


def collect(tickets_dir: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for folder in FOLDERS:
        d = os.path.join(tickets_dir, folder)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md") or name.startswith("_"):
                continue
            text = open(os.path.join(d, name), encoding="utf-8").read()
            fm = frontmatter(text)
            tid = fm.get("ticket_id") or name.split("_")[0]
            rows.append(
                {
                    "id": tid,
                    "folder": folder,
                    "title": fm.get("title", ""),
                    "assignee": fm.get("assignee", ""),
                    "updated_at": fm.get("updated_at", ""),
                    # 「現在地」「完了報告」が空のチケットは、[x] の根拠が
                    # タイトル頼みになる。あとで両論併記できるよう印を残す。
                    "has_report": "有"
                    if (section(text, "完了報告") or section(text, "現在地"))
                    else "無",
                    "now": section(text, "現在地") or section(text, "完了報告"),
                }
            )
    return rows


def main() -> int:
    args = sys.argv[1:]
    prev_path = ""
    if "--prev" in args:
        i = args.index("--prev")
        prev_path = args[i + 1]
        del args[i : i + 2]
    if len(args) != 2:
        print(__doc__)
        return 2
    tickets_dir, out_path = args

    rows = collect(tickets_dir)
    dup = {r["id"] for r in rows if sum(1 for x in rows if x["id"] == r["id"]) > 1}
    prev = load_prev(prev_path)
    deliv_root = os.path.join(
        os.path.dirname(tickets_dir.rstrip("/")), "output", "deliverables"
    )

    todo_classify: list[str] = []
    by_folder: dict[str, list[dict[str, str]]] = {f: [] for f in FOLDERS}
    for r in rows:
        summary, stage = prev.get(r["id"], ("", ""))
        if not stage:
            todo_classify.append(f'{r["id"]} [{r["folder"]}] {r["title"]}')
            summary, stage = "（要記入）", "?"
        r["summary"] = summary
        r["stage"] = stage
        r["deliv"] = "有" if os.path.isdir(os.path.join(deliv_root, r["id"])) else "無"
        by_folder[r["folder"]].append(r)

    lines = [
        "# チケット全数棚卸し（事実台帳）",
        "",
        f"対象: `{tickets_dir}` 配下 **全{len(rows)}枚**（"
        + " / ".join(f"{f} {len(by_folder[f])}" for f in FOLDERS)
        + "）",
        "",
        "段階 0〜8 と「実質何が終わったか」は判断です。前回台帳から引き継ぎ、",
        "新規・状態変化ぶんだけを付け直しています。`?` は他分類とも取れるもの。",
        "",
        "## ライフサイクル段階の定義",
        "",
        "| # | 段階 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in STAGES],
        "",
    ]
    for folder in FOLDERS:
        lines += [
            f"## {folder}（{len(by_folder[folder])}枚）",
            "",
            "| ticket_id | 状態 | タイトル | 実質何が終わった（40字以内・事実） | 段階 | 成果物 | 報告欄 | 更新日 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in by_folder[folder]:
            lines.append(
                f'| {r["id"]} | {r["folder"]} | {r["title"]} | {r["summary"]} '
                f'| {r["stage"]} | {r["deliv"]} | {r["has_report"]} | {r["updated_at"]} |'
            )
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"inventory: {out_path}（{len(rows)}枚）")
    if dup:
        print("!! ticket_id の重複（カズヨへ要報告・採番の事故）: " + ", ".join(sorted(dup)))
    if todo_classify:
        print(f"要分類 {len(todo_classify)}枚:")
        for t in todo_classify:
            print("  " + t)
    else:
        print("要分類: なし（すべて前回台帳から引き継ぎ）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
