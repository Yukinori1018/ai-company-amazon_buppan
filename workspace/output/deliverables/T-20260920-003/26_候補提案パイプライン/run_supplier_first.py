#!/usr/bin/env python3
"""仕入れ先起点（NETSEA → Amazon）の候補抽出ドライバ。

**新しい道具ではありません。** 既にある `discover.py` / `profit.py` / `set_count.py` を
NETSEA の JAN 索引（67,662件）に向けて回すだけの薄い配線です。

段取り
------
1. 0トークンの前段フィルタで JAN を絞り、**GO が出やすい順**に並べる
2. `discover.resolve_to_asins` で JAN → ASIN（ハズレ JAN は0トークン）
3. `discover.to_candidates` で「死んでいる棚・売価なし・赤字」を0トークンで落とす
4. 残りを `discovered.json` に積む（= `candidate_pipeline.py` の母数になる）

トークン
--------
残高は1,200が天井・補充20/分（memory: knowledge_keepa_token_ceiling_and_unattended_scan）。
**バッチを投げる前に残高を見て、下限を割るなら投げずに待ちます**（前回これで使い切った）。

出力は全部 `agent_output/`（Git 追跡外）。卸値・卸URL を含むため。
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
PIPE = REPO / "workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
GUARD = REPO / "workspace/output/deliverables/T-20260920-003/24_カート保持者ガード"
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(GUARD))

import discover                       # noqa: E402
from keepa_client import load_api_key  # noqa: E402

WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
TRIED = WORK / "tried_jans.json"       # 一度 Keepa に投げた JAN（二度払わないため）
BUDGET = WORK / "daily_token_budget.json"   # 日ごとの消費（1日の上限を跨いだ実行でも守る）
STOP = WORK / "STOP"                   # これがあれば起動しない（消し方は起動時に案内する）


def spent_today(path: Path = BUDGET) -> tuple[str, int, dict]:
    """今日すでに何トークン使ったか。**プロセスを跨いで数える**（夜間は複数回走る）。"""
    today = date.today().isoformat()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
    return today, int(data.get(today) or 0), data


def record_spend(n: int, path: Path = BUDGET) -> int:
    """消費を**バッチごとに**記録する。最後にまとめて書くと、途中で止まった回が0扱いになる。"""
    today, before, data = spent_today(path)
    data[today] = before + int(n)
    for k in list(data):                      # 30日より古い記録は捨てる
        if k < (date.today() - timedelta(days=30)).isoformat():
            data.pop(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data[today]

# ── 0トークンの前段フィルタ ───────────────────────────────────────────────

# 賞味期限管理が要る／ゲートが固いカテゴリを匂わせる語（§3.3 ゲート⑦）。
# ここで落とさないと、後段で 6トークン/ASIN 払ってから UNKNOWN になる。
EXCLUDE_WORDS = (
    "サプリ", "青汁", "酵素", "乳酸菌", "コラーゲン", "プロテイン", "アミノ",
    "ビタミン", "栄養", "健康食品", "食品", "飲料", "ドリンク", "ジュース",
    "菓子", "チョコ", "クッキー", "せんべい", "ゼリー", "キャンディ", "グミ",
    "レトルト", "カレー", "スープ", "麺", "ラーメン", "そば", "うどん", "パスタ",
    "米", "お茶", "緑茶", "紅茶", "コーヒー", "ビール", "ワイン", "日本酒",
    "焼酎", "ウイスキー", "リキュール", "梅酒", "酒 ",
    "コンドーム", "医薬品", "第2類", "第3類", "指定医薬部外品",
    "ペットフード", "ドッグフード", "キャットフード", "おやつ",
)

# 採算の下限を 0トークンで見るための式（profit.py と同じ前提）。
#   net = 0.9076*sell - 621 - cost      （販売手数料9.24%税込・FBA415・保管等206）
#   GO 条件: net >= 0.07*sell + 200     （誤差幅）
# → sell >= (821 + 1.1*w) / 0.8376
def required_sell(wholesale_excl: float) -> float:
    return (821 + 1.1 * float(wholesale_excl)) / 0.8376


def tier(rec: dict) -> int | None:
    """判定する優先度。None なら今回は投げない。"""
    w = rec.get("unit_price_excl")
    if not w or not (300 <= w <= 9000):
        return None
    if str(rec.get("stock")) == "品切れ":
        return None
    lot = int(rec.get("min_lot_units") or 1)
    title = rec.get("title") or ""
    if any(word in title for word in EXCLUDE_WORDS):
        return None
    if lot > 24:
        return None                     # ロットが大きすぎて6ヶ月で捌けない／予算に載らない
    rp = rec.get("reference_price")
    if rp and rp >= required_sell(w):
        return 0 if lot <= 12 else 1    # 上代ベースで黒字が見込める
    if rp and rp < required_sell(w):
        return 4                        # 上代でも届かない＝Amazon 価格でも厳しい（最後）
    # 上代が無い。必要な倍率が小さい価格帯（卸1,000〜6,000円）を優先する。
    if 1000 <= w <= 6000:
        return 2 if lot <= 12 else 3
    return 3


def plan(index: dict, tried: set[str]) -> list[tuple[int, str, dict]]:
    rows = []
    for jan, rec in index.items():
        if jan in tried or not re.match(r"^\d{12,13}$", jan):
            continue
        t = tier(rec)
        if t is None:
            continue
        rows.append((t, jan, rec))
    # 同じ tier の中は「上代/卸値の倍率が大きい順」（＝余裕が大きい順）。
    def key(row):
        t, _jan, rec = row
        rp = rec.get("reference_price") or 0
        w = rec.get("unit_price_excl") or 1
        return (t, -(rp / w))
    return sorted(rows, key=key)


# ── 残高を見てから投げる ──────────────────────────────────────────────────


def tokens_left(key: str) -> int:
    raw = urllib.request.urlopen(f"https://api.keepa.com/token?key={key}", timeout=60).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return int(json.loads(raw.decode()).get("tokensLeft") or 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--total-tokens", type=int, default=900, help="今回の実行ぶんの予算")
    ap.add_argument("--daily-tokens", type=int, default=0,
                    help="1日に使ってよい総量（0なら無制限）。複数回の実行を跨いで守る")
    ap.add_argument("--floor", type=int, default=240, help="これ以下まで減らさない残高")
    ap.add_argument("--minutes", type=int, default=75, help="通算の上限（分）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if STOP.exists():
        print(f"STOP ファイルがあるので起動しません: {STOP}\n"
              f"再開するには削除してください: rm '{STOP}'")
        return 0

    # 1日の上限。**残りがゼロなら今回の予算もゼロにする**（夜間に何回起動しても超えない）。
    if a.daily_tokens:
        today, already, _ = spent_today()
        room_today = max(0, a.daily_tokens - already)
        if room_today <= 0:
            print(f"今日（{today}）はすでに {already} トークン使っています"
                  f"（上限 {a.daily_tokens}）。何もしません。")
            return 0
        if room_today < a.total_tokens:
            print(f"今日の残り {room_today} トークンに合わせて予算を縮めます"
                  f"（指定 {a.total_tokens}・今日の消費 {already}/{a.daily_tokens}）")
            a.total_tokens = room_today

    index = discover.load_index()["jans"]
    tried = set(json.loads(TRIED.read_text()) if TRIED.exists() else [])
    todo = plan(index, tried)
    from collections import Counter
    print(f"索引 {len(index):,}件 / 既投 {len(tried):,}件 → 今回の対象 {len(todo):,}件")
    print("  tier 内訳:", dict(sorted(Counter(t for t, _, _ in todo).items())))
    if a.dry_run or not todo:
        for t, jan, rec in todo[:15]:
            print(f"  t{t} {jan} 卸{rec['unit_price_excl']} 上代{rec.get('reference_price')} "
                  f"lot{rec.get('min_lot_units')} {rec['title'][:44]}")
        return 0

    key = load_api_key()
    cache = discover.load_cache()
    spent_total, start = 0, time.time()
    i = 0
    while i < len(todo) and spent_total < a.total_tokens:
        if STOP.exists():
            print("STOP ファイルを検知したので安全に止めます。", flush=True)
            break
        if time.time() - start > a.minutes * 60:
            print("時間上限に達しました。")
            break
        left = tokens_left(key)
        room = min(left - a.floor, a.total_tokens - spent_total)
        if room < 60:
            wait = min(300, max(60, int((a.floor + 60 - left) / 20 * 60) if left < a.floor + 60 else 60))
            print(f"残高 {left}（下限 {a.floor}）。{wait}秒待ちます。")
            time.sleep(wait)
            continue
        # ⚠️ **1リクエスト分（100件）ずつ渡す。**300件渡すと `resolve_to_asins` が
        # 予算切れで途中で止めたとき、**投げていない JAN まで「既投」に記録**してしまい、
        # 二度と拾わなくなる（2026-10-01 に134件そうした。復旧済み）。
        chunk = todo[i:i + discover.CODE_BATCH]
        i += len(chunk)
        jans = [j for _t, j, _r in chunk]
        netsea = {j: r for _t, j, r in chunk}
        by_jan, spent = discover.resolve_to_asins(jans, token_budget=room, api_key=key)
        spent_total += spent
        cands, tally = discover.to_candidates(netsea, by_jan)
        for c in cands:
            cache.setdefault("candidates", {})[c.asin] = c.__dict__
        tried.update(jans)
        discover.save_cache(cache)
        TRIED.write_text(json.dumps(sorted(tried)))
        if a.daily_tokens:
            record_spend(spent)
        print(f"  == 累計消費 {spent_total}/{a.total_tokens} / 候補プール "
              f"{len(cache.get('candidates', {}))}件 ==", flush=True)

    rest = len(todo) - i
    print(f"\n完了: 消費 {spent_total} / 候補プール {len(cache.get('candidates', {}))}件 / "
          f"未投入の JAN 残り {rest:,}件")
    if a.daily_tokens:
        _t, total, _ = spent_today()
        print(f"今日の消費: {total}/{a.daily_tokens} トークン")
    # ⚠️ 完走フラグは書きません。--total-tokens を切った回は「全部やり切った」ではないので
    #    （memory: knowledge_keepa_token_ceiling_and_unattended_scan §9）。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
