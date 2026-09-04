#!/usr/bin/env python3
"""NETSEA 仕入れ起点 × Keepa 検証 — 利益が取れる商品を抽出する（T-20260831-006）。

    仕入れられることが確定している棚（NETSEA の承認済みサプライヤー225社）から始めて、
    Amazon で本当に売れて利益が残るものだけを残す。

なぜ向きを反転させたか:
    Amazon 起点は「売れている商品」から入るので、**仕入れられるかが最後まで分からない**。
    NETSEA 起点なら「そこに売っている＝仕入れられる」ことが確定していて、卸値も実額。
    社長の最大の不満だった「仕入れ値が推定で不正確」が構造的に消えます。
    Keepa の役割は**発見ではなく検証**（社長のご指示）。

3段構え（トークンを本命に集中させるための設計）:
    段1 NETSEA から商品を取る      … 0トークン。無料でいくらでも取れる
    段2 機械的に落とす（screen）    … 0トークン。ここで落とした1件が本命1件ぶんになる
    段3 Keepa で検証（1トークン/件）… **Amazon に無い JAN は0トークン**（実測）

使い方:
    # まず小さく回す（サプライヤー5社ぶん）
    python3 netsea_scan.py --suppliers 5

    # 全225社（時間がかかるので nohup 推奨）
    python3 netsea_scan.py --suppliers 0

    # 段1だけ / 段3だけ を別々に回す（再開可能）
    python3 netsea_scan.py --stage harvest --suppliers 0
    python3 netsea_scan.py --stage verify

    # 利益ラインを超えた行だけ、実セラー数を確定する（6.5トークン/件と高い）
    python3 netsea_scan.py --stage verify --verify-sellers

⛔ このスクリプトは **商品データの取得と計算しかしません**。
   NETSEA での発注・購入は行いません（CLAUDE.md §4.1）。
"""

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LEGACY_CODE = REPO / "workspace" / "output" / "deliverables" / "T-20260521-005" / "code"
for p in (str(HERE), str(LEGACY_CODE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline import (  # noqa: E402
    config, evaluate, heartbeat, keepa_verify, screen, store, supplier_profile,
)

# 業態（メーカー／卸専業／…）の一次情報。Buyer API は業態を持たないため、
# 秘書カズヨが社長のログイン中に管理画面から取得した CSV を名寄せして使う。
# ⚠️ API では再取得できません。取引先が増えたら取り直し（＝またログインの一手）が要ります。
PROFILE_CSV_DEFAULT = (
    REPO / "workspace" / "output" / "agent_output" / "T-20260831-006"
    / "netsea_取引申請状況_480社.csv"
)

OUT = HERE / "out"
ITEMS_JSONL = OUT / "netsea_items.jsonl"         # 段1の生データ（Git 追跡外）
FACTS_JSONL = OUT / "keepa_facts.jsonl"          # 段3の Keepa 結果（Git 追跡外）
CANDIDATES_CSV = OUT / "candidates.csv"          # 最終成果（Git 追跡外）
REJECTED_CSV = OUT / "rejected_by_screen.csv"    # 落とした理由つき（Git 追跡外）
SUPPLIERS_CSV = OUT / "suppliers.csv"            # 取引先単位の集計（Git 追跡外）
STATS_JSON = HERE / "run_stats.json"             # 統計だけは Git 追跡する
HEARTBEAT = OUT / "heartbeat.json"               # 生死の証拠（Git 追跡外）

# 心拍。**プロセスの存在ではなく、これの更新時刻で生死を判断する。**
# `python3 netsea_scan.py --status` で人が読める形に出ます。
BEAT = heartbeat.Heartbeat(HEARTBEAT)
LOG_PATH = OUT / "scan.log"

JST = timezone(timedelta(hours=9))


def log(msg: str) -> None:
    line = f"[{datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# =============================================================================
# 段1: NETSEA から商品を取る（0トークン）
# =============================================================================
def harvest(limit_suppliers: int, max_items_per_supplier: int) -> dict:
    """承認済みサプライヤーの商品を JSONL に貯める。**再開可能**（取得済みは飛ばす）。"""
    from adapters.netsea import (  # noqa: E402
        PURPOSE_PROCUREMENT, NetseaClient, assert_procurement_use,
    )

    # 用途の関門。ここを通らない使い方をしたら、その時点で落ちるのが正しい。
    assert_procurement_use(PURPOSE_PROCUREMENT)

    keepa_verify.load_env()
    client = NetseaClient()
    if not client.is_live:
        raise SystemExit(
            f"NETSEA に接続できません: {client._why_not_live()}\n"
            "NETSEA_API_TOKEN を .env か環境変数に設定してください（有効期限180日）。"
        )

    suppliers = client.list_suppliers()
    log(f"承認済みサプライヤー: {len(suppliers)}社（＝今すぐ仕入れられる相手）")
    if limit_suppliers:
        suppliers = suppliers[:limit_suppliers]
        log(f"  → 今回は先頭 {len(suppliers)}社のみ処理します")

    itemstore = store.JsonlStore(ITEMS_JSONL, key="_uid")
    done_suppliers = {
        int(r["supplier_id"]) for r in itemstore.load().values() if r.get("supplier_id")
    }

    stats = {"suppliers_total": len(suppliers), "suppliers_fetched": 0,
             "items_fetched": 0, "suppliers_empty": 0, "errors": []}
    for i, sup in enumerate(suppliers, 1):
        sid = sup["id"]
        if sid in done_suppliers:
            log(f"  [{i}/{len(suppliers)}] supplier {sid} は取得済み。飛ばします")
            continue
        rows, cov = client.list_supplier_items_raw(sid, max_items=max_items_per_supplier)
        if cov.get("error"):
            stats["errors"].append({"supplier_id": sid, "error": cov["error"]})
        # 商品IDだけでは規格が潰れるので、supplier+product を一意キーにする。
        for r in rows:
            r["_uid"] = f"{r.get('supplier_id')}-{r.get('product_id')}"
        itemstore.append(rows)
        stats["suppliers_fetched"] += 1
        stats["items_fetched"] += len(rows)
        BEAT.beat("段1 NETSEA収集", done=i, total=len(suppliers),
                  note=f"商品{stats['items_fetched']}件を取得")
        if not rows:
            stats["suppliers_empty"] += 1
        log(
            f"  [{i}/{len(suppliers)}] supplier {sid} → 商品{len(rows)}件"
            f"{'（打ち切り）' if cov.get('truncated') else ''}"
            f"{'  ⚠ ' + str(cov['error'])[:60] if cov.get('error') else ''}"
        )
        time.sleep(0.2)
    return stats


# =============================================================================
# 段2: 機械的に落とす（0トークン）
# =============================================================================
def build_candidates(cfg: config.ScanConfig, profiles=None) -> tuple:
    """JSONL の生データ → 判定済み候補。戻り値は (通過, 全件, 統計)。"""
    BEAT.beat("段2 前段フィルタ", note="NETSEA商品を読み込み中")
    raw = list(store.JsonlStore(ITEMS_JSONL, key="_uid").load().values())
    log(f"段2: NETSEA 商品 {len(raw)}件 を判定します（Keepa は1トークンも使いません）")

    all_c: list = []
    for item in raw:
        all_c.extend(screen.to_candidates(item))
    log(f"  規格(set)単位に展開: {len(all_c)}件")

    # 業態を貼る。名寄せできなかった社は**空欄のまま**にする（推測で埋めない）。
    unmatched = set()
    if profiles and len(profiles):
        for c in all_c:
            c.business_type = profiles.business_type(c.supplier_name)
            if not c.business_type:
                unmatched.add(c.supplier_name)
        tagged = len({c.supplier_name for c in all_c}) - len(unmatched)
        log(f"  業態を付与: {tagged}社に付与 / {len(unmatched)}社は名寄せできず空欄")

    for c in all_c:
        screen.screen_one(c, cfg)
    passed = [c for c in all_c if c.verdict == screen.PASS]

    deduped, dropped = screen.dedupe_by_jan(passed)
    log(f"  通過 {len(passed)}件 → 同一JAN重複 {dropped}件 を潰して 残り {len(deduped)}件（これが Keepa の母数）")

    BEAT.beat("段2 前段フィルタ", done=len(deduped), total=len(all_c),
              note="判定完了")
    reasons = screen.summarize(all_c)
    for reason, n in reasons.items():
        log(f"    {reason}: {n}件")

    stats = {
        "netsea_products": len(raw),
        "candidates_expanded": len(all_c),
        "passed_screen": len(passed),
        # ⚠️ 2026-09-04 改名。旧キー名は `deduped_by_jan` で、**潰した重複の数**でしたが、
        #    「重複を除いた後の件数」と読まれ、母数を 26,942 → 15,132 と
        #    1万件以上少なく見積もる誤読を実際に生みました（T-20260904-004）。
        #    数を出す列は「何を数えたか」が名前で分かる形にすること。
        "dropped_as_duplicate_jan": dropped,
        "unique_jan_candidates": len(deduped),
        "to_keepa": len(deduped),
        "screen_reasons": reasons,
        "suppliers_without_business_type": len(unmatched),
    }
    return deduped, all_c, stats


# =============================================================================
# 段3: Keepa で検証（1トークン/件・ヒットしなければ0）
# =============================================================================
def verify(candidates: list, cfg: config.ScanConfig, verify_sellers: bool,
           new_limit: int = 0) -> tuple:
    factstore = store.JsonlStore(FACTS_JSONL, key="jan")
    cached = factstore.load()
    todo = [c.jan for c in candidates if c.jan not in cached]
    log(
        f"段3: Keepa 検証 対象{len(candidates)}件 "
        f"（うち取得済み{len(candidates) - len(todo)}件・今回{len(todo)}件）"
    )
    if new_limit and len(todo) > new_limit:
        # 1回の実行で新規に検証する件数の上限。**キャッシュ済みは数えません。**
        # これを付けると、長時間ジョブを「何度でも足せる短いジョブ」に割れます
        # （毎回 candidates.csv が最新まで書き直され、途中で落ちても損は1周分だけ）。
        todo = todo[:new_limit]
        log(f"  --new-limit により今回は新規{len(todo)}件だけ検証します")

    verifier = keepa_verify.KeepaVerifier(log=log)
    status = verifier.token_status()
    log(f"  Keepa 残トークン {status.get('tokensLeft')} / 補充 {status.get('refillRate')}/分")
    tokens_before = verifier.budget.left

    def save(batch):
        factstore.append([_facts_to_dict(f) for f in batch])

    def tick(done, total, waiting_sec):
        BEAT.beat(
            "段3 Keepa検証", done=done, total=total,
            tokens_left=verifier.budget.left,
            tokens_per_code=round(verifier.budget.tokens_per_code, 2),
            note=(f"トークン回復待ち あと{waiting_sec}秒" if waiting_sec else "検証中"),
        )

    BEAT.beat("段3 Keepa検証", done=0, total=len(todo), note="開始")
    if todo:
        verifier.verify_all(todo, batch_size=cfg.keepa_batch, on_batch=save, on_tick=tick)

    cached = factstore.load()
    facts_by_jan = {jan: _dict_to_facts(row) for jan, row in cached.items()}

    # ⚠️ **未検証を「Amazon未出品」として出さない。**
    #    evaluate() に空の AmazonFacts を渡すと「Amazon未出品(同一JANのASINなし)」になります。
    #    それは「Keepa に聞いて無かった」という意味で、「まだ聞いていない」ではありません。
    #    キャッシュに found=False の行がある JAN だけが「本当に無い」です。
    #    無人ジョブが一番やってはいけないのが、この取り違え（未着手を結果として書くこと）。
    verified = [c for c in candidates if c.jan in facts_by_jan]
    unverified = len(candidates) - len(verified)
    if unverified:
        log(f"  ⚠ 未検証 {unverified}件 は CSV に出しません（Amazon未出品と区別できないため）")

    evaluations = [evaluate.evaluate(c, facts_by_jan[c.jan], cfg) for c in verified]

    # 利益ラインを超えた行だけ、実セラー数を確定する（6.5トークン/件と高い）。
    if verify_sellers:
        winners = [e for e in evaluations if e.is_profitable and e.facts.asin]
        log(f"  実セラー数の確定: {len(winners)}件 × 約6.5トークン ≒ {len(winners)*6.5:.0f}トークン")
        counts = verifier.verify_sellers([e.facts.asin for e in winners])
        for e in winners:
            n = counts.get(e.facts.asin)
            if n is not None:
                # 出所ラベルは AmazonFacts.seller_count_source が値から導出する。
                # ここで文字列を代入しない（入れ忘れの経路を作らないため）。
                e.facts.real_seller_count = n

    consumed = verifier.budget.consumed_total
    stats = {
        "candidates_total": len(candidates),
        "verified_cumulative": len(verified),
        "unverified_remaining": unverified,
        "coverage_pct": (
            round(len(verified) / len(candidates) * 100, 1) if candidates else 0
        ),
        "keepa_requests": verifier.requests_made,
        "keepa_codes_sent": verifier.codes_sent,
        "keepa_products_returned": verifier.products_returned,
        "keepa_tokens_consumed": consumed,
        "keepa_tokens_before": tokens_before,
        "keepa_tokens_left": verifier.budget.left,
        "keepa_cost_per_candidate": (
            round(consumed / len(todo), 3) if todo else None
        ),
    }
    return evaluations, stats


def _facts_to_dict(f) -> dict:
    d = dict(f.__dict__)
    d["package_mm"] = list(f.package_mm)
    return d


def _dict_to_facts(row: dict):
    row = dict(row)
    row["package_mm"] = tuple(row.get("package_mm") or ())
    known = keepa_verify.AmazonFacts.__dataclass_fields__.keys()
    facts = keepa_verify.AmazonFacts(**{k: v for k, v in row.items() if k in known})
    # 入数は**常に商品名から計算し直す**。pack_size を持たない古いキャッシュ行を
    # 「入数1」として読むと、まとめ売り出品の利益が数倍に膨らんで出てしまう。
    # 導出できる値をキャッシュの有無に依存させない。
    facts.pack_size = keepa_verify.detect_pack_size(facts.title)
    return facts


# =============================================================================
# 出力
# =============================================================================
def report(evaluations: list, all_candidates: list, cfg: config.ScanConfig) -> dict:
    rows = [evaluate.to_row(e) for e in evaluations]
    profitable = [e for e in evaluations if e.is_profitable]
    gems = [e for e in evaluations if e.result and e.result.verdict == profit_gem()]
    not_on_amazon = [e for e in evaluations if e.status == evaluate.STATUS_NOT_ON_AMAZON]

    # 純利益の降順。計算できなかった行は末尾へ。
    rows.sort(key=lambda r: (r["純利益"] if isinstance(r["純利益"], (int, float)) else -10**9),
              reverse=True)
    store.write_csv(CANDIDATES_CSV, evaluate.COLUMNS, rows)

    rejected = [
        {"商品名": c.product_name, "JAN": c.jan, "サプライヤー名": c.supplier_name,
         "卸値(税抜)": c.wholesale_ex_tax, "除外理由": c.reason,
         "NETSEA商品ページ": c.product_url}
        for c in all_candidates if c.verdict != screen.PASS
    ]
    store.write_csv(
        REJECTED_CSV,
        ["商品名", "JAN", "サプライヤー名", "卸値(税抜)", "除外理由", "NETSEA商品ページ"],
        rejected,
    )

    suppliers = evaluate.supplier_summary(evaluations, all_candidates)
    store.write_csv(SUPPLIERS_CSV, evaluate.SUPPLIER_COLUMNS, suppliers)

    bands: dict = {}
    for e in evaluations:
        if e.result is not None:
            b = evaluate.margin_band(e.result.margin_rate)
            bands[b] = bands.get(b, 0) + 1

    return {
        "evaluated": len(evaluations),
        "margin_bands": dict(sorted(bands.items())),
        "suppliers_with_profitable_item": sum(1 for s in suppliers if s["利益プラス"] > 0),
        "suppliers_listed": len(suppliers),
        "profitable_with_sales": sum(
            1 for e in evaluations
            if e.is_profitable and (e.facts.drops30 or 0) >= evaluate.DROPS_DECENT
        ),
        "amazon_found": sum(1 for e in evaluations if e.facts.found),
        "not_on_amazon": len(not_on_amazon),
        "profitable": len(profitable),
        "gems": len(gems),
        "hit_rate_vs_evaluated": (
            round(len(profitable) / len(evaluations) * 100, 1) if evaluations else 0
        ),
    }


def profit_gem() -> str:
    from calc.profit import VERDICT_GEM
    return VERDICT_GEM


# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true",
                    help="走っているスキャンの生死と進捗を1行で表示して終了")
    ap.add_argument("--stage", choices=["all", "harvest", "verify"], default="all")
    ap.add_argument("--suppliers", type=int, default=5,
                    help="処理するサプライヤー数。0 で全社（既定5＝小さく試す）")
    ap.add_argument("--max-items", type=int, default=2000,
                    help="1サプライヤーあたりの商品取得上限")
    ap.add_argument("--min-wholesale", type=int, default=config.WHOLESALE_MIN_YEN)
    ap.add_argument("--max-wholesale", type=int, default=config.WHOLESALE_MAX_YEN)
    ap.add_argument("--min-profit", type=int, default=config.MIN_NET_PROFIT_YEN)
    ap.add_argument("--keepa-batch", type=int, default=config.KEEPA_CODE_BATCH)
    ap.add_argument("--keepa-limit", type=int, default=0,
                    help="Keepa に投げる件数の上限（0＝制限なし）。トークンを守るための安全弁")
    ap.add_argument("--new-limit", type=int, default=0,
                    help="1回の実行で**新規に**検証する件数の上限（0＝制限なし）。"
                         "キャッシュ済みは数えない。長時間ジョブを短く割るために使う")
    ap.add_argument("--verify-sellers", action="store_true",
                    help="利益ライン超えの行だけ実セラー数を確定（6.5トークン/件）")
    ap.add_argument("--allow-regulated", action="store_true",
                    help="規制品キーワードで落とさない")
    ap.add_argument("--profile-csv", default=str(PROFILE_CSV_DEFAULT),
                    help="取引申請状況CSV（業態の一次情報）。カズヨが管理画面から取得したもの")
    ap.add_argument("--makers-first", action="store_true", default=True,
                    help="Keepaトークンをメーカーから先に使う（既定）。社長の狙いはメーカー仕入れ")
    ap.add_argument("--only-makers", action="store_true",
                    help="業態がメーカーのサプライヤーだけを対象にする")
    ap.add_argument("--allow-used", action="store_true",
                    help="中古品を除外しない。⛔ 古物商許可を取得してからのみ使用可")
    args = ap.parse_args()

    if args.status:
        # ⚠️ ここで ps や PID を見ないこと。PID は使い回されるし、
        #    生きているだけで何もしていないプロセスもある。**心拍の更新時刻だけを見る。**
        print(heartbeat.describe(HEARTBEAT))
        return

    cfg = config.ScanConfig(
        wholesale_min=args.min_wholesale,
        wholesale_max=args.max_wholesale,
        min_net_profit=args.min_profit,
        drop_regulated=not args.allow_regulated,
        drop_used=not args.allow_used,
        keepa_batch=args.keepa_batch,
    )

    started = time.time()
    stats = {"started_at": datetime.now(JST).isoformat(),
             "assumptions": cfg.costs.as_note()}

    if args.stage in ("all", "harvest"):
        stats["harvest"] = harvest(args.suppliers, args.max_items)

    profiles = supplier_profile.SupplierProfiles.load(args.profile_csv)
    if len(profiles):
        log(f"取引申請状況CSV: {len(profiles)}社を読み込みました（業態の一次情報）")
    else:
        log(f"⚠ 取引申請状況CSVが見つかりません（{args.profile_csv}）。業態は空欄になります")
    stats["profile_rows"] = len(profiles)

    candidates, all_candidates, screen_stats = build_candidates(cfg, profiles)
    stats["screen"] = screen_stats

    if args.only_makers:
        candidates = [c for c in candidates if c.business_type.startswith("メーカー")]
        log(f"  --only-makers により メーカーのみ {len(candidates)}件")
    elif args.makers_first:
        # 限られたトークンをメーカーから使う。業態不明は卸の後ろ（除外はしない）。
        rank = {"メーカー": 0, "卸専業": 1, "卸および小売業": 2, "その他": 3}
        candidates.sort(key=lambda c: (
            rank.get(c.business_type.split("（")[0], 9), c.wholesale_ex_tax))
        log("  メーカー優先で並べ替えました（--keepa-limit はこの順で消費されます）")

    if args.keepa_limit:
        # 直前の並べ替え（メーカー優先・その中で卸値の安い順）を尊重して先頭から取る。
        candidates = candidates[: args.keepa_limit]
        log(f"  --keepa-limit により先頭 {len(candidates)}件に絞ります")
        stats["screen"]["to_keepa"] = len(candidates)

    if args.stage in ("all", "verify"):
        evaluations, keepa_stats = verify(candidates, cfg, args.verify_sellers,
                                          new_limit=args.new_limit)
        stats["keepa"] = keepa_stats
        stats["result"] = report(evaluations, all_candidates, cfg)
        log("── 実測 ────────────────────────────────")
        log(f"  NETSEA 商品          : {stats['screen']['netsea_products']}件")
        log(f"  規格展開             : {stats['screen']['candidates_expanded']}件")
        log(f"  段2 通過             : {stats['screen']['to_keepa']}件")
        log(f"  Keepa 検証済み(累計) : {keepa_stats['verified_cumulative']}"
            f" / {keepa_stats['candidates_total']}件"
            f"（{keepa_stats['coverage_pct']}%）"
            f"  ← 残り未検証 {keepa_stats['unverified_remaining']}件")
        log(f"  Keepa 消費トークン   : {keepa_stats['keepa_tokens_consumed']}")
        log(f"  1件あたり実効コスト  : {keepa_stats['keepa_cost_per_candidate']} トークン")
        log(f"  Amazon に存在        : {stats['result']['amazon_found']}件")
        log(f"  Amazon に無い        : {stats['result']['not_on_amazon']}件"
            "（好機か需要ゼロかは、この数字だけでは区別できません）")
        log(f"  利益プラス           : {stats['result']['profitable']}件")
        log(f"  うち回転もある(30日3個以上): {stats['result']['profitable_with_sales']}件"
            "  ← 社長に見せるべきはここ")
        log(f"  利益率の分布           : {stats['result']['margin_bands']}")
        log(f"  取引先{stats['result']['suppliers_listed']}社中、"
            f"利益の出る商品を持つ社: {stats['result']['suppliers_with_profitable_item']}社")
        log(f"  → 取引先一覧 {SUPPLIERS_CSV}")
        log(f"  → {CANDIDATES_CSV}")

    stats["elapsed_sec"] = round(time.time() - started, 1)
    BEAT.beat("完了", note=f"所要 {stats['elapsed_sec']:.0f}秒")
    store.write_json(STATS_JSON, stats)
    log(f"統計を {STATS_JSON} に保存しました")


if __name__ == "__main__":
    main()
