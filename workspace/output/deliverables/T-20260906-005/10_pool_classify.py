# -*- coding: utf-8 -*-
"""出展社2,353件を「社長が連絡すべきメーカー候補」かどうかで機械分類する。
落とした理由コードを必ず残す（何件がなぜ落ちたかを報告するため）。
"""
import csv, re, sys, unicodedata
from collections import Counter
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CSVP = REPO / "workspace/output/agent_output/T-20260831-005/tigs102_出展社リスト_全件.csv"
OUT = REPO / "workspace/output/agent_output/T-20260906-005"

FOREIGN = re.compile(r"(CO\.,?\s*LTD|LIMITED|INC\.?|LLC|CORP|PTE|SDN|GMBH|S\.?A\.?$)", re.I)
# 団体・支援機関・自治体・教育機関＝メーカーではない（連絡先としては無効）
ORG = re.compile(r"(商工会議所|商工会$|商工会／|商工会 |協同組合|事業協同組合|工業会|協会|"
                 r"連合会|振興会|振興機構|推進機構|promotion|県$|市$|町$|村$|"
                 r"大学|高校|高等学校|専門学校|JETRO|ジェトロ|公社|財団|一般財団|公益財団|"
                 r"組合連合|農業協同組合|漁業協同組合|観光|物産振興)")
# 版元・音楽・ゲーム＝社長確定の除外カテゴリ
EXCL_CAT = re.compile(r"(出版|書店|レコード|ミュージック|音楽|ゲーム|DVD|CD|書房|文庫|新聞社)")
# 商社・輸入代理店＝「メーカー直」ではない（別枠。落とさず区別）
TRADING = re.compile(r"(貿易|インポート|IMPORT|商事|物産|輸入|ディストリビュー|エージェンシー|"
                     r"代理店|コンサル|マーケティング|デザイン事務所|デザイン研究室|広告)", re.I)


def is_ascii_heavy(s):
    a = sum(1 for c in s if ord(c) < 128)
    return a / max(1, len(s)) > 0.7


rows = list(csv.DictReader(open(CSVP, encoding="utf-8")))
seen = set()
out = []
reasons = Counter()
for r in rows:
    e = (r.get("exhibitor") or "").strip()
    if not e:
        continue
    if e in seen:
        reasons["重複"] += 1
        continue
    seen.add(e)
    n = unicodedata.normalize("NFKC", e)
    if FOREIGN.search(n) or is_ascii_heavy(n):
        code = "海外表記(国内から仕入れられない)"
    elif ORG.search(n):
        code = "団体・自治体・教育機関(メーカーでない)"
    elif EXCL_CAT.search(n):
        code = "除外カテゴリ(版元/音楽/ゲーム)"
    elif TRADING.search(n):
        code = "商社・代理店・デザイン(メーカー直でない)"
    else:
        code = "PASS"
    reasons[code] += 1
    out.append({"exhibitor": e, "booth": r.get("booth", ""), "class": code})

w = csv.DictWriter(open(OUT / "13_pool_class.csv", "w", encoding="utf-8", newline=""),
                   fieldnames=["exhibitor", "booth", "class"])
w.writeheader()
w.writerows(out)
print("raw rows:", len(rows))
for k, v in reasons.most_common():
    print(f"  {k}: {v}")
