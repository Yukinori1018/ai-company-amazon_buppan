# -*- coding: utf-8 -*-
"""第一陣候補20社だけを gBizINFO で名寄せし、法人番号・所在地・従業員数を確定させる。"""
import csv, importlib.util, unicodedata, re
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
spec = importlib.util.spec_from_file_location(
    "gbizinfo", REPO / "workspace/output/deliverables/T-20260831-004/30_gbizinfo.py")
gb = importlib.util.module_from_spec(spec); spec.loader.exec_module(gb)
OUT = REPO / "workspace/output/agent_output/T-20260906-005"

# (表示名, 検索語, 期待する所在地キーワード) 期待地で同名企業を切り分ける
T = [
    ("株式会社宇野刷毛ブラシ製作所", "宇野刷毛ブラシ製作所", "墨田"),
    ("有限会社大橋量器", "大橋量器", "大垣"),
    ("株式会社木村硝子店", "木村硝子店", "文京"),
    ("朝倉染布株式会社", "朝倉染布", "桐生"),
    ("廣田硝子株式会社", "廣田硝子", "墨田"),
    ("河野製紙株式会社", "河野製紙", "高知"),
    ("守田漆器株式会社", "守田漆器", "加賀"),
    ("池本刷子工業株式会社", "池本刷子工業", "東大阪"),
    ("楠橋紋織株式会社", "楠橋紋織", "今治"),
    ("側島製罐株式会社", "側島製罐", "大治"),
    ("金野タオル株式会社", "金野タオル", "泉佐野"),
    ("本野はきもの工業", "本野はきもの", "日田"),
    ("株式会社北尾化粧品部", "北尾化粧品部", "生野"),
    ("株式会社清水硝子", "清水硝子", "葛飾"),
    ("木内籐材工業株式会社", "木内籐材工業", "文京"),
    ("小野甚味噌醤油醸造株式会社", "小野甚味噌醤油醸造", "京丹後"),
    ("七福タオル株式会社", "七福タオル", "今治"),
    ("株式会社高柳製茶", "高柳製茶", "牧之原"),
    ("亀崎染工有限会社", "亀崎染工", "串木野"),
    ("株式会社ビスポーク", "ビスポーク", "さいたま"),
]

cli = gb.GBizInfo(cache_dir=OUT / "cache")
w = csv.writer(open(OUT / "31_gbiz_targeted.csv", "w", encoding="utf-8", newline=""))
w.writerow(["display", "term", "n_hits", "corporate_number", "gbiz_name",
            "location", "employee_number", "company_url", "status", "gbiz_url"])
for disp, term, loc in T:
    hits = cli.search_by_name(term, limit=100)
    cands = [h for h in hits if h.get("status") != "閉鎖"]
    pick = [h for h in cands if loc in (h.get("location") or "")]
    if not pick:
        pick = cands[:1]
    rows = 0
    for h in pick[:2]:
        cn = h.get("corporate_number")
        d = cli.fetch_by_number(cn) or h
        w.writerow([disp, term, len(cands), cn, d.get("name", ""), d.get("location", ""),
                    d.get("employee_number", ""), d.get("company_url", ""), d.get("status", ""),
                    f"https://info.gbiz.go.jp/hojin/ichiran?hojinBango={cn}"])
        print(disp, cn, d.get("name"), d.get("location"), "従業員=", d.get("employee_number"), flush=True)
        rows += 1
    if rows == 0:
        w.writerow([disp, term, len(cands), "", "", "", "", "", "", ""])
        print(disp, "NO MATCH", flush=True)
cli.flush()
print("live_calls=", cli.live_calls)
