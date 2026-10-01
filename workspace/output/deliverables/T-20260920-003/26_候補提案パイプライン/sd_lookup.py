#!/usr/bin/env python3
"""SD 突合 CLI — Amazon 側の「売れている棚」を SD で買えるか当て、仕入れ先商品リストに積む。

    python3 sd_lookup.py --limit 8                   # 既定：非ログイン・取得60回まで
    python3 sd_lookup.py --limit 8 --dry-run          # 何を何語で投げるか見るだけ（通信0）
    python3 sd_lookup.py --from-netsea-index          # NETSEA の JAN 索引をシートへ流し込む
    python3 sd_lookup.py --approval-list              # 卸価格の申請をしたい出展企業の一覧を出す

入力（Amazon 側）
---------------
`agent_output/.../unmatched_selling.json` ── `discover_selling.py`（B案）が
**「売れている棚のうち NETSEA に無かったもの」**として残したリストです。
NETSEA で買えなかったものを SD で当てるのが、いちばん素直な順番になります。

🔴 正直な見積り（2026-09-30 実測）
--------------------------------
SD は **JAN で検索できません**（`superdelivery.py` 冒頭）。だから1件当てるのに
「検索1〜4回 ＋ 商品ページ 最大4枚」＝**最大8リクエスト・2秒間隔で約16秒**かかります。
216件を全部投げると最大1,700リクエスト。**これは人が手で見る規模を超えます。**

だから SD の正しい使い方は逆で、**仕入れ先起点で索引を積むこと**です（社長指示②）。
一度 JAN が仕入れ先商品リストに入れば、次からの突合は**0リクエスト**です。
この CLI は「Amazon 起点の当て込み」もできますが、既定の上限（60回）で必ず止まります。
**上限に当たったことは必ず表示します**（黙って0件にしない）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import superdelivery as sd                          # noqa: E402
import supplier_catalog as cat                      # noqa: E402
from candidate_sources import REPO                  # noqa: E402

WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
SELLING = WORK / "unmatched_selling.json"
SD_ROWS = WORK / "sd_rows.json"                     # 取れた SD の行（卸価格は入らない）
SD_TRACE = WORK / "sd_trace.json"                   # 何語で何回投げたか
SD_WHOLESALE = WORK / "sd_wholesale.json"           # ★カズヨがブラウザで埋める口
APPROVALS = WORK / "sd_approval_requests.json"      # 申請したい出展企業（申請はしない）
PRICE_WORKLIST = WORK / "sd_price_worklist.json"    # ★カズヨが卸価格を拾うための作業リスト

# 仕入れ先起点の種語。**SD が実際に強い棚**にしてあります（ファッション・生活雑貨・
# インテリア・什器）。Amazon 起点で出てくる「売れている棚」は国内大手ブランドの化粧品・
# 日用品に偏り、実測で SD とほとんど重なりませんでした（10件投げて一致0件）。
SEED_WORDS = [
    "珪藻土マット", "ステンレス保存容器", "収納ボックス", "キッチンマット", "アロマディフューザー",
    "ランチボックス", "スリッパ", "タオルケット", "水切りかご", "折りたたみ傘",
    "ペットベッド", "掛け時計", "ガーデニング 鉢", "ラッピング袋", "食器 プレート",
]


def ser(s) -> dict:
    """SDSet を JSON に落とす（`supplier` は入れ子の dataclass なので手で開く）。"""
    d = dict(s.__dict__)
    d["supplier"] = s.supplier.__dict__ if s.supplier else None
    return d


# SD 担当（別チケット作業）がカズヨの実機で取得した「取引企業」一覧。
# **一括申請済みなので、ここに載っている企業は卸価格が既に見えます** ＝ 申請の必要がない。
TRADING_TSV = (REPO / "workspace/output/agent_output/T-20260920-003/sd"
               / "sd_trading_partners_20260930.tsv")


def _norm_company(s: str) -> str:
    """社名の名寄せ。法人格と記号・空白を落として NFKC で畳む。"""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").strip()
    s = re.sub(r"株式会社|有限会社|\(株\)|\(有\)|Co\.,?\s*Ltd\.?|㈱|㈲", "", s, flags=re.I)
    return re.sub(r"[\s　・,，\.\-（）\(\)]", "", s)


def mark_already_trading(reqs: list[dict], tsv=None) -> list[dict]:
    """既に取引中の企業に印を付ける。**申請リストに混ぜない**のが目的。

    ⚠️ **突合は出展企業ID を第一、社名の名寄せを第二**にします。社名だけで当てると
    別会社を同一視します（`knowledge_maker_name_normalization`）。
    リストが無ければ**全社を「申請が要る」扱いにはせず、判定不能として印を付けません**
    （無いことを「取引していない」の根拠にしない）。
    """
    import csv
    tsv = tsv or TRADING_TSV
    reqs = [dict(r) for r in reqs]              # 呼び出し側の dict を書き換えない
    if not tsv.exists():
        for r in reqs:
            r["取引中の判定"] = "未確認（取引企業リストが手元に無い）"
        return reqs
    rows = list(csv.DictReader(tsv.open(encoding="utf-8"), delimiter="\t"))
    by_id = {r["dealer_id"]: r["name"] for r in rows}
    by_name = {_norm_company(r["name"]): r["dealer_id"] for r in rows}
    for r in reqs:
        hit = by_id.get(str(r["supplier_id"])) or by_name.get(_norm_company(r["出展企業"]))
        r["既に取引中"] = bool(hit)
        r["取引中の判定"] = (f"取引企業リストに一致（{len(rows)}社中）" if hit
                             else f"取引企業リスト（{len(rows)}社）に無し＝申請が要る")
        if hit:
            r["申請したい理由"] = ("既に取引中なので申請は不要。"
                                   "カズヨがブラウザで卸価格を読めば採算が出ます")
    return reqs


def report_stop(trace: dict) -> int:
    """打ち切りの理由を**標準出力に出し、終了コードに反映する**。

    「0件でした」だけを返すと、**SD に無かった**のか**こちらが止められた**のかが区別できません。
    2026-09-30 に実際にこれで判断を誤りかけました（429 を1件ずつの失敗として飲み込んでいた）。
    レート制限のときは終了コード 2 を返し、呼び出し側（ルーチン・フック）も気づけるようにします。
    """
    why = trace.get("stopped")
    if not why:
        return 0
    if "レート制限" in why:
        print(f"\n🔴 打ち切り: {why}")
        print("   **自動で再試行しません。**SD への取得を止め、間隔と総量の判定"
              "（法務ハルオへ依頼中）を待ってください。")
        return 2
    print(f"\n打ち切り: {why}（SD に無いという意味ではありません）")
    return 0


def load_trading_names(tsv=None) -> dict[str, str]:
    """取引企業 2,175社の {出展企業ID: 社名}。無ければ空（**無いことを根拠にしない**）。"""
    import csv
    tsv = tsv or TRADING_TSV
    if not tsv.exists():
        return {}
    return {r["dealer_id"]: r["name"]
            for r in csv.DictReader(tsv.open(encoding="utf-8"), delimiter="\t")}


def resolve_dealer(token: str, names: dict[str, str]) -> str | None:
    """`--dealers` の指定を出展企業ID に解く。数字ならそのまま、社名なら名寄せで引く。

    **当たらなければ None を返して黙って別の会社を使いません**（社名の名寄せは
    当たらないことがある。`knowledge_maker_name_normalization`）。
    """
    if token.isdigit():
        return token
    want = _norm_company(token)
    hits = [i for i, n in names.items() if _norm_company(n) == want]
    if len(hits) == 1:
        return hits[0]
    print(f"  ⚠️ 「{token}」は出展企業IDに解けませんでした"
          f"（候補 {len(hits)}件）。ID を直接指定してください")
    return None


def write_price_worklist(rows: list, names: dict[str, str], path=None) -> Path:
    """**カズヨがブラウザで卸価格を拾うための作業リスト。**

    `sd_wholesale.json` は「埋めた結果」を入れる口で、こちらは「何を見ればよいか」の側です。
    企業ごと・商品ページごとにまとめてあるので、1ページ開けば複数の規格を一度に埋められます。
    **卸価格と商品URL が入るので `agent_output/` にだけ置きます**（このリポは PUBLIC）。
    """
    path = path or PRICE_WORKLIST
    if not rows:
        # **空で上書きしない。**前回ぶんの作業リストを消すと、カズヨの手が戻ります。
        print("卸価格の作業リスト: 対象0件だったので書き換えません")
        return path
    by_dealer: dict[str, dict] = {}
    for r in rows:
        did = r.supplier.supplier_id if r.supplier else "?"
        d = by_dealer.setdefault(did, {
            "出展企業": (r.supplier.name if r.supplier else "未確認"),
            "supplier_id": did,
            "取引中": did in names,
            "商品ページ": {},
        })
        page = d["商品ページ"].setdefault(r.product_id, {
            "商品URL": r.url, "商品名": r.name, "規格": []})
        page["規格"].append({
            "sd_code": r.sd_code, "JAN": r.jan, "入り数": r.units_per_set,
            "メーカー品番": r.maker_code, "上代(税抜)": r.retail_excl,
            "在庫": r.stock, "ネット販売": r.net_sales_ok,
            "卸価格": None, "価格の単位": None, "承認状態": r.approval,
        })
    out = {
        "使い方": ("各 商品URL をログイン済みブラウザで開き、規格（口）ごとの卸価格を読んで "
                   "sd_wholesale.json に次の形で入れてください。\n"
                   "  {\"<sd_code>\": {\"卸価格\": 620, \"価格の単位\": \"1点あたり\", "
                   "\"入り数\": 1, \"承認状態\": \"承認済み\"}}\n"
                   "🔴 `価格の単位` は必須です。\"1点あたり\" か \"1セットあたり\" の"
                   "どちらかを、画面の表記を見て書いてください。"
                   "同じ JAN に「1点」「×10点」「×100点」の口が並び、どちらの建て付けかは"
                   "口によって違います。**書かれていない行は卸価格を取り込みません**"
                   "（推測で埋めると単位ずれを3回目として作ります）。\n"
                   "見えなければ {\"承認状態\": \"卸価格未承認\"} と入れてください"
                   "（申請すれば見えるので NO-GO ではありません）"),
        "企業": sorted(by_dealer.values(),
                       key=lambda d: (not d["取引中"], -len(d["商品ページ"]))),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    pages = sum(len(d["商品ページ"]) for d in by_dealer.values())
    print(f"卸価格の作業リスト: {len(by_dealer)}社・商品ページ {pages}枚 → {path}")
    return path


def merge_and_save(rows: list, path=None) -> list[dict]:
    """取れた SD 行を `sd_rows.json` に**足し込む**（前回ぶんを消さない）。

    上書き保存にしていると、走らせ直すたびに申請候補の企業リストが縮みます。
    索引は積み上げる資産なので、キー（SD品番）で畳んで足します。
    """
    path = path or SD_ROWS
    have = {r["sd_code"]: r for r in (json.loads(path.read_text(encoding="utf-8"))
                                     if path.exists() else [])}
    for r in rows:
        have[r.sd_code] = ser(r)
    out = list(have.values())
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load_targets(limit: int) -> list[dict]:
    """Amazon 側の対象。**JAN が無いものは投げません**（一致の確認ができないので）。"""
    if not SELLING.exists():
        raise SystemExit(f"{SELLING} がありません。先に discover_selling.py を走らせてください。")
    rows = json.loads(SELLING.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        jans = [j for j in (r.get("jans") or []) if sd.JAN_RE.match(str(j))]
        if not jans:
            continue
        out.append({"asin": r["asin"], "jan": jans[0], "title": r.get("title") or "",
                    "brand": r.get("brand") or "", "maker_code": r.get("maker_code") or "",
                    "monthlySold": r.get("monthlySold")})
        if len(out) >= limit:
            break
    return out


def run_lookup(targets: list[dict], cap: int, dry_run: bool, log=print):
    """1件ずつ SD に当てる。取得上限に当たったら止め、**止まったことを返します。**"""
    fetcher = sd.Fetcher(cap=cap)
    rows: list = []
    traces: list[dict] = []
    asin_by_jan: dict[str, str] = {}
    stopped = None

    for t in targets:
        plan = sd.lookup_plan(t["jan"], t["maker_code"], t["brand"], t["title"])
        log(f"  {t['asin']} 月販{t['monthlySold']} JAN {t['jan']} → 検索語 {plan}")
        if dry_run:
            traces.append({"asin": t["asin"], "plan": plan})
            continue
        hits, trace = sd.find_by_identity(t["jan"], t["maker_code"], t["brand"], t["title"],
                                          fetch=fetcher, log=log)
        trace["asin"] = t["asin"]
        traces.append(trace)
        for h in hits:
            asin_by_jan[h.jan] = t["asin"]
        rows.extend(hits)
        if trace.get("stopped"):
            stopped = trace["stopped"]
            log(f"  ⚠️ {stopped} で打ち切りました（{fetcher.used}/{cap} 回）。"
                "残りは未確認です（SD に無いという意味ではありません）")
            break
    return rows, traces, asin_by_jan, fetcher.used, stopped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SD 突合 ＋ 仕入れ先商品リストへの積み上げ")
    ap.add_argument("--limit", type=int, default=8, help="当てにいく Amazon 側の件数")
    ap.add_argument("--cap", type=int, default=sd.DEFAULT_FETCH_CAP,
                    help="SD への取得回数の上限（既定60・2秒間隔）")
    ap.add_argument("--dry-run", action="store_true", help="検索語だけ見る（通信0）")
    ap.add_argument("--no-sheet", action="store_true", help="シートに書かない")
    ap.add_argument("--from-netsea-index", action="store_true",
                    help="NETSEA の JAN 索引を仕入れ先商品リストへ流し込む（SD には触らない）")
    ap.add_argument("--approval-list", action="store_true",
                    help="保存済みの SD 行から、卸価格を申請したい出展企業の一覧を作る")
    ap.add_argument("--seed-words", default="",
                    help="**仕入れ先起点**で SD を索引する（カンマ区切りの語）。"
                         "既定の語は SEED_WORDS。JAN での当て込みはしない")
    ap.add_argument("--dealers", default="",
                    help="**企業を指名して索引する**（カンマ区切りの出展企業IDか社名）。"
                         "卸価格が既に見える先＝取引中の企業に使う")
    ap.add_argument("--per-dealer", type=int, default=14,
                    help="1社あたり開く商品ページの枚数（既定14）")
    ap.add_argument("--build-netsea-index", type=int, metavar="社数", default=0,
                    help="NETSEA の JAN 索引を作る／続ける（Keepa トークン0・前回の続きから）。"
                         "1社ずつ保存するので、途中で止めても失われません")
    a = ap.parse_args(argv)
    WORK.mkdir(parents=True, exist_ok=True)

    # ── NETSEA の JAN 索引を作る／続ける（0トークン・時間だけ）
    if a.build_netsea_index:
        import discover
        idx = discover.build_netsea_index(shops_per_run=a.build_netsea_index)
        print(f"索引: {len(idx.get('indexed_shops') or [])}社・JAN {len(idx.get('jans') or {}):,}件")
        print("→ 続きは同じコマンドで走ります。シートへ入れるのは --from-netsea-index")
        return 0

    # ── 企業を指名して索引する（卸価格が既に見える先＝取引中の企業）
    if a.dealers:
        names = load_trading_names()
        ids = [d.strip() for d in a.dealers.split(",") if d.strip()]
        ids = [i for i in (resolve_dealer(x, names) for x in ids) if i]
        print(f"SD の出展企業 {len(ids)}社を指名して索引します（取得上限 {a.cap}回）")
        for i in ids:
            print(f"  {i}: {names.get(i, '（取引企業リストに無し）')}")
        rows, trace = sd.index_by_dealer(ids, fetch=sd.Fetcher(cap=a.cap),
                                         products_per_dealer=a.per_dealer)
        SD_TRACE.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
        merge_and_save(rows)
        write_price_worklist(rows, names)
        print(f"\nSD の行 {len(rows)}件（JAN 付き）／取得 {trace['fetched']}回")
        rc = report_stop(trace)
        if not a.no_sheet and rows:
            n = cat.append(cat.from_sd_sets(rows))
            print(f"仕入れ先商品リストへ {n}行 追記 → {cat.sheet_url()}")
        return rc

    # ── 仕入れ先起点で SD を索引する（社長指示②）
    if a.seed_words:
        words = [w.strip() for w in a.seed_words.split(",") if w.strip()]
        words = SEED_WORDS if words == ["default"] else words
        print(f"SD を仕入れ先起点で索引します（語 {len(words)}件・取得上限 {a.cap}回）")
        rows, trace = sd.index_by_words(words, fetch=sd.Fetcher(cap=a.cap))
        SD_TRACE.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
        merge_and_save(rows)
        print(f"\nSD の行 {len(rows)}件（JAN 付き）／取得 {trace['fetched']}回")
        rc = report_stop(trace)
        if not a.no_sheet and rows:
            n = cat.append(cat.from_sd_sets(rows))
            print(f"仕入れ先商品リストへ {n}行 追記 → {cat.sheet_url()}")
        return rc

    # ── NETSEA の JAN 索引を資産化する（社長指示②。Keepa トークン0・SD への通信0）
    if a.from_netsea_index:
        import discover
        idx = discover.load_index()
        rows = cat.from_netsea_index(idx.get("jans") or {})
        print(f"NETSEA 索引: {len(idx.get('indexed_shops') or [])}社ぶん・JAN {len(rows):,}件")
        if a.no_sheet:
            return 0
        n = cat.append(rows)
        print(f"仕入れ先商品リストへ {n:,}行 追記 → {cat.sheet_url()}")
        return 0

    # ── 申請したい出展企業の一覧（⛔ 申請は実行しない。§4.1）
    if a.approval_list:
        saved = json.loads(SD_ROWS.read_text(encoding="utf-8")) if SD_ROWS.exists() else []
        sets = [sd.SDSet(**{**r, "supplier": sd.SDSupplier(**r["supplier"])
                            if r.get("supplier") else None}) for r in saved]
        reqs = mark_already_trading(sd.approval_requests(sets))
        APPROVALS.write_text(json.dumps(reqs, ensure_ascii=False, indent=1), encoding="utf-8")
        need = [r for r in reqs if not r.get("既に取引中")]
        print(f"SD の出展企業 {len(reqs)}社 → うち**申請が要る {len(need)}社** → {APPROVALS}")
        for r in reqs:
            tag = "【既に取引中＝画面で卸価格が見えます】" if r.get("既に取引中") else "【申請が要る】"
            print(f"  {tag} {r['出展企業']}（商品{r['該当商品数']}件・"
                  f"ネット販売{r['ネット販売']}・直送{r['消費者直送']}）")
        print("\n⛔ 申請は実行していません（出展企業への連絡＝CLAUDE.md §4.1）。"
              "社長承認はカズヨが取ります。")
        return 0

    # ── Amazon 起点の SD 突合
    targets = load_targets(a.limit)
    print(f"Amazon 側の対象 {len(targets)}件（売れている棚で NETSEA に無かったもの）")
    rows, traces, asin_by_jan, used, stopped = run_lookup(targets, a.cap, a.dry_run)
    SD_TRACE.write_text(json.dumps(traces, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.dry_run:
        print(f"\n（dry-run）検索語だけ出しました。通信 0 回。→ {SD_TRACE.name}")
        return 0

    # カズヨがブラウザで見た卸価格があれば流し込む（無ければ「未確認」のまま積む）
    filled = sd.load_json(SD_WHOLESALE)
    if filled:
        sd.merge_wholesale(rows, filled)
        print(f"卸価格を人の確認から {len(filled)}件 流し込みました")

    merge_and_save(rows)
    print(f"\nSD で JAN 一致 {len(rows)}件 / SD への取得 {used}回"
          f"{'（' + stopped + 'で打ち切り）' if stopped else ''}")

    cat_rows = cat.from_sd_sets(rows, asin_by_jan)
    if not a.no_sheet and cat_rows:
        n = cat.append(cat_rows)
        print(f"仕入れ先商品リストへ {n}行 追記 → {cat.sheet_url()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
