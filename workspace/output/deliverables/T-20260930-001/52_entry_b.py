"""入口(b)：売価 1,500〜2,199円の帯でメーカー候補を足し、窓口集めキューの末尾に並べる（T-20260930-001 / タカシ 2026-10-15）。

なぜ：12_窓口集めキュー.csv は 3,189位で尽きた（11_追加候補は全件消化）。02_抽出の漏斗.md §1 の「(b) 売価≥2,200 → ≥1,500」を
取りに行く。売価の下限は当社が置いた定数で、中村本の3基準ではない（CLAUDE.md §3.3-27「実践者は単価の下限を置かない」）。

基準（変えていないもの）
- 中村本の3基準：Amazon 本体が売っていない（365日 BB 本体≤10% → product の本体365日在庫切れ率≥90% で再判定）・
  大カテゴリー 50,000位以内・FBA 出品者（入口(a) と同じ「FBA≥2、または FBA≥1 かつ新品オファー≥2」）
- 積極条件：過去1ヶ月の販売数 ≥ 50。除外ルート・カートが FBA・資格なしでない・カートが今 Amazon でない
- 一次除外（maker_rules.classify：中国系OEM・海外ブランド・大手）・本人カート疑い（30_build.self_cart）・
  規模（36_size_additions：gBiz）・上場（37_listed_dedup）は既存のものをそのまま使う
変えたもの：売価の帯だけ。Finder は current_NEW 1,500〜2,199、product 再判定は「カート価格（無ければ新品最安）≥1,500」。

    python3 52_entry_b.py list                     # Finder 一覧（約75 token）→ raw/order_wideB.json（既取得 ASIN を除く）
    python3 52_entry_b.py fetch --until 01:30      # product を月販の多い順に取得（1 token/ASIN・中断点から再開）
    python3 52_entry_b.py build --until 01:30 [--dry-run]
        # 取得済み分だけで集約 → 代表 ASIN のカート保持者（3 token/社）→ gBiz 規模（0円）→ キュー末尾に追記
    再実行は冪等：キャッシュ済みは0 token、キューに入った社は「既存キューと同社」で二重に増えない。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11c_追加候補_入口b.csv          新規に集約した全社（除外・落とした理由つき）
  12d_入口b_落とした行.csv         キューに入れなかった社と理由
  12_窓口集めキュー.csv            末尾に追記（.bak_entryb_<日付> に退避）
  entry_b_status.json            取得の進み具合と続きの手順（夜間タスクが読む）
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import runpy
import shutil
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import keepa_io
import maker_rules as R

HERE = Path(__file__).resolve().parent
WORK = keepa_io.RAW.parent
ORDER = keepa_io.RAW / "order_wideB.json"
STATUS = WORK / "entry_b_status.json"
TAG = "wideB"
PRICE_MIN_B, PRICE_MAX_B = 1_500, 2_199


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


E = runpy.run_path(str(HERE / "50_expand.py"), run_name="lib")
SEL_B = {**E["WIDE_A"], "current_NEW_gte": PRICE_MIN_B, "current_NEW_lte": PRICE_MAX_B}


def deadline(s: str | None) -> datetime | None:
    if not s:
        return None
    h, m = map(int, s.split(":"))
    now = datetime.now()
    d = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return d if d > now else d + timedelta(days=1)


def can_spend(need: int, until: datetime | None) -> bool:
    """need token を until までに使い切れるか（20 token/分で補充）。"""
    if until is None:
        return True
    left = keepa_io.tokens_left()
    wait_min = max(0, need - left) / 20
    return datetime.now() + timedelta(minutes=wait_min + 1) < until


def status(**kw) -> None:
    s = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    s.update(kw); s["更新"] = datetime.now().isoformat(timespec="minutes")
    STATUS.write_text(json.dumps(s, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- list / fetch
def cmd_list() -> None:
    known: set[str] = set()
    for fn in ("order.json", "order_wideA.json", "order_seller.json"):
        p = keepa_io.RAW / fn
        if p.exists():
            known |= set(json.loads(p.read_text()))
    got = E["_list"](SEL_B, "wideB")          # 月販の降順（10,000件超なら昇順も足す）
    new = [a for a in got if a not in known]
    ORDER.write_text(json.dumps(new))
    status(一覧=len(got), 新規ASIN=len(new), 既取得と重複=len(got) - len(new))
    print(f"入口(b) 一覧 {len(got)} / 既取得と重複 {len(got) - len(new)} / 新規 {len(new)} ASIN", flush=True)


def cmd_fetch(until: datetime | None) -> int:
    order = json.loads(ORDER.read_text())
    n = 0
    for i in range(0, len(order), 100):
        cached = (keepa_io.RAW / f"prod_{TAG}_{i // 100:04d}.json.gz").exists()
        if not cached and not can_spend(len(order[i:i + 100]) + 5, until):
            print(f"締め切り {until:%H:%M} までに次の100件を取れないので止める（{i}/{len(order)}）", flush=True)
            break
        keepa_io.products(order[: i + 100], TAG, log=lambda s: print(s, flush=True))
        n = min(i + 100, len(order))
    status(product取得済み=n, product未取得=len(order) - n)
    print(f"product 取得済み {n}/{len(order)}", flush=True)
    return n


# ---------------------------------------------------------------- build
TIER_NAMES = {1: "1 印なし・中小", 2: "2 印あり・中小", 3: "3 規模不明", 4: "4 本人カート疑い", 5: "5 大手"}
ENTRY_MARK = "（入口b 売価1,500〜2,199）"


def _gbiz_exact(names: list[str]) -> None:
    """35_gbiz_rescue.py と同じ照合で、救済用の完全一致を引いて R.GBIZ_EXACT とファイルに足す（0円・1.15秒/件）。"""
    G35 = _mod("g35", HERE / "35_gbiz_rescue.py")
    outp = G35.OUT / "exact_by_name.json"
    res = json.loads(outp.read_text()) if outp.exists() else {}
    cli = G35.G.GBizInfo(G35.OUT)
    for n in names:
        if n in res:
            continue
        hits: dict[str, dict] = {}
        for q in G35.M.query_variants(n):
            for c in G35.M.pick_exact(cli.search_by_name(q), q):
                hits[c["corporate_number"]] = {"name": c.get("name"), "no": c["corporate_number"],
                                               "loc": (c.get("location") or "")[:20]}
        res[n] = list(hits.values())
    cli.flush(); outp.write_text(json.dumps(res, ensure_ascii=False))
    R.GBIZ_EXACT.update(res)


def cmd_build(until: datetime | None, dry: bool) -> None:
    B = _mod("b30", HERE / "30_build.py")
    Q = _mod("q51", HERE / "51_extend_queue.py")
    S = _mod("s36", HERE / "36_size_additions.py")
    order = json.loads(ORDER.read_text())
    ps = keepa_io.products(order, TAG, offline=True)
    funnel = [("入口(b) 新規 ASIN（Finder 一覧−既取得）", len(order)), ("product 取得済み", len(ps))]

    # 1) product 再判定。30_build.POST の売価だけを帯の下限に替える（他の条件は同じ関数）
    post = [(lbl, ok) for lbl, ok in B.POST if not lbl.startswith("6 ")]
    post.insert(4, (f"6 売価（カート価格・無ければ新品最安）≥ {PRICE_MIN_B:,}円",
                    lambda f: f["price"] is not None and f["price"] >= PRICE_MIN_B))
    alive = [(p, B.facts(p)) for p in ps]
    for lbl, ok in post:
        alive = [(p, f) for p, f in alive if ok(f)]
        funnel.append((lbl, len(alive)))

    # 2) メーカーに集約。旧プール（基本・入口(a)・セラー）に同じ社がいれば判定済みなので落とす
    old_keys = {R.maker_key(p)[0] for p in B.load_products()}
    groups: dict[str, list] = defaultdict(list)
    for p, f in alive:
        k, name = R.maker_key(p)
        groups[k].append((p, f, name))
    rows, dropped = [], []

    def classify_all(gs):
        out = []
        for k, items in gs:
            rep_p, rep_f, name = max(items, key=lambda x: ((x[1]["ms"] or 0), -(x[1]["rank"] or 10**9)))
            excl, why, rescue = R.classify(rep_p, [x[0] for x in items])
            out.append((k, items, rep_p, rep_f, name, excl, why, rescue))
        return out

    fresh = [(k, it) for k, it in groups.items() if k not in old_keys]
    for k, it in groups.items():
        if k in old_keys:
            rep = max(it, key=lambda x: x[1]["ms"] or 0)
            dropped.append(({"メーカー名": rep[2], "代表ASIN": rep[1]["asin"], "該当ASIN数": len(it)},
                            "旧プール（基本・入口(a)・セラー）と同社＝判定済み"))
    cl = classify_all(fresh)
    sus = sorted({n for c in cl if c[5] in R.RESCUABLE for n in [c[4], (c[2].get("brand") or "").strip()] if n})
    if sus:
        print(f"救済用 gBiz 照合 {len(sus)} 名", flush=True)
        _gbiz_exact(sus)
        cl = classify_all(fresh)
    for k, items, rep_p, rep_f, name, excl, why, rescue in cl:
        r = {"_p": rep_p, "_key": k, "優先度": "" if excl else "B", "メーカー名": name,
             "ブランド": " / ".join(dict.fromkeys((p.get("brand") or "").strip() for p, _, _ in items if p.get("brand")))[:60],
             "代表ASIN": rep_f["asin"], "代表商品名": rep_f["title"], "Amazon URL": f"https://www.amazon.co.jp/dp/{rep_f['asin']}",
             "該当ASIN数": len(items), "過去1ヶ月の販売数(代表)": rep_f["ms"], "代表の売価": rep_f["price"],
             "代表のFBA数": rep_f["fba"], "代表の新品オファー数": rep_f["offers"],
             "カテゴリ": R.ROOT_NAMES.get(rep_f["root"], str(rep_f["root"])),
             "印": "・".join(sorted({R.MARK_ROOTS[f["root"]] for _, f, _ in items if f["root"] in R.MARK_ROOTS})),
             "カート保持セラー(代表)": "", "要確認": "", "除外理由": excl, "判定の根拠": why, "救済の根拠": rescue,
             "大手": "", "規模": "", "法人番号(gBiz)": "", "入口": "入口(b) 売価1,500〜2,199"}
        rows.append(r)
        if excl:
            dropped.append((r, f"一次除外：{excl}"))

    # 3) 既存キュー・既存台帳と照合（カート保持者を引く前に落として token を節約）
    qpath = WORK / "12_窓口集めキュー.csv"
    queue = Q.read(qpath)
    last = max(int(x["順位"]) for x in queue)
    q_key = {}
    for x in queue:
        q_key.setdefault(Q.key(x["メーカー名"]), x)
    q_asin = {x["代表ASIN"] for x in queue}
    l_key, l_asin = Q.ledger_index()
    cand = []
    for r in rows:
        if r["除外理由"]:
            continue
        a, k = r["代表ASIN"], Q.key(r["メーカー名"])
        if k and k in q_key:
            x = q_key[k]
            if ENTRY_MARK in x["層"]:
                continue  # 前回の実行でこの入口から追記済み（冪等）。落とした行には数えない
            dropped.append((r, f"既存キューと同社：{x['順位']}位 {x['メーカー名']}"))
        elif a in q_asin:
            dropped.append((r, "既存キューと同じ代表ASIN"))
        elif a in l_asin:
            dropped.append((r, f"既存台帳と同じ代表ASIN：{l_asin[a]}"))
        elif k and k in l_key:
            dropped.append((r, f"既存台帳と同社：{l_key[k]}"))
        else:
            cand.append(r)
    print(f"集約 {len(groups)}社 / 旧プールと同社 {len(groups) - len(fresh)} / 新規 {len(rows)}"
          f"（除外 {sum(1 for r in rows if r['除外理由'])}）/ キュー・台帳照合後 {len(cand)}社", flush=True)

    # 4) 代表 ASIN のカート保持者（3 token/社）。締め切りまでに取れた分だけ
    reps = [r["代表ASIN"] for r in cand]
    have = keepa_io.products_buybox(reps, offline=True)
    need = [a for a in reps if a not in have]
    for i in range(0, len(need), 100):
        if dry or not can_spend(len(need[i:i + 100]) * 3 + 5, until):
            break
        have.update(keepa_io.products_buybox(need[i:i + 100], log=lambda s: print(s, flush=True)))
    sids = {a: ((have.get(a) or {}).get("stats") or {}).get("buyBoxSellerId") for a in reps if a in have}
    names = keepa_io.sellers([s for s in sids.values() if s], offline=dry or not can_spend(len(sids) + 5, until))
    for r in cand:
        if r["代表ASIN"] not in have:
            r["要確認"] = "カート保持者 未取得"
            continue
        sid = sids.get(r["代表ASIN"])
        seller = names.get(sid or "", "") or (sid or "")
        r["カート保持セラー(代表)"] = seller
        r["要確認"] = B.self_cart(seller, r["_p"].get("brand") or "", r["_p"].get("manufacturer") or "",
                                r["代表の新品オファー数"])

    # 5) 規模（gBiz・0円）と上場。36・51 と同じ判定
    ready = [r for r in cand if r["要確認"] != "カート保持者 未取得"]
    if not dry:
        client = S.RS.gb.GBizInfo(WORK / "gbiz")
        for r in ready:
            brand = r["ブランド"].split(" / ")[0]
            rec = S.size_of(client, r["メーカー名"], brand)
            r["大手"], r["規模"] = S.label(rec, R.known_big(brand, r["メーカー名"]))
            r["法人番号(gBiz)"] = rec.get("法人番号", "")
        client.flush()
    exact, cores = Q.ld.listed(str(Q.XLSX))

    def listed_mark(r) -> str:  # 51_extend_queue.main の listed_mark と同じ
        ks = [Q.nm.match_key(x) for x in (r["メーカー名"], *r["ブランド"].split(" / ")) if x]
        hit = next((exact[x] for x in ks if x in exact), "")
        if hit:
            short = min(len(x) for x in ks if x in exact) <= 4
            return f"大手（上場）：{hit}" + ("（社名が短い・同名別会社の可能性）" if short else "")
        mk = ks[0] if ks else ""
        par = next((tag for core, tag in cores if mk.startswith(core) and len(mk) > len(core) and Q.ld._boundary_ok(mk, core)), "")
        return f"大手（上場子会社の疑い）：親 {par}" if par else ""

    def tier(r) -> int:
        if r["大手"] or r["_上場"].startswith("大手（上場）"):
            return 5
        if r["要確認"]:
            return 4
        if r["規模"].startswith("中小"):
            return 1 if not r["印"] else 2
        return 3

    num = lambda x: float(x) if x not in ("", None) else 0
    for r in ready:
        r["_上場"] = listed_mark(r)
        r["_tier"] = tier(r)
    ready.sort(key=lambda r: (r["_tier"], -num(r["該当ASIN数"]), -num(r["過去1ヶ月の販売数(代表)"])))
    new = []
    for i, r in enumerate(ready, last + 1):
        new.append({"順位": str(i), "層": TIER_NAMES[r["_tier"]] + ENTRY_MARK, "メーカー名": r["メーカー名"],
                    "ブランド": r["ブランド"], "代表ASIN": r["代表ASIN"], "AmazonURL": r["Amazon URL"],
                    "該当ASIN数": r["該当ASIN数"], "月販": r["過去1ヶ月の販売数(代表)"], "売価": r["代表の売価"],
                    "印": r["印"], "要確認": r["要確認"], "規模": r["規模"], "カート保持セラー": r["カート保持セラー(代表)"],
                    "上場": r["_上場"], "統合先": ""})
    gq = defaultdict(list)
    for x in new:
        gq[Q.key(x["メーカー名"]) or x["メーカー名"]].append(x)
    for g in gq.values():
        if len(g) > 1:
            g[0]["統合先"] = f"（統合先・{len(g)}行・ASIN数合算 {sum(int(x['該当ASIN数'] or 0) for x in g)}）"
            for x in g[1:]:
                x["統合先"] = f"→ {g[0]['順位']}位 {g[0]['メーカー名']}"

    tiers = Counter(x["層"] for x in new)
    why = Counter(re.sub(r"：.*", "", w) for _, w in dropped)
    pend = len(cand) - len(ready)
    print("漏斗:", *[f"  {a}: {b}" for a, b in funnel], sep="\n")
    print(f"キューに足す {len(new)}社（{last + 1}〜{last + len(new)}位）層 {dict(tiers)}")
    print(f"落とした {len(dropped)}: {dict(why)} / カート保持者 未取得で保留 {pend}社")
    summ = {"漏斗": funnel, "集約した社": len(groups), "キューに足した社": len(new), "層": dict(tiers),
            "落とした理由": dict(why), "保留(カート保持者未取得)": pend,
            "新しい末尾": last + len(new), "前の末尾": last}
    if dry:
        print("(dry-run: 書き込みなし)")
        return

    cols = ["優先度", "メーカー名", "ブランド", "代表ASIN", "代表商品名", "Amazon URL", "該当ASIN数", "過去1ヶ月の販売数(代表)",
            "代表の売価", "代表のFBA数", "代表の新品オファー数", "カテゴリ", "印", "カート保持セラー(代表)", "要確認",
            "除外理由", "判定の根拠", "救済の根拠", "大手", "規模", "法人番号(gBiz)", "入口"]
    with (WORK / "11c_追加候補_入口b.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with (WORK / "12d_入口b_落とした行.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["落とした理由", "メーカー名", "代表ASIN", "該当ASIN数", "要確認"])
        for r, wy in dropped:
            w.writerow([wy, r.get("メーカー名"), r.get("代表ASIN"), r.get("該当ASIN数"), r.get("要確認", "")])
    if new:
        bak = qpath.with_name(qpath.name + f".bak_entryb_{datetime.now():%Y%m%d_%H%M}")
        shutil.copy(qpath, bak)
        qcols = list(queue[0].keys())
        with qpath.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=qcols); w.writeheader(); w.writerows(queue + new)
        print(f"書き込み: {qpath.name}（{len(queue)}→{len(queue) + len(new)}行）退避 {bak.name}")
    status(build=summ)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "fetch", "build"])
    ap.add_argument("--until", help="HH:MM。これを過ぎる取得はしない（夜間タスクと Keepa を分け合うため）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    u = deadline(a.until)
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "fetch":
        cmd_fetch(u)
    else:
        cmd_build(u, a.dry_run)
