"""02_抽出の漏斗.md の数表部分を再生成する（0 token）— T-20260930-001。

    python3 40_report.py   # agent_output の funnel.json / funnel_post.json から数表を標準出力へ

公開してよいのは件数（統計）だけ。個別 ASIN の Keepa 加工値は出さない（法務判定 ABCD の B クラス）。
"""
import json
from pathlib import Path

import keepa_io

W = keepa_io.RAW.parent
pre = json.loads((W / "funnel.json").read_text())
post = json.loads((W / "funnel_post.json").read_text())

print("| 段 | 条件（累積） | 残件数 |\n|---|---|---:|")
for r in pre:
    print(f"| Finder | {r['step']} | {r['total']:,} |")
for label, n in post["funnel"]:
    print(f"| product | {label} | {n:,} |")
print(f"\nメーカー数 {post['メーカー数']:,} / 優先度 {post['優先度']}")
print("\n| 除外理由 | 社数 |\n|---|---:|")
for k, v in post["除外内訳(社)"].items():
    print(f"| {k} | {v} |")
print(f"\n要確認（本人カート疑い）: {post['要確認(残す社)']} 社 / カート保持者未取得: {post['カート保持者未取得(残す社)']} 社")
print(f"印（残す社）: {post['印(残す社)']}")
