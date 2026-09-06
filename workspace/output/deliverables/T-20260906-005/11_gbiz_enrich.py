# -*- coding: utf-8 -*-
"""ギフトショー出展社(国内表記)に gBizINFO で法人番号・所在地・従業員数・HPを付ける。

T-20260906-005 / サトル / 2026-09-06
入力: workspace/output/agent_output/T-20260831-005/tigs102_出展社リスト_全件.csv (2,353行)
出力: 11_gbiz_enriched.csv

規約遵守: 1秒1リクエスト以下 (MIN_INTERVAL_SEC=1.15)。キャッシュで再問い合わせ回避。
"""
import csv, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request, urllib.error
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
sys.path.insert(0, str(REPO / "workspace/output/deliverables/T-20260831-004"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "gbizinfo", REPO / "workspace/output/deliverables/T-20260831-004/30_gbizinfo.py")
gb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gb)

OUT = REPO / "workspace/output/agent_output/T-20260906-005"
CSVP = REPO / "workspace/output/agent_output/T-20260831-005/tigs102_出展社リスト_全件.csv"

FOREIGN = re.compile(r"(CO\.,?\s*LTD|LIMITED|INC\.?|LLC|CORP|PTE|SDN|GMBH|S\.?A\.?$)", re.I)
KAKKO = ["株式会社", "有限会社", "合同会社", "合資会社", "合名会社", "（株）", "(株)",
         "（有）", "(有)", "㈱", "㈲", "一般社団法人", "公益社団法人", "協同組合", "事業協同組合"]


def is_ascii_heavy(s):
    a = sum(1 for c in s if ord(c) < 128)
    return a / max(1, len(s)) > 0.7


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for w in KAKKO:
        s = s.replace(w, "")
    return re.sub(r"[\s\-‐―–—・.,'\"()（）]", "", s).lower()


def query_name(s):
    """検索に投げる商号候補。／区切りの先頭、法人格除去、記号除去。"""
    s = unicodedata.normalize("NFKC", s)
    s = re.split(r"[／/|]", s)[0].strip()
    for w in KAKKO:
        s = s.replace(w, "")
    s = s.replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", "", s).strip()


rows = list(csv.DictReader(open(CSVP, encoding="utf-8")))
seen, pool = set(), []
for r in rows:
    e = (r.get("exhibitor") or "").strip()
    if not e or e in seen:
        continue
    seen.add(e)
    if FOREIGN.search(e) or is_ascii_heavy(e):
        continue                       # 海外表記は対象外(国内から仕入れられない)
    q = query_name(e)
    if len(q) < 2:
        continue
    pool.append((e, r.get("booth", ""), q))

print(f"pool(国内表記・重複除去)={len(pool)} / raw={len(rows)}", flush=True)

cli = gb.GBizInfo(cache_dir=OUT / "cache")
fout = open(OUT / "11_gbiz_enriched.csv", "w", encoding="utf-8", newline="")
w = csv.writer(fout)
w.writerow(["exhibitor", "booth", "query", "match_type", "n_exact",
            "corporate_number", "gbiz_name", "location", "postal_code",
            "employee_number", "company_url", "business_summary", "status"])

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else len(pool)
stat = {}
for i, (e, booth, q) in enumerate(pool[:LIMIT], 1):
    try:
        hits = cli.search_by_name(q, limit=100)
    except Exception as ex:
        print("ERR search", e, ex, flush=True)
        hits = []
    nq = norm(q)
    exact = []
    for h in hits:
        if h.get("status") == "閉鎖":
            continue
        if norm(h.get("name") or "") == nq:
            exact.append(h)
    # 出展社名に法人格が書いてある場合は、同じ法人格の法人を優先する
    ne = unicodedata.normalize("NFKC", e)
    want = None
    if "(株)" in ne or "株式会社" in ne or "㈱" in ne:
        want = "株式会社"
    elif "(有)" in ne or "有限会社" in ne or "㈲" in ne:
        want = "有限会社"
    elif "合同会社" in ne:
        want = "合同会社"
    if want and len(exact) > 1:
        pref = [h for h in exact if want in (h.get("name") or "")]
        if len(pref) >= 1:
            exact = pref
    if len(exact) == 1:
        mt = "exact1"
    elif len(exact) > 1:
        mt = "exact_multi"
    elif hits:
        mt = "partial_only"
    else:
        mt = "no_hit"
    stat[mt] = stat.get(mt, 0) + 1

    targets = exact[:3] if exact else []
    if not targets:
        w.writerow([e, booth, q, mt, 0, "", "", "", "", "", "", "", ""])
    for h in targets:
        cn = h.get("corporate_number")
        d = None
        try:
            d = cli.fetch_by_number(cn)
        except Exception as ex:
            print("ERR detail", cn, ex, flush=True)
        d = d or h
        w.writerow([e, booth, q, mt, len(exact), cn, d.get("name", ""),
                    d.get("location", ""), d.get("postal_code", ""),
                    d.get("employee_number", ""), d.get("company_url", ""),
                    (d.get("business_summary") or "").replace("\n", " ")[:200],
                    d.get("status", "")])
    fout.flush()
    if i % 25 == 0:
        cli.flush()
        print(f"{i}/{min(LIMIT,len(pool))} live={cli.live_calls} {stat}", flush=True)

cli.flush()
fout.close()
print("DONE", stat, "live_calls=", cli.live_calls, flush=True)
