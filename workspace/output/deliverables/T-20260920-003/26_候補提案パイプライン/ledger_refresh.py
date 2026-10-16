#!/usr/bin/env python3
"""商品判定台帳（Googleスプレッドシート）を最新の採点で引き直し、足りない行を足す。

社長指示（2026-10-10 夜）の要旨:
  「取引できる卸から仕入れられる商品を必ず台帳に加えろ。SD も加えろ。
    仕入れられない商品も載せてよいが、満たさない基準を明示し、
    『こう変えれば仕入れられる』というコメントを付けろ。」

やること（この順）
  1. NETSEA 側：旧プール(10/04)＋新規逆引き(10/09) を score_20261004 で採点し直す
     （Keepa は叩かない。手元の取得済みデータだけで再計算＝トークン0・§3.3-21）
  2. 10/09 のゲート実機確認（restrictions/approve）の結果を反映する
  3. SD 側：sd_candidates_private.csv（SD 起点 375行）を ASIN 単位で1行にして足す。
     カズヨが社長の Chrome で読んだ卸価格（sd_price_manual_20261010.csv）があれば採算を確定する。
     **SD への自動取得はしない**（CLAUDE.md §3.3-14・18）
  4. 判定理由を「未達（§3.5 の項目番号）／こう変えれば／人が見る項目」の3段に揃える
  5. 機械判定が全部通った行も GO にしない。**人の実画面確認（キーゾン・カート）が済むまで
     UNKNOWN**（§3.3-16）。判定理由に「機械判定は通過・実画面確認待ち」と書く

守ること
  - 列の追加・削除・様式変更はしない。値の更新と行の追記だけ
  - 「確認者」が人（カズヨ）の行は**一切上書きしない**（§3.3-16）
  - 卸値・卸率・購入先URL は**シートにだけ**書く。このスクリプトは値を持たない（PUBLIC リポ）
  - 捨てない。NO-GO も理由つきで残す

規定と実装のずれ（2026-10-10 タカシが発見。ここで規定側に合わせて読み替える）
  - 実売：実装は「ランク 30万位より下で FAIL」。§3.3-8 は「10万〜50万位は UNKNOWN、
    50万位より下で NO-GO」。→ 30万〜50万位の FAIL は UNKNOWN（キーゾンで決める）に読み替える
  - 採算：実装の C は「中央値で利益率20%未満かつ手残り400円未満」。§3.5 #18 の C は
    「中央値で利益率5%未満かつ手残り400円未満」。→ 中央値5%以上の C は B（最小ロットで1回）
    に読み替える
  どちらも判定理由に「（§…による読み替え・実装は FAIL/C）」と明記する。

使い方
  python3 ledger_refresh.py --dry-run     # シートに書かず、集計と差分だけ出す
  python3 ledger_refresh.py               # シートへ書く（書く前の全値を before_*.json に退避）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: §3.5 #18 実績枠の判定文字列（consistency.TRACK_RECORD と同じ。import 前に EXTRA で使うので直書き）
K_TR = "GO（実績枠）"
REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
BUY = WORK / "buylist20261009"
SDB = WORK / "sd_buylist20261009"
OUT = WORK / "ledger20261010"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))
sys.path.insert(0, str(BUY))

import score_20261004 as S     # noqa: E402
import fba_cost                # noqa: E402
sys.path.insert(0, str(REPO / "scripts/sourcing_gate"))
import consistency as K        # noqa: E402
import screen_checks as SC     # noqa: E402
import hidden_cart as HC       # noqa: E402
import profit                  # noqa: E402
import discontinued as DISC    # noqa: E402

#: 2026-10-11 実売 UNKNOWN 行を Keepa で取り直した生データ（stats=90&history=1&buybox=1）
FRESH_RAW = OUT / "keepa_unknown_20261011.jsonl"
FRESH: dict[str, tuple[dict, int]] = {}      # {ASIN: (product, fetched_unix)}
#: GO(テスト)／カートなし黒字の別記（社長判断の材料）。main() で CSV に書く
EXTRA: dict[str, list[dict]] = {"GO": [], K_TR: [], "GO・ゲート未確認": [], "カートなし黒字": []}

#: 人の実画面確認（カート・ゲート・キーゾン）。main() で読み込む。ここに載っている ASIN は
#: 「確認者=カズヨ」でも凍結せず、毎回この証跡から人の値を合流させて引き直す。
SCREEN = SC.ScreenChecks({}, {}, {})
LEGAL = SC.load_legal()            # 法務判定で販売を止める行（GO にしない）


def load_price_checks() -> dict[str, dict]:
    """人が実画面で見た実勢価格で NO-GO にする行（2026-10-14〜・#13）。

    `ledger20261010/price_checks_*.csv`（ASIN・実勢価格・根拠・確認者・確認時刻）。
    Keepa の90日中央値より実際のカート・次点が安く、採算の前提が崩れている行を止める。"""
    out = {}
    for p in sorted(OUT.glob("price_checks_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            a = (r.get("ASIN") or "").strip()
            if a:
                out[a] = r
    return out


PRICE_CHECKS = load_price_checks()

DIAG: list[dict] = []          # 行ごとの項目の状態（GO の手前で止まっている理由の集計用）
WAIT_FULL: list[dict] = []     # 実画面確認待ち（NETSEA）の全列。autofill.py に渡す


def consistency_gate(s: dict, comp: dict) -> dict:
    """実画面確認待ちに上げる前に、算術を consistency.py（§3.3-17）で検算する。
    崩れていたら待ちに上げず、理由を書いて UNKNOWN に留める（数字は直さない）。"""
    if not comp["waiting"]:
        return comp
    row = S.as_row(s, full=True)
    res = K.check_row(row)
    if res.ok:
        WAIT_FULL.append(row)
        return comp
    msg = " ／ ".join(clean(f.line(), 80) for f in res.blocking[:3])
    comp = dict(comp)
    comp["waiting"] = False
    comp["verdict"] = "UNKNOWN"
    comp["reason"] = (f"整合性検査 NG（§3.3-17・採算の数字は信用しない）：{msg} ／"
                      f"【こう変えれば】卸と Amazon の画面で単位・売価を人が確かめれば決まる ／ "
                      + comp["reason"])[:1800]
    return comp

SHEET_ID = "1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I"
CRED = Path.home() / ".config/claude-session-sheets/credentials.json"
TICKET = "T-20260920-003"
TODAY = date.today().isoformat()
SD_MANUAL = SDB / "sd_price_manual_20261010.csv"
#: 2026-10-11 22:30 カズヨが社長 Chrome で読んだ SD 卸価格（SD品番キー・段階価格つき）。
#: SD_MANUAL（10/10・ASIN キー）より新しいので、同じ SD 品番ではこちらが勝つ
SD_SCREEN = SDB / "sd_price_screen_20261011.csv"
#: NETSEA 停止中（10/7〜）に、同じ購入元の SD 出展で買える ASIN の仕入れ経路を SD に切り替える。
#: 卸価格は人の実画面（カズヨ）。値はこのファイルにだけあり、スクリプトは持たない（PUBLIC）
SD_ROUTE = SDB / "sd_route_override_20261011.csv"
#: 2026-10-12：ヤザワ（DNライティング）の SD 一覧価格（カズヨ実画面・120型番）を型番で突き合わせた分。
#: 一覧で見たのは価格だけなので**在庫は未確認**（＝#17 仕入れは UNKNOWN）。
#: 同じ ASIN が SD_ROUTE（10/11・在庫確認済み）にあれば、そちらを優先する。
SD_ROUTE_EXTRA = sorted(SDB.glob("sd_route_override_2026101[2-9]*.csv"))
#: 2026-10-12 サトル：問屋 国分ネット卸の非ログイン商品ページ（kokubu_lookup.py・法務判定50）で
#: 読んだ値段。SD_ROUTE と同じ列＋「卸サイト」列。値はこのファイルにだけあり、スクリプトは持たない
KOKUBU_ROUTE = sorted((WORK / "kokubu").glob("kokubu_route_override_*.csv"))
#: 2026-10-12 サトル：仕入れ先起点（supplier_screen.py）で見つけた台帳外の ASIN。
#: 列は ASIN・JAN・仕入れ先。商品データは supplier_screen のキャッシュ（トークン0）から読む
FEEDS = sorted(OUT.glob("new_supplier_candidates_*.csv"))

#: score_20261004 のゲート名 → CLAUDE.md §3.5 の項目番号
ITEM = {
    "価格の動き": "#13-14 販売価格・価格の傾き",
    "カート保持者": "#5 カートの販売元",
    "実売": "#9 実売",
    "仕入れ": "#17 卸の在庫",
    "セット数": "#15 Amazon側のセット構成",
    "採算": "#18 採算等級",
    "季節の窓": "#11 季節の窓",
    "取り直し": "#13 価格データ",
    "取引条件": "#4 仕入れ先の Amazon 出品可否",
    "Amazonカタログ": "#16 カタログJAN",
    "ゲート": "#1-2 出品許可",
    "取り分": "#10 取り分と在庫月数",
    "取り寄せ価格": "#13 販売価格（取り寄せ型の値付けしかない）",
    "終売": "#12 終売（今だけ3条件）",
    "実勢価格": "#13 実勢価格",
    "知財": "#8 知財申立てのサイン",
}
HUMAN_ITEMS_BASE = ["#9 キーゾンで3か月の実数（型番ごと）",
                    "#5 カートの販売元を実画面で読む",
                    "#7 新品出品者の内訳（出品一覧）"]


def clean(t: str, n: int = 90) -> str:
    t = re.sub(r"\*\*|`", "", t or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def yen(x) -> str:
    return f"{int(round(x)):,}円"


# ── NETSEA 側の採点（make_list.py と同じ母集団・同じ採点）──────────────────

def score_netsea() -> list[dict]:
    import score_new  # buylist20261009/
    old = S.score_all()
    for s in old:
        s["_src"] = "旧プール(10/04)"
    new_rows = json.loads((BUY / "new_rows.json").read_text())
    prods = score_new.load_products()
    idx = json.loads((WORK / "pipeline/netsea_jan_index.json").read_text())["jans"]
    names = json.loads((WORK / "pipeline/seller_names.json").read_text())
    rc: Counter = Counter()
    for p in prods.values():
        cur = (p.get("stats") or {}).get("current") or []
        if len(cur) > 3 and cur[3] and cur[3] > 0:
            rc[cur[3]] += 1
    new = []
    for a, r in new_rows.items():
        s = S.build(r, {"fba_yen": r.get("_fba_yen") or None}, prods[a], idx, names,
                    "2026-10-01", None, dict(rc))
        s["_src"] = "新規逆引き(10/09)"
        s["_supplier_url"] = r.get("_supplier_url")
        s["_cand"], s["_idx_day"] = {"fba_yen": r.get("_fba_yen") or None}, "2026-10-01"
        new.append(s)
    new += score_kz_entry(idx, names, rc)
    new += score_feeds(idx, names, rc)
    # 2026-10-11：実売 UNKNOWN 行は Keepa を取り直した（buybox=1 でカート保持者・history=1 で
    # ランク履歴）。取り直した ASIN は新しい商品データで採点し直す（同じ行・同じ卸データ）。
    load_fresh()
    if FRESH:
        cands = json.loads(S.DISCOVERED.read_text())["candidates"]
        idx_day_old = S.load_all()[5]
        for s in old:
            s.setdefault("_cand", cands.get(s["asin"]) or {})
            s.setdefault("_idx_day", idx_day_old)
        rc2 = Counter(rc)
        for p, _ in FRESH.values():
            cur = (p.get("stats") or {}).get("current") or []
            if len(cur) > 3 and cur[3] and cur[3] > 0:
                rc2[cur[3]] += 1
        out = []
        supp = load_supplement()
        for s in old + new:
            f = FRESH.get(s["asin"])
            if not f and _no_product(s):
                f = supp.get(s["asin"])
            if f and s.get("row"):
                s2 = S.build(s["row"], s["_cand"], f[0], idx, names, s["_idx_day"], None, dict(rc2))
                for k in ("_src", "_supplier_url", "_cand", "_idx_day"):
                    if k in s:
                        s2[k] = s[k]
                s2["_fresh"] = f[1]
                s = s2
            out.append(s)
        out += score_screened_orphans(out, idx, names, dict(rc2))
        return route_to_sd(out + score_off_ledger(out, idx, names, dict(rc2)), idx, names, dict(rc2))
    base = old + new
    base += score_screened_orphans(base, idx, names, dict(rc))
    return route_to_sd(base + score_off_ledger(base, idx, names, dict(rc)), idx, names, dict(rc))


#: 2026-10-14 まで採点プールだった「生きている」buy_list_private（毎晩 台帳ダンプで上書きされる）
LIVE_POOL = WORK / "pipeline/buy_list_private.csv"
#: 台帳にある ASIN（main() がシートを読んだ後に入れる）。採点プール外の孤児行を拾うのに使う
LEDGER_ASINS: set[str] = set()


def score_screened_orphans(scored: list[dict], idx: dict, names: dict, rc: dict) -> list[dict]:
    """台帳にある（または人の実画面確認がある）のに、どの採点プールにも居ない ASIN を採点に戻す。

    なぜ要るか（2026-10-15 タカシ）：10/14 に POOL を 648行の凍結コピーに戻したため、10/13 の
    生きたプール（台帳ダンプ）でしか採点されていなかった行が「孤児」になり、以後 ledger_refresh が
    一度も引き直さない。そこへカズヨがゲート・カートを実画面で見ても判定に効かない
    （10/15 の browser_results 85件のうち16件。B07G4HFP3N はゲート FAIL なのに UNKNOWN のまま）。

    範囲：当初（10/15 22時）は人の証跡がある ASIN だけ。秘書判断で同日 23時に**台帳の孤児行の全量**に広げた
    （判定日 10/13・10/14 のまま止まっていた約850行）。
    行は生きたプールの同じ ASIN の行、商品データは手元の取得済み（FRESH・取り直し・補完）だけ。
    データが無ければ採点しない＝既存行は据え置き（keep_when_no_data と同じ考え方）。Keepa は叩かない。"""
    have = {x["asin"] for x in scored}
    todo = ({a for a in (set(SCREEN.cart) | set(SCREEN.gate)) if SCREEN.covers(a)} | LEDGER_ASINS) - have
    if not todo or not LIVE_POOL.exists():
        return []
    rows = {}
    for r in csv.DictReader(LIVE_POOL.open(encoding="utf-8-sig")):
        a = (r.get("ASIN") or "").strip()
        if a in todo and a not in rows:
            rows[a] = r
    if not rows:
        return []
    load_fresh()
    prods: dict[str, tuple[dict, int]] = dict(load_supplement())
    prods.update({k: v for k, v in FRESH.items() if k not in prods or v[1] >= prods[k][1]})
    if KZ_FULL.exists():
        for line in KZ_FULL.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("asin") and o.get("product") and o["asin"] not in prods:
                prods[o["asin"]] = (o["product"], o.get("fetched") or 0)
    cands = json.loads(S.DISCOVERED.read_text())["candidates"]
    idx_day = S.load_all()[5]
    out = []
    for a, row in rows.items():
        pf = prods.get(a)
        if not pf:
            continue
        cand = cands.get(a) or {}
        s = S.build(row, cand, pf[0], idx, names, idx_day, None, dict(rc))
        s.update({"_src": "孤児行(10/13 生きたプール)", "_cand": cand,
                  "_idx_day": idx_day, "_fresh": pf[1]})
        out.append(s)
    return out


#: 台帳の外の SD 候補で、秘書が SD 実画面で卸値を読んで sd_route_override に入れた ASIN のうち、
#: 採点プールに無いもの。Keepa の商品データが無ければ取り直し待ちとして書き出す（unknown_stages s0）
OFF_NEEDS = WORK / "unknown_queue" / "off_ledger_needs_keepa.txt"


def score_off_ledger(scored: list[dict], idx: dict, names: dict, rc: dict) -> list[dict]:
    """sd_route_override にあるのに採点プールに無い ASIN を、手元の Keepa データで採点する。
    卸値は route_to_sd が SD 実画面の値で差し替える（ここでは仮の行を作るだけ）。"""
    have = {x["asin"] for x in scored}
    route = load_sd_route()
    todo = [a for a in route if a not in have]
    if not todo:
        if OFF_NEEDS.exists():
            OFF_NEEDS.write_text("")
        return []
    prods: dict[str, tuple[dict, int]] = dict(load_supplement())
    for f in [KZ_FULL, *sorted(STAGE_RAW.glob("keepa_stage_*.jsonl"))]:
        if f.exists():
            for line in f.open():
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("asin") and o.get("product"):
                    t = o.get("fetched") or 0
                    if o["asin"] not in prods or t >= prods[o["asin"]][1]:
                        prods[o["asin"]] = (o["product"], t)
    prods.update({k: v for k, v in FRESH.items() if k not in prods or v[1] >= prods[k][1]})
    # 台帳外の古いプールが持っている取得済みデータ（取得時刻が無いので最後の手段＝無い ASIN にだけ使う）
    for f in (WORK / "sd_lookup_keepa_raw_20261011.json", WORK / "sanrio8/raw.json"):
        if f.exists():
            d = json.loads(f.read_text())
            for p in (d.values() if isinstance(d, dict) else d):
                if p.get("asin") and p["asin"] not in prods:
                    prods[p["asin"]] = (p, int((p.get("lastUpdate") or 0) + 21564000) * 60)
    out, missing = [], []
    for a in todo:
        o = route[a]
        pf = prods.get(a)
        if not pf:
            missing.append(a)
            continue
        p, fetched = pf
        row = {"ASIN": a, "商品名": p.get("title") or o.get("商品名") or "", "ブランド": p.get("brand") or "",
               "AmazonURL": f"https://www.amazon.co.jp/dp/{a}", "JAN": (o.get("JAN") or "").strip(),
               "卸の1点あたり原価(税込)": "", "購入先URL": o.get("購入先URL") or "",
               "購入元の名前": o.get("購入元の名前") or o.get("SD出展企業") or "", "ゲート種別": "未確認"}
        cand = {"fba_yen": (p.get("fbaFees") or {}).get("pickAndPackFee")}
        s2 = S.build(row, cand, p, idx, names, "2026-10-01", None, rc)
        s2.update({"_src": "台帳外SD(off_ledger)", "_cand": cand, "_idx_day": "2026-10-01",
                   "_fresh": fetched})
        out.append(s2)
    OFF_NEEDS.parent.mkdir(parents=True, exist_ok=True)
    OFF_NEEDS.write_text("".join(f"{a}\n" for a in missing))
    return out


#: 2026-10-12：kz 入口（monthlySold を問わず Keepa 再現の3か月販売数で選んだ Amazon 起点）の
#: 台帳に未登録の行。採点は既存の行と同じ S.build、実売は kz_estimate_*_kzentry.csv
#: （kz_entry_candidates.py estimate）を screen_checks が読んで決める。Keepa は叩かない。
KZ_NEW = OUT / "new_kz_candidates_20261011.csv"
KZ_FULL = WORK / "kz_entry/keepa_full.jsonl"


def score_kz_entry(idx: dict, names: dict, rc: Counter) -> list[dict]:
    if not (KZ_NEW.exists() and KZ_FULL.exists()):
        return []
    import kz_entry_candidates as KE
    full = KE.load_jsonl(KZ_FULL)
    out = []
    for r in csv.DictReader(KZ_NEW.open(encoding="utf-8-sig")):
        a = r["ASIN"].strip()
        if a not in full:
            continue
        p, fetched = full[a]
        row = KE.build_row(a, p, idx, None, 1)
        if not row:
            continue
        cand = {"fba_yen": row.get("_fba_yen") or None}
        s = S.build(row, cand, p, idx, names, KE.IDX_DAY, None, dict(rc))
        s["_src"] = "kz入口(10/11)"
        s["_supplier_url"] = row.get("_supplier_url")
        s["_cand"], s["_idx_day"], s["_fresh"] = cand, KE.IDX_DAY, fetched
        out.append(s)
    return out


def score_feeds(idx: dict, names: dict, rc: Counter) -> list[dict]:
    """仕入れ先起点の台帳外 ASIN を、既存の行と同じ S.build で採点する（2026-10-12 サトル）。

    卸値は NETSEA 索引（10/01）か、国分の実測（KOKUBU_ROUTE）。NETSEA 索引に無い国分の JAN は
    国分の実測を索引の形にして足す。経路の切り替え（SD／国分）は route_to_sd が行う。"""
    if not FEEDS:
        return []
    import kz_entry_candidates as KE
    import supplier_screen as SS
    want: dict[str, dict] = {}
    for f in FEEDS:
        for r in csv.DictReader(f.open(encoding="utf-8-sig")):
            a = (r.get("ASIN") or "").strip()
            if a:
                want.setdefault(a, r)
    latest, _ = SS.load_by_asin(set(want))
    idx2 = dict(idx)
    for o in load_sd_route().values():
        j = (o.get("JAN") or "").strip()
        if o.get("卸サイト") == "国分ネット卸" and j and j not in idx2:
            idx2[j] = {"jan": j, "unit_price_excl": S._num(o["卸価格_税抜_1点"]),
                       "min_lot_units": int(S._num(o.get("卸の最小ロット(点)")) or 1),
                       "stock": o.get("在庫") or "", "title": o.get("卸の商品名") or "",
                       "supplier_name": "問屋 国分ネット卸", "supplier_url": o.get("購入先URL") or ""}
    out = []
    for a, r in want.items():
        c = latest.get(a)
        if not c:
            continue
        row = KE.build_row(a, c.product, idx2, None, 1)
        if not row:
            continue
        cand = {"fba_yen": row.get("_fba_yen") or None}
        s = S.build(row, cand, c.product, idx2, names, KE.IDX_DAY, None, dict(rc))
        s["_src"] = f"仕入れ先起点({r.get('仕入れ先') or ''})"
        s["_supplier_url"] = row.get("_supplier_url")
        s["_cand"], s["_idx_day"], s["_fresh"] = cand, KE.IDX_DAY, c.fetched
        out.append(s)
    return out


def load_sd_route() -> dict[str, dict]:
    out: dict[str, dict] = {}
    # 古い順に読み、先に入った（在庫まで確認済みの）行を後のファイルで上書きしない
    for f in [SD_ROUTE, *SD_ROUTE_EXTRA, *KOKUBU_ROUTE]:
        if not f.exists():
            continue
        for r in csv.DictReader(f.open(encoding="utf-8-sig")):
            a = (r.get("ASIN") or "").strip()
            if not (a and S._num(r.get("卸価格_税抜_1点"))):
                continue
            # 2026-10-15：JAN 照合済みの値は、先に入った JAN 未照合の値より勝つ（ファイルの順に関係なく）
            prev = out.get(a)
            if prev is None or ((prev.get("JAN照合") or "済").strip() != "済"
                                and (r.get("JAN照合") or "済").strip() == "済"):
                out[a] = r
    return out


def route_to_sd(scored: list[dict], idx: dict, names: dict, rc: dict) -> list[dict]:
    """NETSEA 行のうち、SD で同じ購入元から買える ASIN を SD 経路で採点し直す（2026-10-11）。

    - 原価は SD の卸1点（税抜・人の実画面）×1.1。NETSEA の卸値は使わない
    - NETSEA の索引（在庫・URL）を引かないよう、その JAN を外した索引で build する
    - #17 仕入れは SD 実画面の在庫で PASS／FAIL を付け直す（索引が無いので UNKNOWN になるため）
    """
    route = load_sd_route()
    if not route:
        return scored
    out = []
    for s in scored:
        o = route.get(s["asin"])
        if not (o and s.get("row") and s.get("product")):
            out.append(s)
            continue
        row = dict(s["row"])
        excl = S._num(o["卸価格_税抜_1点"])
        row["卸の1点あたり原価(税込)"] = f"{excl * 1.1:.1f}"
        row["Amazon1個あたり原価(税込)"] = ""
        row["卸の最小ロット(点)"] = o.get("卸の最小ロット(点)") or "1"
        row["購入先URL"] = o["購入先URL"]
        jan = (row.get("JAN") or "").strip()
        idx2 = {k: v for k, v in idx.items() if k != jan}   # URL は SD に替えたので索引に当たらない
        s2 = S.build(row, s.get("_cand") or {}, s["product"], idx2, names,
                     s.get("_idx_day") or "2026-10-01", None, rc)
        for k in ("_src", "_cand", "_idx_day", "_fresh"):
            if k in s:
                s2[k] = s[k]
        stock = (o.get("在庫") or "").strip()
        sold_out = "SOLD OUT" in stock.upper() or stock in ("なし", "品切れ")
        # 2026-10-12：在庫を見ていない行（一覧で価格だけ見た）を「在庫あり」にしない
        in_stock = stock in ("あり", "在庫あり")
        st = "FAIL" if sold_out else ("PASS" if in_stock else "UNKNOWN")
        word = {"FAIL": "在庫なし", "PASS": "在庫あり", "UNKNOWN": "在庫は未確認（価格のみ確認）"}[st]
        site = o.get("卸サイト") or "スーパーデリバリー"
        memo = (o.get("メモ") or "").strip()
        s2["gates"] = [g for g in s2["gates"] if g[0] != "仕入れ"] + [(
            "仕入れ", st,
            f"{'SD' if site == 'スーパーデリバリー' else site}（{o['購入先URL']}）で{word}・卸1点 {excl:,.0f}円（税抜）"
            f"（{o.get('確認者', '')} {o.get('確認時刻', '')}）" + (f"。{memo}" if memo and site != "スーパーデリバリー" else "")
            + "。**発注直前に卸値を引き直してください。**")]
        s2["在庫"] = {"FAIL": "在庫なし", "PASS": "在庫あり", "UNKNOWN": "未確認"}[st]
        s2["channel"] = site
        s2["_route"] = o
        out.append(s2)
    return out


#: 2026-10-11：旧プールのうち 705行は refetch20261004/raw.jsonl に商品データが無く、
#: 「今日の値を取り直せていません」のまま一度も採点されていなかった。手元に既にある取得済み
#: データ（トークン0）で埋める。**商品データが1つも無い行にだけ**使う（既にデータがある行を
#: buybox なしの古いデータで上書きしない）。後ろほど新しい＝後勝ち。
SUPP_RAW = [BUY / "resolve_raw.jsonl",                 # 2026-10-09 stats=90&history=1（buybox なし）
            BUY / "buybox_raw.jsonl",                  # 2026-10-09 buybox=1
            OUT / "keepa_kz_hist_20261011.jsonl"]      # 2026-10-11 キーゾン再現用 history=1


def _no_product(s: dict) -> bool:
    g = s.get("gates") or []
    return bool(g) and g[0][0] == "取り直し"


#: 「商品データが無い」ことを示す判定理由の文言（score_20261004.build の取り直しゲート）
NO_DATA_TEXT = "今日の値を取り直せていません"
_VRANK = {"GO": 0, "UNKNOWN": 1, "NO-GO": 2}


def better(new: dict, old: dict | None) -> bool:
    """同じ ASIN が採点プールに2行あるとき、new を採るか。

    判定の良い方（GO>UNKNOWN>NO-GO）を採るが、**商品データが無い行（取り直し）は
    データのある行に必ず負ける**。2026-10-13 18:00、データなしの UNKNOWN が NO-GO に勝って
    台帳の判定理由を消した（データなしは判定の根拠にならない）。"""
    if old is None:
        return True
    if _no_product(new) != _no_product(old):
        return not _no_product(new)
    return _VRANK.get(new["判定"], 3) < _VRANK.get(old["判定"], 3)


def keep_when_no_data(row: dict, s: dict) -> bool:
    """手元に商品データが無い採点で、台帳の既存行を上書きしないか。

    既存行がデータに基づく判定（理由に「取り直せていません」が無い）なら据え置く。
    2026-10-12 は GO 行だけ守っていたが、NO-GO の理由（在庫月数・季節など）も同じく根拠であり、
    「データが無い」で消してよいものではない（2026-10-14）。"""
    if not _no_product(s):
        return False
    if row.get("判定") in K.GO_VERDICTS or (row.get("判定理由") or "").startswith("#17 卸値の出どころ"):
        return True
    return bool(row.get("判定")) and NO_DATA_TEXT not in (row.get("判定理由") or "")


def restore_no_data_rows(rows: list[dict], snap_path: Path, header: list[str]) -> list[str]:
    """一度だけの修復：取り直しで上書きされた行を、上書き前のスナップショットから戻す。

    対象＝人の行でなく、今の理由が「取り直せていません」で、スナップショットでは
    データに基づく判定だった行。値は列名で合わせる（列が増えていても動く）。"""
    snap = json.loads(snap_path.read_text())
    sh = snap[0]
    old = {r[sh.index("ASIN")]: dict(zip(sh, r + [""] * (len(sh) - len(r)))) for r in snap[1:] if r}
    done = []
    for r in rows:
        if is_human(r) or NO_DATA_TEXT not in (r.get("判定理由") or ""):
            continue
        o = old.get(r["ASIN"])
        if not o or NO_DATA_TEXT in (o.get("判定理由") or "") or not o.get("判定"):
            continue
        for h in header:
            if h in o:
                r[h] = o[h]
        done.append(r["ASIN"])
    return done


def load_supplement() -> dict[str, tuple[dict, int]]:
    out: dict[str, tuple[dict, int]] = {}
    for f in SUPP_RAW:
        if not f.exists():
            continue
        for line in f.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("asin") and o.get("product"):
                out[o["asin"]] = (o["product"], o.get("fetched") or 0)
    return out


#: 2026-10-12：UNKNOWN の段階解消（unknown_stages.py）が取り直した生データ。FRESH と同じ扱いで、
#: 同じ ASIN は fetched が新しい方を使う
STAGE_RAW = WORK / "unknown_queue"


def load_fresh() -> None:
    if FRESH:
        return
    for f in [FRESH_RAW, *sorted(STAGE_RAW.glob("keepa_stage_*.jsonl"))]:
        if not f.exists():
            continue
        for line in f.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if not (o.get("asin") and o.get("product")):
                continue
            t = o.get("fetched") or 0
            if o["asin"] not in FRESH or t >= FRESH[o["asin"]][1]:
                FRESH[o["asin"]] = (o["product"], t)


def econ_at(s: dict, sell: float, sell_worst: float | None):
    """売価を差し替えて採算を出す（カートなし棚の基準売価用）。build() と同じ式。"""
    p = s.get("product") or {}
    n, per_pt = s.get("n_set"), s.get("per_pt")
    if not (n and per_pt and s.get("セット数の確度") in ("確定", "単独")):
        return None
    fba_yen = (p.get("fbaFees") or {}).get("pickAndPackFee") or (s.get("_cand") or {}).get("fba_yen")
    if not fba_yen:
        return None
    unit = per_pt * n
    freight = 0.0 if S.freight_in_cost(s.get("row") or {}) else None   # 国分は卸値に按分済み
    e = profit.compute(sell, p.get("referralFeePercentage"), fba_yen, unit, 10,
                       monthly_sold=None, category=s.get("category"), unit_decided=True,
                       supplier_freight=freight)
    est = ["保管月数（売り切り月数が実測でない）"]
    if not (p.get("fbaFees") or {}).get("pickAndPackFee"):
        est.append("FBA配送代行（Keepa 実測なし）")
    gr = fba_cost.grade(sell, unit, e.size_tier, category=s.get("category"),
                        keepa_pct=p.get("referralFeePercentage"), months_to_sell=3.0,
                        unit_decided=True, sell_worst=sell_worst, estimated=tuple(est),
                        supplier_freight=freight)
    return e, gr


def load_gate_checks() -> dict[str, dict]:
    p = BUY / "gate_check_20261009.csv"
    return {r["ASIN"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig"))}


def reread_gates(s: dict) -> list[tuple[str, str, str, str]]:
    """(ゲート, 状態, 理由, 読み替えの注記)。§3.3-8 / §3.5 #18 に合わせて読み替える。"""
    out = []
    e = s.get("econ")
    for name, st, why in s["gates"]:
        note = ""
        # 2026-10-11：実売（§3.3-8）と採算 B（§3.5 #18）の読み替えは、ライブラリ本体
        # （score_20261004.velocity_of / fba_cost.grade）を規定に合わせて直したので撤去した。
        if name == "採算" and st == "FAIL" and e and e.grade in ("A", "B") \
                and e.order_total > S.MAX_ORDER_TOTAL_YEN:
            st, note = "PASS", (f"等級 {e.grade}。発注額 {yen(e.order_total)} が1SKU枠を超えるだけ"
                                f"＝最小ロットに減らせば枠内（§3.5 B は最小ロットで1回）")
        out.append((name, st, why, note))
    return out


def fix_for(name: str, st: str, why: str, s: dict) -> tuple[str, bool]:
    """(こう変えれば, 変えようがないか)。"""
    e = s.get("econ")
    if name == "実勢価格":
        return ("実勢価格（カートと次点の即納価格）が採算の線に戻れば再判定。"
                "ふるさと納税など相場外の出品が消えるかを定点で見る"), False
    if name == "カート保持者" and st == "FAIL" and "メーカー" in why:
        return "変えようがない：メーカー/ブランド本人がカート（原価で負ける・§3.3-5）", True
    if name == "カート保持者" and st == "FAIL":
        return "変えようがない：Amazon 本体がカート（値下げしても取れない・§3.3-1）", True
    if name == "カート保持者" and "疑い" in why:
        return "出品者プロフィールの事業者名を見て、メーカーと別会社なら可", False
    if name == "カート保持者" and "カートなし" in why:
        return ("売価を相場（90日中央値）に戻せばカートを取れる可能性。出品一覧の最安の即納価格と"
                "90日中央値を比べれば決まる"), False
    if name == "取り分":
        info = s.get("_share") or {}
        fix = info.get("fix") or "人が確認すれば決まる"
        sh = info.get("share")
        if sh is not None and st == "FAIL":
            if sh >= K.TRACK_MIN_SHARE:
                floor = max(int(s.get("min_lot") or 1), 10 if s.get("_docs") else 1)
                m = floor / sh
                if m > K.TRACK_MAX_MONTHS:
                    ok_lot = int(sh * K.TRACK_MAX_MONTHS)
                    fix += (f"／取り分 {sh:.1f}個/月は実績枠の線（月{K.TRACK_MIN_SHARE:g}個以上）は満たすが、"
                            f"最小ロット {floor}点で在庫 {m:.1f}か月（6か月超）。"
                            f"{ok_lot}点以下で買える仕入れ先（小分けの卸）なら GO（実績枠）の候補")
                else:
                    fix += (f"／取り分 {sh:.1f}個/月は実績枠の線（月{K.TRACK_MIN_SHARE:g}個以上）は満たす"
                            "＝中央値で手残り0円以上なら GO（実績枠・最小ロット1回）")
            else:
                fix += f"／実績枠でも月{K.TRACK_MIN_SHARE:g}個以上が要る（いま {sh:.1f}個）"
        return fix, False
    if name == "カート保持者":
        return "実画面でカートの販売元を読めば決まる（カート不在なら出品者の内訳を見る）", False
    if name == "実売" and st == "FAIL":
        sea = s.get("season")
        if sea and sea.peak_months:
            pk = "・".join(f"{m}月" for m in sea.peak_months)
            return f"通年では売れていない。ピーク {pk} の2か月前に再判定すれば拾える可能性", False
        return f"変えようがない：売れている根拠がない（{clean(why, 50)}）", True
    if name == "実売":
        return "キーゾンで3か月の実数を見れば決まる（月3個以上の取り分があれば可）", False
    if name == "価格の動き" and st == "FAIL":
        return "下落が止まり、90日の後半が前半比-5%以内に戻れば再判定で通る", False
    if name == "知財" and st == "FAIL":
        return ("変えようがない：ブランド公式・正規店が出品している棚は、知財申立てや販売者限定化で"
                "排除される側に回る（§3.3-5）。メーカー直取引で販売許可を得れば別"), True
    if name == "知財":
        return "出品一覧と Keepa の出品者数グラフで公式・正規店の有無を見れば決まる", False
    if name == "取り寄せ価格":
        return ("即納で売れる相場が無い。Keepa で即納の出品者がいた時期のカート価格（1年前など）を"
                "売価にして採算を引き直し、黒字なら可"), False
    if name in ("価格の動き", "取り直し"):
        return "実画面で売価（カート価格）を確認すれば採算を計算できる", False
    if name == "仕入れ" and st == "FAIL":
        return "NETSEA 品切れ。再入荷か、SD 等で同一 JAN を探せば可", False
    if name == "仕入れ":
        return "卸サイトで同一 JAN の在庫・卸値を確認すれば決まる", False
    if name == "セット数":
        return "Amazon と卸の画面で「Amazon1個＝卸何点」を人が確認すれば採算を計算できる", False
    if name == "季節の窓":
        sea = s.get("season")
        pk = "・".join(f"{m}月" for m in (sea.peak_months if sea else ())) or "ピーク"
        return f"今季は間に合わない。{pk}の2〜3か月前に発注すれば窓に入る", False
    if name == "採算":
        return fix_profit(s), False
    if name == "終売":
        if "(a)" in why and "在庫なし" in why:
            return "終売品：仕入れ先に在庫が戻るか、同じ型番の在庫がある別の卸を探せば可", False
        if "(b)" in why and "＞" in why:
            return "終売品：初回点数を減らし、製造終了までに売り切れる量にすれば可", False
        if "下落" in why:
            return "終売品：値崩れが止まり価格が横ばいに戻れば再判定で通る", False
        return "終売品：卸の在庫・在庫月数（取り分）・価格の傾きが決まれば今だけ仕入れ可か決まる", False
    return "人が確認すれば決まる", False


def fix_profit(s: dict) -> str:
    e = s.get("econ")
    if not e:
        lv = s.get("price")
        miss = []
        if not (lv and lv.sell_for_profit):
            miss.append("売価（実画面）")
        if not s.get("per_pt"):
            miss.append("卸の1点単価")
        if not s.get("n_set"):
            miss.append("セット数")
        return (f"{'・'.join(miss) or 'FBA手数料'}が決まれば計算できる"
                if miss else "FBA 手数料（サイズ区分）が決まれば計算できる")
    if e.grade not in ("A", "B", "C"):
        return "寸法が分かればサイズ区分が決まり計算できる（セラセンの商品登録画面で確認）"
    tr_note = ""
    if e.grade == "C":
        mid = mid_net(e)
        if mid is not None and mid >= K.TRACK_MIN_NET_YEN:
            tr_note = (f"中央値の手残り {yen(mid)}＝実績枠の採算の線（0円以上）は満たす。"
                       "ほかの地雷が全部 PASS・取り分 月1個以上なら GO（実績枠・最小ロット1回）")
        elif mid is not None:
            n_ = s.get("n_set") or 1
            tr_note = (f"実績枠（手残り0円以上）まであと {yen(-mid)}"
                       f"＝卸1点を {yen(-mid / n_ / 1.1)}（税抜）下げれば実績枠の採算は満たす")
    if e.cost_ratio_pct < S.MIN_PLAUSIBLE_COST_RATIO:
        return (f"卸率{e.cost_ratio_pct}%は低すぎる＝単位ずれか終売の疑い。"
                f"卸と Amazon の画面で単位を確かめれば決まる")
    base = e.sell - e.referral_fee_yen - e.fba_yen - e.other_unit_costs
    cap = max(base - e.sell * 0.05, base - fba_cost.MIN_PROFIT_YEN)   # §3.5 B の原価上限
    n = s.get("n_set") or 1
    parts = []
    if cap > 0:
        per_pt_excl = cap / n / 1.1
        now_pt = (s.get("per_pt") or e.unit_cost_incl / n) / 1.1
        parts.append(f"卸1点 {yen(per_pt_excl)}（税抜）以下なら B（いま {yen(now_pt)}）")
    else:
        parts.append(f"売価 {yen(e.sell)} では原価0円でも利益率5%に届かない")
    tier = e.size_tier
    if tier:
        need = fba_cost.required_sell(e.unit_cost_incl, tier, 0.05,
                                      category=s.get("category"))
        if need:
            parts.append(f"売価 {yen(need)} 以上の棚なら B")
        try:
            bn, btxt = fba_cost.bundle_advice(tier, e.sell / n, e.unit_cost_incl / n,
                                              category=s.get("category"))
            if bn and bn > 1:
                parts.append(f"セット組 {bn}個なら固定費が割れる（{clean(btxt, 60)}）")
        except Exception:
            pass
    if e.cliff_note:
        parts.append(clean(e.cliff_note, 70))
    if tr_note:
        parts.insert(0, tr_note)
    return "／".join(parts)


def mid_net(e) -> int | None:
    """等級を決めた中央シナリオの手残り。古い Economics（属性なし）なら None＝推測しない。"""
    return getattr(e, "mid_net_per_unit", None) if e else None


def price_is_normal(s: dict) -> tuple[bool, str]:
    """実績枠 ⑥。現在価格は人の実画面のカート価格 → 実画面売価 → Keepa の最終観測の順。"""
    lv = s.get("price")
    if not lv:
        return False, "価格履歴が無い＝平常か判断できない"
    c = SCREEN.cart.get(s["asin"])
    cur = (SC._num(c.price) if c and c.price else None) or lv.screen_price or lv.current
    return K.price_normal(cur, lv.median90, getattr(lv, "median365", None),
                          getattr(lv, "days_covered365", 0))


def track_record_frame(s: dict, gates: list, gate: dict | None) -> dict | None:
    """§3.5 #18 実績枠に入るか（2026-10-12 社長方針「プラマイ0でも卸で実績を作る」）。

    入る条件（CLAUDE.md §3.5 #18 実績枠 ①〜⑤）
      - 採算：等級 C（取り分だけが足りない B も拾う）で、中央値の1個手残りが0円以上
        ※ 損益計算書の手残り（net_per_unit）と等級の中央シナリオの両方が0円以上（保守側）
      - 取り分：月1個以上（通常3個）。在庫月数は**最小ロット1回ぶん**で6か月以内
      - それ以外の項目（地雷）は全部 PASS。人の確認（カート・ゲート）の要否は GO と同じ扱い
    返り値：入るなら {"mid","worst","share","rec","months","why"}、入らなければ None。
    """
    e = s.get("econ")
    if not e or e.grade not in ("B", "C"):
        return None
    st = {g[0]: g[1] for g in gates}
    pf = st.get("採算")
    if e.grade == "C" and pf != "FAIL":
        return None   # 卸率の番兵（UNKNOWN）などは実績枠に入れない
    others = {k: v for k, v in st.items() if k not in ("採算", "取り分")}
    if not others or any(v != "PASS" for v in others.values()):
        return None
    mid = mid_net(e)
    if mid is None or e.net_per_unit is None:
        return None
    mid_use = min(mid, e.net_per_unit)
    # ⑥ 価格が平常か（2026-10-12 追加）。品薄の一時高値で黒字に見える棚はテストではなく賭け
    pn_ok, pn_why = price_is_normal(s)

    def blocked() -> None:
        # ①〜⑤ は満たすのに ⑥ だけで外れた行にだけ、理由を判定理由へ書く（他で落ちる行に書かない）
        s["_tr_block"] = f"実績枠 ⑥ に該当しない：{pn_why}"
        return None
    if "取り分" not in st:
        # 実売は PASS だが出品者の内訳が無く取り分が出ていない。採算は実績枠の線を満たすので
        # 落とさず「実績枠の候補・取り分待ち」（UNKNOWN）にする＝出品一覧を見れば決まる
        floor = max(int(s.get("min_lot") or 1), 10 if (gate and gate.get("書類")) else 1)
        best = s.get("_monthly") or s.get("monthlySold")   # 競合ゼロでも取り分は月販まで
        if best and floor / best > K.TRACK_MAX_MONTHS:
            return None   # 競合ゼロでも最小ロットが6か月で捌けない＝取り分を見ても入らない
        if mid_use >= K.TRACK_MIN_NET_YEN and e.grade == "C":
            if not pn_ok:
                return blocked()
            return {"pending": True, "mid": mid_use, "worst": e.worst_net_per_unit}
        return None
    if e.grade == "B" and st.get("取り分") == "PASS":
        return None   # B で取り分も足りていれば通常の GO
    info = s.get("_share") or {}
    share = info.get("share")
    if share is None:
        return None
    docs = bool(gate and gate.get("書類"))
    floor = max(int(s.get("min_lot") or 1), 10 if docs else 1)
    months = floor / share if share > 0 else None
    ok_, why = K.track_record(e.grade, mid_use, share, months)
    if not ok_:
        return None
    if not pn_ok:
        return blocked()
    return {"mid": mid_use, "worst": e.worst_net_per_unit, "share": share, "rec": floor,
            "months": months, "why": why + "・" + pn_why}


def apply_screen(s: dict, gates: list, gate: dict | None) -> bool:
    """人の実画面確認を gates に合流させる。人の確認が1つでもあれば True。"""
    a = s["asin"]
    if not SCREEN.has_any(a):
        return False
    c = SCREEN.cart.get(a)
    p = s.get("product") or {}
    if c and not c.holder and c.has_cart and s.get("_fresh"):
        sid = (p.get("stats") or {}).get("buyBoxSellerId")
        nm = (s.get("カート保持者") or "").rsplit("（", 1)[0] or None
        c = SC.supplement_holder(c, sid, nm, p.get("brand") or "", p.get("manufacturer") or "")
        SCREEN.cart[a] = c
    if c:
        st, why = SC.cart_gate(c)
        gates[:] = [g for g in gates if g[0] != "カート保持者"] + [("カート保持者", st, why, "")]
    ip = SCREEN.ip.get(a)
    if ip:
        gates[:] = [g for g in gates if g[0] != "知財"] + [
            ("知財", ip["知財のサイン"], f"{ip['根拠']}（{ip['確認者']} {ip['確認時刻']}）", "")]
    sea = SCREEN.season.get(a)
    if sea:
        gates[:] = [g for g in gates if g[0] != "季節の窓"] + [
            ("季節の窓", sea["季節の窓"], f"{sea['根拠']}（{sea['確認者']} {sea['確認時刻']}）", "")]
        s["_season_note"] = sea.get("追記") or ""
    bo = SC.backorder_only(a)
    if bo:
        gates.append(("取り寄せ価格", "UNKNOWN", bo, ""))
    sale_st = next((g[1] for g in gates if g[0] == "実売"), "UNKNOWN")
    st, why, monthly = SC.sales(a, s, sale_st, SCREEN)
    gates[:] = [g for g in gates if g[0] != "実売"] + [("実売", st, why, "")]
    s["_sales_why"], s["_monthly"] = why, monthly
    if st == "PASS" and monthly:
        e = s.get("econ")
        # 書類申請のゲート（ブランド出品許可）は請求書10点が要る＝最小ロット10点（§3.5 #3）
        docs = bool(gate and gate.get("書類"))
        st2, why2, info = SC.share_gate(a, monthly, e.qty if e else None, s.get("min_lot"), docs)
        s["_share"] = info
        gates.append(("取り分", st2, why2, ""))
    return True


def compose_netsea(s: dict, gate: dict | None) -> dict:
    comp = _compose_netsea(s, gate)
    # 終売の印は PASS（今だけ可）でも判定理由に残す（§3.5 #12・2026-10-12）
    mark = next((g[2] for g in comp["gates"] if g[0] == "終売" and g[1] == "PASS"), "")
    if mark:
        mark = mark[:400]
        comp["reason"] = comp["reason"][:1800 - len(mark) - 3] + " ／ " + mark
    c = SCREEN.cart.get(s["asin"])
    if c and "在庫あり" in (c.amazon_direct or "") and "アマゾン直販が在庫あり" not in comp["reason"]:
        # §3.5 #6（補助）：キーゾンのアマゾン直販が在庫あり＝本体が出品中。単独では落とさないが必ず書く
        comp["reason"] = ("🔴 #6 キーゾンのアマゾン直販が在庫あり（カズヨ実画面 "
                          f"{c.checked_at}）＝Amazon 本体が出品中でカートを取り返されるおそれ ／ "
                          + comp["reason"])[:1800]
    tag, info = classify_extra(s, comp["gates"], gate)
    comp["extra"] = (tag, info)
    if comp["verdict"] in K.GO_VERDICTS:
        comp["extra"] = (comp["verdict"], info)
        sn = s.get("_season_note")
        if sn:
            comp["reason"] = (comp["reason"] + " ／ " + sn)[:1800]
        return comp
    add = []
    if tag:
        add.append(f"【{tag}】{info['why']}")
    if add:
        comp["reason"] = (" ／ ".join(add) + " ／ " + comp["reason"])[:1800]
    return comp


def classify_extra(s: dict, gates: list, gate: dict | None) -> tuple[str, dict]:
    """GO・ゲート未確認／カートなし黒字 の別記。判定（GO/UNKNOWN/NO-GO）は変えない。

    （当初作った「推定月販で GO(テスト)」の別枠は、§3.3-16 改訂（9c673a11）でキーゾン再現値を
      実数同等に扱うことになったので撤去し、正規の GO 判定に統合した）
    カートなし黒字：いまカートが無い棚で、カートが立っていた最後の90日の BuyBox 中央値を売価に
      して採算 A/B。ほかに FAIL が無い（価格・採算は差し替えるので見ない）。
    """
    st = {}
    for g in gates:
        st[g[0]] = g[1]
    if gate:
        st["ゲート"] = "PASS" if gate["ゲート判定"] == "OK" else "FAIL"
    e = s.get("econ")
    # ── GO・ゲート未確認：ゲート以外が全部 PASS（実売はキーゾン or キーゾン再現値）で、
    #    出品可否（restrictions/approve）だけ人が見ていない行。ゲートを見れば GO/NO-GO が決まる
    others = {k: x for k, x in st.items() if k != "ゲート"}
    if (not gate and others and all(x == "PASS" for x in others.values())
            and e and e.grade in ("A", "B")):
        return "GO・ゲート未確認", {"why": "ゲート以外は全項目 PASS。出品可否を見れば GO/NO-GO が決まる",
                                 "grade": e.grade, "margin": e.net_margin_pct,
                                 "net": e.net_per_unit}
    # ── カートなし黒字
    cart = st.get("カート保持者")
    cart_why = next((g[2] for g in gates if g[0] == "カート保持者"), "")
    no_cart = cart == "UNKNOWN" and ("カートなし" in cart_why or "カートが立っていません" in cart_why)
    hard = {k: x for k, x in st.items() if k not in ("価格の動き", "採算", "カート保持者", "取り直し")}
    if no_cart and s.get("_fresh") and "FAIL" not in hard.values():
        pb = HC.past_buybox(s.get("product") or {}, s["_fresh"])
        if pb:
            r = econ_at(s, pb.median, pb.p25)
            if r and r[1].grade in ("A", "B"):
                e2, gr = r
                why = (f"出品すればカートを取れる見込み。基準売価＝{pb.text()}で等級 {gr.grade}"
                       f"（利益率 {gr.mid.get('利益率(%)')}%・手残り {gr.mid.get('手残り')}円）。"
                       "いまの出品は相場より高くカート非表示。発注前に出品一覧の最安と比べる")
                return "カートなし黒字", {"why": why, "sell": pb.median, "grade": gr.grade,
                                         "margin": gr.mid.get("利益率(%)"),
                                         "net": gr.mid.get("手残り")}
    return "", {}


def end_gate(s: dict, gates: list) -> None:
    """§3.5 #12 終売（2026-10-12 社長方針「今だけ、儲かるなら廃止決定品も仕入れて良い」）。

    法令品目・卸の廃番に印を付け、(a)仕入れ先の在庫 (b)在庫月数 ≦ 製造終了まで (c)価格が上昇〜横ばい
    の3条件で判定する。印の無い行にはゲートを足さない。Keepa の兆候（signs）はここでは見ない
    （台帳では product の鮮度がまちまちで、兆候は supplier_screen 側で見ている）。
    """
    r = s.get("row") or {}
    e = s.get("econ")
    lv = s.get("price")
    months = (s.get("_share") or {}).get("months") or (e.months_to_sell if e else None)
    stock = next((g[1] for g in gates if g[0] == "仕入れ"), None)
    ctx = DISC.now_only_from(stock, months, lv.verdict if lv else None, date.fromisoformat(TODAY))
    d = DISC.check(None, r.get("商品名"), "", "", None, now_only=ctx)
    if not d.marked:
        return
    st = {DISC.NO_GO: "FAIL", DISC.PASS: "PASS"}.get(d.verdict, "UNKNOWN")
    gates[:] = [g for g in gates if g[0] != "終売"] + [("終売", st, d.label(), "")]


def _compose_netsea(s: dict, gate: dict | None) -> dict:
    gates = reread_gates(s)
    s["_docs"] = bool(gate and gate.get("書類"))
    screened = apply_screen(s, gates, gate)
    end_gate(s, gates)
    if gate:
        if gate["ゲート判定"] == "NG":
            gates.append(("ゲート", "FAIL", gate["根拠"], ""))
        else:
            gates.append(("ゲート", "PASS", gate["根拠"], ""))
    pc = PRICE_CHECKS.get(s["asin"])
    if pc:
        # 2026-10-14：人の実画面で実勢価格が採算の前提（90日中央値）より安い行は NO-GO（#13）
        gates.append(("実勢価格", "FAIL",
                      f"{pc.get('根拠', '')}（{pc.get('確認者', '')} {pc.get('確認時刻', '')}）", ""))
    DIAG.append({"ASIN": s["asin"], "items": {n: st for n, st, *_ in gates},
                 "gate": (gate or {}).get("ゲート判定", ""), "cart_human": s["asin"] in SCREEN.cart,
                 "grade": getattr(s.get("econ"), "grade", "")})
    miss = [(n, st, w, nt) for n, st, w, nt in gates if st != "PASS"]
    lines_miss, fixes, never = [], [], []
    for n, st, w, nt in miss:
        lines_miss.append(f"{ITEM.get(n, n)} {st}：{clean(w, 70)}" + (f"（{nt}）" if nt else ""))
        if n == "ゲート":
            never.append("変えようがない：新品の申請経路が無い（§3.3-25）")
            continue
        if n == "採算" and st == "UNKNOWN" and any(
                x[0] in ("価格の動き", "セット数", "取り直し") and x[1] != "PASS" for x in gates):
            continue  # 売価・セット数の側で「こう変えれば」を書いている（重複させない）
        f, nv = fix_for(n, st, w, s)
        (never if nv else fixes).append(f)
    tr = track_record_frame(s, gates, gate)
    if tr and tr.get("pending"):
        note = K.track_record_note(tr["mid"], tr["worst"])
        gates = [(n, "UNKNOWN", f"実績枠の候補（{note}）。取り分が未計算＝出品一覧の内訳"
                                f"（FBA・即納の自己発送）を見て月1個以上なら GO（実績枠）", "")
                 if n == "採算" else (n, st, w, nt) for n, st, w, nt in gates]
        miss = [(n, st, w, nt) for n, st, w, nt in gates if st != "PASS"]
        lines_miss = [f"{ITEM.get(n, n)} {st}：{clean(w, 140)}" for n, st, w, nt in miss]
        fixes = ["出品一覧（/gp/offer-listing/<ASIN>/?f_new=true）でカート対象の出品者数を数えれば取り分が決まる"]
        never = []
        tr = None
    if not tr and not s.get("_tr_block"):
        # 実績枠の採算の線（中央値で手残り0円以上の C）を満たし、ほかに FAIL が無く UNKNOWN が残るだけの
        # 行は、NO-GO（採算 C）で落とさず UNKNOWN「実績枠の候補」に残す（UNKNOWN が解ければ実績枠に入りうる）
        e_ = s.get("econ")
        mid_ = min(mid_net(e_), e_.net_per_unit) if (e_ and mid_net(e_) is not None) else None
        fails = {n for n, st, *_ in gates if st == "FAIL"}
        sh_ = (s.get("_share") or {}).get("share")
        share_ok = "取り分" not in fails or (sh_ is not None and sh_ >= K.TRACK_MIN_SHARE)
        # 2026-10-14 秘書判断 A（§3.5 #18）：B 等級で #10 の取り分だけが月1〜3個のため落ちた行も
        # 実績枠の候補にする（C だけ残して B を落とす逆転を解消）
        b_share_only = bool(e_ and e_.grade == "B" and fails == {"取り分"})
        if (e_ and (e_.grade == "C" or b_share_only) and mid_ is not None
                and mid_ >= K.TRACK_MIN_NET_YEN
                and fails and fails <= {"採算", "取り分"} and share_ok
                and any(st == "UNKNOWN" for _, st, *_ in gates)):
            note = K.track_record_note(mid_, e_.worst_net_per_unit)
            gates = [(n, "UNKNOWN", f"実績枠の候補（{note}）。残りの UNKNOWN が解ければ実績枠に入りうる", "")
                     if n in ("採算", "取り分") and st == "FAIL" else (n, st, w, nt)
                     for n, st, w, nt in gates]
            miss = [(n, st, w, nt) for n, st, w, nt in gates if st != "PASS"]
            lines_miss = [f"{ITEM.get(n, n)} {st}：{clean(w, 140)}" for n, st, w, nt in miss]
    s["_tr"] = tr
    if tr:
        # 実績枠に入る行は、採算（C）と取り分（月1〜3個）を「実績枠で PASS」と読み替えて判定する
        note = K.track_record_note(tr["mid"], tr["worst"])
        gates = [(n, "PASS", w, note) if n in ("採算", "取り分") else (n, st, w, nt)
                 for n, st, w, nt in gates]
        miss = [(n, st, w, nt) for n, st, w, nt in gates if st != "PASS"]
    adj = [nt for n, st, w, nt in gates if st == "PASS" and nt and not (tr and n in ("採算", "取り分"))]
    sts = [st for _, st, _, _ in gates]
    machine = "NO-GO" if "FAIL" in sts else ("UNKNOWN" if "UNKNOWN" in sts else "GO")
    if s.get("pinned"):
        machine = "NO-GO"
    human = []
    if not (s.get("monthlySold")):
        human.append(HUMAN_ITEMS_BASE[0])
    human += HUMAN_ITEMS_BASE[1:]
    if not gate:
        human.append("#1-2 ゲート（restrictions/approve）")
    human.append("#4 仕入れ先の Amazon 出品可否")
    waiting = False
    if machine == "GO" and screened and SCREEN.cart.get(s["asin"]) and gate \
            and gate["ゲート判定"] == "OK":
        # 出品可否（restrictions/approve）を人が見ていない行は GO にしない（2026-10-11 追加）
        # 人がカートを見て、実売（キーゾン or 実画面の月販表示）と取り分まで通った行だけ GO
        verdict, waiting = ("GO" if not tr else K.TRACK_RECORD), True
        sh = s.get("_share") or {}
        reason = ("GO：§3.5 の機械項目＋人の確認がすべて PASS。"
                  f"#5 {next(g[2] for g in gates if g[0] == 'カート保持者')} ／ "
                  f"#9 {s.get('_sales_why')} ／ #10 {next((g[2] for g in gates if g[0] == '取り分'), '')} ／ "
                  f"#1-2 {(gate or {}).get('根拠', '')}（{(gate or {}).get('確認日', '')}） ／ "
                  f"推奨初回 {sh.get('rec')}点（発注点数・粗利の列は採算計算時の点数）。"
                  "発注直前に残す確認：#7 出品一覧の画面実数（いまは Keepa のカート対象数）・"
                  "#4 卸の商品ページの注意事項・#17 卸の在庫と価格の取り直し・"
                  "§3.5 21項目の記録（order-gate-guard）")
        dn = SC.doc_note(s["row"].get("商品名") or "")
        if dn:
            reason += " ／ " + dn
        if tr:
            reason = (f"GO（実績枠）＝{K.track_record_note(tr['mid'], tr['worst'])}。"
                      f"{tr['why']}。最小ロット {tr['rec']}点で1回だけ（卸で取引・販売実績を作り、"
                      "メーカー直取引の打診材料にする枠・§3.5 #18）。通常の GO とは別に数える ／ "
                      + reason.replace(f"推奨初回 {sh.get('rec')}点", f"推奨初回 {tr['rec']}点（実績枠＝最小ロット）"))
        o = s.get("_route")
        if o:
            reason = (f"SD 経由で即発注可（購入元＝{s['row'].get('購入元の名前') or ''}・SD 取引中・"
                      f"卸1点 {S._num(o['卸価格_税抜_1点']):,.0f}円税抜 {o.get('確認時刻', '')} 実画面）。"
                      "PSE 書類（適合性確認・自主検査記録）を発注前にヤザワへ取り寄せ。"
                      "SD の取引条件表で Amazon 出品可を発注前に確認（NETSEA 側は確認済み） ／ " + reason)
        if adj:
            reason += " ／ 読み替え：" + " ／ ".join(adj)
        return {"verdict": verdict, "reason": reason[:1800], "waiting": waiting,
                "gates": gates, "screened": screened}
    if machine == "GO":
        verdict, waiting = "UNKNOWN", True
        head = "機械判定は通過・実画面確認待ち"
        if tr:
            head = (f"実績枠の候補（{K.track_record_note(tr['mid'], tr['worst'])}・{tr['why']}）。"
                    "機械判定は通過・実画面確認待ち")
        reason = (f"{head}。" + (f"読み替え：{' ／ '.join(adj)}。" if adj else "")
                  + f"人が見る項目：{'・'.join(human)}")
    else:
        verdict = machine
        reason = "未達：" + " ／ ".join(lines_miss)
        if s.get("_tr_block"):
            lines_miss.append(s["_tr_block"])
            reason += " ／ " + s["_tr_block"]
        if never:
            reason += " ／【こう変えれば】" + never[0]
        else:
            reason += " ／【こう変えれば】" + " ／ ".join(dict.fromkeys(fixes))
        if machine == "UNKNOWN" and not never:
            only_human = all(n in ("実売", "カート保持者") for n, *_ in miss)
            if only_human:
                waiting = True
                reason = ("機械判定は通過・実画面確認待ち（残りは人が見れば決まる項目だけ）。"
                          + reason)
        if adj:
            reason += " ／ 読み替え：" + " ／ ".join(adj)
    if screened:
        reason = "（人の実画面確認を反映）" + reason
    return {"verdict": verdict, "reason": reason[:1800], "waiting": waiting,
            "gates": gates, "screened": screened}


#: 台帳の列「卸値の出どころ」（2026-10-12 社長指摘：SD で卸値が見えているのに想定のまま放置されていた）
WSRC = "卸値の出どころ"


def route_src(o: dict) -> str:
    """経路上書きファイルの1行 → 出どころ。国分はサトルの非ログイン商品ページ実測（法務判定50）。"""
    day = (o.get("確認時刻") or "")[:10]
    if o.get("卸サイト") == "国分ネット卸":
        return f"国分実額({day})"
    # 2026-10-12：SD の企業内検索は JAN が無いと別商品を返すことがある（シューズラック B005LIEBEC が
    # SD の別商品＝2段を拾っていた）。JAN を照合していない卸値は GO・実績枠の根拠にしない
    if (o.get("JAN照合") or "済").strip() != "済":
        return f"SD実画面(JAN未照合)({day})"
    if (o.get("JAN照合") or "").strip() == "済":
        return f"SD実画面(JAN照合済み)({day})"
    return f"SD実画面({day})"


def wholesale_src_of(s: dict) -> str:
    """採点に使った卸値の出どころ。SD の人の実画面＞NETSEA の実額（API/索引）＞未確認。"""
    o = s.get("_route")
    if o:
        return route_src(o)
    if not s.get("per_pt"):
        return "未確認"
    src = s.get("per_pt_src") or ""
    if src.startswith("索引") or src == "台帳":
        # 台帳＝旧プール（NETSEA Buyer API で取った卸1点）・索引＝NETSEA 索引。どちらも NETSEA の実額
        return f"NETSEA実額({s.get('_idx_day') or '2026-10-01'})"
    return "未確認"


def apply_wholesale_rule(cells: dict) -> dict:
    """卸値の出どころが想定・未確認の行は GO・GO（実績枠）にしない（#17 UNKNOWN）。"""
    if cells.get("判定") in K.GO_VERDICTS and not K.wholesale_source_ok(cells.get(WSRC, "")):
        cells = dict(cells)
        cells["判定"] = "UNKNOWN"
        cells["判定理由"] = (f"#17 卸値の出どころ UNKNOWN：{cells.get(WSRC) or '空欄'}＝卸値が実額でない。"
                          "【こう変えれば】卸サイトの実画面で卸値を読めば決まる ／ "
                          + (cells.get("判定理由") or ""))[:1800]
    return cells


RATIO_COL = "卸率(売価比)"


def ratio_cell(v) -> str | None:
    """卸率（%の数値）→ シートに書く文字列 "58.2%"。

    2026-10-14（T-20261014-001）：数値 58.2 を USER_ENTERED で書くと、%書式のセルでは
    「5820.00%」と表示されていた（99行→この日の台帳で352行）。"58.2%" の文字列で書けば
    シートは 0.582 として持ち、どの書式のセルでも 58.2% と表示される。"""
    if v is None or v == "":
        return None
    return f"{round(float(v), 1)}%"


def ratio_from_sheet(formatted: str, raw) -> str:
    """シートから読んだ卸率のセルを正しい "x.x%" に直す（表示ずれの修復・冪等）。

    - 表示に % が無い数値（例 "71"）… 値そのものが % の数（71%）
    - 表示に % がある … シートの生値が 0.582 なら 58.2%（正しい行）。生値が 10 より大きければ
      % の数をそのまま書いた**表示ずれ**（58.2 → 5820%）なので、生値を % の数として読む。
      境界を 10（表示1000%）に置くのは、単位ずれ疑いの行に本当に 624.8% があるため
      （2026-10-14 B0CGZPDLQJ。境界5では2回目に 6.2% へ壊した）。卸率10%未満の表示ずれは
      番兵（卸率が低すぎる行は UNKNOWN）に当たる帯で、取り違えても判定は動かない
    - 文字（「未確認」「算出不能…」・説明つき）はそのまま
    """
    f = (formatted or "").strip()
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return formatted
    if not f.endswith("%"):
        return ratio_cell(raw)
    return ratio_cell(raw if raw > 10 else raw * 100)


def netsea_cells(s: dict, gate: dict | None, comp: dict) -> dict:
    e, lv, r = s.get("econ"), s.get("price"), s["row"]
    has = bool(e and e.grade in ("A", "B", "C"))
    g = {}
    g["判定日"] = TODAY
    g["Amazon価格"] = (lv.sell_for_profit if lv and lv.sell_for_profit else "未確認")
    g["カートの販売元"] = s.get("カート保持者") or "未確認"
    if gate:
        g["ゲート種別"] = f"restrictions/approve（{gate['確認日']}）：{gate['根拠']}"
        g["ゲート可否"] = "可（新品）" if gate["ゲート判定"] == "OK" else "不可（新品の申請経路なし）"
    for col, val in (("卸率(売価比)", ratio_cell(e.cost_ratio_pct) if has else None),
                     ("発注点数", e.qty if has else None),
                     ("発注額(円・税込)", e.order_total if has else None),
                     ("1個粗利(円)", e.net_per_unit if has else None),
                     ("利益率(%)", e.net_margin_pct if has else None),
                     ("売り切る月数", (e.months_to_sell or "未確定（月販非表示）") if has else None),
                     ("半値処分時の損失(円)", e.half_disposal_loss if has else None)):
        g[col] = val if val is not None else "未確認"
    g["判定"] = comp["verdict"]
    g["判定理由"] = comp["reason"]
    g[WSRC] = wholesale_src_of(s)
    lg = LEGAL.get(s["asin"])
    if lg:
        if g["判定"] in K.GO_VERDICTS:
            g["判定"] = lg[0]
        g["判定理由"] = (lg[1] + " ／ " + g["判定理由"])[:1800]
    g["確認方法"] = ("Keepa 取得済みデータで再採点（価格90日中央値・ランク12ヶ月・buybox）"
                     f"{TODAY}" + (f"＋セラセン restrictions/approve {gate.get('確認日', '')}"
                                   if gate else ""))
    g["確認者"] = "タカシ（機械判定・実画面未確認）"
    if comp.get("screened"):
        g.update(screen_cells(s, gate))
    o = s.get("_route")
    if o:
        site = o.get("卸サイト") or "スーパーデリバリー"
        g["卸サイト"] = site
        g["購入先URL"] = o["購入先URL"]
        if site == "スーパーデリバリー":
            g["確認方法"] = (g["確認方法"] + f"＋SD 卸価格・在庫はカズヨが社長 Chrome で確認 {o.get('確認時刻', '')}"
                             "（NETSEA 停止中のため SD 経路で採算）")
        else:
            g["購入元の名前"] = o.get("仕入れ先") or g.get("購入元の名前") or "未確認"
            g["確認方法"] = (g["確認方法"] + f"＋{site} の値段・在庫は{o.get('確認者', '')}が"
                             f"非ログインの商品ページで確認 {o.get('確認時刻', '')}（法務判定50）")
    return g


def screen_cells(s: dict, gate: dict | None) -> dict:
    """人の実画面確認を書く列（NETSEA・SD 共通）。"""
    a, g, how, who = s["asin"], {}, [], []
    c = SCREEN.cart.get(a)
    if c:
        g["カートの販売元"] = (f"{c.holder}（カズヨ実画面 {c.checked_at}" +
                              (f"・{c.price}円" if c.price else "") +
                              (f"・過去1か月 {c.sold_label}" if c.sold_label else "") + "）")
        how.append(f"Chrome 実画面でカート保持者 {c.checked_at[:10]}")
        who.append("カート")
    if gate and gate.get("人"):
        how.append(f"セラセン restrictions/approve {gate['確認日']}")
        who.append("ゲート")
    k = SCREEN.keizon.get(a)
    if k:
        g["キーゾン 平均月販"] = (f"{k.avg:g}" if k.avg is not None else k.label)
        for i, col in enumerate(("キーゾン 過去1ヶ月", "キーゾン 過去2ヶ月", "キーゾン 過去3ヶ月")):
            g[col] = k.months[i] if len(k.months) > i else k.label
        if k.checked.startswith("Keepa"):
            how.append("キーゾン再現値（Keepa ランク改善3%超・§3.3-16）")
        else:
            how.append(f"キーゾン（ASIN 単位）{k.checked}")
            who.append("キーゾン")
    sh = s.get("_share") or {}
    # §3.5 #7：人が出品一覧で数えた値を Keepa より優先する（2026-10-15 GO 一覧の「セラー数」「本体」）
    if c and c.amazon_on_listing:
        g["Amazon本体の有無"] = f"{c.amazon_on_listing}（出品一覧・カズヨ実画面 {c.checked_at}）"
    if sh.get("src") and sh.get("human"):
        g["新品出品者数(画面実数)"] = (f"カート対象 FBA {sh['fba']}／即納の自己発送 {sh['fbm']}"
                                    f"（{sh['src']}）")
    elif c and c.offers_new is not None:
        g["新品出品者数(画面実数)"] = (f"新品{c.offers_new}件（出品一覧・カズヨ実画面 {c.checked_at}）"
                                    + (f"。カート対象の内訳は Keepa：FBA {sh['fba']}／自己発送 {sh['fbm']}"
                                       if sh.get("src") else ""))
    elif sh.get("src"):
        g["新品出品者数(画面実数)"] = (f"未確認（{sh['src']} カート対象：FBA {sh['fba']}／"
                                    f"自己発送 {sh['fbm']}）")
    if sh.get("months"):
        g["売り切る月数"] = (f"{sh['months']:.1f}（推奨初回 {sh['rec']}点÷取り分 "
                           f"{sh['share']:.1f}個/月）")
    if how:
        g["確認方法"] = "＋".join(how) + f"＋Keepa 取得済みデータで機械判定 {TODAY}"
        g["確認者"] = (f"カズヨ（実画面：{'・'.join(who)}）／タカシ（機械判定）" if who
                      else "タカシ（機械判定・キーゾン再現値）")
    return g


def netsea_new_row(s: dict, header: list[str], gate, comp) -> list:
    r = s["row"]
    base = {h: "未確認" for h in header}
    base.update({
        "チケットID": TICKET, "ASIN": s["asin"], "商品名": (r.get("商品名") or "")[:80],
        "ブランド": r.get("ブランド") or "未確認",
        "Amazon URL": r.get("AmazonURL") or f"https://www.amazon.co.jp/dp/{s['asin']}",
        "新品出品者数(画面実数)": f"未確認（Keepa {r.get('セラー数') or '—'}）",
        "Amazon本体の有無": r.get("Amazon本体の有無") or "未確認",
        "ゲート種別": r.get("ゲート種別") or "未確認",
        "購入元の名前": r.get("購入元の名前") or "未確認",
        "卸サイト": "NETSEA" if s.get("在庫") in ("在庫あり", "品切れ") else "未確認",
        "購入先URL": s.get("_supplier_url") or "未確認",
        "発注状況": "未発注",
    })
    base.update(netsea_cells(s, gate, comp))
    return [base[h] for h in header]


# ── SD 側 ────────────────────────────────────────────────────────────────

def load_sd_screen() -> list[dict]:
    """10/11 の実画面 SD 卸価格（SD品番キー）を SD_MANUAL と同じ形に直す。

    「卸単価(税抜)x最小点数」は段階価格（例 単価x1/単価x10/単価x200）。採算は**最小の口の単価**
    （最初の段＝一番高い単価）で計算する＝利益を多く見せない側。まとめ買いの段はメモに残す。
    ASIN は sd_candidates_private.csv の SD品番（5053100S1 等）の前方一致で引く。
    """
    if not SD_SCREEN.exists():
        return []
    cands = list(csv.DictReader((SDB / "sd_candidates_private.csv").open(encoding="utf-8-sig")))
    out = []
    for r in csv.DictReader(SD_SCREEN.open(encoding="utf-8-sig")):
        code = (r.get("SD品番") or "").strip()
        tiers = [t.split("x") for t in (r.get("卸単価(税抜)x最小点数") or "").split("/") if "x" in t]
        if not (code and tiers):
            continue
        first_price, first_lot = tiers[0]
        asins = sorted({c["ASIN"] for c in cands
                        if c.get("ASIN") and re.match(re.escape(code) + r"(S\d+)?$", c.get("SD品番", ""))})
        for a in asins:
            out.append({"ASIN": a, "SD品番": code, "購入先URL": r.get("購入先URL", ""),
                        "卸価格_税抜_1点": first_price, "入数・最小ロット": f"{first_lot}点〜（段階 {r.get('卸単価(税抜)x最小点数')}）",
                        "在庫": r.get("在庫", ""), "確認時刻": r.get("確認時刻", ""),
                        "メモ": f"{r.get('確認者', '')}・採算は最小口の単価で計算（まとめ買いの段は使わない＝保守側）"})
    return out


def load_sd_manual() -> dict[str, dict]:
    out: dict[str, list] = {}
    for r in load_sd_screen():          # 新しい方を先に置く（同じ SD 品番では先勝ち）
        out.setdefault(r["ASIN"], []).append(r)
    if not SD_MANUAL.exists():
        return out
    for r in csv.DictReader(SD_MANUAL.open(encoding="utf-8-sig")):
        a = (r.get("ASIN") or "").strip()
        if a:
            out.setdefault(a, []).append(r)
    return out


def sd_trading_status() -> dict[str, bool]:
    d = json.loads((WORK / "pipeline/sd_approval_requests.json").read_text())
    return {x["出展企業"]: bool(x.get("既に取引中")) for x in d}


def parse_sd_gates(txt: str) -> list[tuple[str, str, str]]:
    return [(m.group(1), m.group(2), m.group(3).strip())
            for m in re.finditer(r"\[([^:\]]+):([A-Z]+)\]([^｜]*)", txt or "")]


def num(x):
    """数値セル → float。「2/3」の分数も読む（#15 セット数・2026-10-11）。本体は S._num。"""
    return S._num(x)


def sd_rows(header: list[str]) -> tuple[list[list], list[dict]]:
    rows = list(csv.DictReader((SDB / "sd_candidates_private.csv").open(encoding="utf-8-sig")))
    manual = load_sd_manual()
    trading = sd_trading_status()
    order = {"要・卸値確認（Amazon側PASS）": 0, "UNKNOWN": 1, "NO-GO": 2}
    best: dict[str, dict] = {}
    for r in rows:
        k = r["ASIN"]
        ms = num(re.sub(r"[^0-9]", "", r.get("過去1ヶ月の販売数") or "")) or 0
        key = (order.get(r["判定"], 3), -ms)
        if any(r.get("SD品番", "").startswith((m.get("SD品番") or "#").strip())
               for m in manual.get(k, [])):
            key = (-1, 0)   # カズヨが卸価格を見た SD 品番の行を優先する
        if k not in best or key < best[k][0]:
            best[k] = (key, r)
    out, waiting = [], []
    for a, (_, r) in best.items():
        gates = parse_sd_gates(r["判定理由"])
        sup = re.sub(r"（スーパーデリバリー）", "", r["購入元の名前"])
        is_trading = trading.get(sup)
        price_rows = manual.get(a) or []
        mp = None
        for pr in price_rows:
            if r.get("SD品番", "").startswith((pr.get("SD品番") or "#").strip()):
                mp = pr
                break
        sell = num(r["販売価格(90日中央値)"])
        n = num(r["Amazon側のセット数(Amazon1個=卸何点か)"]) or None
        set_conf = r.get("セット数の確度")
        # 人の #15 確認（set_check_*.csv）が勝つ。高・中だけ使い、低・未確定は UNKNOWN（2026-10-11）
        hs = S.human_set_checks().get(a)
        if hs:
            hn = num(hs.get("Amazon1個＝卸◯点"))
            if hn and (hs.get("確度") or "").strip() in S.HUMAN_SET_OK:
                n, set_conf = hn, "確定"
            else:
                set_conf = "人の確認で未確定"
        tier = r.get("サイズ区分") or None
        gr = None
        split_note = ""
        def _grade(nn):
            # 売り切り月数は3か月の仮置き（SD 行は月販から月数を出していない）＝推定費目
            return fba_cost.grade(sell, num(mp["卸価格_税抜_1点"]) * 1.1 * nn, tier,
                                  keepa_pct=num(r["販売手数料率(%)"]),
                                  sell_worst=num(r["保守値(90日の下位25%)"]),
                                  estimated=("保管月数（3か月の仮置き）",))
        if mp and num(mp.get("卸価格_税抜_1点")) and sell and n and tier:
            if set_conf in ("確定", "単独"):
                gr = _grade(n)
            else:
                # セット数が未確定でも、候補の全部（1点・表記の n 点）で同じ等級なら
                # 結論は動かない。違えば UNKNOWN（単位ずれは真偽・§3.3-17）。
                g1, gn = _grade(1), _grade(n)
                if g1.grade == gn.grade == "C" or (g1.grade in ("A", "B") and gn.grade in ("A", "B")):
                    gr = gn
                    gr.reason += (f"（セット数は未確定だが、1点でも{S.set_label(n)}点でも等級 "
                                  f"{g1.grade}/{gn.grade} で結論は同じ）")
                else:
                    split_note = (f"#15 セット数 UNKNOWN（{set_conf}）：SD 卸1点 "
                                  f"{mp['卸価格_税抜_1点']}円なら、Amazon1個＝卸1点で等級 {g1.grade}"
                                  f"（{g1.mid.get('利益率(%)')}%）・{S.set_label(n)}点で等級 {gn.grade}"
                                  f"（{gn.mid.get('利益率(%)')}%）。どちらかで結論が変わる")
        miss, fixes, never = [], [], []
        sold_out = bool(mp and "SOLD OUT" in (mp.get("在庫") or "").upper()
                        and "あり" not in (mp.get("在庫") or ""))
        if sold_out:
            miss.append(f"#17 卸の在庫 FAIL：SD で SOLD OUT（{mp['確認時刻']} 実画面）")
            fixes.append("SD で再入荷すれば可（同一 JAN を NETSEA でも探す）")
        for nme, st, why in gates:
            if st == "PASS":
                continue
            if nme == "採算" and gr:
                continue  # 卸価格が入ったので下で引き直す
            miss.append(f"{ITEM.get(nme, nme)} {st}：{clean(why, 70)}")
            if nme == "取引条件":
                never.append("変えようがない：この卸は Amazon 出品を認めていない（取引条件表）")
            elif nme == "Amazonカタログ":
                never.append("変えようがない：JAN が Amazon のカタログに無い（新規出品なら別検討）")
            elif nme == "採算" and "原価0円でも" in why:
                fixes.append("売価が低すぎる。Amazon 側に多い個数のセット ASIN があればそちらで計算")
            elif nme == "採算":
                fixes.append(f"卸1点 {r.get('B等級に必要な卸値上限(1点・税抜)') or '—'}円（税抜）以下なら B・"
                             f"{r.get('A等級に必要な卸値上限(1点・税抜)') or '—'}円以下なら A")
            else:
                f, nv = fix_for(nme if nme != "季節" else "季節の窓", st, why, {"econ": None})
                (never if nv else fixes).append(f)
        sts = [st for nm_, st, _ in gates if not (nm_ == "採算" and gr)]
        if sold_out:
            sts.append("FAIL")
        tr_sd = bool(gr and gr.grade == "C" and (gr.mid.get("手残り") is not None)
                     and gr.mid["手残り"] >= K.TRACK_MIN_NET_YEN)
        if gr:
            if gr.grade == "C":
                # 実績枠（§3.5 #18）：中央値で手残り0円以上の C は落とさず、ほかが全部 PASS なら
                # 「実績枠の候補・実画面確認待ち」に上げる（取り分は人が出品一覧で見る）
                sts.append("TR" if tr_sd else "FAIL")
                miss.append(f"#18 採算等級 C：{clean(gr.reason, 90)}")
                cap = r.get("B等級に必要な卸値上限(1点・税抜)")
                fixes.append(f"卸1点 {cap}円（税抜）以下なら B（いま {mp['卸価格_税抜_1点']}円）")
                if tr_sd:
                    fixes.insert(0, "中央値の手残り0円以上＝実績枠の採算は満たす。ほかの地雷が全部 PASS・"
                                    "取り分 月1個以上なら GO（実績枠・最小ロット1回）")
            elif gr.grade == "UNKNOWN":
                sts.append("UNKNOWN")
                miss.append(f"#18 採算等級 UNKNOWN：{clean(gr.reason, 70)}")
        elif split_note:
            sts.append("UNKNOWN")
            miss.append(split_note)
            fixes.append("Amazon の商品画像・商品名と SD の入数を人が見て「Amazon1個＝卸何点」を決めれば確定")
        elif r["判定"].startswith("要・卸値確認"):
            sts.append("UNKNOWN")
            miss.append("#17 卸価格未確認（SDログインで要確認）")
            fixes.append(f"卸1点 {r.get('B等級に必要な卸値上限(1点・税抜)') or '—'}円（税抜）以下なら B・"
                         f"{r.get('A等級に必要な卸値上限(1点・税抜)') or '—'}円以下なら A")
        if is_trading is False:
            miss.append("#17 SD 取引申請が必要（取引企業リストに無い）")
            fixes.append("SD で取引申請すれば卸価格が見えて発注できる")
        machine = "NO-GO" if "FAIL" in sts else ("UNKNOWN" if "UNKNOWN" in sts else "GO")
        tr_note = (K.track_record_note(gr.mid["手残り"], gr.worst.get("手残り"))
                   if tr_sd and machine == "GO" else "")
        human = [HUMAN_ITEMS_BASE[0]] if not num(re.sub(r"[^0-9]", "", r["過去1ヶ月の販売数"] or "")) \
            else []
        human += HUMAN_ITEMS_BASE[1:] + ["#1-2 ゲート（restrictions/approve）"]
        wait = False
        if machine == "GO":
            verdict, wait = "UNKNOWN", True
            reason = (f"機械判定は通過・実画面確認待ち（SD 卸価格 {mp['確認時刻'] if mp else ''} 確認済み・"
                      f"等級 {gr.grade}）。人が見る項目：{'・'.join(human)}")
            if tr_note:
                reason = (f"実績枠の候補（{tr_note}）。" + reason
                          + "・#10 取り分（月1個以上・最小ロット1回で在庫6か月以内）"
                          + "・⑥ 1年の価格（現在価格と90日中央値が1年中央値の1.3倍以内か＝品薄の一時高値でないか）")
        else:
            verdict = machine
            reason = "未達：" + " ／ ".join(miss)
            reason += " ／【こう変えれば】" + (never[0] if never else " ／ ".join(dict.fromkeys(fixes)))
            if machine == "UNKNOWN" and not never:
                pending = [m for m in miss if not m.startswith(("#9", "#5"))]
                if all(("卸価格未確認" in m) or ("取引申請" in m) for m in pending):
                    reason = "Amazon側の機械判定は通過・卸価格待ち。" + reason
        cells = {h: "未確認" for h in header}
        has = gr and gr.grade in ("A", "B", "C")
        cells.update({
            "判定日": TODAY, "チケットID": TICKET, "ASIN": a, "商品名": r["商品名"][:80],
            "ブランド": "未確認", "Amazon URL": r["AmazonURL"],
            "Amazon価格": sell or "未確認",
            "新品出品者数(画面実数)": f"未確認（{clean(r['セラー数'], 40)}）",
            "Amazon本体の有無": clean(r["Amazon本体の有無"], 60),
            "カートの販売元": r["カートの販売元"] or "未確認",
            "ゲート種別": r.get("ゲート種別") or "未確認",
            "購入元の名前": r["購入元の名前"], "卸サイト": "スーパーデリバリー",
            "購入先URL": (mp or {}).get("購入先URL") or r.get("購入先URL") or "未確認",
            "卸率(売価比)": (ratio_cell(gr.mid["原価"] / sell * 100) if has else "未確認"),
            "1個粗利(円)": (gr.mid["手残り"] if has else "未確認"),
            "利益率(%)": (gr.mid["利益率(%)"] if has else "未確認"),
            "判定": verdict, "判定理由": reason[:1800],
            "確認方法": ("SD 商品ページ（非ログイン・9/30〜10/09）＋取引条件表＋Keepa（JAN 逆引き）"
                         + ("＋卸価格はカズヨが社長 Chrome で確認" if mp else "")),
            "確認者": "タカシ（機械判定・実画面未確認）"
                      + (SD_PRICE_ONLY_NOTE if mp else ""),
            "発注状況": "未発注",
            WSRC: (f"SD実画面({(mp.get('確認時刻') or '')[:10]})" if mp else "未確認"),
        })
        out.append([cells[h] for h in header])
        if wait or reason.startswith("Amazon側の機械判定は通過"):
            waiting.append({"ASIN": a, "商品名": r["商品名"][:40], "卸サイト": "SD",
                            "購入元": sup, "利益率": cells["利益率(%)"],
                            "手残り": cells["1個粗利(円)"], "月販": r["過去1ヶ月の販売数"],
                            "状態": "実画面確認待ち" if wait else "卸価格待ち",
                            "取引中": is_trading})
    return out, waiting


def sd_screen(cells: dict) -> dict:
    """SD 行に人の実画面確認（カート・ゲート）を合流させる。卸価格待ちの判定は動かさない。"""
    a = cells["ASIN"]
    # 2026-10-12：キーゾン再現値（機械・§3.3-16 で実数同等）だけの SD 行にも #9 を合流させる
    # （以前は人の確認がある行だけ。SD 行の #9「販売数もランクも取れていません」が解けなかった）
    if not SCREEN.has_any(a):
        return cells
    cells = dict(cells)
    gate = SCREEN.gate.get(a)
    pre, fail, never = [], False, ""
    c = SCREEN.cart.get(a)
    if c:
        st, why = SC.cart_gate(c)
        pre.append(f"#5 カートの販売元 {st}：{why}")
        if st == "FAIL":
            fail = True
            never = ("変えようがない：メーカー/ブランド本人がカート（§3.3-5）" if "メーカー" in why
                     else "変えようがない：Amazon 本体がカート（§3.3-1）")
    if gate and gate.get("人"):
        cells["ゲート種別"] = f"restrictions/approve（{gate['確認日']}）：{gate['根拠']}"
        cells["ゲート可否"] = "可（新品）" if gate["ゲート判定"] == "OK" else "不可（新品の申請経路なし）"
        pre.append(f"#1-2 出品許可 {'PASS' if gate['ゲート判定'] == 'OK' else 'FAIL'}：{gate['根拠']}")
        if gate["ゲート判定"] != "OK":
            fail, never = True, "変えようがない：新品の申請経路が無い（§3.3-25）"
    k = SCREEN.keizon.get(a)
    if k:
        # キーゾン（人の画面 or 再現値＝§3.3-16 で同等）で #9 を決める。機械の「ランク10万〜50万位
        # で UNKNOWN」より優先（2026-10-11：SD 行だけキーゾンを表示するだけで判定に使っていなかった）
        st9, why9, _ = SC.sales(a, {}, "UNKNOWN", SCREEN)
        pre.append(f"#9 実売 {st9}：{why9}")
        if st9 == "FAIL" and not fail:
            fail, never = True, "変えようがない：3か月の販売が実質ゼロ（§3.3-16）。季節品なら12か月ランクで再判定"
    elif c and c.sold_label:
        pre.append(f"#9 実画面 過去1か月 {c.sold_label}（キーゾン未確認）")
    cells.update({x: y for x, y in screen_cells({"asin": a}, gate).items()})
    label = "（人の実画面確認を反映）" if SCREEN.covers(a) else "（キーゾン再現値を反映）"
    head = label + " ／ ".join(pre) + "。"
    if fail:
        cells["判定"] = "NO-GO"
        cells["判定理由"] = (head + f"【こう変えれば】{never} ／ 機械判定："
                            + cells["判定理由"])[:1800]
    else:
        rest = cells["判定理由"]
        if k and st9 == "PASS":
            rest = drop_settled_sales(rest)
        cells["判定理由"] = (head + "残り：" + rest)[:1800]
    return cells


#: 機械の #9 UNKNOWN の文と、その「こう変えれば」。人のキーゾン（再現値含む）で #9 が PASS したら消す
_SALES_UNKNOWN_SEG = re.compile(r"#9 実売 UNKNOWN：.*?(?: ／ |$)")
_SALES_FIX_SEG = re.compile(r"キーゾンで3か月の実数を見れば決まる.*?(?: ／ |$)")


def drop_settled_sales(reason: str) -> str:
    """SD 行の機械の判定理由から、キーゾンで解けた #9 UNKNOWN とその「こう変えれば」を取り除く（2026-10-17）。

    sd_screen は機械の理由を「残り：」として後ろに足すので、キーゾンで #9 PASS になっても
    「未達：#9 実売 UNKNOWN」が残り、一歩手前の集計で #9 待ちに数えられていた（B0CGHV2SZ2 ほか）。
    文の区切りは「 ／ 」。消した後に区切りが末尾に残れば落とす。"""
    out = _SALES_FIX_SEG.sub("", _SALES_UNKNOWN_SEG.sub("", reason))
    out = re.sub(r"(?: ／ |【こう変えれば】|未達：)+$", "", out.rstrip())
    return out


# ── 本体 ────────────────────────────────────────────────────────────────

# 2026-10-07〜 NETSEA はランサムウェア被害で停止中（新規登録も停止）。NETSEA 経由の GO は
# 「買える」ではなく「復旧すれば買える」。判定は GO のまま残し、判定理由の先頭に書く（カズヨ 10/11 指示）。
# API は叩かない（このスクリプトは手元の索引だけを読む）。復旧したらこの定数を "" にする。
NETSEA_DOWN_NOTE = "【NETSEA 復旧待ち】10/7〜ランサムウェア被害で停止中（新規登録も停止）。"
#: 購入元の社名 → NETSEA を通さない直販窓口。社名の部分一致で引く
DIRECT_WINDOWS = {"カネイシ": "卸売ドットコム", "国分": "国分ネット卸"}
#: 2026-10-12 サトル：直販窓口の登録状態（仕入れ先台帳 49・2026-10-11）。無い社は「会員登録待ち」
WINDOW_STATUS = {"国分": "会員登録済み（10/11）"}
#: 2026-10-12 サトル：同じ会社が SD に出展し、取引中で卸値が見える社（仕入れ先台帳 49）。
#: SD の卸値を人が読めば（sd_queue_<日付>.csv → sd_route_override_*.csv）SD 経路に切り替わる
SD_SAME_COMPANY = ("ハリマ", "ヤザワ", "不二貿易")


def supply_note(site: str, supplier: str) -> str:
    """NETSEA 経由の行に付ける仕入れ経路の注記（NETSEA 以外・復旧後は空文字）。"""
    if not (NETSEA_DOWN_NOTE and (site or "").startswith("NETSEA")):
        return ""
    note = NETSEA_DOWN_NOTE
    for key, window in DIRECT_WINDOWS.items():
        if key in (supplier or ""):
            note += (f"購入元（{supplier}）は直販窓口（{window}）でも仕入れ可の見込み・"
                     f"{WINDOW_STATUS.get(key, '会員登録待ち')}。")
            break
    for key in SD_SAME_COMPANY:
        if key in (supplier or ""):
            note += ("同じ会社がスーパーデリバリーに出展・取引中（卸値が見える）＝SD の卸値を実画面で読めば"
                     "SD 経路に切り替わる（sd_queue）。")
            break
    return note


def with_supply_note(reason: str, site: str, supplier: str) -> str:
    """判定理由の先頭に注記を付ける。2回走らせても二重にならない（冪等）。"""
    note = supply_note(site, supplier)
    reason = reason or ""
    if not note or reason.startswith(NETSEA_DOWN_NOTE):
        return reason
    return note + reason


SD_PRICE_ONLY_NOTE = "／カズヨ（SD 卸価格のみ実画面）"   # 機械が付ける注記（is_human は凍結しない）


def is_human(row: dict) -> bool:
    """凍結する人の行か。実画面確認の証跡ファイル（screen_checks）に載っている ASIN は
    凍結せず、毎回その証跡から人の値を合流させて引き直す（2026-10-11）。"""
    who = row.get("確認者") or ""
    # 2026-10-17（秘書判断 A）：「／カズヨ（SD 卸価格のみ実画面）」は sd_rows が**機械で付ける**注記。
    # 人が見たのは卸値だけで判定は機械なので、凍結の根拠にしない（10/11 から26行が一度も引き直されず、
    # 人のセット数確認 B00H2E0JLW も効かなかった）。卸値の人の値は load_sd_manual 経由で引き続き勝つ
    who = who.replace(SD_PRICE_ONLY_NOTE, "")
    # 2026-10-12：秘書が台帳で直接下した最終判断（確認者にタカシ＝機械の名が無い行。例
    # 「カズヨ（社長方針で終売品を許容・…）」）は、証跡ファイルに載っていても凍結する。
    # 機械の合流で作る確認者は必ず「／タカシ（…）」を含むので区別できる（§3.3-16）。
    if "カズヨ" in who and "タカシ" not in who:
        return True
    if SCREEN.covers(row.get("ASIN", "")):
        return False
    return "カズヨ" in who


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore-from", type=Path, default=None,
                    help="取り直しで上書きされた行を、このスナップショット（before_*.json）から戻す（一度だけの修復）")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    import gspread
    from google.oauth2.service_account import Credentials
    gc = gspread.authorize(Credentials.from_service_account_file(
        str(CRED), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet("判定台帳")
    global SCREEN
    SCREEN = SC.load(sh, load_gate_checks())
    vals = ws.get_all_values()
    stamp = date.today().strftime("%Y%m%d") + "_" + os.environ.get("RUN_TAG", "run")
    (OUT / f"before_{stamp}.json").write_text(json.dumps(vals, ensure_ascii=False))
    header, body = vals[0], vals[1:]
    LEDGER_ASINS.update(x[header.index("ASIN")] for x in body if x)
    # 卸率の表示ずれ（58.2% が 5820.00%）を直すため、その列だけ生値でも読む（2026-10-14）
    ratio_fixed = 0
    if RATIO_COL in header:
        from gspread.utils import rowcol_to_a1
        ci = header.index(RATIO_COL) + 1
        a1 = rowcol_to_a1(2, ci)[:-1]
        raw_col = ws.get(f"{a1}2:{a1}{len(vals)}", value_render_option="UNFORMATTED_VALUE")
        ri = ci - 1
        for k, line in enumerate(body):
            raw = raw_col[k][0] if k < len(raw_col) and raw_col[k] else None
            if ri < len(line):
                fixed = ratio_from_sheet(line[ri], raw)
                if fixed != line[ri]:
                    a_, b_ = S._num(fixed), S._num(line[ri])
                    if a_ is None or b_ is None or abs(a_ - b_) > 0.05:
                        ratio_fixed += 1      # 値が変わった行だけ数える（"71"→"71.0%" は数えない）
                    line[ri] = fixed
    if WSRC not in header:          # 2026-10-12 列を末尾に1本足す（既存の列は動かさない）
        header = header + [WSRC]
    rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in body]

    def count(rs):
        return (dict(Counter(r["判定"] for r in rs)), dict(Counter(r["卸サイト"] for r in rs)))
    before = count(rows)
    prev_verdict = {r["ASIN"]: r["判定"] for r in rows}   # 新しく GO／NO-GO から外れた行の検出用
    # SCREEN を読んだ後でないと is_human が正しく働かないので、ここで復元する
    restored = restore_no_data_rows(rows, a.restore_from, header) if a.restore_from else []

    scored = score_netsea()
    gates = SCREEN.gate
    by_asin: dict[str, dict] = {}
    for s in scored:  # 同じ ASIN が2行あれば判定の良い方。ただしデータなしは必ず負ける（better）
        if better(s, by_asin.get(s["asin"])):
            by_asin[s["asin"]] = s

    waiting = []
    updated = skipped_human = 0
    kept_no_data: list[str] = []
    routed = set(load_sd_route())
    for r in rows:
        if r["卸サイト"] == "スーパーデリバリー" and r["ASIN"] not in routed:
            continue
        s = by_asin.get(r["ASIN"])
        if not s:
            continue
        if is_human(r):
            skipped_human += 1
            continue
        if keep_when_no_data(r, s):
            # 2026-10-12：別ルート（candidate_pipeline 等）が自前の Keepa データで GO にした行を、
            # 手元にデータが無いだけで UNKNOWN に落とさない（B0BP7M69YH）。データなしは判定の根拠にならない
            # 2026-10-14：GO だけでなく NO-GO・UNKNOWN の既存判定も同じく据え置く
            kept_no_data.append(r["ASIN"])
            continue
        comp = consistency_gate(s, compose_netsea(s, gates.get(r["ASIN"])))
        r.update(apply_wholesale_rule({**r, **netsea_cells(s, gates.get(r["ASIN"]), comp)}))
        record_extra(comp, r, s)
        updated += 1
        if comp["waiting"]:
            waiting.append(wait_row(s, r, "NETSEA"))

    # 2026-10-11：SD 行が既にある ASIN を「卸サイト=未確認」の NETSEA 行として二重に足していた
    # （旧プールに SD 由来の候補が混ざったため・250行）。台帳に既にある ASIN は経路を問わず足さない
    have_netsea = {r["ASIN"] for r in rows}
    appended = []
    for k, s in by_asin.items():
        if k in have_netsea:
            continue
        comp = consistency_gate(s, compose_netsea(s, gates.get(k)))
        line = netsea_new_row(s, header, gates.get(k), comp)
        appended.append(line)
        record_extra(comp, dict(zip(header, line)), s)
        if comp["waiting"]:
            waiting.append(wait_row(s, dict(zip(header, line)), "NETSEA"))

    # SD 行：既にある行も引き直す（人の行は触らない）。2026-10-11 まで既存の SD 行は
    # 飛ばしていたため、卸価格や規定が変わっても台帳に反映されなかった。
    sd_lines, sd_wait = sd_rows(header)
    ia = header.index("ASIN")
    sd_by_asin = {ln[ia]: ln for ln in sd_lines}
    have_sd = set()
    for r in rows:
        if r["卸サイト"] != "スーパーデリバリー" or r["ASIN"] in routed:
            continue
        have_sd.add(r["ASIN"])
        ln = sd_by_asin.get(r["ASIN"])
        if not ln:
            continue
        if is_human(r):
            skipped_human += 1
            continue
        r.update(apply_wholesale_rule(sd_screen(dict(zip(header, ln)))))
        updated += 1
    human_sd = {r["ASIN"] for r in rows
                if r["卸サイト"] == "スーパーデリバリー" and is_human(r)}
    sd_wait = [w for w in sd_wait if w["ASIN"] not in human_sd]
    sd_lines = [[sd_screen(dict(zip(header, ln)))[h] for h in header]
                for ln in sd_lines if ln[ia] not in have_sd and ln[ia] not in have_netsea]
    waiting += sd_wait

    # 卸値の出どころが空の行（人の凍結行・今回採点しなかった行）を、手元の証跡から埋める。
    # 人の行は判定を触らない（値の列を1本足すだけ）
    sd_seen = {a_: (m[0].get("確認時刻") or "")[:10] for a_, m in load_sd_manual().items() if m}
    route = load_sd_route()
    idx_urls = {(v.get("supplier_url") or "").strip() for v in json.loads(
        (WORK / "pipeline/netsea_jan_index.json").read_text())["jans"].values()} - {""}
    for r in rows:
        if r.get(WSRC):
            continue
        a_ = r["ASIN"]
        if a_ in route:
            r[WSRC] = route_src(route[a_])
        elif a_ in by_asin:
            r[WSRC] = wholesale_src_of(by_asin[a_])
        elif r["卸サイト"] == "スーパーデリバリー" and a_ in sd_seen:
            r[WSRC] = f"SD実画面({sd_seen[a_]})"
        elif (r.get("購入先URL") or "").strip() in idx_urls:
            r[WSRC] = "NETSEA実額(2026-10-01)"     # 購入先URL が NETSEA 索引の商品ページと完全一致
        else:
            r[WSRC] = "未確認"
    for r in rows:
        if not is_human(r):
            r.update(apply_wholesale_rule(r))
    appended = [[apply_wholesale_rule(dict(zip(header, x)))[h] for h in header] for x in appended]
    sd_lines = [[apply_wholesale_rule(dict(zip(header, x)))[h] for h in header] for x in sd_lines]
    final = [[r[h] for h in header] for r in rows] + appended + sd_lines
    # NETSEA 経由の GO に「復旧待ち」を付ける（人の行は触らない）
    i_site, i_sup = header.index("卸サイト"), header.index("購入元の名前")
    i_v, i_why = header.index("判定"), header.index("判定理由")
    for x in final:
        if x[i_v] in K.GO_VERDICTS and not is_human(dict(zip(header, x))):
            x[i_why] = with_supply_note(x[i_why], x[i_site], x[i_sup])
    for x in EXTRA["GO"] + EXTRA[K_TR]:
        x["判定理由"] = with_supply_note(x.get("判定理由"), x.get("卸サイト"), x.get("購入元の名前"))
    after = count([dict(zip(header, x)) for x in final])
    summary = {"前": before, "後": after, "更新": updated, "人の行(据え置き)": skipped_human,
               "データなしで据え置き": len(kept_no_data),
               "データなしで GO 据え置き": [x for x in kept_no_data if x in prev_verdict
                                         and prev_verdict[x] in K.GO_VERDICTS],
               "取り直しから復元": len(restored),
               "追記NETSEA": len(appended), "追記SD": len(sd_lines),
               "実画面確認待ち": Counter(w["状態"] for w in waiting),
               "実画面確認待ち_経路": Counter(w["卸サイト"] for w in waiting),
               "SD手入力卸価格": SD_MANUAL.exists(), "SD実画面卸価格(10/11)": len(load_sd_screen()),
               "SD経路へ切替": sorted(routed),
               "卸率の表示を直した行（読み込み時）": ratio_fixed}
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    with (OUT / "waiting_list.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["状態", "ASIN", "商品名", "卸サイト", "購入元", "月販",
                                          "利益率", "手残り", "取引中"], extrasaction="ignore")
        w.writeheader()
        for x in sorted(waiting, key=lambda x: (x["状態"], x["卸サイト"])):
            w.writerow(x)
    if WAIT_FULL:
        with (OUT / "waiting_netsea_full.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(WAIT_FULL[0].keys()), extrasaction="ignore")
            w.writeheader()
            w.writerows(WAIT_FULL)
    summary["別記"] = {k: len(v) for k, v in EXTRA.items()}
    print("別記", summary["別記"])
    allx = [x for v in EXTRA.values() for x in v]
    if allx:
        with (OUT / f"extra_go_{date.today().strftime('%Y%m%d')}.csv").open(
                "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(allx[0].keys()))
            w.writeheader()
            w.writerows(allx)
    (OUT / f"diag_items_{date.today().strftime('%Y%m%d')}.json").write_text(
        json.dumps(DIAG, ensure_ascii=False))
    # GO 一覧（社長が発注を決める表・CLAUDE.md §3.2 の必須列を含む）。購入先URL は agent_output にだけ置く
    go_cols = ["今回GOになった", "ASIN", "商品名", "卸サイト", "購入元の名前", "セット数(Amazon1個=卸何点)",
               "セット数の根拠", "利益率(%)", "手残り(円)", "3か月販売数",
               "取り分(個/月)", "カートの販売元", "出品可否", "推奨初回点数", "過去1ヶ月の販売数",
               "セラー数", "Amazon本体の有無", "Amazon URL", "購入先URL", "等級", "判定理由"]
    for x in EXTRA["GO"]:
        x["今回GOになった"] = "Y" if prev_verdict.get(x["ASIN"]) != "GO" else ""
    EXTRA["GO"].sort(key=lambda x: x["今回GOになった"] != "Y")
    with (OUT / f"go_list_{date.today().strftime('%Y%m%d')}.csv").open(
            "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=go_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(EXTRA["GO"])
    # GO（実績枠）一覧（通常 GO と別ファイル・同じ必須列＋中央値/悲観値の手残り）
    for x in EXTRA[K_TR]:
        x["今回GOになった"] = "Y" if prev_verdict.get(x["ASIN"]) != K_TR else ""
    with (OUT / f"track_record_list_{date.today().strftime('%Y%m%d')}.csv").open(
            "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=go_cols[:8] + ["中央値の手残り(円)", "悲観値の手残り(円)"]
                           + go_cols[8:], extrasaction="ignore")
        w.writeheader()
        w.writerows(EXTRA[K_TR])
    # GO の手前で、残りがゲート（#1-2）とカート（#5）の未確認だけの行
    # ＝カズヨが実画面で見れば決まる行。毎回作り直す（0件でもファイルを書く）。
    # 2026-10-11：旧版は「前回 NO-GO だった行」だけを拾っていた。前回から UNKNOWN のまま
    # ゲート・カート待ちで止まっている行が出てこなかったので、判定が GO でない行すべてに広げた。
    # 「今回NO-GOから外れた」列で、新しく入ってきた行と前からの行を分ける
    ia, ij, ir = header.index("ASIN"), header.index("判定"), header.index("判定理由")
    queue = []
    for x in final:
        if x[ij] in (*K.GO_VERDICTS, "NO-GO") or is_human(dict(zip(header, x))):
            continue
        items = set(re.findall(r"(#[\d-]+)[^：／]*? (?:FAIL|UNKNOWN)", x[ir]))
        if items and items <= {"#1-2", "#5"}:
            new_in = "Y" if prev_verdict.get(x[ia]) == "NO-GO" else ""
            queue.append("\t".join([x[ia], "+".join(sorted(items)), new_in, x[i_site], x[i_sup],
                                    supply_note(x[i_site], x[i_sup])]))
    (OUT / f"gate_cart_queue_{date.today().strftime('%Y%m%d')}.txt").write_text(
        "# GO の手前で、ゲート(#1-2)・カート(#5)の未確認だけで止まっている ASIN"
        f"（ledger_refresh {TODAY}）{len(queue)}件\n"
        "# ASIN\t未確認の項目\t今回NO-GOから外れた\t卸サイト\t購入元\t仕入れ経路の注記\n"
        + "".join(q + "\n" for q in queue))
    summary["ゲート・カート待ち"] = len(queue)
    summary["新しくGO"] = sum(1 for x in EXTRA["GO"] if x.get("今回GOになった") == "Y")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    if a.dry_run:
        (OUT / "after_dryrun.json").write_text(json.dumps([header] + final, ensure_ascii=False))
        return 0

    need = len(final) + 1 - ws.row_count
    if need > 0:
        ws.add_rows(need + 10)
    if len(header) > ws.col_count:
        ws.add_cols(len(header) - ws.col_count)
    ws.update(range_name="A1", values=[header], value_input_option="RAW")
    ws.update(range_name="A2", values=final, value_input_option="USER_ENTERED")
    (OUT / f"after_{stamp}.json").write_text(json.dumps([header] + final, ensure_ascii=False))
    print(f"書き込み {len(final)}行")
    return 0


def record_extra(comp: dict, cells: dict, s: dict) -> None:
    tag, info = comp.get("extra") or ("", {})
    if cells.get("判定") in K.GO_VERDICTS:
        tag = cells["判定"]
    if tag in K.GO_VERDICTS and (cells.get("判定") not in K.GO_VERDICTS
                                 or not K.wholesale_source_ok(cells.get(WSRC, ""))):
        return   # 卸値が実額でない行は GO 一覧に載せない（apply_wholesale_rule と同じ線）
    if not tag:
        return
    e = s.get("econ")
    ms = s.get("monthlySold")
    c = SCREEN.cart.get(s["asin"])
    EXTRA[tag].append({
        "区分": tag, "ASIN": s["asin"], "商品名": (cells.get("商品名") or "")[:60],
        "過去1ヶ月の販売数": (f"{ms}個（Keepa）" if ms else
                         (f"{c.sold_label}（実画面）" if c and c.sold_label else "表示なし（月50個未満）")),
        "3か月販売数": (SCREEN.keizon[s["asin"]].label if s["asin"] in SCREEN.keizon else ""),
        "取り分(個/月)": (round((s.get("_share") or {}).get("share"), 1)
                       if (s.get("_share") or {}).get("share") else ""),
        "セラー数": cells.get("新品出品者数(画面実数)"),
        "Amazon本体の有無": cells.get("Amazon本体の有無"),
        "カートの販売元": cells.get("カートの販売元"),
        "Amazon URL": cells.get("Amazon URL"),
        "購入元の名前": cells.get("購入元の名前"),
        "購入先URL": cells.get("購入先URL"),
        "売価": info.get("sell") or cells.get("Amazon価格"),
        "等級": info.get("grade") or (e.grade if e else ""),
        "利益率(%)": info.get("margin") or cells.get("利益率(%)"),
        "手残り(円)": info.get("net") or cells.get("1個粗利(円)"),
        "卸サイト": cells.get("卸サイト"),
        "出品可否": cells.get("ゲート可否"),
        "推奨初回点数": ((s.get("_tr") or {}).get("rec") or (s.get("_share") or {}).get("rec")
                    or cells.get("発注点数")),
        "中央値の手残り(円)": (s.get("_tr") or {}).get("mid", ""),
        "悲観値の手残り(円)": ((s.get("_tr") or {}).get("worst", "") if s.get("_tr") else ""),
        "セット数(Amazon1個=卸何点)": (S.set_label(s["n_set"]) if s.get("n_set") else "未確定"),
        "セット数の根拠": f"{s.get('セット数の確度') or ''}" + (
            "（人の確認）" if str(s.get("セット数の確度")) == "確定" and
            s["asin"] in S.human_set_checks() else ""),
        "判定": cells.get("判定"), "判定理由": (cells.get("判定理由") or "")[:400],
    })


def wait_row(s: dict, cells: dict, route: str) -> dict:
    return {"ASIN": s["asin"], "商品名": (s["row"].get("商品名") or "")[:40], "卸サイト": route,
            "購入元": s["row"].get("購入元の名前"), "利益率": cells.get("利益率(%)"),
            "手残り": cells.get("1個粗利(円)"),
            "月販": (f"{s['monthlySold']}個" if s.get("monthlySold") else "表示なし"),
            "状態": "実画面確認待ち"}


if __name__ == "__main__":
    raise SystemExit(main())
