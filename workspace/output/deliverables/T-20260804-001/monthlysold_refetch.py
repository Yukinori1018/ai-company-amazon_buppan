"""実測月販(Keepa monthlySold=Amazon"◯◯+個購入")を全商品ぶん取り直す。
出力: monthlysold.csv (asin, monthly_sold_real, main_rank)。実測が無い商品は空欄。
再開対応: 既存出力のASINはスキップ。トークン補充待ち。
"""
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
sys.path.insert(0, str(CODE))
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.amazon_data import KeepaBackend  # noqa

D = ROOT / "workspace/output/deliverables/T-20260804-001"
SRC = D / "maker_products.csv"
OUT = D / "monthlysold.csv"
PROG = D / "monthlysold_progress.log"
CHUNK = 90
MIN_TOKENS = 120


def log(m):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {m}"
    print(line, flush=True)
    with open(PROG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_tokens(kb, need=MIN_TOKENS):
    import requests
    while True:
        try:
            d = requests.get(f"https://api.keepa.com/token?key={kb.api_key}&domain=5", timeout=30).json()
        except Exception:
            time.sleep(10); continue
        left = d.get("tokensLeft", 0)
        if left >= need:
            return left
        wait = min(max((need - left) / (d.get("refillRate") or 20) * 60, 15), 300)
        log(f"  補充待ち left={left} → {wait:.0f}s")
        time.sleep(wait)


def main():
    asins = [r["asin"] for r in csv.DictReader(open(SRC, encoding="utf-8"))]
    asins = list(dict.fromkeys(asins))
    done = {}
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                done[r["asin"]] = r
        log(f"[resume] 既存 {len(done)}件スキップ")
    todo = [a for a in asins if a not in done]
    kb = KeepaBackend()
    log(f"実測月販 取り直し: 全{len(asins)} / 残{len(todo)} Keepa={kb.is_live}")

    rows = list(done.values())

    def flush():
        tmp = OUT.with_suffix(".csv.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["asin", "monthly_sold_real", "main_rank"])
            w.writeheader(); w.writerows(rows)
        tmp.replace(OUT)

    i = 0
    while i < len(todo):
        wait_tokens(kb)
        chunk = todo[i:i + CHUNK]
        i += CHUNK
        try:
            pay = kb._request(asin=",".join(chunk))
        except Exception as e:
            log(f"  err {e}"); time.sleep(10); continue
        for prod in pay.get("products", []):
            a = prod.get("asin")
            ms = prod.get("monthlySold")
            st = prod.get("stats") or {}
            cur = st.get("current") or []
            rank = cur[3] if len(cur) > 3 else ""
            rows.append({"asin": a,
                         "monthly_sold_real": int(ms) if isinstance(ms, (int, float)) and ms > 0 else "",
                         "main_rank": rank if rank and rank > 0 else ""})
        log(f"  {min(i,len(todo))}/{len(todo)} 実測有={sum(1 for r in rows if r['monthly_sold_real'])} tokensLeft={pay.get('tokensLeft')}")
        flush()
        time.sleep(0.2)
    flush()
    n_real = sum(1 for r in rows if r["monthly_sold_real"])
    log(f"=== 完了: {len(rows)}件 / 実測monthlySold取得 {n_real}件 ===")


if __name__ == "__main__":
    main()
