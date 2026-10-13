#!/usr/bin/env python3
"""自動ふるい — 仕入れ先1社（または卸サイトの索引）の商品一覧から「人が実画面で見る価値のある候補」を出す。

2026-10-11 タカシ（T-20260920-003・社長指示「利益の出る商品を仕入れる仕組みを作って」の部品2）。

なぜ要るか
----------
卸サイトの売れ筋の多くは卸値が Amazon の売価に近く、赤字です。GO は「大量の候補を
安く機械でふるった後の少数」からしか出ません。だから、**仕入れ先の一覧を丸ごと入れて、
機械で決まる §3.5 の項目を全部当て、残った行だけを人に渡す**道具を1本にしました。

新しい判定ロジックは書いていません。台帳と同じ採点（`score_20261004.build`：価格履歴・
カート・セット数・採算等級・季節の窓）をそのまま呼び、次の4つを足しただけです。

| 足したもの | 中身 | §3.5 |
|---|---|---|
| 実売（キーゾン相当） | Keepa ランク履歴で「30日ごとに直前より3%超改善した回数」（キーゾン実画面25ASIN×3か月で一致を確認済み） | #9 |
| 取り分 | 3か月平均 ÷（カート対象の FBA＋自己発送＋1）。3個/月未満は落とす | #10 |
| メーカー本人のカート | カート保持者の表示名がブランド名・メーカー名と一致したら疑い（UNKNOWN） | #5 |
| 終売フラグ | `discontinued.py`（法令品目・卸の廃番は印＋「今だけ」3条件で判定・兆候は UNKNOWN。2026-10-12） | #12 |

入口の流れ
----------
    入力 CSV（JAN・卸単価・入数・最小ロット …／`supplier_inputs.py` が作る）
      → JAN → Keepa（**キャッシュ優先**。手元の Keepa 生データ約4千件を先に引く）
      → 足りない JAN だけ `code` 逆引き（1トークン/商品・当たらない JAN は課金されない）
      → **セット品 ASIN も全部**（JAN はセットと単品で同じ。§3.3-19）
      → 採点 → 候補の行にだけ buybox を取り直す（カート保持者と出品者数。3トークン/商品）

**このスクリプトは台帳に書きません。**出力 CSV（台帳と同じ32列＋補助列）を合流させるのは
台帳の再採点（`ledger_refresh.py`）の役目です。発注もしません（§4.1）。

🔴 出力には卸値・購入先URL が入るので **agent_output にだけ置きます**（PUBLIC リポ）。

使い方
------
    python3 supplier_inputs.py sd-screen                       # 入力を作る（SD 実画面価格）
    python3 supplier_screen.py run <入力CSV> --label sd         # キャッシュだけで回す（0トークン）
    python3 supplier_screen.py run <入力CSV> --label netsea --tokens 600   # 足りない JAN を引く
    python3 supplier_screen.py run <入力CSV> --tokens 600 --wait            # 残高が回復するまで待って使い切る
    python3 test_supplier_screen.py                             # テスト（通信0）

トークン
--------
Keepa の API キーは全チケット共有の1本です（memory: knowledge_keepa_key_is_a_shared_resource）。
`--tokens` はこの実行で使ってよい量、`--floor` は残しておく残高です。**未取得の JAN は
`state/fetch_queue` に残り、次の実行で続きから引きます**（上限ではなく順番。§3.3-34）。
順番は仕入れ先ごとのラウンドロビン（1社20件で次の社へ）です。
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import discontinued as DISC           # noqa: E402
import price_history as PH            # noqa: E402
import schedule as SC                 # noqa: E402
import score_20261004 as S            # noqa: E402
import supplier_inputs as SI          # noqa: E402
from ledger_sheet import COLUMNS      # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
OUT_DIR = WORK / "supplier_screen"
STATE = OUT_DIR / "state"
OWN_CACHE = STATE / "keepa_cache.jsonl"       # この道具が取った商品（追記のみ）
JAN_SEEN = STATE / "jan_seen.json"            # code 逆引きした JAN → ASIN（当たらなかった JAN も []）
NAMES = WORK / "pipeline/seller_names.json"   # セラーID → 表示名（keepa_sellers と共有）
LEDGER_SNAP_DIR = WORK / "ledger20261010"
TICKET = "T-20260920-003"

KEEPA_EPOCH_MIN = 21564000
AMAZON_JP = "AN1VRQENFRJN5"
KZ_THR = 0.03            # キーゾン相当式の閾値（knowledge_keizon_reproduced_from_keepa_rank）
MIN_SHARE = 3.0          # §3.5 #10 取り分の下限（個/月）
TARGET_MONTHS = 3        # 発注点数＝取り分の3か月分（最小ロット以上）
MAX_MONTHS = 6           # §3.5 #10 在庫月数の上限
BB_MAX_AGE_DAYS = 14     # カート情報をこれより古いキャッシュから借りない
PER_SUPPLIER = 20        # ラウンドロビンの引き金（1社20件で次の社へ・上限ではない）

# 手元の Keepa 生データ（新しい順に並べる必要はない。ASIN ごとに取得時刻の新しい方を採る）
CACHE_SOURCES = [
    WORK / "kz_entry/keepa_full.jsonl",
    WORK / "kz_entry/keepa_hist.jsonl",
    WORK / "ledger20261010/keepa_unknown_20261011.jsonl",
    WORK / "ledger20261010/keepa_kz_hist_20261011.jsonl",
    WORK / "buylist20261009/resolve_raw.jsonl",
    WORK / "buylist20261009/buybox_raw.jsonl",
    WORK / "sd_buylist20261009/keepa_raw.jsonl",        # {code, fetched, products}＝JAN 逆引き
    WORK / "refetch20261004/raw.jsonl",
    WORK / "sd_lookup_keepa_raw_20261011.json",         # {asin: product}（取得時刻はファイル時刻）
]

_EAN_RE = re.compile(r'"eanList":\s*\[([^\]]*)\]')


# ── Keepa の手元キャッシュ ───────────────────────────────────────────────


@dataclass
class Cached:
    product: dict
    fetched: int            # Unix 秒
    source: str


def _has_bb(p: dict) -> bool:
    st = p.get("stats") or {}
    return "buyBoxSellerId" in st or "buyBoxIsAmazon" in st


class KeepaStore:
    """JAN / ASIN → Keepa 商品。キャッシュ優先、足りない分だけ API。"""

    def __init__(self, jans: set[str], sources: list[Path] | None = None, log=print):
        self.jans = jans
        self.latest: dict[str, Cached] = {}
        self.latest_bb: dict[str, Cached] = {}
        self.by_jan: dict[str, set[str]] = defaultdict(set)
        self.complete: set[str] = set()       # code 逆引き済み＝セット品まで網羅している JAN
        self.tokens_spent = 0
        self.log = log
        self._load(sources if sources is not None else CACHE_SOURCES + [OWN_CACHE])
        seen = json.loads(JAN_SEEN.read_text()) if JAN_SEEN.exists() else {}
        for j, v in seen.items():
            if j in jans:
                self.complete.add(j)
                for a in v.get("asins") or []:
                    self.by_jan[j].add(a)

    # 読み込み ---------------------------------------------------------------
    def _offer(self, p: dict, fetched: int, source: str, via_code: str | None = None) -> None:
        eans = {str(e) for e in (p.get("eanList") or []) + (p.get("upcList") or [])}
        hit = eans & self.jans
        if not hit:
            return
        a = p.get("asin")
        c = Cached(p, int(fetched or 0), source)
        if a not in self.latest or c.fetched > self.latest[a].fetched:
            self.latest[a] = c
        if _has_bb(p) and (a not in self.latest_bb or c.fetched > self.latest_bb[a].fetched):
            self.latest_bb[a] = c
        for j in hit:
            self.by_jan[j].add(a)
        if via_code and via_code in self.jans:
            self.complete.add(via_code)

    def _load(self, sources: list[Path]) -> None:
        for path in sources:
            if not path.exists():
                continue
            n0 = len(self.latest)
            if path.suffix == ".jsonl":
                with path.open() as f:
                    for line in f:
                        m = _EAN_RE.search(line)
                        if m and not ({x.strip().strip('"') for x in m.group(1).split(",")}
                                      & self.jans):
                            continue          # 速さのため：対象 JAN を含まない行は解析しない
                        try:
                            o = json.loads(line)
                        except ValueError:
                            continue
                        if "products" in o:
                            for p in o.get("products") or []:
                                self._offer(p, o.get("fetched"), path.name, str(o.get("code") or ""))
                            if not o.get("products") and str(o.get("code")) in self.jans:
                                self.complete.add(str(o["code"]))     # 当たらなかった JAN
                        elif o.get("product"):
                            self._offer(o["product"], o.get("fetched"), path.name,
                                        o.get("via_code"))
            else:
                d = json.loads(path.read_text())
                mt = int(path.stat().st_mtime)
                vals = d.get("products") if isinstance(d, dict) and "products" in d else (
                    d.values() if isinstance(d, dict) else d)
                for p in vals:
                    if isinstance(p, dict):
                        self._offer(p, mt, path.name)
            self.log(f"  キャッシュ {path.name}: +{len(self.latest) - n0} ASIN")

    # 参照 -----------------------------------------------------------------
    def product(self, asin: str) -> tuple[dict, int, str, str]:
        """(商品, 取得時刻, 出どころ, カート情報の注記)。

        最新の取得にカート情報（buybox）が無く、14日以内の別の取得にあれば、
        カート保持者と出品者数だけそちらから借りる（借りたことを注記に書く）。
        """
        c = self.latest[asin]
        p = c.product
        note = ""
        if not _has_bb(p) and asin in self.latest_bb:
            b = self.latest_bb[asin]
            if abs(c.fetched - b.fetched) <= BB_MAX_AGE_DAYS * 86400:
                p = dict(p)
                st = dict(p.get("stats") or {})
                bst = b.product.get("stats") or {}
                for k in ("buyBoxSellerId", "buyBoxIsAmazon", "buyBoxIsFBA"):
                    if k in bst:
                        st[k] = bst[k]
                p["stats"] = st
                if b.product.get("buyBoxEligibleOfferCounts") is not None:
                    p["buyBoxEligibleOfferCounts"] = b.product["buyBoxEligibleOfferCounts"]
                note = f"カート情報は {_day(b.fetched)} の取得から"
        return p, c.fetched, c.source, note

    # API -----------------------------------------------------------------
    def _get(self, params: dict) -> dict:
        from keepa_client import load_api_key
        params = {"key": load_api_key(), "domain": 5, **params}
        raw = urllib.request.urlopen("https://api.keepa.com/product?" + urllib.parse.urlencode(params),
                                     timeout=300).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode())

    def _save(self, products: list[dict], fetched: int, via_code: str | None, source: str) -> None:
        STATE.mkdir(parents=True, exist_ok=True)
        with OWN_CACHE.open("a") as f:
            for p in products:
                f.write(json.dumps({"asin": p.get("asin"), "fetched": fetched, "via_code": via_code,
                                    "product": p}, ensure_ascii=False) + "\n")
                self._offer(p, fetched, source, via_code)

    def resolve_jans(self, jans: list[str], budget: int, floor: int, wait: bool) -> list[str]:
        """未取得の JAN を `code` で逆引きする。戻り値は引けた JAN。

        1リクエスト最大100 JAN。課金は**返ってきた商品数**（当たらない JAN は無料・基本1）。
        予算を超えそうなら、その手前で止める（実測レートで次のバッチを縮める）。
        """
        seen = json.loads(JAN_SEEN.read_text()) if JAN_SEEN.exists() else {}
        done: list[str] = []
        rate = 2.0                      # 1 JAN あたりの消費（安全側の初期値・走りながら更新。実測1.5〜1.7）
        i = 0
        while i < len(jans):
            room = budget - self.tokens_spent
            left = tokens_left()
            if left - floor < 20:
                if not wait:
                    self.log(f"  残高 {left}（下限 {floor}）。--wait なしなので止めます")
                    break
                self.log(f"  残高 {left}（下限 {floor}）。60秒待ちます")
                time.sleep(60)
                continue
            n = min(100, int(min(room, left - floor) / rate))
            if n < 1:
                break
            chunk = jans[i:i + n]
            i += len(chunk)
            d = self._get({"code": ",".join(chunk), "stats": 90, "history": 1, "days": 400})
            if d.get("error"):
                self.log(f"  Keepa エラー: {d['error']}")
                break
            prods = d.get("products") or []
            spent = d.get("tokensConsumed") or 0
            self.tokens_spent += spent
            now = int(time.time())
            hit: dict[str, list[str]] = {j: [] for j in chunk}
            for p in prods:
                for e in (p.get("eanList") or []) + (p.get("upcList") or []):
                    if str(e) in hit:
                        hit[str(e)].append(p["asin"])
            self._save(prods, now, None, "code逆引き")
            for j, asins in hit.items():
                seen[j] = {"asins": sorted(set(asins)), "fetched": now}
                self.complete.add(j)
            done.extend(chunk)
            JAN_SEEN.write_text(json.dumps(seen))
            rate = max(0.3, self.tokens_spent / max(1, len(done))) * 1.15   # 1割5分の余裕
            self.log(f"  JAN {len(done)}/{len(jans)} → 商品 {len(prods)} / 消費 {spent}"
                     f"（累計 {self.tokens_spent}・残 {d.get('tokensLeft')}）")
        return done

    def refresh_buybox(self, asins: list[str], budget: int, floor: int, wait: bool) -> int:
        """候補の行だけ buybox=1 で取り直す（カート保持者・カート対象の出品者数）。3トークン/商品。"""
        got = 0
        i = 0
        while i < len(asins):
            room = budget - self.tokens_spent
            left = tokens_left()
            if left - floor < 3:
                if not wait:
                    self.log(f"  残高 {left}（下限 {floor}）。buybox の取り直しを止めます")
                    break
                time.sleep(60)
                continue
            n = min(100, int(min(room, left - floor) / 3))
            if n < 1:
                break
            chunk = asins[i:i + n]
            i += len(chunk)
            d = self._get({"asin": ",".join(chunk), "stats": 90, "history": 1, "days": 400,
                           "buybox": 1})
            if d.get("error"):
                self.log(f"  Keepa エラー: {d['error']}")
                break
            prods = d.get("products") or []
            self.tokens_spent += d.get("tokensConsumed") or 0
            self._save(prods, int(time.time()), None, "buybox取り直し")
            got += len(prods)
            self.log(f"  buybox {got}/{len(asins)}（累計 {self.tokens_spent}・残 {d.get('tokensLeft')}）")
        return got


def tokens_left() -> int:
    from keepa_client import load_api_key
    raw = urllib.request.urlopen(f"https://api.keepa.com/token?key={load_api_key()}", timeout=60).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return int(json.loads(raw.decode()).get("tokensLeft") or 0)


def _day(unix: int) -> str:
    return datetime.fromtimestamp(unix).strftime("%Y-%m-%d") if unix else ""


# ── キーゾン相当の3か月販売数 ────────────────────────────────────────────


def kz_months(product: dict, fetched_unix: int) -> tuple[list[int], list[int]] | None:
    """[(m1, m2, m3), (観測回数)]。式は kz_estimate.py と同じ（30日窓・3%超の改善回数）。"""
    c = product.get("csv") or []
    csv3 = c[3] if len(c) > 3 else None
    if not csv3:
        return None
    now = fetched_unix // 60 - KEEPA_EPOCH_MIN
    ps = [(csv3[i], csv3[i + 1]) for i in range(0, len(csv3) - 1, 2)]
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


def sales_gate(product: dict, fetched: int) -> tuple[str, str, list[int] | None, float | None]:
    """(状態, 理由, [m1,m2,m3], 3か月平均)。§3.5 #9。"""
    k = kz_months(product, fetched)
    if not k:
        return "UNKNOWN", "ランク履歴がなく3か月の販売数を数えられません", None, None
    m, obs = k
    avg = round(sum(m) / 3, 1)
    txt = f"キーゾン相当 3か月 {m[0]}/{m[1]}/{m[2]}個（平均{avg:g}）"
    notes = []
    if product.get("parentAsin"):
        notes.append("バリエーション子＝family合計")
    if any(o < 10 for o in obs):
        notes.append("観測少(" + "/".join(map(str, obs)) + ")")
    if max(m) > 13:
        notes.append("月13個超は未検算・過小の可能性")
    tail = f"（{'・'.join(notes)}）" if notes else ""
    if sum(obs) == 0:
        return "FAIL", "直近90日に売れ筋ランクの観測が1回もない＝この出品は売れていない（§3.5 #9）", m, avg
    if sum(m) == 0:
        if any(o < 10 for o in obs):
            return "UNKNOWN", f"{txt}{tail}＝観測が少なく0個と区別できない", m, avg
        return "FAIL", f"{txt}＝3か月で売れていません（§3.5 #9）", m, avg
    if product.get("parentAsin"):
        return "UNKNOWN", f"{txt}{tail}＝この ASIN 単独の数ではない", m, avg
    return "PASS", txt + tail, m, avg


def share_of(product: dict, avg: float | None) -> tuple[float | None, str]:
    bb = product.get("buyBoxEligibleOfferCounts") or []
    if avg is None:
        return None, "販売数が無い"
    if len(bb) < 2:
        return None, "カート対象の出品者数が取れていない（buybox 未取得）"
    fba, fbm = max(bb[0], 0), max(bb[1], 0)
    return avg / (fba + fbm + 1), f"{avg:g}÷(FBA {fba}＋自己発送 {fbm}＋1)"


def maker_gate(product: dict, names: dict) -> tuple[str, str]:
    """§3.5 #5 のうちメーカー本人の検出。名前が無ければ判定しない（注記だけ）。"""
    from screen_checks import maker_suspect
    sid = (product.get("stats") or {}).get("buyBoxSellerId")
    if not sid or sid in ("-1", AMAZON_JP):
        return "PASS", ""
    nm = names.get(sid)
    if not nm:
        return "PASS", f"カート保持者 {sid} の表示名が未取得（メーカー本人かは実画面で）"
    sus = maker_suspect(nm, product.get("brand") or "", product.get("manufacturer") or "")
    return ("UNKNOWN", f"メーカー/ブランド本人の疑い：{sus}") if sus else ("PASS", f"カート保持者 {nm}")


# ── 1行の採点 ─────────────────────────────────────────────────────────────


@dataclass
class Scored:
    asin: str
    inp: dict
    s: dict
    verdict: str
    bucket: str
    cells: dict = field(default_factory=dict)


def ceil_div(a: float, b: float) -> int:
    return int(math.ceil(a / b)) if b else int(a)


def rank_alive(product: dict, fetched: int, days: int = 60) -> bool:
    """直近 days 日に売れ筋ランク（csv[3]）の正の値があるか。"""
    c = product.get("csv") or []
    csv3 = c[3] if len(c) > 3 and c[3] else []
    now = fetched // 60 - KEEPA_EPOCH_MIN
    pts = [(csv3[i], csv3[i + 1]) for i in range(0, len(csv3) - 1, 2)]
    if not pts:
        return False
    if pts[-1][1] > 0 and now - pts[-1][0] < days * 1440:
        return True
    return any(v > 0 for t, v in pts if t >= now - days * 1440)


def score_asin(asin: str, inp: dict, store: KeepaStore, names: dict, rank_counts: dict,
               ledger: set[str], family_alive: bool = False) -> Scored:
    p, fetched, source, bb_note = store.product(asin)
    jan = inp["JAN"]
    per_pt_excl = float(inp["卸単価(税抜)"])
    lot = int(float(inp.get("最小ロット") or 1) or 1)
    site = inp.get("卸サイト") or "不明"
    idx = {jan: {"jan": jan, "unit_price_excl": per_pt_excl, "min_lot_units": lot,
                 "stock": inp.get("在庫") or "", "title": inp.get("卸の商品名") or "",
                 "supplier_name": inp.get("仕入れ先") or "", "supplier_url": inp.get("購入先URL") or ""}}
    row = {"ASIN": asin, "JAN": jan, "商品名": p.get("title") or "",
           "購入先URL": inp.get("購入先URL") or "",
           "卸の1点あたり原価(税込)": round(per_pt_excl * 1.1, 1), "卸の最小ロット(点)": lot,
           "ゲート種別": "未確認"}

    # 発注点数：取り分の3か月分（最小ロットを Amazon 個数に直した数以上）
    n_set, _conf, _src = S.set_count_of(row, p, idx[jan]["title"], lot)
    sale_st, sale_why, m, avg = sales_gate(p, fetched)
    share, share_why = share_of(p, avg)
    lot_amz = ceil_div(lot, float(n_set)) if n_set else lot
    qty = max(lot_amz, math.floor(share * TARGET_MONTHS)) if share else max(lot_amz, 1)
    row["発注点数(Amazon何個)"] = qty
    if share:
        row["売り切る月数"] = round(qty / share, 1)

    cand = {}
    if not (p.get("fbaFees") or {}).get("pickAndPackFee"):
        lv0 = PH.from_product(p)
        tier = S.fba_cost.tier_from_dimensions(p.get("packageLength"), p.get("packageWidth"),
                                               p.get("packageHeight"), p.get("packageWeight"))
        if tier and lv0.sell_for_profit:
            cand["fba_yen"] = S.fba_cost.fba_fee_yen(tier, lv0.sell_for_profit)
    idx_day = inp.get("卸値の確認日") or date.today().isoformat()
    try:
        date.fromisoformat(idx_day)
    except ValueError:
        idx_day = date.today().isoformat()
    s = S.build(row, cand, p, idx, names, idx_day, None, rank_counts)
    g = [x for x in s["gates"] if x[0] not in ("実売", "仕入れ", "季節の窓")]

    # 実売 → キーゾン相当に差し替え（monthlySold は月50個未満だと出ない）
    g.append(("実売", sale_st, sale_why))
    # 取り分（§3.5 #10）。売れていない行に取り分を当てても意味がないので、実売が FAIL なら省く
    few_obs = "観測少" in sale_why
    if sale_st == "FAIL":
        pass
    elif avg is not None and avg < MIN_SHARE and not few_obs:
        # 取り分 ＝ 平均 ÷（出品者＋1）≦ 平均。出品者数を見なくても基準に届かないことが決まる
        g.append(("取り分", "FAIL", f"3か月平均 {avg:g}個/月 で、出品者が自分だけでも取り分は"
                                   f"{MIN_SHARE:g}個/月に届かない（§3.5 #10）"))
    elif sale_st == "UNKNOWN" and p.get("parentAsin") and share is not None and share < MIN_SHARE:
        # family 合計は この ASIN の上限。上限で見ても基準に届かないなら落としてよい
        g.append(("取り分", "FAIL", f"family 合計で見ても取り分 {share:.1f}個/月（基準 {MIN_SHARE:g}）"
                                   f"＝{share_why}。この ASIN 単独ならさらに少ない"))
    elif sale_st == "UNKNOWN":
        g.append(("取り分", "UNKNOWN", "実売が決まらないので取り分も決まらない"
                                      + (f"（参考 {share:.1f}個/月＝{share_why}）" if share else "")))
    elif share is None:
        g.append(("取り分", "UNKNOWN", share_why))
    elif share < MIN_SHARE:
        g.append(("取り分", "FAIL", f"取り分 {share:.1f}個/月（基準 {MIN_SHARE:g}）＝{share_why}"))
    else:
        g.append(("取り分", "PASS", f"取り分 {share:.1f}個/月＝{share_why}"))
    months = row.get("売り切る月数")
    if months and months > MAX_MONTHS:
        g.append(("在庫月数", "FAIL", f"最小ロット {lot}点で在庫 {months}か月（上限 {MAX_MONTHS}）"))

    # 仕入れ（在庫）— 卸サイト名つきで書き直す
    stock = inp.get("在庫") or ""
    if stock == "品切れ":
        g.append(("仕入れ", "FAIL", f"{site} で品切れ（{idx_day} 時点）"))
    elif stock == "在庫あり":
        g.append(("仕入れ", "PASS", f"{site} で在庫あり（{idx_day} 時点・発注直前に取り直す）"))
    else:
        g.append(("仕入れ", "UNKNOWN", f"{site} の在庫が「{stock or '不明'}」（人が卸の画面で見る）"))

    # 季節の窓 — 卸サイト別のリードタイムで引き直す
    e = s.get("econ")
    plan = SC.build(S.TODAY, channel=site, gate_needed=True,
                    months_to_sell=(e.months_to_sell if e else None) or 3.0,
                    peak_months=s["season"].peak_months, season_verdict=s["season"].verdict)
    st = {SC.MISSED: "FAIL", SC.EDGE: "UNKNOWN"}.get(plan.season_window, "PASS")
    g.append(("季節の窓", st, plan.season_note))

    # メーカー本人
    mk_st, mk_why = maker_gate(p, names)
    if mk_st != "PASS":
        g.append(("メーカー本人", mk_st, mk_why))

    # 終売（§3.5 #12）
    # 2026-10-12：終売の印だけでは落とさない。「今だけ」3条件（在庫・在庫月数・価格の傾き）で判定
    stock_st = next((x[1] for x in g if x[0] == "仕入れ"), None)
    lv = s.get("price")
    ctx = DISC.now_only_from(stock_st, months if months else (e.months_to_sell if e else None),
                             lv.verdict if lv else None, S.TODAY)
    d = DISC.check(p, p.get("title"), inp.get("卸の商品名"), inp.get("備考"), fetched,
                   family_alive=family_alive, now_only=ctx)
    if d.verdict != DISC.PASS or d.marked:
        g.append(("終売", {DISC.NO_GO: "FAIL", DISC.PASS: "PASS"}.get(d.verdict, "UNKNOWN"), d.label()))
    s["gates"] = g
    s["disc"] = d

    sts = [x[1] for x in g]
    grade = s.get("等級")
    if s.get("pinned"):
        verdict, bucket = "NO-GO", "落とした"
        g.append(("人の確認", "FAIL", s["pinned"]))
    elif "FAIL" in sts:
        verdict, bucket = "NO-GO", "落とした"
    elif grade in ("A", "B"):
        verdict = "UNKNOWN"   # 機械が全部通しても GO にしない（§3.3-16・§3.5 の人の項目が残る）
        bucket = ("人が見る価値あり（機械項目は全部通過）" if "UNKNOWN" not in sts
                  else "人が見る価値あり（機械で決まらない項目あり）")
    else:
        verdict, bucket = "UNKNOWN", "保留（採算が決まらない）"

    sc = Scored(asin, inp, s, verdict, bucket)
    sc.cells = to_cells(sc, p, fetched, source, bb_note, m, avg, share, jan, ledger)
    return sc


HUMAN_ITEMS = ("#1-2 restrictions/approve（新品の申請経路）・#4 卸の取引条件（Amazon 可否）・"
               "#5 カートの実画面・#7 出品一覧の実数・#8 知財のサイン・#16 JAN と納品物・"
               "#19 FBA可否/危険物・#20 期限")


def first_fail(g: list) -> str:
    for n, st, _ in g:
        if st == "FAIL":
            return n
    for n, st, _ in g:
        if st == "UNKNOWN":
            return f"{n}（未確定）"
    return ""


FIX = {
    "採算": "卸値の安い段（まとめ買い）か、セット数の大きい ASIN なら届くかを見る",
    "取り分": "出品者が減るのを待つ／別の ASIN（セット品）で出す",
    "実売": "季節性なら窓を待つ。通年で0なら見送り",
    "価格の動き": "下落が止まってから再採点（価格は毎回取り直す）",
    "カート保持者": "Amazon 本体の棚は値下げしても取れない＝見送り",
    "終売": "後継品の型番（LED など）で同じ仕入れ先を探す",
    "仕入れ": "再入荷を待つ／同じ JAN を別の卸で探す",
    "季節の窓": "ピークの2か月前に再採点",
    "在庫月数": "最小ロットの小さい卸で同じ JAN を探す",
}


def to_cells(sc: Scored, p: dict, fetched: int, source: str, bb_note: str, m, avg, share,
             jan: str, ledger: set[str]) -> dict:
    s, inp, a = sc.s, sc.inp, sc.asin
    e, lv = s.get("econ"), s.get("price")
    st = p.get("stats") or {}
    oos = st.get("outOfStockPercentage365")
    oos = oos[0] if isinstance(oos, list) and oos else oos
    cur_amz = (st.get("current") or [None])[0]
    bb = p.get("buyBoxEligibleOfferCounts") or []
    g = s["gates"]
    fails = [f"[{n}:{st_}]{why}" for n, st_, why in g if st_ != "PASS"]
    passed = [n for n, st_, _ in g if st_ == "PASS"]
    ff = first_fail(g)
    reason = (f"【等級 {s.get('等級')}】"
              + ("未達：" + " ｜ ".join(fails) + " ｜ " if fails else "機械項目は全部通過 ｜ ")
              + f"通過：{'・'.join(passed)} ｜ 人が見る項目：{HUMAN_ITEMS}")
    cells = {h: "未確認" for h in COLUMNS}
    cells.update({
        "判定日": date.today().isoformat(), "チケットID": TICKET, "ASIN": a,
        "商品名": (p.get("title") or "")[:80], "ブランド": p.get("brand") or "未確認",
        "Amazon URL": f"https://www.amazon.co.jp/dp/{a}",
        "Amazon価格": (lv.sell_for_profit if lv and lv.sell_for_profit else "未確認"),
        "キーゾン 平均月販": f"{avg:g}（Keepa 再現値）" if avg is not None else "未確認",
        "キーゾン 過去1ヶ月": m[0] if m else "未確認", "キーゾン 過去2ヶ月": m[1] if m else "未確認",
        "キーゾン 過去3ヶ月": m[2] if m else "未確認",
        "新品出品者数(画面実数)": (f"未確認（Keepa カート対象：FBA {bb[0]}／自己発送 {bb[1]}）"
                              if len(bb) >= 2 else "未確認"),
        "Amazon本体の有無": ("いま本体の在庫あり" if cur_amz and cur_amz > 0 else "いま本体の在庫なし")
                          + "・実画面未確認",
        "カートの販売元": s.get("カート保持者") or "未確認",
        "本体365日在庫率": (f"{100 - oos}%" if isinstance(oos, int) and 0 <= oos <= 100 else "本体の記録なし"),
        "購入元の名前": inp.get("仕入れ先") or "未確認", "卸サイト": inp.get("卸サイト") or "未確認",
        "購入先URL": inp.get("購入先URL") or "未確認",
        "卸率(売価比)": e.cost_ratio_pct if e else "未確認",
        "発注点数": e.qty if e else "未確認", "発注額(円・税込)": e.order_total if e else "未確認",
        "1個粗利(円)": e.net_per_unit if e else "未確認", "利益率(%)": e.net_margin_pct if e else "未確認",
        "売り切る月数": e.months_to_sell if (e and e.months_to_sell) else "未確認",
        "半値処分時の損失(円)": e.half_disposal_loss if e else "未確認",
        "判定": sc.verdict, "判定理由": reason[:1900],
        "確認方法": (f"機械判定のみ・実画面未確認（supplier_screen.py：Keepa {source} {_day(fetched)}"
                 f"{'・' + bb_note if bb_note else ''}／卸値 {inp.get('卸値の確認日') or '不明'}）"),
        "確認者": "タカシ（機械判定・実画面未確認）", "発注状況": "未発注",
    })
    d = s["disc"]
    cells.update({
        "JAN": jan, "機械の区分": sc.bucket, "等級": s.get("等級"),
        "取り分(個/月)": round(share, 1) if share else "",
        "Amazon側のセット数": s.get("n_set") or "", "セット数の確度": s.get("セット数の確度"),
        "卸の1点あたり原価(税込)": round(float(inp["卸単価(税抜)"]) * 1.1, 1),
        "Amazon1個あたり原価(税込)": (round(float(inp["卸単価(税抜)"]) * 1.1 * float(s["n_set"]))
                                if s.get("n_set") else ""),
        "90日中央値": lv.median90 if lv else "", "90日下位25%": lv.p25_90 if lv else "",
        "価格の判定": lv.verdict if lv else "", "価格の傾き(%/30日)": lv.slope_pct_per_30d if lv else "",
        "季節": s["season"].label(), "悲観の手残り": e.worst_net_per_unit if e else "",
        "終売フラグ": d.verdict, "終売の理由": " ／ ".join(d.reasons),
        "落ちた理由": ff, "こう変えれば": FIX.get(ff.split("（")[0], "") if ff else "",
        "台帳に既存": "既存" if a in ledger else "",
        "卸の備考": inp.get("備考") or "",
    })
    return cells


AUX = ["JAN", "機械の区分", "等級", "取り分(個/月)", "Amazon側のセット数", "セット数の確度",
       "卸の1点あたり原価(税込)", "Amazon1個あたり原価(税込)", "90日中央値", "90日下位25%",
       "価格の判定", "価格の傾き(%/30日)", "季節", "悲観の手残り", "終売フラグ", "終売の理由",
       "落ちた理由", "こう変えれば", "台帳に既存", "卸の備考"]


# ── 台帳の ASIN（重複の印だけ。台帳には触らない）────────────────────────


def ledger_snapshots() -> list[Path]:
    """台帳の実際の状態を写したスナップショット（古い順）。

    before_* はシートから読んだ値、after_* は書き込んだ値。**dry-run の after（after_dryrun.json・
    after_*_dry.json）はシートに書いていない**ので除く（2026-10-14 修正。サトル引き継ぎの既知バグ：
    dry-run で足す予定だった行を「台帳にある」と数え、重複の印が狂っていた）。"""
    snaps = [p for p in LEDGER_SNAP_DIR.glob("after_*.json") if "dry" not in p.stem]
    snaps += list(LEDGER_SNAP_DIR.glob("before_*.json"))
    return sorted(snaps, key=lambda p: p.stat().st_mtime)


def ledger_asins() -> set[str]:
    snaps = ledger_snapshots()
    if not snaps:
        return set()
    rows = json.loads(snaps[-1].read_text())
    i = rows[0].index("ASIN")
    return {r[i] for r in rows[1:] if len(r) > i}


# ── 実行 ─────────────────────────────────────────────────────────────────


def roundrobin(items: list[dict], key: str = "仕入れ先", per: int = PER_SUPPLIER) -> list[dict]:
    """仕入れ先ごとに per 件ずつ交互に並べる（§3.3-34：上限ではなく順番）。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in items:
        groups[r.get(key) or ""].append(r)
    order, qs = [], [list(v) for v in groups.values()]
    while any(qs):
        for q in qs:
            order.extend(q[:per])
            del q[:per]
    return order


def run(input_csv: Path, label: str, tokens: int, floor: int, wait: bool,
        buybox_tokens: int | None = None, log=print) -> dict:
    rows = [r for r in SI.read_input(input_csv) if SI.JAN_RE.match(r["JAN"]) and r["卸単価(税抜)"]]
    by_jan: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_jan[r["JAN"]].append(r)
    log(f"入力 {len(rows):,}行（JAN {len(by_jan):,}）: {input_csv.name}")
    store = KeepaStore(set(by_jan), log=log)

    # 1) 足りない JAN を code 逆引き（キャッシュに無い → キャッシュにあるが未網羅 の順・社ごとに順番）
    if tokens > 0:
        todo_raw = [r for r in rows if r["JAN"] not in store.complete]
        fresh = [r for r in todo_raw if r["JAN"] not in store.by_jan]
        partial = [r for r in todo_raw if r["JAN"] in store.by_jan]
        order = [r["JAN"] for r in roundrobin(fresh) + roundrobin(partial)]
        order = list(dict.fromkeys(order))
        log(f"code 逆引きの待ち行列 {len(order):,} JAN（予算 {tokens}・下限 {floor}）")
        store.resolve_jans(order, tokens, floor, wait)

    names = json.loads(NAMES.read_text()) if NAMES.exists() else {}
    ledger = ledger_asins()
    rc: Counter = Counter()
    for c in store.latest.values():
        cur = (c.product.get("stats") or {}).get("current") or []
        if len(cur) > 3 and cur[3] and cur[3] > 0:
            rc[cur[3]] += 1

    def score_all() -> list[Scored]:
        out = []
        for jan, inps in by_jan.items():
            inp = min(inps, key=lambda r: float(r["卸単価(税抜)"]))   # 同じ JAN が複数あれば安い方
            fam = [a for a in sorted(store.by_jan.get(jan, ())) if a in store.latest]
            alive = {a for a in fam if rank_alive(store.latest[a].product, store.latest[a].fetched)}
            for a in fam:
                out.append(score_asin(a, inp, store, names, dict(rc), ledger,
                                      family_alive=bool(alive - {a})))
        return out

    scored = score_all()

    # 2) 候補にだけ buybox を取り直す（カート・出品者数が無い行）
    bt = tokens - store.tokens_spent if buybox_tokens is None else buybox_tokens
    need = [x.asin for x in scored if x.bucket.startswith("人が見る")
            and not (x.s.get("product") or {}).get("buyBoxEligibleOfferCounts")]
    if need and bt > 0:
        log(f"候補 {len(need)}件の buybox を取り直します（予算 {bt}）")
        before = store.tokens_spent
        store.refresh_buybox(need, before + bt, floor, wait)
        scored = score_all()

    # 3) 出力
    stamp = date.today().strftime("%Y%m%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_all = OUT_DIR / f"screen_{label}_{stamp}.csv"
    out_cand = OUT_DIR / f"candidates_{label}_{stamp}.csv"
    cols = COLUMNS + AUX

    def key(x: Scored):
        e = x.s.get("econ")
        sh = x.cells.get("取り分(個/月)") or 0
        return (not x.bucket.startswith("人が見る"), x.bucket, -((e.net_per_unit if e else 0) * (sh or 1)))
    scored.sort(key=key)
    for path, rs in ((out_all, scored), (out_cand, [x for x in scored if x.bucket.startswith("人が見る")])):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(x.cells for x in rs)

    jan_hit = {j for j in by_jan if store.by_jan.get(j)}
    summ = {
        "入力行": len(rows), "入力JAN": len(by_jan),
        "Keepaに当たったJAN": len(jan_hit),
        "code逆引き済みJAN（セット品まで網羅）": len(store.complete & set(by_jan)),
        "未取得JAN（次回の待ち行列）": len([j for j in by_jan if j not in store.complete]),
        "ASIN": len(scored),
        "機械の区分": dict(Counter(x.bucket for x in scored)),
        "判定": dict(Counter(x.verdict for x in scored)),
        "等級": dict(Counter(str(x.s.get("等級")) for x in scored)),
        "落ちた理由（最初のFAIL）": dict(Counter(first_fail(x.s["gates"]) for x in scored
                                       if x.verdict == "NO-GO")),
        "終売で落ちた": sum(1 for x in scored if x.s["disc"].verdict == DISC.NO_GO),
        "終売疑い": sum(1 for x in scored if x.s["disc"].verdict == DISC.UNKNOWN),
        "消費トークン": store.tokens_spent,
        "出力": [str(out_all), str(out_cand)],
    }
    (OUT_DIR / f"summary_{label}_{stamp}.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    log(json.dumps(summ, ensure_ascii=False, indent=1))
    return summ


# ── 台帳の既存行に終売フラグを当てる（台帳には書かない。CSV を出すだけ）──────────

_ASIN_RE = re.compile(r'"asin":\s*"([A-Z0-9]{10})"')


def load_by_asin(asins: set[str], sources: list[Path] | None = None) -> tuple[dict, dict]:
    """({asin: Cached}, {asin: 同じ JAN を持つ別 ASIN の集合})。2周で読む（1周目は正規表現だけ）。"""
    sources = sources if sources is not None else CACHE_SOURCES + [OWN_CACHE]
    ean_of: dict[str, set[str]] = defaultdict(set)
    jsonl = [p for p in sources if p.exists() and p.suffix == ".jsonl"]
    for path in jsonl:
        with path.open() as f:
            for line in f:
                m = _EAN_RE.search(line)
                a = _ASIN_RE.search(line)
                if m and a:
                    ean_of[a.group(1)] |= {x.strip().strip('"') for x in m.group(1).split(",") if x.strip()}
    want_eans = set().union(*(ean_of.get(a, set()) for a in asins)) if asins else set()
    sib: dict[str, set[str]] = defaultdict(set)
    for a, es in ean_of.items():
        for e in es & want_eans:
            sib[e].add(a)
    need = set(asins) | set().union(*sib.values()) if sib else set(asins)
    latest: dict[str, Cached] = {}
    for path in jsonl:
        with path.open() as f:
            for line in f:
                a = _ASIN_RE.search(line)
                if not a or a.group(1) not in need:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                prods = o.get("products") if "products" in o else [o.get("product")]
                for p in prods or []:
                    if p and p.get("asin") in need:
                        c = Cached(p, int(o.get("fetched") or 0), path.name)
                        if p["asin"] not in latest or c.fetched > latest[p["asin"]].fetched:
                            latest[p["asin"]] = c
    family = {a: set().union(*(sib.get(e, set()) for e in ean_of.get(a, set()))) - {a}
              for a in asins} if asins else {}
    return latest, family


def ledger_flags(out: Path, log=print) -> dict:
    """台帳の最新スナップショットの全行に discontinued.check を当て、印の付いた行を CSV に出す。"""
    snaps = ledger_snapshots()
    rows = json.loads(snaps[-1].read_text())
    head = rows[0]
    recs = [dict(zip(head, r)) for r in rows[1:]]
    asins = {r["ASIN"] for r in recs if r.get("ASIN")}
    log(f"台帳スナップショット {snaps[-1].name}: {len(recs)}行")
    latest, family = load_by_asin(asins)
    idx = json.loads((WORK / "pipeline/netsea_jan_index.json").read_text())["jans"]
    by_url = {(v.get("supplier_url") or "").strip(): v for v in idx.values() if v.get("supplier_url")}
    out_rows, n = [], Counter()
    for r in recs:
        a = r.get("ASIN")
        c = latest.get(a)
        w = by_url.get((r.get("購入先URL") or "").strip()) or {}
        alive = any(rank_alive(latest[x].product, latest[x].fetched) for x in family.get(a, ()) if x in latest)
        d = DISC.check(c.product if c else None, r.get("商品名"), w.get("title") or "",
                       "", c.fetched if c else None, family_alive=alive)
        n[d.verdict] += 1
        if d.verdict == DISC.PASS:
            continue
        kind = ("分類ルール" if d.rule else "") + ("・仕入れ先の記載" if "仕入れ先の記載" in " ".join(d.reasons) else "") \
            + ("・Keepa の兆候" if "兆候" in " ".join(d.reasons) else "")
        out_rows.append({
            "ASIN": a, "商品名": r.get("商品名", ""), "購入元の名前": r.get("購入元の名前", ""),
            "台帳の判定": r.get("判定", ""), "終売フラグ": d.verdict, "根拠の種類": kind.strip("・"),
            "品目": (d.rule.rule.label + (f"（{d.rule.detail}）" if d.rule.detail else "")) if d.rule else "",
            "製造・輸出入の終了": (d.rule.ends or d.rule.rule.ends) if d.rule else "",
            "根拠URL": d.rule.rule.source_url if d.rule else "",
            "理由": " ／ ".join(d.reasons),
            "Keepa の取得日": _day(c.fetched) if c else "キャッシュなし（兆候は見ていない）",
            "推奨": ("「今だけ」3条件を満たさない（§3.5 #12・2026-10-12 方針）。後継品＝LED の同じ仕入れ先を探す"
                   if d.verdict == DISC.NO_GO else
                   ("終売の印あり：仕入れ先の在庫・在庫月数・価格の傾きを確かめれば今だけ仕入れ可（§3.5 #12）"
                    if d.marked else "人がメーカー公式の製品DBで現行品か確認（UNKNOWN）")),
        })
    out_rows.sort(key=lambda x: (x["終売フラグ"] != DISC.NO_GO, x["購入元の名前"], x["商品名"]))
    cols = ["ASIN", "商品名", "購入元の名前", "台帳の判定", "終売フラグ", "根拠の種類", "品目",
            "製造・輸出入の終了", "根拠URL", "理由", "Keepa の取得日", "推奨"]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(out_rows)
    summ = {"台帳行": len(recs), "Keepa キャッシュあり": sum(1 for a in asins if a in latest),
            "判定": dict(n), "台帳でGO/UNKNOWNのまま終売NO-GO": sum(
                1 for x in out_rows if x["終売フラグ"] == DISC.NO_GO and x["台帳の判定"] != "NO-GO"),
            "出力": str(out)}
    log(json.dumps(summ, ensure_ascii=False, indent=1))
    return summ


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("input", type=Path)
    r.add_argument("--label", default="")
    r.add_argument("--tokens", type=int, default=0, help="この実行で使ってよい Keepa トークン（0＝キャッシュだけ）")
    r.add_argument("--buybox-tokens", type=int, default=None)
    r.add_argument("--floor", type=int, default=200, help="残しておく残高（他のジョブのため）")
    r.add_argument("--wait", action="store_true", help="残高が下限を割ったら回復を待つ")
    lf = sub.add_parser("ledger-flags", help="台帳の既存行に終売フラグを当てて CSV に出す（台帳には書かない）")
    lf.add_argument("--out", type=Path,
                    default=LEDGER_SNAP_DIR / f"discontinued_flags_{date.today().strftime('%Y%m%d')}.csv")
    a = ap.parse_args(argv)
    if a.cmd == "ledger-flags":
        ledger_flags(a.out)
        return 0
    run(a.input, a.label or a.input.stem, a.tokens, a.floor, a.wait, a.buybox_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
