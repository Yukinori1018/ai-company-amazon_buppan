"""段1の後処理＋段2：product を再判定 → メーカー単位に集約 → 一次除外 → 優先度（T-20260930-001）。

    python3 30_build.py --from-raw          # 0 token。保存済み raw だけで再計算
    python3 30_build.py --bb                # 代表 ASIN のカート保持者を取得（3 token/ASIN＋1 token/セラー）

出力
- agent_output/T-20260930-001/10_メーカー候補_完全版.csv  … Keepa 加工値を含む（Git 除外側）
- deliverables/T-20260930-001/03_メーカー候補_公開版.csv   … A クラス（公開可）の列だけ
- agent_output/T-20260930-001/funnel_post.json            … 02_抽出の漏斗.md の後段の数字

再判定する理由: Finder の索引と product の現在値は更新時刻が違う（memory knowledge_keepa_product_finder_fields）。
本体の有無は **outOfStockPercentage365（Amazon 列）** で判定する。スナップショットでは判定しない
（memory knowledge_amazon_presence_is_history_not_snapshot）。
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import keepa_io
import maker_rules as R

HERE = Path(__file__).resolve().parent
WORK = keepa_io.RAW.parent

# Keepa の csv 種別インデックス（stats.current / avg90 の添字）
AMAZON, NEW, SALES, COUNT_NEW, BUY_BOX, COUNT_FBA = 0, 1, 3, 11, 18, 34

MS_MIN, OOS_MIN, RANK_MAX, FBA_MIN, PRICE_MIN = 50, 90, 50_000, 2, 2_200
A_MS, A_PRICE = 100, 3_900


def _v(arr, i):
    try:
        x = arr[i]
    except (TypeError, IndexError):
        return None
    return None if x is None or x < 0 else x


def facts(p: dict) -> dict:
    """1商品の判定に使う値を取り出す（純関数）。"""
    st = p.get("stats") or {}
    cur, a90 = st.get("current") or [], st.get("avg90") or []
    oos = st.get("outOfStockPercentage365") or []
    oos_amz = oos[0] if oos and oos[0] is not None else -1
    bb = _v(cur, BUY_BOX)
    price = bb if bb else _v(cur, NEW)
    return {
        "asin": p["asin"],
        "ms": p.get("monthlySold"),
        # -1 = Amazon の価格データなし（＝365日間 本体の出品が観測されていない）→ 100% 扱い
        "oos_amz": 100 if oos_amz is None or oos_amz < 0 else oos_amz,
        "rank": _v(cur, SALES),
        "price": price,
        "price_new90": _v(a90, NEW),
        "price_new": _v(cur, NEW),
        "fba": _v(cur, COUNT_FBA),
        "offers": _v(cur, COUNT_NEW),
        "offers90": _v(a90, COUNT_NEW),
        "root": p.get("rootCategory"),
        "store": bool(p.get("brandStoreName")),
        "parent": p.get("parentAsin") or p["asin"],
        "title": (p.get("title") or "")[:70],
    }


# 後段の再判定（Finder で絞った条件を product 側でもう一度当てる）。順番＝漏斗の順
POST = [
    ("1 monthlySold ≥ 50（product 再判定）", lambda f: (f["ms"] or 0) >= MS_MIN),
    ("2 本体の365日在庫切れ率 ≥ 90%", lambda f: f["oos_amz"] >= OOS_MIN),
    ("4 大カテゴリーランク ≤ 50,000（再判定）", lambda f: f["rank"] is not None and f["rank"] <= RANK_MAX),
    ("3 FBA出品者 ≥ 2（再判定）", lambda f: f["fba"] is not None and f["fba"] >= FBA_MIN),
    ("6 売価（カート価格・無ければ新品最安）≥ 2,200円", lambda f: f["price"] is not None and f["price"] >= PRICE_MIN),
    ("7 除外ルート（再判定）", lambda f: f["root"] not in R.EXCLUDE_ROOTS),
]


def signs(f: dict) -> str:
    """値崩れ・相乗り増の兆候（限定化提案が刺さる材料）。落とさず列にする。"""
    s = []
    if f["price_new"] and f["price_new90"] and f["price_new"] <= f["price_new90"] * 0.9:
        s.append(f"新品最安が90日平均比 -{round(100 - 100 * f['price_new'] / f['price_new90'])}%")
    if f["offers"] is not None and f["offers90"] is not None and f["offers"] >= f["offers90"] + 2:
        s.append(f"新品オファー {f['offers90']}→{f['offers']}")
    return "・".join(s)


def self_cart(seller: str, brand: str, maker: str, offers) -> str:
    """メーカー本人がカートを持つ疑い（除外せず「要確認」）。CLAUDE.md §3.3-5。"""
    why = []
    sn = R._n(seller)
    for name in (brand, maker):
        for part in R.bb._parts(name):
            if len(part) >= 3 and sn and (part in sn or sn in part):
                why.append(f"カート保持セラー「{seller}」がブランド/メーカー名と一致")
                break
        if why:
            break
    if seller and any(w in seller for w in ("公式", "直営", "オフィシャル", "Official", "OFFICIAL", "official", "直販")):
        why.append(f"カート保持セラー「{seller}」が公式/直営を名乗る")
    if offers == 1:
        why.append("新品オファー1本")
    return "要確認：" + " / ".join(dict.fromkeys(why)) if why else ""


def load_products() -> list[dict]:
    order = json.loads((keepa_io.RAW / "order.json").read_text())
    ps = keepa_io.products(order, "all", offline=True)
    seen, out = set(), []
    for p in ps:
        if p["asin"] not in seen:
            seen.add(p["asin"]); out.append(p)
    return out


def build(fetch_bb: bool = False) -> None:
    ps = load_products()
    order = json.loads((keepa_io.RAW / "order.json").read_text())
    funnel = [("Finder 一覧（段2b まで）", len(order)), ("product 取得済み", len(ps))]
    alive = [(p, facts(p)) for p in ps]
    for label, ok in POST:
        alive = [(p, f) for p, f in alive if ok(f)]
        funnel.append((label, len(alive)))

    # メーカー単位に集約
    groups: dict[str, list] = defaultdict(list)
    for p, f in alive:
        k, name = R.maker_key(p)
        groups[k].append((p, f, name))

    rows = []
    for k, items in groups.items():
        a_items = [x for x in items if (x[1]["ms"] or 0) >= A_MS and (x[1]["price"] or 0) >= A_PRICE]
        pool = a_items or items
        rep_p, rep_f, name = max(pool, key=lambda x: ((x[1]["ms"] or 0), -(x[1]["rank"] or 10**9)))
        excl, why, rescue = R.classify(rep_p, [x[0] for x in items])
        marks = sorted({R.MARK_ROOTS[f["root"]] for _, f, _ in items if f["root"] in R.MARK_ROOTS})
        rows.append({
            "_p": rep_p,
            "優先度": "" if excl else ("A" if a_items else "B"),
            "メーカー名": name,
            "ブランド": " / ".join(dict.fromkeys((p.get("brand") or "").strip() for p, _, _ in items if p.get("brand")))[:60],
            "代表ASIN": rep_f["asin"],
            "代表商品名": rep_f["title"],
            "Amazon URL": f"https://www.amazon.co.jp/dp/{rep_f['asin']}",
            "該当ASIN数": len(items),
            "該当ファミリー数": len({f["parent"] for _, f, _ in items}),
            "A条件のASIN数": len(a_items),
            "過去1ヶ月の販売数(代表)": rep_f["ms"],
            "代表の売価": rep_f["price"],
            "代表のFBA数": rep_f["fba"],
            "代表の新品オファー数": rep_f["offers"],
            "本体365日在庫切れ率(代表)": rep_f["oos_amz"],
            "ブランドストア": "あり" if any(f["store"] for _, f, _ in items) else "なし",
            "値崩れ・相乗り増の兆候": signs(rep_f),
            "カテゴリ": R.ROOT_NAMES.get(rep_f["root"], str(rep_f["root"])),
            "印": "・".join(marks),
            "カート保持セラー(代表)": "",
            "要確認": "",
            "除外理由": excl,
            "判定の根拠": why,
            "救済の根拠": rescue,
        })

    # 代表 ASIN のカート保持者（残す社だけ）
    keep = [r for r in rows if not r["除外理由"]]
    bbp = keepa_io.products_buybox([r["代表ASIN"] for r in keep], offline=not fetch_bb)
    sids = [((bbp.get(r["代表ASIN"]) or {}).get("stats") or {}).get("buyBoxSellerId") for r in keep]
    names = keepa_io.sellers([s for s in sids if s], offline=not fetch_bb)
    for r, sid in zip(keep, sids):
        p = r["_p"]
        if r["代表ASIN"] not in bbp:
            r["要確認"] = "カート保持者 未取得"
            continue
        seller = names.get(sid or "", "") or (sid or "")
        r["カート保持セラー(代表)"] = seller
        r["要確認"] = self_cart(seller, p.get("brand") or "", p.get("manufacturer") or "", r["代表の新品オファー数"])

    # gBiz で引き直す対象（区分で落ちた／救済された社の名前）。35_gbiz_rescue.py が読む
    sus = sorted({n for r in rows if r["除外理由"] in R.RESCUABLE or r["判定の根拠"].startswith("救済")
                  for n in [r["メーカー名"], *r["ブランド"].split(" / ")] if n})
    (WORK / "suspect_names.json").write_text(json.dumps(sus, ensure_ascii=False))

    rank = {"A": 0, "B": 1, "": 2}
    rows.sort(key=lambda r: (rank[r["優先度"]], -r["該当ASIN数"], -(r["過去1ヶ月の販売数(代表)"] or 0)))
    for r in rows:
        r.pop("_p")

    cols = list(rows[0].keys())
    with open(WORK / "10_メーカー候補_完全版.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    # 公開版：A クラス（Amazon の現在表示）と当社の判定だけ。Keepa の履歴・派生値（在庫切れ率・90日比）は出さない
    pub_cols = ["優先度", "メーカー名", "ブランド", "代表ASIN", "代表商品名", "Amazon URL", "該当ASIN数",
                "過去1ヶ月の販売数(代表)", "カテゴリ", "印", "要確認", "除外理由", "救済の根拠"]
    with open(HERE / "03_メーカー候補_公開版.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=pub_cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    write_additions(rows)
    keep = [r for r in rows if r["優先度"]]
    summ = {
        "funnel": funnel,
        "メーカー数": len(rows),
        "優先度": dict(Counter(r["優先度"] or "除外" for r in rows)),
        "除外内訳(社)": dict(Counter(r["除外理由"] for r in rows if r["除外理由"]).most_common()),
        "要確認(残す社)": sum(1 for r in rows if r["優先度"] and r["要確認"].startswith("要確認")),
        "カート保持者未取得(残す社)": sum(1 for r in rows if r["優先度"] and r["要確認"] == "カート保持者 未取得"),
        "印(残す社)": dict(Counter(r["印"] for r in rows if r["優先度"] and r["印"])),
        "印あり(残す社)": sum(1 for r in keep if r["印"]),
        "印なし(残す社)": sum(1 for r in keep if not r["印"]),
        "印なし・要確認なし(残す社)": sum(1 for r in keep if not r["印"] and not r["要確認"]),
        "救済で残した社": dict(Counter(r["判定の根拠"] for r in keep if r["判定の根拠"].startswith("救済"))),
        "該当ASIN数の合計(残す社)": sum(r["該当ASIN数"] for r in keep),
        "残す社を作ったASIN数(全社)": sum(r["該当ASIN数"] for r in rows),
    }
    (WORK / "funnel_post.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def write_additions(rows: list[dict]) -> None:
    """連絡先台帳の50社（30_最終_50社.csv）に無い、残した社の一覧 → agent_output/11_追加候補.csv。
    50社側は手で統合した行があるので、社名（正規化）と ASIN（代表・統合した行）の両方で突き合わせる。"""
    p50 = WORK / "30_最終_50社.csv"
    names, asins = set(), set()
    if p50.exists():
        for r in csv.DictReader(p50.open(encoding="utf-8-sig")):
            names.add(R._n(r["メーカー名(タカシ)"]))
            for a in (r.get("代表ASIN(タカシ)", "") + " " + r.get("統合した行のASIN", "")).replace(",", " ").replace("/", " ").split():
                asins.add(a.strip())
    add = [r for r in rows if r["優先度"] and R._n(r["メーカー名"]) not in names and r["代表ASIN"] not in asins]
    cols = ["優先度", "メーカー名", "ブランド", "代表ASIN", "代表商品名", "Amazon URL", "該当ASIN数", "A条件のASIN数",
            "過去1ヶ月の販売数(代表)", "代表の売価", "代表のFBA数", "代表の新品オファー数", "カテゴリ", "印",
            "カート保持セラー(代表)", "要確認", "判定の根拠", "救済の根拠"]
    with open(WORK / "11_追加候補.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(add)
    print(f"11_追加候補.csv: {len(add)} 社（50社台帳 {len(names)} 社を除く）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-raw", action="store_true", help="保存済み raw だけで再計算（既定）")
    ap.add_argument("--bb", action="store_true", help="代表 ASIN のカート保持者を取得する（token を使う）")
    a = ap.parse_args()
    build(fetch_bb=a.bb)
