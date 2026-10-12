#!/usr/bin/env python3
"""商品判定台帳の UNKNOWN を、理由（§3.5 の項目番号）別のキューに分けて段階的に潰す。

2026-10-12 タカシ（T-20260920-003）。社長方針：
  「アンノウンは放置しない。ただし一気にやると崩壊しそうなので、段階的に改善する仕組みにして」

仕組み（§3.3-34「上限を置かない・順番で散らす」）
  - UNKNOWN 行を、まだ決まっていない項目で段（キュー）に振り分ける。1行が複数の段に入ってよい
  - 1回の `run` で、機械の段を ①→②→③ の順に**1バッチずつ**回し、台帳に書き戻す（ラウンドロビン）
    バッチは「1回分の量」であって上限ではない。キューが残っていれば次の回は続きから始まる
  - 人が要る段（④実画面・⑤人手）は、機械では回さずファイルに出す（秘書が在席時に回す）

段（安くて機械で潰せる順）
  ① s1_sales   #9 実売       Keepa ランク履歴（csv[3]）→ キーゾン再現式（§3.3-16）で3か月販売数
  ② s2_price   #13/#13-14 価格・#10 内訳  Keepa 取り直し（stats=90&history=1&buybox=1）
  ③ s3_season  #11 季節      12か月ランク履歴を取り直す（無い／古い行だけ）
  ④ browser    #5 カート・#1-2 ゲート・#7 内訳・キーゾン表示なし・取り直しても価格が無い行
               → needs_browser_<日付>.txt（社長 Chrome の iframe 確認。秘書が在席時に回す）
  ⑤ human      #17 卸値・#15 セット数・#4 仕入れ先の出品可否 → needs_human_<日付>.txt
  （#18 採算・#12 終売・#10 取り分は他の項目が決まれば自動で決まる＝「依存」。キューは持たない）

守ること
  - **卸サイト（SD）には一切アクセスしない**（§3.3-14）。Keepa だけを使う
  - Keepa は**バッチ単位でトークン残高を確かめ**、足りなければ待たずに止めて次回に回す
    （一気に流して他チケットのトークンを潰さない・nightly.sh と同じキーを共有している）
  - 人の確認で凍結されている行（確認者がカズヨだけ）は機械の段に入れない（§3.3-16）
  - 取得した生データ・キュー・状態はすべて agent_output（Git 除外）に置く。コードは値を持たない

使い方
  python3 unknown_stages.py plan                 # キューの件数を数えるだけ（Keepa もシートも書かない）
  python3 unknown_stages.py run                  # ①②③を1バッチずつ回し、台帳に書き戻す
  python3 unknown_stages.py run --batch 100 --rotations 2   # 1回で2巡（夜間・トークンに余裕があるとき）
  python3 unknown_stages.py run --no-write       # Keepa は取るが台帳には書かない（確認用・dry-run）
  python3 unknown_stages.py status               # state.json の要約

状態：agent_output/T-20260920-003/unknown_queue/state.json（処理済み・次の段・各段の残り・履歴）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
QDIR = WORK / "unknown_queue"
STATE = QDIR / "state.json"
LEDGER = WORK / "ledger20261010"
#: ①の結果。screen_checks.load_kz_estimate() が kz_estimate_*.csv を名前順に読み、後のファイルが勝つ。
#: "kz_estimate_stages.csv" は日付つきのファイルより後ろに並ぶ＝最新の取り直しが勝つ
KZ_OUT = LEDGER / "kz_estimate_stages.csv"
BUDGET = WORK / "pipeline/daily_token_budget.json"
SHEET_ID = "1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I"
CRED = Path.home() / ".config/claude-session-sheets/credentials.json"
sys.path.insert(0, str(HERE))

#: Keepa の生データ（後ろほど新しい扱い。同じ ASIN は fetched が新しい方を使う）
RAW_FILES = [WORK / "refetch20261004/raw.jsonl",
             WORK / "buylist20261009/resolve_raw.jsonl",
             WORK / "buylist20261009/buybox_raw.jsonl",
             LEDGER / "keepa_kz_hist_20261011.jsonl",
             LEDGER / "keepa_unknown_20261011.jsonl",
             WORK / "kz_entry/keepa_full.jsonl"]

MACHINE_STAGES = ("s1_sales", "s2_price", "s3_season")
STAGE_LABEL = {"s1_sales": "①#9 実売（キーゾン再現式）", "s2_price": "②#13-14 価格（Keepa 取り直し）",
               "s3_season": "③#11 季節（12か月ランク）", "browser": "④実画面（社長 Chrome）",
               "human": "⑤人手（卸値・セット数・出品可否）"}
#: 1バッチの既定。**上限ではない**：残りは次の回に続きから回る（§3.3-34）
BATCH = 100
#: 1 ASIN あたりの Keepa トークン（product 1 ＋ buybox 2。history・stats は追加なし）
COST = 3
#: 同じ ASIN を同じ段でもう一度機械にかけるまでの日数。データが変わらないのに毎晩取り直さないため
REVISIT_DAYS = {"s1_sales": 7, "s2_price": 7, "s3_season": 30}
#: 「取り直したのに価格が無い」と判断する鮮度（日）。これより新しいデータで価格が無ければ人の段へ
FRESH_DAYS = 3

ITEM_RE = re.compile(r"(#[\d-]+)[^：／]*? (FAIL|UNKNOWN|PASS)")


def today() -> str:
    return date.today().isoformat()


# ── 台帳を読んでキューに分ける ────────────────────────────────────────────

def read_sheet() -> tuple[list[str], list[dict]]:
    import gspread
    from google.oauth2.service_account import Credentials
    gc = gspread.authorize(Credentials.from_service_account_file(
        str(CRED), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    vals = gc.open_by_key(SHEET_ID).worksheet("判定台帳").get_all_values()
    h = vals[0]
    return h, [dict(zip(h, r + [""] * (len(h) - len(r)))) for r in vals[1:]]


def outstanding(reason: str) -> set[str]:
    """判定理由から「まだ決まっていない項目」を取り出す。
    人の確認の合流で同じ項目が PASS と書かれていれば（例「#9 実売 PASS：キーゾン…」）決まった扱い。"""
    bad, good = set(), set()
    for item, st in ITEM_RE.findall(reason or ""):
        (good if st == "PASS" else bad).add(item)
    return bad - good


def frozen(row: dict) -> bool:
    """人の最終判断で凍結されている行（ledger_refresh.is_human の凍結側と同じ線）。"""
    who = row.get("確認者") or ""
    return "カズヨ" in who and "タカシ" not in who


def classify(row: dict) -> dict[str, list[str]]:
    """{段: [その段で決める項目]}。1行が複数の段に入る。"""
    r = row.get("判定理由") or ""
    items = outstanding(r)
    out: dict[str, list[str]] = {}

    def add(stage, item):
        out.setdefault(stage, []).append(item)

    machine_ok = not frozen(row)
    for it in sorted(items):
        if it == "#9":
            if "キーゾン表示なし" in r:
                add("browser", "#9 キーゾン画面の見直し（人の「表示なし」は機械で上書きしない）")
            elif machine_ok:
                add("s1_sales", "#9")
            else:
                add("browser", "#9 キーゾン")
        elif it in ("#13", "#13-14", "#14"):
            if "取り寄せ型" in r:
                add("browser", "#13 即納の売価（取り寄せ型の値付けしかない）")
            elif machine_ok:
                add("s2_price", it)
            else:
                add("browser", "#13 実画面の売価")
        elif it == "#11":
            add("s3_season" if machine_ok else "human", "#11")
        elif it == "#10":
            if "内訳が取れない" in r and machine_ok:
                add("s2_price", "#10 内訳（Keepa buybox）")
            else:
                add("browser", "#7 出品一覧の内訳（取り分）")
        elif it in ("#5", "#1-2", "#7"):
            add("browser", it)
        elif it in ("#17", "#15", "#4", "#16", "#3"):
            add("human", it)
        # #18 #12 は他の項目で決まる（依存）
    if not items and "実画面確認待ち" in r:
        add("browser", "人が見る項目（判定理由の末尾）")
    if "GO・ゲート未確認" in r:
        add("browser", "#1-2")
    return out


def build_queues(rows: list[dict]) -> dict[str, list[dict]]:
    q: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("判定") != "UNKNOWN":
            continue
        n_items = len(outstanding(row.get("判定理由") or ""))
        for stage, items in classify(row).items():
            q.setdefault(stage, []).append({
                "ASIN": row["ASIN"], "items": items, "n_open": n_items,
                "site": row.get("卸サイト") or "", "supplier": row.get("購入元の名前") or "",
                "name": (row.get("商品名") or "")[:40]})
    # 「安くて機械で潰せる順」＝残りの項目が少ない行から（同数なら ASIN 順で決定的に）
    for v in q.values():
        v.sort(key=lambda x: (x["n_open"], x["ASIN"]))
    return q


# ── 状態 ────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"next_stage": MACHINE_STAGES[0], "done": {s: {} for s in MACHINE_STAGES}, "history": []}


def save_state(st: dict) -> None:
    QDIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def pending(stage: str, queue: list[dict], st: dict) -> list[dict]:
    """REVISIT_DAYS 以内に同じ段で処理した ASIN は除く（データが変わらないのに取り直さない）。"""
    done = st["done"].setdefault(stage, {})
    lim = REVISIT_DAYS[stage]
    out = []
    for x in queue:
        d = done.get(x["ASIN"])
        if d and (date.today() - date.fromisoformat(d)).days < lim:
            continue
        out.append(x)
    return out


# ── Keepa ───────────────────────────────────────────────────────────────

def raw_files() -> list[Path]:
    return RAW_FILES + sorted(QDIR.glob("keepa_stage_*.jsonl"))


def load_products() -> dict[str, tuple[dict, int]]:
    """{ASIN: (product, fetched)}。同じ ASIN は fetched が新しい方。"""
    out: dict[str, tuple[dict, int]] = {}
    for f in raw_files():
        if not f.exists():
            continue
        for line in f.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            a, p = o.get("asin"), o.get("product")
            if not (a and p):
                continue
            t = o.get("fetched") or 0
            if a not in out or t >= out[a][1]:
                out[a] = (p, t)
    return out


def keepa_tokens() -> int:
    import keepa_unknown_fetch as KF
    return int(KF.get(f"https://api.keepa.com/token?key={KF.key()}").get("tokensLeft", 0))


def fetch(asins: list[str], reserve: int) -> tuple[int, str]:
    """Keepa から取り直して keepa_stage_<日付>.jsonl に追記。(取れた件数, 止まった理由)。
    トークンが「バッチの必要量＋予備」に足りなければ**待たずに止める**（次回に続き）。"""
    import keepa_unknown_fetch as KF
    if not asins:
        return 0, ""
    k = KF.key()
    left = keepa_tokens()
    need = COST * len(asins)
    if left < need + reserve:
        return 0, f"Keepa トークン不足（残 {left}・必要 {need}＋予備 {reserve}）＝次回に続き"
    out = QDIR / f"keepa_stage_{date.today().strftime('%Y%m%d')}.jsonl"
    got = 0
    used = 0
    for i in range(0, len(asins), 50):
        part = asins[i:i + 50]
        q = urllib.parse.urlencode({"key": k, "domain": 5, "asin": ",".join(part),
                                    "stats": 90, "history": 1, "buybox": 1})
        d = KF.get(f"https://api.keepa.com/product?{q}")
        now = int(time.time())
        used += int(d.get("tokensConsumed") or 0)
        with out.open("a") as f:
            for p in d.get("products") or []:
                f.write(json.dumps({"asin": p["asin"], "fetched": now, "product": p},
                                   ensure_ascii=False) + "\n")
                got += 1
    _budget(used)
    return got, ""


def _budget(used: int) -> None:
    """nightly.sh と同じ日次の消費台帳に足す（チケット横断でトークンを数えるため）。"""
    try:
        d = json.loads(BUDGET.read_text()) if BUDGET.exists() else {}
        d[today()] = int(d.get(today(), 0)) + used
        BUDGET.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:
        pass


def age_days(fetched: int) -> float:
    return (time.time() - fetched) / 86400 if fetched else 9999.0


# ── 段の処理 ────────────────────────────────────────────────────────────

def write_kz(asins: list[str], prods: dict) -> int:
    """①：キーゾン再現式（kz_entry_harvest.kz_months＝kz_estimate.py と同じ式）で3か月販売数を出し、
    KZ_OUT に ASIN 単位で上書き保存する（同じ ASIN は今回の値が勝つ＝冪等）。"""
    from kz_entry_harvest import kz_months, T0
    cols = ["ASIN", "推定m1", "推定m2", "推定m3", "3か月平均", "式", "一致度", "観測回数m1/m2/m3", "注意",
            "取得日"]
    have = {}
    if KZ_OUT.exists():
        have = {r["ASIN"]: r for r in csv.DictReader(KZ_OUT.open(encoding="utf-8-sig"))}
    n = 0
    for a in asins:
        if a not in prods:
            continue
        p, fetched = prods[a]
        c3 = (p.get("csv") or [None] * 4)[3] if len(p.get("csv") or []) > 3 else None
        if not c3 or not fetched:
            continue
        m, obs = kz_months(c3, fetched // 60 - T0)
        note = []
        if p.get("parentAsin"):
            note.append("バリエーション子＝family合計")
        if any(o < 10 for o in obs):
            note.append("観測少(" + "/".join(map(str, obs)) + ")")
        if max(m) > 13:
            note.append("月13個超は未検算・過小の可能性")
        have[a] = {"ASIN": a, "推定m1": m[0], "推定m2": m[1], "推定m3": m[2],
                   "3か月平均": round(sum(m) / 3, 1),
                   "式": "30日窓ごとにランクが直前観測より3%超改善した回数",
                   "一致度": "キーゾン25ASIN×3か月で完全一致69/75・最大誤差1個",
                   "観測回数m1/m2/m3": "/".join(map(str, obs)), "注意": "・".join(note),
                   "取得日": datetime.fromtimestamp(fetched).date().isoformat()}
        n += 1
    with KZ_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(sorted(have.values(), key=lambda r: r["ASIN"]))
    return n


def run_stage(stage: str, batch: list[dict], prods: dict, reserve: int, dry: bool) -> dict:
    asins = [x["ASIN"] for x in batch]
    rec = {"stage": stage, "batch": len(asins), "fetched": 0, "to_browser": [], "stop": ""}
    if not asins:
        return rec
    if stage == "s1_sales":
        # ランク履歴が無い・古い（7日超）ものだけ取り直す
        need = [a for a in asins if a not in prods or age_days(prods[a][1]) > 7
                or len((prods[a][0].get("csv") or [])) < 4 or not prods[a][0]["csv"][3]]
    elif stage == "s2_price":
        need = [a for a in asins if a not in prods or age_days(prods[a][1]) > FRESH_DAYS]
        # 新しいデータがあるのに価格が決まらない行は、取り直しても変わらない＝人の画面へ
        rec["to_browser"] = [a for a in asins if a not in need]
    else:  # s3_season
        need = [a for a in asins if a not in prods or age_days(prods[a][1]) > 30
                or len((prods[a][0].get("csv") or [])) < 4 or not prods[a][0]["csv"][3]]
        rec["to_browser"] = [a for a in asins if a not in need]
    if need and not dry:
        got, stop = fetch(need, reserve)
        rec["fetched"], rec["stop"] = got, stop
        if stop:
            return rec
        prods.update({k: v for k, v in load_products().items() if k in need})
    if stage == "s1_sales":
        rec["kz_written"] = write_kz(asins, prods)
    return rec


def refresh_ledger(write: bool) -> dict:
    """ledger_refresh.py で台帳を引き直す（取り直したデータ・再現値を合流させて書き戻す）。"""
    env = dict(os.environ, RUN_TAG=f"stages_{datetime.now().strftime('%H%M%S')}")
    cmd = [sys.executable, str(HERE / "ledger_refresh.py")] + ([] if write else ["--dry-run"])
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ledger_refresh が失敗しました：{p.stderr[-800:]}")
    return json.loads((LEDGER / "summary.json").read_text())


def write_human_files(q: dict[str, list[dict]], extra_browser: list[str]) -> tuple[Path, Path]:
    d = date.today().strftime("%Y%m%d")
    pb, ph = QDIR / f"needs_browser_{d}.txt", QDIR / f"needs_human_{d}.txt"
    bro = {x["ASIN"]: x for x in q.get("browser", [])}
    for a in extra_browser:
        bro.setdefault(a, {"ASIN": a, "items": ["#13 実画面の売価（Keepa を取り直しても価格が無い）"],
                           "n_open": 0, "site": "", "supplier": "", "name": ""})
    head = ("# 社長 Chrome の実画面で確かめる ASIN（unknown_stages ④・秘書が在席時に回す）\n"
            "# 見方：#5 カートの販売元／#1-2 restrictions/approve?asin=<ASIN>&itemcondition=New／"
            "#7 /gp/offer-listing/<ASIN>/?f_new=true／#9 キーゾン（iframe）\n"
            "# ASIN\t見る項目\t卸サイト\t購入元\t商品名\n")
    pb.write_text(head + "".join(
        f"{x['ASIN']}\t{' '.join(x['items'])}\t{x['site']}\t{x['supplier']}\t{x['name']}\n"
        for x in sorted(bro.values(), key=lambda x: (x["n_open"], x["ASIN"]))))
    hum = q.get("human", [])
    ph.write_text("# 人手で決める ASIN（unknown_stages ⑤）。#17 卸値＝SD 承認待ち・国分ネット卸など／"
                  "#15 セット数＝卸と Amazon の両画面／#4 取引条件表／#11 は12か月ランクの目視\n"
                  "# ASIN\t項目\t卸サイト\t購入元\t商品名\n" + "".join(
                      f"{x['ASIN']}\t{' '.join(x['items'])}\t{x['site']}\t{x['supplier']}\t{x['name']}\n"
                      for x in hum))
    return pb, ph


def counts(q: dict[str, list[dict]]) -> dict[str, int]:
    return {STAGE_LABEL[s]: len(q.get(s, [])) for s in (*MACHINE_STAGES, "browser", "human")}


def cmd_plan(a) -> int:
    _, rows = read_sheet()
    q = build_queues(rows)
    st = load_state()
    print(f"UNKNOWN {sum(1 for r in rows if r.get('判定') == 'UNKNOWN')}行（台帳 {len(rows)}行）")
    for s in (*MACHINE_STAGES, "browser", "human"):
        extra = ""
        if s in MACHINE_STAGES:
            extra = f"（いま機械にかけられる {len(pending(s, q.get(s, []), st))}件）"
        print(f"  {STAGE_LABEL[s]}: {len(q.get(s, []))}件{extra}")
    print(f"次に回す段：{STAGE_LABEL[st['next_stage']]}")
    return 0


def cmd_status(a) -> int:
    st = load_state()
    print(json.dumps({"next_stage": st["next_stage"],
                      "処理済み": {k: len(v) for k, v in st["done"].items()},
                      "直近の履歴": st["history"][-5:]}, ensure_ascii=False, indent=1))
    return 0


def cmd_run(a) -> int:
    QDIR.mkdir(parents=True, exist_ok=True)
    st = load_state()
    _, rows = read_sheet()
    before = {r["ASIN"]: (r["判定"], outstanding(r.get("判定理由") or "")) for r in rows}
    q = build_queues(rows)
    q_before = counts(q)
    prods = load_products()
    run_log = {"at": datetime.now().isoformat(timespec="seconds"), "rotations": [], "batch": a.batch}
    to_browser: list[str] = []
    order = list(MACHINE_STAGES)
    i0 = order.index(st.get("next_stage", order[0]))
    stopped = ""
    touched: dict[str, set[str]] = {}
    # s0：台帳の外の SD 候補で、秘書が SD 実画面の卸値を sd_route_override に入れたのに Keepa の
    # 商品データが無い ASIN（ledger_refresh が off_ledger_needs_keepa.txt に書く）を先に取る
    off = QDIR / "off_ledger_needs_keepa.txt"
    if off.exists() and not a.no_fetch:
        need0 = [x.strip() for x in off.read_text().split() if x.strip()]
        need0 = [x for x in need0 if x not in prods][: a.batch]
        if need0:
            got0, stop0 = fetch(need0, a.reserve)
            run_log["rotations"].append({"stage": "s0_offledger", "batch": len(need0),
                                         "fetched": got0, "stop": stop0})
            if stop0:
                stopped = stop0
    for rot in range(0 if stopped else a.rotations):
        for j in range(len(order)):
            stage = order[(i0 + j) % len(order)]
            todo = pending(stage, q.get(stage, []), st)[: a.batch]
            rec = run_stage(stage, todo, prods, a.reserve, a.no_fetch)
            rec["remaining_after"] = max(0, len(pending(stage, q.get(stage, []), st)) - len(todo))
            if rec["stop"]:
                stopped = rec["stop"]
                st["next_stage"] = stage           # 次回はこの段のこのバッチから
                run_log["rotations"].append(rec)
                break
            for x in todo:
                st["done"].setdefault(stage, {})[x["ASIN"]] = today()
                touched.setdefault(x["ASIN"], set()).add(stage)
            to_browser += rec.get("to_browser", [])
            run_log["rotations"].append({k: v for k, v in rec.items() if k != "to_browser"}
                                        | {"to_browser": len(rec.get("to_browser", []))})
            st["next_stage"] = order[(i0 + j + 1) % len(order)]
        if stopped:
            break
    save_state(st)
    summ = refresh_ledger(write=not a.no_write)
    if a.no_write:
        h, *body = json.loads((LEDGER / "after_dryrun.json").read_text())
        rows2 = [dict(zip(h, r)) for r in body]
    else:
        _, rows2 = read_sheet()
    q2 = build_queues(rows2)
    after = {r["ASIN"]: (r["判定"], outstanding(r.get("判定理由") or "")) for r in rows2}
    resolved = Counter()
    left_unknown = Counter()
    for asin, stages in touched.items():
        b, aft = before.get(asin), after.get(asin)
        if not (b and aft):
            continue
        if b[0] == "UNKNOWN" and aft[0] != "UNKNOWN":
            left_unknown[aft[0]] += 1
        for s in stages:
            key = {"s1_sales": "#9", "s2_price": "#13", "s3_season": "#11"}[s]
            had = any(i.startswith(key) for i in b[1])
            still = any(i.startswith(key) for i in aft[1])
            if had and not still:
                resolved[s] += 1
    pb, ph = write_human_files(q2, to_browser)
    run_log.update({"stop": stopped, "queues_before": q_before, "queues_after": counts(q2),
                    "resolved_items": dict(resolved), "unknown_left_to": dict(left_unknown),
                    "verdicts_before": summ.get("前", [{}])[0], "verdicts_after": summ.get("後", [{}])[0],
                    "needs_browser": str(pb), "needs_human": str(ph),
                    "next_stage": st["next_stage"], "wrote_sheet": not a.no_write})
    st["history"].append(run_log)
    save_state(st)
    print(json.dumps(run_log, ensure_ascii=False, indent=1, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="判定台帳の UNKNOWN を段階的に潰す（§3.3-34 ラウンドロビン）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(fn=cmd_plan)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    r = sub.add_parser("run")
    r.add_argument("--batch", type=int, default=BATCH, help="1段あたり1回分の量（上限ではない）")
    r.add_argument("--rotations", type=int, default=1, help="①→②→③を何巡するか（既定1）")
    r.add_argument("--reserve", type=int, default=300,
                   help="Keepa トークンをこれだけ残す（他の夜間処理の分）")
    r.add_argument("--no-write", action="store_true", help="台帳に書かない（dry-run）")
    r.add_argument("--no-fetch", action="store_true", help="Keepa を叩かない（手元のデータだけ）")
    r.set_defaults(fn=cmd_run)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
