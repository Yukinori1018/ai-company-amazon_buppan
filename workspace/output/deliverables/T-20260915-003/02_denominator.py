# -*- coding: utf-8 -*-
"""既存データだけでメーカーの分母を数える（T-20260915-003 タカシ分）。

API は一切呼ばない。入力はすべて取得済みのファイル:
  T-1   deliverables/T-20260914-002/out/t1_all.csv          （Keepa 取得済み・3,385 ASIN）
  展示会 deliverables/T-20260906-005/20_出展社2353件の機械分類.csv
  NETSEA deliverables/T-20260831-006/out/netsea_items.jsonl  （取引中サプライヤーの全商品）
         agent_output/T-20260831-006/netsea_取引申請状況_480社.csv
         deliverables/T-20260915-001/out/categories.json     （カテゴリ名）

出力: 集計を標準出力と out/summary.json に、社名入りの明細を out/*.csv に（Git 追跡外）。
社名の照合は T-20260831-001 の normalize.py（法人格・和英併記・記号を落とした照合キー）を使う。
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
DLV = REPO / "workspace/output/deliverables"
OUT = DLV / "T-20260915-003/out"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(DLV / "T-20260831-001"))
from pipeline.normalize import extract_variants, match_key, split_scripts, strip_legal_form  # noqa: E402

MONTHLY = 300  # 型Aの実践者の送信数（T-20260915-002/01 の下限）

# ---------------------------------------------------------------- 照合キー
_NOISE = {"株式会社", "有限会社", "合同会社", "ノーブランド品", "ノーブランド", "noname", "generic",
          "不明", "その他"}
# 文字種で割った断片に出てくる一般語。初回実行でこれが誤一致を起こした
# （XX商事↔YY商事、XX商会↔YY商会、XX企画↔YY企画、…ジャパン、…(HONGKONG)、…SHOP、…公式店 の型で約10組）。
_GENERIC = {match_key(w) for w in (
    "商事", "商会", "企画", "ジャパン", "japan", "shop", "ショップ", "公式", "公式店", "店", "ストア", "store",
    "hongkong", "工業", "産業", "製作所", "研究所", "本舗", "商店", "トイズ", "toys", "group", "グループ",
    "インターナショナル", "international", "trading", "トレーディング", "デザイン", "design",
    "プロダクツ", "products", "netsea", "creation", "クリエイション", "コーポレーション", "corporation")}


def keys_of(name: str) -> set[str]:
    """社名から照合キーの集合を作る。

    全体キーと、括弧・スラッシュの別名はそのまま使う。文字種の境界で割った断片
    （'XX商事' → '商事'）は一般語になりやすいので、一般語リストに無く、
    和文3文字以上・英字4文字以上のときだけ使う。
    """
    if not name or not name.strip():
        return set()
    primary, aliases = extract_variants(name)
    frags = set(split_scripts(primary))
    noise = {match_key(n) for n in _NOISE}
    out = set()
    for v in [primary, *aliases]:
        k = match_key(strip_legal_form(v))
        if not k or k in noise or k in _GENERIC:
            continue
        ascii_only = all(ord(c) < 128 for c in k)
        min_len = (4 if ascii_only else 3) if v in frags else (4 if ascii_only else 2)
        if len(k) >= min_len:
            out.add(k)
    return out


# ---------------------------------------------------------------- 統一カテゴリ
# 3つのソースはカテゴリ体系が違う。粗い共通バケットに寄せる（寄せ方は下の表がすべて）。
AMZ2B = {
    "ホーム＆キッチン": "キッチン・日用品", "ペット用品": "ペット",
    "家電＆カメラ": "家電・PC", "パソコン・周辺機器": "家電・PC", "大型家電": "家電・PC",
    "楽器・音響機器": "家電・PC",
    "車＆バイク": "車・DIY・工具", "DIY・工具・ガーデン": "車・DIY・工具", "産業・研究開発用品": "車・DIY・工具",
    "スポーツ＆アウトドア": "スポーツ・ホビー・玩具", "おもちゃ": "スポーツ・ホビー・玩具",
    "ホビー": "スポーツ・ホビー・玩具",
    "ファッション": "ファッション", "文房具・オフィス用品": "文具・事務・店舗用品",
    "ベビー＆マタニティ": "ベビー",
}
NETSEA2B = {
    "日用雑貨": "キッチン・日用品", "家具・インテリア": "家具・インテリア",
    "家電・PC・AV機器": "家電・PC", "ホビー・スポーツ": "スポーツ・ホビー・玩具",
    "ファッショングッズ": "ファッション", "レディースアパレル": "ファッション", "メンズアパレル": "ファッション",
    "中国発レディスファッション": "ファッション", "中国発メンズファッション": "ファッション",
    "美容・健康": "美容・健康", "食品・飲料": "食品", "店舗用品・事務用品": "文具・事務・店舗用品",
}
# ギフトショーは出展社名とブースしか無い。ホール＝併催展でしか分けられない。
HALL2B = {"東1": "食品", "西1": "家具・インテリア", "西3": "家具・インテリア", "西4": "家具・インテリア"}
HALL_DEFAULT = "ギフト・生活雑貨（未分類）"
HALL_SHOW = {"東1": "グルメショー", "西1": "LxD", "西3": "LxD", "西4": "LxD・L&D"}

# ---------------------------------------------------------------- T-1
t1 = list(csv.DictReader(open(DLV / "T-20260914-002/out/t1_all.csv", encoding="utf-8-sig")))
t1 = [r for r in t1 if r["段6再判定"] == "OK"]


def t1_company(r):
    """T-1 漏斗（t1_build.py）と同じ会社の単位: nrm(メーカー or ブランド)。これで 2,127／994 が再現する。"""
    s = unicodedata.normalize("NFKC", (r["メーカー"] or r["ブランド"] or "")).lower()
    return re.sub(r"[^0-9a-z぀-ゟ゠-ヿ一-鿿]", "", s).replace("・", "")


def t1_display(rows):
    """照合に使う社名: 行に出てくる生表記（メーカー or ブランド）のうち最頻のもの。括弧の別名を保つため生のまま。"""
    return Counter((r["メーカー"] or r["ブランド"]).strip() for r in rows).most_common(1)[0][0]


t1_all_co = {t1_company(r) for r in t1 if t1_company(r)}
t1_target = [r for r in t1 if r["区分"] == "国内" and not r["大手"]]
t1_target_co = {t1_company(r) for r in t1_target if t1_company(r)}

t1_cat = defaultdict(lambda: {"asin": 0, "co": set(), "co_target": set(), "asin_target": 0})
for r in t1:
    c = t1_cat[r["カテゴリ"]]
    c["asin"] += 1
    if t1_company(r):
        c["co"].add(t1_company(r))
    if r["区分"] == "国内" and not r["大手"]:
        c["asin_target"] += 1
        if t1_company(r):
            c["co_target"].add(t1_company(r))
t1_cls = Counter()
for co in t1_all_co:
    rows = [r for r in t1 if t1_company(r) == co]
    t1_cls["大手" if any(r["大手"] for r in rows) else rows[0]["区分"]] += 1

# 1社あたり ASIN 数（打診母数）
asin_per_co = Counter(t1_company(r) for r in t1_target if t1_company(r))
t1_single = sum(1 for v in asin_per_co.values() if v == 1)

# ---------------------------------------------------------------- 展示会
gs = list(csv.DictReader(open(DLV / "T-20260906-005/20_出展社2353件の機械分類.csv", encoding="utf-8-sig")))
FOREIGN_LEGAL = re.compile(r"(CO\.,?\s*LTD|LIMITED|INC\.?|LLC|CORP|PTE|SDN|GMBH)", re.I)


def hall(b):
    return unicodedata.normalize("NFKC", b).split("-")[0]


for r in gs:
    r["hall"] = hall(r["booth"])
    n = unicodedata.normalize("NFKC", r["exhibitor"])
    # 機械分類の「海外表記」は英字社名を一律に落としている（国内の英字ブランドを含む）。
    # 南1・南2（海外パビリオン）と海外法人格だけを海外とする緩い判定を上限として並べる。
    r["domestic_loose"] = (r["hall"] not in ("南1", "南2") and not FOREIGN_LEGAL.search(n)
                           and not r["class"].startswith(("団体", "除外")))
    r["domestic_strict"] = r["class"] == "PASS"
    r["bucket"] = HALL2B.get(r["hall"], HALL_DEFAULT)

gs_by_hall = defaultdict(Counter)
for r in gs:
    gs_by_hall[r["hall"]]["all"] += 1
    gs_by_hall[r["hall"]]["strict"] += r["domestic_strict"]
    gs_by_hall[r["hall"]]["loose"] += r["domestic_loose"]

# ---------------------------------------------------------------- NETSEA
cats = {x["id"]: x["name"].split(" > ")[0]
        for x in json.load(open(DLV / "T-20260915-001/out/categories.json"))}


def netsea_top(cid):
    s = str(cid)
    for L in range(len(s), 0, -1):
        if s[:L] in cats:
            return cats[s[:L]]
    return "不明"


ns_items = defaultdict(Counter)   # supplier_id -> top cat -> item数
ns_name = {}
for line in open(DLV / "T-20260831-006/out/netsea_items.jsonl", encoding="utf-8"):
    d = json.loads(line)
    ns_items[d["supplier_id"]][netsea_top(d.get("category_id"))] += 1
    ns_name[d["supplier_id"]] = d.get("shop_name") or ""

sup_csv = {r["サプライヤー名"]: r for r in
           csv.DictReader(open(DLV / "T-20260831-006/out/suppliers.csv", encoding="utf-8-sig"))}
app = list(csv.DictReader(open(REPO / "workspace/output/agent_output/T-20260831-006/netsea_取引申請状況_480社.csv",
                               encoding="utf-8-sig")))
app_active = [r for r in app if r["取引状況"] == "取引中"]


def gyotai(s):
    return (s or "").split("（")[0] or "不明"


app_gyotai = Counter(gyotai(r["業態"]) for r in app_active)
ns_rows = []
for sid, c in ns_items.items():
    nm = ns_name[sid]
    g = gyotai(sup_csv.get(nm, {}).get("業態", ""))
    ns_rows.append({"supplier_id": sid, "name": nm, "業態": g, "主カテゴリ": c.most_common(1)[0][0],
                    "カテゴリ数": len(c), "商品数": sum(c.values())})
ns_cat_any = Counter(t for c in ns_items.values() for t in c)
ns_cat_main = Counter(r["主カテゴリ"] for r in ns_rows)
ns_gyotai = Counter(r["業態"] for r in ns_rows)
pool = list(csv.DictReader(open(DLV / "T-20260831-006/out/candidates.csv", encoding="utf-8-sig")))
pool_sup = {r["サプライヤー名"] for r in pool}

# ---------------------------------------------------------------- 名寄せ（3ソースの和集合）
# 実体 = (ソース, 社名, バケット)。照合キーを1つでも共有したら同じ会社（union-find）。
ents = []  # dict(src, name, bucket, target)
t1_rows_by_co = defaultdict(list)
for r in t1:
    if t1_company(r):
        t1_rows_by_co[t1_company(r)].append(r)
for co, rows in t1_rows_by_co.items():
    b = Counter(AMZ2B.get(r["カテゴリ"], "その他") for r in rows).most_common(1)[0][0]
    name = t1_display(rows)
    alias = ({r["ブランド"] for r in rows if r["ブランド"]} | {r["メーカー"] for r in rows if r["メーカー"]}) - {name}
    ents.append({"src": "T1", "name": name, "bucket": b, "target": co in t1_target_co, "alias": alias})
for r in gs:
    ents.append({"src": "GS", "name": r["exhibitor"], "bucket": r["bucket"],
                 "target": r["domestic_strict"], "loose": r["domestic_loose"], "alias": set()})
active_names = {r["サプライヤー名"] for r in app_active}
seen_ns = set()
for r in ns_rows:
    seen_ns.add(r["name"])
    ents.append({"src": "NS", "name": r["name"], "bucket": NETSEA2B.get(r["主カテゴリ"], "その他"),
                 "target": True, "maker": r["業態"] == "メーカー", "alias": set()})
for r in app_active:  # API で商品が見えない取引中サプライヤー（カテゴリは業態の括弧内しか分からない）
    if r["サプライヤー名"] in seen_ns:
        continue
    m = re.search(r"（(.+?)）", r["業態"] or "")
    g2b = {"雑貨": "キッチン・日用品", "ファッション": "ファッション", "美容健康": "美容・健康", "食品": "食品",
           "家具・インテリア": "家具・インテリア", "アクセサリー・時計": "ファッション",
           "ビジネス・事務用品": "文具・事務・店舗用品"}
    ents.append({"src": "NS", "name": r["サプライヤー名"], "bucket": g2b.get(m.group(1), "その他") if m else "その他",
                 "target": True, "maker": gyotai(r["業態"]) == "メーカー", "alias": set(), "no_api": True})

for e in ents:
    e["keys"] = keys_of(e["name"])
    # T-1 のブランド名は「他ソースとの照合」にだけ使う。T-1 同士をブランドで繋ぐと
    # 別メーカーが連鎖する（初回実行で、1ブランドにぶら下がる別メーカー3社が1社に寄った）。
    e["brand_keys"] = set().union(*[keys_of(a) for a in e["alias"]]) - e["keys"] if e["alias"] else set()

parent = list(range(len(ents)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


owner = {}
for i, e in enumerate(ents):
    for k in e["keys"]:
        if k in owner:
            parent[find(i)] = find(owner[k])
        else:
            owner[k] = i
# ブランドキー: 同じキーを社名として持つ T-1 以外の実体とだけ繋ぐ
non_t1_owner = defaultdict(list)
for i, e in enumerate(ents):
    if e["src"] != "T1":
        for k in e["keys"]:
            non_t1_owner[k].append(i)
for i, e in enumerate(ents):
    for k in e["brand_keys"]:
        for j in non_t1_owner.get(k, []):
            parent[find(i)] = find(j)
groups = defaultdict(list)
for i in range(len(ents)):
    groups[find(i)].append(i)

# 同一ソース内の名寄せ（同じ会社が2表記）と、ソース間の一致を分けて数える
pair = Counter()
overlap_rows = []
for g in groups.values():
    srcs = sorted({ents[i]["src"] for i in g})
    if len(srcs) >= 2:
        pair["×".join(srcs)] += 1
        overlap_rows.append({"sources": "×".join(srcs),
                             "names": " | ".join(sorted({f'{ents[i]["src"]}:{ents[i]["name"]}' for i in g}))})
    for a in srcs:
        for b in srcs:
            if a < b:
                pair[f"{a}&{b}"] += 1


def uniq(pred):
    """pred を満たす実体を1つ以上含むグループの数＝重複を除いた社数"""
    return sum(1 for g in groups.values() if any(pred(ents[i]) for i in g))


def uniq_by_bucket(pred):
    c = Counter()
    for g in groups.values():
        es = [ents[i] for i in g if pred(ents[i])]
        if es:
            c[Counter(e["bucket"] for e in es).most_common(1)[0][0]] += 1
    return c


is_target = lambda e: e["target"] and (e["src"] != "NS" or True)  # noqa: E731
is_target_maker = lambda e: e["target"] and (e["src"] != "NS" or e.get("maker"))  # noqa: E731

summary = {
    "T1": {"asin": len(t1), "companies": len(t1_all_co), "target_asin": len(t1_target),
           "target_companies": len(t1_target_co), "company_class": dict(t1_cls),
           "target_single_asin_companies": t1_single,
           "by_category": {k: {"asin": v["asin"], "companies": len(v["co"]),
                               "target_asin": v["asin_target"], "target_companies": len(v["co_target"])}
                           for k, v in sorted(t1_cat.items(), key=lambda kv: -len(kv[1]["co"]))}},
    "GS": {"all": len(gs), "class": dict(Counter(r["class"] for r in gs)),
           "domestic_strict": sum(r["domestic_strict"] for r in gs),
           "domestic_loose": sum(r["domestic_loose"] for r in gs),
           "by_hall": {h: dict(v) for h, v in sorted(gs_by_hall.items())}},
    "NS": {"applied": len(app), "active": len(app_active), "active_gyotai": dict(app_gyotai),
           "api_suppliers": len(ns_rows), "api_items": sum(r["商品数"] for r in ns_rows),
           "api_gyotai": dict(ns_gyotai), "cat_any": dict(ns_cat_any.most_common()),
           "cat_main": dict(ns_cat_main.most_common()), "pool_rows": len(pool), "pool_suppliers": len(pool_sup)},
    "overlap": dict(pair),
    "union": {
        "all_entities": len(ents), "groups": len(groups),
        "all": uniq(lambda e: True),
        "target": uniq(lambda e: e["target"]),
        "target_plus_gs_loose": uniq(lambda e: e["target"] or e.get("loose")),
        "target_makers_only": uniq(is_target_maker),
        "by_bucket_target": dict(uniq_by_bucket(lambda e: e["target"]).most_common()),
        "by_bucket_target_loose": dict(uniq_by_bucket(lambda e: e["target"] or e.get("loose")).most_common()),
    },
}
json.dump(summary, open(OUT / "summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- 明細（Git 追跡外）
with open(OUT / "overlap_社名一致.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["sources", "names"])
    w.writeheader()
    w.writerows(sorted(overlap_rows, key=lambda r: r["sources"]))
with open(OUT / "union_ユニーク社.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["group", "代表社名", "ソース", "バケット", "打診母数に入る", "表記"])
    for gi, g in enumerate(groups.values()):
        es = [ents[i] for i in g]
        w.writerow([gi, es[0]["name"], "+".join(sorted({e["src"] for e in es})),
                    Counter(e["bucket"] for e in es).most_common(1)[0][0],
                    any(e["target"] for e in es), " | ".join(sorted({e["name"] for e in es}))])
with open(OUT / "netsea_supplier_カテゴリ.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ns_rows[0].keys()))
    w.writeheader()
    w.writerows(ns_rows)
