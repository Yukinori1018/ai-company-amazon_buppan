#!/usr/bin/env python3
"""キーゾン「過去1/2/3ヶ月目の販売数（新品）」を Keepa の売れ筋ランク履歴（csv[3]）から再現する。
2026-10-11 タカシ（T-20260920-003）。

式（キーゾン実画面 25 ASIN・75か月分で検算して採用）
  m_k = 「now−30k日 〜 now−30(k−1)日」に、ランクが直前の観測より 3% を超えて良くなった回数
  now = Keepa から取得した時刻。ランクなし（-1）を挟んだら直前値をリセット。
  一致度：月ごとの絶対誤差の平均 0.08 個・3か月合計の誤差の平均 0.16 個・最大誤差 1 個・
          完全一致 69/75（取得時刻が確定している 10/11 組は 27/27 完全一致）。

注意（推定の限界。台帳に書くときは必ず添える）
  - バリエーションの子はランクを兄弟と共有する＝この数は family 合計（キーゾン自身も同じ値を出す）。
  - 1回の観測間隔に2個以上売れると1回に潰れる＝売れる商品ほど過小。検算できたのは月0〜13個の範囲だけ。
  - その月の観測が少ない（<10回）月は 0 と区別できない → 「観測少」を立てる。
置き場（2026-10-27 T-20261027-001）
  式はこのファイル（Git 管理）。データは agent_output（Git 対象外・Keepa の生データ）に置いたまま。
  旧置き場 agent_output/T-20260920-003/ledger20261010/kz_estimate.py は、ここを呼ぶだけの薄い入口。

使い方：python3 scripts/sourcing_gate/kz_estimate.py [データのフォルダ]
  データのフォルダ省略時は workspace/output/agent_output/T-20260920-003/ledger20261010
  入力：kz_queue_20261011.txt / keepa_unknown_20261011.jsonl / keepa_kz_hist_20261011.jsonl（取得済み生データ）
  出力：kz_estimate_20261011.csv（同じフォルダ）
  ほかのコードからは months(product, now) だけを import して使ってよい。
"""
import csv, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
O = REPO / "workspace/output/agent_output/T-20260920-003/ledger20261010"  # main() の既定のデータ置き場
T0 = 21564000
THR = 0.03
FORMULA = "30日窓ごとにランクが直前観測より3%超改善した回数"
MATCH = "キーゾン25ASIN×3か月で月MAE0.08個・3か月合計MAE0.16個・最大誤差1個・完全一致69/75"

def months(p, now):
    c = (p.get("csv") or [None] * 4)[3] or []
    ps = [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
    out, obs = [], []
    for k in (1, 2, 3):
        lo, hi = now - 30 * k * 1440, now - 30 * (k - 1) * 1440
        n = o = 0; prev = None
        for t, r in ps:
            if r <= 0:
                prev = None; continue
            if lo <= t < hi:
                o += 1
                if prev is not None and (prev - r) / prev > THR:
                    n += 1
            prev = r
        out.append(n); obs.append(o)
    return out, obs

def main():
    global O
    if len(sys.argv) > 1:
        O = Path(sys.argv[1]).resolve()
    q = [a.strip() for a in (O / "kz_queue_20261011.txt").read_text().replace("\n", ",").split(",") if a.strip()]
    P = {}
    for f in ("keepa_unknown_20261011.jsonl", "keepa_kz_hist_20261011.jsonl"):
        p = O / f
        if p.exists():
            for l in p.open():
                d = json.loads(l); P[d["asin"]] = d
    rows = []
    for a in q:
        d = P.get(a)
        if not d:
            rows.append({"ASIN": a, "式": FORMULA, "一致度": MATCH, "注意": "Keepa 未取得"}); continue
        p = d["product"]; now = d["fetched"] // 60 - T0
        m, obs = months(p, now)
        note = []
        if p.get("parentAsin"): note.append("バリエーション子＝family合計")
        if any(o < 10 for o in obs): note.append("観測少(" + "/".join(map(str, obs)) + ")")
        if max(m) > 13: note.append("月13個超は未検算・過小の可能性")
        if not (p.get("csv") or [None]*4)[3]: note.append("ランク履歴なし")
        rows.append({"ASIN": a, "推定m1": m[0], "推定m2": m[1], "推定m3": m[2],
                     "3か月平均": round(sum(m) / 3, 1), "式": FORMULA, "一致度": MATCH,
                     "観測回数m1/m2/m3": "/".join(map(str, obs)), "注意": "・".join(note)})
    cols = ["ASIN", "推定m1", "推定m2", "推定m3", "3か月平均", "式", "一致度", "観測回数m1/m2/m3", "注意"]
    with (O / "kz_estimate_20261011.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
    est = [r for r in rows if "推定m1" in r]
    ok = [r for r in est if r["3か月平均"] >= 3]
    print(f"対象 {len(q)}・推定 {len(est)}・未取得 {len(q)-len(est)}")
    print(f"3か月平均≥3: {len(ok)}（うち family {sum('family' in r['注意'] for r in ok)}・観測少 {sum('観測少' in r['注意'] for r in ok)}）")
    print(f"m1≥3: {sum(r['推定m1']>=3 for r in est)}・3か月すべて≥3: {sum(min(r['推定m1'],r['推定m2'],r['推定m3'])>=3 for r in est)}・3か月とも0: {sum(r['推定m1']+r['推定m2']+r['推定m3']==0 for r in est)}")
    clean = [r for r in ok if not r["注意"]]
    print(f"3か月平均≥3 かつ 注意なし: {len(clean)}")

if __name__ == "__main__":
    main()
