"""窓口集めキューに「上場」と「統合先」を付ける（T-20260930-001 / 2026-10-05）。**順位は変えない**（リサーチャーが作業中）。

    python3 37_listed_dedup.py <JPX の data_j.xlsx>

上場
- JPX 公式「東証上場銘柄一覧」（https://www.jpx.co.jp/markets/statistics-equities/misc/01.html の data_j.xlsx・無料）
  の内国株式（プライム・スタンダード・グロース）。PRO Market・ETF・REIT は使わない
- 「大手（上場）」＝ メーカー名かブランドが銘柄名と一致（法人格・全角半角・記号・空白を落として比較）
- 「大手（上場子会社の疑い）」＝ メーカー名が親の名前（銘柄名からホールディングス・グループを落とした核・3文字以上）で始まる。
  例：資生堂パーラー → 資生堂、キリンビバレッジ → キリンホールディングス。前方一致なので誤りはありうる＝「疑い」
統合先
- 照合キー（T-20260831-004 31_name_match.match_key：法人格・記号・空白を落として NFKC 小文字）が同じ行を同一社とみなす
- 一番上の順位の行を統合先にし、他の行の「統合先」にその順位と社名を書く。統合先の行に ASIN 数の合算を書く
"""
from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
WORK = REPO / "workspace/output/agent_output/T-20260930-001"
spec = importlib.util.spec_from_file_location("nm", REPO / "workspace/output/deliverables/T-20260831-004/31_name_match.py")
nm = importlib.util.module_from_spec(spec); spec.loader.exec_module(nm)

import re

# 前方一致の語境界：親の核がカタカナ/英字で終わり、続く文字も同じ種類なら別の語（リード|バディ、グリー|ンノート、FUJI|YA）
KATA, LATIN = re.compile(r"[ァ-ヴー]"), re.compile(r"[a-z0-9]")
# 語境界を越えても子会社とみなす親（グループ会社の社名が「親＋カタカナ」になる既知の大手）
GROUP_PREFIX = ("アサヒ", "キリン", "サントリー", "コーセー", "カルビー", "ニチレイ", "ヤクルト", "エステー", "ライオン")


def _boundary_ok(mk: str, core: str) -> bool:
    if core in GROUP_PREFIX:
        return True
    a, b = core[-1], mk[len(core)]
    return not ((KATA.match(a) and KATA.match(b)) or (LATIN.match(a) and LATIN.match(b)))


SUFFIX = ("ホールディングス", "ホールディング", "グループ本社", "グループ", "hd", "holdings")


def listed(xlsx: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    d = pd.read_excel(xlsx)
    d = d[d["市場・商品区分"].astype(str).str.contains("内国株式")]
    exact, cores = {}, []
    for _, r in d.iterrows():
        name = str(r["銘柄名"]); tag = f"{name}（{str(r['市場・商品区分']).replace('（内国株式）', '')}・{r['コード']}）"
        k = nm.match_key(name)
        exact[k] = tag
        core = k
        for s in SUFFIX:
            if core.endswith(s):
                core = core[: -len(s)]
        if len(core) >= 3:
            cores.append((core, tag))
    cores.sort(key=lambda x: -len(x[0]))  # 長い親を優先
    return exact, cores


def main(xlsx: str) -> None:
    exact, cores = listed(xlsx)
    q = WORK / "12_窓口集めキュー.csv"
    v1 = WORK / "12_窓口集めキュー_v1.csv"
    if not v1.exists():
        shutil.copy(q, v1)
    rows = list(csv.DictReader(v1.open(encoding="utf-8-sig")))
    for r in rows:
        keys = [nm.match_key(x) for x in (r["メーカー名"], *r["ブランド"].split(" / ")) if x]
        hit = next((exact[k] for k in keys if k in exact), "")
        if hit:
            short = min(len(k) for k in keys if k in exact) <= 4
            r["上場"] = f"大手（上場）：{hit}" + ("（社名が短い・同名別会社の可能性）" if short else "")
            continue
        mk = keys[0] if keys else ""
        par = next((tag for core, tag in cores if mk.startswith(core) and len(mk) > len(core) and _boundary_ok(mk, core)), "")
        r["上場"] = f"大手（上場子会社の疑い）：親 {par}" if par else ""
    groups = defaultdict(list)
    for r in rows:
        groups[nm.match_key(r["メーカー名"]) or r["メーカー名"]].append(r)
    for g in groups.values():
        head = g[0]
        head["統合先"] = ""
        if len(g) > 1:
            head["統合先"] = f"（統合先・{len(g)}行・ASIN数合算 {sum(int(x['該当ASIN数'] or 0) for x in g)}）"
            for x in g[1:]:
                x["統合先"] = f"→ {head['順位']}位 {head['メーカー名']}"
    cols = list(rows[0].keys())
    with q.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    n_l = sum(1 for r in rows if r["上場"].startswith("大手（上場）"))
    n_s = sum(1 for r in rows if "子会社" in r["上場"])
    n_d = sum(1 for r in rows if r["統合先"].startswith("→"))
    top = [r for r in rows if int(r["順位"]) <= 300]
    print(f"キュー {len(rows)}行 / 上場 {n_l} / 上場子会社の疑い {n_s} / 重複で統合先あり {n_d}行（{sum(1 for g in groups.values() if len(g) > 1)}社）")
    print(f"1〜300位: 上場 {sum(1 for r in top if r['上場'].startswith('大手（上場）'))} / 子会社疑い {sum(1 for r in top if '子会社' in r['上場'])} / 重複 {sum(1 for r in top if r['統合先'].startswith('→'))}")
    print("層1(印なし・中小)の印:", sum(1 for r in rows if r["層"].startswith("1") and r["上場"]))


if __name__ == "__main__":
    main(sys.argv[1])
