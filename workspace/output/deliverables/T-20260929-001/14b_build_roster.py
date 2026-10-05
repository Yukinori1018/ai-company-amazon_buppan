#!/usr/bin/env python3
"""名簿拡張（09 §3-0）の純増を作り、送信キューのシートに「名簿拡張」タブとして載せる（T-20260929-001）。

    python3 14b_build_roster.py              # 0 token。手元のデータだけで作り直す（シートは触らない）
    python3 14b_build_roster.py --sheet      # 同じものをシートへ（「名簿拡張」タブだけを全置換・社長入力列は保持）
    python3 14b_build_roster.py --bb --sheet # ① の代表 ASIN のカート保持者を取ってから（3 token/社）

経路（09 §3-0-1 論点1 の取得順。1社が複数の経路に出たら、先の経路に置き、残りを「他の経路」に書く）
  ①a Keepa 3,000円以上・月30個相当まで   … 14a_keepa_fetch.py が取った product（tag r14a ＋ サトルの抜き取り r12samp）
  ①b 同・月20個相当まで（①a を除く）     … 同（tag r14b）
  ②  ギフトショー第102回（出展社PDF）＋ RX ライフスタイルWeek 3展（sitemap の社名。サトルが 10/5 に1展1回取得済み）
  ③  ものづくり補助金 一般型 1〜23次の採択企業（消費財のキーワード一致・酒と要冷蔵/要冷凍を除く）

名寄せ（重複を除く相手）
  - 送信キューのシート「メーカー連絡先」タブの全行（正式社名・メーカー名(タカシ)・ブランド）
  - T-20260930-001 の候補 6,725社（除外した社も含む＝一度判定した社を二度入れない）の メーカー名・ブランド
  - 法人番号：T-20260930-001 11_追加候補 の gBiz 法人番号
  社名は法人格・空白・記号・括弧書きを落として完全一致で比べる。包含は使わない
  （10/5 に試したら88件中ほぼ全部が「クリエイト」「グローバル」のような一般語での誤一致だった）。

ハルオ 13 の条件（このスクリプトが守っていること）
  - 名簿（社名の一覧）は agent_output/ と非公開シートにだけ書く。このファイル（PUBLIC）に社名は無い
  - RX は保存済みの社名を読むだけ。出展社詳細ページ・PDF には一切アクセスしない
  - ものづくり補助金の「事業計画名」欄には認定支援機関名（個人名を含む）が混ざっている。
    分類にだけ使い、出力には書かない（社名・法人番号・採択回・分類だけ）
  - ザ・ビジネスモールは使わない
  - 連絡先は載せない（各社の公式サイトから採る＝次の工程。列「窓口」は「未採取」）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
T1 = HERE.parent / "T-20260930-001"
sys.path.insert(0, str(T1))
import keepa_io  # noqa: E402
import maker_rules as R  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("b30", T1 / "30_build.py")
B = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(B)  # facts / self_cart を流用

_s37 = importlib.util.spec_from_file_location("l37", T1 / "37_listed_dedup.py")
L37 = importlib.util.module_from_spec(_s37); _s37.loader.exec_module(L37)   # JPX 上場照合（listed / _boundary_ok）

AO = keepa_io.RAW.parent.parent                      # workspace/output/agent_output
W1 = AO / "T-20260930-001"
WORK = AO / "T-20260929-001"
CALC = WORK / "12_calc"
OUT = WORK / "14_roster"

SHEET_ID = "1FyKBUHG4sRQG6lgV0mXDpotWUWIvG6zt00YaCoinvPI"   # T-20260930-001 の送信キュー型シート
MAIN_TAB = "メーカー連絡先"
TAB = "名簿拡張"
CRED = os.path.expanduser("~/.config/claude-session-sheets/credentials.json")
OWNER_COLS = ["接触ステータス", "接触日", "メモ"]           # 社長・送信担当が書く列。作り直しても消さない

PRICE_MIN = 3_000
JPX = OUT / "data_j.xlsx"   # JPX「東証上場銘柄一覧」（公開・無料）。T-20260930-001 37_ と同じ版
CUTS = json.loads((CALC / "rank_cut.json").read_text())


# ---------------------------------------------------------------- 社名の正規化
LEG = re.compile(r"(株式会社|有限会社|合同会社|合資会社|合名会社|\(株\)|\(有\)|\(同\)|㈱|㈲|"
                 r"co\.?,?\s*ltd\.?|inc\.?|corporation|corp\.?|ltd\.?|llc)", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = LEG.sub("", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    return re.sub(r"[\s・\.\-,'’&/　]", "", s)


class Index:
    """重複判定用の社名・法人番号の索引。"""

    def __init__(self):
        self.names: set[str] = set()
        self.corps: set[str] = set()

    def add(self, name: str = "", corp: str = "") -> None:
        n = norm(name)
        if len(n) >= 2 and n not in self.names:
            self.names.add(n)
        if re.fullmatch(r"\d{13}", corp or ""):
            self.corps.add(corp)

    def hit(self, names: list[str], corp: str = "") -> str:
        if corp and corp in self.corps:
            return "法人番号"
        for name in names:
            n = norm(name)
            if len(n) < 2:
                continue
            if n in self.names:
                return "社名一致"
        return ""


def existing_index() -> tuple[Index, dict]:
    ix, src = Index(), Counter()
    for r in csv.DictReader((W1 / "10_メーカー候補_完全版.csv").open(encoding="utf-8-sig")):
        for k in [r["メーカー名"], *r["ブランド"].split(" / ")]:
            ix.add(k)
        src["候補6725"] += 1
    for r in csv.DictReader((W1 / "11_追加候補.csv").open(encoding="utf-8-sig")):
        ix.add(r["メーカー名"], r.get("法人番号(gBiz)", ""))
    try:
        import gspread
        ws = gspread.service_account(CRED).open_by_key(SHEET_ID).worksheet(MAIN_TAB)
        vals = ws.get_all_values()
        h = vals[0]
        for row in vals[1:]:
            d = dict(zip(h, row))
            for k in ("正式社名", "メーカー名(タカシ)", "ブランド"):
                for part in re.split(r"[／/]", d.get(k, "")):
                    ix.add(part.strip())
            src["シート行"] += 1
    except Exception as e:  # シートが読めなくても候補6,725社で名寄せはできる（記録に残す）
        src["シート読めず:" + type(e).__name__] += 1
    return ix, dict(src)


def band(price) -> str:
    if not price:
        return "不明（Amazon 売価なし）"
    return ("1万円以上" if price >= 10_000 else "5,000〜1万円" if price >= 5_000
            else "3,000〜5,000円" if price >= 3_000 else "2,200〜3,000円")


# ---------------------------------------------------------------- 経路①
def route1(fetch_bb: bool) -> tuple[list[dict], dict]:
    order_a = set(json.loads((keepa_io.RAW / "order_r14a.json").read_text()))
    root_of = json.loads((OUT / "r14_root_of.json").read_text())
    ps, seen, stat = [], set(), Counter()
    samp = [a for a, _ in json.loads((CALC / "q1_sample_asins.json").read_text())]
    for tag, fn in (("r14a", "order_r14a_fetch.json"), ("r14b", "order_r14b_fetch.json")):
        f = keepa_io.RAW / fn
        if f.exists():
            for p in keepa_io.products(json.loads(f.read_text()), tag, offline=True):
                if p["asin"] not in seen:
                    seen.add(p["asin"]); ps.append(p)
    for p in keepa_io.products(samp, "r12samp", offline=True):
        if p["asin"] not in seen and p["asin"] in root_of:
            seen.add(p["asin"]); ps.append(p)
    stat["product 取得済み"] = len(ps)
    stat["①a の対象ASIN"] = len(order_a)

    alive = []
    for p in ps:
        f = B.facts(p)
        cut = CUTS.get(str(f["root"]))
        if f["oos_amz"] < 90:
            stat["落：本体の365日在庫切れ率<90%"] += 1; continue
        if not cut or f["rank"] is None or f["rank"] > cut["R20"]:
            stat["落：ランクが月20個相当を超えた（取得時点で再判定）"] += 1; continue
        if not (f["fba"] is not None and (f["fba"] >= 2 or (f["fba"] >= 1 and (f["offers"] or 0) >= 2))):
            stat["落：FBA/オファー条件"] += 1; continue
        if f["price"] is None or f["price"] < PRICE_MIN:
            stat["落：売価<3,000円"] += 1; continue
        f["route"] = "①a" if (p["asin"] in order_a or f["rank"] <= cut["R30"]) else "①b"
        alive.append((p, f))
    stat["条件を通ったASIN"] = len(alive)

    groups: dict[str, list] = defaultdict(list)
    for p, f in alive:
        k, name = R.maker_key(p)
        groups[k].append((p, f, name))
    rows = []
    for k, items in groups.items():
        rep_p, rep_f, name = max(items, key=lambda x: ((x[1]["ms"] or 0), -(x[1]["rank"] or 10**9)))
        excl, why, rescue = R.classify(rep_p, [x[0] for x in items])
        if excl:
            stat["除外（社）:" + excl] += 1; continue
        route = "①a" if any(f["route"] == "①a" for _, f, _ in items) else "①b"
        rows.append({
            "_p": rep_p, "経路": route, "社名": name,
            "ブランド": " / ".join(dict.fromkeys((p.get("brand") or "").strip() for p, _, _ in items if p.get("brand")))[:60],
            "法人番号": "", "出典": "Keepa（入口(a)・3,000円以上・ランク換算）",
            "分類": R.ROOT_NAMES.get(rep_f["root"], str(rep_f["root"])),
            "代表ASIN": rep_f["asin"], "Amazon URL": f"https://www.amazon.co.jp/dp/{rep_f['asin']}",
            "過去1ヶ月の販売数(代表)": rep_f["ms"] if rep_f["ms"] else "表示なし（月50個未満）",
            "代表の売価": rep_f["price"], "売価帯": band(rep_f["price"]), "該当ASIN数": len(items),
            "代表の新品オファー数": rep_f["offers"], "カート保持セラー(代表)": "", "要確認": "",
            "確度メモ": "Amazon 出店あり。月20〜49個はランクからの推測",
        })
    stat["残した社（名寄せ前）"] = len(rows)
    return rows, dict(stat)


def cart_check(rows: list[dict], fetch_bb: bool) -> None:
    """① の代表 ASIN のカート保持者（CLAUDE.md §3.3-5：メーカー本人がカートを持つ棚は避ける）。"""
    bbp = keepa_io.products_buybox([r["代表ASIN"] for r in rows], offline=not fetch_bb)
    sids = [((bbp.get(r["代表ASIN"]) or {}).get("stats") or {}).get("buyBoxSellerId") for r in rows]
    names = keepa_io.sellers([s for s in sids if s], offline=not fetch_bb)
    for r, sid in zip(rows, sids):
        if r["代表ASIN"] not in bbp:
            r["要確認"] = "カート保持者 未取得"; continue
        p = r["_p"]
        seller = names.get(sid or "", "") or (sid or "")
        if sid == "AN1VRQENFRJN5":
            seller = "Amazon.co.jp"
        r["カート保持セラー(代表)"] = seller
        r["要確認"] = B.self_cart(seller, p.get("brand") or "", p.get("manufacturer") or "", r["代表の新品オファー数"])
        if seller == "Amazon.co.jp":
            r["要確認"] = "要確認：カートが Amazon 本体（取得時点）"


# ---------------------------------------------------------------- 経路②
FOREIGN = re.compile(r"(CO\.,?\s*LTD|LIMITED|INC\.?|LLC|CORP|PTE|SDN|GMBH|S\.?A\.?$)", re.I)
ORG = re.compile(r"(商工会議所|商工会$|商工会／|商工会 |協同組合|工業会|協会|連合会|振興会|振興機構|推進機構|"
                 r"promotion|県$|市$|町$|村$|大学|高校|高等学校|専門学校|JETRO|ジェトロ|公社|財団|"
                 r"組合連合|農業協同組合|漁業協同組合|観光|物産振興)", re.I)
EXCL_CAT = re.compile(r"(出版|書店|レコード|ミュージック|音楽|ゲーム|DVD|CD|書房|文庫|新聞社)")
TRADING = re.compile(r"(貿易|インポート|IMPORT|商事|輸入|ディストリビュー|エージェンシー|代理店|コンサル|"
                     r"マーケティング|デザイン事務所|デザイン研究室|広告)", re.I)


def ex_class(name: str) -> str:
    n = unicodedata.normalize("NFKC", name)
    jp_corp = re.search(r"株式会社|有限会社|合同会社|㈱|㈲|\(株\)|\(有\)", n)  # 英字名でも日本の法人格なら国内
    if not jp_corp and FOREIGN.search(n) or sum(1 for c in n if ord(c) < 128) / max(1, len(n)) > 0.7 and not jp_corp:
        return "海外表記"
    if ORG.search(n):
        return "団体・自治体・教育機関"
    if EXCL_CAT.search(n):
        return "除外カテゴリ（版元・音楽・ゲーム）"
    return ""


def route2() -> tuple[list[dict], dict]:
    stat = Counter()
    gb = {}
    for r in csv.DictReader((AO / "T-20260906-005/11_gbiz_enriched.csv").open(encoding="utf-8-sig")):
        if r["match_type"] == "exact1":
            gb[r["exhibitor"]] = (r["corporate_number"], r["company_url"])
    rows, seen = [], set()
    src = [(r["exhibitor"].strip(), "ギフトショー第102回")
           for r in csv.DictReader((AO / "T-20260831-005/tigs102_出展社リスト_全件.csv").open(encoding="utf-8"))]
    show = {"summer": "RX 夏", "autumn": "RX 秋", "spring": "RX 春"}
    src += [(n.strip(), show.get(s, "RX " + s)) for n, s in json.loads((CALC / "rx_pass.json").read_text())]
    stat["生の社名（GS 2,353＋RX 日本語社名）"] = len(src)
    for name, where in src:
        if not name:
            continue
        n = norm(name)
        if n in seen:
            stat["②の中の重複（GS∩RX ほか）"] += 1; continue
        seen.add(n)
        c = ex_class(name)
        if c:
            stat["除外：" + c] += 1; continue
        corp, url = gb.get(name, ("", ""))
        rows.append({"経路": "②", "社名": name, "法人番号": corp, "出典": where,
                     "分類": "商社・輸入元" if TRADING.search(unicodedata.normalize("NFKC", name)) else "",
                     "公式サイトURL(gBiz)": url, "売価帯": band(None),
                     "確度メモ": "消費財メーカーの割合 GS 93%・RX 75%（サトル12の抜き取り）"})
    stat["残した社（名寄せ前）"] = len(rows)
    return rows, dict(stat)


# ---------------------------------------------------------------- 経路③
SAKE = re.compile(r"酒造|日本酒|清酒|焼酎|泡盛|ワイン|ワイナリー|ビール|ブルワリー|ブルーイング|ウイスキー|ウィスキー|"
                  r"クラフトジン|ジン蒸留|リキュール|梅酒|蒸留|酒類|どぶろく|シードル|酒蔵|蔵元")
BREW = re.compile(r"醸造")
NOT_SAKE_BREW = re.compile(r"醤油|しょうゆ|味噌|みそ|酢|麹|こうじ|調味")
COLD = re.compile(r"冷凍|冷蔵|チルド|凍結|生鮮|鮮魚|精肉|刺身|生肉|アイスクリーム|ジェラート")
# 消費財キーワードに当たったが、明らかに業務用・設備・サービスのもの（目視で多かった型）
NOISE = re.compile(r"畳|病室|施設用|造作|業務用|搾乳|コンクリート|ＶＲ|VR|プラットフォーム|マッチング|"
                   r"システムの開発|ＥＲＰ|半製品|受託|下請|加工設備|洗浄構造")


def route3() -> tuple[list[dict], dict]:
    stat = Counter()
    rows_in = json.loads((CALC / "mono_cls.json").read_text())
    stat["採択の行（1〜23次）"] = len(rows_in)
    by: dict[str, dict] = {}
    for r in rows_in:
        if not r["hit"]:
            continue
        text = r["plan"] + " " + r["name"]          # 分類にだけ使う（出力しない）
        key = r["corp"] if re.fullmatch(r"\d{13}", r["corp"]) else "N:" + norm(r["name"])
        g = by.setdefault(key, {"name": r["name"], "corp": r["corp"], "rounds": set(), "cats": Counter(),
                                "sake": False, "cold": False, "noise": 0, "n": 0})
        g["rounds"].add(r["round"]); g["cats"][r["cats"][0]] += 1; g["n"] += 1
        g["name"] = r["name"] if r["round"] >= max(g["rounds"]) else g["name"]
        if SAKE.search(text) or (BREW.search(text) and not NOT_SAKE_BREW.search(text)):
            g["sake"] = True
        if COLD.search(text):
            g["cold"] = True
        if NOISE.search(text):
            g["noise"] += 1
    stat["消費財キーワード一致（社）"] = len(by)
    out = []
    for key, g in by.items():
        if g["sake"]:
            stat["除外：酒（論点4）"] += 1; continue
        if g["cold"]:
            stat["除外：要冷蔵・要冷凍（論点4）"] += 1; continue
        if g["noise"] == g["n"]:
            stat["除外：業務用・設備・サービス"] += 1; continue
        cat = g["cats"].most_common(1)[0][0]
        corp = g["corp"] if re.fullmatch(r"\d{13}", g["corp"]) else ""
        out.append({"経路": "③", "社名": g["name"], "法人番号": corp,
                    "出典": "ものづくり補助金 " + "・".join(f"{x}次" for x in sorted(g["rounds"])),
                    "分類": cat, "売価帯": band(None),
                    "確度メモ": ("食品・飲料（目視の適合 71%）" if cat == "食品・飲料" else "非食品（目視の適合 33%）")
                    + ("" if corp else "・法人番号なし（個人事業主の可能性＝個人情報として扱う）")})
    stat["残した社（名寄せ前）"] = len(out)
    return out, dict(stat)


# ---------------------------------------------------------------- 統合
COLS = ["経路", "他の経路", "売価帯", "社名", "法人番号", "ブランド", "出典", "分類", "確度メモ",
        "代表ASIN", "Amazon URL", "過去1ヶ月の販売数(代表)", "代表の売価", "該当ASIN数",
        "カート保持セラー(代表)", "要確認", "公式サイトURL(gBiz)", "窓口", *OWNER_COLS]
BAND_ORDER = {"1万円以上": 0, "5,000〜1万円": 1, "3,000〜5,000円": 2, "2,200〜3,000円": 3, "不明（Amazon 売価なし）": 4}
ROUTE_ORDER = {"①a": 0, "①b": 1, "②": 2, "③": 3}


def listed_check():
    """(社名リスト) → ("除外" | "疑い" | "", 根拠)。完全一致は大手として落とし、子会社の前方一致は印だけ。"""
    if not JPX.exists():
        return lambda names: ("", "")
    exact, cores = L37.listed(str(JPX))
    nm = L37.nm

    def f(names):
        keys = [nm.match_key(x) for x in names if x]
        hit = next((exact[k] for k in keys if k in exact), "")
        if hit and min(len(k) for k in keys if k in exact) > 4:   # 4文字以下は同名別会社が普通にいる（37_ の注記）
            return "除外", hit
        mk = keys[0] if keys else ""
        par = next((t for c, t in cores if mk.startswith(c) and len(mk) > len(c) and L37._boundary_ok(mk, c)), "")
        if hit:
            return "疑い", f"上場と同名（社名が短い・同名別会社の可能性）：{hit}"
        return ("疑い", f"上場子会社の疑い：親 {par}") if par else ("", "")
    return f


def merge(parts: list[list[dict]], ex: Index) -> tuple[list[dict], dict]:
    stat = Counter()
    is_listed = listed_check()
    out: list[dict] = []
    by_name: dict[str, dict] = {}
    by_corp: dict[str, dict] = {}
    for rows in parts:
        for r in rows:
            names = [r["社名"], *[b for b in (r.get("ブランド") or "").split(" / ") if b]]
            h = ex.hit(names, r.get("法人番号", ""))
            if h:
                stat[f"{r['経路']} 既存と重複（{h}）"] += 1; continue
            inner = [x for nme in names for x in re.findall(r"[（(]([^)）]+)[)）]", nme)]  # 「英字名 (カタカナ名)」の括弧内も上場照合に使う
            lv, why = is_listed(names + inner)
            if lv == "除外":
                stat[f"{r['経路']} 除外（上場）"] += 1; continue
            if lv == "疑い":
                r["要確認"] = "・".join(x for x in [r.get("要確認"), "要確認：" + why] if x)
            n = norm(r["社名"])
            prev = by_corp.get(r.get("法人番号") or "-") or by_name.get(n)
            if prev is not None:
                if r["経路"] not in (prev.get("他の経路") or "").split("・") and r["経路"] != prev["経路"]:
                    prev["他の経路"] = "・".join(x for x in [prev.get("他の経路"), r["経路"]] if x)
                if not prev.get("法人番号") and r.get("法人番号"):
                    prev["法人番号"] = r["法人番号"]
                stat[f"{r['経路']} 先の経路と重複"] += 1; continue
            r.setdefault("他の経路", ""); r["窓口"] = "未採取（各社の公式サイトから採る）"
            r["_n"] = n
            out.append(r)
            by_name[n] = r
            if r.get("法人番号"):
                by_corp[r["法人番号"]] = r
            stat[f"{r['経路']} 純増"] += 1
    out.sort(key=lambda r: (ROUTE_ORDER[r["経路"]], BAND_ORDER[r["売価帯"]],
                            -(r.get("代表の売価") or 0) if r["経路"].startswith("①") else 0))
    return out, dict(stat)


def to_sheet(rows: list[dict]) -> dict:
    import gspread
    sh = gspread.service_account(CRED).open_by_key(SHEET_ID)
    titles = [w.title for w in sh.worksheets()]
    keep: dict[tuple, dict] = {}
    if TAB in titles:
        ws = sh.worksheet(TAB)
        vals = ws.get_all_values()
        if vals:
            h = vals[0]
            owner_idx = [h.index(c) for c in OWNER_COLS if c in h]
            has_owner = any(v[i] for v in vals[1:] for i in owner_idx if i < len(v))
            if h != COLS and has_owner:
                raise SystemExit(f"「{TAB}」の見出しが想定と違うので中止（手で直された可能性）: {h[:6]}…")
            for v in vals[1:]:
                d = dict(zip(h, v))
                if h == COLS and any(d.get(c) for c in OWNER_COLS):
                    keep[(d["経路"], norm(d["社名"]))] = {c: d.get(c, "") for c in OWNER_COLS}
    else:
        ws = sh.add_worksheet(title=TAB, rows=len(rows) + 10, cols=len(COLS))
    body = [COLS]
    kept = 0
    for r in rows:
        o = keep.get((r["経路"], norm(r["社名"])), {})
        kept += bool(o)
        body.append([("" if r.get(c) is None else r.get(c)) if c not in OWNER_COLS else o.get(c, "") for c in COLS])
    # 社長入力のある行が今回消えるなら中止（名寄せの相手が変わって行が消えた等。黙って捨てない）
    lost = len(keep) - kept
    if lost:
        raise SystemExit(f"社長入力のある {lost} 行が新しい名簿に無いので中止")
    ws.resize(rows=max(len(body), 2), cols=len(COLS))
    ws.clear()
    for i in range(0, len(body), 2000):
        ws.update(values=body[i:i + 2000], range_name=f"A{i + 1}", value_input_option="RAW")
    ws.freeze(rows=1)
    ws.set_basic_filter(f"A1:{gspread.utils.rowcol_to_a1(len(body), len(COLS))}")
    return {"rows": len(body) - 1, "owner_rows_kept": kept, "gid": ws.id}


RECORD = HERE / "14_名簿拡張の実行記録.md"
AUTO_A, AUTO_B = "<!-- AUTO:14b ここから -->", "<!-- AUTO:14b ここまで -->"


def write_record(summary: dict) -> None:
    """実行記録（PUBLIC）の自動欄を件数だけで書き直す。社名は書かない。"""
    if not RECORD.exists():
        return
    s1, sm = summary["①"], summary["統合"]
    lines = [AUTO_A, "", f"最終更新：{time.strftime('%Y-%m-%d %H:%M')}（14b_build_roster.py が自動で書き換える欄）", "",
             "| 経路 | 名寄せ前 | 既存と重複 | 先の経路と重複 | **純増** |", "|---|---:|---:|---:|---:|"]
    pre = {"①a": None, "①b": None, "②": summary["②"]["残した社（名寄せ前）"], "③": summary["③"]["残した社（名寄せ前）"]}
    for k in ("①a", "①b", "②", "③"):
        dup = sum(v for kk, v in sm.items() if kk.startswith(k + " 既存と重複")) + s1.get("既存と重複", {}).get(k, 0)
        if k.startswith("①"):
            pre[k] = s1.get("名寄せ前", {}).get(k, 0)
        lines.append(f"| {k} | {pre[k] if pre[k] is not None else '—'} | {dup} | {sm.get(k + ' 先の経路と重複', 0)} | **{sm.get(k + ' 純増', 0)}** |")
    lines += ["", f"① の取得：product {s1.get('product 取得済み', 0):,} 件（①a 対象 {s1.get('①a の対象ASIN', 0):,} ASIN）・"
              f"条件を通った ASIN {s1.get('条件を通ったASIN', 0):,}・残した社（名寄せ前）{s1.get('残した社（名寄せ前）', 0):,}・"
              f"カート未取得 {s1.get('カート：未取得', 0)}・本人/本体カートの疑い {s1.get('カート：本人・Amazon 本体の疑い（除外せず要確認）', 0)}", "",
              "| 経路 | 売価帯 | 社数 |", "|---|---|---:|"]
    for k, v in sorted(summary["経路×売価帯"].items()):
        a, b_ = k.split("|")
        lines.append(f"| {a} | {b_} | {v} |")
    if summary.get("シート"):
        lines += ["", f"シート「{TAB}」：{summary['シート']['rows']:,} 行（社長入力を保持した行 {summary['シート']['owner_rows_kept']}）"]
    lines += ["", AUTO_B]
    t = RECORD.read_text()
    if AUTO_A in t and AUTO_B in t:
        t = t[:t.index(AUTO_A)] + "\n".join(lines) + t[t.index(AUTO_B) + len(AUTO_B):]
        RECORD.write_text(t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bb", action="store_true", help="① の代表 ASIN のカート保持者を Keepa で取る（3 token/社）")
    ap.add_argument("--sheet", action="store_true", help="シートの「名簿拡張」タブへ書く")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ex, ex_src = existing_index()
    r1, s1 = route1(a.bb)
    r2, s2 = route2()
    r3, s3 = route3()
    # ① は名寄せしてからカート保持者を取る（既存社の分の token を使わない）
    s1["名寄せ前"] = dict(Counter(r["経路"] for r in r1))
    r1d = [r for r in r1 if not ex.hit([r["社名"], *[b for b in r["ブランド"].split(" / ") if b]])]
    s1["既存と重複"] = dict(Counter(r["経路"] for r in r1) - Counter(r["経路"] for r in r1d))
    r1 = r1d
    cart_check(r1, a.bb)
    s1["カート：本人・Amazon 本体の疑い（除外せず要確認）"] = sum(1 for r in r1 if r["要確認"].startswith("要確認"))
    s1["カート：未取得"] = sum(1 for r in r1 if r["要確認"] == "カート保持者 未取得")
    rows, sm = merge([[r for r in r1 if r["経路"] == "①a"], [r for r in r1 if r["経路"] == "①b"], r2, r3], ex)
    for r in rows:
        r.pop("_p", None); r.pop("_n", None)
    with (OUT / "14_名簿拡張_純増.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    summary = {"名寄せの相手": ex_src, "①": s1, "②": s2, "③": s3, "統合": sm,
               "経路×売価帯": {f"{k[0]}|{k[1]}": v for k, v in Counter((r["経路"], r["売価帯"]) for r in rows).items()},
               "①の要確認(純増)": dict(Counter((r["経路"], r["要確認"][:20]) for r in rows if r["経路"].startswith("①")).most_common(8))}
    summary["①の要確認(純増)"] = {f"{k[0]}|{k[1]}": v for k, v in summary["①の要確認(純増)"].items()}
    if a.sheet:
        summary["シート"] = to_sheet(rows)
    (OUT / "14_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    write_record(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
