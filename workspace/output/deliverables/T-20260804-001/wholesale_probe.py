"""実仕入値の実態調査（Phase C）。
優先55社の代表商品について、Keepaで JAN と 参考価格(listPrice/定価) を取り直し、
NETSEA(卸API)で JAN 照合して【実際の卸価格(税抜)・上代】を取得する。
NETSEAに無い分は空欄。実卸値はメーカー見積(=実連絡§4.1)でしか確定しない旨を明示。
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

from adapters.amazon_data import KeepaBackend, _product_to_amazon, _keepa_price_yen  # noqa
from adapters.netsea import NetseaClient  # noqa

D = ROOT / "workspace/output/deliverables/T-20260804-001"
OUT_CSV = D / "wholesale_probe.csv"
LOG = D / "wholesale_probe.log"


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def list_price_from_raw(prod):
    """Keepa raw から参考価格(定価/上代)を拾う。無ければ None。"""
    for key in ("listPrice",):
        v = prod.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return _keepa_price_yen(v)
    # csv[4] = LISTPRICE 履歴（[time,price,...]）の最終値
    try:
        arr = (prod.get("csv") or [])[4]
        if arr:
            last = arr[-1]
            if last and last > 0:
                return _keepa_price_yen(last)
    except (IndexError, TypeError):
        pass
    return None


def main():
    if LOG.exists():
        LOG.unlink()
    # 優先55社（連絡先取得済＝ledgerで tel/email/url いずれか有）の代表ASIN
    led = list(csv.DictReader(open(D / "maker_ledger.csv", encoding="utf-8")))
    targets = [(r["maker"], r["top_asin"]) for r in led
               if (r["maker_tel"] or r["maker_email"] or r["maker_url"]) and r["top_asin"]]
    log(f"実査対象: 優先{len(targets)}社の代表商品")

    kb = KeepaBackend()
    net = NetseaClient()
    log(f"Keepa={kb.is_live} NETSEA={net.is_live}")

    rows = []
    asins = [a for _, a in targets]
    amap = {a: m for m, a in targets}
    # Keepaで JAN + 定価 を取得（15件ずつ）
    jan_of = {}
    price_of = {}
    listp_of = {}
    i = 0
    while i < len(asins):
        chunk = asins[i:i + 15]
        i += 15
        try:
            pay = kb._request(asin=",".join(chunk))
        except Exception as e:
            log(f"  keepa err: {e}"); time.sleep(15); continue
        for prod in pay.get("products", []):
            ap = _product_to_amazon(prod)
            if ap is None:
                continue
            eans = [str(c) for c in (prod.get("eanList") or [])]
            jan_of[ap.asin] = eans[0] if eans else ""
            price_of[ap.asin] = ap.current_price
            listp_of[ap.asin] = list_price_from_raw(prod)
        log(f"  Keepa {min(i,len(asins))}/{len(asins)} tokensLeft={pay.get('tokensLeft')}")
        time.sleep(1)

    # NETSEAで JAN 照合 → 実卸価格
    n_hit = 0
    for maker, asin in targets:
        jan = jan_of.get(asin, "")
        wholesale = None; jouba = None; supplier = ""
        if jan:
            try:
                hits = net.search(jan_code=jan, results=5)
            except Exception:
                hits = []
            best = None
            for h in hits:
                p = getattr(h, "price", None)
                if p and (best is None or p < best):
                    best = p; supplier = getattr(h, "name", "")[:30]
            if best:
                wholesale = best; n_hit += 1
        rows.append({
            "maker": maker, "asin": asin, "jan": jan,
            "amazon_price": price_of.get(asin, ""),
            "list_price_teika": listp_of.get(asin) or "",
            "netsea_wholesale_excl": wholesale or "",
            "netsea_supplier": supplier,
            "note": "NETSEA実卸(税抜)" if wholesale else "NETSEA該当なし＝実卸はメーカー見積必要",
        })
        time.sleep(0.2)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    n_list = sum(1 for r in rows if r["list_price_teika"])
    log(f"=== 完了: {len(rows)}社 / NETSEA実卸ヒット{n_hit}社 / 定価取得{n_list}社 ===")


if __name__ == "__main__":
    main()
