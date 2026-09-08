#!/usr/bin/env python3
"""再評価の結果から、社長にお出しする上位10件を作る。

**入数が解けている行だけ**を並べる。解けていない行は利益率が入数倍に膨らむので、
混ぜた瞬間に上位が汚染される（2026-09-07 の事故）。

金額を含む一覧は out/ に出す（Git 追跡外。Amazon価格＋手数料モデルから卸値を逆算できるため）。
"""
import csv, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.load((HERE / "out/reevaluated.json").open())
inrun = [r for r in rows if r["in_run"]]

N = 10
for name, data in (("全体", rows), ("回転検証も通過", inrun)):
    print(f"\n===== 上位{N}件（{name}・{len(data):,}件から）=====")
    for i, r in enumerate(data[:N], 1):
        mark = " ★要書類確認" if r.get("requires_document_check") else ""
        print(f"{i:2d}. 利益率{r['margin']*100:5.1f}%  入数{r['pack']:>3}  "
              f"{r['amazon_title'][:42]}{mark}")
        for f in r.get("flags", []):
            print(f"     印: {f[:74]}")

with (HERE / "out/top10.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["順位", "ASIN", "Amazon商品名", "NETSEA商品名", "サプライヤー",
                "出品の入数", "入数の根拠", "利益率%", "純利益", "総合判定",
                "PSE判定", "PSE規則", "要書類確認(通過≠発注可)", "確認事項",
                "その他の印", "回転検証(T-20260906-003)", "Amazonページ"])
    for i, r in enumerate(inrun[:N], 1):
        w.writerow([i, r["asin"], r["amazon_title"], r["netsea_name"], r["supplier"],
                    r["pack"], r["pack_reason"], round(r["margin"] * 100, 1),
                    round(r["net"]), r["verdict"],
                    r.get("pse_verdict", ""), r.get("pse_rule_id", ""),
                    "要" if r.get("requires_document_check") else "",
                    r.get("pse_review_note", ""),
                    " / ".join(r.get("flags", [])),
                    "通過" if r["in_run"] else "-", r["url"]])

# 全件版も出す（社長が母数を見たいと仰ることがあるため）
with (HERE / "out/all_candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ASIN", "Amazon商品名", "サプライヤー", "出品の入数", "利益率%",
                "純利益", "PSE判定", "要書類確認", "その他の印", "回転検証"])
    for r in rows:
        w.writerow([r["asin"], r["amazon_title"], r["supplier"], r["pack"],
                    round(r["margin"] * 100, 1), round(r["net"]),
                    r.get("pse_verdict", ""),
                    "要" if r.get("requires_document_check") else "",
                    " / ".join(r.get("flags", [])),
                    "通過" if r["in_run"] else "-"])

n_doc = sum(1 for r in inrun if r.get("requires_document_check"))
n_ip = sum(1 for r in inrun if any("知財" in x for x in r.get("flags", [])))
print(f"\n■ 回転検証も通過した {len(inrun):,} 件の内訳")
print(f"  PSE要書類確認（通過だが発注可ではない）: {n_doc:,}")
print(f"  知財ブランドのフラグつき（ゲート確認の対象）: {n_ip:,}")
print(f"\n→ 上位{N}件の明細: {HERE/'out/top10.csv'}")
print(f"→ 全候補: {HERE/'out/all_candidates.csv'}（Git 追跡外・Finder から開けます）")
