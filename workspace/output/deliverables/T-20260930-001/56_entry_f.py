"""入口(f)：手持ちの Keepa product を今のルールで判定し直し、取りこぼした社を窓口集めキューに足す
（T-20260930-001 / タカシ 2026-10-20 夜間）。Finder・product は取り直さない（0 token）。token を使うのはカート保持者だけ。

なぜ：キューは 5,361位で尽きる。売価をこれ以上下げる入口は掛けで落ちる（入口(e) 売価1,000〜1,249 は接触候補57社のうち27社が基準NG）。
10/19 夜の2案を件数で測った（2026-10-20 02時・キュー/台帳と重複しない社の数・0 token）：
  案1 一次除外「中国系OEM疑い」の救済の見直し … 対象 2,440社。新しい根拠で救える社は約25社（同じ社の手持ち product に JAN45/49）。
       ただし救えるのは海外ブランドの日本輸入元（Dove・M・A・C 等）が中心で、送り先として薄い → 採らない。
       商品名の「日本製」は中国系セラーも書く（「日本製センサー搭載」）ので根拠にしない
  案2 旧プール同社で落とした社の状態変化 … 採用。**52_entry_b の「旧プールと同社＝判定済み」は、旧プールで条件を通らなかった
       商品しか無い社まで落としていた**（旧プールの社のキー＝取得した全 product の社。集約して判定した社ではない）。
  手持ちの product には名簿拡張①（T-20260929-001 の r14a/r14b・3,000円以上・約36,000件）も入れた。同じ基準で通る社が出る。

基準（変えていないもの）：monthlySold ≥ 50・本体の365日在庫切れ率 ≥ 90%・FBA 出品者の条件・除外ルート・一次除外（maker_rules.classify、
  救済の根拠は条件を通った ASIN だけ）・本人カート疑い・規模（gBiz）・上場。キュー・台帳と同社／同じ代表 ASIN は足さない。
売価×ランク：過去の入口の和集合から売価1,000〜1,249 を抜いたもの（ランク≤5万×売価≥1,250、ランク≤30万×売価≥1,500）。
変えたもの：「判定済み」の定義＝過去の候補ファイル（10_完全版・11_・11c〜11f）に載った社（残した・除外したの両方）。
  それ以外の社（旧プールに商品はあったが集約されなかった社・名簿拡張①にだけいる社）を今のルールで判定する。

v1（2026-10-20 02:58）は除外した社も判定し直し、大手に big_verify・救済に同じ社の全 product を当てた → 218社のうち89社が
  海外の有名ブランド（Crucial・Miele・Dove・M・A・C 等）と大手（サントリー・コーセー・ユニ・チャーム等。big_verify が商品名の
  カタカナ表記を見ずに層3 へ落とした）だった。キューを退避から戻し、v1 の版は 12_窓口集めキュー.csv.entryf_v1_rejected_20261020 に残した。

    python3 56_entry_f.py build [--until 03:30] [--dry-run] [--prefetch]
    再実行は冪等：キューに入った社は「既存キューと同社」で二重に増えない。キューへは追記のみ（既存行は書き換えない）。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11g_追加候補_入口f.csv / 12h_入口f_落とした行.csv / 12_窓口集めキュー.csv（.bak_entryf_<日時> に退避）/ entry_f_status.json
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


M = _mod("entry_b", HERE / "52_entry_b.py")       # can_spend・_gbiz_exact・TIER_NAMES を使い回す
R, keepa_io = M.R, M.keepa_io
WORK = M.WORK
STATUS = WORK / "entry_f_status.json"
LABEL = "入口(f) 手持ちの再判定"
ENTRY_MARK = "（入口f 再判定）"
OUT_CAND, OUT_DROP, BAK_TAG = "11g_追加候補_入口f.csv", "12h_入口f_落とした行.csv", "entryf"
FRESH_NOTE = "未判定（旧プール同社で落としていた／名簿拡張①のみ）"  # 57_entry_g が差し替える
M.RESERVE = 300  # 2026-10-20 夜は UNKNOWN 潰し・プレミアム監視も Keepa を使う。終わった時点で 300 以上残す

# 手持ちの product（先に書いたものを優先して ASIN の重複を落とす）。(product タグ, order ファイル)
POOL = [("all", "order.json"), ("wideA", "order_wideA.json"), ("seller", "order_seller.json"),
        ("wideB", "order_wideB.json"), ("wideC", "order_wideC.json"), ("wideD", "order_wideD.json"),
        ("wideE", "order_wideE.json"), ("wideE2", "order_wideE2.json"),
        ("r14a", "order_r14a_fetch.json"), ("r14b", "order_r14b_fetch.json")]
# 過去の候補ファイル。ここに載った社＝集約して判定した社（残した社はキューか重複で処理済み・除外した社は除外のまま）
PREV = ["10_メーカー候補_完全版.csv", "11_追加候補.csv", "11c_追加候補_入口b.csv", "11d_追加候補_入口c.csv",
        "11e_追加候補_入口d.csv", "11f_追加候補_入口e_rank.csv", "11f_追加候補_入口e_price.csv"]


RANK_PRICE_LABEL = "4・6 ランク≤5万×売価≥1,250 または ランク≤30万×売価≥1,500"


def rank_price_ok(f: dict) -> bool:
    r, p = f["rank"], f["price"]
    if r is None or p is None:
        return False
    return (r <= 50_000 and p >= 1_250) or (r <= 300_000 and p >= 1_500)


def status(**kw) -> None:
    s = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    s.update(kw); s["更新"] = datetime.now().isoformat(timespec="minutes")
    STATUS.write_text(json.dumps(s, ensure_ascii=False, indent=1))


def load_pool() -> list[dict]:
    seen, out = set(), []
    for tag, fn in POOL:
        f = keepa_io.RAW / fn
        if not f.exists():
            continue
        for p in keepa_io.products(json.loads(f.read_text()), tag, offline=True):
            if p["asin"] not in seen:
                seen.add(p["asin"]); p["_src"] = tag; out.append(p)
    return out


def prev_index() -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    for fn in PREV:
        p = WORK / fn
        if not p.exists():
            continue
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out.setdefault(R._n(r["メーカー名"]), (fn, r.get("除外理由", "") or "", r.get("優先度", "") or ""))
    return out


AMAZON_SELLER = "AN1VRQENFRJN5"  # Amazon.co.jp のセラーID（50_expand.py と同じ値）


def cmd_build(until, dry: bool, prefetch: bool = False) -> None:
    B = _mod("b30", HERE / "30_build.py")
    Q = _mod("q51", HERE / "51_extend_queue.py")
    S = _mod("s36", HERE / "36_size_additions.py")
    ps = load_pool()
    funnel = [("手持ちの product（基本・入口a・セラー・入口b〜e・名簿拡張①）", len(ps))]
    post = [(lbl, ok) for lbl, ok in B.POST if not lbl.startswith(("4 ", "6 "))]
    post.append((RANK_PRICE_LABEL, rank_price_ok))  # 58_entry_h が両方を差し替える
    alive = [(p, B.facts(p)) for p in ps]
    for lbl, ok in post:
        alive = [(p, f) for p, f in alive if ok(f)]
        funnel.append((lbl, len(alive)))

    groups: dict[str, list] = defaultdict(list)
    for p, f in alive:
        k, name = R.maker_key(p)
        groups[k].append((p, f, name))

    qpath = WORK / "12_窓口集めキュー.csv"
    queue = Q.read(qpath)
    last = max(int(x["順位"]) for x in queue)
    q_key: dict[str, dict] = {}
    for x in queue:
        q_key.setdefault(Q.key(x["メーカー名"]), x)
    q_asin = {x["代表ASIN"] for x in queue}
    l_key, l_asin = Q.ledger_index()
    prev = prev_index()

    dropped, fresh = [], []
    for k, items in groups.items():
        rep = max(items, key=lambda x: ((x[1]["ms"] or 0), -(x[1]["rank"] or 10**9)))
        a, qk = rep[1]["asin"], Q.key(rep[2])
        info = {"メーカー名": rep[2], "代表ASIN": a, "該当ASIN数": len(items)}
        if qk and qk in q_key:
            if ENTRY_MARK not in q_key[qk]["層"]:  # この入口で足した社は冪等のため数えない
                dropped.append((info, f"既存キューと同社：{q_key[qk]['順位']}位"))
            continue
        if a in q_asin:
            dropped.append((info, "既存キューと同じ代表ASIN")); continue
        if a in l_asin:
            dropped.append((info, f"既存台帳と同じ代表ASIN：{l_asin[a]}")); continue
        if qk and qk in l_key:
            dropped.append((info, f"既存台帳と同社：{l_key[qk]}")); continue
        pv = prev.get(k)
        if pv:  # 過去に集約して判定した社（残した／除外した）。v1 は除外した社も判定し直したが、海外の有名ブランドと大手が89社混ざった
            dropped.append((info, f"過去の候補で判定済み（{pv[0]}・{'残した' if pv[2] else '除外：' + pv[1]}）")); continue
        fresh.append((k, items, rep, pv))

    def classify_all():
        out = []
        for k, items, rep, pv in fresh:
            excl, why, rescue = R.classify(rep[0], [x[0] for x in items])  # 救済の根拠は条件を通った ASIN だけ（既存の入口と同じ）
            out.append((k, items, rep, pv, excl, why, rescue))
        return out

    cl = classify_all()
    sus = sorted({n for c in cl if c[4] in R.RESCUABLE for n in [c[2][2], (c[2][0].get("brand") or "").strip()]
                  if n and n not in R.GBIZ_EXACT})
    if sus and not dry:
        print(f"救済用 gBiz 照合 {len(sus)} 名（0円・約1.15秒/名）", flush=True)
        M._gbiz_exact(sus)
        cl = classify_all()

    rows, cand = [], []
    for k, items, (rp, rf, name), pv, excl, why, rescue in cl:
        srcs = sorted({x[0]["_src"] for x in items})
        r = {"_p": rp, "優先度": "" if excl else "B", "メーカー名": name,
             "ブランド": " / ".join(dict.fromkeys((p.get("brand") or "").strip() for p, _, _ in items if p.get("brand")))[:60],
             "代表ASIN": rf["asin"], "代表商品名": rf["title"], "Amazon URL": f"https://www.amazon.co.jp/dp/{rf['asin']}",
             "該当ASIN数": len(items), "過去1ヶ月の販売数(代表)": rf["ms"], "代表の売価": rf["price"],
             "代表のFBA数": rf["fba"], "代表の新品オファー数": rf["offers"],
             "カテゴリ": R.ROOT_NAMES.get(rf["root"], str(rf["root"])),
             "印": "・".join(sorted({R.MARK_ROOTS[f["root"]] for _, f, _ in items if f["root"] in R.MARK_ROOTS})),
             "カート保持セラー(代表)": "", "要確認": "", "除外理由": excl, "判定の根拠": why, "救済の根拠": rescue,
             "大手": "", "規模": "", "法人番号(gBiz)": "", "入口": LABEL, "取得元": "・".join(srcs),
             "前回の判定": (f"{pv[0]}：除外（{pv[1]}）" if pv else FRESH_NOTE)}
        rows.append(r)
        if excl:
            dropped.append((r, f"一次除外：{excl}"))
        else:
            cand.append(r)
    print(f"集約 {len(groups)}社 / 判定し直した社 {len(fresh)} / 一次除外を通った {len(cand)}社", flush=True)

    # カート保持者（3 token/社）。キャッシュ済みは0 token
    reps = [r["代表ASIN"] for r in cand]
    have = keepa_io.products_buybox(reps, offline=True)
    need = [a for a in reps if a not in have]
    for i in range(0, len(need), 100):
        n = len(need[i:i + 100]) * 3 + 5
        if dry or not M.can_spend(n, until):
            break
        keepa_io.wait_for(n + M.RESERVE, log=lambda s: print(s, flush=True))
        have.update(keepa_io.products_buybox(need[i:i + 100], log=lambda s: print(s, flush=True)))
    sids = {a: ((have.get(a) or {}).get("stats") or {}).get("buyBoxSellerId") for a in reps if a in have}
    new_sids = [s for s in sids.values() if s]
    _known = json.loads((keepa_io.RAW / "seller_names.json").read_text())
    print(f"カート保持セラー {len(set(new_sids))} 件のうち名前が未取得 {len(set(new_sids) - set(_known))} 件（1 token/件）", flush=True)
    names =keepa_io.sellers(new_sids, offline=dry or not M.can_spend(len(new_sids) + 5 + M.RESERVE, until))
    miss = [a for a in reps if a not in have]
    status(カート保持者=f"{len(reps) - len(miss)}/{len(reps)}", 残高=keepa_io.tokens_left())
    if prefetch:
        print(f"prefetch: カート保持者 {len(reps) - len(miss)}/{len(reps)} 社", flush=True)
        return
    for r in cand:
        if r["代表ASIN"] not in have:
            r["要確認"] = "カート保持者 未取得"; continue
        sid = sids.get(r["代表ASIN"])
        seller = names.get(sid or "", "") or (sid or "")
        r["カート保持セラー(代表)"] = seller
        r["要確認"] = B.self_cart(seller, r["_p"].get("brand") or "", r["_p"].get("manufacturer") or "", r["代表の新品オファー数"])
        if sid == AMAZON_SELLER:  # 2026-10-23（タカシ）：ISSE が層3 に残った。本体カートの棚は打診しても売れない（§3.3-1）
            r["_本体カート"] = True
            r["優先度"], r["除外理由"] = "", "Amazon 本体がカート（§3.3-1）"  # 11*_追加候補 の読み手にも除外として見せる
            dropped.append((r, "一次除外：Amazon 本体がカート（§3.3-1・Keepa buyBoxSellerId）"))

    ready = [r for r in cand if r["要確認"] != "カート保持者 未取得" and not r.get("_本体カート")]
    if not dry:
        client = S.RS.gb.GBizInfo(WORK / "gbiz")
        for r in ready:
            rec = S.size_of(client, r["メーカー名"], r["ブランド"].split(" / ")[0])
            r["大手"], r["規模"] = S.label(rec, R.known_big(r["ブランド"].split(" / ")[0], r["メーカー名"]))
            r["法人番号(gBiz)"] = rec.get("法人番号", "")
        client.flush()
    exact, cores = Q.ld.listed(str(Q.XLSX))

    def listed_mark(r) -> str:  # 2026-10-21：37_listed_dedup.listed_mark に一本化（同名別会社の取り違え対策）
        return Q.ld.listed_mark(r["メーカー名"], r["ブランド"].split(" / "), exact, cores, big=r["大手"], size=r["規模"])

    def tier(r) -> int:  # 52_entry_b と同じ（BIG_VERIFY あり）
        if r["大手"] or r["_上場"].startswith("大手（上場）"):
            return 5  # big_verify は使わない（v1 でサントリー・コーセー・ユニ・チャーム等 30社超を層3 に落とした）
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
        note = "・死に帯" if 1_001 <= num(r["代表の売価"]) <= 1_100 else ""
        new.append({"順位": str(i), "層": M.TIER_NAMES[r["_tier"]] + ENTRY_MARK + note, "メーカー名": r["メーカー名"],
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
    prevc = Counter(re.sub(r"：除外（(.{0,10}).*", r"：除外（\1", r["前回の判定"]) for r in ready)
    pend = len(cand) - len(ready)
    print("漏斗:", *[f"  {a}: {b}" for a, b in funnel], sep="\n")
    print(f"キューに足す {len(new)}社（{last + 1}〜{last + len(new)}位）層 {dict(tiers)}")
    print(f"前回の判定 {dict(prevc)}")
    print(f"落とした {len(dropped)}: {dict(why)} / カート保持者 未取得で保留 {pend}社")
    summ = {"漏斗": funnel, "集約した社": len(groups), "判定し直した社": len(fresh), "キューに足した社": len(new),
            "層": dict(tiers), "前回の判定": dict(prevc), "落とした理由": dict(why), "保留(カート保持者未取得)": pend,
            "新しい末尾": last + len(new), "前の末尾": last}
    if dry:
        print("(dry-run: 書き込みなし)")
        return

    cols = ["優先度", "メーカー名", "ブランド", "代表ASIN", "代表商品名", "Amazon URL", "該当ASIN数", "過去1ヶ月の販売数(代表)",
            "代表の売価", "代表のFBA数", "代表の新品オファー数", "カテゴリ", "印", "カート保持セラー(代表)", "要確認",
            "除外理由", "判定の根拠", "救済の根拠", "大手", "規模", "法人番号(gBiz)", "入口", "取得元", "前回の判定"]
    # 2026-10-27（タカシ）：冪等確認の2回目の build（足す社0）が、1回目に書いた候補ファイル（11i3_）を
    # 「除外行だけ」で上書きし、sync_ledger が読む代表のFBA数が消えて ZZH の接触候補が全部「未確認：FBA数」に落ちた。
    # 足す社が0で、既存の候補ファイルに候補行（優先度あり）が残っているときは書き換えない。
    out = WORK / OUT_CAND
    if not new and out.exists() and any((r.get("優先度") or "").strip() for r in csv.DictReader(out.open(encoding="utf-8-sig"))):
        print(f"{OUT_CAND} は書き換えない（足す社0・既存の候補行を守る）")
        return
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with (WORK / OUT_DROP).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["落とした理由", "メーカー名", "代表ASIN", "該当ASIN数", "要確認"])
        for r, wy in dropped:
            w.writerow([wy, r.get("メーカー名"), r.get("代表ASIN"), r.get("該当ASIN数"), r.get("要確認", "")])
    if new:
        bak = qpath.with_name(qpath.name + f".bak_{BAK_TAG}_{datetime.now():%Y%m%d_%H%M}")
        shutil.copy(qpath, bak)
        qcols = list(queue[0].keys())
        if not qpath.read_bytes().endswith(b"\n"):
            raise RuntimeError(f"{qpath.name} の末尾が改行でない。追記すると最終行が壊れるので止める")
        with qpath.open("a", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=qcols).writerows(new)
        print(f"書き込み: {qpath.name}（{len(queue)}→{len(queue) + len(new)}行）退避 {bak.name}")
    status(build=summ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--until", help="HH:MM。これを過ぎる Keepa 取得はしない")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prefetch", action="store_true", help="カート保持者だけ先に取る。キューは書かない")
    a = ap.parse_args()
    cmd_build(M.deadline(a.until), a.dry_run, a.prefetch)


if __name__ == "__main__":
    main()
