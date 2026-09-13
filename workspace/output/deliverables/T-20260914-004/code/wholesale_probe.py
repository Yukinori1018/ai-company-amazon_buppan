#!/usr/bin/env python3
"""T-2 §4: 登録前の3卸に、上位30ブランドの「商品があるか」だけを非ログインで当てる。
- robots.txt: 卸問屋.com=全許可／SD=検索(word=)は許可／国分=robots.txt なし(404)。規約に自動取得の明示禁止なし（2026-09-14 確認）
- 件数だけ取る。価格は取らない（どこも会員限定）。2秒間隔・1回ずつ。raw は probe_raw.jsonl
"""
import csv, json, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict, Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
T2 = HERE.parents[4] / "workspace/output/deliverables/T-20260914-002/out/t2_input.csv"
OUT = HERE / f"probe_raw_{(sys.argv[1] if len(sys.argv) > 1 else 'all').replace(',', '_')}.jsonl"
UA = {"User-Agent": "Mozilla/5.0 (T-20260914-004 manual-scale check)"}
SLEEP = 2.0
SITES = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else {"oroshi", "sd", "kokubu"}
SKIP = {"ノーブランド品", "Generic", "アミューズメント専用景品", ""}

def http(url, data=None, enc="utf-8"):
    req = urllib.request.Request(url, data=data, headers={**UA, **({"Content-Type": "application/x-www-form-urlencoded"} if data else {})})
    b = urllib.request.urlopen(req, timeout=40).read(); time.sleep(SLEEP)
    return b.decode(enc, errors="replace")
def text(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S); return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))

def oroshi(q):
    # 画面の JS（header_etc.js K_TopSearch）と同じく ?sName= に語を付けて POST する。
    # POST 本文だけだと検索語が無視され「全商品の件数」が返る（2026-09-14 に踏んだ）
    t = http("https://www.orosidonya.com/users/shohinsearch.asp?sName=" + urllib.parse.quote(q, encoding="cp932"),
             urllib.parse.urlencode({"sr_syouhin": q}, encoding="cp932").encode(), "cp932")
    m = re.search(r"該当が\s*([\d,]+)\s*件", text(t)); return int(m.group(1).replace(",", "")) if m else 0
def sd(q):
    t = text(http("https://www.superdelivery.com/p/do/psl/?word=" + urllib.parse.quote(q)))
    m = re.search(r"全\s*([\d,]+)\s*社", t); return int(m.group(1).replace(",", "")) if m else 0
def kokubu(jan):
    t = http(f"http://netton.kokubu.jp/shop/g/g{jan}/", enc="cp932")
    title = (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0]
    return "】 ～" not in title and "】～" not in title, title[:60]

rows = list(csv.DictReader(open(T2, encoding="utf-8-sig")))
by = defaultdict(list)
for r in rows: by[(r["ブランド"] or r["メーカー"]).strip()].append(r)
def ok(b, rs): return b not in SKIP and not all(r["区分"].startswith("中国系") for r in rs)
top = [b for b, rs in sorted(by.items(), key=lambda kv: -len(kv[1])) if ok(b, rs)][:30]
def kw(b):
    m = re.match(r"^([^()（）]+)", b); return (m.group(1) if m else b).strip()

out = open(OUT, "w", encoding="utf-8")
# 卸問屋.com の JAN 検索が効くか（非ログイン詳細で JAN が見えた HIRO の品）
jt = oroshi("4580800477326") if "oroshi" in SITES else 0; out.write(json.dumps({"test": "oroshi_jan_search", "hits": jt}, ensure_ascii=False) + "\n"); print("oroshi JAN test", jt, flush=True)
for b in top:
    q = kw(b); rs = by[b]
    rec = {"brand": b, "q": q, "asins": len(rs), "jans": sum(bool(r["JAN"]) for r in rs), "区分": dict(Counter(r["区分"] for r in rs)),
           "大手": sum(bool(r["大手"]) for r in rs)}
    if "oroshi" in SITES:
        try: rec["卸問屋_件"] = oroshi(q)
        except Exception as e: rec["卸問屋_件"] = f"ERR {e}"
    if "sd" in SITES:
        try: rec["SD_社"] = sd(q)
        except Exception as e: rec["SD_社"] = f"ERR {e}"
    jans = [j for r in rs for j in re.split(r"[ |;,/]+", r["JAN"]) if re.match(r"^4[59]\d{11}$", j)][:10]
    hits = []
    for j in (jans if "kokubu" in SITES else []):
        try:
            ex, ti = kokubu(j)
            if ex: hits.append((j, ti))
        except Exception as e: hits.append((j, f"ERR {e}"))
    rec["国分_JAN照会"] = len(jans); rec["国分_JANあり"] = len([h for h in hits if not h[1].startswith("ERR")])
    rec["国分_例"] = hits[:3]
    if jt > 0:
        oh = 0
        for j in jans[:5]:
            try: oh += oroshi(j) > 0
            except Exception: pass
        rec["卸問屋_JAN照会"] = min(len(jans), 5); rec["卸問屋_JANあり"] = oh
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush(); print(json.dumps(rec, ensure_ascii=False), flush=True)
print("DONE", flush=True)
