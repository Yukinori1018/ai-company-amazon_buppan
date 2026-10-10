#!/usr/bin/env python3
"""規定（CLAUDE.md）と実装を揃えた2件のテスト（2026-10-11）。

    python3 test_rules_20261011.py

1. 実売 `score_20261004.velocity_of()` ＝ §3.3-8
   10万位以内 PASS ／ 10万〜50万位 UNKNOWN ／ 50万位より下 FAIL（NO-GO）
2. 採算 `fba_cost.grade()` ＝ §3.5 #18
   A＝中央・悲観とも〔20%以上 または 400円以上〕／B＝中央で〔5%以上 または 400円以上〕かつ A でない／
   C＝中央でどちらも満たさない／推定費目ありは最高 B

どちらも旧実装は規定とずれていた（実売は30万位で FAIL、採算は中央20%未満を C）。
境界値と縮退入力（欠損・0・負・型違い・全部同じ値）を固定する。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[4] / "scripts/sourcing_gate"))

import fba_cost as F                 # noqa: E402
import score_20261004 as S           # noqa: E402

FAILS: list[str] = []


def eq(got, want, label):
    ok = got == want
    print(f"  {'ok' if ok else 'NG'} {label}（got={got!r} want={want!r}）")
    if not ok:
        FAILS.append(label)


def prod(rank=None, ms=None, current=None, stats=True):
    p: dict = {}
    if ms is not None:
        p["monthlySold"] = ms
    if stats:
        cur = current if current is not None else [-1, -1, -1, rank if rank is not None else -1]
        p["stats"] = {"current": cur}
    return p


print("■ 実売（§3.3-8）")
eq(S.velocity_of(prod(rank=50_000))[0], "PASS", "5万位・共有なし → PASS")
eq(S.velocity_of(prod(rank=100_000))[0], "PASS", "境界 10万位ちょうど → PASS")
eq(S.velocity_of(prod(rank=100_001))[0], "UNKNOWN", "10万1位 → UNKNOWN")
eq(S.velocity_of(prod(rank=300_001))[0], "UNKNOWN", "30万1位 → UNKNOWN（旧実装は FAIL）")
eq(S.velocity_of(prod(rank=500_000))[0], "UNKNOWN", "境界 50万位ちょうど → UNKNOWN")
eq(S.velocity_of(prod(rank=500_001))[0], "FAIL", "50万1位 → FAIL")
eq(S.velocity_of(prod(rank=900_000, ms=120))[0], "PASS", "monthlySold があればランクに関係なく PASS")
eq(S.velocity_of(prod(rank=900_000, ms=120))[2], 120, "monthlySold を返す")
# 共有ランク
sh = {200_000: 3, 50_000: 2, 600_000: 4}
eq(S.velocity_of(prod(rank=50_000), sh)[0], "UNKNOWN", "共有ランクは10万位以内でも根拠にしない → UNKNOWN")
eq(S.velocity_of(prod(rank=200_000), sh)[0], "UNKNOWN", "共有ランク20万位 → UNKNOWN")
eq(S.velocity_of(prod(rank=600_000), sh)[0], "FAIL", "共有ランクでも50万位より下は一族ごと FAIL")
eq(S.velocity_of(prod(rank=400_000), {400_000: 1})[0], "UNKNOWN", "共有数1は共有でない")
# 縮退入力
eq(S.velocity_of({})[0], "UNKNOWN", "空の product → UNKNOWN（落とさない・通さない）")
eq(S.velocity_of(prod(stats=False))[0], "UNKNOWN", "stats 無し → UNKNOWN")
eq(S.velocity_of(prod(current=[]))[0], "UNKNOWN", "current が空 → UNKNOWN")
eq(S.velocity_of(prod(current=[1, 2, 3]))[0], "UNKNOWN", "current が3要素（ランク欄なし）→ UNKNOWN")
eq(S.velocity_of(prod(rank=0))[0], "UNKNOWN", "ランク0 → UNKNOWN")
eq(S.velocity_of(prod(rank=-1))[0], "UNKNOWN", "ランク-1（Keepa の欠損）→ UNKNOWN")
eq(S.velocity_of(prod(rank=None))[0], "UNKNOWN", "ランク None → UNKNOWN")
eq(S.velocity_of(prod(rank=50_000, ms=0))[0], "PASS", "monthlySold=0 は無視してランクで判定")
eq(S.velocity_of(prod(rank=700_000, ms=-1))[0], "FAIL", "monthlySold 負は無視")
eq(S.velocity_of(prod(rank=700_000, ms="120"))[0], "FAIL", "monthlySold が文字列なら信用しない")
eq(S.velocity_of(prod(rank=700_000, ms=True))[0], "FAIL", "monthlySold が bool なら信用しない")
eq(S.velocity_of(prod(rank=700_000, ms=12.5))[0], "FAIL", "monthlySold が float なら信用しない")
eq(S.velocity_of(prod(current=[-1, -1, -1, "50000"]))[0], "UNKNOWN", "ランクが文字列 → UNKNOWN")
eq(S.velocity_of(prod(rank=200_000), None)[0], "UNKNOWN", "shared_ranks=None でも動く")
# 縮退：全 ASIN が同じランク（全部共有）
allsame = {250_000: 10}
eq(S.velocity_of(prod(rank=250_000), allsame)[0], "UNKNOWN", "全部が同じランクを共有 → UNKNOWN")


print("■ 採算（§3.5 #18）")
cat = "ホーム&キッチン"


def g(sell, cost, tier="標準1", **kw):
    return F.grade(sell, cost, tier, category=cat, **kw)


def ok_a(sc):
    return sc["利益率(%)"] >= 20 or sc["手残り"] >= 400


def ok_b(sc):
    return sc["利益率(%)"] >= 5 or sc["手残り"] >= 400


# 規定の式そのもので期待値を出し、原価を1円刻みで振って全域を突き合わせる
mism = 0
seen = set()
for sell in (600, 750, 900, 1500, 3000, 6000):
    for cost in range(50, int(sell * 1.1), 7):
        for sw in (None, sell * 0.85):
            r = g(sell, cost, sell_worst=sw)
            exp = "C" if not ok_b(r.mid) else ("A" if ok_a(r.mid) and ok_a(r.worst) else "B")
            seen.add(exp)
            if r.grade != exp:
                mism += 1
eq(mism, 0, "全域（売価6点×原価1円刻み×悲観売価2通り）で等級が規定の式と一致")
eq(seen, {"A", "B", "C"}, "全域スイープで A/B/C の3つとも出る（テストが縮退していない）")

# 典型例
r = g(3000, 1800)
eq((r.grade, ok_b(r.mid), ok_a(r.mid)), ("B", True, False),
   "中央8.9%（5〜20%・400円未満）→ B（旧実装は C）")
r = g(1500, 900)
eq(r.grade, "C", "中央で赤字 → C")
r = g(1500, 396)
eq(r.grade, "A", "中央・悲観とも20%超 → A")
eq(F.grade(1500, 396, "標準1", category=cat, estimated=("保管月数（仮置き）",)).grade, "B",
   "推定費目ありは数字が A でも最高 B")
eq(F.grade(1500, 900, "標準1", category=cat, estimated=("保管月数",)).grade, "C",
   "推定費目ありでも C は C（天井であって下限ではない）")
eq(F.grade(1500, 396, "標準1", category=cat, estimated=()).grade, "A", "推定費目が空なら A のまま")
eq(F.grade(1500, 396, "標準1", category=cat, estimated=("",)).grade, "A", "空文字の推定費目は数えない")
eq("最小ロット" in g(3000, 1800).reason, True, "B の理由に「最小ロットで1回だけ」を書く")
eq("推定費目" in F.grade(1500, 396, "標準1", category=cat, estimated=("保管月数",)).reason, True,
   "推定で B にした理由を書く")

# 額の線（率は低いが400円以上）
r = g(20000, 17500, "標準4")
eq((r.mid["手残り"] >= 400, r.mid["利益率(%)"] < 5), (True, True) if r.mid["手残り"] >= 400 else (False, True),
   "高単価・低率の行の前提確認")
if r.mid["手残り"] >= 400:
    eq(r.grade in ("A", "B"), True, "利益率5%未満でも手残り400円以上なら C にしない")

# 縮退入力
eq(F.grade(None, 500, "小型").grade, "UNKNOWN", "売価 None → UNKNOWN")
eq(F.grade(0, 500, "小型").grade, "UNKNOWN", "売価0 → UNKNOWN")
eq(F.grade(-100, 500, "小型").grade, "UNKNOWN", "売価が負 → UNKNOWN")
eq(F.grade(1500, None, "小型").grade, "UNKNOWN", "原価 None → UNKNOWN")
eq(F.grade(1500, 0, "小型").grade, "UNKNOWN", "原価0 → UNKNOWN（推測で埋めない）")
eq(F.grade(1500, 396, None).grade, "UNKNOWN", "サイズ区分 None → UNKNOWN")
eq(F.grade(1500, 396, "小型", unit_decided=False).grade, "UNKNOWN", "セット数未確定 → UNKNOWN")
eq(F.grade(1500, 396, "標準1", category=cat, sell_worst=0).grade,
   F.grade(1500, 396, "標準1", category=cat).grade, "悲観売価0は中央売価で代用（落ちない）")
eq(F.grade(1500, 396, "標準1", category=cat, estimated=None).grade, "A", "estimated=None でも動く")


print("■ consistency（表の等級の検査も同じ規定）")
try:
    import consistency as C
    ctx = lambda n, m, wn, wm: {"net": n, "margin": m, "net_worst": wn, "margin_worst": wm}
    row = lambda gr: {C.COLS.grade: gr}
    eq(C._c_grade_rule(row("B"), ctx(268, 8.9, 160, 5.3)), None, "中央8.9%の B は NG にしない")
    eq(C._c_grade_rule(row("C"), ctx(268, 8.9, 160, 5.3)) is not None, True, "中央8.9%を C と書いたら NG")
    eq(C._c_grade_rule(row("B"), ctx(500, 30, 450, 25)), None, "数字が A で表が B（推定費目の天井）は NG にしない")
    eq(C._c_grade_rule(row("A"), ctx(268, 8.9, 160, 5.3)) is not None, True, "数字が B で表が A は NG")
    eq(C._c_grade_rule(row("C"), ctx(-50, -3, -100, -8)), None, "中央でどちらも満たさない C は OK")
except ImportError as ex:
    print(f"  (consistency を読めませんでした：{ex})")
    FAILS.append("consistency import")

print()
print("全件通過" if not FAILS else f"失敗 {len(FAILS)}件: {FAILS}")
sys.exit(1 if FAILS else 0)
