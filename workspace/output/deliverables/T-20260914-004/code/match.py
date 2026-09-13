#!/usr/bin/env python3
"""T-2: 需要先行リスト（T-1 t2_input 3,255 ASIN）× NETSEA raw（2026-08-31 harvest）の照合。0 API call。

確度:
  JAN一致          … T-1 の eanList と NETSEA 規格の JAN が一致
  JAN一致(Keepa経由) … NETSEA JAN を Keepa が引いた ASIN が T-1 の ASIN と一致（T-20260831-006 candidates）
  型番一致          … Keepa の model/partNumber（英数混在・5文字以上）が NETSEA 商品名/規格名に現れる
  名称近似          … ブランド名が NETSEA 商品名に現れ、かつタイトルの文字3-gram Jaccard ≥ 0.25
"""
import csv, glob, gzip, json, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
D = REPO / "workspace/output/deliverables"
T2 = D / "T-20260914-002/out/t2_input.csv"
RAW = REPO / "workspace/output/agent_output/T-20260914-002/t1_raw"
SPECS = HERE / "netsea_specs.jsonl"
CAND = D / "T-20260831-006/out/candidates.csv"
OUT = HERE / "matches.jsonl"

def nk(s): return unicodedata.normalize("NFKC", s or "").upper()
def alnum(s): return re.sub(r"[^0-9A-Z]", "", nk(s))
def grams(s, n=3):
    s = re.sub(r"\s+", "", nk(s)); return {s[i:i+n] for i in range(max(len(s)-n+1, 0))}
def jac(a, b): return len(a & b) / len(a | b) if a and b else 0.0
TOK = re.compile(r"[0-9A-Z][0-9A-Z\-_/\.]{3,}[0-9A-Z]")
def model_tokens(text):
    out = set()
    for t in TOK.findall(nk(text)):
        a = alnum(t)
        if len(a) >= 5 and re.search(r"\d", a) and re.search(r"[A-Z]", a): out.add(a)
    return out

prods = {}
for f in sorted(RAW.glob("prod_*.json.gz")):
    for p in json.loads(gzip.decompress(f.read_bytes())).get("products") or []:
        prods[p["asin"]] = p
t2 = list(csv.DictReader(open(T2, encoding="utf-8-sig")))

jan_idx, model_idx, specs = defaultdict(list), defaultdict(list), []
with open(SPECS, encoding="utf-8") as f:
    for i, line in enumerate(f):
        d = json.loads(line); specs.append(d)
        if d["jan"]: jan_idx[d["jan"].lstrip("0")].append(i)
        for t in model_tokens(f"{d['name']} {d['label'] or ''} {d['spec'] or ''}"): model_idx[t].append(i)
print("specs", len(specs), "jan", len(jan_idx), "model tokens", len(model_idx), file=sys.stderr)
cand_by_asin = defaultdict(list)
for r in csv.DictReader(open(CAND, encoding="utf-8-sig")):
    if r["ASIN"]: cand_by_asin[r["ASIN"]].append(r["JAN"].lstrip("0"))

# 名称近似用: 商品名（重複除去）→ 規格 index
name_specs = defaultdict(list)
for i, d in enumerate(specs): name_specs[nk(d["name"])].append(i)
names = list(name_specs)
def brand_keys(r):
    ks = set()
    for b in (r["ブランド"], r["メーカー"]):
        b = nk(b).strip()
        for part in re.split(r"[()（）\s/・]+", b):
            part = part.strip()
            if len(part) >= 3 and part not in {"株式会社", "有限会社", "JAPAN", "OFFICIAL"}: ks.add(part)
    return ks
brands = defaultdict(set)
for r in t2:
    for k in brand_keys(r): brands[k].add(r["ASIN"])
brand_names = defaultdict(list)  # brand key -> names containing it
for k in brands:
    ascii_ = k.isascii()
    pat = re.compile(r"(?<![0-9A-Z])" + re.escape(k) + r"(?![0-9A-Z])") if ascii_ else None
    for nm in names:
        if (pat.search(nm) if ascii_ else (k in nm)): brand_names[k].append(nm)
print("brands", len(brands), "with netsea names", sum(1 for k in brand_names if brand_names[k]), file=sys.stderr)

with open(OUT, "w", encoding="utf-8") as w:
    for r in t2:
        p = prods.get(r["ASIN"], {})
        jans = {j.lstrip("0") for j in re.split(r"[ |;,/]+", r["JAN"]) if j} | {e.lstrip("0") for e in (p.get("eanList") or [])}
        hits = []
        for j in jans:
            for i in jan_idx.get(j, []): hits.append((i, "JAN一致"))
        if not hits:
            for j in cand_by_asin.get(r["ASIN"], []):
                for i in jan_idx.get(j, []): hits.append((i, "JAN一致(Keepa経由)"))
        if not hits:
            mts = set()
            for k in ("model", "partNumber"):
                a = alnum(p.get(k) or "")
                if len(a) >= 5 and re.search(r"\d", a) and re.search(r"[A-Z]", a): mts.add(a)
            for t in mts:
                for i in model_idx.get(t, []): hits.append((i, "型番一致"))
        if not hits:
            tg = grams(r["タイトル"])
            best = []
            for k in brand_keys(r):
                for nm in brand_names.get(k, []):
                    s = jac(tg, grams(nm))
                    if s >= 0.25: best.append((s, nm))
            for s, nm in sorted(best, reverse=True)[:3]:
                for i in name_specs[nm][:5]: hits.append((i, f"名称近似({s:.2f})"))
        if hits:
            seen = set(); ms = []
            for i, how in hits:
                if i in seen: continue
                seen.add(i); ms.append({**specs[i], "how": how})
            w.write(json.dumps({"asin": r["ASIN"], "t2": r, "matches": ms}, ensure_ascii=False) + "\n")
