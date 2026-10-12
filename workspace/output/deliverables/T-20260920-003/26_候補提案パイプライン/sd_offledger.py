#!/usr/bin/env python3
"""台帳の外にある SD 起点の古い候補を洗い出し、SD の企業別商品一覧（秘書の実画面）と突き合わせる。

2026-10-12 タカシ（T-20260920-003）。社長指摘：
  「SD で卸値が見えているのに、こちらの分析は『想定』の卸値のまま放置されていた」
  （例：サンリオ おせわセット。9/21 の sanrio8 分析が卸率55%の仮置きのまま、台帳にも未登録）

サブコマンド
  list   台帳の外の古い候補プール（sanrio8・sd_lookup_queue*・sd_candidates/sd_shortlist・sd_queue・
         marushin・sd_rows_harvested）から、台帳に無い ASIN を一覧にする
         → agent_output/T-20260920-003/unknown_queue/off_ledger_sd_<日付>.csv
           列：ASIN・JAN・SD出展企業・SD商品URLかID・旧分析の卸値・旧分析の卸値の出どころ・出所ファイル
         JAN だけで ASIN が分からない行は off_ledger_sd_noasin_<日付>.csv に分ける
  match  秘書が SD の企業別商品一覧を読んだ JSON（sd_catalog_<企業ID>_<日付>.json）を、
         NETSEA 索引の同社商品（名前・JAN）と突き合わせる
         - 名前を正規化（NFKC・【…】［…］(…)の除去・空白/記号の除去・小文字）して**完全一致かつ1対1**、
           かつ入数（◯個入・◯本・◯枚 など）が両方で一致した行だけ「採用」
           → sd_buylist20261009/sd_route_override_<日付>_cat<企業ID>.csv（ledger_refresh が読む）
         - 似ているだけ（類似度0.80以上）・入数が食い違う・複数に当たる行は「候補」として出すだけ
           → sd_buylist20261009/sd_catalog_candidates_<企業ID>_<日付>.csv（**自動採用しない**）
         - JAN から ASIN が引けない行は「ASIN 未特定」に分ける（Keepa の JAN 逆引きが要る）

  使い方
    python3 sd_offledger.py list
    python3 sd_offledger.py match --catalog <sd_catalog_204961_20261012.json> --netsea-supplier ハリマ \\
        [--sd-company ハリマ共和物産]

catalog JSON の形（秘書が出す）：配列、または {"items": [...]}。1件は次のキーを持つ（別名も読む）
  SD商品ID（or product_id / id）・商品名（or name）・卸単価（or 卸単価(税抜) / wholesale_price_excl / price）・
  在庫（or stock）・入数（任意）・JAN（任意。あれば名前より優先して JAN で突き合わせる）

守ること
  - SD には一切アクセスしない（§3.3-14）。読むのは秘書の実画面の JSON と手元のファイルだけ
  - 卸値・URL は agent_output にだけ書く（PUBLIC リポ）。このスクリプトは値を持たない
  - 曖昧一致は自動採用しない（単位ずれ・別商品を黒字に見せる事故の型・§3.3-17）
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
SDB = WORK / "sd_buylist20261009"
QDIR = WORK / "unknown_queue"
IDX = WORK / "pipeline/netsea_jan_index.json"
SHEET_ID = "1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I"
CRED = Path.home() / ".config/claude-session-sheets/credentials.json"
TODAY = date.today().strftime("%Y%m%d")
sys.path.insert(0, str(HERE))

FUZZY = 0.80   # 候補として出す類似度の下限（採用には使わない）


# ── 共通 ────────────────────────────────────────────────────────────────

def ledger_asins() -> set[str]:
    import gspread
    from google.oauth2.service_account import Credentials
    gc = gspread.authorize(Credentials.from_service_account_file(
        str(CRED), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    vals = gc.open_by_key(SHEET_ID).worksheet("判定台帳").get_all_values()
    i = vals[0].index("ASIN")
    return {r[i].strip() for r in vals[1:] if len(r) > i and r[i].strip()}


def jan_to_asins() -> dict[str, set[str]]:
    """手元の Keepa 生データの eanList から JAN → ASIN（トークン0）。"""
    import unknown_stages as U
    out: dict[str, set[str]] = {}
    prods = {a: p for a, (p, _) in U.load_products().items()}
    raw = WORK / "sd_lookup_keepa_raw_20261011.json"
    if raw.exists():
        prods.update(json.loads(raw.read_text()))
    s8 = WORK / "sanrio8/raw.json"
    if s8.exists():
        prods.update({p["asin"]: p for p in json.loads(s8.read_text()) if p.get("asin")})
    for a, p in prods.items():
        for j in (p.get("eanList") or []):
            out.setdefault(str(j), set()).add(a)
    return out


def _csv(p: Path) -> list[dict]:
    return list(csv.DictReader(p.open(encoding="utf-8-sig"))) if p.exists() else []


# ── list ────────────────────────────────────────────────────────────────

def collect() -> list[dict]:
    """古い候補プールから (ASIN, JAN, SD出展企業, SD商品URLかID, 旧卸値, 出どころ, 出所) を集める。"""
    rows: list[dict] = []

    def add(src, asin="", jan="", company="", sdref="", price="", price_src="未確認"):
        rows.append({"ASIN": (asin or "").strip(), "JAN": (jan or "").strip(),
                     "SD出展企業": (company or "").strip(), "SD商品URLかID": (sdref or "").strip(),
                     "旧分析の卸値": price, "旧分析の卸値の出どころ": price_src, "出所ファイル": src})

    t = WORK / "sanrio8/table.json"
    if t.exists():
        for x in json.loads(t.read_text()):
            add("sanrio8/table.json（9/21）", x.get("asin"), x.get("ean"), "サンリオ（SD）", "",
                "", "想定（卸率55%の仮置き・sanrio8/calc.py）")
    for name in ("sd_lookup_queue_big_20261011.csv", "sd_lookup_queue_20261011.csv"):
        for r in _csv(WORK / name):
            add(name, r.get("ASIN"), r.get("JAN"), r.get("ブランド"), r.get("SD検索URL"), "",
                "未確認（卸値の上限だけ計算・実額なし）")
    for name in ("sd_candidates_private.csv", "sd_shortlist_private.csv"):
        for r in _csv(SDB / name):
            v = (r.get("卸の1点あたり原価(税込)") or "").strip()
            add(f"sd_buylist20261009/{name}", r.get("ASIN"), "", r.get("購入元の名前"),
                r.get("購入先URL") or r.get("SD品番"), v,
                "旧分析の値（出どころ未記録）" if v else "未確認（非ログイン・卸価格は承認待ち）")
    for r in _csv(SDB / "sd_queue_20261012.csv"):
        add("sd_buylist20261009/sd_queue_20261012.csv", r.get("ASIN"), r.get("JAN"), r.get("SD出展企業"),
            r.get("SD検索URL") or r.get("SD出展ID"), r.get("NETSEA卸1点(税抜・10/01・参考)") or "",
            "NETSEA実額(10/01)の参考値（SD の卸値ではない）")
    for r in _csv(WORK / "marushin/candidates.csv"):
        add("marushin/candidates.csv", r.get("ASIN"), "", f"丸進（{r.get('ブランド群') or ''}）", "", "",
            "未確認（ブランド起点・卸値なし）")
    h = SDB / "sd_rows_harvested.jsonl"
    if h.exists():
        for line in h.open():
            try:
                o = json.loads(line)
            except Exception:
                continue
            w = o.get("wholesale_price_excl")
            add("sd_buylist20261009/sd_rows_harvested.jsonl", "", o.get("jan"),
                (o.get("supplier") or {}).get("name"), o.get("url") or o.get("product_id"),
                w or "", "SD（取得時の値・確認日不明）" if w else "未確認（非ログイン取得）")
    return rows


def cmd_list(a) -> int:
    QDIR.mkdir(parents=True, exist_ok=True)
    have = ledger_asins()
    j2a = jan_to_asins()
    rows = collect()
    out, noasin = {}, {}
    for r in rows:
        asins = {r["ASIN"]} if r["ASIN"] else j2a.get(r["JAN"], set())
        if not asins:
            if r["JAN"]:
                noasin.setdefault(r["JAN"], r)
            continue
        for x in sorted(asins):
            if x in have:
                continue
            rr = dict(r, ASIN=x)
            prev = out.get(x)
            if not prev:
                out[x] = rr
                continue
            # 同じ ASIN が複数のプールにあれば1行にまとめる：出所は全部並べ、SD の参照と JAN は
            # 埋まっている方、卸値は「値がある方 → 出どころが未確認でない方（想定など）」を残す
            prev["出所ファイル"] = " / ".join(dict.fromkeys(prev["出所ファイル"].split(" / ")
                                                       + [rr["出所ファイル"]]))
            for k in ("JAN", "SD出展企業", "SD商品URLかID"):
                prev[k] = prev[k] or rr[k]
            if (not prev["旧分析の卸値"] and rr["旧分析の卸値"]) or (
                    not prev["旧分析の卸値"] and prev["旧分析の卸値の出どころ"].startswith("未確認")
                    and not rr["旧分析の卸値の出どころ"].startswith("未確認")):
                prev["旧分析の卸値"], prev["旧分析の卸値の出どころ"] = rr["旧分析の卸値"], rr["旧分析の卸値の出どころ"]
    cols = ["ASIN", "JAN", "SD出展企業", "SD商品URLかID", "旧分析の卸値", "旧分析の卸値の出どころ", "出所ファイル"]
    p1 = QDIR / f"off_ledger_sd_{TODAY}.csv"
    with p1.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(sorted(out.values(), key=lambda r: (r["出所ファイル"], r["ASIN"])))
    p2 = QDIR / f"off_ledger_sd_noasin_{TODAY}.csv"
    with p2.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(noasin.values())
    from collections import Counter
    print(f"台帳の外の ASIN {len(out)}件 → {p1}")
    print("  出所別（重複あり）:", dict(Counter(f.split("（")[0] for r in out.values()
                                          for f in r["出所ファイル"].split(" / "))))
    print("  旧卸値の出どころ別:", dict(Counter(r["旧分析の卸値の出どころ"].split("（")[0]
                                       for r in out.values())))
    print(f"JAN だけで ASIN 未特定 {len(noasin)}件 → {p2}")
    return 0


# ── match ───────────────────────────────────────────────────────────────

_BRACKETS = re.compile(r"【[^】]*】|［[^］]*］|\[[^\]]*\]|〔[^〕]*〕|＜[^＞]*＞|<[^>]*>")
_UNITS = re.compile(r"(\d+)\s*(個入り?|入り?|本入り?|本|枚入り?|枚|袋入り?|袋|個|包|粒|錠|足|組|セット|p|pcs)",
                    re.I)


def norm(s: str) -> str:
    """名前の正規化：NFKC・【メーカー】等の括弧書き除去・空白と記号の除去・小文字。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = _BRACKETS.sub("", s)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[\s　・/／\-‐－―_,，、。.．:：;；!！?？'\"“”‘’★☆◆◇■□●○※]", "", s)
    return s.lower()


def units(s: str) -> set[str]:
    """入数の手がかり（例 {"12個"}）。比較は数字＋単位の正規化で行う。"""
    s = unicodedata.normalize("NFKC", s or "")
    out = set()
    for n, u in _UNITS.findall(s):
        u = re.sub(r"入り?$", "", u.lower()) or "個"
        out.add(f"{int(n)}{u}")
    return out


def _get(d: dict, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def load_catalog(p: Path) -> list[dict]:
    d = json.loads(p.read_text())
    items = d.get("items") if isinstance(d, dict) else d
    out = []
    for x in items or []:
        pid = str(_get(x, "SD商品ID", "product_id", "id") or "").strip()
        name = str(_get(x, "商品名", "name") or "")
        price = _get(x, "卸単価", "卸単価(税抜)", "wholesale_price_excl", "price")
        try:
            price = float(str(price).replace(",", "").replace("円", "")) if price is not None else None
        except ValueError:
            price = None
        out.append({"id": pid, "name": name, "price": price,
                    "stock": str(_get(x, "在庫", "stock") or ""),
                    "irisu": str(_get(x, "入数", "units") or ""),
                    "jan": str(_get(x, "JAN", "jan") or "").strip()})
    return out


def cmd_match(a) -> int:
    cat_path = Path(a.catalog)
    m = re.search(r"sd_catalog_(\d+)_", cat_path.name)
    cid = m.group(1) if m else "x"
    items = load_catalog(cat_path)
    idx = json.loads(IDX.read_text())["jans"]
    pool = [v for v in idx.values() if a.netsea_supplier in (v.get("supplier_name") or "")]
    by_norm: dict[str, list[dict]] = {}
    for v in pool:
        by_norm.setdefault(norm(v.get("title") or ""), []).append(v)
    j2a = jan_to_asins()
    adopt, cands, no_asin = [], [], []
    for it in items:
        if it["price"] is None:
            cands.append({**_cand(it), "判定": "卸単価が読めない", "NETSEA商品名": "", "JAN": "", "類似度": ""})
            continue
        hits, how = [], ""
        if it["jan"] and it["jan"] in idx:
            hits, how = [idx[it["jan"]]], "JAN 一致"
        elif norm(it["name"]) in by_norm:
            hits, how = by_norm[norm(it["name"])], "名前の完全一致（正規化後）"
        if len(hits) == 1:
            v = hits[0]
            u_sd = units(it["name"] + " " + it["irisu"])
            u_ns = units(v.get("title") or "")
            if u_sd != u_ns and (u_sd or u_ns):
                cands.append({**_cand(it), "判定": f"入数が食い違う（SD {sorted(u_sd)}・NETSEA {sorted(u_ns)}）",
                              "NETSEA商品名": v.get("title"), "JAN": v.get("jan"), "類似度": 1.0})
                continue
            asins = sorted(j2a.get(v.get("jan") or "", set()))
            if not asins:
                no_asin.append({**_cand(it), "判定": f"{how}・ASIN 未特定（Keepa の JAN 逆引きが要る）",
                                "NETSEA商品名": v.get("title"), "JAN": v.get("jan"), "類似度": 1.0})
                continue
            for x in asins:
                adopt.append({"ASIN": x, "JAN": v.get("jan"), "SD品番": it["id"],
                              "購入先URL": f"https://www.superdelivery.com/p/r/pd_p/{it['id']}/",
                              "卸価格_税抜_1点": f"{it['price']:g}", "卸の最小ロット(点)": "1",
                              "在庫": it["stock"], "確認時刻": a.checked_at, "確認者": "カズヨ(Chrome実画面)",
                              "メモ": f"SD 企業{cid} 商品一覧 × NETSEA 索引（{a.netsea_supplier}）{how}・"
                                      f"入数一致 {sorted(units(it['name']))}（タカシ突合）",
                              "卸サイト": "スーパーデリバリー"})
            continue
        if len(hits) > 1:
            for v in hits:
                cands.append({**_cand(it), "判定": f"{how}が複数（{len(hits)}件）＝人が選ぶ",
                              "NETSEA商品名": v.get("title"), "JAN": v.get("jan"), "類似度": 1.0})
            continue
        n = norm(it["name"])
        best = sorted(((SequenceMatcher(None, n, k).ratio(), k) for k in by_norm), reverse=True)[:3]
        hit = [(r, k) for r, k in best if r >= FUZZY]
        if not hit:
            cands.append({**_cand(it), "判定": "NETSEA 索引に該当なし", "NETSEA商品名": "", "JAN": "",
                          "類似度": round(best[0][0], 2) if best else ""})
        for r, k in hit:
            for v in by_norm[k]:
                cands.append({**_cand(it), "判定": "似ているだけ（自動採用しない）",
                              "NETSEA商品名": v.get("title"), "JAN": v.get("jan"), "類似度": round(r, 2)})
    d = a.date or TODAY
    p_adopt = SDB / f"sd_route_override_{d}_cat{cid}.csv"
    if adopt:
        with p_adopt.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, list(adopt[0].keys()))
            w.writeheader()
            w.writerows(adopt)
    p_c = SDB / f"sd_catalog_candidates_{cid}_{d}.csv"
    allc = cands + no_asin
    with p_c.open("w", encoding="utf-8-sig", newline="") as f:
        cols = ["判定", "SD商品ID", "SD商品名", "SD卸単価(税抜)", "在庫", "NETSEA商品名", "JAN", "類似度"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(allc)
    print(f"SD 一覧 {len(items)}件・NETSEA 同社 {len(pool)}件 → 採用 {len(adopt)}行（{p_adopt if adopt else 'なし'}）"
          f"・候補（人が見る）{len(cands)}件・ASIN 未特定 {len(no_asin)}件 → {p_c}")
    return 0


def _cand(it: dict) -> dict:
    return {"SD商品ID": it["id"], "SD商品名": it["name"], "SD卸単価(税抜)": it["price"], "在庫": it["stock"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="台帳の外の SD 候補の洗い出しと、SD 商品一覧の突合")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    m = sub.add_parser("match")
    m.add_argument("--catalog", required=True, help="sd_catalog_<企業ID>_<日付>.json")
    m.add_argument("--netsea-supplier", required=True, help="NETSEA 索引の supplier_name に含まれる語（例 ハリマ）")
    m.add_argument("--checked-at", default=date.today().isoformat() + " 12:00",
                   help="秘書が SD 一覧を読んだ時刻（確認時刻の列に入る）")
    m.add_argument("--date", help="出力ファイルの日付（既定は今日 YYYYMMDD）")
    m.set_defaults(fn=cmd_match)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
