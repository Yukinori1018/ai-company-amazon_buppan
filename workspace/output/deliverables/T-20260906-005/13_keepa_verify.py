# -*- coding: utf-8 -*-
"""第一陣候補メーカーの Amazon.co.jp 上の取扱状況を Keepa で「検証」する。
発見用途ではない。1社1クエリ(10トークン)に限定し、トークンを浪費しない。
"""
import csv, json, os, re, subprocess, sys, time, unicodedata, urllib.parse
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
OUT = REPO / "workspace/output/agent_output/T-20260906-005"
KEY = None
for line in open(REPO / "workspace/output/agent_output/T-20260521-005/code/.env", encoding="utf-8"):
    if line.startswith("KEEPA_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
assert KEY

# 検証対象: (社名, Keepaに投げる検索語) — 検索語はブランド/商品名寄りにする
TARGETS = [
    ("株式会社宇野刷毛ブラシ製作所", "宇野刷毛ブラシ"),
    ("有限会社大橋量器", "大橋量器 枡"),
    ("株式会社木村硝子店", "木村硝子店"),
    ("田中帽子店", "田中帽子店"),
    ("朝倉染布株式会社", "朝倉染布"),
    ("廣田硝子株式会社", "廣田硝子"),
    ("河野製紙株式会社", "河野製紙"),
    ("守田漆器株式会社", "守田漆器"),
    ("池本刷子工業株式会社", "池本刷子"),
    ("楠橋紋織株式会社", "楠橋紋織"),
    ("側島製罐株式会社", "側島製罐"),
    ("金野タオル株式会社", "金野タオル"),
    ("本野はきもの工業", "本野はきもの"),
    ("株式会社北尾化粧品部", "北尾化粧品"),
    ("株式会社清水硝子", "清水硝子 江戸切子"),
    ("木内籐材工業株式会社", "木内籐材"),
    ("小野甚味噌醤油醸造株式会社", "小野甚"),
    ("七福タオル株式会社", "七福タオル"),
    ("株式会社高柳製茶", "高柳製茶"),
    ("亀崎染工有限会社", "亀染屋"),
]


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for w in ["株式会社", "有限会社", "合同会社", "（株）", "(株)", "（有）", "(有)"]:
        s = s.replace(w, "")
    return re.sub(r"[\s\-‐―–—・.,'\"()（）]", "", s).lower()


def get(url):
    p = subprocess.run(["curl", "-s", "--compressed", "--max-time", "60", url],
                       capture_output=True)
    return json.loads(p.stdout.decode("utf-8"))


w = csv.writer(open(OUT / "21_keepa_verify.csv", "w", encoding="utf-8", newline=""))
w.writerow(["company", "term", "hits", "brand_match", "matched_field_value",
            "top_asin", "top_title", "tokensLeft"])

for name, term in TARGETS:
    url = (f"https://api.keepa.com/search?key={KEY}&domain=5&type=product"
           f"&term={urllib.parse.quote(term)}")
    d = None
    for _ in range(6):
        try:
            d = get(url)
            break
        except Exception as ex:
            print("retry", name, ex, flush=True)
            time.sleep(45)
    if d is None:
        print("FAIL", name, flush=True)
        continue
    left = d.get("tokensLeft", -1)
    prods = d.get("products") or []
    n = norm(name)
    nt = norm(term)
    mv, match = "", "NO"
    for p in prods:
        for f in ("brand", "manufacturer"):
            v = p.get(f) or ""
            if v and (n in norm(v) or norm(v) in n or nt in norm(v) or norm(v) in nt):
                match, mv = "YES", f"{f}:{v}"
                break
        if match == "YES":
            break
    top = prods[0] if prods else {}
    w.writerow([name, term, len(prods), match, mv,
                top.get("asin", ""), (top.get("title") or "")[:60], left])
    print(f"{name} hits={len(prods)} match={match} {mv} left={left}", flush=True)
    if left is not None and left < 40:
        print("  ...tokens low, wait 120s", flush=True)
        time.sleep(120)
    else:
        time.sleep(3)
print("DONE", flush=True)
