#!/usr/bin/env python3
"""大口・カート価格で利益を引き直す（T-20260909-002 / 2026-09-12）。

見直しで見つかった「利益を低く見る」系統誤差を2つ外して、候補を数え直す。
  1. 基本成約料 110円/点 … 2026-09-12 に大口へ切替済み。0 にする
  2. 売値＝新品最安値(送料込) … 実際に売れるのはカート価格。**カート価格の直近90日平均**を使う
     取れなければ現在のカート価格、それも無ければ従来の最安値。どれを使ったかは列で出す
他の費目（販売手数料・FBA・保管・納品送料・返品引当）とルール（回転6ヶ月・予算10万・
Amazon本体除外・蛍光灯除外・PSE v2.1・入数未解決は計算しない）は一切変えない。

使い方:
    python3 recalc_buybox.py plan     # ローカルだけで絞る。Keepa を叩く件数とトークン見積りを出す
    python3 recalc_buybox.py fetch    # 絞った ASIN だけカート価格を取る（buybox=1・offersなし＝3 token/件）
    python3 recalc_buybox.py report   # out/07_修正後候補.csv / .html を出す

★金額・Keepa加工値は out/ と agent_output/ にだけ書く（PUBLIC リポ）。このファイルには書かない。
"""
import csv, dataclasses, html, json, math, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCAN = REPO / "workspace/output/deliverables/T-20260831-006"
RUN = REPO / "workspace/output/deliverables/T-20260906-003"
SEL_DIR = REPO / "workspace/output/deliverables/T-20260907-001"
CACHE = REPO / "workspace/output/agent_output/T-20260909-002/buybox90.jsonl"
OUT = HERE / "out"
sys.path[:0] = [str(SCAN), str(SEL_DIR), str(RUN)]

from pipeline import config, evaluate  # noqa: E402
import reevaluate as RE                 # noqa: E402  入出力の変換を二重に書かない
import selection_rules as SEL           # noqa: E402

csv.field_size_limit(10 ** 9)

# ── 社長の固定ルール（order_set.py と同値。変えない）──
TURNOVER_CAP_MONTHS = 6.0
TOTAL_BUDGET_YEN = 100_000
MIN_MARGIN = 0.05            # 2026-08-31 社長「5% から候補に含める」
GATE_LISTINGS = 10           # ゲート申請は「10点以上の請求書」
# Keepa に当てる前の緩い足切り。カート価格が最安値を何割まで上回りうると見るか。
# ここで落ちた行は「カートがこれだけ高くても 5% に届かない」＝取っても無駄。
PREFILTER_UPLIFT = 1.30
TOKENS_PER_ASIN = 3          # 実測 2026-09-12: stats=90&buybox=1 で 3 ASIN = 9 token

BEFORE = config.ScanConfig()                                   # 小口・最安値（従来）
AFTER = dataclasses.replace(BEFORE, costs=dataclasses.replace(BEFORE.costs, closing_fee_yen=0.0))


def num(x, default=0.0):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return default


def load_run():
    """T-20260906-003 の検証結果（読むだけ）。passed={asin: rec}, verified=set"""
    passed, verified = {}, set()
    for name, dst in (("passed.jsonl", passed), ("verified.jsonl", None)):
        for line in (RUN / "out" / name).open():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if dst is not None and r.get("ok"):
                dst[r["asin"]] = r
            if dst is None and r.get("asin"):
                verified.add(r["asin"])
    return passed, verified


def lot(row, pack):
    """最小ロット（入数の倍数に切り上げ）と、10出品ぶんの商品代。送料は含まない。"""
    moq = int(num(row.get("最小発注数"), 1)) or 1
    moq_yen = num(row.get("最小発注額(税込)"))
    unit = moq_yen / moq if moq else 0
    min_units = math.ceil(moq / pack) * pack
    units10 = max(GATE_LISTINGS * pack, min_units)
    units10 = math.ceil(units10 / pack) * pack
    return unit, min_units, round(unit * min_units), units10 // pack, round(unit * units10)


def evaluate_row(row, fact, cfg, price=None):
    f = RE.to_facts(fact)
    if price is not None:
        f = dataclasses.replace(f, price_yen=int(round(price)))
    return evaluate.evaluate(RE.to_cand(row), f, cfg)


def base_rows():
    """ローカルだけで判定できる列を全行に付ける。価格に依らない条件はここで全部当てる。"""
    facts = RE.load_facts()
    passed, verified = load_run()
    rows = list(csv.DictReader((SCAN / "out/candidates.csv").open(encoding="utf-8-sig")))
    out = []
    for row in rows:
        asin = row.get("ASIN")
        fact = facts.get(asin)
        if not fact:
            continue
        ev0 = evaluate_row(row, fact, BEFORE)
        rec = {"row": row, "fact": fact, "asin": asin, "ev0": ev0,
               "passed": asin in passed, "is_child": (passed.get(asin) or {}).get("is_child"),
               "verified": asin in verified,
               "drops5": (fact.get("drops30") or 0) >= 5,
               "why": []}
        if ev0.result is None:
            rec["why"].append("入数が解けない" if ev0.review_reason else "Amazon未出品/価格なし")
            out.append(rec)
            continue
        sel = SEL.judge(netsea_name=row.get("商品名") or "", amazon_title=fact.get("title") or "",
                        brand=fact.get("brand") or "", category_names=fact.get("category_names") or [],
                        supplier_name=row.get("サプライヤー名") or "",
                        availability_amazon=fact.get("availability_amazon"))
        rec["sel"] = sel
        if sel.excluded:
            rec["why"].append("選定除外: " + sel.exclude_reasons[0].split("（")[0])
        pack = ev0.pack_size or 1
        unit, min_units, lot_yen, n10, yen10 = lot(row, pack)
        drops = fact.get("drops30") or 0
        sellers = int(num(row.get("出品者数")))
        per_month = drops / (sellers + 1) if drops else 0.0
        months = (min_units // pack) / per_month if per_month else None
        rec.update(pack=pack, unit=unit, min_units=min_units, lot_yen=lot_yen,
                   n10=n10, yen10=yen10, drops=drops, sellers=sellers,
                   per_month=per_month, months=months)
        if months is None:
            rec["why"].append("月販見込が出せない（ドロップ0）")
        elif months > TURNOVER_CAP_MONTHS:
            rec["why"].append("回転6ヶ月超")
        if lot_yen > TOTAL_BUDGET_YEN:
            rec["why"].append("最小ロット10万円超")
        out.append(rec)
    return out, passed, verified


def nonprice_ok(r):
    """価格以外の条件を全部満たすか（入数解決・選定・回転・予算）。比率ガードは価格で変わるので別。"""
    return not r["why"]


def margin_at(r, cfg, price):
    ev = evaluate_row(r["row"], r["fact"], cfg, price)
    if ev.result is None:
        return None, ev
    return ev.result.margin_rate, ev


def fetch_targets(recs):
    """Keepa を当てる ASIN。②③通過 × 価格以外の条件を満たす × カートが3割高くても5%届かない行は外す。"""
    t = set()
    for r in recs:
        if not (r["passed"] and nonprice_ok(r)):
            continue
        lo = r["fact"].get("price_yen") or 0
        m, _ = margin_at(r, AFTER, lo * PREFILTER_UPLIFT)
        if m is not None and m >= MIN_MARGIN:
            t.add(r["asin"])
    return t


def load_cache():
    d = {}
    if CACHE.exists():
        for line in CACHE.open():
            try:
                x = json.loads(line)
                d[x["asin"]] = x
            except Exception:
                pass
    return d


def cmd_fetch(targets):
    import verify_pool as V   # トークン待ち・リトライを持つ既存のクライアントを流用
    cache = load_cache()
    todo = sorted(a for a in targets if a not in cache)
    print(f"取得対象 {len(targets)} / 未取得 {len(todo)} / 見積り {len(todo)*TOKENS_PER_ASIN} token")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        if not V.wait_for_tokens(len(chunk) * TOKENS_PER_ASIN + 10, "bb90"):
            break
        d = V.call("product", {"asin": ",".join(chunk), "stats": 90, "buybox": 1}, "bb90")
        got = {p["asin"]: p for p in d.get("products", [])}
        with CACHE.open("a") as f:
            for a in chunk:
                s = (got.get(a) or {}).get("stats") or {}
                def g(key):
                    v = (s.get(key) or [None] * 19)
                    v = v[18] if len(v) > 18 else None
                    return v if v is not None and v > 0 else None
                f.write(json.dumps({"asin": a, "bb_avg90": g("avg90"), "bb_cur": g("current"),
                                    "ts": time.strftime("%F %T")}) + "\n")
        print(f"  {i+len(chunk)}/{len(todo)} consumed={d.get('tokensConsumed')} left={d.get('tokensLeft')}", flush=True)


def price_after(r, cache):
    c = cache.get(r["asin"]) or {}
    if c.get("bb_avg90"):
        return c["bb_avg90"], "カート90日平均"
    if c.get("bb_cur"):
        return c["bb_cur"], "現在のカート価格"
    return r["fact"].get("price_yen"), "最安値(カート取れず)"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    recs, passed, verified = base_rows()
    targets = fetch_targets(recs)
    if cmd == "plan":
        p_ok = [r for r in recs if r["passed"] and nonprice_ok(r)]
        print(f"評価行 {len(recs):,} / ②③通過ASIN {len(passed):,}")
        print(f"②③通過×価格以外の条件OK: 行 {len(p_ok):,} / ASIN {len({r['asin'] for r in p_ok}):,}")
        print(f"Keepa 取得対象 {len(targets):,} ASIN ＝ 約 {len(targets)*TOKENS_PER_ASIN:,} token")
        return
    if cmd == "fetch":
        cmd_fetch(targets)
        return
    import report_buybox
    report_buybox.write(recs, passed, verified, load_cache(), targets, sys.modules[__name__])


if __name__ == "__main__":
    main()
