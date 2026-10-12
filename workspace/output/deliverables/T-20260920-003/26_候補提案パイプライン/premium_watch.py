#!/usr/bin/env python3
"""品薄・終売プレミアムの定点監視と「紙の上の仕入れ」（2026-10-12 タカシ・T-20260920-003）

社長指示（2026-10-12）
  「品薄・終売で価格が上がった商品を仕入れる方法も可能性の一つとして知見に入れたい。
   定点監視をし、物販手法として取り入れられるか判断して」
→ **発注はしない。**監視開始日に最小ロットを買ったとみなし、実際に買っていたら儲かったかを
  毎日の Keepa の実データで測る。8週間（〜2026-12-07）で採用／条件つき採用／不採用を判断する材料にする。

使い方（夜間タスク amazon-buppan-nightly-sourcing から毎日1回）
  python3 premium_watch.py run            # 監視リスト更新 → Keepa 取得 → history.csv → pnl.csv
  python3 premium_watch.py run --no-fetch # Keepa を叩かず、今日の取得済み生データだけで計算し直す
  python3 premium_watch.py weekly         # 週次サマリー weekly_<日付>.md と判定3指標
  python3 premium_watch.py list           # 監視リストだけ作り直す（Keepa 0トークン）

置き場（すべて agent_output＝Git 除外。卸値・原価を含むので PUBLIC リポに出さない）
  agent_output/T-20260920-003/premium_watch/
    watchlist.csv      監視リスト（追記のみ。外すのは定期棚卸しで人が行う＝§3.3-34）
    history.csv        日次の観測（(日付, ASIN) で一意。同じ日に2回走らせても行は増えず値も同じ）
    raw/keepa_<日付>.jsonl  その日の Keepa 生データ（同じ日の2回目はここを読み、Keepa を叩かない）
    pnl.csv            仮想損益（毎回 history.csv から全部計算し直す＝漂わない）
    weekly_<日付>.md   週次サマリー

監視リストに入る条件（どれか1つ・上限なし）
  ① 固定：DN ライティング FLR910（B00Q64QHII / B008FIN7NQ）＝社長が名指しした起点
  ② 終売フラグ（§3.5 #12）：ledger20261010/discontinued_flags_20261011.csv の 終売フラグ=NO-GO
     （分類ルール・仕入れ先の記載で終売と判った行。UNKNOWN＝Keepa の兆候だけの行は②では入れない）
  ③ 価格の跳ね：（現在価格 または 90日中央値）が 1年中央値の 1.3倍超（TRACK_MAX_PRICE_RATIO と同じ線）
     判定に使う価格は手元の最新 Keepa 生データ（Keepa 0トークン）。台帳の全行に当てる

仮想仕入れの式（利益計算は1円もごまかさない。推定はすべて列に出す）
  - 原価＝Amazon 1個あたり原価（税込）。出所の優先順：
      SD ヤザワ一覧（yazawa_sd_listprice_*.csv の型番が商品名に一致）→ 卸1点(税抜)×1.1
      → 台帳の「発注額(円・税込)÷発注点数」
      どちらも無い行は **原価未確認**＝損益を計算しない（監視だけ続ける）
  - ロット＝台帳の発注点数（無ければ 10点＝出品許可書類の要件）
  - 販売開始＝監視開始日＋21日（卸→おりおん→FBA 納品の2〜4週間の中央）
  - 1日に売れる数＝その日の kz 再現月販 m1 ÷ (カート対象 FBA＋自己発送＋1) ÷ 30（§3.5 #10 の取り分）
    カートを Amazon 本体が持っている日は 0個（値下げしても取れない＝§3.3-1）
  - 1個の入金＝fba_cost._scenario（販売手数料・750円の崖・FBA 配送代行・保管・納品送料・おりおん費用）
    を原価0で回した手残り。売価はその日のカート価格（無ければ新品最安）
  - 悲観＝売価がずっと「監視開始時の1年中央値」に戻った場合（同じ数量・同じ費用）
  - 悲観2＝売価が Amazon 外の最安（offamazon_prices.csv・手入力・週1）まで戻った場合。
    Amazon 価格がこれの1.3倍を超える行は「公正価格ポリシーでカートを失う恐れ」と印を付ける
    （2026-10-12 サトル：FLR910 は終売ではなく DN が2027年12月まで生産。Amazon外最安 6,065円 に対し Amazon 9,130円＝+51%）

判定の3指標（weekly に出す。秘書が 2026-12-07 に使う）
  ① 仮想損益（評価込み）が黒字の ASIN が、原価の判っている監視対象の過半か
  ② 悲観シナリオで全数を売り切ったときの損が、1ロットあたり 1万円以内か（最大損の ASIN で見る）
  ③ 高値（カート価格＞1年中央値×1.3）が 4週以上続いた ASIN の割合
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fba_cost as F          # noqa: E402  原価モデルの唯一の正
import price_history as PH    # noqa: E402  価格履歴の読み方の唯一の正

REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR") or HERE.parents[4])
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
OUT = WORK / "premium_watch"
RAW_DIR = OUT / "raw"
WATCHLIST = OUT / "watchlist.csv"
HISTORY = OUT / "history.csv"
PNL = OUT / "pnl.csv"
#: Amazon 外の最安値（手入力・週1。秘書が価格.com の型番検索で入れる）。列：ASIN,型番,Amazon外最安(税込),店,確認日,確認者,備考（送料込みか等）
OFF_AMAZON = OUT / "offamazon_prices.csv"
OFF_COLS = ["ASIN", "型番", "Amazon外最安(税込)", "店", "確認日", "確認者", "備考"]
FAIR_PRICE_RATIO = 1.3      # Amazon価格 ÷ Amazon外最安 がこれを超えたら「公正価格ポリシーでカートを失う恐れ」
DISCONTINUED = WORK / "ledger20261010/discontinued_flags_20261011.csv"
YAZAWA_GLOB = "sd_buylist20261009/yazawa_sd_listprice_*.csv"
#: 価格判定に使う手元の Keepa 生データ（後ろほど新しい＝後勝ち）。screen_checks と同じ並び＋本監視の取得
CACHED_RAW = [WORK / "refetch20261004/raw.jsonl",
              WORK / "buylist20261009/resolve_raw.jsonl",
              WORK / "buylist20261009/buybox_raw.jsonl",
              WORK / "ledger20261010/keepa_kz_hist_20261011.jsonl",
              WORK / "ledger20261010/keepa_unknown_20261011.jsonl",
              WORK / "kz_entry/keepa_full.jsonl"]

FIXED = {"B00Q64QHII": "社長名指し（FLR910・1年前3,100〜3,800円→9,130円）",
         "B008FIN7NQ": "社長名指し（FLR910・1年前3,100〜3,800円→9,130円）"}
PRICE_JUMP = 1.3            # consistency.TRACK_MAX_PRICE_RATIO と同じ線（品薄の一時高値）
LEAD_DAYS = 21              # 仮想仕入れ → 販売開始
DEFAULT_LOT = 10            # 出品許可の書類要件（profit.MIN_QTY_FOR_UNGATING）
WATCH_END = date(2026, 12, 7)
MAX_LOSS_PER_LOT = 10_000   # 判定②
HIGH_STREAK_DAYS = 28       # 判定③
KEEPA_T0 = 21564000         # Keepa 分 = unix分 − これ
KEEPA_BATCH = 100
KEEPA_COST_PER_ASIN = 3     # stats＋history 1 ＋ buybox 2（keepa_unknown_fetch と同じ実測）
KEEPA_MAX_WAIT_SEC = 20 * 60
KZ_THR = 0.03               # kz_estimate.py と同じ式（キーゾン25ASIN×3か月で検算済み）

WATCH_COLS = ["ASIN", "商品名", "追加日", "追加理由", "購入元の名前",
              "Amazon1個あたり原価(税込)", "原価の出所", "最小ロット(Amazon個)",
              "1年中央値(追加時)", "追加時の倍率(現在/1年中央値)"]
HIST_COLS = ["日付", "ASIN", "Keepa取得時刻", "カート価格", "カートは本体", "カート販売元ID",
             "新品最安", "カート対象FBA", "カート対象自己発送", "本体価格", "本体在庫あり",
             "売れ筋ランク", "kz_m1", "kz_m2", "kz_m3", "90日中央値", "1年中央値", "1年の観測日数",
             "FBA配送代行(Keepa)", "販売手数料率(Keepa)", "高値の連続日数(履歴遡り)"]
PNL_COLS = ["ASIN", "商品名", "追加理由", "監視開始", "販売開始", "観測日数", "原価(税込)", "ロット",
            "最新カート価格", "1年中央値", "倍率", "取り分(個/月)", "売れた個数", "残在庫",
            "入金累計", "現金損益", "評価込み損益", "悲観損益(全数を1年中央値で)",
            "Amazon外最安", "Amazon外の確認日", "倍率(Amazon/Amazon外)", "公正価格の恐れ",
            "悲観損益(全数をAmazon外最安で)",
            "高値の継続日数(監視中)", "高値の連続日数(履歴遡り)", "注意"]


# ── 小道具 ──────────────────────────────────────────────────────────────

def _num(v) -> float | None:
    if v is None:
        return None
    s = re.sub(r"[,円\s%]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def _read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(p: Path, cols: list[str], rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(p)


def _fetched_dt(fetched_unix: int) -> datetime:
    return datetime.fromtimestamp(int(fetched_unix), timezone.utc)


def _day0(dt: datetime) -> datetime:
    """price_history と同じく「その日の0時（UTC）」に揃える＝同じ日の2回目で窓が動かない。"""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


# ── Keepa から読む値（すべて純関数） ─────────────────────────────────────

def kz_months(product: dict, fetched_unix: int) -> tuple[list[int], list[int]]:
    """キーゾン「過去1/2/3ヶ月の販売数」の再現。式は ledger20261010/kz_estimate.py と同一
    （CLAUDE.md §3.3-16 の 2026-10-11 更新）。ランクが直前観測より3%超よくなった回数を30日窓で数える。"""
    now = int(fetched_unix) // 60 - KEEPA_T0
    c = (product.get("csv") or [None] * 4)[3] or []
    ps = [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
    out, obs = [], []
    for k in (1, 2, 3):
        lo, hi = now - 30 * k * 1440, now - 30 * (k - 1) * 1440
        n = o = 0
        prev = None
        for t, r in ps:
            if r <= 0:
                prev = None
                continue
            if lo <= t < hi:
                o += 1
                if prev is not None and (prev - r) / prev > KZ_THR:
                    n += 1
            prev = r
        out.append(n)
        obs.append(o)
    return out, obs


def daily_grid(points: list, days: int, now: datetime) -> dict[int, int]:
    """price_history.daily_samples と同じ持ち越し規則で、{何日前: 値} を返す（日付を揃えるため）。"""
    if not points:
        return {}
    pts = sorted(points, key=lambda p: p[0])
    end = pts[-1][0] + timedelta(days=PH.MAX_CARRY_DAYS)
    out: dict[int, int] = {}
    j, cur = 0, None
    for d in range(days, -1, -1):
        at = now - timedelta(days=d)
        while j < len(pts) and pts[j][0] <= at:
            cur = pts[j][1]
            j += 1
        if cur is None or at < pts[0][0] or at > end:
            continue
        out[d] = cur
    return out


def price_levels(product: dict, fetched_unix: int) -> dict:
    """平常価格（1年）・現在価格・90日中央値と、末尾から数えた「平常×1.3 超」の連続日数。

    🔴 **平常価格＝その日に買えた最安（カート・新品最安・Amazon 本体）の1年中央値。**
    price_history.median365 をそのまま使うと、品薄の棚ほど「高値の期間しか点が無い系列」
    （カートが高値の時期だけ立った等）が選ばれ、平常が高く出る。2026-10-12、B008FIN7NQ で
    カート系列の1年中央値が 8,448円（点のある85日がほぼ高値期）、同じ日の本体価格は 3,539円だった。
    悲観シナリオ（＝平常に戻る）を甘くしないため、日ごとの最安で揃える。
    """
    now = _day0(_fetched_dt(fetched_unix))
    lv = PH.from_product(product, now=now)
    csvs = product.get("csv") or []
    grids = [daily_grid(PH.parse_series(csvs, i), 365, now)
             for i in (PH.CSV_BUYBOX, PH.CSV_NEW, PH.CSV_AMAZON)]
    days = sorted(set().union(*grids), reverse=True)          # 古い → 新しい
    low = [min(g[d] for g in grids if d in g) for d in days]
    normal = int(median(low)) if len(low) >= PH.MIN_DAYS_COVERED else None
    streak = None
    if normal:
        streak = 0
        for v in reversed(low):
            if v > normal * PRICE_JUMP:
                streak += 1
            else:
                break
    return {"current": lv.current, "median90": lv.median90, "median365": normal,
            "days365": len(low), "source": lv.source, "streak": streak}


def observe(asin: str, product: dict, fetched_unix: int, day: date) -> dict:
    """Keepa 1件 → history.csv の1行。日付は生データのファイルの日（取得が0時をまたいでも同じ日に入る）。"""
    s = product.get("stats") or {}
    cur = s.get("current") or []
    bb = product.get("buyBoxEligibleOfferCounts") or []
    m, _obs = kz_months(product, fetched_unix)
    lv = price_levels(product, fetched_unix)
    amazon_price = cur[0] if len(cur) > 0 else -1
    new_low = cur[1] if len(cur) > 1 else -1
    bbp = s.get("buyBoxPrice")
    return {
        "日付": day.isoformat(),
        "ASIN": asin,
        "Keepa取得時刻": _fetched_dt(fetched_unix).astimezone().isoformat(timespec="seconds"),
        "カート価格": bbp if bbp and bbp > 0 else "",
        "カートは本体": "1" if s.get("buyBoxIsAmazon") else "0",
        "カート販売元ID": s.get("buyBoxSellerId") or "",
        "新品最安": new_low if new_low and new_low > 0 else "",
        "カート対象FBA": max(bb[0], 0) if len(bb) >= 2 else "",
        "カート対象自己発送": max(bb[1], 0) if len(bb) >= 2 else "",
        "本体価格": amazon_price if amazon_price and amazon_price > 0 else "",
        "本体在庫あり": "1" if amazon_price and amazon_price > 0 else "0",
        "売れ筋ランク": cur[3] if len(cur) > 3 and cur[3] and cur[3] > 0 else "",
        "kz_m1": m[0], "kz_m2": m[1], "kz_m3": m[2],
        "90日中央値": lv["median90"] or "", "1年中央値": lv["median365"] or "", "1年の観測日数": lv["days365"],
        "FBA配送代行(Keepa)": (product.get("fbaFees") or {}).get("pickAndPackFee") or "",
        "販売手数料率(Keepa)": product.get("referralFeePercentage") or "",
        "高値の連続日数(履歴遡り)": "" if lv["streak"] is None else lv["streak"],
    }


def off_amazon_prices() -> dict[str, dict]:
    """ASIN → 一番新しい確認日の行。無ければ空（ファイルはヘッダだけ作っておく＝秘書が足す場所を明示）。"""
    if not OFF_AMAZON.exists():
        _write_csv(OFF_AMAZON, OFF_COLS, [])
    out: dict[str, dict] = {}
    for r in _read_csv(OFF_AMAZON):
        a = (r.get("ASIN") or "").strip()
        if a and _num(r.get("Amazon外最安(税込)")) and (a not in out or r.get("確認日", "") >= out[a].get("確認日", "")):
            out[a] = r
    return out


# ── 監視リスト ──────────────────────────────────────────────────────────

def _iter_raw(paths: list[Path], want: set[str] | None = None):
    for p in paths:
        if not p.exists():
            continue
        with p.open() as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                a = d.get("asin")
                if a and (want is None or a in want) and d.get("product") and d.get("fetched"):
                    yield a, d


def latest_cached(want: set[str]) -> dict[str, dict]:
    """手元の Keepa 生データから ASIN ごとに一番新しい1件（Keepa 0トークン）。"""
    paths = CACHED_RAW + sorted((WORK / "unknown_queue").glob("keepa_stage_*.jsonl")) \
        + sorted(RAW_DIR.glob("keepa_*.jsonl"))
    best: dict[str, dict] = {}
    for a, d in _iter_raw(paths, want):
        if a not in best or d["fetched"] >= best[a]["fetched"]:
            best[a] = d
    return best


def yazawa_costs() -> list[tuple[str, float]]:
    """SD ヤザワ一覧（秘書が人手で更新）→ [(型番, 卸1点 税抜)]。長い型番から当てる。"""
    files = sorted(WORK.glob(YAZAWA_GLOB))
    if not files:
        return []
    rows = _read_csv(files[-1])
    out = [(r["型番"].strip().upper(), _num(r.get("SD卸単価(税抜・1点・一覧の最安)")))
           for r in rows if r.get("型番")]
    return sorted([o for o in out if o[1]], key=lambda o: -len(o[0]))


def _norm_model(s: str) -> str:
    return re.sub(r"[\s\-‐ー－]", "", (s or "").upper())


def cost_for(title: str, ledger_row: dict | None, yz: list[tuple[str, float]]) -> tuple[float | None, str]:
    """Amazon 1個あたり原価（税込）と出所。"""
    t = _norm_model(title)
    for model, excl in yz:
        if _norm_model(model) and _norm_model(model) in t:
            return float(round(excl * F.TAX)), f"SD ヤザワ一覧 {model} 卸1点 税抜×1.1"
    if ledger_row:
        amt, qty = _num(ledger_row.get("発注額(円・税込)")), _num(ledger_row.get("発注点数"))
        if amt and qty:
            return float(round(amt / qty)), "台帳 発注額÷発注点数"
    return None, "原価未確認"


def read_ledger() -> list[dict]:
    import ledger_sheet as L      # gspread は夜間のローカル環境にある
    ws = L.open_tab()
    v = ws.get_all_values()
    head = v[0]
    return [dict(zip(head, r)) for r in v[1:]]


def build_watchlist(today: date, ledger: list[dict] | None = None) -> tuple[list[dict], dict]:
    """監視リストを更新して返す。**既存行は動かさない**（開始日・原価・1年中央値を固定＝漂わない）。"""
    current = {r["ASIN"]: r for r in _read_csv(WATCHLIST)}
    ledger = ledger if ledger is not None else read_ledger()
    by_asin: dict[str, dict] = {}
    for r in ledger:          # 重複行は「原価が読める行」を優先、同点なら後ろ
        a = (r.get("ASIN") or "").strip()
        if not a:
            continue
        has = bool(_num(r.get("発注額(円・税込)")) and _num(r.get("発注点数")))
        if a not in by_asin or has or not (_num(by_asin[a].get("発注額(円・税込)"))):
            by_asin[a] = r
    disc = {r["ASIN"]: r for r in _read_csv(DISCONTINUED) if r.get("終売フラグ") == "NO-GO"}
    want = set(by_asin) | set(FIXED) | set(disc)
    cached = latest_cached(want)
    yz = yazawa_costs()

    reasons: dict[str, list[str]] = defaultdict(list)
    for a, why in FIXED.items():
        reasons[a].append(why)
    for a in disc:
        reasons[a].append("終売フラグ（§3.5 #12）")
    levels: dict[str, dict] = {}
    for a, d in cached.items():
        lv = price_levels(d["product"], d["fetched"])
        levels[a] = lv
        m365 = lv["median365"]
        top = max([x for x in (lv["current"], lv["median90"]) if x] or [0])
        if m365 and top > m365 * PRICE_JUMP:
            reasons[a].append(f"価格の跳ね（{top:,}円＝1年中央値 {m365:,}円 の {top / m365:.2f}倍）")

    added = 0
    for a, rs in reasons.items():
        if a in current:
            continue
        lr = by_asin.get(a)
        title = (lr or {}).get("商品名") or (disc.get(a) or {}).get("商品名") \
            or ((cached.get(a) or {}).get("product") or {}).get("title") or ""
        cost, src = cost_for(title, lr, yz)
        lot = int(_num((lr or {}).get("発注点数")) or DEFAULT_LOT)
        lv = levels.get(a) or {}
        m365, top = lv.get("median365"), max([x for x in (lv.get("current"), lv.get("median90")) if x] or [0])
        current[a] = {"ASIN": a, "商品名": title, "追加日": today.isoformat(), "追加理由": "／".join(rs),
                      "購入元の名前": (lr or {}).get("購入元の名前") or (disc.get(a) or {}).get("購入元の名前") or "",
                      "Amazon1個あたり原価(税込)": int(cost) if cost else "", "原価の出所": src,
                      "最小ロット(Amazon個)": lot, "1年中央値(追加時)": m365 or "",
                      "追加時の倍率(現在/1年中央値)": round(top / m365, 2) if (m365 and top) else ""}
        added += 1
    rows = sorted(current.values(), key=lambda r: (r["追加日"], r["ASIN"]))
    _write_csv(WATCHLIST, WATCH_COLS, rows)
    stats = {"監視対象": len(rows), "今回追加": added, "台帳の行": len(ledger),
             "価格判定に使えた ASIN（手元の Keepa）": len(cached)}
    return rows, stats


# ── Keepa 取得（その日の分は1回だけ） ────────────────────────────────────

def _keepa_key() -> str:
    k = os.environ.get("KEEPA_API_KEY")
    if k:
        return k
    for line in (Path.home() / ".config/ai-company-amazon-buppan/keepa.env").read_text().splitlines():
        if line.startswith("KEEPA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("KEEPA_API_KEY がありません")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


def fetch_today(asins: list[str], today: date) -> dict:
    """今日の生データに無い ASIN だけ取る。トークンが待っても足りなければ止めて、残りを返す。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"keepa_{today.isoformat()}.jsonl"
    have = {a for a, _ in _iter_raw([raw])}
    todo = [a for a in asins if a not in have]
    res = {"取得済み(今日)": len(have), "今回取得": 0, "未取得": []}
    if not todo:
        return res
    k = _keepa_key()
    for i in range(0, len(todo), KEEPA_BATCH):
        chunk = todo[i:i + KEEPA_BATCH]
        need = len(chunk) * KEEPA_COST_PER_ASIN
        waited = 0
        while True:
            left = _get(f"https://api.keepa.com/token?key={k}").get("tokensLeft", 0)
            if left >= need:
                break
            if waited >= KEEPA_MAX_WAIT_SEC:
                res["未取得"] = todo[i:]
                print(f"  Keepa トークン {left} < {need}。{waited}秒待っても足りないので止める"
                      f"（残り {len(todo) - i}件は次回）", flush=True)
                return res
            s = min(300, max(20, int((need - left) / 20 * 60) + 5))
            time.sleep(s)
            waited += s
        url = (f"https://api.keepa.com/product?key={k}&domain=5&asin={','.join(chunk)}"
               f"&stats=90&history=1&buybox=1&days=400")
        d = _get(url)
        now = int(time.time())
        with raw.open("a") as f:
            for p in d.get("products") or []:
                f.write(json.dumps({"asin": p.get("asin"), "fetched": now, "product": p},
                                   ensure_ascii=False) + "\n")
        res["今回取得"] += len(d.get("products") or [])
        print(f"  Keepa {i + len(chunk)}/{len(todo)}・消費 {d.get('tokensConsumed')}・残 {d.get('tokensLeft')}",
              flush=True)
    return res


def update_history(today: date) -> int:
    """今日の生データ → history.csv。(日付, ASIN) で置き換える＝2回目で行が増えない。"""
    raw = RAW_DIR / f"keepa_{today.isoformat()}.jsonl"
    latest: dict[str, dict] = {}
    for a, d in _iter_raw([raw]):
        if a not in latest or d["fetched"] >= latest[a]["fetched"]:
            latest[a] = d
    new = {a: observe(a, d["product"], d["fetched"], today) for a, d in latest.items()}
    rows = [r for r in _read_csv(HISTORY) if not (r["日付"] == today.isoformat() and r["ASIN"] in new)]
    rows += list(new.values())
    rows.sort(key=lambda r: (r["日付"], r["ASIN"]))
    _write_csv(HISTORY, HIST_COLS, rows)
    return len(new)


# ── 仮想損益（history.csv から毎回全部計算し直す） ─────────────────────────

def _tier(fba_yen, price, product_like: dict | None = None) -> str:
    t = F.tier_from_fba_fee(int(fba_yen) if fba_yen else None, price)
    return t or "標準3"


def unit_net(price: float, fba_yen, keepa_pct, months_to_sell: float) -> int:
    """1個売れたときの入金（原価を引く前）。fba_cost._scenario を原価0で回す＝台帳と同じ費用。"""
    tier = _tier(fba_yen, price)
    sc = F._scenario(price, 0.0, tier, worst=False, category=None,
                     keepa_pct=float(keepa_pct) if keepa_pct else None,
                     months_to_sell=months_to_sell, peak=False, apparel=False)
    return int(sc["手残り"])


def simulate(w: dict, obs: list[dict], today: date, off: dict | None = None) -> dict:
    a = w["ASIN"]
    start = date.fromisoformat(w["追加日"])
    sale = start + timedelta(days=LEAD_DAYS)
    cost = _num(w.get("Amazon1個あたり原価(税込)"))
    lot = int(_num(w.get("最小ロット(Amazon個)")) or DEFAULT_LOT)
    m365 = _num(w.get("1年中央値(追加時)"))
    obs = sorted([o for o in obs if o["日付"] >= w["追加日"]], key=lambda o: o["日付"])
    last = obs[-1] if obs else {}
    row = {"ASIN": a, "商品名": w["商品名"], "追加理由": w["追加理由"], "監視開始": w["追加日"],
           "販売開始": sale.isoformat(), "観測日数": len(obs), "原価(税込)": int(cost) if cost else "",
           "ロット": lot, "最新カート価格": last.get("カート価格") or last.get("新品最安") or "",
           "1年中央値": int(m365) if m365 else "", "高値の連続日数(履歴遡り)": last.get("高値の連続日数(履歴遡り)", "")}
    lp = _num(row["最新カート価格"])
    row["倍率"] = round(lp / m365, 2) if (lp and m365) else ""
    # 監視中に高値（1年中央値×1.3 超）が続いた日数（観測日の連続）
    streak = 0
    for o in reversed(obs):
        p = _num(o.get("カート価格")) or _num(o.get("新品最安"))
        if p and m365 and p > m365 * PRICE_JUMP:
            streak += 1
        else:
            break
    row["高値の継続日数(監視中)"] = streak
    notes = []

    def share(o: dict) -> float | None:
        m1 = _num(o.get("kz_m1"))
        f, b = _num(o.get("カート対象FBA")), _num(o.get("カート対象自己発送"))
        if m1 is None or f is None or b is None:
            return None
        return m1 / (f + b + 1)

    # Amazon 外の最安（手入力）。Amazon 価格がこれの1.3倍を超えると公正価格ポリシーでカートを外される恐れ
    offp = _num((off or {}).get("Amazon外最安(税込)"))
    if offp:
        row["Amazon外最安"] = int(offp)
        row["Amazon外の確認日"] = (off or {}).get("確認日", "")
        if lp:
            row["倍率(Amazon/Amazon外)"] = round(lp / offp, 2)
            row["公正価格の恐れ"] = "恐れあり" if lp / offp > FAIR_PRICE_RATIO else ""
    sh = share(last) if last else None
    row["取り分(個/月)"] = round(sh, 2) if sh is not None else ""
    if not cost:
        notes.append("原価未確認＝損益は計算しない（監視だけ）")
        row["注意"] = "・".join(notes)
        return row
    months = min(12.0, lot / sh) if sh else 3.0
    inv = float(lot)
    cash_in = 0.0
    by_day = {o["日付"]: o for o in obs}
    cur: dict | None = None
    d = start
    while d <= today:
        cur = by_day.get(d.isoformat(), cur)
        if d >= sale and cur and inv > 0:
            p = _num(cur.get("カート価格")) or _num(cur.get("新品最安"))
            s = share(cur)
            if p and s and cur.get("カートは本体") != "1":
                q = min(inv, s / 30.0)
                inv -= q
                cash_in += q * unit_net(p, cur.get("FBA配送代行(Keepa)"), cur.get("販売手数料率(Keepa)"), months)
        d += timedelta(days=1)
    spent = cost * lot
    sold = lot - inv
    pess_unit = unit_net(m365, last.get("FBA配送代行(Keepa)"), last.get("販売手数料率(Keepa)"), months) if m365 else None
    row.update({"売れた個数": round(sold, 1), "残在庫": round(inv, 1), "入金累計": int(round(cash_in)),
                "現金損益": int(round(cash_in - spent)),
                "評価込み損益": int(round(cash_in - spent + inv * pess_unit)) if pess_unit is not None else "",
                "悲観損益(全数を1年中央値で)": int(round(lot * pess_unit - spent)) if pess_unit is not None else ""})
    if offp:     # 悲観②：価格が Amazon 外最安まで戻る（公正価格ポリシーでカートを外されたら、そこまで下げないと売れない）
        off_unit = unit_net(offp, last.get("FBA配送代行(Keepa)"), last.get("販売手数料率(Keepa)"), months)
        row["悲観損益(全数をAmazon外最安で)"] = int(round(lot * off_unit - spent))
    if row.get("公正価格の恐れ"):
        notes.append(f"公正価格ポリシーでカートを失う恐れ（Amazon {int(lp):,}円＝Amazon外最安 {int(offp):,}円 の {lp / offp:.2f}倍）")
    if today < sale:
        notes.append(f"販売開始前（{sale.isoformat()}〜）")
    if not obs:
        notes.append("観測なし")
    if last.get("カートは本体") == "1":
        notes.append("最新はカートが Amazon 本体＝売れない日")
    if sh is None and obs:
        notes.append("取り分不明（出品者内訳なし）")
    if last and not F.tier_from_fba_fee(int(_num(last.get("FBA配送代行(Keepa)")) or 0) or None, lp):
        notes.append("サイズ区分不明＝標準3で仮置き（推定費目）")
    notes.append("評価込み＝残在庫を1年中央値で売った場合で評価（保守側）")
    row["注意"] = "・".join(notes)
    return row


def compute_pnl(today: date) -> list[dict]:
    wl = _read_csv(WATCHLIST)
    hist = defaultdict(list)
    for r in _read_csv(HISTORY):
        hist[r["ASIN"]].append(r)
    off = off_amazon_prices()
    rows = [simulate(w, hist.get(w["ASIN"], []), today, off.get(w["ASIN"])) for w in wl]
    _write_csv(PNL, PNL_COLS, rows)
    return rows


def judge(rows: list[dict]) -> dict:
    priced = [r for r in rows if r.get("原価(税込)") not in ("", None) and r.get("評価込み損益") not in ("", None)]
    win = [r for r in priced if (_num(r["評価込み損益"]) or 0) > 0]
    pess = []
    for r in priced:      # 悲観2本（1年中央値／Amazon外最安）のうち悪い方
        vs = [_num(r.get(c)) for c in ("悲観損益(全数を1年中央値で)", "悲観損益(全数をAmazon外最安で)")]
        vs = [v for v in vs if v is not None]
        if vs:
            pess.append((min(vs), r))
    worst = min(pess, key=lambda x: x[0]) if pess else None
    observed = [r for r in rows if int(r.get("観測日数") or 0) >= HIGH_STREAK_DAYS]
    high4 = [r for r in observed if int(r.get("高値の継続日数(監視中)") or 0) >= HIGH_STREAK_DAYS]
    back = [r for r in rows if str(r.get("高値の連続日数(履歴遡り)", "")).strip() != ""]
    back4 = [r for r in back if int(r["高値の連続日数(履歴遡り)"]) >= HIGH_STREAK_DAYS]
    return {
        "①母数(原価が判っている)": len(priced), "①黒字": len(win),
        "①過半か": (len(win) * 2 > len(priced)) if priced else None,
        "②最大損(悲観)": worst[0] if worst else None, "②最大損のASIN": worst[1]["ASIN"] if worst else "",
        "②1万円以内か": (worst[0] >= -MAX_LOSS_PER_LOT) if worst else None,
        "②悲観で1万円超の損の件数": sum(1 for v, _ in pess if v < -MAX_LOSS_PER_LOT),
        "公正価格の恐れ(Amazon外の価格が入っている行のうち)": f"{sum(1 for r in rows if r.get('公正価格の恐れ'))}/{sum(1 for r in rows if r.get('Amazon外最安'))}",
        "③母数(監視28日以上)": len(observed), "③4週以上高値": len(high4),
        "③参考 履歴遡りの母数": len(back), "③参考 履歴遡りで4週以上高値": len(back4),
    }


# ── 週次サマリー ─────────────────────────────────────────────────────────

def weekly(today: date) -> Path:
    rows = compute_pnl(today)
    j = judge(rows)
    hist = defaultdict(list)
    for r in _read_csv(HISTORY):
        hist[r["ASIN"]].append(r)
    pct = lambda a, b: f"{a}/{b}（{a / b * 100:.0f}%）" if b else f"{a}/0（判定不能）"
    L = [f"# 品薄・終売プレミアム 定点監視 週次サマリー（{today.isoformat()}）", "",
         f"- 監視対象 {len(rows)}件（うち原価が判っている {j['①母数(原価が判っている)']}件）・判定日 {WATCH_END.isoformat()}",
         "- 発注はしていない。監視開始日に最小ロットを買ったとみなした**紙の上の取引**",
         "- 式：販売開始＝開始＋21日／1日の販売＝kz再現 m1÷(カート対象FBA＋自己発送＋1)÷30・本体カートの日は0／"
         "入金＝fba_cost の費用一式（手数料・FBA・保管・納品・おりおん）／悲観＝売価が1年中央値に戻る", "",
         "## 判定の3指標（秘書が 2026-12-07 に使う）", "",
         "| # | 指標 | 値 | 線 |", "|---|---|---|---|",
         f"| ① | 評価込みで黒字の ASIN | {pct(j['①黒字'], j['①母数(原価が判っている)'])} | 過半 |",
         f"| ② | 悲観（全数を1年中央値で／Amazon外最安での悪い方）の最大損 | {j['②最大損(悲観)'] if j['②最大損(悲観)'] is not None else '—'}円（{j['②最大損のASIN']}）・1万円超の損 {j['②悲観で1万円超の損の件数']}件 | 1ロット1万円以内 |",
         f"| ③ | 高値が4週以上続いた | {pct(j['③4週以上高値'], j['③母数(監視28日以上)'])} | （参考）履歴遡り {pct(j['③参考 履歴遡りで4週以上高値'], j['③参考 履歴遡りの母数'])} |",
         f"| — | 公正価格ポリシーでカートを失う恐れ（Amazon価格がAmazon外最安の1.3倍超） | {j['公正価格の恐れ(Amazon外の価格が入っている行のうち)']}（Amazon外の価格が入っている行のうち） | 手入力（offamazon_prices.csv）・週1 |",
         "", "判定の目安：①過半 かつ ②1万円以内 → 採用／どちらか一方 → 条件つき採用（満たした側の条件で絞る）／どちらも不可 → 不採用。"
         "③は「高値がどれだけ持つか」＝仕入れから販売開始までの21日を高値が越えられるかの根拠。", "",
         "## ASIN ごと（評価込み損益の順）", "",
         "| ASIN | 商品名 | 開始 | 最新カート | 1年中央値 | 倍率 | 取り分/月 | 売れた | 残 | 現金損益 | 評価込み | 悲観 | 悲観(Amazon外) | Amazon外最安(倍率) | 高値継続(監視/遡り) | 価格推移（週ごと） |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def key(r):
        v = _num(r.get("評価込み損益"))
        return (v is None, -(v or 0))
    for r in sorted(rows, key=key):
        h = sorted(hist.get(r["ASIN"], []), key=lambda o: o["日付"])
        wk = []
        for o in h:
            if not wk or (date.fromisoformat(o["日付"]) - date.fromisoformat(wk[-1][0])).days >= 7:
                wk.append((o["日付"], o.get("カート価格") or o.get("新品最安") or "—"))
        trend = " → ".join(f"{d[5:]} {p}" for d, p in wk[-8:]) or "—"
        L.append(f"| [{r['ASIN']}](https://www.amazon.co.jp/dp/{r['ASIN']}) | {r['商品名'][:30]} | {r['監視開始']} | "
                 f"{r.get('最新カート価格') or '—'} | {r.get('1年中央値') or '—'} | {r.get('倍率') or '—'} | "
                 f"{r.get('取り分(個/月)', '') or '—'} | {r.get('売れた個数', '—')} | {r.get('残在庫', '—')} | "
                 f"{r.get('現金損益', '—')} | {r.get('評価込み損益', '—')} | {r.get('悲観損益(全数を1年中央値で)', '—')} | "
                 f"{r.get('悲観損益(全数をAmazon外最安で)') or '—'} | "
                 f"{(str(r['Amazon外最安']) + '（' + str(r.get('倍率(Amazon/Amazon外)', '')) + '倍' + ('・🔴公正価格ポリシーでカートを失う恐れ' if r.get('公正価格の恐れ') else '') + '）') if r.get('Amazon外最安') else '未入力'} | "
                 f"{r.get('高値の継続日数(監視中)', 0)}/{r.get('高値の連続日数(履歴遡り)') or '—'} | {trend} |")
    p = OUT / f"weekly_{today.isoformat()}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["run", "weekly", "list"])
    ap.add_argument("--no-fetch", action="store_true", help="Keepa を叩かない")
    ap.add_argument("--today", help="YYYY-MM-DD（検算用）")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd in ("run", "list"):
        wl, st = build_watchlist(today)
        print("監視リスト:", json.dumps(st, ensure_ascii=False))
        if a.cmd == "list":
            return 0
        if not a.no_fetch:
            r = fetch_today([w["ASIN"] for w in wl], today)
            print("Keepa:", json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()},
                                        ensure_ascii=False))
        n = update_history(today)
        rows = compute_pnl(today)
        print(f"history.csv：今日 {n}行（置き換え）・pnl.csv {len(rows)}行")
        print("判定:", json.dumps(judge(rows), ensure_ascii=False))
        if today.weekday() == 0:          # 月曜は週次も出す
            print("週次:", weekly(today))
        return 0
    print("週次:", weekly(today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
