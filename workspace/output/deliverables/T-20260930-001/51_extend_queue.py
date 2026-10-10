"""窓口集めキュー（12_窓口集めキュー.csv）を、11_追加候補.csv の残り全件で延ばす（T-20260930-001 / タカシ 2026-10-11）。

なぜ：36_size_additions.py はキューに入れる行を「大手でも本人カート疑い（要確認）でもない」に絞っていた。
キューは 2169 位で尽き、11 の残り 1,074 行は誰も調べない状態だった。§3.3-34（調査に上限を置かない）に従い、
**捨てずに後ろへ並べる**。

並べ方（既存キューの規則を延長。既存の 1〜2169 位は1行も動かさない）
  層 4 本人カート疑い … 11 の「要確認」あり・大手でない・上場一致でない
  層 5 大手          … 11 の「大手」あり、または JPX 上場銘柄と社名一致（37_listed_dedup.listed と同じ判定）
  各層の中は 36 と同じ：優先度A → 該当ASIN数 降順 → 月販 降順

落とす行（理由列つきで 12b_窓口集めキュー_延長で落とした行.csv に残す。削除ではない）
  - 既存キュー（1〜2169位）と同社（照合キー一致）… 既存側が統合先
  - 既存台帳（30・22・24_連絡先_batch*.csv）と同社または同じ代表ASIN … 既に調べた社
新規行どうしの同社は落とさず、37 と同じく若い順位を統合先にして「→ N位」を書く。

入出力（agent_output/T-20260930-001/。Keepa 由来の値を含むので Git 除外）
  入力  11_追加候補.csv / 12_窓口集めキュー.csv / 30_最終_50社.csv / 22_連絡先_印付き.csv / 24_連絡先_batch*.csv
        JPX data_j.xlsx（T-20260929-001/14_roster/。37 と同じもの）
  出力  12_窓口集めキュー.csv（2170 位以降を追記）・12_窓口集めキュー.csv.bak_extend_<日付>・12b_…落とした行.csv
実行
  python3 workspace/output/deliverables/T-20260930-001/51_extend_queue.py [--dry-run]
  再実行しても既存キューに入った行は「既存キューと同社／同ASIN」で落ちるので二重には増えない（冪等）。
"""
from __future__ import annotations

import csv
import glob
import importlib.util
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
WORK = REPO / "workspace/output/agent_output/T-20260930-001"
XLSX = REPO / "workspace/output/agent_output/T-20260929-001/14_roster/data_j.xlsx"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


nm = _load("nm", REPO / "workspace/output/deliverables/T-20260831-004/31_name_match.py")
ld = _load("ld", HERE / "37_listed_dedup.py")

TIER_NAMES = {4: "4 本人カート疑い", 5: "5 大手"}
PAREN = re.compile(r"[（(][^）)]*[）)]")


def key(name: str) -> str:
    """照合キー。台帳の正式社名は「有限会社大塚薬品（キュー・gBiz照合）」のように注記つきなので括弧を落とす。"""
    return nm.match_key(PAREN.sub("", name or "").strip()) if name else ""


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def ledger_index() -> tuple[dict, dict]:
    """既存台帳の (社名キー→出典, ASIN→出典)。"""
    by_key, by_asin = {}, {}
    files = [WORK / "30_最終_50社.csv", WORK / "22_連絡先_印付き.csv"]
    files += [Path(p) for p in sorted(glob.glob(str(WORK / "24_連絡先_batch*.csv")))]
    for f in files:
        if not f.exists():
            continue
        for r in read(f):
            src = f"{f.name} 順位{r.get('順位', '')}".strip()
            for n in (r.get("メーカー名(タカシ)"), r.get("正式社名")):
                k = key(n or "")
                if k and len(k) >= 2:
                    by_key.setdefault(k, src)
            for a in [r.get("代表ASIN(タカシ)", "")] + (r.get("統合した行のASIN") or "").replace(";", " ").replace("、", " ").split():
                a = (a or "").strip()
                if re.fullmatch(r"[A-Z0-9]{10}", a):
                    by_asin.setdefault(a, src)
    return by_key, by_asin


def main() -> None:
    dry = "--dry-run" in sys.argv
    qpath = WORK / "12_窓口集めキュー.csv"
    queue = read(qpath)
    cols = list(queue[0].keys())
    last = max(int(r["順位"]) for r in queue)
    q_key = {}
    for r in queue:
        q_key.setdefault(key(r["メーカー名"]), r)
    q_asin = {r["代表ASIN"] for r in queue}
    l_key, l_asin = ledger_index()
    exact, cores = ld.listed(str(XLSX))

    cand = read(WORK / "11_追加候補.csv")
    keep, dropped = [], []
    for r in cand:
        a, k = r["代表ASIN"], key(r["メーカー名"])
        if a in q_asin:
            continue  # 既にキューにいる行（2169行）。落とした行には数えない
        if k and k in q_key:
            dropped.append((r, f"既存キューと同社：{q_key[k]['順位']}位 {q_key[k]['メーカー名']}"))
        elif a in l_asin:
            dropped.append((r, f"既存台帳と同じ代表ASIN：{l_asin[a]}"))
        elif k and k in l_key:
            dropped.append((r, f"既存台帳と同社：{l_key[k]}"))
        else:
            keep.append(r)

    def listed_mark(r) -> str:
        ks = [nm.match_key(x) for x in (r["メーカー名"], *r["ブランド"].split(" / ")) if x]
        hit = next((exact[x] for x in ks if x in exact), "")
        if hit:
            short = min(len(x) for x in ks if x in exact) <= 4
            return f"大手（上場）：{hit}" + ("（社名が短い・同名別会社の可能性）" if short else "")
        mk = ks[0] if ks else ""
        par = next((tag for core, tag in cores if mk.startswith(core) and len(mk) > len(core) and ld._boundary_ok(mk, core)), "")
        return f"大手（上場子会社の疑い）：親 {par}" if par else ""

    num = lambda x: float(x) if x not in ("", None) else 0
    for r in keep:
        r["_上場"] = listed_mark(r)
        r["_tier"] = 5 if (r["大手"] or r["_上場"].startswith("大手（上場）")) else 4
    keep.sort(key=lambda r: (r["_tier"], r["優先度"] != "A", -num(r["該当ASIN数"]), -num(r["過去1ヶ月の販売数(代表)"])))

    new = []
    for i, r in enumerate(keep, last + 1):
        new.append({"順位": str(i), "層": TIER_NAMES[r["_tier"]], "メーカー名": r["メーカー名"], "ブランド": r["ブランド"],
                    "代表ASIN": r["代表ASIN"], "AmazonURL": r["Amazon URL"], "該当ASIN数": r["該当ASIN数"],
                    "月販": r["過去1ヶ月の販売数(代表)"], "売価": r["代表の売価"], "印": r["印"], "要確認": r["要確認"],
                    "規模": r["規模"], "カート保持セラー": r["カート保持セラー(代表)"], "上場": r["_上場"], "統合先": ""})
    groups = defaultdict(list)
    for r in new:
        groups[key(r["メーカー名"]) or r["メーカー名"]].append(r)
    for g in groups.values():
        if len(g) > 1:
            g[0]["統合先"] = f"（統合先・{len(g)}行・ASIN数合算 {sum(int(x['該当ASIN数'] or 0) for x in g)}）"
            for x in g[1:]:
                x["統合先"] = f"→ {g[0]['順位']}位 {g[0]['メーカー名']}"

    print(f"11_追加候補 {len(cand)}行 / 既存キュー {len(queue)}行（末尾 {last}位）")
    print(f"追加 {len(new)}行 → 末尾 {last + len(new)}位 / 層: {dict(Counter(r['層'] for r in new))}")
    print(f"  うち新規どうしの同社で統合先あり {sum(1 for r in new if r['統合先'].startswith('→'))}行")
    print(f"落とした {len(dropped)}行: {dict(Counter(re.sub(r'：.*', '', why) for _, why in dropped))}")
    rest = len(cand) - len(queue) - len(new) - len(dropped)
    print(f"検算: 11 の行 {len(cand)} = キュー既存 {len(queue)} + 追加 {len(new)} + 落とした {len(dropped)} + 残差 {rest}")
    if dry:
        print("(dry-run: 書き込みなし)")
        return
    if not new:
        print("追加なし（11 の候補は尽きています）")
    bak = qpath.with_name(qpath.name + f".bak_extend_{date.today():%Y%m%d}")
    if not bak.exists():
        shutil.copy(qpath, bak)
    with qpath.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(queue + new)
    dpath = WORK / "12b_窓口集めキュー_延長で落とした行.csv"
    with dpath.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["落とした理由", "メーカー名", "ブランド", "代表ASIN", "AmazonURL", "該当ASIN数", "月販", "大手", "要確認"])
        for r, why in dropped:
            w.writerow([why, r["メーカー名"], r["ブランド"], r["代表ASIN"], r["Amazon URL"], r["該当ASIN数"],
                        r["過去1ヶ月の販売数(代表)"], r["大手"], r["要確認"]])
    print(f"書き込み: {qpath.name}（{len(queue) + len(new)}行）・{dpath.name}（{len(dropped)}行）・退避 {bak.name}")


if __name__ == "__main__":
    main()
