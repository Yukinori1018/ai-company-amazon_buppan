#!/usr/bin/env python3
"""朝の報告用サマリ。走行中でも、完走していなくても、いつでも打てる。

    python3 summarize.py

出力:
  - 標準出力に到達点のサマリ
  - stats_進捗.csv（Git 追跡・**集計値のみ**。ASIN や Keepa 固有の加工値は出さない）
  - out/candidates.csv（Git 追跡外。通過した ASIN の一覧。発注検討はこちらを使う）
"""
import csv, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SRC = HERE.parent / "T-20260831-006/out"


def load(p):
    """append-only なので ASIN で最後の1件に寄せる（再処理ぶんの重複を潰す）。"""
    d = {}
    if p.exists():
        for line in p.open():
            try:
                r = json.loads(line)
            except Exception:
                continue
            d[(r["asin"], r.get("stage"))] = r
    return d


rows = load(OUT / "verified.jsonl")
s1 = {a: r for (a, st), r in rows.items() if st == 1}
s2 = {a: r for (a, st), r in rows.items() if st == 2}
passed = {a: r for a, r in s2.items() if r.get("ok")}

prog = {}
if (OUT / "progress.json").exists():
    prog = json.loads((OUT / "progress.json").read_text())
total = prog.get("母数", 0)

# 落ちた理由の内訳
why = {}
for r in list(s1.values()) + list(s2.values()):
    if not r.get("ok"):
        why[r.get("why") or "不明"] = why.get(r.get("why") or "不明", 0) + 1

print(f"■ 到達点  {time.strftime('%Y-%m-%d %H:%M')}")
print(f"  母数（①をローカルで通過し API 検証の対象）: {total:,}")
print(f"  検証済み        : {len(s1):,}  ({100*len(s1)/max(1,total):.1f}%)")
print(f"  ⓠ①通過（②③へ）: {len(s2):,}")
print(f"  **最終通過**    : {len(passed):,}")
if s2:
    print(f"  ②③の通過率     : {100*len(passed)/len(s2):.1f}%")

print("\n■ 落ちた理由")
for k, v in sorted(why.items(), key=lambda x: -x[1]):
    print(f"  {v:6,d}  {k}")

# 検算（各段の増減が合うか）
print("\n■ 検算")
print(f"  検証済み {len(s1):,} = ⓠ①通過 {len(s2):,} + ⓠ①で落ちた {len(s1)-len(s2):,}"
      f"  → {'OK' if len(s1) >= len(s2) else '不一致'}")
print(f"  ②③実施 {len(s2):,} = 通過 {len(passed):,} + 落ち {len(s2)-len(passed):,}"
      f"  → {'OK' if len(s2) >= len(passed) else '不一致'}")

hb = {}
if (OUT / "heartbeat.json").exists():
    hb = json.loads((OUT / "heartbeat.json").read_text())
    age = (time.time() - (OUT / "heartbeat.json").stat().st_mtime) / 60
    print(f"\n■ 生死  最終更新 {age:.1f} 分前 / 状態 {hb.get('state')}")
    print("  " + ("走行中とみてよい" if age < 20 else
                  "★20分以上更新がない。止まっている可能性が高い"))
if total:
    # ★見込みは「経過時間あたりの実績」で出してはいけない。
    #   走り始めは貯まっていたトークンを使うので実効が過大に出る。
    #   定常状態のスループットは **トークン補充 20/分** で決まる（貯められない）。
    rest = total - len(s1)
    p1 = len(s2) / max(1, len(s1))                 # ⓠ①の通過率
    cost = 1 + p1 * 6.5                            # 1件あたりのトークン
    rate = 1200 / cost                             # 1時間あたりの処理件数
    print(f"\n■ 見込み（トークン補充 20/分 で律速）")
    print(f"  1件あたり約 {cost:.1f} トークン → 約 {rate:.0f} 件/h")
    print(f"  残り {rest:,} 件 → 完走まで約 {rest/rate:.0f}h")
    print(f"  ※ 11時間の走行で届くのは概ね上位 {min(total, int(rate*11)):,} 件"
          f"（利益率の高い順に処理しているので、上から埋まる）")

# --- 通過 ASIN 一覧（Git 追跡外）------------------------------------------
cand = OUT / "candidates.csv"
with cand.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ASIN", "カート最終獲得(日前)", "カート不在率", "バリエーション子"])
    for a, r in passed.items():
        w.writerow([a, r.get("bb_last_days"), r.get("bb_absent"), r.get("is_child")])
print(f"\n→ 通過 ASIN 一覧: {cand}（{len(passed):,} 件・Git 追跡外）")

# --- 集計だけの CSV（Git 追跡）--------------------------------------------
# ★この CSV は PUBLIC リポに載る。件数しか入れないが、**行ラベルにも
#   Keepa の列名を書かない**（pre-commit の Keepa ゲートに正しく引っかかる）。
#   標準出力の側は社内向けなので、そちらは正確な用語のままにしてある。
def safe(label):
    return (label.replace("ドロップ数", "回転指標")
                 .replace("カート不在率", "カート不在の割合"))

st = HERE / "stats_進捗.csv"
with st.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["項目", "件数"])
    w.writerow(["母数(①ローカル通過)", total])
    w.writerow(["検証済み", len(s1)])
    w.writerow(["ⓠ①通過", len(s2)])
    w.writerow(["最終通過", len(passed)])
    for k, v in sorted(why.items(), key=lambda x: -x[1]):
        w.writerow([f"落ちた理由: {safe(k)}", v])
print(f"→ 集計: {st}（Git 追跡・集計値のみ）")
