#!/usr/bin/env python3
"""再評価の結果から、社長にお出しする上位10件を作る。

**入数が解けている行だけ**を並べる。解けていない行は利益率が入数倍に膨らむので、
混ぜた瞬間に上位が汚染される（2026-09-07 の事故）。
金額を含む一覧は out/ に出す（Git 追跡外。逆算で卸値が出るため）。
"""
import csv, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.load((HERE / "out/reevaluated.json").open())
inrun = [r for r in rows if r["in_run"]]

for name, data in (("全体", rows), ("回転検証も通過", inrun)):
    top = data[:10]
    print(f"\n===== 上位10件（{name}・{len(data):,}件から）=====")
    for i, r in enumerate(top, 1):
        print(f"{i:2d}. 利益率{r['margin']*100:5.1f}%  入数{r['pack']:>3}  "
              f"{r['amazon_title'][:44]}")
        print(f"     根拠: {r['pack_reason'][:66]}")

# 社長用の明細（Git 追跡外）
with (HERE / "out/top10.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["順位", "ASIN", "Amazon商品名", "NETSEA商品名", "サプライヤー",
                "出品の入数", "入数の根拠", "利益率%", "純利益", "総合判定",
                "回転検証(T-20260906-003)", "Amazonページ"])
    for i, r in enumerate(inrun[:10], 1):
        w.writerow([i, r["asin"], r["amazon_title"], r["netsea_name"], r["supplier"],
                    r["pack"], r["pack_reason"], round(r["margin"] * 100, 1),
                    round(r["net"]), r["verdict"],
                    "通過" if r["in_run"] else "-", r["url"]])
print(f"\n→ 明細: {HERE/'out/top10.csv'}（Git 追跡外・Finder から開けます）")
